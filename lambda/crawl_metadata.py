"""Harvest ALL decision metadata for a date range, defeating the 100-row cap by
recursive sub-splitting: court -> decision-type -> proceeding -> judge. Only
splits a bucket when it comes back capped (==100), so sparse days stay cheap.

Completeness: decision-type and proceeding are clean partitions, so court x dtype
x proceeding is <100 on virtually any single day; judge is the last-resort split.
Any leaf STILL ==100 after all splits is logged as a possible undercount.

Resumable: writes metadata/<YYYY>/<YYYY-MM-DD>.json per day; existing files are
skipped. Empty days write [] so they aren't retried.

Usage:  python crawl_metadata.py 2024-01-01 2026-07-03 [workers]
Output: metadata/<year>/<date>.json  (list of raw decision dicts, deduped by DecisionID)
"""
from __future__ import annotations

import json
import queue
import re
import sys
import threading
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, r"C:\zot-vaod\zot-vaod-main\court_scraper")
from court_scraper.client import parse_form_fields  # noqa: E402
from demo_raw_dump import Session, raw_store, court_options, QUERY_URL, XHR_HEADERS  # noqa: E402

CAP = 100
DTYPES = ["2"]                         # פסק דין ONLY (1/2/3/4 = החלטה/פסק דין/הכרעת דין/גזר דין)
# A day we KNOW is heavily populated: an all-courts query for it must return rows.
# Used as a liveness probe — if THIS comes back empty, the site is blocking us.
CONTROL_DAY = "23/02/2025"
OPT_RE = re.compile(r"value='([^']*)'\s*>([^<]+)</option>")
# Previously value='(-?\d+)' - numeric-only, which silently matched ZERO
# options for GetJudgeCB specifically: judge option values are strings like
# "070058649@GOV.IL", not bare integers. proceeding/case-type/case-interest
# IDs are numeric so this widened pattern still matches them identically -
# strictly more permissive, not a behavior change for existing callers.
_tl = threading.local()

# Cache the control-probe result for a short window instead of re-querying it
# fresh for every single ambiguous-empty slice. On sparse years ~73% of slices
# are genuinely empty, so under real concurrency MANY threads were firing this
# exact same "all courts, one fixed day" query near-simultaneously - identical
# repeated requests are exactly the pattern a WAF flags, and once the control
# query itself starts getting throttled, EVERY empty slice looks "blocked",
# cascading into a false mass-block (confirmed: dense-year pipelines that rarely
# hit this branch saw zero such errors under the same load). A short shared
# cache still catches a REAL block within seconds, but stops the self-inflicted
# hammering of one specific query.
_control_lock = threading.Lock()
_control_cache = {"ts": 0.0, "ok": True}
_CONTROL_TTL_SEC = 20.0


def control_probe_ok(s: "Crawler") -> bool:
    with _control_lock:
        if time.time() - _control_cache["ts"] < _CONTROL_TTL_SEC:
            return _control_cache["ok"]
    ok = bool(s.query(CONTROL_DAY, court="-1"))
    with _control_lock:
        _control_cache["ts"] = time.time()
        _control_cache["ok"] = ok
    return ok


import random  # noqa: E402
import concurrent.futures  # noqa: E402

import httpx  # noqa: E402
from curl_cffi import requests as ccffi  # noqa: E402
from curl_cffi.requests.exceptions import RequestException as CCError  # noqa: E402
from court_scraper.client import (  # noqa: E402
    HOME_URL, decode_response_text, parse_form_fields as _pff,
)

RETRIES = 8
NET_ERRORS = (httpx.HTTPError, CCError)


class HardTimeoutError(Exception):
    """A network call didn't return even though it had its own timeout= set.
    curl_cffi/libcurl have a documented bug class (curl#9272, curl#18216)
    where a stuck DNS resolution can silently bypass the configured timeout
    and wedge the whole session - confirmed live via netstat showing zero
    open connections while the process sat non-responsive. There's no way
    to cancel the underlying native call, so the worker thread is abandoned
    (a harmless leak - the process is expected to exit shortly after this is
    raised) and this is intentionally NOT a subclass of the errors the
    retry/rebuild loops below already catch: retrying just re-triggers the
    same wedge, so callers should let this crash the process instead."""


# Dedicated pool ONLY for enforcing the hard wall-clock bound below - reusing
# a worker's own thread would defeat the point (you can't time yourself out).
_NET_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=64, thread_name_prefix="net-hardtimeout")
_HARD_TIMEOUT_SLACK = 20  # let curl's own timeout= win in the normal case


