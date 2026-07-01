"""
scraper_by_metadata.py — הורדת DOCX לפי קובץ מטאדאטא, חיפוש לפי מספר תיק.

עבור כל שורה במטאדאטא (שסוג ההחלטה שלה הוא פסק/גזר/הכרעת דין):
  1. פותח את טופס "איתור לפי תיק"
  2. ממלא מספר תיק, ערכאה, סוג תיק (אם רלוונטי)
  3. מוצא את השורה המתאימה בתוצאות (לפי תאריך + סוג החלטה)
  4. מוריד קובץ Word
  5. לוחץ "חזרה" וממשיך לתיק הבא

הרצה:
    python scraper_by_metadata.py config_metadata_dl.json
"""
from __future__ import annotations

import asyncio
import csv
import ctypes
import json
import random
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("חסר playwright. הרץ: pip install playwright && playwright install chromium")
    raise SystemExit(1)

# ── קונפיג ──────────────────────────────────────────────────
_config_path = sys.argv[1] if len(sys.argv) > 1 else "config_metadata_dl.json"
_cfg = json.loads(Path(_config_path).read_text(encoding="utf-8"))

INPUT_CSV   = Path(_cfg["input_csv"])
OUTPUT_DIR  = Path(_cfg["output_dir"])
DOCX_DIR    = Path(_cfg.get("docx_dir", str(OUTPUT_DIR)))
PROGRESS_DL = OUTPUT_DIR / _cfg.get("progress_file", "progress_dl.json")
LOG_FILE    = OUTPUT_DIR / _cfg.get("log_file", "scraper_metadata_log.txt")
HEADLESS    = _cfg.get("headless", False)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DOCX_DIR.mkdir(parents=True, exist_ok=True)

SITE_URL = "https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"
DECISION_TYPES_WANTED = {"פסק דין", "גזר דין", "הכרעת דין"}
SUPREME_COURT_NAMES   = {"העליון"}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
]

# ── מיפוי סוג תיק → קוד ב-dropdown ─────────────────────────
# ערך None = ערכאה ללא בחירת סוג תיק (העליון) או מסלול תעבורה
SUG_TIK_MAP: dict[str, str | None] = {
    'ערעור אזרחי (ע"א)':                                        'עא',
    'ערעור פלילי (ע"פ)':                                        'עפ',
    'ערעור פלילי גזר דין (עפ"ג)':                               'עפג',
    'עתירה לבג"ץ (בג"ץ)':                                       None,
    'רשות ערעור אזרחי (רע"א)':                                  'ראע',
    'רשות ערעור פלילי (רע"פ)':                                  'רעפ',
    'רשות ערעור בתי סוהר (רעב"ס)':                             'רעב',
    'דיון נוסף (ד"ן)':                                          'דן',
    'דיון נוסף אזרחי (דנ"א)':                                   'דנא',
    'דיון נוסף בג"ץ (דנג"ץ)':                                   'דנגץ',
    'דיון נוסף פלילי (דנ"פ)':                                   'דנפ',
    'תיק אזרחי בסדר דין רגיל (ת"א)':                           'א',
    'תיק אזרחי בסדר דין מקוצר (תא"ק)':                         'א',
    'המרצת פתיחה (ה"פ)':                                        'הפ',
    'תאונת דרכים (ת"ד)':                                        'תד',
    'תיק פלילי (ת"פ)':                                          'פ',
    'תיק פשעים חמורים (תפ"ח)':                                  'פח',
    'תיק פלילי בניה (תפ"ב)':                                    'פ',
    'תכנון ובנייה - ועדות מקומיות (תו"ב)':                     'תוב',
    'ערעור עבודה (ע"ע)':                                        'עע',
    'ערעור ביטוח לאומי (עב"ל)':                                 'עבל',
    'ערעור בחירות (ע"ב)':                                       'עבח',
    'בקשות שונות אזרחי (בש"א)':                                 'בשא',
    'בקשות שונות פלילי (בש"פ)':                                 'בשפ',
    'בקשות שונות בג"ץ (בשג"ץ)':                                 'בשגץ',
    'בקשה לשחזור תיק (בש"ז)':                                   'בשז',
    'מעצר עד תום ההליכים (מ"ת)':                               'מת',
    'משפט חוזר (מ"ח)':                                          'מח',
    'ערעור לשכת עורכי הדין (על"ע)':                             'עלע',
    'ערעור משמעתי עובדי מדינה (עש"מ)':                         'עשמ',
    'ערעור לפי חוק הרשויות המקומיות (משמעת) (ער"מ)':           'ערמ',
    'תיק לאיתור (תל"א)':                                        'תלא',
    'תובענה ארגונית (בין עובד לארגון עובדים) (תע"א)':           'תעא',
    'דיון מהיר בסמכות שופט (דמ"ש)':                            'דמ',
    'תיק תעבורה (תת"ע)':                                        None,  # מסלול תעבורה
    'ערעור על החלטת רשם (ע"ר)':                                 'ערמ',
}

