"""
scrape_range.py — סקראפר עם חלוקה בינארית של תאריכים
במקום לפלטר לפי שופט מראש, מחלק טווח תאריכים לשניים כשיש 100 תוצאות.
אם מגיע ליום בודד עם 100 — עובר לפילטר שופט ואז הליך.
"""

import asyncio
import csv
import ctypes
import json
import random
import re
import tempfile
from datetime import date, timedelta, datetime
from pathlib import Path

from playwright.async_api import async_playwright

# ── קריאת הגדרות ──────────────────────────────────────────
_cfg = json.loads(Path("config_heavy.json").read_text(encoding="utf-8"))

# בגרסה זו: date_from ו-date_to במקום target_date בלבד
DATE_FROM = _cfg.get("date_from", _cfg.get("target_date", "2026-01-01"))
DATE_TO   = _cfg.get("date_to",   _cfg.get("target_date", "2026-01-01"))

OUTPUT_DIR    = Path(_cfg["output_dir"])
MASTER_CSV    = OUTPUT_DIR / _cfg.get("metadata_file", "metadata.csv")
PROGRESS_FILE = OUTPUT_DIR / _cfg.get("progress_file", "progress.json")
DATA_FILE     = OUTPUT_DIR / "data.json"
LOG_FILE      = OUTPUT_DIR / _cfg.get("log_file", "log.txt")

HEADLESS        = _cfg.get("headless", False)
DECISION_TYPES  = _cfg.get("decision_types", ["פסק דין", "גזר דין", "הכרעת דין"])
STEP_DAYS       = int(_cfg.get("step_days", 1))          # כמה ימים בכל צעד (1=יומי, 7=שבועי, 30=חודשי)
COURT_LIST = _cfg.get("court_list", [])         # רשימת ערכאות לסריקה — ריק = הכל


SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

# ─────────────────────────────────────────────────────────
_log_fh = None


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


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
                await page.wait_for_timeout(600)
                return
        except Exception:
            pass