def _hard_call(fn, *args, timeout, **kwargs):
    """Run fn(*args, timeout=timeout, **kwargs) with a hard outer bound of
    timeout+slack. In the normal case curl's own timeout fires first and its
    exception just passes through. Only when curl's timeout itself fails to
    fire (the actual observed bug) does this raise HardTimeoutError."""
    fut = _NET_EXECUTOR.submit(fn, *args, timeout=timeout, **kwargs)
    try:
        return fut.result(timeout=timeout + _HARD_TIMEOUT_SLACK)
    except concurrent.futures.TimeoutError:
        raise HardTimeoutError(
            f"{getattr(fn, '__name__', fn)} did not return within "
            f"{timeout + _HARD_TIMEOUT_SLACK}s (configured timeout={timeout}s) - "
            "treating as a stuck DNS/connect (curl#9272/curl#18216), not retrying"
        ) from None


def _hard_bound(fn, *args, bound, **kwargs):
    """Like _hard_call but for calls (e.g. close()) that take no timeout= of
    their own - still enforces a hard wall-clock bound without injecting an
    unsupported kwarg into fn."""
    fut = _NET_EXECUTOR.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=bound)
    except concurrent.futures.TimeoutError:
        raise HardTimeoutError(
            f"{getattr(fn, '__name__', fn)} did not return within {bound}s - "
            "treating as a stuck DNS/connect/close (curl#9272/curl#18216), not retrying"
        ) from None

# Global rate gate: WAF blocks on bursts, so cap the WHOLE process to a steady
# request rate regardless of worker count. Every outbound HTTP call waits here.
RATE_PER_SEC = float(__import__("os").environ.get("NGCS_RPS", "6"))
_rate_lock = threading.Lock()
_next_slot = [0.0]


def rate_gate():
    with _rate_lock:
        now = time.monotonic()
        due = max(now, _next_slot[0])
        _next_slot[0] = due + 1.0 / RATE_PER_SEC
    wait = due - now
    if wait > 0:
        time.sleep(wait + random.uniform(0, 0.05))  # tiny jitter, no lockstep


class CurlClient:
    """Drop-in replacement for NgcsClient's transport, backed by curl_cffi with
    Chrome TLS impersonation (the site's WAF blocks plain-httpx fingerprints)."""

    def __init__(self):
        self._client = self  # crawler reaches transport via `.client._client`
        self._s = ccffi.Session(impersonate="chrome", timeout=90)
        self._home_fields = None  # cached homepage postback fields (viewstate)

    # transport surface used by the crawler ---------------------------------
    def get(self, url, timeout=90, **kw):
        return _hard_call(self._s.get, url, timeout=timeout, allow_redirects=True, **kw)

    def post(self, url, data=None, content=None, headers=None, timeout=90, **kw):
        body = content if content is not None else data
        return _hard_call(self._s.post, url, data=body, headers=headers, timeout=timeout,
                           allow_redirects=True, **kw)

    def close(self):
        try:
            _hard_bound(self._s.close, bound=30)
        except HardTimeoutError:
            raise  # unrecoverable wedge - propagate, don't silently swallow like a normal close error
        except Exception:
            pass

    # NgcsClient API ---------------------------------------------------------
    def navigate_to_decision_search(self):
        # Cache the homepage GET viewstate once per session; reuse it for every
        # reset postback. Cuts the per-query cost from 4 requests to 3.
        if self._home_fields is None:
            rate_gate()
            r = _hard_call(self._s.get, HOME_URL, timeout=90, allow_redirects=True)
            r.raise_for_status()
            f = _pff(decode_response_text(r))
            f["__EVENTTARGET"] = "Header1$UpperMenu1$btnVerdictLocalization"
            f["__EVENTARGUMENT"] = ""
            self._home_fields = f
        rate_gate()
        r = _hard_call(self._s.post, HOME_URL, data=self._home_fields, timeout=90, allow_redirects=True)
        r.raise_for_status()
        return decode_response_text(r)


