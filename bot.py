"""
בוט בדיקה - רק השורה הראשונה
מדפיס כל שלב כדי שנוכל לאבחן בעיות
"""

import asyncio
import csv
import re
import requests
from pathlib import Path
from playwright.async_api import async_playwright

# ============================================================
# הגדרות
# ============================================================
OUTPUT_DIR = Path(r"C:\Users\MPI-User\Desktop\nethamishpat")
COURT_INDEX = 1   # בית משפט ראשון ברשימה
HEADLESS = False  # רואים את הדפדפן
# ============================================================


def safe_name(text, max_len=60):
    clean = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', str(text).strip())
    return clean[:max_len]


async def dismiss_popup(page, timeout=3000):
    try:
        btn = page.locator("button", has_text="אישור")
        await btn.wait_for(state="visible", timeout=timeout)
        await btn.click()
        await page.wait_for_timeout(800)
        print("  [OK] סגרתי פופאפ")
    except Exception:
        pass


async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        # --- שלב 1: ניווט ---
        print("\n[1] פותח את האתר...")
        await page.goto("https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx")
        await page.wait_for_timeout(4000)
        await dismiss_popup(page)

        await page.get_by_text("איתור החלטות").first.click()
        await page.wait_for_timeout(2000)
        await page.get_by_text("איתור לפי פרמטרים").first.click()
        await page.wait_for_timeout(1000)
        print("  [OK] הגעתי לדף החיפוש")

        # --- שלב 2: חיפוש ---
        print("\n[2] מחפש בית משפט...")
        dropdown = page.locator("#LocateByParameters1_ddlSelectCourt")
        await dropdown.select_option(index=COURT_INDEX)
        await page.wait_for_timeout(500)

        court_name = await page.locator(
            "#LocateByParameters1_ddlSelectCourt option:checked"
        ).inner_text()
        court_name = court_name.strip()
        print(f"  בית משפט שנבחר: {court_name}")

        await page.locator("#ButtonsGroup1_btnLocate").click()

        # ממתינים שהפופאפ "100 תוצאות" יופיע ואז סוגרים אותו
        # הפופאפ הזה מופיע אחרי שהשרת מחזיר תוצאות - לכן timeout ארוך יותר
        try:
            btn = page.locator("button", has_text="אישור")
            await btn.wait_for(state="visible", timeout=10000)
            await btn.click()
            await page.wait_for_timeout(1000)
            print("  [OK] סגרתי פופאפ 100 תוצאות")
        except Exception:
            print("  לא הופיע פופאפ (פחות מ-100 תוצאות, או שנסגר כבר)")

        await page.wait_for_timeout(1000)
        print("  [OK] עמוד תוצאות נטען")

        # --- שלב 3: חילוץ השורה הראשונה בלבד ---
        print("\n[3] מחפש את הטבלה...")

        # הגישה הנכונה: מוצאים קישור NGCSViewer ועולים ממנו לטבלה שמכילה אותו
        ngcs_count = await page.locator("a[href*='NGCSViewer']").count()
        print(f"  קישורי NGCSViewer בדף: {ngcs_count}")

        if ngcs_count == 0:
            print("  אין קישורי NGCSViewer בדף - ייתכן שאין תוצאות, או שהדף לא נטען")
            await browser.close()
            return

        # עולים בעץ ה-HTML מהקישור הראשון עד לטבלה שמכילה אותו
        table = page.locator("a[href*='NGCSViewer']").first.locator("xpath=ancestor::table[1]")
        print("  [OK] נמצאה טבלת תוצאות (דרך קישורי NGCSViewer)")

        # סופרים שורות
        rows = table.locator("tr")
        total_rows = await rows.count()
        print(f"  סה\"כ שורות בטבלה: {total_rows}")

        if total_rows < 2:
            print("  אין מספיק שורות - אולי הטבלה לא נטענה?")
            await browser.close()
            return

        # --- לוקחים רק שורה 1 (index 1 = אחרי הכותרת) ---
        print("\n[4] חולץ שורה ראשונה...")
        first_row = rows.nth(1)
        cells = first_row.locator("td")
        num_cells = await cells.count()
        print(f"  מספר תאים בשורה: {num_cells}")

        # מדפיסים את כל התאים כדי לדעת מה בכל עמודה
        print("  תוכן כל תא:")
        for i in range(num_cells):
            cell_text = (await cells.nth(i).inner_text()).strip()
            print(f"    תא {i}: '{cell_text}'")

        # חילוץ לפי מה שיודעים
        if num_cells >= 7:
            date         = (await cells.nth(0).inner_text()).strip()
            court        = (await cells.nth(1).inner_text()).strip()
            proc_type    = (await cells.nth(2).inner_text()).strip()
            case_type    = (await cells.nth(3).inner_text()).strip()
            case_number  = (await cells.nth(4).inner_text()).strip()
            case_name    = (await cells.nth(5).inner_text()).strip()
            decision     = (await cells.nth(6).inner_text()).strip()
        else:
            print(f"  שגיאה: פחות מ-7 תאים! יש רק {num_cells}")
            await browser.close()
            return

        print(f"\n  תאריך:     {date}")
        print(f"  ערכאה:     {court}")
        print(f"  סוג הליך:  {proc_type}")
        print(f"  סוג תיק:   {case_type}")
        print(f"  מספר תיק:  {case_number}")
        print(f"  שם תיק:    {case_name}")
        print(f"  סוג החלטה: {decision}")

        # חיפוש קישור PDF
        pdf_el = first_row.locator("a[href*='NGCSViewer']")
        pdf_count = await pdf_el.count()
        print(f"\n  קישורי NGCSViewer בשורה: {pdf_count}")

        pdf_href = None
        if pdf_count > 0:
            pdf_href = await pdf_el.first.get_attribute("href")
            print(f"  href: {pdf_href}")
        else:
            print("  אין קישור PDF בשורה זו")

        # --- שלב 5: הורדת ה-PDF ---
        pdf_saved = "אין קישור"

        if pdf_href:
            print("\n[5] מנסה להוריד PDF...")

            # בניית URL מלא
            if pdf_href.startswith("/"):
                pdf_url = "https://www.court.gov.il" + pdf_href
            elif not pdf_href.startswith("http"):
                pdf_url = "https://www.court.gov.il/NGCS.Web.Site/" + pdf_href
            else:
                pdf_url = pdf_href
            print(f"  URL מלא: {pdf_url}")

            try:
                cookies = await context.cookies()
                session = requests.Session()
                for c in cookies:
                    session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))

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
                first_bytes = resp.content[:8]
                print(f"  HTTP status: {resp.status_code}")
                print(f"  content-type: {content_type}")
                print(f"  4 bytes ראשונים: {first_bytes}")

                court_dir = OUTPUT_DIR / safe_name(court_name)
                court_dir.mkdir(parents=True, exist_ok=True)
                fname = f"{safe_name(date)}_{safe_name(case_number)}.pdf"
                pdf_path = court_dir / fname

                if b"%PDF" in first_bytes or "pdf" in content_type:
                    with open(pdf_path, "wb") as f:
                        f.write(resp.content)
                    pdf_saved = str(pdf_path)
                    print(f"  [OK] PDF נשמר: {pdf_path}")
                else:
                    print("  התשובה לא נראית כמו PDF")
                    print("  מנסה לפתוח דף viewer...")

                    # פתיחת viewer בדפדפן ובדיקה
                    viewer_page = await context.new_page()
                    await viewer_page.goto(pdf_url)
                    await viewer_page.wait_for_timeout(3000)
                    viewer_url = viewer_page.url
                    print(f"  URL אחרי redirect: {viewer_url}")

                    # מחפשים embed/iframe של PDF
                    embed = viewer_page.locator("embed, iframe, object")
                    embed_count = await embed.count()
                    print(f"  embed/iframe/object: {embed_count}")
                    for i in range(embed_count):
                        src = await embed.nth(i).get_attribute("src") or ""
                        typ = await embed.nth(i).get_attribute("type") or ""
                        print(f"    [{i}] src={src[:80]}  type={typ}")

                    await viewer_page.close()
                    pdf_saved = "שגיאה - ראה פלט"

            except Exception as e:
                print(f"  שגיאה: {e}")
                pdf_saved = f"שגיאה: {e}"

        # --- שלב 6: שמירת CSV (שורה אחת) ---
        print("\n[6] שומר CSV...")
        court_dir = OUTPUT_DIR / safe_name(court_name)
        court_dir.mkdir(parents=True, exist_ok=True)
        csv_path = court_dir / "metadata.csv"

        row_data = {
            "תאריך": date,
            "ערכאה": court,
            "סוג הליך": proc_type,
            "סוג תיק": case_type,
            "מספר תיק": case_number,
            "שם תיק": case_name,
            "סוג החלטה": decision,
            "pdf_saved": pdf_saved,
        }

        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(row_data.keys()))
            writer.writeheader()
            writer.writerow(row_data)

        print(f"  [OK] נשמר: {csv_path}")

        print("\n=== סיום ===")
        await browser.close()


asyncio.run(main())
