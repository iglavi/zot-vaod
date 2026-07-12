"""חילוץ טקסט ומטא-דאטה מקבצי פסקי דין.

תומך גם ב-.docx (הפורמט האמיתי מאתר נט-המשפט) וגם ב-.txt (גיבוי/בדיקות).
מחלץ מגוף המסמך פרטים שאינם קיימים בקובץ ה-CSV: שם השופט/ת ותאריך ההחלטה.
"""
from __future__ import annotations

import re
from pathlib import Path

from .config import HEB_MONTHS

_MONTHS_ALT = "|".join(HEB_MONTHS)

# "לפני כב' השופטת רוני סלע" / "לפני כבוד הרשם ..." וכד' — חלק מהמסמכים
# (כ-2,200 בפועל) משתמשים ב'בפני' במקום 'לפני'; בלעדיו judge יצא ריק
# לכולם. גם ':' אחרי לפני/בפני ('בפני: כבוד...') חייב להיות אופציונלי —
# אחרת ה-search מדלג על השורה הנכונה (הראשונה, עם השם) ותופס בטעות אזכור
# כללי מאוחר יותר בגוף ההחלטה (למשל 'יובא לפני כבוד הרשם' בלי שם). גם
# ספרה בודדת שנדבקת ל'לפני/בפני' (כ-176 מסמכים בפועל, כנראה שריד של
# הערת-שוליים/מספר עמוד שנשרך אל תוך זרימת הטקסט) חייבת להיות אופציונלית.
_JUDGE_RE = re.compile(r"[לב]פנ[יי]\s*\d*\s*:?\s*כב(?:ו?ד|['׳])?\s*(.{0,70})")
# תבנית תאריך לועזי בתוך גוף פסק הדין: "01 ינואר 2026"
_DATE_RE = re.compile(r"(\d{1,2})\s+(" + _MONTHS_ALT + r")\s+(\d{4})")
# מילים שמסמנות את סוף שם השופט/ת (תארים, תפקידי צדדים, מונחי פתיח)
_JUDGE_STOP = re.compile(
    r"העתק|פסק[\s\-]?דין|החלט|בעניין|בין\b|נגד|נ['׳]|מיום|"
    r"מבקש|משיב|עורר|מערער|תוב[ ע]|נתבע|עות[ר]|המבקש|בקשה|רקע|"
    r"ת[\"״]?א|\d|\n"
)


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _read_docx(p: Path) -> str:
    """קורא טקסט מלא מ-.docx ישירות מה-XML הגולמי (לא דרך python-docx
    document.paragraphs/tables). הכרחי כי תבניות המסמכים הרשמיים של בתי
    המשפט משתמשות ב'content controls' (שדות מילוי: שם השופט/ת, מספר
    התיק, הצדדים) שעוטפים את הפסקה כולה ב-<w:sdt><w:sdtContent>. פסקה
    כזו אינה צאצא ישיר של גוף המסמך, ולכן document.paragraphs מדלג עליה
    לגמרי — מה שגרם לשדות מטא-דאטה קריטיים לצאת ריקים כמעט תמיד."""
    import zipfile
    from lxml import etree

    with zipfile.ZipFile(str(p)) as z:
        xml = z.read("word/document.xml")
    root = etree.fromstring(xml)
    paragraphs = []
    for p_el in root.iter(f"{{{_W_NS}}}p"):
        text = "".join(t.text or "" for t in p_el.findall(f".//{{{_W_NS}}}t"))
        if text.strip():
            paragraphs.append(text)
    return "\n".join(paragraphs)


def read_text(path: str | Path) -> str:
    """קורא טקסט מלא מקובץ pdf/docx/txt. מחזיר מחרוזת ריקה במקרה כשל."""
    p = Path(path)
    suffix = p.suffix.lower()
    try:
        if suffix == ".docx":
            return _read_docx(p)
        if suffix == ".doc":
            import docx  # python-docx (לא תומך רשמית ב-.doc הישן, best-effort)

            document = docx.Document(str(p))
            parts = [para.text for para in document.paragraphs]
            return "\n".join(t for t in parts if t and t.strip())
        if suffix == ".pdf":
            return _read_pdf(p)
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