class Crawler(Session):
    """A session that can search with the full parameter set and enumerate sub-options.

    Every network call is retried with backoff; a poisoned session is rebuilt.
    Bootstrap is retried too, so transient server disconnects never kill a worker.
    """

    def __init__(self):
        self.client = None
        self._rebuild()

    def _rebuild(self):
        """(Re)create the underlying client and re-open the search page, with retries."""
        for attempt in range(RETRIES):
            try:
                if self.client is not None:
                    try:
                        self.client.close()
                    except HardTimeoutError:
                        raise  # unrecoverable wedge - don't swallow, let it crash the process
                    except Exception:
                        pass
                self.client = CurlClient()
                self.page_html = self.client.navigate_to_decision_search()
                self.fields = parse_form_fields(self.page_html)
                self.fields.pop("LocateByParameters1:ddlSelectCaseType", None)
                self.fields.pop("LocateByParameters1:ddlSelectCaseInterest", None)
                return
            except (*NET_ERRORS, json.JSONDecodeError, RuntimeError):
                time.sleep(min(2 * (attempt + 1), 15))  # linear backoff (aggressive)
        raise RuntimeError("could not bootstrap session after retries")

    def _navigate(self):
        for attempt in range(RETRIES):
            try:
                return self.client.navigate_to_decision_search()
            except NET_ERRORS:
                # rebuild rarely — churny session recreation floods the per-IP
                # connection cap, which is what actually triggers the WAF block
                if attempt >= 4:
                    self._rebuild()
                else:
                    time.sleep(1.5 * (attempt + 1))  # linear backoff (aggressive)
        raise RuntimeError("navigate failed after retries")

    def _post(self, url, retries=None, timeout=90, **kw):
        """POST with retries; rebuilds the session on repeated failure.

        retries/timeout are overridable (default RETRIES=8, 90s each - up to
        ~13min worst case) because a self-diagnostic stack dump caught two
        worker threads simultaneously stuck cycling through this exact retry
        loop for a single failing document-viewer request each - not an
        actual hang, curl's own timeout WAS firing each time (that's why it
        landed in this except block's time.sleep, not a HardTimeoutError) -
        just slow enough, on a genuinely-failing document, to look identical
        to a hang from the outside. Best-effort callers (document fetch
        fallbacks, where failure just means "no document for this pair" and
        is retried on a future pass) should pass a much smaller bound so one
        bad document can't block a worker thread for minutes."""
        n = retries if retries is not None else RETRIES
        for attempt in range(n):
            try:
                rate_gate()
                r = self.client._client.post(url, timeout=timeout, **kw)
                r.raise_for_status()
                return r
            except NET_ERRORS:
                if attempt == n - 1:
                    raise
                time.sleep(1.5 * (attempt + 1))  # linear backoff (aggressive)
                if attempt >= 4:  # rebuild rarely (connection-cap churn = block)
                    self._rebuild()
        raise RuntimeError("unreachable")

    def _prime(self, court, proc="-1", casetype="-1", caseinterest="-1"):
        """Register the dependent-dropdown chain in server session so posted
        proceeding/case-type/case-interest filter values actually take effect
        (same session-priming requirement the court filter has)."""
        self._post(f"{QUERY_URL}/GetProceedingCB",
                   content=json.dumps({"courtID": int(court), "proceedingID": int(proc)}),
                   headers=XHR_HEADERS)
        if casetype != "-1":
            self._post(f"{QUERY_URL}/GetCaseTypeCB",
                       content=json.dumps({"courtID": int(court), "proceedingID": int(proc),
                                           "caseTypeID": int(casetype), "caseInterestID": -1}),
                       headers=XHR_HEADERS)
        if caseinterest != "-1":
            self._post(f"{QUERY_URL}/GetCaseInterestCB",
                       content=json.dumps({"courtID": int(court), "proceedingID": int(proc),
                                           "caseTypeID": int(casetype), "caseInterestID": int(caseinterest)}),
                       headers=XHR_HEADERS)

    def query(self, day, court, dtype="-1", proc="-1", casetype="-1", caseinterest="-1"):
        self.fields = parse_form_fields(self._navigate())
        self.fields.pop("LocateByParameters1:ddlSelectCaseType", None)
        self.fields.pop("LocateByParameters1:ddlSelectCaseInterest", None)
        if court != "-1":
            self._prime(court, proc, casetype, caseinterest)
        f = dict(self.fields)
        f.update({
            "hdnSelectedTab": "1",
            "LocateByParameters1:ddlSelectCourt": court,
            "LocateByParameters1:ddlSelectProceeding": proc,
            "LocateByParameters1:ddlSelectCaseType": casetype,
            "LocateByParameters1:ddlSelectCaseInterest": caseinterest,
            "LocateByParameters1:ddlJudgeName": "-1",
            "LocateByParameters1:ddlDecisionType": dtype,
            "LocateByParameters1:dateFrom": day,
            "LocateByParameters1:DateTo": day,
            "__EVENTTARGET": "ButtonsGroup1$btnLocate",
            "__EVENTARGUMENT": "",
        })
        r = self._post(QUERY_URL, data=f)
        rows = json.loads(raw_store(r.content.decode("windows-1255", "replace")) or "[]")
        try:  # heartbeat: proves the crawl is actively issuing queries (not hung)
            (Path(__file__).parent / "heartbeat").write_text(str(time.time()))
        except Exception:
            pass
        return rows

    def query_full(self, day, court, dtype="-1", proc="-1", casetype="-1", caseinterest="-1"):
        """Like query() but also returns the raw response html (needed for the
        follow-up btnDownloadWordDocs postback's viewstate - see
        download2325_handler.py). Duplicates query()'s POST rather than
        reusing it because query() only returns the parsed rows. Accepts the
        full parameter set so query_full_deep() can call it at every level of
        the same recursive cap-split query()/crawl_slice_court() already use -
        query_full alone (dtype=-1 only) silently truncated at CAP for any
        busy court+day, since it had no fallback (confirmed for real: major
        courts in 2023-2025 hit this on essentially every day)."""
        self.fields = parse_form_fields(self._navigate())
        self.fields.pop("LocateByParameters1:ddlSelectCaseType", None)
        self.fields.pop("LocateByParameters1:ddlSelectCaseInterest", None)
        if court != "-1":
            self._prime(court, proc, casetype, caseinterest)
        f = dict(self.fields)
        f.update({
            "hdnSelectedTab": "1",
            "LocateByParameters1:ddlSelectCourt": court,
            "LocateByParameters1:ddlSelectProceeding": proc,
            "LocateByParameters1:ddlSelectCaseType": casetype,
            "LocateByParameters1:ddlSelectCaseInterest": caseinterest,
            "LocateByParameters1:ddlJudgeName": "-1",
            "LocateByParameters1:ddlDecisionType": dtype,
            "LocateByParameters1:dateFrom": day,
            "LocateByParameters1:DateTo": day,
            "__EVENTTARGET": "ButtonsGroup1$btnLocate",
            "__EVENTARGUMENT": "",
        })
        r = self._post(QUERY_URL, data=f)
        if "LocateDecisionOutput.aspx" not in str(r.url):
            return None, []
        html = r.content.decode("windows-1255", "replace")
        return html, json.loads(raw_store(html) or "[]")

    def query_full_deep(self, day, court, html0=None, rows0=None):
        """Like query_full(day, court) but beats the CAP the same way
        crawl_slice_court/collect_day do: only recurses into dtype/proceeding/
        case-type/case-interest when a bucket comes back capped. Returns a
        list of (html, rows) leaf results instead of one - each leaf's rows
        must be downloaded using ITS OWN html/viewstate, not a shared one
        (each sub-query is a distinct search-result state server-side).

        html0/rows0: pass the caller's ALREADY-fetched top-level query_full()
        result if it has one (callers that only invoke this once they've seen
        a capped top-level result always do) - re-issuing that exact same
        query here just to throw the answer away was a needless second
        request AND a fragility: if THAT redundant repeat happened to come
        back transiently empty (seen live: a capped 100-row result followed
        immediately by a 0-row repeat of the identical query), the "floor"
        write below silently replaced a known-real 100+ rows with 0."""
        leaves: list[tuple[str, list[dict]]] = []
        if html0 is None:
            html0, rows0 = self.query_full(day, court)
        if len(rows0) < CAP:
            leaves.append((html0, rows0))
            return leaves
        leaves.append((html0, rows0))  # floor: keep what we got even though capped
        for dt in DTYPES:
            html_dt, rows_dt = self.query_full(day, court, dtype=dt)
            if len(rows_dt) < CAP:
                leaves.append((html_dt, rows_dt)); continue
            leaves.append((html_dt, rows_dt))  # floor
            for pr in self.proceedings(court):
                html_pr, rows_pr = self.query_full(day, court, dtype=dt, proc=pr)
                if len(rows_pr) < CAP:
                    leaves.append((html_pr, rows_pr)); continue
                leaves.append((html_pr, rows_pr))  # floor
                for ct in self.case_types(court, pr):
                    html_ct, rows_ct = self.query_full(day, court, dtype=dt, proc=pr, casetype=ct)
                    if len(rows_ct) < CAP:
                        leaves.append((html_ct, rows_ct)); continue
                    leaves.append((html_ct, rows_ct))  # floor
                    for cint in self.case_interests(court, pr, ct):
                        html_ci, rows_ci = self.query_full(day, court, dtype=dt, proc=pr,
                                                            casetype=ct, caseinterest=cint)
                        leaves.append((html_ci, rows_ci))  # finest axis: always keep, capped or not
        return leaves

    def _opts(self, method, payload):
        r = self._post(f"{QUERY_URL}/{method}", content=json.dumps(payload), headers=XHR_HEADERS)
        html = json.loads(r.content.decode("windows-1255"))["d"]
        return [v for v, _ in OPT_RE.findall(html) if v != "-1"]

    def proceedings(self, court):
        return self._opts("GetProceedingCB", {"courtID": int(court), "proceedingID": -1})

    def case_types(self, court, proc):
        return self._opts("GetCaseTypeCB", {"courtID": int(court), "proceedingID": int(proc),
                                            "caseTypeID": -1, "caseInterestID": -1})

    def case_interests(self, court, proc, casetype):
        return self._opts("GetCaseInterestCB", {"courtID": int(court), "proceedingID": int(proc),
                                                "caseTypeID": int(casetype), "caseInterestID": -1})


