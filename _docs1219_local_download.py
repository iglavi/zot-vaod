"""הורדת שאר הזוגות של 2012-2019 מקומית (בלי AWS Lambda בכלל) - כדי לא
להמשיך לצבור עלות אמיתית עכשיו שהחשבון בתשלום. משתמש באותו קוד מתוקן
ומאומת מ-download1219_handler.py (Word->PDF-viewer fallback, cap-split,
תיקון ה-query_full_deep) - רק רץ בתהליך מקומי אחד, לא ב-Lambda.

מקור-הזוגות: התור הקיים ngcs-crawl-use1-docs1219 ב-SQS - כבר מכיל בדיוק
את הזוגות שטרם עובדו. קריאה/מחיקה מ-SQS היא בעלות זניחה (הרבה מתחת ל-
free tier של מיליון בקשות/חודש) - שונה לחלוטין מעלות ה-Lambda compute
שרצינו להימנע ממנה. שמירת הקבצים - ישירות למקומי (documents_ngcs_2012_2019/,
אותה תיקייה שכבר קיבלה את הגיבוי המלא), בלי כתיבה ל-S3 בכלל.

מעקב-התקדמות מקומי (לא S3): קובץ progress.csv עם שורות "day|court|status".

הרצה:  python _docs1219_local_download.py
"""
from __future__ import annotations

import base64
import csv
import faulthandler
import io
import json
import os
import re
import sys
import threading
import time
import zipfile
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).parent / "lambda"))
sys.path.insert(0, str(Path(__file__).parent / "court_scraper"))
os.environ.setdefault("NGCS_RPS", "8")  # ראו גם WORKERS למטה - אבחון חדש (31/07)
# אחרי הביניים (12/15) עדיין 100% blocked (39/40, 0 הצליחו) - בדיקה מבודדת
# (thread יחיד, session בודד, query_full ל-CONTROL_DAY) הצליחה מיד (100
# שורות אמיתיות) ברגע שההורדה הרב-thread-ית נהרגה - כלומר זו לא חסימת-IP
# מתמשכת/cooldown, אלא תגובה בזמן-אמת למספר ה-sessions הנפרדים הפתוחים
# בו-זמנית מאותו IP (כל thread יוצר cm.Crawler() משלו, session TLS-
# impersonation נפרד - הרבה sessions מקבילים מ-IP אחד כנראה נראה בוטי
# ל-WAF, יותר מקצב הבקשות הגולמי). לכן הגורם החשוד עכשיו הוא WORKERS
# (concurrency), לא NGCS_RPS.

import crawl_metadata as cm  # noqa: E402
from court_scraper.client import parse_form_fields  # noqa: E402

from PIL import Image  # noqa: E402

REGION = "us-east-1"
QUEUE_NAME = "ngcs-crawl-use1-docs1219"
OUT_DIR = Path(__file__).parent / "documents_ngcs_2012_2019"
PROGRESS_CSV = Path(__file__).parent / "data" / "ngcs_2012_2019" / "local_progress.csv"
WORKERS = 4  # ירידה חדה מ-15 (31/07) - בודקים את תיאוריית ה-concurrent-sessions,
# ראו הערה ליד NGCS_RPS למעלה. זה גם קרוב למספר ה-threads-לכל-container
# שעבד היטב ב-Lambda (docs1219: 4 threads/container, אבל שם זה היה מפוזר
# על הרבה containers = הרבה IPs נפרדים, לא IP אחד).