# PDF-ים עבריים ישנים (בעיקר טפסי בתי-משפט מלפני ~2015) נוצרו בפונטים
# 'ויזואליים' שאינם תומכים ב-BiDi תקני — pdfplumber/pypdf מחלצים מהם את
# התווים לפי סדר הציור על הדף (משמאל לימין), כך שכל שורה עברית יוצאת
# הפוכה לגמרי. מזהים את התופעה לפי מילת-מפתח נפוצה שמופיעה הפוכה (ולא
# במצורה הרגילה) בטקסט שחולץ, ומתקנים עם python-bidi (base_dir='R'
# משמר נכון גם רצפי מספרים/אנגלית מוטמעים, בניגוד להיפוך שורה גולמי).
_REVERSED_SIGNATURE = "טפשמה תיב"  # 'בית המשפט' הפוך
_NORMAL_SIGNATURE = "בית המשפט"


def _fix_visual_hebrew(text: str) -> str:
    if not text or _REVERSED_SIGNATURE not in text or _NORMAL_SIGNATURE in text:
        return text
    try:
        from bidi.algorithm import get_display
    except ImportError:
        return text
    return "\n".join(get_display(line, base_dir="R") for line in text.split("\n"))


def _read_pdf(p: Path) -> str:
    """מחלץ טקסט מקובץ PDF. מנסה pdfplumber (טוב יותר לעברית) ואז pypdf."""
    try:
        import pdfplumber

        with pdfplumber.open(str(p)) as pdf:
            pages = [(page.extract_text() or "") for page in pdf.pages]
        text = "\n".join(pages).strip()
        if text:
            return _fix_visual_hebrew(text)
    except Exception:
        pass
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(p))
        text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        return _fix_visual_hebrew(text)
    except Exception:
        return ""


def extract_judge(text: str) -> str:
    """מחלץ את שם השופט/ת (כולל תואר) משורת 'לפני כב\'...'."""
    if not text:
        return ""
    m = _JUDGE_RE.search(text)
    if not m:
        return ""
    seg = m.group(1)
    seg = _JUDGE_STOP.split(seg)[0]
    seg = re.sub(r"\s+", " ", seg).strip(" .,:-‏‎")
    return seg


def extract_decision_date(text: str) -> str:
    """מחלץ את תאריך ההחלטה (הלועזי) ומחזיר ISO 'YYYY-MM-DD', או ''."""
    if not text:
        return ""
    m = _DATE_RE.search(text)
    if not m:
        return ""
    day = int(m.group(1))
    month = HEB_MONTHS[m.group(2)]
    year = int(m.group(3))
    try:
        return f"{year:04d}-{month:02d}-{day:02d}"
    except Exception:
        return ""


# זיהוי כותרת פסק הדין: {בית משפט} {סוג תיק} {מספר תיק} {צדדים} לפני ...
_HEAD_RE = re.compile(
    r"(?P<ctype>[֐-׿\"״]{2,6})\s+"
    r"(?P<num>\d{2,6}[-/]\d{1,2}(?:-\d{2,4})?)"
)
# סימני-עצירה אמינים תמיד (פותחים בפועל את שורת השופט/ת או 'תיק חיצוני').
_PARTIES_STOP = re.compile(r"[לב]פנ[יי]|תיק\s+חיצוני")
# 'כבוד'/"כב'" כשלעצמו הוא סימון-עצירה חלש יותר: ארגונים בשם 'דרך כבוד'
# וכד' הכילו את המילה בשם הצד עצמו, וגרמו לקטיעה שגויה של השם. משמש רק
# כגיבוי אם לא נמצא 'לפני/בפני' תקין באותה שורה כלל.
_PARTIES_STOP_FALLBACK = re.compile(r"כב(?:ו?ד|['׳])")

# התאמה נחשבת כותרת אמיתית רק אם נמצאה קרוב לתחילת המסמך. אחרת, כנראה
# שההתאמה מקרית (איזשהו מספר בטקסט הגוף, לא מספר התיק בפועל) — וניפול
# למקרה 'לא נמצאה כותרת' (שדות ריקים) במקום למלא אותם בזבל.
_HEAD_MAX_POS = 150

