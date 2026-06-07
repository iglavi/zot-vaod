"""
scrape_range.py — סקראפר עם חלוקה בינארית של תאריכים
במקום לפלטר לפי שופט מראש, מחלק טווח תאריכים לשניים כשיש 100 תוצאות.
אם מגיע ליום בודד עם 100 — עובר לפילטר שופט ואז הליך.
"""

import asyncio
import calendar
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
_cfg = json.loads(Path("config_net_hamishpat_D.json").read_text(encoding="utf-8"))

# בגרסה זו: date_from ו-date_to במקום target_date בלבד
DATE_FROM = _cfg.get("date_from", _cfg.get("target_date", "2026-01-01"))
DATE_TO   = _cfg.get("date_to",   _cfg.get("target_date", "2026-01-01"))

OUTPUT_DIR    = Path(_cfg["output_dir"])
MASTER_CSV    = OUTPUT_DIR / _cfg.get("metadata_file", "metadata.csv")
PROGRESS_FILE = OUTPUT_DIR / _cfg.get("progress_file", "progress.json")
DATA_FILE     = OUTPUT_DIR / "data.json"
LOG_FILE      = OUTPUT_DIR / _cfg.get("log_file", "log.txt")

HEADLESS       = _cfg.get("headless", False)
DECISION_TYPES = _cfg.get("decision_types", ["פסק דין", "גזר דין", "הכרעת דין"])
BATCH_SIZE     = _cfg.get("batch_size", 30)
BATCH_REST_SEC = _cfg.get("batch_rest_seconds", 45)

MASTER_COLS = [
    "תאריך", "בית משפט", "הליך", "סוג תיק", "סוג עניין",
    "מספר תיק", "שם תיק", "סוג החלטה", "אופי החלטה", "file_path",
]

SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

# ─────────────────────────────────────────────────────────
_log_fh = None
_download_count = 0


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


async def dismiss_ndc_popup(page):
    for overlay_id in [
        "lean_overlay_MessageLS_NoDocumentChosenToDownload",
        "lean_overlay_MessageLS_LocateDecisionsOverflow",
        "lean_overlay_MessageLS_TooManyDocumentChosenToDownload",
        "lean_overlay_MessageLS_ChosenDocumentsUnavailableToDownload",
    ]:
        try:
            overlay = page.locator(f"#{overlay_id}")
            if await overlay.count() > 0 and await overlay.is_visible():
                closed = False
                for selector in [
                    "a.modal_ReturnMessageClose",
                    "a#returnFocus",
                    "button:has-text('אישור')",
                    "a:has-text('אישור')",
                ]:
                    try:
                        el = page.locator(selector)
                        if await el.count() > 0 and await el.first.is_visible():
                            await el.first.click()
                            closed = True
                            break
                    except Exception:
                        pass
                if not closed:
                    await overlay.click(force=True)
                await page.wait_for_timeout(800)
                return
        except Exception:
            pass



async def navigate_to_search(page):
    """
    מנווט לדף החיפוש לפי פרמטרים.
    אם האתר לא זמין — ממתין 2 דקות, אחר כך 2 שעות, אחר כך 2 שעות נוספות.
    """
    WAIT_SCHEDULE = [
        120,        # ניסיון 2: אחרי 2 דקות
        2 * 3600,   # ניסיון 3: אחרי 2 שעות
        2 * 3600,   # ניסיון 4: אחרי 2 שעות נוספות
    ]

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
    """בוחר תאריך ספציפי דרך datepicker."""
    year  = str(d.year)
    month = str(d.month - 1)   # 0-based
    day   = str(d.day)

    await page.locator(f"#{field_id}").click()
    await page.wait_for_timeout(800)
    dp = "#ui-datepicker-div"
    try:
        await page.locator(f"{dp} select.ui-datepicker-year").select_option(year)
        await page.wait_for_timeout(300)
    except Exception:
        pass
    await page.locator(f"{dp} select.ui-datepicker-month").select_option(month)
    await page.wait_for_timeout(300)
    await page.locator(f"{dp} a.ui-state-default", has_text=day).first.click()
    await page.wait_for_timeout(300)


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
    await dismiss_ndc_popup(page)
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
            await dismiss_ndc_popup(page)
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