async def navigate_to_search(page):
    """
    מנווט לדף החיפוש לפי פרמטרים.
    מנסה קודם ללחוץ על הטאב ישירות (מהיר) — ורק אם נכשל טוען מחדש את האתר.
    אם האתר לא זמין — ממתין 2 דקות, אחר כך 2 שעות, אחר כך 2 שעות נוספות.
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
            await page.wait_for_timeout(800)
            # בדיקה שהטופס נטען — שדה הערכאה קיים
            if await page.locator("#LocateByParameters1_ddlSelectCourt").count() > 0:
                return
    except Exception:
        pass

    # ניסיון מלא — טעינה מחדש של האתר
    for attempt in range(1, len(WAIT_SCHEDULE) + 2):
        try:
            await page.goto(SITE_URL, timeout=45000)
            await page.wait_for_timeout(random.uniform(3500, 5000))
            await dismiss_popup(page)
            await page.get_by_text("איתור החלטות").first.click(timeout=20000)
            await page.wait_for_timeout(random.uniform(1500, 2500))
            await page.get_by_text("איתור לפי פרמטרים").first.click(timeout=20000)
            await page.wait_for_timeout(random.uniform(1000, 2000))
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
    """ממלא שדה תאריך ישירות דרך JS — מהיר, ללא פתיחת datepicker."""
    date_str = d.strftime("%d/%m/%Y")  # הפורמט שהאתר מצפה לו
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
    await page.wait_for_timeout(200)


async def do_search(page, court_idx: int, dt_name: str,
                    from_date: date, to_date: date,
                    judge_idx: int | None = None,
                    proc_idx: int | None = None):
    """חיפוש לפי ערכאה + סוג + טווח תאריכים (+ שופט/הליך אופציונלי)."""
    await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
    await page.wait_for_timeout(1200)

    if judge_idx is not None:
        try:
            await page.locator("#LocateByParameters1_ddlJudgeName").select_option(index=judge_idx)
            await page.wait_for_timeout(400)
        except Exception:
            pass

    await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label=dt_name)
    await page.wait_for_timeout(400)

    if proc_idx is not None:
        try:
            await page.locator("#LocateByParameters1_ddlSelectProceeding").select_option(index=proc_idx)
            await page.wait_for_timeout(400)
        except Exception:
            pass

    await set_date_picker(page, "LocateByParameters1_dateFrom", from_date)
    await set_date_picker(page, "LocateByParameters1_DateTo", to_date)

    await page.locator("#ButtonsGroup1_btnLocate").click()
    await page.wait_for_timeout(3000)
    await dismiss_popup(page)
    await page.wait_for_timeout(800)


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
        tmp = Path(tempfile.mktemp(suffix=".csv"))
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
            await page.wait_for_timeout(800)
            await page.locator(".ag-menu-option").click()
            await page.wait_for_timeout(500)
            await page.get_by_text("ייצוא נתונים ל- CSV").click()
        dl = await dl_info.value
        await dl.save_as(str(tmp))
        with open(tmp, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        tmp.unlink(missing_ok=True)
        return rows
    except Exception as e:
        log(f"    שגיאת CSV: {e}")
        return []





# ── master CSV ────────────────────────────────────────────

# cache בזיכרון — נטען פעם אחת בתחילת הריצה, ומתעדכן בכל כתיבה
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
            log(f"  cache: נטענו {len(_existing_keys)} מפתחות קיימים מהקובץ המאוחד")
        except Exception as e:
            log(f"  אזהרה — לא הצלחתי לקרוא קובץ קיים: {e}")


def append_to_master_csv(rows: list[dict]):
    """
    מוסיף שורות חדשות ל-MASTER_CSV.
    משתמש ב-cache בזיכרון — לא קורא את הקובץ בכל קריאה.
    """
    global _master_fieldnames

    if not rows:
        return

    _init_master_cache()

    if not _master_fieldnames:
        _master_fieldnames = list(rows[0].keys())

    # סינון כפולות לפי cache
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
    log(f"    נוספו {len(to_add)} שורות, דולגו {skipped} כפולות")


# ── עיבוד תוצאות ─────────────────────────────────────────

async def process_results(page):
    """מייצא CSV של כל התוצאות ומאחד לקובץ המרכזי."""
    all_rows = await export_page_csv(page)
    if not all_rows:
        log("    אין שורות לעיבוד")
        return
    log(f"    CSV: {len(all_rows)} שורות")
    append_to_master_csv(all_rows)


# ── חלוקה בינארית ─────────────────────────────────────────

async def scrape_range(page, court_idx: int, dt_name: str,
                       from_date: date, to_date: date,
                       judge_idx: int | None = None,
                       proc_idx: int | None = None,
                       depth: int = 0):
    """
    מחלק טווח תאריכים לשניים כשיש 100 תוצאות.
    אם הגיע ליום בודד עם 100 — עובר לפילטר שופט, ואז הליך.
    """
    indent = "  " * depth

    await navigate_to_search(page)
    await do_search(page, court_idx, dt_name, from_date, to_date, judge_idx, proc_idx)

    count, is_capped = await get_result_count(page)
    range_str = f"{date_to_str(from_date)} עד {date_to_str(to_date)}"
    log(f"{indent}[{range_str}] תוצאות: {count}{' ← מוגבל!' if is_capped else ''}")

    if count == 0:
        return

    if not is_capped:
        # פחות מ-100 — מוריד הכל
        await process_results(page)
        return

    # יש 100 תוצאות — צריך לחלק
    if from_date == to_date:
        # יום בודד עם 100 — לא ניתן לחלק תאריכים
        if judge_idx is None:
            # עוברים לפילטר שופטים — קוראים את הרשימה מתוך טופס החיפוש
            log(f"{indent}  יום בודד עם 100 — מחלק לפי שופטים")
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
                await asyncio.sleep(random.uniform(1, 2))
        elif proc_idx is None:
            # כבר פילטרנו שופט — עוברים להליך
            log(f"{indent}  שופט+יום עם 100 — מחלק לפי הליך")
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
                await asyncio.sleep(random.uniform(1, 2))
        else:
            # גם הליך לא עזר — מוריד מה שיש (100 תוצאות)
            log(f"{indent}  לא ניתן לחלק יותר — מוריד 100 תוצאות")
            await process_results(page)
        return

    # חלוקה בינארית של הטווח
    mid = mid_date(from_date, to_date)
    log(f"{indent}  מחלק: {date_to_str(from_date)}-{date_to_str(mid)} | {date_to_str(mid + timedelta(days=1))}-{date_to_str(to_date)}")

    await scrape_range(page, court_idx, dt_name, from_date, mid,
                       judge_idx, proc_idx, depth + 1)
    await asyncio.sleep(random.uniform(1, 2))
    await scrape_range(page, court_idx, dt_name, mid + timedelta(days=1), to_date,
                       judge_idx, proc_idx, depth + 1)


# ── main ──────────────────────────────────────────────────

async def main():
    global _log_fh
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    prevent_sleep()
    _log_fh = open(LOG_FILE, "a", encoding="utf-8")
    log("=" * 60)
    log(f"net_hamishpat_scraper — {DATE_FROM} עד {DATE_TO}")

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

            # ערכאות שדולגות תמיד — בית דין צבאי, ועדת שחרורים
            SKIP_PREFIXES = ("בית דין", "בית משפט צבאי", "ועדת שחרורים")

            # לולאה לפי צעד (יום / שבוע / חודש)
            current_d = from_d
            while current_d <= to_d:
                step_end = min(current_d + timedelta(days=STEP_DAYS - 1), to_d)
                range_str = date_to_str(current_d) if current_d == step_end else f"{date_to_str(current_d)} עד {date_to_str(step_end)}"
                log(f"\n{'=' * 50}")
                log(f"טווח: {range_str}")

                for dt_name in DECISION_TYPES:
                    log(f"\n  סוג החלטה: {dt_name}")

                    for court_idx in range(1, num_courts):
                        court_name = court_names[court_idx]

                        # דילוג על ערכאות לא רלוונטיות תמיד
                        if any(court_name.startswith(p) for p in SKIP_PREFIXES):
                            log(f"    ערכאה {court_idx}: {court_name} — מדולג (לא רלוונטי)")
                            continue

                        # דילוג על ערכאות שלא ברשימה (אם הוגדרה)
                        if COURT_LIST and court_name not in COURT_LIST:
                            continue

                        key = progress_key(date_to_str(current_d), date_to_str(step_end), dt_name, court_idx)

                        if key in done:
                            log(f"    ערכאה {court_idx}: {court_name} — כבר הושלם")
                            continue

                        log(f"\n    ערכאה {court_idx}: {court_name}")
                        await scrape_range(page, court_idx, dt_name, current_d, step_end)

                        done.add(key)
                        save_progress(done)
                        await asyncio.sleep(random.uniform(1, 3))

                current_d += timedelta(days=STEP_DAYS)

        except KeyboardInterrupt:
            log("\nנעצר על ידי המשתמש")
        except Exception as e:
            log(f"\nשגיאה: {e}")
            import traceback
            log(traceback.format_exc())
        finally:
            save_progress(done)
            allow_sleep()
            try:
                await browser.close()
            except Exception:
                pass
            log(f"\nסיום. {len(done)} שילובים הושלמו.")
            if _log_fh:
                _log_fh.close()


asyncio.run(main())