EXCEL_MONTHS = {
    'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12',
}


# ── מצב ריצה ─────────────────────────────────────────────
@dataclass
class State:
    log_fh:    object = None
    downloaded: int   = 0
    skipped:    int   = 0
    errors:     int   = 0
    no_match:   int   = 0

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


# ── שמות קבצים ──────────────────────────────────────────────
def safe_name(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text.strip())[:60] or "document"

def date_for_filename(raw: str) -> str:
    """DD/MM/YYYY HH:MM:SS → YYYY-MM-DD"""
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', raw)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    return re.sub(r'[^\d\-]', '', raw)[:10]

def build_dest(case_num: str, date_raw: str, index: int = 0) -> Path:
    base = safe_name(case_num) + "_" + date_for_filename(date_raw)
    suffix = f"_{index}" if index > 0 else ""
    return DOCX_DIR / f"{base}{suffix}.docx"


# ── מיון מספרי תיק ──────────────────────────────────────────
def parse_case_number(cn: str) -> dict:
    """
    מחזיר: {'format': 'new'|'old', 'serial': str, 'month': str|None, 'year': str}
    'new' = 3 רכיבים (serial/month/year), 'old' = 2 רכיבים (serial/year)
    אם Excel טרף את המספר (JAN-00) — מחזיר {'format': 'mangled'}
    """
    cn = cn.strip()
    # Excel mangling: JAN-00
    m = re.match(r'^([A-Z]{3})-(\d{2,4})$', cn)
    if m:
        return {'format': 'mangled', 'original': cn}

    parts = re.split(r'[/\-]', cn)
    if len(parts) == 3:
        return {'format': 'new', 'serial': parts[0].strip(), 'month': parts[1].strip(), 'year': parts[2].strip()}
    elif len(parts) == 2:
        return {'format': 'old', 'serial': parts[0].strip(), 'year': parts[1].strip()}
    else:
        return {'format': 'unknown', 'serial': cn, 'year': ''}


