"""
בוט להורדת החלטות שיפוטיות מנט המשפט (court.gov.il)

שלבי הרצה:
    1. pip install -r requirements.txt
    2. playwright install chromium
    3. python bot.py
"""

import asyncio
import csv
import re
import requests
from pathlib import Path
from playwright.async_api import async_playwright


# ============================================================
# הגדרות - ניתן לשנות כאן
# ============================================================

# תיקיית שמירה על המחשב שלך
OUTPUT_DIR = Path(r"C:\Users\MPI-User\Desktop\nethamishpat")

# מספר בית המשפט ברשימה (1 = ראשון, 2 = שני, וכו')
# לאחר בדיקה מוצלחת ניתן להפעיל לולאה על כל 170 בתי המשפט
COURT_INDEX = 1

# False = רואים את הדפדפן (מומלץ לבדיקה)
# True  = הדפדפן רץ ברקע (מהיר יותר בהרצה מלאה)
HEADLESS = False

# ============================================================


def log(msg):
    """הדפסת הודעה למסך"""
    print(msg)


def safe_name(text, max_len=60):
    """הפיכת טקסט לשם קובץ תקין (ללא תווים אסורים)"""
    clean = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', str(text).strip())
    return clean[:max_len]


async def dismiss_popup(page, timeout=3000):
    """סגירת פופאפ 'אישור' אם קיים"""
    try:
        btn = page.locator("button", has_text="אישור")
        await btn.wait_for(state="visible", timeout=timeout)
        await btn.click()
        await page.wait_for_timeout(800)
    except Exception:
        pass  # אם אין פופאפ - ממשיכים


async def navigate_to_search(page):
    """שלב 1: פתיחת האתר וניווט לדף החיפוש"""
    log("פותח את האתר...")
    await page.goto("https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx")
    await page.wait_for_timeout(4000)

    await dismiss_popup(page)  # סגירת פופאפ תנאי שימוש

    await page.get_by_text("איתור החלטות").first.click()
    await page.wait_for_timeout(2000)

    await page.get_by_text("איתור לפי פרמטרים").first.click()
    await page.wait_for_timeout(1000)

    log("  הגעתי לדף החיפוש")


async def search_by_court(page, court_index):
    """שלב 2: בחירת בית משפט וחיפוש - מחזיר את שם בית המשפט"""
    dropdown = page.locator("#LocateByParameters1_ddlSelectCourt")
    await dropdown.select_option(index=court_index)
    await page.wait_for_timeout(500)

    # קריאת השם שנבחר
    court_name = await page.locator(
        "#LocateByParameters1_ddlSelectCourt option:checked"
    ).inner_text()
    court_name = court_name.strip()
    log(f"מחפש החלטות של: {court_name}")

    await page.locator("#ButtonsGroup1_btnLocate").click()
    await page.wait_for_timeout(4000)

    await dismiss_popup(page)  # סגירת פופאפ "100 תוצאות"

    return court_name


async def find_results_table(page):
    """מציאת טבלת התוצאות בדף - מנסה כמה selectors"""
    # ניסיון עם selectors נפוצים לטבלאות ASP.NET GridView
    for selector in [
        "table[id*='GridView']",
        "table[id*='grid']",
        "table[id*='Grid']",
        ".rgMasterTable",
    ]:
        el = page.locator(selector)
        if await el.count() > 0:
            log(f"  נמצאה טבלת תוצאות: {selector}")
            return el.first

    # fallback: הטבלה שיש בה הכי הרבה שורות
    log("  לא נמצאה טבלה ספציפית, משתמש בטבלה הראשית")
    return page.locator("table").first


