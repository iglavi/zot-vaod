"""
POC — שליפת URL של viewer על ידי לחיצה על אייקון המסמך בדף התוצאות
המטרה: לקבל את ה-DocumentNumber ולשמור את ה-URL במקום להוריד קובץ
"""

import asyncio
from playwright.async_api import async_playwright

SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"

async def get_viewer_url_for_row(row_index: int = 0):
    """
    נכנס לאתר, מחפש, ולוחץ על אייקון המסמך של השורה הראשונה.
    מקליט את ה-URL של הטאב החדש שנפתח.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # ── כניסה לאתר ──
        print("נכנס לאתר...")
        await page.goto(SITE_URL, timeout=45000)
        await page.wait_for_timeout(3000)
        
        # סגירת פופאפ פתיחה אם קיים
        for selector in ["a.modal_ReturnMessageClose", "a#returnFocus", "input[value='אישור']", "a:has-text('אישור')", "button:has-text('אישור')"]:
            try:
                el = page.locator(selector)
                if await el.count() > 0 and await el.first.is_visible():
                    await el.first.click(force=True)
                    await page.wait_for_timeout(1000)
                    break
            except Exception:
                pass
        
        await page.get_by_text("איתור החלטות").first.click(timeout=20000)
        await page.wait_for_timeout(1500)
        await page.get_by_text("איתור לפי פרמטרים").first.click(timeout=20000)
        await page.wait_for_timeout(1500)

        # ── הגדרת חיפוש (ערכאה 3 = חיפה, פסק דין) ──
        print("מגדיר חיפוש...")
        # אזורי לעבודה ב"ש בשבתו באילת
        await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(label='אזורי לעבודה ב"ש בשבתו באילת')
        await page.wait_for_timeout(1000)
        # פסק דין
        await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label="פסק דין")
        await page.wait_for_timeout(500)

        # תאריך: 01/01/2026
        await page.locator("#LocateByParameters1_dateFrom").fill("01/02/2026")
        await page.locator("#LocateByParameters1_DateTo").fill("01/02/2026")
        await page.wait_for_timeout(500)

        # ── חיפוש ──
        print("מחפש...")
        await page.locator("#ButtonsGroup1_btnLocate").click()
        await page.wait_for_load_state("networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # ── מציאת אייקון המסמך בשורה הראשונה ──
        print("מחפש אייקון מסמך בשורה הראשונה...")
        
        # האייקון הוא img עם src של Doc.gif בתוך תא של ag-grid
        doc_icons = page.locator("img[src*='Doc.gif']")
        count = await doc_icons.count()
        print(f"נמצאו {count} אייקוני מסמך")
        
        if count == 0:
            print("לא נמצאו אייקונים")
            await browser.close()
            return

        # ── לחיצה על האייקון ותפיסת הטאב החדש ──
        print(f"לוחץ על אייקון שורה {row_index}...")
        
        async with context.expect_page() as new_page_info:
            await doc_icons.nth(row_index).click()
        
        new_page = await new_page_info.value
        await new_page.wait_for_load_state("domcontentloaded", timeout=15000)
        await new_page.wait_for_timeout(1000)
        
        viewer_url = new_page.url
        print(f"\n[OK] URL של viewer:")
        print(f"  {viewer_url}")
        
        # חילוץ DocumentNumber
        if "DocumentNumber=" in viewer_url:
            doc_num = viewer_url.split("DocumentNumber=")[1]
            print(f"\n  DocumentNumber: {doc_num}")
            constructed = f"https://www.court.gov.il/NGCS.Web.Site/Viewer/NGCSViewerPage.aspx?DocumentNumber={doc_num}"
            print(f"  URL מבונה: {constructed}")
            print(f"  זהה? {viewer_url == constructed}")
        
        await new_page.close()
        await browser.close()


asyncio.run(get_viewer_url_for_row(0))
