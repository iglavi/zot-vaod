"""
case_fetcher.py — שליפת מטאדאטא של החלטות לפי מספר תיק מנט המשפט
קבלת מספר תיק → כניסה לאתר → חיפוש לפי תיק → ייצוא CSV → איחוד לקובץ מרכזי
"""

import asyncio
import csv
import re
import tempfile
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright

# ── הגדרות ──────────────────────────────────────────────────
SITE_URL     = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"
OUTPUT_DIR   = Path(r"C:\Users\MPI-User\Desktop\nethamishpat")
COMBINED_CSV = OUTPUT_DIR / "metadata_combined.csv"
LOG_FILE     = OUTPUT_DIR / "case_fetcher_log.txt"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]


# ── לוג ────────────────────────────────────────────────────
def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── פיצול מספר תיק ─────────────────────────────────────────

def parse_case_number(raw: str) -> dict:
    """
    מקבל מחרוזת מספר תיק ומחזיר:
      {
        "main": "54951",
        "suffix": "08-25",
        "is_new": True/False,
      }

    פורמטים נתמכים:
      תיק חדש (מקף):        54951-08-25
      תיק חדש (לוכסן הפוך): 7/24/5304
      תיק ישן (לוכסן):      4084/17
    """
    raw = raw.strip()

    m = re.match(r'^(\d{1,2})/(\d{2})/(\d{3,})$', raw)
    if m:
        month = m.group(1).zfill(2)
        year  = m.group(2)
        return {"main": m.group(3), "suffix": f"{month}-{year}", "is_new": True}

    m = re.match(r'^(\d+)-(\d{2}-\d{2})$', raw)
    if m:
        return {"main": m.group(1), "suffix": m.group(2), "is_new": True}

    m = re.match(r'^(\d+)/(\d+)$', raw)
    if m:
        return {"main": m.group(1), "suffix": m.group(2), "is_new": False}

    raise ValueError(f"לא זוהה פורמט מספר תיק: '{raw}'")


# ── ניווט ───────────────────────────────────────────────────

async def dismiss_popup(page):
    for locator in [
        page.locator("button", has_text="אישור"),
        page.locator("input[value='אישור']"),
        page.locator("a.modal_ReturnMessageClose"),
        page.locator("a#returnFocus"),
    ]:
        try:
            if await locator.count() > 0 and await locator.first.is_visible():
                await locator.first.click()
                await page.wait_for_timeout(600)
                return
        except Exception:
            pass


async def navigate_to_case_search(page):
    log("נכנס לאתר...")
    await page.goto(SITE_URL, timeout=45000)
    await page.wait_for_timeout(3500)
    await dismiss_popup(page)
    await page.wait_for_timeout(500)

    log("לוחץ על איתור החלטות...")
    await page.get_by_text("איתור החלטות").first.click(timeout=20000)
    await page.wait_for_timeout(2000)

    log("לוחץ על איתור לפי תיק...")
    await page.get_by_text("איתור לפי תיק").first.click(timeout=20000)
    await page.wait_for_timeout(1500)


# ── מילוי טופס חיפוש ────────────────────────────────────────

