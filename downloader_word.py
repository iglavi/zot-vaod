"""
downloader_word.py — מוריד פסקי דין כ-DOCX (קובץ Word טקסטואלי) מנט המשפט.
קורא metadata.csv קיים, מחפש כל פסק דין באתר, ומוריד דרך כפתור "הורד Word".

הרצה:
    python downloader_word.py config_word.json

קובץ קונפיג לדוגמה:
{
  "metadata_file": "D:\\Research-bot\\2020\\metadata.csv",
  "output_dir":    "D:\\Research-bot\\2020\\docx",
  "progress_file": "D:\\Research-bot\\2020\\progress_word.json",
  "log_file":      "D:\\Research-bot\\2020\\downloader_word_log.txt",
  "year_filter":   2020,
  "headless":      false
}
"""

from __future__ import annotations

import asyncio
import csv
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("חסר playwright. הרץ: pip install playwright && playwright install chromium")
    raise SystemExit(1)

# ── קונפיג ──────────────────────────────────────────────────
_config_path = sys.argv[1] if len(sys.argv) > 1 else "config_word.json"
_cfg = json.loads(Path(_config_path).read_text(encoding="utf-8"))

METADATA_FILE = Path(_cfg["metadata_file"])
OUTPUT_DIR    = Path(_cfg["output_dir"])
PROGRESS_FILE = Path(_cfg.get("progress_file", OUTPUT_DIR / "progress_word.json"))
LOG_FILE      = Path(_cfg.get("log_file",      OUTPUT_DIR / "downloader_word_log.txt"))
YEAR_FILTER   = _cfg.get("year_filter", None)
HEADLESS      = _cfg.get("headless", False)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"

# ── לוג ─────────────────────────────────────────────────────
_log_handle = LOG_FILE.open("a", encoding="utf-8")

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    _log_handle.write(line + "\n")
    _log_handle.flush()

# ── פרוגרס ──────────────────────────────────────────────────
def load_progress() -> set[str]:
    if PROGRESS_FILE.exists() and PROGRESS_FILE.stat().st_size > 0:
        try:
            data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            return set(data.get("done", []))
        except Exception:
            pass
    return set()

def save_progress(done: set[str]):
    tmp = PROGRESS_FILE.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"done": sorted(done)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(PROGRESS_FILE)

def progress_key(date_str: str, case_num: str) -> str:
    return f"{date_str}|{case_num}"

# ── מטאדאטא ─────────────────────────────────────────────────
def load_metadata() -> list[dict]:
    rows = []
    with METADATA_FILE.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_raw = row.get("תאריך מתן החלטה", "").strip()
            if not date_raw:
                continue
            try:
                dt = datetime.strptime(date_raw, "%d/%m/%Y %H:%M:%S")
            except ValueError:
                try:
                    dt = datetime.strptime(date_raw, "%d/%m/%Y")
                except ValueError:
                    continue
            if YEAR_FILTER and dt.year != YEAR_FILTER:
                continue
            rows.append({
                "date_str":  dt.strftime("%d/%m/%Y"),
                "date_sort": dt,
                "court":     row.get("בית משפט", "").strip(),
                "case_num":  row.get("מספר תיק", "").strip(),
                "case_name": row.get("שם תיק", "").strip(),
                "dec_type":  row.get("סוג החלטה", "").strip(),
            })
    return rows

def safe_name(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text.strip())[:80] or "document"

# ── Playwright helpers ────────────────────────────────────────
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

async def dismiss_ndc_popup(page):
    for overlay_id in [
        "lean_overlay_MessageLS_NoDocumentChosenToDownload",
        "lean_overlay_MessageLS_LocateDecisionsOverflow",
        "lean_overlay_MessageLS_TooManyDocumentChosenToDownload",
        "lean_overlay_MessageLS_ChosenDocumentsUnavailableToDownload",
    ]:
        try:
            overlay = page.locator(f"#{overlay_id}")
            if await overlay.count() > 0 and await overlay.is_visible():
                for selector in ["a.modal_ReturnMessageClose", "a#returnFocus",
                                  "button:has-text('אישור')", "a:has-text('אישור')"]:
                    try:
                        el = page.locator(selector)
                        if await el.count() > 0 and await el.first.is_visible():
                            await el.first.click()
                            break
                    except Exception:
                        pass
                await page.wait_for_timeout(800)
                return
        except Exception:
            pass