async def go_next_page(page) -> bool:
    try:
        moved = await page.evaluate("""
            () => {
                const container = document.querySelector('[ref="btNext"]');
                if (!container) return false;
                if (container.getAttribute('aria-disabled') === 'true') return false;
                // מנסה כפתור פנימי, אחר כך ה-container עצמו
                const btn = container.querySelector('button');
                if (btn) { btn.click(); return true; }
                container.click();
                return true;
            }
        """)
        if moved:
            await page.wait_for_timeout(2000)
            log("    → דף הבא")
            return True
    except Exception:
        pass
    return False


# ── הורדות ───────────────────────────────────────────────

def safe_name(text: str, max_len: int = 60) -> str:
    clean = re.sub(r'[\\/:*?"<>|\n\r\t ]', '_', str(text).strip())
    return clean[:max_len]


def extract_date_from_row(row: dict) -> str:
    """מחלץ תאריך ומנקה לפורמט YYYY-MM-DD. האתר שולח '02/01/2026 14:06:10'."""
    raw = ""
    for key in row.keys():
        if 'תאריך' in key:
            raw = row[key].strip()
            break
    if not raw:
        return DATE_FROM
    # פורמט DD/MM/YYYY (עם או בלי שעה)
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', raw)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    # פורמט YYYY-MM-DD
    m = re.search(r'(\d{4}-\d{2}-\d{2})', raw)
    if m:
        return m.group(1)
    return DATE_FROM


async def click_checkbox_for_row(page, row_idx: int, local_idx: int) -> dict | None:
    # גלילה לשורה
    try:
        await page.evaluate(f"""
            () => {{
                const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
                if (row) {{
                    row.scrollIntoView({{block: 'center', behavior: 'instant'}});
                }} else {{
                    const agBody = document.querySelector('.ag-body-viewport');
                    if (agBody) {{
                        const anyRow = document.querySelector('.ag-row');
                        const rowH = anyRow ? (anyRow.offsetHeight || 42) : 42;
                        agBody.scrollTop = Math.max(0, {row_idx} * rowH - agBody.clientHeight / 2);
                    }}
                }}
            }}
        """)
        await page.wait_for_timeout(500)
    except Exception:
        pass

    # מציאת ה-checkbox
    pos = None
    try:
        pos = await page.evaluate(f"""
            () => {{
                const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
                if (row) {{
                    const cb = row.querySelector('input[type=checkbox]');
                    if (cb) {{
                        const r = cb.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0)
                            return {{x: r.left + r.width / 2, y: r.top + r.height / 2}};
                    }}
                }}
                const dataCbs = [...document.querySelectorAll('input[type=checkbox]')].filter(cb =>
                    cb.offsetParent !== null &&
                    !cb.parentElement?.parentElement?.className.includes('ag-header-select-all')
                );
                if ({local_idx} >= dataCbs.length) return null;
                const cell = dataCbs[{local_idx}].closest('.ag-cell');
                if (!cell) return null;
                const r = cell.getBoundingClientRect();
                return {{x: r.x + r.width / 2, y: r.y + r.height / 2}};
            }}
        """)
    except Exception:
        return None

    if not pos:
        log(f"      אין checkbox לשורה {row_idx}")
        return None

    await page.mouse.click(pos["x"], pos["y"])
    await page.wait_for_timeout(600)

    is_checked = await page.evaluate(f"""
        () => {{
            const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
            if (row) {{
                const cb = row.querySelector('input[type=checkbox]');
                if (cb) return cb.checked;
            }}
            const dataCbs = [...document.querySelectorAll('input[type=checkbox]')].filter(cb =>
                cb.offsetParent !== null &&
                !cb.parentElement?.parentElement?.className.includes('ag-header-select-all')
            );
            if ({local_idx} < dataCbs.length) return dataCbs[{local_idx}].checked;
            return false;
        }}
    """)

    if not is_checked:
        await page.mouse.click(pos["x"], pos["y"])
        await page.wait_for_timeout(600)
        is_checked = await page.evaluate(f"""
            () => {{
                const dataCbs = [...document.querySelectorAll('input[type=checkbox]')].filter(cb =>
                    cb.offsetParent !== null &&
                    !cb.parentElement?.parentElement?.className.includes('ag-header-select-all')
                );
                if ({local_idx} < dataCbs.length) return dataCbs[{local_idx}].checked;
                return false;
            }}
        """)
        if not is_checked:
            log(f"      checkbox לא נרשם — מדלג")
            return None

    return pos