def session() -> Crawler:
    if not hasattr(_tl, "s"):
        _tl.s = Crawler()
    return _tl.s


def collect_day(day: str, warn: list) -> list[dict]:
    """Return all deduped decisions for one day, recursively splitting capped buckets."""
    s = session()
    out: dict[int, dict] = {}
    qn = [0]

    def q(**k):
        qn[0] += 1
        if qn[0] % 50 == 0:
            print(f"    ...{day} in progress: {qn[0]} queries, {len(out)} decisions so far",
                  flush=True)
        return s.query(day, **k)

    def add(rows):
        for r in rows:
            out[r["DecisionID"]] = r

    # Fast path: one all-courts query. If the whole day is under the cap, we're
    # done in a single request instead of sweeping 89 courts (huge win for
    # weekends / sparse / holiday days).
    allc = q(court="-1")
    if len(allc) < CAP:
        add(allc)
        return list(out.values())

    # Recursive split to beat the 100-cap: court -> decision-type -> proceeding
    # -> case-type -> case-interest. Only split a bucket when it comes back capped.
    # ALWAYS add the rows we got (floor) so nothing is ever dropped; warn if a
    # leaf still caps after the finest available axis.
    for court, _name in COURTS:
        crows = q(court=court)
        if len(crows) < CAP:
            add(crows); continue
        for dt in DTYPES:
            drows = q(court=court, dtype=dt)
            if len(drows) < CAP:
                add(drows); continue
            for pr in s.proceedings(court):
                prows = q(court=court, dtype=dt, proc=pr)
                if len(prows) < CAP:
                    add(prows); continue
                add(prows)  # floor: keep the 100 even while we split deeper
                for ct in s.case_types(court, pr):
                    ctrows = q(court=court, dtype=dt, proc=pr, casetype=ct)
                    if len(ctrows) < CAP:
                        add(ctrows); continue
                    add(ctrows)  # floor
                    cis = s.case_interests(court, pr, ct)
                    if not cis:
                        warn.append(f"{day} c={court} dt={dt} pr={pr} ct={ct} CAPPED (no case-interest axis)")
                        continue
                    for cint in cis:
                        cirows = q(court=court, dtype=dt, proc=pr, casetype=ct, caseinterest=cint)
                        add(cirows)  # floor at the finest axis
                        if len(cirows) >= CAP:
                            warn.append(f"{day} c={court} dt={dt} pr={pr} ct={ct} ci={cint} STILL CAPPED")
    return list(out.values())


