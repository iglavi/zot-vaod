"""
scraper_par.py — סקראפר נט המשפט, גרסה מקבילה
זהה ל-scraper.py אך כאשר יש 100+ תוצאות ביום מחלק את 89 הערכאות
בין N טאבים במקביל (parallel_pages בקונפיג, ברירת מחדל: 4).
מהיר פי ~N על שנים עמוסות שבהן רוב הימים מחזירים 100+.

הבדלים מ-scraper.py:
  - scrape_day מקבל רשימת pages (במקום page בודד)
  - כשיש 100+: asyncio.gather על N chunks במקביל
  - כשאין 100+: עובד על pages[0] בלבד (כמו המקורי)
  - בריסטרט אחרי timeout: מנווט את כל הדפים חזרה לחיפוש
"""

import asyncio
import csv
import ctypes
import json
import random
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from pathlib import Path

from playwright.async_api import async_playwright

# ── קריאת הגדרות ──────────────────────────────────────────
_config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
_cfg = json.loads(Path(_config_path).read_text(encoding="utf-8"))

DATE_FROM = _cfg["date_from"]
DATE_TO   = _cfg["date_to"]

OUTPUT_DIR    = Path(_cfg["output_dir"])
MASTER_CSV    = OUTPUT_DIR / _cfg.get("metadata_file", "metadata.csv")
PROGRESS_FILE = OUTPUT_DIR / _cfg.get("progress_file", "progress.json")
DATA_FILE     = OUTPUT_DIR / "data.json"
LOG_FILE      = OUTPUT_DIR / _cfg.get("log_file", "log.txt")

HEADLESS        = _cfg.get("headless", True)
DECISION_TYPES  = _cfg.get("decision_types", ["פסק דין", "גזר דין", "הכרעת דין"])
PARALLEL_PAGES  = _cfg.get("parallel_pages", 4)

SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

SKIP_PREFIXES = ("בית דין", "בית משפט צבאי", "ועדת שחרורים")


# ── מצב ריצה ─────────────────────────────────────────────

@dataclass
class RunState:
    log_fh: object = None
    docs_downloaded: int = 0
    errors_count: int = 0


_state = RunState()


def log(msg: str, is_error: bool = False):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _state.log_fh:
        _state.log_fh.write(line + "\n")
        _state.log_fh.flush()
    if is_error:
        _state.errors_count += 1


def prevent_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    except Exception:
        pass


def allow_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    except Exception:
        pass


# ── progress ─────────────────────────────────────────────

def load_progress() -> set:
    if PROGRESS_FILE.exists():
        data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        return set(data.get("done", []))
    return set()