async def navigate_to_search(page):
    await page.goto(SITE_URL, timeout=45000)
    await page.wait_for_timeout(3500)
    await dismiss_popup(page)
    await page.get_by_text("איתור החלטות").first.click(timeout=20000)
    await page.wait_for_timeout(2000)
    await page.get_by_text("איתור לפי פרמטרים").first.click(timeout=20000)
    await page.wait_for_timeout(1500)

async def do_search(page, court_name: str, date_str: str, dec_type: str):
    """חיפוש לפי ערכאה + תאריך + סוג החלטה."""
    await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(label=court_name)
    await page.wait_for_timeout(1200)
    await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label=dec_type)
    await page.wait_for_timeout(400)
    await page.locator("#LocateByParameters1_dateFrom").fill(date_str)
    await page.locator("#LocateByParameters1_DateTo").fill(date_str)
    await page.wait_for_timeout(300)
    await page.locator("#ButtonsGroup1_btnLocate").click()
    await page.wait_for_load_state("networkidle", timeout=30000)
    await page.wait_for_timeout(1500)
    await dismiss_popup(page)
    await page.wait_for_timeout(500)

async def get_rows_from_page(page) -> list[dict]:
    """מחזיר רשימת {row_index, case_num} מה-ag-grid הנוכחי."""
    return await page.evaluate("""
        () => {
            const rows = [...document.querySelectorAll('.ag-row')];
            return rows.map(row => {
                const idx = parseInt(row.getAttribute('row-index') || '-1');
                // מנסה לקרוא את מספר התיק מהתא הרלוונטי
                const cells = [...row.querySelectorAll('.ag-cell')];
                let caseNum = '';
                for (const cell of cells) {
                    const t = cell.innerText.trim();
                    if (t && t.length > 3 && !t.match(/^\\d{1,2}\\/\\d{1,2}\\/\\d{4}/)) {
                        caseNum = t;
                        break;
                    }
                }
                return { row_index: idx, case_num: caseNum };
            });
        }
    """)

async def find_row_index(page, target_case: str) -> int | None:
    """מוצא את row-index של תיק לפי מספר תיק."""
    rows = await get_rows_from_page(page)
    for r in rows:
        if target_case in r["case_num"] or r["case_num"] in target_case:
            return r["row_index"]
    return None

async def click_checkbox(page, row_idx: int, local_idx: int) -> bool:
    """מסמן checkbox של שורה. מחזיר True אם הצליח."""
    try:
        await page.evaluate(f"""
            () => {{
                const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
                if (row) row.scrollIntoView({{block: 'center', behavior: 'instant'}});
            }}
        """)
        await page.wait_for_timeout(400)
    except Exception:
        pass

    pos = await page.evaluate(f"""
        () => {{
            const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
            if (row) {{
                const cb = row.querySelector('input[type=checkbox]');
                if (cb) {{
                    const r = cb.getBoundingClientRect();
                    if (r.width > 0) return {{x: r.left + r.width/2, y: r.top + r.height/2}};
                }}
            }}
            const cbs = [...document.querySelectorAll('input[type=checkbox]')].filter(cb =>
                cb.offsetParent !== null &&
                !cb.parentElement?.parentElement?.className.includes('ag-header-select-all')
            );
            if ({local_idx} >= cbs.length) return null;
            const cell = cbs[{local_idx}].closest('.ag-cell');
            if (!cell) return null;
            const r = cell.getBoundingClientRect();
            return {{x: r.x + r.width/2, y: r.y + r.height/2}};
        }}
    """)

    if not pos:
        return False

    await page.mouse.click(pos["x"], pos["y"])
    await page.wait_for_timeout(600)

    checked = await page.evaluate(f"""
        () => {{
            const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
            if (row) {{
                const cb = row.querySelector('input[type=checkbox]');
                if (cb) return cb.checked;
            }}
            const cbs = [...document.querySelectorAll('input[type=checkbox]')].filter(cb =>
                cb.offsetParent !== null &&
                !cb.parentElement?.parentElement?.className.includes('ag-header-select-all')
            );
            return {local_idx} < cbs.length ? cbs[{local_idx}].checked : false;
        }}
    """)

    if not checked:
        await page.mouse.click(pos["x"], pos["y"])
        await page.wait_for_timeout(600)
        checked = await page.evaluate(f"""
            () => {{
                const cbs = [...document.querySelectorAll('input[type=checkbox]')].filter(cb =>
                    cb.offsetParent !== null &&
                    !cb.parentElement?.parentElement?.className.includes('ag-header-select-all')
                );
                return {local_idx} < cbs.length ? cbs[{local_idx}].checked : false;
            }}
        """)

    return bool(checked)