async def download_word_for_row(page, row_idx: int, local_idx: int, case_number: str, file_date: str) -> Path | None:
    global _download_count

    docs_dir = OUTPUT_DIR / "Giluy_Naot"
    docs_dir.mkdir(parents=True, exist_ok=True)

    safe_cn = safe_name(case_number)
    fname = f"{safe_cn}_{file_date}.docx"
    save_path = docs_dir / fname

    if save_path.exists():
        log(f"      קיים: {fname} — מדלג")
        return save_path

    await dismiss_ndc_popup(page)

    pos = await click_checkbox_for_row(page, row_idx, local_idx)
    if not pos:
        return None

    save_path = None
    handle_dialog = None
    try:
        async def handle_dialog(dialog):
            await dialog.accept()
        page.on("dialog", handle_dialog)

        save_path = docs_dir / fname

        async with page.expect_download(timeout=15000) as dl_info:
            await page.locator("#btnDownloadWordDocs").click()
        dl = await dl_info.value
        await dl.save_as(str(save_path))
        log(f"      [OK] {fname}")
        _download_count += 1

    except Exception as e:
        log(f"      שגיאת הורדה: {e}")
        save_path = None
        # סגירת פופאפ שגיאת הורדה — מנסה כמה דרכים
        try:
            closed = False
            for selector in [
                "a.modal_ReturnMessageClose",
                "a#returnFocus",
                ".modal_close2",
                "a:has-text('אישור')",
            ]:
                try:
                    el = page.locator(selector)
                    if await el.count() > 0:
                        await el.first.click(force=True)
                        await page.wait_for_timeout(800)
                        closed = True
                        break
                except Exception:
                    pass
            if not closed:
                # ניסיון אחרון — Escape
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)
        except Exception:
            pass
        await dismiss_ndc_popup(page)
    finally:
        if handle_dialog:
            try:
                page.remove_listener("dialog", handle_dialog)
            except Exception:
                pass

    # ביטול כל הסימונים — מונע TooManyDocuments בהורדה הבאה
    try:
        await page.evaluate("""
            () => {
                const dataCbs = [...document.querySelectorAll('input[type=checkbox]')].filter(cb =>
                    cb.offsetParent !== null &&
                    !cb.parentElement?.parentElement?.className.includes('ag-header-select-all')
                );
                dataCbs.forEach(cb => {
                    if (cb.checked) {
                        cb.checked = false;
                        cb.dispatchEvent(new Event('change', {bubbles: true}));
                        cb.dispatchEvent(new Event('click', {bubbles: true}));
                    }
                });
            }
        """)
        await page.wait_for_timeout(400)
    except Exception:
        pass

    return save_path


# ── master CSV ────────────────────────────────────────────

