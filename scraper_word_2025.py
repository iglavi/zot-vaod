"""
scraper_word_2025.py — סקראפר + הורדת DOCX בריצה אחת.

לכל יום: מחפש, שומר מטאדאטא ל-CSV, ומוריד קובץ Word לכל תוצאה.
אסטרטגיית חיפוש זהה לסקריפר הקיים:
  1. כל הערכאות — אם <100 תוצאות, גמרנו.
  2. אם 100+ — מחלק לפי ערכאה.
  3. אם ערכאה בודדת עדיין 100 — מחלק לפי שופט ואז הליך.

שני קבצי פרוגרס:
  progress_scrape.json  — אילו (יום|סוג_החלטה) כבר נסרקו
  progress_download.json — אילו (תאריך|מספר_תיק) כבר הורדו

הרצה:
    python scraper_word_2025.py config_word_2025.json
"""

from __future__ import annotations

import asyncio
import csv
import ctypes
import json
import random
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta, datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("חסר playwright. הרץ: pip install playwright && playwright install chromium")
    raise SystemExit(1)

# ── קונפיג ──────────────────────────────────────────────────
_config_path = sys.argv[1] if len(sys.argv) > 1 else "config_word_2025.json"
_cfg = json.loads(Path(_config_path).read_text(encoding="utf-8"))

DATE_FROM      = _cfg["date_from"]
DATE_TO        = _cfg["date_to"]
OUTPUT_DIR     = Path(_cfg["output_dir"])
DOCX_DIR       = Path(_cfg.get("docx_dir", OUTPUT_DIR / "docx"))
MASTER_CSV     = OUTPUT_DIR / _cfg.get("metadata_file", "metadata.csv")
PROGRESS_SCRAPE = OUTPUT_DIR / _cfg.get("progress_scrape",  "progress_scrape.json")
PROGRESS_DL     = OUTPUT_DIR / _cfg.get("progress_download", "progress_download.json")
DATA_FILE      = OUTPUT_DIR / "data.json"
LOG_FILE       = OUTPUT_DIR / _cfg.get("log_file", "scraper_word_log.txt")
HEADLESS       = _cfg.get("headless", False)
DECISION_TYPES = _cfg.get("decision_types", ["פסק דין", "גזר דין", "הכרעת דין"])

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DOCX_DIR.mkdir(parents=True, exist_ok=True)

SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]
SKIP_PREFIXES = ("בית דין", "בית משפט צבאי", "ועדת שחרורים")

# ── מצב ריצה ─────────────────────────────────────────────
@dataclass
class State:
    log_fh: object = None
    scraped: int = 0
    downloaded: int = 0
    dl_errors: int = 0
    errors: int = 0

_state = State()


# ── לוג ─────────────────────────────────────────────────────
def log(msg: str, is_error: bool = False):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if _state.log_fh:
        _state.log_fh.write(line + "\n")
        _state.log_fh.flush()
    if is_error:
        _state.errors += 1


def prevent_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    except Exception:
        pass

def allow_sleep():
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
    except Exception:
        pass


# ── פרוגרס ──────────────────────────────────────────────────
def load_progress(path: Path) -> set[str]:
    if path.exists() and path.stat().st_size > 0:
        try:
            return set(json.loads(path.read_text(encoding="utf-8")).get("done", []))
        except Exception:
            pass
    return set()

def save_progress(path: Path, done: set[str]):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"done": sorted(done)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)

def pkey(*parts) -> str:
    return "|".join(str(p) for p in parts)


# ── תאריכים ──────────────────────────────────────────────────
def d2s(d: date) -> str:
    return d.strftime("%Y-%m-%d")

def s2d(s: str) -> date:
    return date.fromisoformat(s)

def mid_date(d1: date, d2: date) -> date:
    return d1 + (d2 - d1) // 2