async def fill_case_search(page, case_number: str, is_traffic: bool = False,
                           court_name: str = ""):
    parsed = parse_case_number(case_number)
    main   = parsed["main"]
    suffix = parsed["suffix"]
    is_new = parsed["is_new"]

    log(f"מספר תיק: main={main}, suffix={suffix}, {'חדש' if is_new else 'ישן'}, {'תעבורה' if is_traffic else 'בית משפט'}")

    if is_new:
        new_radio = page.locator("#CaseLocatorUC1_BamaCaseIdentifierOptionBoxVT")
        if await new_radio.count() > 0 and not await new_radio.is_checked():
            await new_radio.click()
            await page.wait_for_timeout(500)

        if is_traffic:
            traffic_radio = page.locator("#CaseLocatorUC1_NumeratorGroupTypeVT_Value_eq_2")
            if await traffic_radio.count() > 0:
                await traffic_radio.click()
                await page.wait_for_timeout(500)

        await page.evaluate(f"""
            () => {{
                const el = document.getElementById('CaseLocatorUC1_BamaCaseNumberTextBoxVT');
                if (el) {{ el.removeAttribute('readonly'); el.value = '{main}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }}
            }}
        """)
        await page.wait_for_timeout(300)
        await page.evaluate(f"""
            () => {{
                const el = document.getElementById('CaseLocatorUC1_BamaMonthYearTextBoxVT');
                if (el) {{ el.removeAttribute('readonly'); el.value = '{suffix}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }}
            }}
        """)
        await page.wait_for_timeout(300)

    else:
        old_radio = page.locator("#CaseLocatorUC1_OldCaseIdentifierOptionBoxVT")
        if await old_radio.count() > 0:
            await old_radio.click()
            await page.wait_for_timeout(500)

        if court_name:
            try:
                court_options = await page.locator("#CaseLocatorUC1_PreviousCourtComboBoxVT option").all()
                for opt in court_options:
                    opt_text = await opt.inner_text()
                    if court_name.strip() in opt_text:
                        opt_val = await opt.get_attribute("value")
                        await page.locator("#CaseLocatorUC1_PreviousCourtComboBoxVT").select_option(value=opt_val)
                        log(f"  בית משפט נבחר: {opt_text.strip()}")
                        await page.wait_for_timeout(500)
                        break
            except Exception as e:
                log(f"  שגיאה בבחירת בית משפט: {e}")

        await page.evaluate(f"""
            () => {{
                const el = document.getElementById('CaseLocatorUC1_OldCaseNumberTextBoxVT');
                if (el) {{ el.removeAttribute('readonly'); el.value = '{main}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }}
            }}
        """)
        await page.wait_for_timeout(300)
        await page.evaluate(f"""
            () => {{
                const el = document.getElementById('CaseLocatorUC1_OldYearTextBoxVT');
                if (el) {{ el.removeAttribute('readonly'); el.value = '{suffix}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }}
            }}
        """)
        await page.wait_for_timeout(300)

    log("מחפש...")
    await page.locator("#ButtonsGroup1_btnLocate").click()
    await page.wait_for_timeout(3000)
    await dismiss_popup(page)
    await page.wait_for_timeout(800)


# ── ייצוא תוצאות ────────────────────────────────────────────

async def export_results_csv(page) -> list[dict]:
    """
    מייצא את כל תוצאות החיפוש ל-CSV בלחיצה אחת.
    האתר מייצא את כל התוצאות (מכל העמודים) בבת אחת.
    """
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
        log(f"  CSV יוצא בהצלחה — {len(rows)} שורות")
        return rows
    except Exception as e:
        log(f"  שגיאת ייצוא CSV: {e}")
        return []


# ── איחוד לקובץ מרכזי ───────────────────────────────────────

def _find_col(row: dict, *keywords) -> str:
    """מוצא שם עמודה לפי מילות מפתח."""
    for key in row.keys():
        if all(kw in key for kw in keywords):
            return key
    return ""


def _make_key(row: dict) -> tuple | None:
    """יוצר מפתח ייחודי מ-(מספר תיק, תאריך החלטה)."""
    case_col = _find_col(row, "מספר")
    date_col = _find_col(row, "תאריך")
    if case_col and date_col:
        return (str(row[case_col]).strip(), str(row[date_col]).strip())
    # גיבוי — עמודה ראשונה ושנייה
    keys = list(row.keys())
    if len(keys) >= 2:
        return (str(row[keys[0]]).strip(), str(row[keys[1]]).strip())
    return None


