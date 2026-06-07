"""
scraper.py — סקראפר נט המשפט
עובד יום-יום על כל הערכאות הרלוונטיות.
מוריד פסקי דין, גזרי דין והכרעות דין.

אסטרטגיה:
  1. חיפוש "כל הערכאות" (index 0) — אם יש פחות מ-100 תוצאות, מורידים הכל בחיפוש אחד.
  2. אם יש 100+ — יורדים לחיפוש לפי ערכאה בנפרד (רשת ביטחון).
  3. אם גם ערכאה בודדת ביום בודד מחזירה 100 — מחלקים לפי שופט ואז לפי הליך.
"""

import asyncio
import csv
import ctypes
import json
import random
import re
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from pathlib import Path

from playwright.async_api import async_playwright

# ── קריאת הגדרות ──────────────────────────────────────────
_cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))

DATE_FROM = _cfg["date_from"]
DATE_TO   = _cfg["date_to"]

OUTPUT_DIR    = Path(_cfg["output_dir"])
MASTER_CSV    = OUTPUT_DIR / _cfg.get("metadata_file", "metadata.csv")
PROGRESS_FILE = OUTPUT_DIR / _cfg.get("progress_file", "progress.json")
DATA_FILE     = OUTPUT_DIR / "data.json"
LOG_FILE      = OUTPUT_DIR / _cfg.get("log_file", "log.txt")

HEADLESS       = _cfg.get("headless", True)
DECISION_TYPES = _cfg.get("decision_types", ["פסק דין", "גזר דין", "הכרעת דין"])

SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

# ערכאות שמדלגים עליהן תמיד — לא רלוונטיות לפרויקט
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


async def navigate_to_search(page):
    """
    מנווט לדף החיפוש לפי פרמטרים.
    מנסה קודם ללחוץ על הטאב ישירות (מהיר) — ורק אם נכשל טוען מחדש.
    אם האתר לא זמין — ממתין 2 דקות, אחר כך 2 שעות, אחר כך 2 שעות נוספות.
    לאחר 4 ניסיונות כושלים — זורק exception ומסיים את הריצה.
    """
    WAIT_SCHEDULE = [
        120,        # ניסיון 2: אחרי 2 דקות
        2 * 3600,   # ניסיון 3: אחרי 2 שעות
        2 * 3600,   # ניסיון 4: אחרי 2 שעות נוספות
    ]

    # ניסיון מהיר — אם כבר נמצאים בדף החיפוש, פשוט לוחצים על הטאב
    try:
        btn = page.get_by_text("איתור לפי פרמטרים").first
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click(timeout=5000)
            await page.wait_for_timeout(600)
            if await page.locator("#LocateByParameters1_ddlSelectCourt").count() > 0:
                return
    except Exception:
        pass

    # ניסיון מלא — טעינה מחדש של האתר
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
    """ממלא שדה תאריך ישירות דרך JS."""
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
    """חיפוש לפי ערכאה + סוג + טווח תאריכים (+ שופט/הליך אופציונלי)."""
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
    await page.wait_for_timeout(2500)
    await dismiss_popup(page)
    await page.wait_for_timeout(500)


async def get_result_count(page) -> tuple[int, bool]:
    try:
        body = await page.locator("body").inner_text()
        m = re.search(r'(\d+)\s*תוצאות', body)
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
            await page.locator(".ag-menu-option").click()
            await page.wait_for_timeout(400)
            await page.get_by_text("ייצוא נתונים ל- CSV").click()
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
    """מפתח ייחודי: (מספר תיק, תאריך מתן החלטה)."""
    case_val = str(row.get("מספר תיק", "")).strip()
    date_val = str(row.get("תאריך מתן החלטה", "")).strip()
    if case_val and date_val:
        return (case_val, date_val)
    return None


