"""
test_judge_drill.py — בודק פיצול לפי שופטים

הלוגיקה שנבדקת:
  1. חיפוש יום+ערכאה+סוג מסמך
  2. אם 100+ — חפש לפי כל שופט בנפרד
  3. זהו. אין שלב שלישי.

ריצה:
    python test_judge_drill.py
"""

import asyncio
import re
from datetime import date
from playwright.async_api import async_playwright

SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"
HEADLESS = False

# ערכאה 88 = שלום ת"א (ידוע שמחזיר 100+ ב-2011-01-03 גזר דין)
COURT_IDX = 88
DT_NAME   = "גזר דין"
TEST_DATE = date(2011, 1, 3)

def p(msg): print(f"  {msg}")

async def set_date(page, fid, d):
    ds = d.strftime("%d/%m/%Y")
    await page.evaluate(f"""() => {{
        const el = document.getElementById('{fid}');
        if (el) {{
            el.removeAttribute('readonly');
            el.value = '{ds}';
            el.dispatchEvent(new Event('change', {{bubbles:true}}));
        }}
    }}""")
    await page.wait_for_timeout(150)

async def read_options(page, sel):
    opts = await page.locator(f"{sel} option").all()
    return [(await o.get_attribute("value"), (await o.inner_text()).strip()) for o in opts]

async def dismiss_popup(page):
    for locator in [
        page.locator("button", has_text="אישור"),
        page.locator("input[value='אישור']"),
    ]:
        try:
            if await locator.count() > 0 and await locator.first.is_visible():
                await locator.first.click()
                await page.wait_for_timeout(400)
                return
        except Exception:
            pass

async def goto_search(page):
    await page.goto(SITE_URL, timeout=45000)
    await page.wait_for_timeout(3000)
    await dismiss_popup(page)
    await page.get_by_text("איתור החלטות").first.click(timeout=20000)
    await page.wait_for_timeout(1500)
    await page.get_by_text("איתור לפי פרמטרים").first.click(timeout=20000)
    await page.wait_for_timeout(1000)

async def get_count(page):
    """קורא ספירה אמיתית מ-pagination, או ספירת שורות כ-fallback."""
    try:
        body = await page.locator("body").inner_text()
        m = re.search(r'מתוך\s+(\d+)', body)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return await page.locator(".ag-row").count()

async def search(page, court_idx, dt_name, d, judge_idx=None):
    """חיפוש + המתנה לתוצאות. מחזיר ספירה."""
    await goto_search(page)
    await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
    await page.wait_for_timeout(900)
    if judge_idx is not None:
        await page.locator("#LocateByParameters1_ddlJudgeName").select_option(index=judge_idx)
        await page.wait_for_timeout(300)
    await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label=dt_name)
    await page.wait_for_timeout(300)
    await set_date(page, "LocateByParameters1_dateFrom", d)
    await set_date(page, "LocateByParameters1_DateTo",   d)
    await page.locator("#ButtonsGroup1_btnLocate").click()
    try:
        await page.locator(".ag-row").first.wait_for(timeout=12000)
    except Exception:
        pass
    await page.wait_for_timeout(600)
    return await get_count(page)

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        ctx     = await browser.new_context()
        page    = await ctx.new_page()

        # ── שלב 1: חיפוש כל הערכאות ────────────────────────
        print(f"=== שלב 1: חיפוש כל הערכאות (index 0) ===")
        count_all = await search(page, 0, DT_NAME, TEST_DATE)
        p(f"כל הערכאות: {count_all} תוצאות {'← מוגבל!' if count_all >= 100 else ''}")

        # ── שלב 2: ודא שהשופטים נטענים לפני PostBack ────────
        print(f"\n=== שלב 2: שופטים לפני חיפוש (ערכאה {COURT_IDX}) ===")
        await goto_search(page)
        await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=COURT_IDX)
        await page.wait_for_timeout(1200)
        judge_opts = await read_options(page, "#LocateByParameters1_ddlJudgeName")
        p(f"שופטים לאחר 1200ms: {len(judge_opts)}")
        if len(judge_opts) > 1:
            p(f"  5 ראשונים: {[x[1] for x in judge_opts[1:6]]}")

        # ── שלב 3: חיפוש ערכאה בלי שופט ───────────────────
        print(f"\n=== שלב 3: חיפוש ערכאה {COURT_IDX} ללא שופט ===")
        count_court = await search(page, COURT_IDX, DT_NAME, TEST_DATE)
        p(f"ערכאה {COURT_IDX}: {count_court} תוצאות {'← מוגבל!' if count_court >= 100 else ''}")

        if count_court < 100:
            p("פחות מ-100, אין צורך בפיצול לפי שופטים. נסה ערכאה אחרת.")
            await browser.close()
            return

        # ── שלב 4: חיפוש לפי כל שופט בנפרד ─────────────────
        print(f"\n=== שלב 4: פיצול לפי שופטים ({len(judge_opts)-1} שופטים) ===")
        total = 0
        for jidx in range(1, len(judge_opts)):
            jname = judge_opts[jidx][1]
            c = await search(page, COURT_IDX, DT_NAME, TEST_DATE, judge_idx=jidx)
            if c == 0:
                p(f"שופט {jidx:3d} ({jname}): 0")
                continue
            capped = " ← מוגבל! (100 בלבד)" if c >= 100 else ""
            p(f"שופט {jidx:3d} ({jname}): {c}{capped}")
            total += c

        p(f"\nסה\"כ לפי שופטים: {total}")
        p(f"(ערכאה ללא פיצול: {count_court})")

        print("\n=== סיום — הדפדפן נשאר פתוח 30 שניות ===")
        await page.wait_for_timeout(30000)
        await browser.close()

asyncio.run(main())