# מסמכים מסוג 'מספר בקשה:N' (החלטות ביניים) לא כוללים בטקסט הגלוי שם
# בית משפט/סוג תיק/מספר תיק בפורמט הרגיל — רק את מספר הבקשה עצמה. בלי
# הזיהוי הזה, _HEAD_RE היה מוצא התאמה מקרית מאוחר יותר בטקסט ומזהם את
# כל השדות (כולל 'בית משפט') בגוש טקסט לא רלוונטי.
_BAKASHA_RE = re.compile(r"^מספר\s+בקשה\s*:?\s*\d+")

# כמעט כל סוג הליך אמיתי כולל מרכאות (ת"א, בג"ץ, חדל"פ...) — בלעדי
# הדרישה הזו, ה-ctype (2-6 תווים עבריים חופשי) תפס במקרה כל מילה קצרה
# שמופיעה במקרה ממש לפני תבנית 'מספר/מספר' כלשהי (תאריך בגוף ההחלטה,
# לרוב) — 'ליום'/'מיום'/'ביום' (תאריך), 'אזרחי'/'פלילי' (תיאור הליך),
# ואף שברי טקסט הפוך שלא תוקנו. זוהה בפועל שהתבנית הבלתי-מוגבלת יצרה
# עשרות ערכי-זבל שונים ב-case_type ובגררה אחריה גם court/case_number
# שגויים (כל הטקסט שלפני ה'התאמה' המקרית).
def _valid_ctype(ctype: str) -> bool:
    return ctype == "העליון" or bool(re.search(r"[\"'׳״]", ctype))


def _find_head_match(head: str):
    for m in _HEAD_RE.finditer(head):
        if m.start() > _HEAD_MAX_POS:
            return None
        if _valid_ctype(m.group("ctype")):
            return m
    return None


_COURT_START_RE = re.compile(r"בית\s*[-–]?\s*ה?משפט|ה?משפט\s+העליון|בג[\"'׳״]?ץ")
_SUPREME_START_RE = re.compile(r"^(בית\s*[-–]?\s*)?ה?משפט\s+העליון")
_BAGATZ_RE = re.compile(r"בג[\"'׳״]?ץ")
# שורות-זבל נפוצות שאינן שם בית משפט כלל (שם שופט/ת שנגרר, כותרות מסמך
# כלליות) — כשלא זוהתה תבנית 'בית משפט' תקינה, אלה היחידות שחוסמות את
# הערך המקורי; כל דבר אחר (למשל 'אזורי לעבודה חיפה', 'המחוזי ירושלים' —
# שמות מקוצרים של סוגי בתי דין/משפט שלא כוללים את המילה 'משפט' עצמה)
# נשמר כפי שהוא, כדי לא לאבד ערכי סינון תקינים-אך-חלקיים.
_JUNK_COURT_RE = re.compile(
    r"^(לפני|בפני)\b|^(תוכן עניינים|תאריך|תקציר|תמצית|מספר|המערער(ת)?|"
    r"תיקים מאוחדים|הודעה לתקשורת)\b"
)
# 'מחוזי חיפה' ו'בית המשפט המחוזי בחיפה' (וכנ"ל 'שלום X'/'בית משפט השלום
# בX') הם אותו בית משפט בדיוק — הצורה הקצרה מגיעה מ-CSV המקור (החלטות
# בית המשפט, לא ארכיון העליון) שמקצר לא-עקבית, ובלי איחוד הן נספרות
# ומוצגות כשני בתי משפט שונים במסנן.
_SHORT_COURT_RE = re.compile(r"^ה?(מחוזי|שלום)\s+(.+)$")
_SHORT_COURT_PREFIX = {"מחוזי": "בית המשפט המחוזי ב", "שלום": "בית משפט השלום ב"}
# 'בית משפט לתעבורה' הוא בית משפט נפרד, לא תת-מסלול של בית משפט השלום —
# חלק מהמסמכים כותבים בטעות 'בית משפט השלום לתעבורה', מה שיוצר גם כפילות
# מול הצורה הנכונה ('בית המשפט לתעבורה מחוז X').
_SHALOM_TRAFFIC_RE = re.compile(r"(בית\s*[-–]?\s*ה?משפט)\s+השלום(\s+לתעבורה)")
# שרידים שהחילוץ המקורי (_HEAD_RE, שרירת מספר-תיק גזלה את 'העליון' לתוך
# case_type — ראו extract_metadata) או טעות הקלדה בודדת במסמך המקור
# משאירים מאחור — בהקשר הזה חד-משמעית בית המשפט העליון (אין בית משפט
# ישראלי אחר בשם 'העליון' סתם, וזו טעות דפוס ברורה של 'בית המשפט העליון').
_SUPREME_EXACT_ALIASES = {"העליון", "בית המשפ העליון", "בבית המשפ העליון"}
# 'בית המשפט קמא' הוא ביטוי-הפניה גנרי לערכאה קודמת בהליך ערעור ('הערכאה
# הראשונה/הקודמת') — לא שם בית משפט ספציפי, ולעיתים נגרר אחריו טקסט
# ההפניה המלא (שם שופט/מספר תיק של הערכאה ההיא). לא ניתן לדעת מכך איזה
# בית משפט זה בפועל.
_KAMA_RE = re.compile(r"^בית\s*[-–]?\s*ה?משפט\s+קמא\b")
# תווי סוגריים שנשמרו הפוכים-כיוון (RTL) בחילוץ מ-PDF ('...)בת-ים(' במקום
# '(בת-ים)') — הכיוון הלוגי לא ידוע, אז פשוט מסירים את כל תווי הסוגריים
# ולא מנסים לשחזר איזה מהם פותח/סוגר.
_BRACKETS_RE = re.compile(r"[()\[\]{}]")