def crawl_slice(day: str, court: str, dtype: str, s: "Crawler | None" = None):
    """One (court, decision-type) for one day — the finest-grained work unit,
    for the Lambda fan-out. Same proceeding->case-type->case-interest descent and
    floor-add as collect_day, scoped to a single court+dtype so it fits well
    inside a 15-min Lambda even on the busiest day. day is 'DD/MM/YYYY'.
    Returns (rows, warnings). Pass an existing session via `s` to reuse it across
    calls (e.g. a per-thread session persisted across a Lambda's warm invocations -
    avoids re-paying the ~3-4 request session bootstrap for every single slice);
    omit it to get the old create-and-close-your-own-session behavior."""
    own_session = s is None
    if own_session:
        s = Crawler()
    out: dict[int, dict] = {}
    warn: list = []

    def add(rows):
        for r in rows:
            out[r["DecisionID"]] = r

    try:
        drows = s.query(day, court, dtype=dtype)
        if len(drows) < CAP:
            add(drows)
        else:
            for pr in s.proceedings(court):
                prows = s.query(day, court, dtype=dtype, proc=pr)
                if len(prows) < CAP:
                    add(prows); continue
                add(prows)
                for ct in s.case_types(court, pr):
                    ctrows = s.query(day, court, dtype=dtype, proc=pr, casetype=ct)
                    if len(ctrows) < CAP:
                        add(ctrows); continue
                    add(ctrows)
                    cis = s.case_interests(court, pr, ct)
                    if not cis:
                        warn.append(f"{day} c={court} dt={dtype} pr={pr} ct={ct} CAPPED (no case-interest axis)")
                        continue
                    for cint in cis:
                        cirows = s.query(day, court, dtype=dtype, proc=pr, casetype=ct, caseinterest=cint)
                        add(cirows)
                        if len(cirows) >= CAP:
                            warn.append(f"{day} c={court} dt={dtype} pr={pr} ct={ct} ci={cint} STILL CAPPED")
        # Integrity guard: an empty result is ambiguous — either the day/court/type
        # genuinely has nothing, OR the site blocked/throttled us and served an empty
        # page. The second silently corrupts the crawl (a blocked response is a
        # "successful" empty file, so it never hits the DLQ — this bit us at high
        # concurrency). So on an empty result, probe a control query we KNOW is
        # populated; if that's empty too, we're blocked -> raise so the message
        # retries and lands in the DLQ instead of persisting a false empty.
        result = list(out.values())
        if not result and not control_probe_ok(s):
            raise RuntimeError(f"BLOCKED: {day} c={court} d={dtype} empty AND control probe empty")
        return result, warn
    finally:
        if own_session:
            s.close()


