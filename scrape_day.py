"""
scrape_day.py
Phase 1 — יום בדיקה מלא: 2026-01-01

לולאה על כל הערכאות / שופטים / סוגי החלטה.
מוריד Word docs ושומר metadata.csv מרכזי.
תומך בהמשכה אחרי קריסה (progress.json).
"""

import asyncio
import csv
import json
import random
import re
import tempfile
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

# ── הגדרות ────────────────────────────────────────────────
TARGET_DATE  = "2026-01-01"
TARGET_DAY   = "1"
TARGET_MONTH = "0"       # 0 = ינואר
TARGET_YEAR  = "2026"

OUTPUT_DIR    = Path(r"C:\Users\MPI-User\Desktop\nethamishpat")
DATE_DIR      = OUTPUT_DIR / TARGET_DATE
MASTER_CSV    = OUTPUT_DIR / "metadata.csv"
PROGRESS_FILE = OUTPUT_DIR / "progress.json"
LOG_FILE      = OUTPUT_DIR / "log.txt"

HEADLESS = False   # False = רואים את הדפדפן

DECISION_TYPES = ["פסק דין", "גזר דין", "הכרעת דין"]

MASTER_COLS = [
    "תאריך", "בית משפט", "הליך", "סוג תיק", "סוג עניין",
    "מספר תיק", "שם תיק", "סוג החלטה", "אופי החלטה", "file_path",
]

SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"
# ─────────────────────────────────────────────────────────

_log_fh = None


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


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

async def dismiss_popup(page, timeout=3000):
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


async def navigate_to_search(page):
    """מנווט לדף החיפוש לפי פרמטרים (מהדף הראשי)."""
    await page.goto(SITE_URL)
    await page.wait_for_timeout(4000)
    await dismiss_popup(page)
    await page.get_by_text("איתור החלטות").first.click()
    await page.wait_for_timeout(2000)
    await page.get_by_text("איתור לפי פרמטרים").first.click()
    await page.wait_for_timeout(1500)


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


async def do_search(page, court_idx: int, dt_name: str,
                    proc_idx: int | None = None):
    """ממלא את טופס החיפוש ולוחץ חפש. שופט = כל השופטים (index 0)."""
    await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
    await page.wait_for_timeout(1500)
    # לא מפלטרים לפי שופט — index 0 = "כל השופטים" (ברירת מחדל)
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
    """מייצא CSV מ-AG-Grid עבור הדף הנוכחי. מחזיר רשימת שורות."""
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


async def discover_pagination(page):
    """מגלה ומדפיס כל כפתורי ניווט עמודים שנמצאו בדף."""
    candidates = [
        '[ref="btNext"]',              '.ag-paging-panel [ref="btNext"]',
        'button:has-text("לדף הבא")', 'a:has-text("לדף הבא")',
        'button:has-text("הבא")',      'a:has-text("הבא")',
        '[id*="btnNext"]',             '[id*="NextPage"]',
        '[id*="next_page"]',           '.next-page',
        '.pagination-next',            'li.next a',
        'a[title="הבא"]',             'input[value="הבא"]',
    ]
    found = []
    for sel in candidates:
        try:
            el = page.locator(sel)
            if await el.count() > 0:
                text = (await el.first.inner_text()).strip()
                visible = await el.first.is_visible()
                found.append(f"    {sel!r}  visible={visible}  text={text!r}")
        except Exception:
            pass
    if found:
        log("  [DISCOVERY] כפתורי ניווט עמודים:")
        for f in found:
            log(f)
    else:
        log("  [DISCOVERY] לא נמצאו כפתורי ניווט עמודים")


