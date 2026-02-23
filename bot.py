"""
בוט בדיקה - רק השורה הראשונה
מדפיס כל שלב כדי שנוכל לאבחן בעיות
"""

import asyncio
import csv
import re
import sys
import requests
from pathlib import Path
from playwright.async_api import async_playwright

# === תיעוד לקובץ ===
_LOG_PATH = Path(r"C:\Users\MPI-User\Desktop\nethamishpat\log.txt")
_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_log = open(_LOG_PATH, "w", encoding="utf-8")

class _Tee:
    def write(self, m): sys.__stdout__.write(m); _log.write(m); _log.flush()
    def flush(self): sys.__stdout__.flush()

sys.stdout = _Tee()
# ===================

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
        await page.wait_for_timeout(3000)  # ממתינים שהדף ייטען

        # סגירת פופאפ "100 תוצאות" - ניסיון עם מספר שיטות
        # (הפופאפ בעמוד התוצאות עשוי להיות בנוי שונה מהפופאפ בדף הבית)
        dismissed = False

        # שיטה 1: button עם טקסט אישור (כמו בדף הבית)
        if not dismissed:
            try:
                btn = page.locator("button", has_text="אישור")
                if await btn.count() > 0:
                    await btn.first.click()
                    dismissed = True
                    print("  [OK] סגרתי פופאפ (button)")
            except Exception:
                pass

        # שיטה 2: input עם value=אישור (סוג אחר של כפתור ב-ASP.NET)
        if not dismissed:
            try:
                btn = page.locator("input[value='אישור']")
                if await btn.count() > 0:
                    await btn.first.click()
                    dismissed = True
                    print("  [OK] סגרתי פופאפ (input[value])")
            except Exception:
                pass

        # שיטה 3: JavaScript - מחפש כל כפתור עם טקסט/value אישור ולוחץ עליו
        if not dismissed:
            try:
                result = await page.evaluate("""
                    () => {
                        const all = [...document.querySelectorAll('button, input[type=button], input[type=submit]')];
                        const found = all.find(el =>
                            (el.textContent || '').includes('אישור') ||
                            (el.value || '').includes('אישור')
                        );
                        if (found) { found.click(); return true; }
                        return false;
                    }
                """)
                if result:
                    dismissed = True
                    print("  [OK] סגרתי פופאפ (JavaScript)")
            except Exception:
                pass

        if not dismissed:
            print("  לא נמצא פופאפ לסגירה (אולי אין כזה)")

        await page.wait_for_timeout(1000)
        print("  [OK] עמוד תוצאות נטען")

        # --- שלב 3: חילוץ השורה הראשונה בלבד ---
        print("\n[3] מחפש את הטבלה...")

        # הקישורים הם PostBack מסוג btnDocument
        doc_links = page.locator("a[href*='btnDocument']")
        doc_count = await doc_links.count()
        print(f"  קישורי btnDocument בדף: {doc_count}")

        if doc_count == 0:
            print("  אין קישורי מסמכים בדף")
            body_text = await page.locator("body").inner_text()
            keywords = ["לא נמצאו", "אין תוצאות", "0 תוצאות", "No results"]
            for kw in keywords:
                if kw in body_text:
                    print(f"  נמצא בדף: '{kw}'")
            screenshot_path = OUTPUT_DIR / "debug_screenshot.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"  צילום מסך נשמר: {screenshot_path}")
            await browser.close()
            return

        # עולים בעץ ה-HTML - הקישור בטבלה פנימית, מנסים table[2] ואחר-כך table[1]
        table = None
        for level in (2, 3, 1):
            candidate = doc_links.first.locator(f"xpath=ancestor::table[{level}]")
            try:
                count = await candidate.locator("tr").count()
            except Exception:
                count = 0
            print(f"  ancestor::table[{level}] → {count} שורות")
            if count > 1:
                table = candidate
                print(f"  [OK] נמצאה טבלת תוצאות (ancestor::table[{level}])")
                break

        if table is None:
            print("  לא מצאתי טבלה עם יותר משורה אחת - מוותר")
            await browser.close()
            return

        # שורות שמכילות ישירות קישורי btnDocument (שורות נתונים, לא כותרת)
        data_rows = table.locator("tr:has(a[href*='btnDocument'])")
        total_data_rows = await data_rows.count()
        print(f"  שורות נתונים: {total_data_rows}")

        if total_data_rows == 0:
            print("  אין שורות נתונים - מוותר")
            await browser.close()
            return

        # --- לוקחים שורת נתונים ראשונה ---
        print("\n[4] חולץ שורה ראשונה...")
        first_row = data_rows.first
        # child::td בלבד (לא td מתוך טבלאות מקוננות)
        cells = first_row.locator("xpath=child::td")
        num_cells = await cells.count()
        print(f"  מספר תאים ישירים בשורה: {num_cells}")

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

        # חיפוש קישור המסמך בשורה הראשונה
        pdf_el = first_row.locator("a[href*='btnDocument']")
        pdf_count = await pdf_el.count()
        print(f"\n  קישורי btnDocument בשורה: {pdf_count}")

        pb_href = None
        if pdf_count > 0:
            pb_href = await pdf_el.first.get_attribute("href")
            print(f"  href: {pb_href}")
        else:
            print("  אין קישור מסמך בשורה זו")

        # --- שלב 5: הורדת ה-PDF דרך PostBack ---
        pdf_saved = "אין קישור"

        if pb_href:
            print("\n[5] לוחץ על קישור המסמך ומחכה לחלון...")

            # חילוץ הארגומנט: __doPostBack("btnDocument","caseId&docId&1")
            pb_match = re.search(r'__doPostBack\("btnDocument","([^"]+)"\)', pb_href)
            if pb_match:
                pb_arg = pb_match.group(1)
                parts = pb_arg.split("&")
                case_id = parts[0] if len(parts) > 0 else ""
                doc_id  = parts[1] if len(parts) > 1 else ""
                print(f"  case_id={case_id}  doc_id={doc_id}")
            else:
                case_id = doc_id = ""
                print("  לא הצלחתי לחלץ case_id/doc_id")

            try:
                # לחיצה על הקישור - מצפה לחלון חדש (popup)
                async with context.expect_page() as popup_info:
                    await pdf_el.first.click()
                popup = await popup_info.value
                await popup.wait_for_load_state("domcontentloaded")
                viewer_url = popup.url
                print(f"  URL שנפתח: {viewer_url}")

                # הורדת ה-PDF מה-URL שנפתח
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

                resp = session.get(viewer_url, headers=headers, stream=True, timeout=30)
                content_type = resp.headers.get("content-type", "").lower()
                first_bytes = resp.content[:8]
                print(f"  HTTP status: {resp.status_code}")
                print(f"  content-type: {content_type}")
                print(f"  8 bytes ראשונים: {first_bytes}")

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
                    embed = popup.locator("embed, iframe, object")
                    embed_count = await embed.count()
                    print(f"  embed/iframe/object בחלון: {embed_count}")
                    for i in range(embed_count):
                        src = await embed.nth(i).get_attribute("src") or ""
                        typ = await embed.nth(i).get_attribute("type") or ""
                        print(f"    [{i}] src={src[:100]}  type={typ}")
                    pdf_saved = "שגיאה - ראה פלט"

                await popup.close()

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
_log.close()