async def extract_rows(page):
    """שלב 3: חילוץ מטאדטה וקישורי PDF מכל שורות העמוד הנוכחי"""
    results = []
    table = await find_results_table(page)
    rows = table.locator("tr")
    count = await rows.count()

    log(f"  סה\"כ שורות בטבלה (כולל כותרת): {count}")

    for i in range(1, count):  # מתחילים מ-1 כדי לדלג על שורת הכותרת
        row = rows.nth(i)
        cells = row.locator("td")
        num_cells = await cells.count()

        if num_cells < 6:
            continue  # שורה ריקה או שורת סיכום - מדלגים

        try:
            date         = (await cells.nth(0).inner_text()).strip()
            court        = (await cells.nth(1).inner_text()).strip()
            proc_type    = (await cells.nth(2).inner_text()).strip()
            case_type    = (await cells.nth(3).inner_text()).strip()
            case_number  = (await cells.nth(4).inner_text()).strip()
            case_name    = (await cells.nth(5).inner_text()).strip()
            decision     = (await cells.nth(6).inner_text()).strip() if num_cells > 6 else ""

            # חיפוש קישור PDF בשורה זו
            pdf_el = row.locator("a[href*='NGCSViewer']")
            pdf_href = None
            if await pdf_el.count() > 0:
                pdf_href = await pdf_el.first.get_attribute("href")

            if date and case_number:  # שורה תקינה עם נתונים
                results.append({
                    "תאריך":       date,
                    "ערכאה":       court,
                    "סוג הליך":    proc_type,
                    "סוג תיק":     case_type,
                    "מספר תיק":    case_number,
                    "שם תיק":      case_name,
                    "סוג החלטה":   decision,
                    "pdf_url":     pdf_href,
                    "pdf_saved":   "",
                })
        except Exception as e:
            log(f"  שגיאה בחילוץ שורה {i}: {e}")

    return results


async def download_pdf(context, pdf_href, save_path):
    """
    שלב 4: הורדת PDF ושמירה לקובץ.
    משתמש ב-cookies מהדפדפן כדי לגשת לקבצים מוגנים.
    מחזיר True אם הצלחנו, False אם לא.
    """
    if not pdf_href:
        return False

    # בניית URL מלא
    if pdf_href.startswith("/"):
        pdf_url = "https://www.court.gov.il" + pdf_href
    elif not pdf_href.startswith("http"):
        pdf_url = "https://www.court.gov.il/NGCS.Web.Site/" + pdf_href
    else:
        pdf_url = pdf_href

    try:
        # שליפת cookies מהדפדפן - חשוב לגישה לקבצים
        cookies = await context.cookies()
        session = requests.Session()
        for c in cookies:
            session.cookies.set(
                c["name"], c["value"], domain=c.get("domain", "")
            )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.court.gov.il/",
        }

        resp = session.get(pdf_url, headers=headers, stream=True, timeout=30)
        content_type = resp.headers.get("content-type", "").lower()

        # מקרה 1: ה-URL מחזיר PDF ישירות
        if "pdf" in content_type or resp.content[:4] == b"%PDF":
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            return True

        # מקרה 2: ה-URL מחזיר HTML (viewer) - מחפשים את ה-PDF בפנים
        if "html" in content_type:
            html = resp.text
            # מחפשים URL של PDF בתוך דף ה-viewer
            pdf_match = re.search(
                r'["\']([^"\']*\.pdf[^"\']*)["\']', html, re.IGNORECASE
            )
            if pdf_match:
                inner_url = pdf_match.group(1)
                if not inner_url.startswith("http"):
                    inner_url = "https://www.court.gov.il" + inner_url
                resp2 = session.get(inner_url, headers=headers, stream=True, timeout=30)
                if resp2.content[:4] == b"%PDF":
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, "wb") as f:
                        for chunk in resp2.iter_content(8192):
                            f.write(chunk)
                    return True

        log(f"    content-type לא מזוהה: {content_type}")
        return False

    except Exception as e:
        log(f"    שגיאה בהורדה: {e}")
        return False


async def get_num_pages(page):
    """מציאת מספר עמודי התוצאות (עד 6)"""
    try:
        max_page = 1
        # חיפוש קישורים עם מספרי עמודים
        all_links = await page.locator("a").all()
        for link in all_links:
            text = (await link.inner_text()).strip()
            if text.isdigit() and 1 < int(text) <= 6:
                max_page = max(max_page, int(text))
        return max_page
    except Exception:
        return 1


