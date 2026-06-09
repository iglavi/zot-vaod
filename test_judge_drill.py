"""
test_judge_drill.py — חוקר את ה-AJAX של שופטים/הליכים לפני ואחרי חיפוש.

מטרה: להבין מתי בדיוק הדרופדאונים מתאכלסים, ולאתר שופט+יום עם 100+
כדי לבחון את פיצול ההליכים.

ריצה:
    python test_judge_drill.py
"""

import asyncio
import re
from datetime import date
from playwright.async_api import async_playwright

SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"
HEADLESS   = False          # פתוח כדי לראות מה קורה

# ───── פרמטרי הבדיקה ─────────────────────────────────────
# ערכאה 88 = שלום ת"א  (ידוע שמחזיר 100 ב-2011-01-03 גזר דין)
COURT_IDX  = 88
DT_NAME    = "גזר דין"
TEST_DATE  = date(2011, 1, 3)
# ─────────────────────────────────────────────────────────

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

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        ctx     = await browser.new_context()
        page    = await ctx.new_page()

        print("=== שלב 1: ניווט לדף החיפוש ===")
        await goto_search(page)

        # ── שלב 2: בחירת ערכאה בלבד (ללא לחיצת איתור) ──
        print(f"\n=== שלב 2: בחירת ערכאה {COURT_IDX} (ללא איתור) ===")
        await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=COURT_IDX)

        for wait_ms in [500, 1000, 2000, 3000]:
            await page.wait_for_timeout(500)
            judges = await read_options(page, "#LocateByParameters1_ddlJudgeName")
            procs  = await read_options(page, "#LocateByParameters1_ddlSelectProceeding")
            elapsed = wait_ms
            p(f"אחרי {elapsed}ms — שופטים: {len(judges)}, הליכים: {len(procs)}")

        judges = await read_options(page, "#LocateByParameters1_ddlJudgeName")
        p(f"סה\"כ שופטים: {len(judges)}")
        if judges:
            p(f"  דוגמה (5 ראשונים): {judges[:5]}")

        procs = await read_options(page, "#LocateByParameters1_ddlSelectProceeding")
        p(f"סה\"כ הליכים: {len(procs)}")
        if procs:
            p(f"  דוגמה: {procs[:5]}")

        # ── שלב 3: חיפוש מלא (לחיצת איתור) ──
        print(f"\n=== שלב 3: חיפוש מלא (ערכאה {COURT_IDX}, {DT_NAME}, {TEST_DATE}) ===")
        await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label=DT_NAME)
        await page.wait_for_timeout(300)
        await set_date(page, "LocateByParameters1_dateFrom", TEST_DATE)
        await set_date(page, "LocateByParameters1_DateTo",   TEST_DATE)
        await page.locator("#ButtonsGroup1_btnLocate").click()
        try:
            await page.locator(".ag-row").first.wait_for(timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(1000)

        judges_after = await read_options(page, "#LocateByParameters1_ddlJudgeName")
        procs_after  = await read_options(page, "#LocateByParameters1_ddlSelectProceeding")
        p(f"אחרי איתור — שופטים: {len(judges_after)}, הליכים: {len(procs_after)}")

        # בדוק ספירת שורות
        rows = await page.locator(".ag-row").count()
        p(f"שורות ag-row: {rows}")

        # ── שלב 4: ניווט מחדש ובחירת ערכאה + שופט ──
        print(f"\n=== שלב 4: בחירת ערכאה + שופט index=1 (ללא איתור) ===")
        await goto_search(page)
        await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=COURT_IDX)
        await page.wait_for_timeout(2000)

        judges2 = await read_options(page, "#LocateByParameters1_ddlJudgeName")
        p(f"שופטים אחרי בחירת ערכאה: {len(judges2)}")

        if len(judges2) > 1:
            # בחר שופט index=1
            await page.locator("#LocateByParameters1_ddlJudgeName").select_option(index=1)
            await page.wait_for_timeout(2000)
            procs2 = await read_options(page, "#LocateByParameters1_ddlSelectProceeding")
            judge_name = judges2[1][1] if len(judges2) > 1 else "?"
            p(f"אחרי בחירת שופט '{judge_name}' — הליכים: {len(procs2)}")
            if procs2:
                p(f"  הליכים: {procs2[:10]}")

            # בחר שופט index=2 ובדוק שוב
            if len(judges2) > 2:
                await page.locator("#LocateByParameters1_ddlJudgeName").select_option(index=2)
                await page.wait_for_timeout(2000)
                procs3 = await read_options(page, "#LocateByParameters1_ddlSelectProceeding")
                judge_name2 = judges2[2][1]
                p(f"אחרי בחירת שופט '{judge_name2}' — הליכים: {len(procs3)}")

        # ── שלב 5: חיפוש עם שופט ובדיקת הליכים אחרי ──
        print(f"\n=== שלב 5: חיפוש עם שופט index=1 ובדיקת הליכים ===")
        await goto_search(page)
        await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=COURT_IDX)
        await page.wait_for_timeout(2000)
        await page.locator("#LocateByParameters1_ddlJudgeName").select_option(index=1)
        await page.wait_for_timeout(500)
        await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label=DT_NAME)
        await page.wait_for_timeout(300)
        await set_date(page, "LocateByParameters1_dateFrom", TEST_DATE)
        await set_date(page, "LocateByParameters1_DateTo",   TEST_DATE)

        procs_before_search = await read_options(page, "#LocateByParameters1_ddlSelectProceeding")
        p(f"הליכים לפני לחיצת איתור: {len(procs_before_search)}")

        await page.locator("#ButtonsGroup1_btnLocate").click()
        try:
            await page.locator(".ag-row").first.wait_for(timeout=15000)
        except Exception:
            pass
        await page.wait_for_timeout(1000)

        procs_after_search = await read_options(page, "#LocateByParameters1_ddlSelectProceeding")
        rows5 = await page.locator(".ag-row").count()
        p(f"הליכים אחרי לחיצת איתור: {len(procs_after_search)}")
        p(f"שורות תוצאה: {rows5}")
        if procs_after_search:
            p(f"  הליכים: {procs_after_search[:10]}")

        # ── שלב 6: הלוגיקה המתוקנת ──────────────────────────
        # זורם כמו scrape_range האמיתי:
        #   לכל שופט → חפש → אם <100 הורד, אם 100+ פצל לפי הליך
        print(f"\n=== שלב 6: לוגיקה מתוקנת — שופט קודם, הליך רק אם 100+ ===")

        # קרא proc_count פעם אחת לפני כל החיפושים (סטטי לערכאה)
        await goto_search(page)
        await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=COURT_IDX)
        await page.wait_for_timeout(1200)
        proc_opts  = await read_options(page, "#LocateByParameters1_ddlSelectProceeding")
        judge_opts = await read_options(page, "#LocateByParameters1_ddlJudgeName")
        p(f"הליכים זמינים (לפני כל חיפוש): {len(proc_opts)} → {[x[1] for x in proc_opts]}")
        p(f"שופטים: {len(judge_opts)}")

        async def get_count(page):
            try:
                body = await page.locator("body").inner_text()
                m = re.search(r'מתוך\s+(\d+)', body)
                if m:
                    return int(m.group(1))
            except Exception:
                pass
            return await page.locator(".ag-row").count()

        async def search_and_count(page, judge_idx, proc_val=None):
            await goto_search(page)
            await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=COURT_IDX)
            await page.wait_for_timeout(900)
            await page.locator("#LocateByParameters1_ddlJudgeName").select_option(index=judge_idx)
            await page.wait_for_timeout(300)
            await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label=DT_NAME)
            await page.wait_for_timeout(300)
            if proc_val is not None:
                await page.locator("#LocateByParameters1_ddlSelectProceeding").select_option(value=proc_val)
                await page.wait_for_timeout(300)
            await set_date(page, "LocateByParameters1_dateFrom", TEST_DATE)
            await set_date(page, "LocateByParameters1_DateTo",   TEST_DATE)
            await page.locator("#ButtonsGroup1_btnLocate").click()
            try:
                await page.locator(".ag-row").first.wait_for(timeout=10000)
            except Exception:
                pass
            await page.wait_for_timeout(500)
            return await get_count(page)

        # עבור על שופטים — בדוק כמה תוצאות, פצל לפי הליך רק אם 100+
        for jidx in range(1, len(judge_opts)):
            jname = judge_opts[jidx][1]
            count = await search_and_count(page, jidx)

            if count == 0:
                p(f"שופט {jidx} ({jname}): 0 — מדלג")
                continue
            elif count < 100:
                p(f"שופט {jidx} ({jname}): {count} — מוריד ישירות")
            else:
                p(f"שופט {jidx} ({jname}): {count} ← מוגבל! מפצל לפי הליך:")
                proc_total = 0
                for pidx in range(1, len(proc_opts)):
                    pval  = proc_opts[pidx][0]
                    pname = proc_opts[pidx][1]
                    pc = await search_and_count(page, jidx, proc_val=pval)
                    capped = " ← עדיין מוגבל!" if pc >= 100 else ""
                    p(f"    {pname}: {pc}{capped}")
                    proc_total += pc
                p(f"  סה\"כ לפי הליכים: {proc_total}")

        print("\n=== סיום — הדפדפן נשאר פתוח 30 שניות לבחינה ידנית ===")
        await page.wait_for_timeout(30000)
        await browser.close()

asyncio.run(main())