async def download_word(page, row_idx: int, local_idx: int, dest: Path) -> bool:
    """מסמן שורה ולוחץ הורד Word. מחזיר True אם הצליח."""
    await dismiss_ndc_popup(page)

    ok = await click_checkbox(page, row_idx, local_idx)
    if not ok:
        log(f"      ✗ checkbox לא נרשם")
        return False

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with page.expect_download(timeout=20000) as dl_info:
            await page.locator("#btnDownloadWordDocs").click()
        dl = await dl_info.value
        await dl.save_as(str(dest))
        return True
    except Exception as e:
        log(f"      ✗ שגיאת הורדה: {e}")
        await dismiss_ndc_popup(page)
        return False

# ── לוגיקה ראשית ─────────────────────────────────────────────
async def main():
    log("=" * 60)
    log(f"downloader_word.py — שנה: {YEAR_FILTER or 'כל'}")

    done = load_progress()
    log(f"הורדות שכבר בוצעו: {len(done)}")

    rows = load_metadata()
    log(f"שורות לטיפול: {len(rows)}")

    # מקבץ לפי (תאריך, ערכאה, סוג_החלטה)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["date_str"], r["court"], r["dec_type"])].append(r)

    def sort_key(item):
        return item[0][0][6:10] + item[0][0][3:5] + item[0][0][:2]  # YYYY-MM-DD

    stats = {"downloaded": 0, "skipped": 0, "not_found": 0, "errors": 0}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        try:
            log("מנווט לדף החיפוש...")
            await navigate_to_search(page)

            for (date_str, court_name, dec_type), group_rows in sorted(groups.items(), key=sort_key):
                log(f"\n{date_str} | {court_name} | {dec_type} ({len(group_rows)} שורות)")

                # חיפוש
                try:
                    await do_search(page, court_name, date_str, dec_type)
                except Exception as e:
                    log(f"  ✗ שגיאת חיפוש: {e}")
                    stats["errors"] += len(group_rows)
                    # ניסיון לחזור לדף החיפוש
                    try:
                        await navigate_to_search(page)
                    except Exception:
                        pass
                    continue

                # בנה מפה של תוצאות: case_num -> row_index
                result_rows = await get_rows_from_page(page)
                result_count = len(result_rows)
                log(f"  נמצאו {result_count} תוצאות")

                if result_count == 0:
                    for meta_row in group_rows:
                        pkey = progress_key(date_str, meta_row["case_num"])
                        if pkey not in done:
                            log(f"  ✗ לא נמצא: {meta_row['case_num']}")
                            stats["not_found"] += 1
                    continue

                for meta_row in group_rows:
                    case_num = meta_row["case_num"]
                    pkey = progress_key(date_str, case_num)

                    if pkey in done:
                        stats["skipped"] += 1
                        continue

                    # חיפוש השורה לפי מספר תיק
                    row_idx = None
                    local_idx = None
                    for i, r in enumerate(result_rows):
                        if case_num in r["case_num"] or r["case_num"] in case_num:
                            row_idx  = r["row_index"]
                            local_idx = i
                            break

                    if row_idx is None:
                        log(f"  ✗ לא נמצא בחיפוש: {case_num}")
                        stats["not_found"] += 1
                        continue

                    filename = f"{safe_name(case_num)}.docx"
                    dest = OUTPUT_DIR / date_str.replace("/", "-") / filename

                    ok = await download_word(page, row_idx, local_idx, dest)
                    if ok:
                        log(f"  ✓ {case_num} → {dest.name}")
                        done.add(pkey)
                        stats["downloaded"] += 1
                        save_progress(done)
                    else:
                        stats["errors"] += 1

                    await page.wait_for_timeout(500)

                # חזרה לדף חיפוש לקבוצה הבאה
                try:
                    await navigate_to_search(page)
                except Exception as e:
                    log(f"  ⚠ שגיאה בחזרה לחיפוש: {e}")

        finally:
            await browser.close()

    log("\n" + "=" * 60)
    log(f"סיכום:")
    log(f"  הורדו:        {stats['downloaded']}")
    log(f"  דולגו:        {stats['skipped']}")
    log(f"  לא נמצאו:    {stats['not_found']}")
    log(f"  שגיאות:       {stats['errors']}")
    log("=" * 60)
    _log_handle.close()

if __name__ == "__main__":
    asyncio.run(main())