# ── ניווט ────────────────────────────────────────────────────
async def dismiss_popup(page):
    for locator in [
        page.locator("button", has_text="אישור"),
        page.locator("input[value='אישור']"),
    ]:
        try:
            if await locator.count() > 0:
                await locator.first.click()
                await page.wait_for_timeout(400)
                return
        except Exception:
            pass
    try:
        overlay = page.locator("[id^='lean_overlay']")
        if await overlay.count() > 0 and await overlay.is_visible():
            await overlay.click()
            await page.wait_for_timeout(400)
    except Exception:
        pass

async def dismiss_ndc_popup(page):
    for oid in [
        "lean_overlay_MessageLS_NoDocumentChosenToDownload",
        "lean_overlay_MessageLS_LocateDecisionsOverflow",
        "lean_overlay_MessageLS_TooManyDocumentChosenToDownload",
        "lean_overlay_MessageLS_ChosenDocumentsUnavailableToDownload",
    ]:
        try:
            ov = page.locator(f"#{oid}")
            if await ov.count() > 0 and await ov.is_visible():
                for sel in ["a.modal_ReturnMessageClose", "a#returnFocus",
                            "button:has-text('אישור')", "a:has-text('אישור')"]:
                    try:
                        el = page.locator(sel)
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
    WAIT_SCHEDULE = [120, 2 * 3600, 2 * 3600]
    try:
        btn = page.get_by_text("איתור לפי פרמטרים").first
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click(timeout=5000)
            await page.wait_for_timeout(600)
            if await page.locator("#LocateByParameters1_ddlSelectCourt").count() > 0:
                return
    except Exception:
        pass
    for attempt in range(1, len(WAIT_SCHEDULE) + 2):
        try:
            await page.goto(SITE_URL, timeout=45000)
            await page.wait_for_timeout(random.uniform(3000, 4500))
            await dismiss_popup(page)
            await page.get_by_text("איתור החלטות").first.click(timeout=20000)
            await page.wait_for_timeout(random.uniform(1200, 2000))
            await page.get_by_text("איתור לפי פרמטרים").first.click(timeout=20000)
            await page.wait_for_timeout(random.uniform(800, 1500))
            return
        except Exception as e:
            err = str(e)
            transient = any(x in err for x in [
                "ERR_NETWORK_IO_SUSPENDED", "ERR_CONNECTION_REFUSED",
                "ERR_NAME_NOT_RESOLVED", "net::", "Timeout",
                "Target page", "context or browser has been closed", "Target crashed",
            ])
            if not transient or attempt > len(WAIT_SCHEDULE):
                raise
            wait_sec = WAIT_SCHEDULE[attempt - 1]
            wait_str = f"{wait_sec // 3600} שעות" if wait_sec >= 3600 else f"{wait_sec // 60} דקות"
            log(f"  [retry {attempt}] האתר לא זמין — ממתין {wait_str}...")
            await asyncio.sleep(wait_sec)


# ── פילטרים וחיפוש ───────────────────────────────────────────
async def set_date_picker(page, field_id: str, d: date):
    date_str = d.strftime("%d/%m/%Y")
    await page.evaluate(f"""
        () => {{
            const el = document.getElementById('{field_id}');
            if (el) {{
                el.removeAttribute('readonly');
                el.value = '{date_str}';
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                el.dispatchEvent(new Event('input',  {{bubbles: true}}));
            }}
        }}
    """)
    await page.wait_for_timeout(150)

