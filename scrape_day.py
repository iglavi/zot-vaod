"""
scrape_day.py
סקראפר החלטות בית משפט — יום אחד, כל הערכאות וסוגי החלטה.
הגדרות: config.json | מטמון ערכאות: data.json | התקדמות: progress.json
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
BATCH_SIZE     = _cfg.get("batch_size", 30)        # מנוחה אחרי כל N הורדות
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
_download_count = 0   # מונה להפעלת מנוחות


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
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    except Exception:
        pass


def allow_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)  # ES_CONTINUOUS
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
    """סוגר popup 'לא נבחרו מסמכים להורדה' — מונע חסימת לחיצות עתידיות."""
    try:
        overlay = page.locator("#lean_overlay_MessageLS_NoDocumentChosenToDownload")
        if await overlay.count() > 0:
            await overlay.click(force=True, timeout=2000)
            await page.wait_for_timeout(500)
            return
    except Exception:
        pass
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
    except Exception:
        pass


async def navigate_to_search(page):
    """מנווט לדף החיפוש לפי פרמטרים."""
    await page.goto(SITE_URL)
    await page.wait_for_timeout(random.uniform(3500, 5000))
    await dismiss_popup(page)
    await page.get_by_text("איתור החלטות").first.click()
    await page.wait_for_timeout(random.uniform(1500, 2500))
    await page.get_by_text("איתור לפי פרמטרים").first.click()
    await page.wait_for_timeout(random.uniform(1000, 2000))


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


async def do_search(page, court_idx: int, dt_name: str, proc_idx: int | None = None):
    """ממלא את טופס החיפוש ולוחץ חפש. שופט = כל השופטים (index 0)."""
    await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
    await page.wait_for_timeout(1500)
    await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label=dt_name)
    if proc_idx is not None:
        await page.locator("#LocateByParameters1_ddlSelectProceeding").select_option(index=proc_idx)
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
    for sel in ['[ref="btNext"]:not(.ag-disabled)', '[id*="btnNext"]:not([disabled])']:
        try:
            el = page.locator(sel).first
            if await el.is_visible() and await el.is_enabled():
                await el.click()
                await page.wait_for_timeout(1500)
                log("    → דף הבא")
                return True
        except Exception:
            pass
    return False


# ── הורדות ───────────────────────────────────────────────

def safe_name(text: str, max_len: int = 60) -> str:
    clean = re.sub(r'[\\/:*?"<>|\n\r\t ]', '_', str(text).strip())
    return clean[:max_len]


async def download_word_for_row(page, row_idx: int, case_number: str) -> Path | None:
    global _download_count
    DATE_DIR.mkdir(parents=True, exist_ok=True)

    safe_cn = safe_name(case_number)
    existing = list(DATE_DIR.glob(f"{safe_cn}_*.docx"))
    if existing:
        log(f"      קיים: {existing[0].name} — מדלג")
        return existing[0]

    # סגירת popup אם נשאר פתוח מניסיון קודם
    await dismiss_ndc_popup(page)

    # גלילה לשורה — AG-Grid מסתיר שורות מחוץ לתצוגה (virtual DOM)
    try:
        await page.evaluate(f"""
            () => {{
                const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
                if (row) {{
                    row.scrollIntoView({{block: 'center', behavior: 'instant'}});
                }} else {{
                    // השורה לא קיימת ב-DOM — גולל את ה-viewport ישירות
                    const agBody = document.querySelector('.ag-body-viewport');
                    if (agBody) {{
                        const anyRow = document.querySelector('.ag-row');
                        const rowH = anyRow ? (anyRow.offsetHeight || 42) : 42;
                        agBody.scrollTop = Math.max(0, {row_idx} * rowH - agBody.clientHeight / 2);
                    }}
                }}
            }}
        """)
        await page.wait_for_timeout(400)   # מחכים ל-DOM להתעדכן
    except Exception:
        pass

    # מציאת checkbox לפי row-index של AG-Grid
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
                // fallback: לפי מיקום בין checkboxes גלויים
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
        log(f"      שגיאת checkbox: {e}")

    if not pos:
        log(f"      אין checkbox לשורה {row_idx}")
        return None

    await page.mouse.click(pos["x"], pos["y"])
    await page.wait_for_timeout(500)

    # הורדת Word
    save_path = None
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
        await dismiss_ndc_popup(page)   # חיוני — popup חוסם לחיצות עתידיות
    finally:
        try:
            page.remove_listener("dialog", handle_dialog)
        except Exception:
            pass

    # ביטול selection
    try:
        await page.mouse.click(pos["x"], pos["y"])
        await page.wait_for_timeout(300)
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

        # זיהוי דף כפול (pagination שחוזרת להתחלה)
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

            await asyncio.sleep(random.uniform(2, 5))

            save_path = await download_word_for_row(page, i, case_number)

            master_row = {col: row.get(col, "") for col in MASTER_COLS}
            master_row["file_path"] = str(save_path) if save_path else ""
            master_rows.append(master_row)

            # מנוחת batch אחרי כל BATCH_SIZE הורדות מוצלחות
            if _download_count > 0 and _download_count % BATCH_SIZE == 0:
                log(f"    [מנוחה] {_download_count} הורדות — מנוחה {BATCH_REST_SEC}ש'...")
                await asyncio.sleep(BATCH_REST_SEC)

        append_to_master_csv(master_rows)

        has_next = await go_next_page(page)
        if not has_next:
            break
        page_num += 1


# ── לולאה ראשית ──────────────────────────────────────────

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
    log(f"User-Agent: {ua[:60]}...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            accept_downloads=True,
            user_agent=ua,
        )
        page = await context.new_page()

        try:
            # קריאת רשימת ערכאות — עם מטמון ב-data.json
            court_names = None
            if DATA_FILE.exists():
                cached = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                court_names = cached.get("court_names")
                if court_names:
                    log(f"ערכאות מהמטמון: {len(court_names) - 1}")

            if not court_names:
                await navigate_to_search(page)
                court_opts = await page.locator(
                    "#LocateByParameters1_ddlSelectCourt option"
                ).all()
                court_names = [(await opt.inner_text()).strip() for opt in court_opts]
                DATA_FILE.write_text(
                    json.dumps({"court_names": court_names}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                log(f"נשמר מטמון ערכאות → data.json  ({len(court_names) - 1} ערכאות)")

            num_courts = len(court_names)
            log(f"סה\"כ ערכאות: {num_courts - 1}  (index 1..{num_courts - 1})")

            for dt_name in DECISION_TYPES:
                log(f"\n{'=' * 50}")
                log(f"סוג החלטה: {dt_name}")

                for court_idx in range(1, num_courts):
                    court_name = court_names[court_idx]
                    key = progress_key(dt_name, court_idx)

                    if key in done:
                        log(f"  ערכאה {court_idx}/{num_courts - 1}: {court_name} — כבר הושלם")
                        continue

                    log(f"\n  ערכאה {court_idx}/{num_courts - 1}: {court_name}")

                    await navigate_to_search(page)
                    await do_search(page, court_idx, dt_name)

                    count, is_capped = await get_result_count(page)
                    log(f"  תוצאות: {count}{' ← מוגבל ל-100!' if is_capped else ''}")

                    if count > 0:
                        await process_results(page)

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
            _log_fh.close()


asyncio.run(main())