OUT_URL = "https://www.court.gov.il/NGCS.Web.Site/LocateDecisions/LocateDecisionOutput.aspx"
DL_URL = "https://www.court.gov.il/NGCS.Web.Site/DownloadDocuments.aspx"
VIEWER_URL = "https://www.court.gov.il/NGCS.Web.Site/Viewer/NGCSViewerPage.aspx"
VIEWER_TIMEOUT = 45
DOC_BATCH = 10  # הועלה מ-5 (31/07) - פחות round-trips לכל זוג
SAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# The hard-timeout wrapper added to crawl_metadata.py's curl_cffi calls did
# NOT stop the recurring hang (confirmed live: a hang still occurred with
# zero "FATAL" log line, meaning the stuck call wasn't in any of THOSE call
# sites). boto3/botocore's SQS calls below were the one network path left
# completely unwrapped - they go over HTTPS to AWS too, and Windows-level
# DNS-resolution stalls are an OS-resolver issue, not a curl_cffi-specific
# one, so botocore's own connect/read timeouts could be just as bypassable.
# Same pattern: a dedicated executor enforces a hard wall-clock bound and
# raises cm.HardTimeoutError (NOT retried anywhere) if boto3 itself wedges.
_BOTO_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=16, thread_name_prefix="boto-hardtimeout")


def _hard_boto_call(fn, *args, hard_timeout=60, **kwargs):
    fut = _BOTO_EXECUTOR.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=hard_timeout)
    except concurrent.futures.TimeoutError:
        raise cm.HardTimeoutError(
            f"{getattr(fn, '__name__', fn)} (boto3) did not return within "
            f"{hard_timeout}s - treating as a stuck DNS/connect, not retrying"
        ) from None


def safe(text: str) -> str:
    return SAFE.sub("_", str(text).strip()) or "doc"


def download_batch(s: "cm.Crawler", html: str, rows: list[dict]) -> list[bytes | None]:
    fields = parse_form_fields(html)
    fields.update({
        "__EVENTTARGET": "btnDownloadWordDocs", "__EVENTARGUMENT": "",
        "documentListIDs": ", ".join(str(r["DocumentID"]) for r in rows),
        "decisionSignatureDateIDs": ", ".join(r["DecisionSignatureDate"] for r in rows),
    })
    # retries=2/timeout=30 (not the 8x90s default): a stack dump caught two
    # worker threads simultaneously stuck cycling this exact retry loop on a
    # single failing document, ~13min worst case each - long enough with no
    # CSV writes to look identical to a hang. This whole batch already has a
    # per-document PDF-viewer fallback, so failing fast here just means a
    # few more documents take the (already-existing) fallback path instead
    # of one bad batch blocking a worker thread for minutes.
    s._post(OUT_URL, data=fields, retries=2, timeout=30)
    cm.rate_gate()
    data = s.client._client.get(DL_URL, timeout=90).content
    if data[:2] != b"PK":
        return [None] * len(rows)
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        names = zf.namelist()
    except zipfile.BadZipFile:
        return [None] * len(rows)
    return [zf.read(names[i]) if i < len(names) else None for i in range(len(rows))]


def _viewer_json(s: "cm.Crawler", viewer_page: str, method: str, payload: dict):
    r = s.client.post(f"{VIEWER_URL}/{method}", content=json.dumps(payload), timeout=VIEWER_TIMEOUT,
                       headers={"Content-Type": "application/json; charset=utf-8",
                                "Accept": "application/json, text/javascript, */*; q=0.01",
                                "X-Requested-With": "XMLHttpRequest", "Referer": viewer_page})
    return json.loads(r.content.decode("utf-8", "replace")).get("d")


def _pdf_via_viewer(s: "cm.Crawler", html: str, row: dict) -> bytes | None:
    df = parse_form_fields(html)
    df.update({"__EVENTTARGET": "btnDocument",
               "__EVENTARGUMENT": f"{row['CaseID']}&{row['DocumentID']}&1"})
    # retries=2/timeout=30 - see download_batch's comment above; this is the
    # exact call a stack dump caught two workers stuck cycling on (8x90s
    # default = ~13min worst case per document) when a single document's
    # viewer link kept failing. This is already the last-resort fallback -
    # failing fast just means one more document ends up with no PDF saved,
    # same as any other empty/failed result, instead of blocking a worker.
    r = s._post(OUT_URL, data=df, retries=2, timeout=30)
    m = re.search(r"DocumentNumber=([0-9a-f]{32})",
                  str(r.url) + "\n" + r.content.decode("windows-1255", "replace"), re.I)
    if not m:
        return None
    dn = m.group(1)
    vp = f"{VIEWER_URL}?DocumentNumber={dn}"
    s.client.get(vp, timeout=VIEWER_TIMEOUT)
    n = _viewer_json(s, vp, "GetNumberOfImages", {"documentNumber": dn})
    if not isinstance(n, int) or n <= 0:
        return None
    imgs = _viewer_json(s, vp, "GetAllImages", {"documentNumber": dn})
    if not isinstance(imgs, list) or not imgs:
        return None
    pil = []
    for x in imgs:
        sx = x if isinstance(x, str) else str(x)
        m2 = re.search(r"base64,([A-Za-z0-9+/=]+)", sx)
        payload = m2.group(1) if m2 else sx
        pil.append(Image.open(io.BytesIO(base64.b64decode(payload))))
    buf = io.BytesIO()
    pil[0].convert("RGB").save(buf, format="PDF", save_all=True, append_images=[p.convert("RGB") for p in pil[1:]])
    return buf.getvalue()


