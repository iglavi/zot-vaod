"""
test_judge_drill.py — בודק פיצול לפי שופטים

הלוגיקה:
  1. חיפוש יום+סוג מסמך (כל הערכאות) — ודא 100+
  2. מצא ערכאה שנותנת 100+ לבד
  3. פצל אותה לפי שופטים

ריצה:
    python test_judge_drill.py
"""

import asyncio
import re
from datetime import date
from playwright.async_api import async_playwright

SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"
HEADLESS    = False
DT_NAME     = "גזר דין"
TEST_DATE   = date(2011, 1, 3)
COURT_IDX   = 71   # ערכאה ידועה עם 100+ ביום זה

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
    try:
        body = await page.locator("body").inner_text()
        m = re.search(r'מתוך\s+(\d+)', body)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return await page.locator(".ag-row").count()

async def search(page, court_idx, dt_name, d, judge_idx=None):
    """חיפוש מלא. מחזיר (count, judge_options_read_before_postback)."""
    await goto_search(page)
    await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
    await page.wait_for_timeout(1200)
    # קרא שופטים לפני PostBack (PostBack מאפס את הדרופדאון)
    judge_opts = await read_options(page, "#LocateByParameters1_ddlJudgeName")
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
    return await get_count(page), judge_opts

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        ctx     = await browser.new_context()
        page    = await ctx.new_page()

        # ── שלב 1: כל הערכאות ────────────────────────────────
        print(f"=== שלב 1: כל הערכאות ===")
        count_all, court_opts = await search(page, 0, DT_NAME, TEST_DATE)
        p(f"כל הערכאות: {count_all} {'← מוגבל!' if count_all >= 100 else ''}")
        p(f"סה\"כ ערכאות בדרופדאון: {len(court_opts)}")

        if count_all < 100:
            p("פחות מ-100 — אין צורך בפיצול")
            await browser.close()
            return

        # ── שלב 2: חיפוש ערכאה ספציפית ──────────────────────
        print(f"\n=== שלב 2: חיפוש ערכאה {COURT_IDX} ===")
        count_court, judge_opts = await search(page, COURT_IDX, DT_NAME, TEST_DATE)
        cname = court_opts[COURT_IDX][1] if COURT_IDX < len(court_opts) else f"#{COURT_IDX}"
        p(f"ערכאה {COURT_IDX} ({cname}): {count_court} {'← מוגבל!' if count_court >= 100 else ''}")
        p(f"שופטים (לפני PostBack): {len(judge_opts)-1}")

        if count_court < 100:
            p("פחות מ-100 — אין מה לפצל. שנה את COURT_IDX.")
            await browser.close()
            return

        if len(judge_opts) <= 1:
            p("אין שופטים בדרופדאון — בעיה בטעינת AJAX")
            await browser.close()
            return

        # ── שלב 3: פיצול לפי שופטים ─────────────────────────
        print(f"\n=== שלב 3: פיצול לפי שופטים ({len(judge_opts)-1} שופטים) ===")
        total = 0
        for jidx in range(1, len(judge_opts)):
            jname = judge_opts[jidx][1]
            c, _ = await search(page, COURT_IDX, DT_NAME, TEST_DATE, judge_idx=jidx)
            if c == 0:
                p(f"שופט {jidx:3d} ({jname}): 0")
                continue
            capped = " ← מוגבל!" if c >= 100 else ""
            p(f"שופט {jidx:3d} ({jname}): {c}{capped}")
            total += c

        p(f"\nסה\"כ: {total}")

        print("\n=== סיום — הדפדפן נשאר פתוח 30 שניות ===")
        await page.wait_for_timeout(30000)
        await browser.close()

asyncio.run(main())