def crawl_slice_court(day: str, court: str, s: "Crawler | None" = None):
    """One court for one day, ALL decision types together — the SAME per-court
    logic collect_day() already uses (query(day, court) defaults dtype='-1',
    i.e. every type in one request), extracted as its own Lambda-fan-out work
    unit instead of collect_day's whole-day sequential loop.

    Supersedes crawl_slice(day, court, dtype) as the crawl's granularity: for
    the years this thin (~3,500-5,000 decisions/year across ALL 89 courts),
    a combined query almost never hits CAP, so this cuts total slices ~4x
    (no more x4 dtype fan-out) with ZERO extra site load - same descent-and-
    floor-add fallback as crawl_slice/collect_day if a court+day IS capped.

    Returns (rows, warnings). Pass an existing session via `s` to reuse it
    (see crawl_slice's docstring - same reasoning)."""
    own_session = s is None
    if own_session:
        s = Crawler()
    out: dict[int, dict] = {}
    warn: list = []

    def add(rows):
        for r in rows:
            out[r["DecisionID"]] = r

    try:
        crows = s.query(day, court)  # dtype="-1" default: all types in one request
        if len(crows) < CAP:
            add(crows)
        else:
            for dt in DTYPES:
                drows = s.query(day, court, dtype=dt)
                if len(drows) < CAP:
                    add(drows); continue
                for pr in s.proceedings(court):
                    prows = s.query(day, court, dtype=dt, proc=pr)
                    if len(prows) < CAP:
                        add(prows); continue
                    add(prows)
                    for ct in s.case_types(court, pr):
                        ctrows = s.query(day, court, dtype=dt, proc=pr, casetype=ct)
                        if len(ctrows) < CAP:
                            add(ctrows); continue
                        add(ctrows)
                        cis = s.case_interests(court, pr, ct)
                        if not cis:
                            warn.append(f"{day} c={court} dt={dt} pr={pr} ct={ct} CAPPED (no case-interest axis)")
                            continue
                        for cint in cis:
                            cirows = s.query(day, court, dtype=dt, proc=pr, casetype=ct, caseinterest=cint)
                            add(cirows)
                            if len(cirows) >= CAP:
                                warn.append(f"{day} c={court} dt={dt} pr={pr} ct={ct} ci={cint} STILL CAPPED")

        result = list(out.values())
        if not result and not control_probe_ok(s):
            raise RuntimeError(f"BLOCKED: {day} c={court} empty AND control probe empty")
        return result, warn
    finally:
        if own_session:
            s.close()