def _process_pair(s: "cm.Crawler", day_iso: str, court: str) -> tuple[str, int, int]:
    dd, mm_, yyyy = day_iso[8:10], day_iso[5:7], day_iso[:4]
    date_ddmmyyyy = f"{dd}/{mm_}/{yyyy}"

    html, rows = s.query_full(date_ddmmyyyy, court)
    if not rows and html is None:
        html, rows = s.query_full(date_ddmmyyyy, court)

    if not rows:
        if not cm.control_probe_ok(s):
            return "blocked", 0, 0
        return "empty", 0, 0

    leaves = [(html, rows)] if len(rows) < cm.CAP else s.query_full_deep(date_ddmmyyyy, court, html, rows)

    saved = 0
    total_rows = 0
    seen_doc_ids: set = set()
    year = day_iso[:4]
    for leaf_html, leaf_rows in leaves:
        if not leaf_rows:
            continue
        fresh = [r for r in leaf_rows if r.get("DocumentID") not in seen_doc_ids]
        for r in fresh:
            seen_doc_ids.add(r.get("DocumentID"))
        total_rows += len(fresh)
        for i in range(0, len(fresh), DOC_BATCH):
            batch = fresh[i:i + DOC_BATCH]
            try:
                docs = download_batch(s, leaf_html, batch)
            except cm.HardTimeoutError:
                raise  # unrecoverable stuck call - let it crash the process, don't paper over it
            except Exception:
                docs = [None] * len(batch)
            for r, doc in zip(batch, docs):
                stem = f"{safe(r['CaseDisplayIdentifier'])}_{r['DocumentID']}"
                if doc is not None:
                    path = OUT_DIR / year / f"{stem}.docx"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(doc)
                    saved += 1
                    continue
                try:
                    pdf = _pdf_via_viewer(s, leaf_html, r)
                except cm.HardTimeoutError:
                    raise  # unrecoverable stuck call - let it crash the process, don't paper over it
                except Exception:
                    pdf = None
                if pdf is not None:
                    path = OUT_DIR / year / f"{stem}.pdf"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(pdf)
                    saved += 1
    return "done", saved, total_rows


def _load_done() -> set[str]:
    done = set()
    if PROGRESS_CSV.exists():
        with open(PROGRESS_CSV, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("|")
                if len(parts) >= 2:
                    done.add(f"{parts[0]}|{parts[1]}")
    return done


_LAST_PROGRESS = [time.monotonic()]


def _record(day_iso: str, court: str, status: str, saved: int, total: int):
    PROGRESS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_CSV, "a", encoding="utf-8") as f:
        f.write(f"{day_iso}|{court}|{status}|{saved}|{total}\n")
    _LAST_PROGRESS[0] = time.monotonic()


_STALL_DUMP_AFTER = 300  # 5 min - well before the external bash watchdog's 20min kill