def save_progress(done: set):
    PROGRESS_FILE.write_text(
        json.dumps({"done": sorted(done)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def progress_key(*parts) -> str:
    return "|".join(str(p) for p in parts)


# ── תאריכים ──────────────────────────────────────────────

def date_to_str(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def str_to_date(s: str) -> date:
    return date.fromisoformat(s)


def mid_date(d1: date, d2: date) -> date:
    return d1 + (d2 - d1) // 2


# ── ניווט ────────────────────────────────────────────────

async def dismiss_popup(page):
    for locator in [
        page.locator("button", has_text="אישור"),
        page.locator("input[value='אישור']"),
    ]:
        try:
            if await locator.count() > 0:
                await locator.first.click()
                await page.wait_for_timeout(400)
                return
        except Exception:
            pass
    # lean_overlay — popup "100+ תוצאות" שחוסם קליקים
    try:
        overlay = page.locator("[id^='lean_overlay']")
        if await overlay.count() > 0 and await overlay.is_visible():
            await overlay.click()
            await page.wait_for_timeout(400)
    except Exception:
        pass


async def navigate_to_search(page):
    WAIT_SCHEDULE = [
        120,
        2 * 3600,
        2 * 3600,
    ]

    try:
        btn = page.get_by_text("איתור לפי פרמטרים").first
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click(timeout=5000)
            await page.wait_for_timeout(600)
            if await page.locator("#LocateByParameters1_ddlSelectCourt").count() > 0:
                return
    except Exception:
        pass

    for attempt in range(1, len(WAIT_SCHEDULE) + 2):
        try:
            await page.goto(SITE_URL, timeout=45000)
            await page.wait_for_timeout(random.uniform(3000, 4500))
            await dismiss_popup(page)
            await page.get_by_text("איתור החלטות").first.click(timeout=20000)
            await page.wait_for_timeout(random.uniform(1200, 2000))
            await page.get_by_text("איתור לפי פרמטרים").first.click(timeout=20000)
            await page.wait_for_timeout(random.uniform(800, 1500))
            return
        except Exception as e:
            err = str(e)
            is_site_down = any(x in err for x in [
                "ERR_NETWORK_IO_SUSPENDED", "ERR_CONNECTION_REFUSED",
                "ERR_NAME_NOT_RESOLVED", "net::", "Timeout",
                "Target page", "context or browser has been closed",
                "Target crashed", "chrome-error",
            ])
            if not is_site_down or attempt > len(WAIT_SCHEDULE):
                raise
            wait_sec = WAIT_SCHEDULE[attempt - 1]
            wait_str = f"{wait_sec // 3600} שעות" if wait_sec >= 3600 else f"{wait_sec // 60} דקות"
            log(f"  [retry {attempt}/{len(WAIT_SCHEDULE)+1}] האתר לא זמין — ממתין {wait_str}...")
            await asyncio.sleep(wait_sec)
            try:
                await page.reload(timeout=45000)
            except Exception:
                pass


# ── פילטרים ──────────────────────────────────────────────

async def set_date_picker(page, field_id: str, d: date):
    date_str = d.strftime("%d/%m/%Y")
    await page.evaluate(f"""
        () => {{
            const el = document.getElementById('{field_id}');
            if (el) {{
                el.removeAttribute('readonly');
                el.value = '{date_str}';
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.dispatchEvent(new Event('input',  {{bubbles: true}}));
            }}
        }}
    """)
    await page.wait_for_timeout(150)


async def do_search(page, court_idx: int, dt_name: str,
                    from_date: date, to_date: date,
                    judge_idx: int | None = None,
                    proc_idx: int | None = None):
    await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
    await page.wait_for_timeout(900)

    if judge_idx is not None:
        try:
            await page.locator("#LocateByParameters1_ddlJudgeName").select_option(index=judge_idx)
            await page.wait_for_timeout(300)
        except Exception:
            pass

    await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label=dt_name)
    await page.wait_for_timeout(300)

    if proc_idx is not None:
        try:
            await page.locator("#LocateByParameters1_ddlSelectProceeding").select_option(index=proc_idx)
            await page.wait_for_timeout(300)
        except Exception:
            pass

    await set_date_picker(page, "LocateByParameters1_dateFrom", from_date)
    await set_date_picker(page, "LocateByParameters1_DateTo", to_date)

    await page.locator("#ButtonsGroup1_btnLocate").click()
    try:
        await page.locator(".ag-row").first.wait_for(timeout=10000)
    except Exception:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    await page.wait_for_timeout(500)
    await dismiss_popup(page)
    await page.wait_for_timeout(300)


async def get_result_count(page) -> tuple[int, bool]:
    try:
        body = await page.locator("body").inner_text()
        m = re.search(r'מתוך\s+(\d+)', body)
        if m:
            n = int(m.group(1))
            return n, (n >= 100)
    except Exception:
        pass
    try:
        count = await page.locator(".ag-row").count()
        if count > 0:
            return count, (count >= 100)
    except Exception:
        pass
    return 0, False


# ── CSV ───────────────────────────────────────────────────

async def export_page_csv(page) -> list[dict]:
    try:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
            tmp = Path(tf.name)
        if await page.locator(".ag-row").count() == 0:
            return []
        # lean_overlay חוסם קליקים כשיש 100+ — לוחצים על ה-overlay עצמו (לא כפתור אישור)
        try:
            overlay = page.locator("[id^='lean_overlay']")
            if await overlay.count() > 0 and await overlay.is_visible():
                await overlay.click()
                await page.wait_for_timeout(400)
        except Exception:
            pass
        async with page.expect_download(timeout=20000) as dl_info:
            await page.evaluate("""
                () => {
                    const row = document.querySelector('.ag-row');
                    if (!row) return;
                    const rect = row.getBoundingClientRect();
                    row.dispatchEvent(new MouseEvent('contextmenu', {
                        bubbles: true, cancelable: true,
                        clientX: rect.left + rect.width / 2,
                        clientY: rect.top + rect.height / 2,
                    }));
                }
            """)
            await page.wait_for_timeout(600)
            await page.locator(".ag-menu-option").dispatch_event("click")
            await page.wait_for_timeout(400)
            await page.get_by_text("ייצוא נתונים ל- CSV").dispatch_event("click")
        dl = await dl_info.value
        await dl.save_as(str(tmp))
        with open(tmp, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        tmp.unlink(missing_ok=True)
        return rows
    except Exception as e:
        log(f"    שגיאת CSV: {e}", is_error=True)
        return []


# ── master CSV ────────────────────────────────────────────

_existing_keys: set[tuple] = set()
_master_fieldnames: list[str] = []
_master_initialized: bool = False


def _make_row_key(row: dict) -> tuple | None:
    case_val = str(row.get("מספר תיק", "")).strip()
    date_val = str(row.get("תאריך מתן החלטה", "")).strip()
    if case_val and date_val:
        return (case_val, date_val)
    return None


def _init_master_cache():
    global _existing_keys, _master_fieldnames, _master_initialized
    if _master_initialized:
        return
    _master_initialized = True
    if MASTER_CSV.exists() and MASTER_CSV.stat().st_size > 0:
        try:
            with open(MASTER_CSV, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                _master_fieldnames = list(reader.fieldnames or [])
                for r in reader:
                    k = _make_row_key(r)
                    if k:
                        _existing_keys.add(k)
            log(f"  cache: נטענו {len(_existing_keys)} מפתחות קיימים")
        except Exception as e:
            log(f"  אזהרה — לא הצלחתי לקרוא קובץ קיים: {e}")


def append_to_master_csv(rows: list[dict]):
    global _master_fieldnames

    if not rows:
        return

    _init_master_cache()

    if not _master_fieldnames:
        _master_fieldnames = list(rows[0].keys())

    to_add = []
    skipped = 0
    for row in rows:
        k = _make_row_key(row)
        if k and k in _existing_keys:
            skipped += 1
        else:
            to_add.append(row)
            if k:
                _existing_keys.add(k)

    if not to_add:
        log(f"    דולגו {skipped} כפולות — אין חדשות")
        return

    file_is_new = not MASTER_CSV.exists() or MASTER_CSV.stat().st_size == 0
    with open(MASTER_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_master_fieldnames, extrasaction="ignore")
        if file_is_new:
            writer.writeheader()
        writer.writerows(to_add)
    _state.docs_downloaded += len(to_add)
    log(f"    נוספו {len(to_add)} שורות, דולגו {skipped} כפולות")


# ── עיבוד תוצאות ─────────────────────────────────────────

async def process_results(page):
    rows = await export_page_csv(page)
    if not rows:
        log("    אין שורות לעיבוד")
        return
    log(f"    CSV: {len(rows)} שורות")
    append_to_master_csv(rows)


# ── חלוקה בינארית (רשת ביטחון) ───────────────────────────

async def scrape_range(page, court_idx: int, dt_name: str,
                       from_date: date, to_date: date,
                       judge_idx: int | None = None,
                       proc_idx: int | None = None,
                       depth: int = 0):
    indent = "  " * depth

    await navigate_to_search(page)
    await do_search(page, court_idx, dt_name, from_date, to_date, judge_idx, proc_idx)

    count, is_capped = await get_result_count(page)
    range_str = f"{date_to_str(from_date)} עד {date_to_str(to_date)}" if from_date != to_date else date_to_str(from_date)
    log(f"{indent}  תוצאות: {count}{' ← מוגבל!' if is_capped else ''}")

    if count == 0:
        return

    if not is_capped:
        await process_results(page)
        return

    if from_date == to_date:
        if judge_idx is None:
            log(f"{indent}  [רשת ביטחון] יום בודד עם 100 — מחלק לפי שופטים")
            # בוחרים ערכאה בלבד, ללא לחיצת "איתור" — ה-PostBack מאפס את ה-dropdown
            # השופטים נטענים ב-AJAX כשבוחרים ערכאה, לפני החיפוש
            await navigate_to_search(page)
            await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
            await page.wait_for_timeout(1200)
            judge_count = await page.locator(
                "#LocateByParameters1_ddlJudgeName option"
            ).count()
            if judge_count <= 1:
                log(f"{indent}  [רשת ביטחון] אין שופטים לפיצול — מוריד 100 תוצאות")
                await do_search(page, court_idx, dt_name, from_date, to_date)
                await process_results(page)
                return
            log(f"{indent}  נמצאו {judge_count - 1} שופטים")
            for jidx in range(1, judge_count):
                await scrape_range(page, court_idx, dt_name,
                                   from_date, to_date,
                                   judge_idx=jidx,
                                   depth=depth + 1)
                await asyncio.sleep(random.uniform(0.5, 1.5))
        elif proc_idx is None:
            log(f"{indent}  [רשת ביטחון] שופט+יום עם 100 — מחלק לפי הליך")
            # הליכים הם דרופדאון סטטי שנטען עם בחירת ערכאה (לפני PostBack)
            # חייבים לקרוא אותו לפני do_search — אחרי PostBack הוא מתאפס ל-0
            await navigate_to_search(page)
            await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
            await page.wait_for_timeout(1200)
            proc_count = await page.locator(
                "#LocateByParameters1_ddlSelectProceeding option"
            ).count()
            if proc_count <= 1:
                log(f"{indent}  [רשת ביטחון] אין הליכים לפיצול — מוריד 100 תוצאות")
                await do_search(page, court_idx, dt_name, from_date, to_date, judge_idx)
                await process_results(page)
                return
            log(f"{indent}  נמצאו {proc_count - 1} הליכים")
            for pidx in range(1, proc_count):
                await scrape_range(page, court_idx, dt_name,
                                   from_date, to_date,
                                   judge_idx=judge_idx,
                                   proc_idx=pidx,
                                   depth=depth + 1)
                await asyncio.sleep(random.uniform(0.5, 1.5))
        else:
            log(f"{indent}  [רשת ביטחון] לא ניתן לחלק יותר — מוריד 100 תוצאות")
            await process_results(page)
        return

    mid = mid_date(from_date, to_date)
    log(f"{indent}  [רשת ביטחון] מחלק: {date_to_str(from_date)}-{date_to_str(mid)} | {date_to_str(mid + timedelta(days=1))}-{date_to_str(to_date)}")
    await scrape_range(page, court_idx, dt_name, from_date, mid,
                       judge_idx, proc_idx, depth + 1)
    await asyncio.sleep(random.uniform(0.5, 1.5))
    await scrape_range(page, court_idx, dt_name, mid + timedelta(days=1), to_date,
                       judge_idx, proc_idx, depth + 1)


# ── סריקת chunk של ערכאות על page אחד ───────────────────

async def scrape_courts_chunk(page, court_indices: list[int], dt_name: str,
                              day: date, court_names: list[str]):
    await navigate_to_search(page)
    for court_idx in court_indices:
        log(f"    ערכאה {court_idx}: {court_names[court_idx]}")
        await scrape_range(page, court_idx, dt_name, day, day)
        await asyncio.sleep(random.uniform(0.8, 2))


# ── חיפוש יומי (עם parallelism בדרילינג) ─────────────────

async def scrape_day(pages: list, dt_name: str, day: date,
                     court_names: list[str], num_courts: int):
    day_str = date_to_str(day)
    main_page = pages[0]

    # שלב 1: חיפוש "כל הערכאות"
    await navigate_to_search(main_page)
    await do_search(main_page, 0, dt_name, day, day)
    count, is_capped = await get_result_count(main_page)
    log(f"  [{dt_name}] {day_str} — כל הערכאות: {count} תוצאות")

    if count == 0:
        return
    if not is_capped:
        await process_results(main_page)
        return

    # שלב 2: 100+ — מחלק לפי ערכאה במקביל
    n = len(pages)
    log(f"  [{dt_name}] {day_str} — 100+ תוצאות, מחפש לפי ערכאה ({n} דפים במקביל)...")

    courts = [
        i for i in range(1, num_courts)
        if not any(court_names[i].startswith(p) for p in SKIP_PREFIXES)
    ]

    # חלוקת ערכאות round-robin בין הדפים
    chunks = [courts[i::n] for i in range(n)]

    await asyncio.gather(*[
        scrape_courts_chunk(pages[i], chunks[i], dt_name, day, court_names)
        for i in range(n)
    ])


# ── main ──────────────────────────────────────────────────

async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prevent_sleep()
    _state.log_fh = open(LOG_FILE, "a", encoding="utf-8")
    run_start = datetime.now()
    log("=" * 60)
    log(f"scraper_par.py — {DATE_FROM} עד {DATE_TO} ({PARALLEL_PAGES} דפים)")

    done = load_progress()
    log(f"התקדמות קיימת: {len(done)} שילובים")

    court_names = None
    if DATA_FILE.exists():
        cached = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        court_names = cached.get("court_names")
        if court_names:
            log(f"ערכאות מהמטמון: {len(court_names) - 1}")

    ua = random.choice(USER_AGENTS)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True, user_agent=ua)

        # פתיחת N דפים
        pages = []
        for _ in range(PARALLEL_PAGES):
            pages.append(await context.new_page())

        try:
            if not court_names:
                await navigate_to_search(pages[0])
                court_opts = await pages[0].locator(
                    "#LocateByParameters1_ddlSelectCourt option"
                ).all()
                court_names = [(await opt.inner_text()).strip() for opt in court_opts]
                existing = {}
                if DATA_FILE.exists():
                    existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                existing["court_names"] = court_names
                DATA_FILE.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            num_courts = len(court_names)
            from_d = str_to_date(DATE_FROM)
            to_d   = str_to_date(DATE_TO)

            current_d = from_d
            while current_d <= to_d:
                day_str = date_to_str(current_d)
                log(f"\n{'=' * 50}")
                log(f"יום: {day_str}")

                for dt_name in DECISION_TYPES:
                    key = progress_key(day_str, dt_name)

                    if key in done:
                        log(f"  [{dt_name}] {day_str} — כבר הושלם")
                        continue

                    for attempt in range(1, 4):
                        try:
                            await scrape_day(pages, dt_name, current_d, court_names, num_courts)
                            break
                        except Exception as e:
                            err = str(e)
                            is_transient = any(x in err for x in [
                                "Timeout", "TimeoutError", "net::",
                                "ERR_", "Target page", "context or browser",
                                "Target crashed",
                            ])
                            if not is_transient or attempt == 3:
                                raise
                            wait_sec = attempt * 120
                            log(f"  [retry {attempt}/3] timeout — ממתין {wait_sec // 60} דקות...", is_error=True)
                            await asyncio.sleep(wait_sec)
                            for pg in pages:
                                try:
                                    await navigate_to_search(pg)
                                except Exception:
                                    pass

                    done.add(key)
                    save_progress(done)
                    await asyncio.sleep(random.uniform(0.5, 1.5))

                current_d += timedelta(days=1)

        except KeyboardInterrupt:
            log("\nנעצר על ידי המשתמש")
        except Exception as e:
            log(f"\nשגיאה: {e}", is_error=True)
            import traceback
            log(traceback.format_exc())
        finally:
            save_progress(done)
            allow_sleep()
            try:
                await browser.close()
            except Exception:
                pass
            elapsed = datetime.now() - run_start
            hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            elapsed_str = f"{hours}:{minutes:02d}:{seconds:02d}"
            log("\n" + "=" * 60)
            log("סיכום הרצה:")
            log(f"  זמן ריצה:       {elapsed_str}")
            log(f"  מסמכים שנוספו:  {_state.docs_downloaded}")
            log(f"  תקלות:          {_state.errors_count}")
            log(f"  שילובים שהושלמו: {len(done)}")
            log("=" * 60)
            if _state.log_fh:
                _state.log_fh.close()


asyncio.run(main())
