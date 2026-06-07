"""
scrape_day.py — גרסה מתוקנת
תיקונים:
1. checkbox: בדיקת checked אחרי לחיצה + retry
2. תאריך: קריאה גמישה מה-CSV + מיצוי משם הקובץ
3. יעילות: חיפוש ללא שופט קודם, שופט רק אם 100 תוצאות
4. dismiss_ndc_popup: מטפל ב-overlay + dialog
5. encoding: ensure_ascii=False בכל JSON
"""

import asyncio
import csv
import ctypes
import json
import random
import re
import tempfile
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

# ── קריאת הגדרות ──────────────────────────────────────────
_cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))

TARGET_DATE  = _cfg["target_date"]
_y, _m, _d  = TARGET_DATE.split("-")
TARGET_DAY   = str(int(_d))
TARGET_MONTH = str(int(_m) - 1)   # 0-based לחודש ב-datepicker
TARGET_YEAR  = _y

OUTPUT_DIR    = Path(_cfg["output_dir"])
DATE_DIR      = OUTPUT_DIR / TARGET_DATE
MASTER_CSV    = OUTPUT_DIR / "metadata.csv"
PROGRESS_FILE = OUTPUT_DIR / "progress.json"
DATA_FILE     = OUTPUT_DIR / "data.json"
LOG_FILE      = OUTPUT_DIR / "log.txt"

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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
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


# ── מניעת שינה (Windows) ─────────────────────────────────

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


# ── ניווט ────────────────────────────────────────────────

async def dismiss_popup(page):
    """סוגר popup כללי עם כפתור אישור."""
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
    try:
        await page.evaluate("""
            () => {
                const el = [...document.querySelectorAll(
                    'button, input[type=button], input[type=submit]'
                )].find(e => (e.textContent + e.value).includes('אישור'));
                if (el) el.click();
            }
        """)
    except Exception:
        pass


async def dismiss_ndc_popup(page):
    """
    סוגר popup 'לא נבחרו מסמכים' ו-'תוצאות מוגבלות'.
    תיקון: ממתין שהחסימה תיעלם לפני שממשיכים.
    """
    for overlay_id in [
        "lean_overlay_MessageLS_NoDocumentChosenToDownload",
        "lean_overlay_MessageLS_LocateDecisionsOverflow",
        "lean_overlay_MessageLS_TooManyDocumentChosenToDownload",
        "lean_overlay_MessageLS_ChosenDocumentsUnavailableToDownload",
    ]:
        try:
            overlay = page.locator(f"#{overlay_id}")
            if await overlay.count() > 0 and await overlay.is_visible():
                ok_btn = page.locator("button", has_text="אישור")
                if await ok_btn.count() > 0:
                    await ok_btn.first.click()
                else:
                    await overlay.click(force=True)
                await page.wait_for_timeout(800)
                log("      [popup] סגרתי overlay")
                return
        except Exception:
            pass

    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
    except Exception:
        pass


async def navigate_to_search(page):
    """
    מנווט לדף החיפוש לפי פרמטרים.
    אם האתר לא זמין — ממתין 3 דקות (x3), אחר כך 8 שעות, אחר כך 2 שעות (x2).
    """
    WAIT_SCHEDULE = [
        180,        # ניסיון 2: אחרי 3 דקות
        180,        # ניסיון 3: אחרי 3 דקות נוספות
        180,        # ניסיון 4: אחרי 3 דקות נוספות
        8 * 3600,   # ניסיון 5: אחרי 8 שעות
        2 * 3600,   # ניסיון 6: אחרי 2 שעות
        2 * 3600,   # ניסיון 7: אחרי 2 שעות נוספות
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

async def set_date(page, field_id: str):
    """בוחר תאריך דרך jQuery UI datepicker."""
    await page.locator(f"#{field_id}").click()
    await page.wait_for_timeout(1000)
    dp = "#ui-datepicker-div"
    try:
        await page.locator(f"{dp} select.ui-datepicker-year").select_option(TARGET_YEAR)
        await page.wait_for_timeout(400)
    except Exception:
        pass
    await page.locator(f"{dp} select.ui-datepicker-month").select_option(TARGET_MONTH)
    await page.wait_for_timeout(400)
    await page.locator(f"{dp} a.ui-state-default", has_text=TARGET_DAY).first.click()
    await page.wait_for_timeout(400)


async def do_search(page, court_idx: int, dt_name: str, judge_idx: int | None = None, proc_idx: int | None = None):
    """
    ממלא את טופס החיפוש ולוחץ חפש.
    judge_idx=None = כל השופטים (ברירת מחדל — לא מציין שופט)
    """
    await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
    await page.wait_for_timeout(1500)

    if judge_idx is not None:
        try:
            await page.locator("#LocateByParameters1_ddlJudgeName").select_option(index=judge_idx)
            await page.wait_for_timeout(500)
        except Exception:
            pass

    await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label=dt_name)
    await page.wait_for_timeout(500)

    if proc_idx is not None:
        await page.locator("#LocateByParameters1_ddlSelectProceeding").select_option(index=proc_idx)
        await page.wait_for_timeout(500)

    await set_date(page, "LocateByParameters1_dateFrom")
    await set_date(page, "LocateByParameters1_DateTo")
    await page.locator("#ButtonsGroup1_btnLocate").click()
    await page.wait_for_timeout(3000)
    await dismiss_popup(page)
    await page.wait_for_timeout(1000)