def _stall_watchdog():
    """Three fix attempts (curl_cffi get/post, boto3 SQS calls, curl_cffi
    close()) each still left the hang reproducing with zero FATAL/HardTimeoutError
    ever printed - meaning the stuck call isn't in any of those paths, and
    guessing at more call sites one at a time isn't converging. py-spy can't
    attach in this environment (os error 87 in git-bash, hangs in PowerShell),
    so this dumps every thread's REAL Python stack via faulthandler the
    moment a stall is detected, well before the external watchdog kills the
    process - that tells us definitively which line is actually stuck instead
    of guessing at another call site."""
    dumped = False
    while True:
        time.sleep(20)
        idle = time.monotonic() - _LAST_PROGRESS[0]
        if idle > _STALL_DUMP_AFTER and not dumped:
            dumped = True
            path = Path(__file__).parent / f"_stall_dump_{int(time.time())}.txt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"STALL DETECTED: {idle:.0f}s since last progress\n\n")
                faulthandler.dump_traceback(file=f, all_threads=True)
            print(f"STALL DETECTED after {idle:.0f}s - dumped all thread stacks to {path}", flush=True)
        elif idle < _STALL_DUMP_AFTER:
            dumped = False  # progress resumed - re-arm for the next stall


def _one(sqs, queue_url, msg, done_set):
    day_iso, court = msg["Body"].strip().split("|")
    key = f"{day_iso}|{court}"
    if key in done_set:
        _hard_boto_call(sqs.delete_message, QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
        return "already_done"
    s = cm.Crawler()
    try:
        status, saved, total = _process_pair(s, day_iso, court)
    except cm.HardTimeoutError:
        raise  # unrecoverable wedge (see HardTimeoutError docstring) - crash the process, don't retry-in-place
    except Exception as e:
        print(f"PAIR FAILED {key}: {type(e).__name__}: {e}", flush=True)
        return "failed"  # leave in queue, will redeliver after visibility timeout
    finally:
        s.close()
    if status == "blocked":
        print(f"PAIR BLOCKED {key}", flush=True)
        return "blocked"
    _record(day_iso, court, status, saved, total)
    _hard_boto_call(sqs.delete_message, QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
    return status


def main():
    threading.Thread(target=_stall_watchdog, daemon=True).start()
    sqs = boto3.client("sqs", region_name=REGION)
    queue_url = _hard_boto_call(sqs.get_queue_url, QueueName=QUEUE_NAME)["QueueUrl"]
    done_set = _load_done()
    print(f"{len(done_set)} pairs already done locally (resume)", flush=True)

    processed = {"done": 0, "empty": 0, "blocked": 0, "failed": 0, "already_done": 0}
    t0 = time.monotonic()

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        empty_polls = 0
        while empty_polls < 5:
            try:
                resp = _hard_boto_call(
                    sqs.receive_message,
                    QueueUrl=queue_url, MaxNumberOfMessages=10,
                    WaitTimeSeconds=10, VisibilityTimeout=600,
                )
            except cm.HardTimeoutError as e:
                print(f"FATAL: {e} - exiting for a clean restart", flush=True)
                os._exit(1)
            msgs = resp.get("Messages", [])
            if not msgs:
                empty_polls += 1
                continue
            empty_polls = 0
            futs = [ex.submit(_one, sqs, queue_url, m, done_set) for m in msgs]
            for fut in futs:
                try:
                    r = fut.result()
                except cm.HardTimeoutError as e:
                    # Unrecoverable stuck network call (see HardTimeoutError
                    # docstring in crawl_metadata.py) - os._exit (not
                    # sys.exit) skips interpreter/executor shutdown, which
                    # would otherwise block waiting for the leaked stuck
                    # thread. The bash watchdog notices the dead PID and
                    # restarts within ~3min instead of waiting the full
                    # 20min hang-detection window.
                    print(f"FATAL: {e} - exiting for a clean restart", flush=True)
                    os._exit(1)
                processed[r] = processed.get(r, 0) + 1

            total = sum(processed.values())
            if total % 50 < 10:
                elapsed = time.monotonic() - t0
                print(f"  ...{total} processed ({processed}), {elapsed:.0f}s elapsed", flush=True)

    print(f"QUEUE EMPTY - DONE: {processed}", flush=True)


if __name__ == "__main__":
    main()