def daterange(a: date, b: date):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


CONTROL = Path(__file__).parent / "worker_target.txt"


def day_file(d: date) -> Path:
    return Path("metadata") / str(d.year) / f"{d.isoformat()}.json"


def read_target(default: int) -> int:
    """Live worker-count target. Written by the supervisor / by hand; re-read each
    tick so workers can be added or retired WITHOUT restarting the process."""
    try:
        return max(1, min(12, int(CONTROL.read_text().strip())))
    except Exception:
        return default


def main() -> int:
    start = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(1997, 1, 1)
    end = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2026, 7, 6)
    init_workers = int(sys.argv[3]) if len(sys.argv) > 3 else 3

    global COURTS
    s0 = Crawler()
    COURTS = court_options(s0)
    s0.close()

    # Work-list is derived PURELY from the filesystem: any day in range whose JSON
    # file doesn't exist yet. Restart-safe by construction — completed days are
    # simply absent from the queue. Newest-first (put in that order; FIFO pops it).
    work: "queue.Queue[date]" = queue.Queue()
    total = remaining = 0
    d = end
    stack = []
    while d >= start:
        total += 1
        if not day_file(d).exists():
            stack.append(d)
        d -= timedelta(days=1)
    for d in stack:                # stack is already newest-first (we walked end->start)
        work.put(d); remaining += 1
    print(f"[init] {len(COURTS)} courts | {start}..{end} | target={init_workers} workers "
          f"| {total} days, {remaining} remaining (newest first)", flush=True)

    warn: list = []
    t0 = time.time()
    lock = threading.Lock()
    active = [0]
    stats = {"done": 0, "decisions": 0, "failed": 0}
    stop = threading.Event()

    def worker():
        s = session()
        while not stop.is_set():
            with lock:                       # honor a lowered target: retire this worker
                if active[0] > read_target(init_workers):
                    active[0] -= 1
                    return
            try:
                d = work.get_nowait()
            except queue.Empty:
                with lock:
                    active[0] -= 1
                return
            try:
                rows = collect_day(d.strftime("%d/%m/%Y"), warn)
                out = day_file(d)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
                with lock:
                    stats["done"] += 1; stats["decisions"] += len(rows)
                rate = stats["done"] / (time.time() - t0) * 60
                eta = work.qsize() / rate if rate else 0
                print(f"  {d.isoformat()}: {len(rows):5}  [done={stats['done']} "
                      f"left={work.qsize()} {stats['decisions']} decisions "
                      f"{rate:.1f} days/min ETA {eta:.0f}m workers={active[0]} fails={stats['failed']}]",
                      flush=True)
            except HardTimeoutError as exc:
                # Unrecoverable wedge (see HardTimeoutError docstring) - don't
                # retry-and-continue like a normal per-day failure, since the
                # same stuck session would just wedge again on the next day.
                # os._exit (not sys.exit) skips interpreter shutdown, which
                # would otherwise block waiting for the leaked stuck thread.
                print(f"  {d.isoformat()}: FATAL {exc} - exiting for a clean restart", flush=True)
                import os as _os
                _os._exit(1)
            except Exception as exc:         # isolate: no file written -> retried on resume
                with lock:
                    stats["failed"] += 1
                print(f"  {d.isoformat()}: ERR {repr(exc)[:100]} (will retry on resume)", flush=True)
            finally:
                work.task_done()

    def spawn(n):
        for _ in range(n):
            with lock:
                active[0] += 1
            threading.Thread(target=worker, daemon=True).start()

    spawn(init_workers)
    # Manager loop: keep the live pool sized to the target while work remains.
    while True:
        time.sleep(5)
        if work.empty() and active[0] == 0:
            break
        with lock:
            deficit = read_target(init_workers) - active[0]
        if deficit > 0 and not work.empty():
            spawn(min(deficit, work.qsize()))

    print(f"\n[done in {(time.time()-t0)/60:.1f}m] {stats['decisions']} decisions across "
          f"{stats['done']} new days, {stats['failed']} failed (rerun to retry)", flush=True)
    if warn:
        print(f"[WARN] {len(warn)} buckets still capped after full split (see log)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