# ── תוצאות ───────────────────────────────────────────────

async def get_result_count(page) -> tuple[int, bool]:
    """מחזיר (מספר תוצאות, האם מוגבל ל-100)."""
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


async def export_page_csv(page) -> list[dict]:
    """מייצא CSV מ-AG-Grid. מחזיר רשימת שורות."""
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
        log(f"    CSV: {len(rows)} שורות")
        return rows
    except Exception as e:
        log(f"    שגיאת CSV: {e}")
        return []


async def go_next_page(page) -> bool:
    """עובר לדף הבא של AG-Grid. מחזיר True אם עבר."""
    try:
        moved = await page.evaluate("""
            () => {
                const btn = document.querySelector('[ref="btNext"]');
                if (!btn) return false;
                if (btn.classList.contains('ag-disabled') || btn.disabled) return false;
                btn.click();
                return true;
            }
        """)
        if moved:
            await page.wait_for_timeout(1500)
            log("    → דף הבא (AG-Grid)")
            return True
    except Exception:
        pass
    return False


# ── הורדות ───────────────────────────────────────────────

def safe_name(text: str, max_len: int = 60) -> str:
    clean = re.sub(r'[\\/:*?"<>|\n\r\t ]', '_', str(text).strip())
    return clean[:max_len]


def extract_date_from_csv_row(row: dict) -> str:
    """
    תיקון: קריאה גמישה של עמודת תאריך.
    שם העמודה האמיתי הוא 'תאריך מתן החלטה' ולא 'תאריך'.
    """
    for key in row.keys():
        if 'תאריך' in key:
            return row[key].strip()
    return TARGET_DATE