async def do_search(page, court_idx: int, dt_name: str,
                    from_date: date, to_date: date,
                    judge_idx: int | None = None,
                    proc_idx:  int | None = None):
    await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
    await page.wait_for_timeout(900)
    if judge_idx is not None:
        try:
            await page.locator("#LocateByParameters1_ddlJudgeName").select_option(index=judge_idx)
            await page.wait_for_timeout(300)
        except Exception:
            pass
    await page.locator("#LocateByParameters1_ddlDecisionType").select_option(label=dt_name)
    await page.wait_for_timeout(300)
    if proc_idx is not None:
        try:
            await page.locator("#LocateByParameters1_ddlSelectProceeding").select_option(index=proc_idx)
            await page.wait_for_timeout(300)
        except Exception:
            pass
    await set_date_picker(page, "LocateByParameters1_dateFrom", from_date)
    await set_date_picker(page, "LocateByParameters1_DateTo",   to_date)
    await page.evaluate("document.getElementById('ButtonsGroup1_btnLocate').click()")
    try:
        await page.locator(".ag-row").first.wait_for(timeout=10000)
    except Exception:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    await page.wait_for_timeout(500)
    await dismiss_popup(page)
    await page.wait_for_timeout(300)

async def get_result_count(page) -> tuple[int, bool]:
    try:
        body = await page.locator("body").inner_text()
        m = re.search(r'מתוך\s+(\d+)', body)
        if m:
            n = int(m.group(1))
            return n, (n >= 100)
    except Exception:
        pass
    try:
        count = await page.locator(".ag-row").count()
        if count > 0:
            return count, (count >= 100)
    except Exception:
        pass
    return 0, False


# ── CSV מטאדאטא ───────────────────────────────────────────────
_existing_keys: set[tuple] = set()
_master_fieldnames: list[str] = []
_master_initialized = False

def _make_row_key(row: dict) -> tuple | None:
    c = str(row.get("מספר תיק", "")).strip()
    d = str(row.get("תאריך מתן החלטה", "")).strip()
    return (c, d) if c and d else None