def _init_master_cache():
    """טוען את המפתחות הקיימים מהקובץ לזיכרון — פעם אחת בלבד."""
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
    """מוסיף שורות חדשות ל-MASTER_CSV, מסנן כפולות לפי cache."""
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
    """מייצא CSV של כל התוצאות בייצוא אחד ומאחד לקובץ המרכזי."""
    rows = await export_page_csv(page)
    if not rows:
        log("    אין שורות לעיבוד")
        return
    log(f"    CSV: {len(rows)} שורות")
    append_to_master_csv(rows)


# ── חלוקה בינארית (רשת ביטחון) ───────────────────────────
#
# מופעלת רק כשיש 100+ תוצאות. מחלקת לפי ערכאה, ואם גם אז
# יש 100 ביום בודד — לפי שופט ואז לפי הליך.

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

    # ── רשת ביטחון: הגענו ל-100 ──────────────────────────
    if from_date == to_date:
        if judge_idx is None:
            log(f"{indent}  [רשת ביטחון] יום בודד עם 100 — מחלק לפי שופטים")
            await navigate_to_search(page)
            await do_search(page, court_idx, dt_name, from_date, to_date)
            judge_count = await page.locator(
                "#LocateByParameters1_ddlJudgeName option"
            ).count()
            log(f"{indent}  נמצאו {judge_count - 1} שופטים")
            for jidx in range(1, judge_count):
                await scrape_range(page, court_idx, dt_name,
                                   from_date, to_date,
                                   judge_idx=jidx,
                                   depth=depth + 1)
                await asyncio.sleep(random.uniform(0.5, 1.5))
        elif proc_idx is None:
            log(f"{indent}  [רשת ביטחון] שופט+יום עם 100 — מחלק לפי הליך")
            await navigate_to_search(page)
            await do_search(page, court_idx, dt_name, from_date, to_date, judge_idx)
            proc_count = await page.locator(
                "#LocateByParameters1_ddlSelectProceeding option"
            ).count()
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


# ── חיפוש יומי: "כל הערכאות" קודם ───────────────────────
#
# חיפוש אחד לכל היום במקום 89 חיפושים נפרדים.
# אם יש פחות מ-100 — מסיימים בחיפוש אחד.
# אם יש 100+ — יורדים לחיפוש לפי ערכאה בנפרד.

async def scrape_day(page, dt_name: str, day: date,
                     court_names: list[str], num_courts: int):
    day_str = date_to_str(day)

    # ── שלב 1: חיפוש "כל הערכאות" (index 0) ──────────────
    await navigate_to_search(page)
    await do_search(page, 0, dt_name, day, day)
    count, is_capped = await get_result_count(page)
    log(f"  [{dt_name}] {day_str} — כל הערכאות: {count} תוצאות")

    if count == 0:
        return  # יום ריק — מדלגים על כל הערכאות

    if not is_capped:
        await process_results(page)  # הכל בחיפוש אחד
        return

    # ── שלב 2: רשת ביטחון — יש 100+, יורדים לפי ערכאה ───
    log(f"  [{dt_name}] {day_str} — 100+ תוצאות, מחפש לפי ערכאה...")
    for court_idx in range(1, num_courts):
        court_name = court_names[court_idx]
        if any(court_name.startswith(p) for p in SKIP_PREFIXES):
            continue
        log(f"    ערכאה {court_idx}: {court_name}")
        await scrape_range(page, court_idx, dt_name, day, day)
        await asyncio.sleep(random.uniform(0.8, 2))


# ── main ──────────────────────────────────────────────────

async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prevent_sleep()
    _state.log_fh = open(LOG_FILE, "a", encoding="utf-8")
    run_start = datetime.now()
    log("=" * 60)
    log(f"scraper.py — {DATE_FROM} עד {DATE_TO}")

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
        page = await context.new_page()

        try:
            if not court_names:
                await navigate_to_search(page)
                court_opts = await page.locator(
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

                    await scrape_day(page, dt_name, current_d, court_names, num_courts)

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