async def click_checkbox_for_row(page, row_idx: int) -> dict | None:
    """
    תיקון עיקרי: לחיצה על checkbox + בדיקה שאכן נרשם ב-AG-Grid.
    מחזיר את המיקום אם הצליח, None אם נכשל.
    """
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

    # מציאת מיקום checkbox
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
                // fallback: לפי index בין checkboxes גלויים
                const dataCbs = [...document.querySelectorAll('input[type=checkbox]')].filter(cb =>
                    cb.offsetParent !== null &&
                    !cb.parentElement?.parentElement?.className.includes('ag-header-select-all')
                );
                if ({row_idx} >= dataCbs.length) return null;
                const cell = dataCbs[{row_idx}].closest('.ag-cell');
                if (!cell) return null;
                const r = cell.getBoundingClientRect();
                return {{x: r.x + r.width / 2, y: r.y + r.height / 2}};
            }}
        """)
    except Exception as e:
        log(f"      שגיאת מציאת checkbox: {e}")
        return None

    if not pos:
        log(f"      אין checkbox לשורה {row_idx}")
        return None

    # לחיצה ראשונה
    await page.mouse.click(pos["x"], pos["y"])
    await page.wait_for_timeout(600)

    # בדיקה שהסימון נרשם ב-AG-Grid
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
            if ({row_idx} < dataCbs.length) return dataCbs[{row_idx}].checked;
            return false;
        }}
    """)

    if not is_checked:
        log(f"      checkbox לא נרשם — מנסה שוב")
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
                if ({row_idx} < dataCbs.length) return dataCbs[{row_idx}].checked;
                return false;
            }}
        """)

        if not is_checked:
            log(f"      checkbox עדיין לא נרשם — מדלג על שורה {row_idx}")
            return None

    return pos


async def download_word_for_row(page, row_idx: int, case_number: str) -> Path | None:
    global _download_count
    DATE_DIR.mkdir(parents=True, exist_ok=True)

    safe_cn = safe_name(case_number)
    existing = list(DATE_DIR.glob(f"{safe_cn}_*.docx"))
    if existing:
        log(f"      קיים: {existing[0].name} — מדלג")
        return existing[0]

    await dismiss_ndc_popup(page)

    pos = await click_checkbox_for_row(page, row_idx)
    if not pos:
        return None

    save_path = None
    handle_dialog = None
    try:
        async def handle_dialog(dialog):
            await dialog.accept()
        page.on("dialog", handle_dialog)

        ts = datetime.now().strftime("%H%M%S")
        fname = f"{safe_cn}_{TARGET_DATE}_{ts}.docx"
        save_path = DATE_DIR / fname

        async with page.expect_download(timeout=30000) as dl_info:
            await page.locator("#btnDownloadWordDocs").click()
        dl = await dl_info.value
        await dl.save_as(str(save_path))
        log(f"      [OK] {fname}")
        _download_count += 1

    except Exception as e:
        log(f"      שגיאת הורדה: {e}")
        save_path = None
        await dismiss_ndc_popup(page)
    finally:
        if handle_dialog:
            try:
                page.remove_listener("dialog", handle_dialog)
            except Exception:
                pass

    # ביטול כל הסימונים — מונע TooMany/Unavailable בהורדה הבאה
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


# ── עיבוד תוצאות ──────────────────────────────────────────

async def process_results(page):
    global _download_count
    page_num = 1
    first_case_of_page1 = None

    while True:
        log(f"    דף תוצאות {page_num}")

        rows = await export_page_csv(page)
        if not rows:
            log("    אין תוצאות בדף")
            break

        first_case = rows[0].get("מספר תיק", "").strip()
        if page_num == 1:
            first_case_of_page1 = first_case
        elif first_case and first_case == first_case_of_page1:
            log(f"    ← דף {page_num} זהה לדף 1 — pagination לא עובדת, עוצר")
            break

        master_rows = []
        for i, row in enumerate(rows):
            case_number = row.get("מספר תיק", row.get("case_number", f"unknown_{i}")).strip()
            log(f"      שורה {i + 1}/{len(rows)}: {case_number}")

            await asyncio.sleep(random.uniform(2, 4))

            save_path = await download_word_for_row(page, i, case_number)

            date_val = extract_date_from_csv_row(row)

            master_row = {col: row.get(col, "") for col in MASTER_COLS}
            master_row["תאריך"] = date_val
            master_row["file_path"] = str(save_path) if save_path else ""
            master_rows.append(master_row)

            if _download_count > 0 and _download_count % BATCH_SIZE == 0:
                log(f"    [מנוחה] {_download_count} הורדות — מנוחה {BATCH_REST_SEC}ש'...")
                await asyncio.sleep(BATCH_REST_SEC)

        append_to_master_csv(master_rows)

        has_next = await go_next_page(page)
        if not has_next:
            break
        page_num += 1


# ── לולאה ראשית מיועלת ───────────────────────────────────

async def process_court_decision_type(page, court_idx: int, court_name: str, dt_name: str, judge_names: list):
    """
    יעילות: חיפוש ללא שופט קודם, פיצול לשופטים רק אם 100 תוצאות.
    """
    log(f"\n  ערכאה {court_idx}: {court_name}")

    await navigate_to_search(page)
    await do_search(page, court_idx, dt_name)  # ללא שופט

    count, is_capped = await get_result_count(page)
    log(f"  תוצאות: {count}{' ← מוגבל ל-100!' if is_capped else ''}")

    if count == 0:
        return

    if not is_capped:
        await process_results(page)
    else:
        log(f"  → מחלק לפי שופטים ({len(judge_names) - 1} שופטים)")
        for judge_idx in range(1, len(judge_names)):
            judge_name = judge_names[judge_idx]
            log(f"    שופט {judge_idx}: {judge_name}")

            await navigate_to_search(page)
            await do_search(page, court_idx, dt_name, judge_idx=judge_idx)

            j_count, j_capped = await get_result_count(page)
            log(f"    תוצאות: {j_count}{' ← עדיין מוגבל!' if j_capped else ''}")

            if j_count == 0:
                continue

            if j_capped:
                log(f"    → מחלק לפי הליך")
                await split_by_proceeding(page, court_idx, dt_name, judge_idx)
            else:
                await process_results(page)

            await asyncio.sleep(random.uniform(1, 2))


async def split_by_proceeding(page, court_idx: int, dt_name: str, judge_idx: int):
    """חיפוש עם פילטר הליך נוסף כשעדיין יש 100 תוצאות."""
    proc_count = await page.locator(
        "#LocateByParameters1_ddlSelectProceeding option"
    ).count()

    for proc_idx in range(1, proc_count):
        await navigate_to_search(page)
        await do_search(page, court_idx, dt_name, judge_idx=judge_idx, proc_idx=proc_idx)

        p_count, _ = await get_result_count(page)
        if p_count == 0:
            continue

        log(f"      הליך {proc_idx}: {p_count} תוצאות")
        await process_results(page)
        await asyncio.sleep(random.uniform(1, 2))


# ── main ──────────────────────────────────────────────────

async def main():
    global _log_fh
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATE_DIR.mkdir(parents=True, exist_ok=True)

    prevent_sleep()

    _log_fh = open(LOG_FILE, "a", encoding="utf-8")
    log("=" * 60)
    log(f"מתחיל ריצה — תאריך: {TARGET_DATE}")

    done = load_progress()
    log(f"התקדמות קיימת: {len(done)} שילובים הושלמו")

    ua = random.choice(USER_AGENTS)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            accept_downloads=True,
            user_agent=ua,
        )
        page = await context.new_page()

        try:
            # קריאת רשימת ערכאות ושופטים
            court_names = None
            judge_names = None

            if DATA_FILE.exists():
                cached = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                court_names = cached.get("court_names")
                judge_names = cached.get("judge_names")
                if court_names:
                    log(f"ערכאות מהמטמון: {len(court_names) - 1}")
                if judge_names:
                    log(f"שופטים מהמטמון: {len(judge_names) - 1}")

            if not court_names or not judge_names:
                await navigate_to_search(page)
                court_opts = await page.locator(
                    "#LocateByParameters1_ddlSelectCourt option"
                ).all()
                court_names = [(await opt.inner_text()).strip() for opt in court_opts]

                # בחר ערכאה ראשונה כדי לטעון רשימת שופטים
                await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=1)
                await page.wait_for_timeout(2000)
                judge_opts = await page.locator(
                    "#LocateByParameters1_ddlJudgeName option"
                ).all()
                judge_names = [(await opt.inner_text()).strip() for opt in judge_opts]

                DATA_FILE.write_text(
                    json.dumps(
                        {"court_names": court_names, "judge_names": judge_names},
                        ensure_ascii=False, indent=2
                    ),
                    encoding="utf-8",
                )
                log(f"נשמר מטמון → data.json ({len(court_names) - 1} ערכאות, {len(judge_names) - 1} שופטים)")

            num_courts = len(court_names)
            log(f"סה\"כ ערכאות: {num_courts - 1}")

            for dt_name in DECISION_TYPES:
                log(f"\n{'=' * 50}")
                log(f"סוג החלטה: {dt_name}")

                for court_idx in range(1, num_courts):
                    court_name = court_names[court_idx]
                    key = progress_key(dt_name, court_idx)

                    if key in done:
                        log(f"  ערכאה {court_idx}/{num_courts - 1}: {court_name} — כבר הושלם")
                        continue

                    await process_court_decision_type(
                        page, court_idx, court_name, dt_name, judge_names
                    )

                    done.add(key)
                    save_progress(done)
                    await asyncio.sleep(random.uniform(1, 3))

        except KeyboardInterrupt:
            log("\nנעצר על ידי המשתמש (Ctrl+C)")
        except Exception as e:
            log(f"\nשגיאה לא צפויה: {e}")
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