async def go_next_page(page) -> bool:
    """עובר לדף הבא של AG-Grid. מחזיר True אם עבר, False אם אין."""
    # שיטה ראשונה: כפתור AG-Grid הפנימי [ref="btNext"] דרך JavaScript
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
    # שיטה שנייה: סלקטורים של AG-Grid
    for sel in [
        '[ref="btNext"]:not(.ag-disabled)',
        '.ag-paging-panel [ref="btNext"]',
        '[id*="btnNext"]:not([disabled])',
        '[id*="NextPage"]:not([disabled])',
    ]:
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
    """
    מוריד Word doc עבור שורה row_idx (0-based).
    לוחץ checkbox פיזית → #btnDownloadWordDocs → שומר.
    מחזיר נתיב שנשמר, או None אם נכשל.
    """
    DATE_DIR.mkdir(parents=True, exist_ok=True)

    # דילוג אם קיים
    safe_cn = safe_name(case_number)
    existing = list(DATE_DIR.glob(f"{safe_cn}_*.docx"))
    if existing:
        log(f"      קיים: {existing[0].name} — מדלג")
        return existing[0]

    # לחיצה פיזית על checkbox
    try:
        # גלילה לשורה תחילה (AG-Grid מסתיר שורות מחוץ לתצוגה)
        await page.evaluate(f"""
            () => {{
                const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
                if (row) row.scrollIntoView({{block: 'center', behavior: 'instant'}});
            }}
        """)
        await page.wait_for_timeout(200)
        pos = await page.evaluate(f"""
            () => {{
                // שיטה ראשונה: לפי row-index של AG-Grid
                const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
                if (row) {{
                    const cb = row.querySelector('input[type=checkbox]');
                    if (cb) {{
                        const r = cb.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0)
                            return {{x: r.left + r.width / 2, y: r.top + r.height / 2}};
                    }}
                }}
                // fallback: לפי מיקום בין כל ה-checkboxes הגלויים
                const allCbs = [...document.querySelectorAll('input[type=checkbox]')];
                const dataCbs = allCbs.filter(cb =>
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
        if not pos:
            log(f"      אין checkbox לשורה {row_idx}")
            return None
        await page.mouse.click(pos["x"], pos["y"])
        await page.wait_for_timeout(500)
    except Exception as e:
        log(f"      שגיאת checkbox: {e}")
        return None

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

    except Exception as e:
        log(f"      שגיאת הורדה: {e}")
        save_path = None
    finally:
        try:
            page.remove_listener("dialog", handle_dialog)
        except Exception:
            pass

    # ביטול selection
    if pos:
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


# ── עיבוד תוצאות (כולל pagination) ──────────────────────

async def process_results(page):
    """
    מעבד את כל דפי התוצאות:
    - מייצא CSV לכל דף
    - מוריד Word לכל שורה
    - עובר לדף הבא עד שנגמר
    """
    page_num = 1
    pagination_discovered = False
    first_case_of_page1 = None   # לזיהוי דף כפול (pagination שחוזרת להתחלה)

    while True:
        log(f"    דף תוצאות {page_num}")

        # גילוי pagination בדף הראשון
        if page_num == 1 and not pagination_discovered:
            await discover_pagination(page)
            pagination_discovered = True

        rows = await export_page_csv(page)
        if not rows:
            count, _ = await get_result_count(page)
            if count == 0:
                log("    אין תוצאות בדף")
            break

        # בדיקת דף כפול — אם הדף החדש מתחיל באותה שורה כמו דף 1, עצור
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

    _log_fh = open(LOG_FILE, "a", encoding="utf-8")
    log("=" * 60)
    log(f"מתחיל ריצה — תאריך: {TARGET_DATE}")

    done = load_progress()
    log(f"התקדמות קיימת: {len(done)} שילובים הושלמו")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # קריאת מספר ערכאות (פעם אחת)
            await navigate_to_search(page)
            court_options = await page.locator(
                "#LocateByParameters1_ddlSelectCourt option"
            ).all()
            num_courts = len(court_options)
            log(f"סה\"כ ערכאות: {num_courts - 1}  (index 1..{num_courts - 1})")

            # טעינת שמות ערכאות מראש
            court_names = []
            for opt in court_options:
                court_names.append((await opt.inner_text()).strip())

            for dt_name in DECISION_TYPES:
                log(f"\n{'=' * 50}")
                log(f"סוג החלטה: {dt_name}")

                for court_idx in range(1, num_courts):  # 0 = "כל הערכאות"
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

                # ── קוד פילטור לפי שופט — שמור לשימוש עתידי (טווחי תאריך רחבים) ──────
                # for court_idx in range(1, num_courts):
                #     await navigate_to_search(page)
                #     court_name = court_names[court_idx]
                #     await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
                #     await page.wait_for_timeout(3000)
                #     judge_options = await page.locator("#LocateByParameters1_ddlJudgeName option").all()
                #     judge_names = [(await opt.inner_text()).strip() for opt in judge_options]
                #     for judge_idx in range(1, len(judge_names)):
                #         judge_name = judge_names[judge_idx]
                #         key = progress_key(dt_name, court_idx, judge_idx)
                #         if key in done:
                #             continue
                #         await navigate_to_search(page)
                #         await do_search(page, court_idx, dt_name)  # להוסיף judge_idx בחתימה
                #         count, is_capped = await get_result_count(page)
                #         if count > 0:
                #             await process_results(page)
                #         done.add(key); save_progress(done)
                # ─────────────────────────────────────────────────────────────────────

        except KeyboardInterrupt:
            log("\nנעצר על ידי המשתמש (Ctrl+C)")
        except Exception as e:
            log(f"\nשגיאה לא צפויה: {e}")
            import traceback
            log(traceback.format_exc())
        finally:
            save_progress(done)
            try:
                await browser.close()
            except Exception:
                pass
            log(f"\nסיום. {len(done)} שילובים הושלמו.")
            _log_fh.close()


asyncio.run(main())
