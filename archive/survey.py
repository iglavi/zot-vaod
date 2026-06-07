"""
survey.py — סקר נפח החלטות לפי ערכאה וחודש
בודק כמה תוצאות יש לכל ערכאה × חודש × סוג החלטה (3 סוגים בלבד, ללא "החלטה")
מסכם לטבלת CSV: שורה = ערכאה, עמודה = חודש
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
OUTPUT_DIR  = Path(r"C:\Users\MPI-User\Desktop\nethamishpat")
OUTPUT_CSV  = OUTPUT_DIR / "survey_results.csv"
PROGRESS_F  = OUTPUT_DIR / "survey_progress.json"
LOG_FILE    = OUTPUT_DIR / "survey_log.txt"
DATA_FILE   = OUTPUT_DIR / "data.json"

SITE_URL       = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"
DECISION_TYPES = ["פסק דין", "גזר דין", "הכרעת דין"]
HEADLESS       = False

# 12 חודשים אחרונים: פברואר 2025 עד ינואר 2026
MONTHS = [
    ("2025", "2",  "2025-02"),
    ("2025", "3",  "2025-03"),
    ("2025", "4",  "2025-04"),
    ("2025", "5",  "2025-05"),
    ("2025", "6",  "2025-06"),
    ("2025", "7",  "2025-07"),
    ("2025", "8",  "2025-08"),
    ("2025", "9",  "2025-09"),
    ("2025", "10", "2025-10"),
    ("2025", "11", "2025-11"),
    ("2025", "12", "2025-12"),
    ("2026", "1",  "2026-01"),
]

# ── לוג ───────────────────────────────────────────────────
_log_fh = None

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _log_fh:
        _log_fh.write(line + "\n")
        _log_fh.flush()


# ── progress ──────────────────────────────────────────────

def load_progress() -> dict:
    """מחזיר dict: {court_idx: {month_label: count}}"""
    if PROGRESS_F.exists():
        return json.loads(PROGRESS_F.read_text(encoding="utf-8"))
    return {}


def save_progress(data: dict):
    PROGRESS_F.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── ניווט ─────────────────────────────────────────────────

async def dismiss_popup(page):
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


async def navigate_to_search(page):
    """
    מנווט לדף החיפוש לפי פרמטרים.
    אם האתר לא זמין — ממתין 3 דקות (x3), אחר כך 8 שעות, אחר כך 2 שעות (x2).
    """
    WAIT_SCHEDULE = [
        180,        # ניסיון 2: אחרי 3 דקות
        180,        # ניסיון 3: אחרי 3 דקות נוספות
        180,        # ניסיון 4: אחרי 3 דקות נוספות
        8 * 3600,   # ניסיון 5: אחרי 8 שעות
        2 * 3600,   # ניסיון 6: אחרי 2 שעות
        2 * 3600,   # ניסיון 7: אחרי 2 שעות נוספות
    ]

    for attempt in range(1, len(WAIT_SCHEDULE) + 2):
        try:
            await page.goto(SITE_URL, timeout=30000)
            await page.wait_for_timeout(random.uniform(2000, 3000))
            await dismiss_popup(page)
            await page.get_by_text("איתור החלטות").first.click(timeout=15000)
            await page.wait_for_timeout(random.uniform(800, 1500))
            await page.get_by_text("איתור לפי פרמטרים").first.click(timeout=15000)
            await page.wait_for_timeout(random.uniform(500, 1000))
            return
        except Exception as e:
            err = str(e)
            is_site_down = any(x in err for x in [
                "ERR_NETWORK_IO_SUSPENDED", "ERR_CONNECTION_REFUSED",
                "ERR_NAME_NOT_RESOLVED", "net::", "Timeout",
                "Target page", "context or browser has been closed",
            ])
            if not is_site_down or attempt > len(WAIT_SCHEDULE):
                raise
            wait_sec = WAIT_SCHEDULE[attempt - 1]
            wait_str = f"{wait_sec // 3600} שעות" if wait_sec >= 3600 else f"{wait_sec // 60} דקות"
            log(f"  [retry {attempt}/{len(WAIT_SCHEDULE)+1}] האתר לא זמין — ממתין {wait_str}...")
            await asyncio.sleep(wait_sec)
            try:
                await page.reload(timeout=45000)
            except Exception:
                pass


# ── תאריך ─────────────────────────────────────────────────

async def set_date_first_of_month(page, field_id: str, year: str, month: str):
    """בוחר את היום הראשון של החודש."""
    await page.locator(f"#{field_id}").click()
    await page.wait_for_timeout(800)
    dp = "#ui-datepicker-div"
    try:
        await page.locator(f"{dp} select.ui-datepicker-year").select_option(year)
        await page.wait_for_timeout(300)
    except Exception:
        pass
    month_0based = str(int(month) - 1)
    await page.locator(f"{dp} select.ui-datepicker-month").select_option(month_0based)
    await page.wait_for_timeout(300)
    await page.locator(f"{dp} a.ui-state-default", has_text="1").first.click()
    await page.wait_for_timeout(300)


async def set_date_last_of_month(page, field_id: str, year: str, month: str):
    """בוחר את היום האחרון של החודש."""
    import calendar
    last_day = str(calendar.monthrange(int(year), int(month))[1])
    await page.locator(f"#{field_id}").click()
    await page.wait_for_timeout(800)
    dp = "#ui-datepicker-div"
    try:
        await page.locator(f"{dp} select.ui-datepicker-year").select_option(year)
        await page.wait_for_timeout(300)
    except Exception:
        pass
    month_0based = str(int(month) - 1)
    await page.locator(f"{dp} select.ui-datepicker-month").select_option(month_0based)
    await page.wait_for_timeout(300)
    await page.locator(f"{dp} a.ui-state-default", has_text=last_day).first.click()
    await page.wait_for_timeout(300)


# ── חיפוש וספירה ─────────────────────────────────────────

async def count_via_csv(page) -> int:
    """
    סופר תוצאות אמיתיות על ידי ייצוא CSV וספירת שורות.
    """
    # בדיקה מהירה: האם יש בכלל תוצאות?
    try:
        row_count = await page.locator(".ag-row").count()
        log(f"      ag-rows גלויים: {row_count}")
        if row_count == 0:
            return 0
    except Exception as e:
        log(f"      שגיאת ag-row: {e}")
        return 0

    # ייצוא CSV וספירת שורות
    try:
        tmp = Path(tempfile.mktemp(suffix=".csv"))
        async with page.expect_download(timeout=15000) as dl_info:
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
            await page.wait_for_timeout(600)
            menu_count = await page.locator(".ag-menu-option").count()
            log(f"      תפריט: {menu_count} אפשרויות")
            await page.locator(".ag-menu-option").click()
            await page.wait_for_timeout(400)
            await page.get_by_text("ייצוא נתונים ל- CSV").click()
        dl = await dl_info.value
        await dl.save_as(str(tmp))
        with open(tmp, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        tmp.unlink(missing_ok=True)
        log(f"      CSV: {len(rows)} שורות")
        return len(rows)
    except Exception as e:
        log(f"      שגיאת CSV: {e}")

    return 0


async def search_and_count(page, court_idx: int, dt_name: str, year: str, month: str) -> int:
    """חיפוש לפי ערכאה + סוג החלטה + חודש מלא. מחזיר ספירה אמיתית."""
    await navigate_to_search(page)

    await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
    await page.wait_for_timeout(1000)
    await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label=dt_name)
    await page.wait_for_timeout(300)

    await set_date_first_of_month(page, "LocateByParameters1_dateFrom", year, month)
    await set_date_last_of_month(page, "LocateByParameters1_DateTo", year, month)

    # לחיצה על איתור — הדף עושה PostBack (לא navigation רגיל)
    # לוחצים ומחכים שה-AG-Grid יופיע (או timeout של 8 שניות)
    try:
        await page.locator("#ButtonsGroup1_btnLocate").click(timeout=15000, no_wait_after=True)
    except Exception:
        pass
    try:
        await page.locator(".ag-row").first.wait_for(timeout=8000)
    except Exception:
        pass  # אין תוצאות — count_via_csv יחזיר 0
    await page.wait_for_timeout(500)
    await dismiss_popup(page)
    await page.wait_for_timeout(300)

    return await count_via_csv(page)


# ── שמירת CSV ─────────────────────────────────────────────

def save_csv(court_names: list, results: dict):
    """
    results = {court_idx: {month_label: total_count}}
    שורה = ערכאה, עמודה = חודש + ממוצע + סה"כ
    """
    month_labels = [m[2] for m in MONTHS]
    fieldnames = ["ערכאה"] + month_labels + ["ממוצע", "סה\"כ"]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for court_idx, month_data in sorted(results.items(), key=lambda x: int(x[0])):
            court_name = court_names[int(court_idx)] if int(court_idx) < len(court_names) else f"ערכאה {court_idx}"
            row = {"ערכאה": court_name}
            total = 0
            count_months = 0
            for ml in month_labels:
                val = month_data.get(ml, "")
                row[ml] = val
                if isinstance(val, int):
                    total += val
                    count_months += 1
            row["סה\"כ"] = total
            row["ממוצע"] = round(total / count_months, 1) if count_months > 0 else ""
            writer.writerow(row)

    log(f"CSV נשמר: {OUTPUT_CSV}")


# ── main ──────────────────────────────────────────────────

async def main():
    global _log_fh
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _log_fh = open(LOG_FILE, "a", encoding="utf-8")
    log("=" * 60)
    log("מתחיל סקר נפח החלטות")

    # טעינת רשימת ערכאות
    court_names = None
    if DATA_FILE.exists():
        cached = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        court_names = cached.get("court_names")
        if court_names:
            log(f"ערכאות מהמטמון: {len(court_names) - 1}")

    results = load_progress()
    log(f"התקדמות קיימת: {len(results)} ערכאות")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        try:
            # טעינת ערכאות אם צריך
            if not court_names:
                await navigate_to_search(page)
                court_opts = await page.locator(
                    "#LocateByParameters1_ddlSelectCourt option"
                ).all()
                court_names = [(await opt.inner_text()).strip() for opt in court_opts]
                # שמירה ל-data.json
                existing = {}
                if DATA_FILE.exists():
                    existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                existing["court_names"] = court_names
                DATA_FILE.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                log(f"נשמרו {len(court_names) - 1} ערכאות")

            num_courts = len(court_names)
            total_searches = (num_courts - 1) * len(MONTHS) * len(DECISION_TYPES)
            log(f"סה\"כ חיפושים: {total_searches}  ({num_courts - 1} ערכאות × {len(MONTHS)} חודשים × {len(DECISION_TYPES)} סוגים)")

            search_num = 0

            for court_idx in range(1, num_courts):
                court_name = court_names[court_idx]
                court_key = str(court_idx)

                if court_key not in results:
                    results[court_key] = {}

                for year, month, month_label in MONTHS:
                    if month_label in results[court_key]:
                        log(f"  [{court_idx}/{num_courts-1}] {court_name} | {month_label} — כבר נסרק ({results[court_key][month_label]})")
                        search_num += len(DECISION_TYPES)
                        continue

                    month_total = 0
                    dt_counts = []

                    for dt_name in DECISION_TYPES:
                        search_num += 1
                        log(f"  [{search_num}/{total_searches}] {court_name} | {month_label} | {dt_name}")

                        try:
                            count = await search_and_count(page, court_idx, dt_name, year, month)
                            month_total += count
                            dt_counts.append(f"{dt_name}={count}")
                            log(f"    תוצאות: {count}")
                        except Exception as e:
                            log(f"    שגיאה: {e}")

                        await asyncio.sleep(random.uniform(1, 2))

                    results[court_key][month_label] = month_total
                    log(f"  סה\"כ {month_label}: {month_total}  ({', '.join(dt_counts)})")

                    # שמירה אחרי כל חודש
                    save_progress(results)
                    save_csv(court_names, results)

                await asyncio.sleep(random.uniform(1, 3))

        except KeyboardInterrupt:
            log("\nנעצר על ידי המשתמש")
        except Exception as e:
            log(f"\nשגיאה: {e}")
            import traceback
            log(traceback.format_exc())
        finally:
            save_progress(results)
            if court_names:
                save_csv(court_names, results)
            try:
                await browser.close()
            except Exception:
                pass
            log("סיום סקר.")
            if _log_fh:
                _log_fh.close()


asyncio.run(main())