def _init_master_cache():
    global _existing_keys, _master_fieldnames, _master_initialized
    if _master_initialized:
        return
    _master_initialized = True
    if MASTER_CSV.exists() and MASTER_CSV.stat().st_size > 0:
        try:
            with open(MASTER_CSV, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                _master_fieldnames = list(reader.fieldnames or [])
                for r in reader:
                    k = _make_row_key(r)
                    if k:
                        _existing_keys.add(k)
            log(f"  cache: {len(_existing_keys)} שורות קיימות")
        except Exception as e:
            log(f"  אזהרה — לא הצלחתי לקרוא CSV קיים: {e}")

def append_to_master_csv(rows: list[dict]) -> list[dict]:
    """מוסיף שורות חדשות. מחזיר רשימת השורות שנוספו בפועל."""
    global _master_fieldnames
    if not rows:
        return []
    _init_master_cache()
    if not _master_fieldnames:
        _master_fieldnames = list(rows[0].keys())
    to_add, skipped = [], 0
    for row in rows:
        k = _make_row_key(row)
        if k and k in _existing_keys:
            skipped += 1
        else:
            to_add.append(row)
            if k:
                _existing_keys.add(k)
    if not to_add:
        log(f"    דולגו {skipped} כפולות — אין חדשות")
        return []
    new_file = not MASTER_CSV.exists() or MASTER_CSV.stat().st_size == 0
    with open(MASTER_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_master_fieldnames, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerows(to_add)
    _state.scraped += len(to_add)
    log(f"    נוספו {len(to_add)} שורות למטאדאטא, דולגו {skipped} כפולות")
    return to_add

async def export_page_csv(page) -> list[dict]:
    try:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir=OUTPUT_DIR) as tf:
            tmp = Path(tf.name)
        if await page.locator(".ag-row").count() == 0:
            return []
        try:
            overlay = page.locator("[id^='lean_overlay']")
            if await overlay.count() > 0 and await overlay.is_visible():
                await overlay.click()
                await page.wait_for_timeout(400)
        except Exception:
            pass
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
            await page.wait_for_timeout(600)
            await page.locator(".ag-menu-option").dispatch_event("click")
            await page.wait_for_timeout(400)
            await page.get_by_text("ייצוא נתונים ל- CSV").dispatch_event("click")
        dl = await dl_info.value
        await dl.save_as(str(tmp))
        with open(tmp, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        tmp.unlink(missing_ok=True)
        return rows
    except Exception as e:
        log(f"    שגיאת CSV: {e}", is_error=True)
        return []


# ── הורדת DOCX ───────────────────────────────────────────────
def safe_name(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text.strip())[:80] or "document"

def extract_date_str(raw: str) -> str:
    """DD/MM/YYYY HH:MM:SS → DD-MM-YYYY"""
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', raw)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    return raw[:10].replace("/", "-")

async def click_checkbox(page, row_idx: int, local_idx: int) -> bool:
    try:
        await page.evaluate(f"""
            () => {{
                const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
                if (row) row.scrollIntoView({{block: 'center', behavior: 'instant'}});
                else {{
                    const body = document.querySelector('.ag-body-viewport');
                    if (body) {{
                        const anyRow = document.querySelector('.ag-row');
                        const h = anyRow ? (anyRow.offsetHeight || 42) : 42;
                        body.scrollTop = Math.max(0, {row_idx} * h - body.clientHeight / 2);
                    }}
                }}
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

async def download_one_docx(page, row_idx: int, local_idx: int, dest: Path) -> bool:
    await dismiss_ndc_popup(page)
    if not await click_checkbox(page, row_idx, local_idx):
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

async def download_all_in_results(page, csv_rows: list[dict],
                                   done_dl: set[str]):
    """לכל שורה בתוצאות: מוריד DOCX אם עדיין לא הורד."""
    for local_idx, row in enumerate(csv_rows):
        case_num = str(row.get("מספר תיק", "")).strip()
        date_raw = str(row.get("תאריך מתן החלטה", "")).strip()
        if not case_num:
            continue

        pk = pkey(date_raw, case_num)
        if pk in done_dl:
            continue

        date_folder = extract_date_str(date_raw)
        dest = DOCX_DIR / date_folder / f"{safe_name(case_num)}.docx"
        if dest.exists():
            done_dl.add(pk)
            continue

        ok = await download_one_docx(page, local_idx, local_idx, dest)
        if ok:
            log(f"      ✓ {case_num} → {dest.name}")
            done_dl.add(pk)
            _state.downloaded += 1
            save_progress(PROGRESS_DL, done_dl)
        else:
            _state.dl_errors += 1

        await page.wait_for_timeout(300)


# ── עיבוד batch ──────────────────────────────────────────────
async def process_results(page, done_dl: set[str]):
    csv_rows = await export_page_csv(page)
    if not csv_rows:
        log("    אין שורות לעיבוד")
        return
    log(f"    CSV: {len(csv_rows)} שורות")
    new_rows = append_to_master_csv(csv_rows)
    await download_all_in_results(page, csv_rows, done_dl)


# ── חלוקה בינארית (זהה לסקריפר הקיים) ───────────────────────
async def scrape_range(page, court_idx: int, dt_name: str,
                       from_date: date, to_date: date,
                       done_dl: set[str],
                       judge_idx: int | None = None,
                       judge_name: str | None = None,
                       proc_idx:  int | None = None,
                       depth: int = 0):
    indent = "  " * depth
    await navigate_to_search(page)
    await do_search(page, court_idx, dt_name, from_date, to_date, judge_idx, proc_idx)
    count, is_capped = await get_result_count(page)
    jlabel = f" [{judge_name}]" if judge_name else ""
    log(f"{indent}  תוצאות{jlabel}: {count}{' ← מוגבל!' if is_capped else ''}")

    if count == 0:
        return
    if not is_capped:
        await process_results(page, done_dl)
        return

    if from_date == to_date:
        if judge_idx is None:
            log(f"{indent}  [רשת ביטחון] יום בודד 100 — מחלק לפי שופטים")
            await navigate_to_search(page)
            await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
            await page.wait_for_timeout(1200)
            judge_opts = await page.locator("#LocateByParameters1_ddlJudgeName option").all()
            judge_names = [(await o.inner_text()).strip() for o in judge_opts]
            if len(judge_names) <= 1:
                log(f"{indent}  אין שופטים — מוריד 100 תוצאות")
                await do_search(page, court_idx, dt_name, from_date, to_date)
                await process_results(page, done_dl)
                return
            log(f"{indent}  {len(judge_names) - 1} שופטים")
            for jidx in range(1, len(judge_names)):
                await scrape_range(page, court_idx, dt_name, from_date, to_date,
                                   done_dl, jidx, judge_names[jidx], None, depth + 1)
                await asyncio.sleep(random.uniform(0.5, 1.5))
        elif proc_idx is None:
            log(f"{indent}  [רשת ביטחון] שופט+יום 100 — מחלק לפי הליך")
            await navigate_to_search(page)
            await page.locator("#LocateByParameters1_ddlSelectCourt").select_option(index=court_idx)
            await page.wait_for_timeout(1200)
            proc_opts = await page.locator("#LocateByParameters1_ddlSelectProceeding option").all()
            proc_names = [(await o.inner_text()).strip() for o in proc_opts]
            if len(proc_names) <= 1:
                log(f"{indent}  אין הליכים — מוריד 100 תוצאות")
                await do_search(page, court_idx, dt_name, from_date, to_date, judge_idx)
                await process_results(page, done_dl)
                return
            log(f"{indent}  {len(proc_names) - 1} הליכים")
            for pidx in range(1, len(proc_names)):
                log(f"{indent}  הליך: {proc_names[pidx]}")
                await scrape_range(page, court_idx, dt_name, from_date, to_date,
                                   done_dl, judge_idx, judge_name, pidx, depth + 1)
                await asyncio.sleep(random.uniform(0.5, 1.5))
        else:
            log(f"{indent}  **100+ לאחר פילטור מלא — תוצאות חלקיות**", is_error=True)
            await process_results(page, done_dl)
        return

    mid = mid_date(from_date, to_date)
    log(f"{indent}  [רשת ביטחון] מחלק: {d2s(from_date)}-{d2s(mid)} | {d2s(mid + timedelta(1))}-{d2s(to_date)}")
    await scrape_range(page, court_idx, dt_name, from_date, mid,
                       done_dl, judge_idx, judge_name, proc_idx, depth + 1)
    await asyncio.sleep(random.uniform(0.5, 1.5))
    await scrape_range(page, court_idx, dt_name, mid + timedelta(1), to_date,
                       done_dl, judge_idx, judge_name, proc_idx, depth + 1)


async def scrape_courts_subset(page, dt_name: str, day: date,
                                court_names: list[str], court_indices: list[int],
                                tag: str, done_dl: set[str]):
    for court_idx in court_indices:
        court_name = court_names[court_idx]
        if any(court_name.startswith(p) for p in SKIP_PREFIXES):
            continue
        log(f"    [{tag}] ערכאה {court_idx}: {court_name}")
        try:
            await scrape_range(page, court_idx, dt_name, day, day, done_dl)
        except Exception as e:
            log(f"    [{tag}] שגיאה בערכאה {court_idx}: {e}", is_error=True)
        await asyncio.sleep(random.uniform(0.8, 2))


async def scrape_day(page, page2, dt_name: str, day: date,
                     court_names: list[str], num_courts: int,
                     done_dl: set[str]):
    day_str = d2s(day)
    await navigate_to_search(page)
    await do_search(page, 0, dt_name, day, day)
    count, is_capped = await get_result_count(page)
    log(f"  [{dt_name}] {day_str} — כל הערכאות: {count} תוצאות")

    if count == 0:
        return
    if not is_capped:
        await process_results(page, done_dl)
        return

    log(f"  [{dt_name}] {day_str} — 100+ תוצאות, מחפש לפי ערכאה (2 טאבים)...")
    court_indices = list(range(1, num_courts))
    half = len(court_indices) // 2
    await asyncio.gather(
        scrape_courts_subset(page,  dt_name, day, court_names,
                             court_indices[:half], "טאב 1", done_dl),
        scrape_courts_subset(page2, dt_name, day, court_names,
                             court_indices[half:], "טאב 2", done_dl),
        return_exceptions=True,
    )


# ── main ──────────────────────────────────────────────────────
async def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prevent_sleep()
    _state.log_fh = open(LOG_FILE, "a", encoding="utf-8")
    run_start = datetime.now()
    log("=" * 60)
    log(f"scraper_word_2025.py — {DATE_FROM} עד {DATE_TO}")

    done_scrape = load_progress(PROGRESS_SCRAPE)
    done_dl     = load_progress(PROGRESS_DL)
    log(f"פרוגרס: {len(done_scrape)} ימים/סוגים נסרקו | {len(done_dl)} קבצים הורדו")

    court_names = None
    if DATA_FILE.exists():
        cached = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        court_names = cached.get("court_names")
        if court_names:
            log(f"ערכאות מהמטמון: {len(court_names) - 1}")

    ua = random.choice(USER_AGENTS)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        context  = await browser.new_context(accept_downloads=True, user_agent=ua)
        context2 = await browser.new_context(accept_downloads=True, user_agent=ua)
        page  = await context.new_page()
        page2 = await context2.new_page()

        try:
            if not court_names:
                await navigate_to_search(page)
                opts = await page.locator("#LocateByParameters1_ddlSelectCourt option").all()
                court_names = [(await o.inner_text()).strip() for o in opts]
                existing = {}
                if DATA_FILE.exists():
                    existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
                existing["court_names"] = court_names
                DATA_FILE.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

            num_courts = len(court_names)
            from_d = s2d(DATE_FROM)
            to_d   = s2d(DATE_TO)
            current = from_d

            while current <= to_d:
                day_str = d2s(current)
                log(f"\n{'=' * 50}")
                log(f"יום: {day_str}")

                for dt_name in DECISION_TYPES:
                    key = pkey(day_str, dt_name)
                    if key in done_scrape:
                        log(f"  [{dt_name}] {day_str} — כבר הושלם")
                        continue

                    for attempt in range(1, 4):
                        try:
                            await scrape_day(page, page2, dt_name, current,
                                             court_names, num_courts, done_dl)
                            break
                        except Exception as e:
                            err = str(e)
                            transient = any(x in err for x in [
                                "Timeout", "TimeoutError", "net::", "ERR_",
                                "Target page", "context or browser", "Target crashed",
                            ])
                            if not transient or attempt == 3:
                                raise
                            wait_sec = attempt * 120
                            log(f"  [retry {attempt}/3] timeout — ממתין {wait_sec//60} דקות...", is_error=True)
                            await asyncio.sleep(wait_sec)
                            await navigate_to_search(page)

                    done_scrape.add(key)
                    save_progress(PROGRESS_SCRAPE, done_scrape)
                    await asyncio.sleep(random.uniform(0.5, 1.5))

                current += timedelta(days=1)

        except KeyboardInterrupt:
            log("\nנעצר על ידי המשתמש")
        except Exception as e:
            log(f"\nשגיאה: {e}", is_error=True)
            import traceback; log(traceback.format_exc())
        finally:
            save_progress(PROGRESS_SCRAPE, done_scrape)
            save_progress(PROGRESS_DL, done_dl)
            allow_sleep()
            try:
                await browser.close()
            except Exception:
                pass
            elapsed = datetime.now() - run_start
            h, rem = divmod(int(elapsed.total_seconds()), 3600)
            m, s = divmod(rem, 60)
            log("\n" + "=" * 60)
            log(f"סיכום: זמן {h}:{m:02d}:{s:02d} | "
                f"מטאדאטא {_state.scraped} | "
                f"DOCX הורדו {_state.downloaded} | "
                f"שגיאות הורדה {_state.dl_errors} | "
                f"שגיאות כלליות {_state.errors}")
            log("=" * 60)
            if _state.log_fh:
                _state.log_fh.close()


asyncio.run(main())