def append_to_master_csv(rows: list[dict]):
    if not rows:
        return
    file_exists = MASTER_CSV.exists()
    with open(MASTER_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=MASTER_COLS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


# ── עיבוד תוצאות ─────────────────────────────────────────

ROWS_PER_PAGE = 18  # AG-Grid מציג 18 שורות בכל עמוד

async def process_results(page):
    global _download_count

    # טוענים את כל המטא-דאטה פעם אחת בלבד (ה-CSV מכיל את כל התוצאות)
    await dismiss_ndc_popup(page)
    all_rows = await export_page_csv(page)
    if not all_rows:
        return
    log(f"    CSV: {len(all_rows)} שורות")

    # מחלקים לעמודים של 18
    pages = [all_rows[i:i+ROWS_PER_PAGE] for i in range(0, len(all_rows), ROWS_PER_PAGE)]
    total_pages = len(pages)

    for page_num, page_rows in enumerate(pages, 1):
        log(f"    דף תוצאות {page_num}/{total_pages}")

        master_rows = []
        for i, row in enumerate(page_rows):
            case_number = row.get("מספר תיק", f"unknown_{i}").strip()
            file_date   = extract_date_from_row(row) or DATE_FROM
            global_idx  = (page_num - 1) * ROWS_PER_PAGE + i + 1
            log(f"      שורה {global_idx}/{len(all_rows)}: {case_number}")

            await asyncio.sleep(random.uniform(2, 4))
            # i הוא האינדקס בתוך העמוד הנוכחי (0-17) — row-index מתאפס בכל עמוד
            save_path = await download_word_for_row(page, i, i, case_number, file_date)

            master_row = {col: row.get(col, "") for col in MASTER_COLS}
            master_row["תאריך"]    = file_date
            master_row["file_path"] = str(save_path) if save_path else ""
            master_rows.append(master_row)

            if _download_count > 0 and _download_count % BATCH_SIZE == 0:
                log(f"    [מנוחה] {_download_count} הורדות...")
                await asyncio.sleep(BATCH_REST_SEC)

        append_to_master_csv(master_rows)

        # עוברים לעמוד הבא רק אם יש עמוד נוסף
        if page_num < total_pages:
            if not await go_next_page(page):
                log(f"    ← לא הצלחנו לעבור לעמוד {page_num + 1} — עוצרים")
                break


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
            # עוברים לפילטר שופטים
            log(f"{indent}  יום בודד עם 100 — מחלק לפי שופטים")
            judge_count = await page.locator(
                "#LocateByParameters1_ddlJudgeName option"
            ).count()
            for jidx in range(1, judge_count):
                await scrape_range(page, court_idx, dt_name,
                                   from_date, to_date,
                                   judge_idx=jidx,
                                   depth=depth + 1)
                await asyncio.sleep(random.uniform(1, 2))
        elif proc_idx is None:
            # כבר פילטרנו שופט — עוברים להליך
            log(f"{indent}  שופט+יום עם 100 — מחלק לפי הליך")
            proc_count = await page.locator(
                "#LocateByParameters1_ddlSelectProceeding option"
            ).count()
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
                from playwright.async_api import async_playwright as _ap
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

            # ערכאות שדולגות — בית דין צבאי, ועדת שחרורים, ועדות שונות
            SKIP_PREFIXES = ("בית דין", "בית משפט צבאי", "ועדת שחרורים")

            # לולאה על כל יום בטווח בנפרד
            current_d = from_d
            while current_d <= to_d:
                day_str = date_to_str(current_d)
                log(f"\n{'=' * 50}")
                log(f"יום: {day_str}")

                for dt_name in DECISION_TYPES:
                    log(f"\n  סוג החלטה: {dt_name}")

                    for court_idx in range(1, num_courts):
                        court_name = court_names[court_idx]

                        if any(court_name.startswith(p) for p in SKIP_PREFIXES):
                            log(f"    ערכאה {court_idx}: {court_name} — מדולג (לא רלוונטי)")
                            continue

                        key = progress_key(day_str, day_str, dt_name, court_idx)

                        if key in done:
                            log(f"    ערכאה {court_idx}: {court_name} — כבר הושלם")
                            continue

                        log(f"\n    ערכאה {court_idx}: {court_name}")
                        await scrape_range(page, court_idx, dt_name, current_d, current_d)

                        done.add(key)
                        save_progress(done)
                        await asyncio.sleep(random.uniform(1, 3))

                current_d += timedelta(days=1)

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