def append_to_combined(rows: list[dict]) -> dict:
    """
    מחבר שורות חדשות לקובץ המאוחד metadata_combined.csv.
    דולג על שורות שכבר קיימות לפי (מספר תיק + תאריך החלטה).
    מחזיר: {"added": int, "skipped": int}
    """
    if not rows:
        return {"added": 0, "skipped": 0}

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # קריאת שורות קיימות
    existing_keys: set[tuple] = set()
    existing_rows: list[dict] = []
    fieldnames: list[str] = []

    if COMBINED_CSV.exists():
        try:
            with open(COMBINED_CSV, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = list(reader.fieldnames or [])
                existing_rows = list(reader)
            for r in existing_rows:
                key = _make_key(r)
                if key:
                    existing_keys.add(key)
        except Exception as e:
            log(f"  אזהרה — לא הצלחתי לקרוא קובץ מאוחד קיים: {e}")

    if not fieldnames and rows:
        fieldnames = list(rows[0].keys())

    # סינון: רק שורות חדשות
    to_add = []
    skipped = 0
    for row in rows:
        key = _make_key(row)
        if key and key in existing_keys:
            skipped += 1
        else:
            to_add.append(row)
            if key:
                existing_keys.add(key)

    # כתיבה
    if to_add:
        write_header = not COMBINED_CSV.exists() or len(existing_rows) == 0
        with open(COMBINED_CSV, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            writer.writerows(to_add)

    log(f"  קובץ מאוחד: נוספו {len(to_add)}, דולגו {skipped} כפולות | {COMBINED_CSV}")
    return {"added": len(to_add), "skipped": skipped}


# ── פונקציה ראשית ────────────────────────────────────────────

async def fetch_case(case_number: str, is_traffic: bool = False,
                     court_name: str = "") -> dict:
    """
    שולף מטאדאטא עבור מספר תיק ומחבר לקובץ המאוחד.

    מחזיר:
    {
        "rows":        [dict, ...],  # כל השורות שנמצאו
        "added":       int,          # שורות שנוספו לקובץ המאוחד
        "skipped":     int,          # שורות שדולגו (כפולות)
        "total_found": int,
        "error":       str | None,
    }
    """
    result = {"rows": [], "added": 0, "skipped": 0, "total_found": 0, "error": None}

    import random
    ua = random.choice(USER_AGENTS)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=ua,
            viewport={"width": 1280, "height": 900},
            accept_downloads=True,
        )
        page = await context.new_page()

        try:
            await navigate_to_case_search(page)
            await fill_case_search(page, case_number, is_traffic=is_traffic,
                                   court_name=court_name)

            # בדיקה שיש תוצאות
            row_count = await page.locator(".ag-row").count()
            if row_count == 0:
                log("  לא נמצאו תוצאות")
                result["error"] = "לא נמצאו תוצאות"
                return result

            # בדיקת גבול 100 תוצאות
            body_text = await page.locator("body").inner_text()
            m = re.search(r'(\d+)\s*(עד|מתוך)\s*(\d+)', body_text)
            if m:
                total = int(m.group(3))
                if total > 100:
                    msg = f"נמצאו {total} תוצאות — יותר מ-100, לא ניתן לעבד"
                    log(f"  שגיאה: {msg}")
                    result["error"] = msg
                    return result

            # ייצוא CSV
            rows = await export_results_csv(page)
            result["rows"]        = rows
            result["total_found"] = len(rows)

            if not rows:
                result["error"] = "ייצוא CSV נכשל או החזיר תוצאות ריקות"
                return result

            # איחוד לקובץ מרכזי
            combined = append_to_combined(rows)
            result["added"]   = combined["added"]
            result["skipped"] = combined["skipped"]

        except Exception as e:
            log(f"  שגיאה כללית: {e}")
            result["error"] = str(e)

        finally:
            await browser.close()

    return result


# ── הרצה ישירה לבדיקה ────────────────────────────────────────

async def main():
    # === לבדיקה: שנה כאן את מספר התיק ===
    case_number = "4084/17"
    is_traffic  = False
    court_name  = "העליון"   # נדרש רק לתיק ישן
    # =====================================

    log(f"מתחיל שליפה: {case_number}")
    result = await fetch_case(case_number, is_traffic=is_traffic,
                              court_name=court_name)

    print("\n" + "="*50)
    print(f"סה״כ נמצאו:  {result['total_found']} שורות")
    print(f"נוספו:       {result['added']} לקובץ המאוחד")
    print(f"דולגו:       {result['skipped']} כפולות")
    if result["error"]:
        print(f"שגיאה:       {result['error']}")
    print(f"קובץ מאוחד:  {COMBINED_CSV}")
    print("="*50)


if __name__ == "__main__":
    asyncio.run(main())