# ── נורמליזציה של תאריכים להשוואה ───────────────────────────
def normalize_date(raw: str) -> str:
    """מחלץ DD/MM/YYYY ומחזיר YYYY-MM-DD לצורך השוואה."""
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', raw)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    # ייתכן DD/MM/YYYY ללא שעה
    m = re.search(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', raw)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    return raw.strip()


# ── ניווט כללי ──────────────────────────────────────────────
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


async def navigate_to_case_search(page):
    """ניווט לדף 'איתור לפי תיק'. מנסה כמה דרכים לחזור לדף."""
    WAIT_SCHEDULE = [120, 2 * 3600]
    for attempt in range(1, len(WAIT_SCHEDULE) + 2):
        try:
            await page.goto(SITE_URL, timeout=45000)
            await page.wait_for_timeout(random.uniform(3000, 4500))
            await dismiss_popup(page)
            await page.get_by_text("איתור החלטות").first.click(timeout=20000)
            await page.wait_for_timeout(random.uniform(1200, 2000))
            await page.get_by_text("איתור לפי תיק").first.click(timeout=20000)
            await page.wait_for_timeout(random.uniform(800, 1500))
            return
        except Exception as e:
            err = str(e)
            transient = any(x in err for x in [
                "ERR_NETWORK", "ERR_CONNECTION", "ERR_NAME",
                "net::", "Timeout", "Target page", "context or browser",
            ])
            if not transient or attempt > len(WAIT_SCHEDULE):
                raise
            wait_sec = WAIT_SCHEDULE[attempt - 1]
            wait_str = f"{wait_sec // 3600} שעות" if wait_sec >= 3600 else f"{wait_sec // 60} דקות"
            log(f"  [retry {attempt}] האתר לא זמין — ממתין {wait_str}...")
            await asyncio.sleep(wait_sec)


async def go_back_to_search(page) -> bool:
    """לוחץ על כפתור 'חזרה' לחזרה לטופס החיפוש."""
    try:
        btn = page.locator("input[value='חזרה'], button:has-text('חזרה')").first
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click()
            await page.wait_for_timeout(1000)
            return True
    except Exception:
        pass
    # ניסיון שני — חיפוש לפי id או value
    try:
        clicked = await page.evaluate("""
            () => {
                const btns = [...document.querySelectorAll('input[type=button], button')];
                const b = btns.find(b => b.value === 'חזרה' || b.innerText.trim() === 'חזרה');
                if (b) { b.click(); return true; }
                return false;
            }
        """)
        if clicked:
            await page.wait_for_timeout(1000)
            return True
    except Exception:
        pass
    return False


# ── מילוי טופס חיפוש לפי תיק ───────────────────────────────
RADIO_ID_HINTS = {
    "תיק ישן": "OldCaseIdentifierOptionBoxVT",
    "תיק חדש": "BamaCaseIdentifierOptionBoxVT",
}

# רדיו "בית משפט"/"תעבורה" בטופס תיק חדש — קבוצת NumeratorGroupTypeVT
NEW_COURT_RADIO_ID   = "NumeratorGroupTypeVT_Value_eq_1"   # בית משפט
NEW_TRAFFIC_RADIO_ID = "NumeratorGroupTypeVT_Value_eq_2"   # תעבורה
NEW_SERIAL_ID    = "BamaCaseNumberTextBoxVT"
NEW_MONTHYEAR_ID = "BamaMonthYearTextBoxVT"

async def _click_element_by_id_contains(page, substr: str) -> bool:
    """לוחץ על האלמנט הראשון שה-id שלו מכיל substr (תבנית ASP.NET קבועה)."""
    try:
        loc = page.locator(f"[id*='{substr}']")
        if await loc.count() > 0:
            await loc.first.click()
            await page.wait_for_timeout(600)
            return True
    except Exception:
        pass
    return False


async def _dump_radios(page):
    """דיבוג: מדפיס את כל ה-radio buttons בדף עם הטקסט הסמוך להם."""
    try:
        info = await page.evaluate("""
            () => {
                const radios = [...document.querySelectorAll('input[type=radio]')];
                return radios.map(r => {
                    let text = '';
                    // label עם for
                    if (r.id) {
                        const lbl = document.querySelector(`label[for="${r.id}"]`);
                        if (lbl) text = lbl.innerText.trim();
                    }
                    if (!text) {
                        const parent = r.closest('td, label, span, div');
                        if (parent) text = parent.innerText.trim().slice(0, 40);
                    }
                    if (!text && r.parentElement) text = r.parentElement.innerText.trim().slice(0, 40);
                    return {id: r.id, name: r.name, value: r.value, checked: r.checked, text};
                });
            }
        """)
        log(f"    [radio-dump] {info}")
    except Exception as e:
        log(f"    [radio-dump] שגיאה: {e}")


async def _click_radio_by_label(page, label_text: str) -> bool:
    """לוחץ על radio button. מנסה קודם לפי id (תבנית ASP.NET קבועה), ואז לפי טקסט סמוך."""
    hint = RADIO_ID_HINTS.get(label_text)
    if hint and await _click_element_by_id_contains(page, hint):
        return True
    try:
        clicked = await page.evaluate(f"""
            () => {{
                const target = '{label_text}';
                // 1. label[for] מתאים
                const labels = [...document.querySelectorAll('label')];
                let lbl = labels.find(l => l.innerText.trim() === target || l.innerText.trim().includes(target));
                if (lbl) {{
                    let radio = null;
                    if (lbl.htmlFor) radio = document.getElementById(lbl.htmlFor);
                    if (!radio) radio = lbl.querySelector('input[type=radio]');
                    if (radio) {{
                        radio.checked = true;
                        radio.click();
                        radio.dispatchEvent(new Event('change', {{bubbles: true}}));
                        radio.dispatchEvent(new Event('click', {{bubbles: true}}));
                        return {{ok: true, method: 'label-for'}};
                    }}
                    lbl.click();
                    return {{ok: true, method: 'label-click'}};
                }}
                // 2. radio עם name/id/value מכיל את הטקסט (לפעמים ASP.NET משתמש ב-id כמו rbOldCase)
                const radios = [...document.querySelectorAll('input[type=radio]')];
                for (const r of radios) {{
                    const parent = r.closest('td, label, span, div');
                    const parentText = parent ? parent.innerText.trim() : '';
                    if (parentText.includes(target)) {{
                        r.checked = true;
                        r.click();
                        r.dispatchEvent(new Event('change', {{bubbles: true}}));
                        return {{ok: true, method: 'parent-text', parentText}};
                    }}
                    let sib = r.nextSibling;
                    let hops = 0;
                    while (sib && hops < 5) {{
                        const t = sib.nodeType === 3 ? sib.textContent : (sib.innerText || '');
                        if (t && t.trim().includes(target)) {{
                            r.checked = true;
                            r.click();
                            r.dispatchEvent(new Event('change', {{bubbles: true}}));
                            return {{ok: true, method: 'sibling-text'}};
                        }}
                        sib = sib.nextSibling;
                        hops++;
                    }}
                }}
                return {{ok: false}};
            }}
        """)
        if clicked.get("ok"):
            await page.wait_for_timeout(500)
            return True
        log(f"    [radio] לא מצאתי '{label_text}'", is_error=True)
        await _dump_radios(page)
    except Exception as e:
        log(f"    [radio] שגיאה: {e}", is_error=True)
    return False


async def _click_search_button(page) -> bool:
    """לוחץ על כפתור החיפוש בטופס 'איתור לפי תיק'."""
    try:
        clicked = await page.evaluate("""
            () => {
                // מחפש כפתור חיפוש בדף
                const candidates = [
                    ...document.querySelectorAll('input[type=submit], input[type=button], button')
                ];
                const btn = candidates.find(b =>
                    (b.value || b.innerText || '').trim() === 'חפש' ||
                    (b.value || b.innerText || '').trim() === 'חיפוש' ||
                    b.id?.includes('btnLocate') || b.id?.includes('btnSearch') ||
                    b.id?.includes('Search') || b.id?.includes('Locate')
                );
                if (btn) { btn.click(); return btn.id || btn.value || 'clicked'; }
                return null;
            }
        """)
        if clicked:
            log(f"    [search] לחץ על כפתור: {clicked}")
            try:
                await page.locator(".ag-row").first.wait_for(timeout=12000)
            except Exception:
                pass
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await page.wait_for_timeout(500)
            await dismiss_popup(page)
            return True
        log("    [search] לא מצאתי כפתור חיפוש", is_error=True)
    except Exception as e:
        log(f"    [search] שגיאה: {e}", is_error=True)
    return False


OLD_COURT_ID    = "PreviousCourtComboBoxVT"
OLD_CASETYPE_ID = "PreviousCaseTypeComboBoxVT"
OLD_SERIAL_ID   = "OldCaseNumberTextBoxVT"
OLD_YEAR_ID     = "OldYearTextBoxVT"


async def _select_dropdown_by_id(page, id_substr: str, want_text: str, prefix_match: bool = False) -> bool:
    """בוחר אופציה ב-select שה-id שלו מכיל id_substr, לפי טקסט מדויק/prefix/includes."""
    try:
        result = await page.evaluate(f"""
            () => {{
                const sel = document.querySelector("[id*='{id_substr}']");
                if (!sel) return {{ok: false, reason: 'select not found'}};
                const opts = [...sel.options];
                const want = '{want_text}'.trim();
                let opt;
                if ({"true" if prefix_match else "false"}) {{
                    opt = opts.find(o => o.text.split('-')[0].trim() === want);
                }}
                if (!opt) opt = opts.find(o => o.text.trim() === want);
                if (!opt) opt = opts.find(o => o.text.includes(want));
                if (!opt) return {{ok: false, reason: 'option not found', available: opts.map(o=>o.text).join('|').slice(0,400)}};
                sel.value = opt.value;
                sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                return {{ok: true, selected: opt.text}};
            }}
        """)
        if result.get("ok"):
            await page.wait_for_timeout(700)
            return True
        log(f"    [select#{id_substr}] '{want_text}': {result.get('reason')} | {result.get('available','')[:250]}", is_error=True)
    except Exception as e:
        log(f"    [select#{id_substr}] שגיאה: {e}", is_error=True)
    return False


async def _fill_input_by_id(page, id_substr: str, value: str) -> bool:
    """ממלא input שה-id שלו מכיל id_substr."""
    try:
        ok = await page.evaluate(f"""
            () => {{
                const el = document.querySelector("[id*='{id_substr}']");
                if (!el) return false;
                el.value = '{value}';
                el.dispatchEvent(new Event('input',  {{bubbles: true}}));
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return true;
            }}
        """)
        if ok:
            await page.wait_for_timeout(150)
            return True
        log(f"    [input#{id_substr}] לא נמצא", is_error=True)
    except Exception as e:
        log(f"    [input#{id_substr}] שגיאה: {e}", is_error=True)
    return False


async def fill_and_search_old_case(page, court: str, sug_tik_code: str | None,
                                    serial: str, year: str,
                                    is_supreme: bool) -> bool:
    """מלא טופס תיק ישן וחפש. אין רדיו תעבורה/בית משפט בטופס הזה — רק דרופדאונים."""
    ok = await _click_radio_by_label(page, "תיק ישן")
    if not ok:
        log("    ✗ לא הצלחתי ללחוץ על 'תיק ישן'", is_error=True)
        return False
    await page.wait_for_timeout(400)

    ok = await _select_dropdown_by_id(page, OLD_COURT_ID, court)
    if not ok:
        return False

    if not is_supreme:
        if not sug_tik_code:
            log(f"    ✗ אין קוד ידוע לסוג תיק — מדלג", is_error=True)
            return False
        ok = await _select_dropdown_by_id(page, OLD_CASETYPE_ID, sug_tik_code, prefix_match=True)
        if not ok:
            return False

    year2 = year.strip()[-2:].zfill(2)
    ok1 = await _fill_input_by_id(page, OLD_YEAR_ID, year2)
    ok2 = await _fill_input_by_id(page, OLD_SERIAL_ID, serial)
    if not ok1 or not ok2:
        return False

    return await _click_search_button(page)


async def fill_and_search_new_case(page, serial: str, month: str, year: str,
                                    is_traffic_case: bool = False) -> bool:
    """
    מלא טופס תיק חדש וחפש. אין דרופדאון ערכאה/סוג תיק בטופס הזה —
    רק רדיו בית משפט/תעבורה ושני שדות טקסט (מספר תיק, חודש-שנה).
    """
    # "תיק חדש" הוא ברירת המחדל בכל פעם שנכנסים לעמוד, אבל לוחצים בכל זאת ליתר ביטחון
    await _click_element_by_id_contains(page, RADIO_ID_HINTS["תיק חדש"])
    await page.wait_for_timeout(300)

    radio_id = NEW_TRAFFIC_RADIO_ID if is_traffic_case else NEW_COURT_RADIO_ID
    ok = await _click_element_by_id_contains(page, radio_id)
    if not ok:
        log(f"    ✗ לא הצלחתי ללחוץ על רדיו {'תעבורה' if is_traffic_case else 'בית משפט'} (תיק חדש)", is_error=True)
        return False
    await page.wait_for_timeout(300)

    month_year = f"{month.strip().zfill(2)}-{year.strip()[-2:].zfill(2)}"
    ok1 = await _fill_input_by_id(page, NEW_MONTHYEAR_ID, month_year)
    ok2 = await _fill_input_by_id(page, NEW_SERIAL_ID, serial)
    if not ok1 or not ok2:
        return False

    return await _click_search_button(page)


# ── קריאת גריד התוצאות ──────────────────────────────────────
async def get_grid_rows(page) -> list[dict]:
    """
    קורא את השורות הגלויות בגריד ומחזיר רשימת דיקטים עם:
    row_idx, date_raw, sug_hachlatah, text_full
    """
    try:
        rows = await page.evaluate("""
            () => {
                const result = [];
                document.querySelectorAll('.ag-row').forEach(row => {
                    const idx = parseInt(row.getAttribute('row-index') ?? '-1');
                    if (idx < 0) return;
                    // מנסה לאסוף עמודות לפי col-id או לפי טקסט
                    const cells = {};
                    row.querySelectorAll('.ag-cell').forEach(cell => {
                        const col = cell.getAttribute('col-id') || '';
                        cells[col] = cell.innerText.trim();
                    });
                    const fullText = row.innerText.replace(/\\n/g, ' | ').trim();
                    result.push({idx, cells, fullText});
                });
                return result;
            }
        """)
        return rows or []
    except Exception:
        return []


def extract_date_from_cell(text: str) -> str:
    """מוצא תאריך בפורמט DD/MM/YYYY מתוך טקסט."""
    m = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    return ""


def find_target_row(rows: list[dict], target_date: str, target_sug: str) -> int | None:
    """
    מוצא את ה-row_idx של השורה התואמת לתאריך ולסוג ההחלטה.
    target_date בפורמט YYYY-MM-DD.
    """
    for row in rows:
        full = row.get("fullText", "")
        cells = row.get("cells", {})

        # חיפוש סוג החלטה
        sug_found = False
        for v in cells.values():
            if target_sug in v:
                sug_found = True
                break
        if not sug_found and target_sug not in full:
            continue

        # חיפוש תאריך
        date_found = False
        for v in cells.values():
            if extract_date_from_cell(v) == target_date:
                date_found = True
                break
        if not date_found:
            # ניסיון מהטקסט המלא
            if extract_date_from_cell(full) == target_date:
                date_found = True
        if date_found:
            return row["idx"]

    return None


async def get_result_count(page) -> int:
    try:
        body = await page.locator("body").inner_text()
        m = re.search(r'מתוך\s+(\d+)', body)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    try:
        return await page.locator(".ag-row").count()
    except Exception:
        return 0


# ── הורדת DOCX (זהה לסקריפר הקיים) ─────────────────────────
async def uncheck_all(page):
    try:
        await page.evaluate("""
            () => {
                const vp = document.querySelector('.ag-body-viewport');
                if (vp) vp.scrollTop = 0;
            }
        """)
        await page.wait_for_timeout(200)
        count = await page.evaluate("""
            () => {
                const checked = [...document.querySelectorAll('input[type=checkbox]')].filter(cb =>
                    cb.checked &&
                    !cb.parentElement?.parentElement?.className.includes('ag-header-select-all')
                );
                checked.forEach(cb => {
                    cb.checked = false;
                    cb.dispatchEvent(new Event('change', {bubbles: true}));
                    cb.dispatchEvent(new Event('click',  {bubbles: true}));
                });
                return checked.length;
            }
        """)
        if count:
            log(f"      [uncheck] ביטל {count} checkboxes")
        await page.wait_for_timeout(300)
    except Exception:
        pass


async def click_checkbox(page, row_idx: int) -> bool:
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
            if (!row) return null;
            const cb = row.querySelector('input[type=checkbox]');
            if (!cb) return null;
            const r = cb.getBoundingClientRect();
            if (r.width <= 0) return null;
            return {{x: r.left + r.width/2, y: r.top + r.height/2}};
        }}
    """)
    if not pos:
        return False

    await page.mouse.click(pos["x"], pos["y"])
    await page.wait_for_timeout(600)

    checked = await page.evaluate(f"""
        () => {{
            const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
            if (!row) return false;
            const cb = row.querySelector('input[type=checkbox]');
            return cb ? cb.checked : false;
        }}
    """)
    if not checked:
        await page.mouse.click(pos["x"], pos["y"])
        await page.wait_for_timeout(600)
        checked = await page.evaluate(f"""
            () => {{
                const row = document.querySelector('.ag-row[row-index="{row_idx}"]');
                if (!row) return false;
                const cb = row.querySelector('input[type=checkbox]');
                return cb ? cb.checked : false;
            }}
        """)
    return bool(checked)


async def download_row_docx(page, row_idx: int, dest: Path) -> bool:
    """מסמן שורה לפי row_idx ומוריד DOCX."""
    await dismiss_ndc_popup(page)
    await uncheck_all(page)

    btn_info = await page.evaluate("""
        () => {
            const btn = document.getElementById('btnDownloadWordDocs');
            if (!btn) return {exists: false};
            const r = btn.getBoundingClientRect();
            return {exists: true, visible: r.width > 0 && r.height > 0};
        }
    """)
    if not btn_info.get("exists") or not btn_info.get("visible"):
        log(f"      ✗ #btnDownloadWordDocs לא זמין")
        return False

    checked = await click_checkbox(page, row_idx)
    if not checked:
        log(f"      ✗ לא הצלחתי לסמן row-index={row_idx}")
        return False

    dialog_accepted = []
    async def _accept_dialog(dlg):
        dialog_accepted.append(dlg.message)
        await dlg.accept()
    page.on("dialog", _accept_dialog)

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with page.expect_download(timeout=20000) as dl_info:
            await page.locator("#btnDownloadWordDocs").click()
            await page.wait_for_timeout(500)
            await dismiss_ndc_popup(page)
        dl = await dl_info.value
        await dl.save_as(str(dest))
        await uncheck_all(page)
        return True
    except Exception as e:
        if dialog_accepted:
            log(f"      ✗ dialog: {dialog_accepted[0]}")
        else:
            log(f"      ✗ שגיאת הורדה: {e!s:.120}")
        await dismiss_ndc_popup(page)
        await uncheck_all(page)
        return False
    finally:
        page.remove_listener("dialog", _accept_dialog)


# ── עיבוד שורה אחת ──────────────────────────────────────────
async def process_row(page, row: dict, done_dl: set[str],
                      row_num: int, total: int) -> bool:
    """מעבד שורה אחת מהמטאדאטא: חיפוש, מציאת תוצאה, הורדה."""
    case_num  = str(row.get("מספר תיק", "")).strip()
    date_raw  = str(row.get("תאריך מתן החלטה", "")).strip()
    court     = str(row.get("בית משפט", "")).strip()
    sug_tik   = str(row.get("סוג תיק", "")).strip()
    sug_hach  = str(row.get("סוג החלטה", "")).strip()

    if not case_num:
        return False

    # בדיקת פרוגרס
    pk = pkey(case_num, date_raw, sug_hach)
    if pk in done_dl:
        _state.skipped += 1
        return True

    target_date = normalize_date(date_raw)
    log(f"  [{row_num}/{total}] {case_num} | {court} | {sug_tik[:30]} | {target_date} | {sug_hach}")

    # בדיקת קובץ קיים
    dest = build_dest(case_num, date_raw, 0)
    if dest.exists():
        log(f"    ← קיים: {dest.name}")
        done_dl.add(pk)
        save_progress(PROGRESS_DL, done_dl)
        _state.skipped += 1
        return True

    # פירוש מספר תיק
    parsed = parse_case_number(case_num)
    if parsed["format"] == "mangled":
        log(f"    ✗ מספר תיק פגום (Excel): {case_num!r}", is_error=True)
        return False
    if parsed["format"] == "unknown":
        log(f"    ✗ מספר תיק לא מזוהה: {case_num!r}", is_error=True)
        return False

    is_supreme = court in SUPREME_COURT_NAMES
    sug_tik_code = None if is_supreme else SUG_TIK_MAP.get(sug_tik)
    if not is_supreme:
        if sug_tik not in SUG_TIK_MAP:
            log(f"    ✗ סוג תיק לא במיפוי: {sug_tik!r}", is_error=True)
            return False
        if sug_tik_code is None:
            log(f"    ✗ אין קוד dropdown ידוע לסוג תיק: {sug_tik!r}", is_error=True)
            return False

    await asyncio.sleep(random.uniform(1.5, 3.0))

    # מילוי טופס וחיפוש
    if parsed["format"] == "old":
        ok = await fill_and_search_old_case(
            page, court, sug_tik_code,
            parsed["serial"], parsed["year"], is_supreme,
        )
    else:
        ok = await fill_and_search_new_case(
            page, parsed["serial"], parsed["month"], parsed["year"],
            is_traffic_case=("תעבורה" in sug_tik or 'תת"ע' in sug_tik),
        )

    if not ok:
        log(f"    ✗ כישלון בחיפוש", is_error=True)
        await go_back_to_search(page)
        return False

    # קריאת תוצאות
    count = await get_result_count(page)
    if count == 0:
        log(f"    — אין תוצאות")
        _state.no_match += 1
        await go_back_to_search(page)
        return False

    log(f"    תוצאות: {count}")

    # אם יותר מ-100 — אזהרה וממשיכים (לא מטפלים בזה כרגע)
    if count >= 100:
        log(f"    ⚠ 100+ תוצאות — יתכן שהתיק לא ייטפל נכון")

    rows = await get_grid_rows(page)
    if not rows:
        log(f"    ✗ לא הצלחתי לקרוא שורות מהגריד", is_error=True)
        await go_back_to_search(page)
        return False

    target_idx = find_target_row(rows, target_date, sug_hach)
    if target_idx is None:
        log(f"    — לא נמצאה שורה תואמת ({target_date}, {sug_hach})")
        log(f"    שורות בגריד: {[r.get('fullText','')[:80] for r in rows[:5]]}")
        _state.no_match += 1
        await go_back_to_search(page)
        return False

    log(f"    נמצא: row-index={target_idx}")

    # הורדה עם טיפול בכפילות שם קובץ
    dest = build_dest(case_num, date_raw, 0)
    idx_suffix = 0
    while dest.exists():
        idx_suffix += 1
        dest = build_dest(case_num, date_raw, idx_suffix)

    success = await download_row_docx(page, target_idx, dest)
    if success:
        log(f"    ✓ הורד: {dest.name}")
        done_dl.add(pk)
        save_progress(PROGRESS_DL, done_dl)
        _state.downloaded += 1
    else:
        log(f"    ✗ כישלון בהורדה", is_error=True)

    await go_back_to_search(page)
    return success


# ── main ──────────────────────────────────────────────────────
async def main():
    prevent_sleep()
    _state.log_fh = open(LOG_FILE, "a", encoding="utf-8")
    run_start = datetime.now()
    log("=" * 60)
    log(f"scraper_by_metadata.py — {INPUT_CSV.name}")

    done_dl = load_progress(PROGRESS_DL)
    log(f"פרוגרס: {len(done_dl)} קבצים הורדו")

    # קריאת CSV וסינון לסוגי ההחלטה הרצויים
    with open(INPUT_CSV, encoding="utf-8-sig") as f:
        all_rows = list(csv.DictReader(f))

    wanted = [r for r in all_rows if r.get("סוג החלטה", "").strip() in DECISION_TYPES_WANTED]
    log(f"שורות בקובץ: {len(all_rows)} | רלוונטיות: {len(wanted)}")

    ua = random.choice(USER_AGENTS)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(accept_downloads=True, user_agent=ua)
        page = await context.new_page()

        try:
            await navigate_to_case_search(page)

            for i, row in enumerate(wanted, 1):
                try:
                    await process_row(page, row, done_dl, i, len(wanted))
                except Exception as e:
                    err = str(e)
                    transient = any(x in err for x in [
                        "Timeout", "TimeoutError", "net::", "ERR_",
                        "Target page", "context or browser", "Target crashed",
                    ])
                    log(f"  ✗ שגיאה בשורה {i}: {err:.120}", is_error=True)
                    if transient:
                        log(f"  [reconnect] מנסה לחזור לדף...")
                        try:
                            await navigate_to_case_search(page)
                        except Exception:
                            log(f"  ✗ לא הצלחתי להתחבר מחדש", is_error=True)
                            break
                    else:
                        try:
                            await go_back_to_search(page)
                        except Exception:
                            await navigate_to_case_search(page)

        except KeyboardInterrupt:
            log("\nנעצר על ידי המשתמש")
        except Exception as e:
            log(f"\nשגיאה כללית: {e}", is_error=True)
            import traceback; log(traceback.format_exc())
        finally:
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
                f"הורדו {_state.downloaded} | "
                f"דולגו {_state.skipped} | "
                f"לא נמצאו {_state.no_match} | "
                f"שגיאות {_state.errors}")
            log("=" * 60)
            if _state.log_fh:
                _state.log_fh.close()


asyncio.run(main())