async def go_to_page(page, page_num):
    """מעבר לעמוד ספציפי בתוצאות"""
    try:
        # כפתורי pagination ב-ASP.NET הם לרוב links עם המספר כטקסט
        link = page.locator(f"a", has_text=str(page_num))
        await link.first.click()
        await page.wait_for_timeout(3000)
        await dismiss_popup(page)
        return True
    except Exception as e:
        log(f"  שגיאה במעבר לעמוד {page_num}: {e}")
        return False


async def save_csv(rows, csv_path):
    """שמירת כל המטאדטה לקובץ CSV (ניתן לפתוח ב-Excel)"""
    if not rows:
        return

    # עמודות לשמירה (ללא עמודת url פנימית)
    fieldnames = ["תאריך", "ערכאה", "סוג הליך", "סוג תיק",
                  "מספר תיק", "שם תיק", "סוג החלטה", "pdf_saved"]

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        # utf-8-sig = UTF-8 עם BOM, כדי ש-Excel יציג עברית נכון
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    log(f"  נשמר קובץ Excel/CSV: {csv_path}")


async def main():
    # יצירת תיקיית הפלט אם לא קיימת
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # ניווט לדף החיפוש
        await navigate_to_search(page)

        # חיפוש בית משפט
        court_name = await search_by_court(page, COURT_INDEX)

        # תיקייה נפרדת לכל בית משפט
        court_dir = OUTPUT_DIR / safe_name(court_name)
        court_dir.mkdir(parents=True, exist_ok=True)
        log(f"תיקיית שמירה: {court_dir}")

        # מציאת מספר עמודים
        num_pages = await get_num_pages(page)
        log(f"נמצאו {num_pages} עמודי תוצאות")

        all_rows = []

        for p_num in range(1, num_pages + 1):
            log(f"\n=== עמוד {p_num}/{num_pages} ===")

            if p_num > 1:
                success = await go_to_page(page, p_num)
                if not success:
                    log("  לא ניתן לעבור לעמוד הבא, מפסיק")
                    break

            # חילוץ נתוני השורות
            rows = await extract_rows(page)
            log(f"  חולצו {len(rows)} החלטות")

            for idx, row in enumerate(rows, 1):
                # בניית שם קובץ: תאריך_מספר-תיק.pdf
                fname = f"{safe_name(row['תאריך'])}_{safe_name(row['מספר תיק'])}.pdf"
                pdf_path = court_dir / fname

                log(f"  [{idx}/{len(rows)}] {row['מספר תיק']} | {row['שם תיק'][:35]}")

                if pdf_path.exists():
                    # הקובץ כבר הורד בעבר - מדלגים
                    log("    קיים כבר, מדלג")
                    row["pdf_saved"] = str(pdf_path)

                elif row["pdf_url"]:
                    success = await download_pdf(context, row["pdf_url"], pdf_path)
                    if success:
                        row["pdf_saved"] = str(pdf_path)
                        log(f"    הורד: {fname}")
                    else:
                        row["pdf_saved"] = "שגיאה בהורדה"
                        log("    שגיאה בהורדה")
                else:
                    row["pdf_saved"] = "אין קישור"
                    log("    אין קישור PDF")

                all_rows.append(row)

        # שמירת קובץ CSV עם כל המטאדטה
        csv_path = court_dir / "metadata.csv"
        await save_csv(all_rows, csv_path)

        # סיכום
        downloaded = sum(
            1 for r in all_rows
            if r.get("pdf_saved", "").endswith(".pdf")
        )
        log(f"\n{'='*40}")
        log(f"סיום! הורדתי {downloaded}/{len(all_rows)} קבצים")
        log(f"תיקייה: {court_dir}")
        log(f"{'='*40}")

        await browser.close()


asyncio.run(main())