def _normalize_court(raw: str) -> str:
    """מנקה ומאחד את שם בית המשפט שחולץ מכותרת המסמך.

    מטפל בשלוש תקלות שנצפו בפועל בשדה הזה: (1) טקסט הפוך מ-PDF ישן —
    כמו ב-full_text (ראו _fix_visual_hebrew), רק שכאן המחרוזת קצרה מדי
    כדי שסימן ההיכר של _fix_visual_hebrew תמיד יופיע בה, ולכן הבדיקה
    כאן מסתמכת על היעדר 'משפט' בכיוון תקין; (2) תווי-זבל שנגררו לפני שם
    בית המשפט (סימני פיסוק, מספרי עמוד, שארית פסקה קודמת) — נחתכים על
    ידי איתור נקודת ההתחלה האמיתית של השם; (3) עשרות גרסאות שונות של
    'בית המשפט העליון' (עם/בלי 'בירושלים', 'תקציר', 'הודעה לתקשורת'
    וכו') שהופכות מסנן בית-משפט באתר לרשימה ארוכה ומבלבלת — לכל אלה יש
    רק בית משפט עליון אחד במדינה, ולכן מאוחדות לערך קנוני יחיד.
    מחזיר מחרוזת ריקה אם לא זוהה שם בית משפט תקין בכלל."""
    s = (raw or "").strip()
    if not s:
        return ""
    if s in _SUPREME_EXACT_ALIASES:
        return "בית המשפט העליון"
    if "משפט" not in s and not _BAGATZ_RE.search(s):
        try:
            from bidi.algorithm import get_display
            fixed = get_display(s, base_dir="R")
        except ImportError:
            fixed = s
        if "משפט" in fixed or _BAGATZ_RE.search(fixed):
            s = fixed
    m_short = _SHORT_COURT_RE.match(s)
    if m_short:
        kind, city = m_short.groups()
        if kind == "מחוזי" and city == "מרכז":
            # יוצא-דופן: שם המחוז ('מרכז') אינו שם עיר שמקבל 'ב' — הכינוי
            # המלא הנהוג הוא 'מחוז מרכז (לוד)', לא 'ב-מרכז'.
            s = "בית המשפט המחוזי מרכז לוד"
        else:
            s = _SHORT_COURT_PREFIX[kind] + city
    # לוקחים את ההתאמה האחרונה, לא הראשונה: לפעמים קודמת לכותרת האמיתית
    # שורת-הקדמה שמזכירה בית משפט אחר בהקשר שונה לגמרי (למשל הודעת איסור
    # פרסום 'לפי החלטת בית משפט מחוזי' לפני הכותרת האמיתית 'בבית המשפט
    # העליון') — ההתאמה הקרובה ביותר למספר התיק היא כמעט תמיד הנכונה.
    matches = list(_COURT_START_RE.finditer(s))
    if matches:
        s = s[matches[-1].start():]
        if _SUPREME_START_RE.match(s):
            return "בית המשפט העליון"
    elif _JUNK_COURT_RE.search(s) or len(s) > 40 or re.search(r"\d", s):
        return ""
    s = _SHALOM_TRAFFIC_RE.sub(r"\1\2", s)
    s = _BRACKETS_RE.sub("", s)
    s = re.sub(r"\s*[-–]\s*", " ", s)
    s = re.sub(r"\s+בהליך\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip(" '\"׳״;:.,]})|+")
    if s in ("בית המשפט", "בית משפט") or _KAMA_RE.match(s):
        # 'בית המשפט' לבדו (בלי שם/עיר/סוג), או 'בית משפט קמא' (הפניה
        # גנרית לערכאה קודמת, לא שם ספציפי) — אי אפשר לדעת מהם איזה בית
        # משפט זה בפועל.
        return ""
    return s if len(s) <= 40 and not re.search(r"\d", s) else ""


def extract_metadata(text: str) -> dict:
    """מחלץ מטא-דאטה מגוף פסק הדין (עבור קבצים ללא שורת CSV).

    מחזיר: court, case_type, case_number, parties, judge, decision_type,
    decision_date — כל שדה best-effort, מחרוזת ריקה אם לא נמצא."""
    out = {"court": "", "case_type": "", "case_number": "", "parties": "",
           "judge": "", "decision_type": "", "decision_date": ""}
    if not text:
        return out
    head = re.sub(r"\s+", " ", text.strip())[:600]

    m = None if _BAKASHA_RE.match(head) else _find_head_match(head)
    if m:
        ctype = m.group("ctype").strip()
        # 'העליון' הוא היוצא-מן-הכלל היחיד שכשיר כ-ctype בלי מרכאות (ראו
        # _valid_ctype) — כשהוא מופיע ממש לפני מספר תיק (כותרות רשם/משפט
        # ביניים מסוג 'בבית המשפט העליון 8382/07') זה חלק משם בית המשפט,
        # לא סוג ההליך, ולכן מצטרף לקטע ה-court במקום להיחשב ctype.
        if ctype == "העליון":
            court = head[:m.end("ctype")].strip(" -–:")
            ctype = ""
        else:
            court = head[:m.start()].strip(" -–:")
        out["court"] = _normalize_court(court)
        out["case_type"] = ctype
        out["case_number"] = m.group("num").strip()
        rest = head[m.end():]
        # תיקים מאוחדים/צמודים חושפים מספר-תיק שני (לפעמים גם שלישי) לפני
        # השורה עם 'לפני/בפני' — בלי לזהות אותו כסימן-עצירה נוסף, הוא היה
        # נגרר לתוך parties (או, אם ארוך מדי, גורם לדחיית השדה כולו).
        candidates = [s for s in (_PARTIES_STOP.search(rest), _find_head_match(rest)) if s]
        stop = min(candidates, key=lambda s: s.start()) if candidates else _PARTIES_STOP_FALLBACK.search(rest)
        parties = (rest[:stop.start()] if stop else rest).strip(" -–:‏‎")
        # מסננים "תיק חיצוני: 123/2025" אם נגרר
        parties = re.sub(r"תיק\s+חיצוני.*$", "", parties).strip(" -–:")
        if len(parties) <= 80:
            out["parties"] = parties

    out["judge"] = extract_judge(text)
    out["decision_date"] = extract_decision_date(text)
    if "פסק דין" in head or "פסק-דין" in head:
        out["decision_type"] = "פסק דין"
    elif "החלט" in head:
        out["decision_type"] = "החלטה"
    return out


def filed_date_from_case(case_number: str) -> str:
    """גוזר תאריך פתיחה משוער ממספר התיק (למשל 49000-12-25 -> 2025-12-01)."""
    if not case_number:
        return ""
    parts = str(case_number).strip().split("-")
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        mm, yy = int(parts[1]), parts[2]
        if 1 <= mm <= 12 and len(yy) == 2:
            return f"20{yy}-{mm:02d}-01"
    return ""
