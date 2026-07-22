"""בניית אינדקס החיפוש (SQLite + FTS5) מתוך metadata.csv ותיקיית פסקי הדין.

מריצים פעם אחת (ובכל פעם שמתווספים פסקי דין חדשים):
    python -m zot.ingest

**אינקרementלי**: אם האינדקס כבר קיים ותואם למבנה הצפוי, מוסיפים רק את
הקבצים החדשים (לפי שם קובץ) — לא קוראים מחדש קבצים שכבר אונדקסו. בנייה
מלאה-מאפס קורית רק כשאין עדיין אינדקס, או כשמבנה הטבלה השתנה (למשל
הוספת עמודה חדשה בעדכון קוד) — במקרה כזה חובה לקרוא הכול מחדש כדי
שהעמודה החדשה תתמלא גם לרשומות ישנות.
"""
from __future__ import annotations

import csv
import re
import sqlite3
import threading
import time
from pathlib import Path

from . import config, storage
from .case_types import normalize_case_type, proceeding_for_case_type
from .extract import (_normalize_court, extract_decision_date, extract_judge,
                      extract_metadata, filed_date_from_case, read_text)

# חלק מהמסמכים (במיוחד PDF פגומים/חריגים, למשל תיקיית PediVerdicts בארכיון
# העליון) גורמים ל-pdfplumber/pypdf להיתקע בפועל במקום לזרוק שגיאה — מה
# שהיה תוקע את כל תהליך האינדוקס על קובץ אחד ללא כל הודעה. timeout מוגן-
# thread (thread חדש לכל קריאה, לא pool משותף — כדי שקובץ תקוע לא יחסום
# קריאות עתידיות) מבטיח שקובץ בודד לעולם לא יעצור את כל התהליך: ה-thread
# התקוע ננטש (daemon, לא חוסם את סיום התהליך), אבל התהליך הראשי ממשיך
# הלאה מיד.
#
# נמצא בפועל: מדובר בתופעה לא-נדירה (סדר גודל 5-7% מקובצי בית המשפט
# העליון) — כנראה PDF מעוותים מבחינה מבנית (לא פשוט "קובץ גדול"; חילוץ
# טקסט רגיל מ-PDF תקין אמור להיות מהיר גם בקבצים גדולים). 30s לקובץ,
# כפול אלפי מקרים, הופך לבזבוז מצטבר של ימים שלמים. הורדנו ל-10s: עדיין
# שוליים נדיבים לחילוץ לגיטימי איטי, אבל חוסך פי-3 מהזמן שמתבזבז על
# קבצים תקועים בפועל.
_READ_TIMEOUT_SEC = 10

# תיקיית PediVerdicts (ארכיון כרכי "פסקי דין" המודפסים של העליון) מכילה,
# לצד קובצי ההחלטות הבודדות, גם קובצי-מנהלה לכל כרך/חלק: דף שער/קולופון
# (סיומת _P — רשימת שופטים, שר המשפטים וכו') ותוכן עניינים (_T) — לשניהם
# יש טקסט קריא (has_document=1 היה יוצא נכון) אך הם אינם פסק דין או
# החלטה כלל, ולכן אסור שיחזרו כתוצאת חיפוש/ספירה. זוהה בפועל: 38 קבצים
# כאלה סופקו כ'תשובה' לשאלת AI על מספר החלטות העליון במאגר.
_PEDI_ADMIN_RE = re.compile(r"PediVerdicts[/\\].*S[A-Z]\d_[PT]\.pdf\.pdf$", re.IGNORECASE)


def _read_text_with_timeout(path: Path) -> str:
    result: list[str] = []

    def _worker():
        result.append(read_text(path))

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=_READ_TIMEOUT_SEC)
    if t.is_alive():
        print(f"  אזהרה: קריאת {path} לקחה מעל {_READ_TIMEOUT_SEC}s — מדלג (ננטש ברקע).")
        return ""
    return result[0] if result else ""

# עדיפות סיומות כשקיימים כמה קבצים לאותו פסק דין (docx נותן טקסט נקי יותר מ-PDF)
_EXT_PRIORITY = {".docx": 0, ".doc": 1, ".txt": 2, ".pdf": 3}
_DATE_DIR_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")

# מבצעים commit תקופתי (לא רק בסוף כל הריצה) — כדי שאם התהליך נעצר/נהרג
# באמצע ריצה ארוכה, העבודה שכבר בוצעה לא תלך לאיבוד: ההרצה הבאה תמשיך
# בדיוק מאיפה שהאחרונה נעצרה, במקום להתחיל את כל הקבצים החדשים מחדש.
_COMMIT_EVERY = 500

# מיפוי כותרות ה-CSV (בעברית) לשמות עמודות באנגלית
COLUMN_ALIASES = {
    "court": ["בית משפט"],
    "proceeding": ["הליך"],
    "case_type": ["סוג תיק"],
    "matter": ["סוג עניין"],
    "case_number": ["מספר תיק"],
    "parties": ["שם תיק"],
    "decision_type": ["סוג החלטה"],
    "decision_nature": ["אופי החלטה"],
    "meta_date": ["תאריך"],
    "file_path": ["file_path", "נתיב"],
}

# סדר העמודות ב-verdicts (בלי id, שהוא PK אוטומטי) — משמש גם ליצירת הטבלה
# וגם לבדיקת התאמת-מבנה (כדי לדעת אם צריך בנייה מלאה מחדש).
_VERDICT_COLUMNS = [
    "case_number", "parties", "court", "proceeding", "case_type", "matter",
    "decision_type", "decision_nature", "filed_date", "decision_date", "judge",
    "filename", "file_relpath", "file_relpath_pdf", "file_relpath_docx",
    "has_document", "structural_summary", "text_length", "is_supreme",
]

# הטקסט המלא עצמו (full_text) לא נשמר בטבלת verdicts - הוא מועלה בנפרד ל-R2
# (ראו zot/storage.py: upload_fulltext/upload_fulltexts) ונשלף משם בעת
# הצורך בלבד. text_length (אורך הטקסט בתווים) כן נשמר כאן - עמודה קטנה
# שמאפשרת למיין לפי 'הכי ארוך'/'רלוונטיות' (ראו zot/search.py) בלי לגרור
# את הטקסט המלא לכל שאילתת מיון.
SCHEMA = """
CREATE TABLE verdicts (
    id INTEGER PRIMARY KEY,
    case_number TEXT,
    parties TEXT,
    court TEXT,
    proceeding TEXT,
    case_type TEXT,
    matter TEXT,
    decision_type TEXT,
    decision_nature TEXT,
    filed_date TEXT,
    decision_date TEXT,
    judge TEXT,
    filename TEXT,
    file_relpath TEXT,
    file_relpath_pdf TEXT,
    file_relpath_docx TEXT,
    has_document INTEGER DEFAULT 0,
    structural_summary TEXT,
    text_length INTEGER DEFAULT 0,
    is_supreme INTEGER NOT NULL DEFAULT 0
);
CREATE VIRTUAL TABLE verdicts_fts USING fts5(
    parties, judge, court, case_number, matter, decision_type, full_text,
    content='',
    tokenize='unicode61 remove_diacritics 2'
);
"""

# בלי אינדקסים, כל שאילתה על עמודה שאינה id (למשל DISTINCT court, מיון
# לפי תאריך, סינון has_document/proceeding) היא סריקה מלאה על 630K+ שורות
# עם full_text ענק inline — שניות שלמות לכל אינטראקציה באתר. נבדק בפועל:
# distinct_courts ירד מ-1.15s ל-12ms אחרי הוספת האינדקסים האלה. אינדקסים
# חלקיים (WHERE court != '') לא עבדו באופן עקבי (ה-query planner לא תמיד
# זיהה שהם רלוונטיים לשאילתת שוויון) — לכן אינדקסים מלאים על העמודה כולה.
# IF NOT EXISTS כי זה רץ גם בנתיב האינקרementלי (לא רק בבנייה מלאה מחדש).
INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_verdicts_court ON verdicts(court);
CREATE INDEX IF NOT EXISTS idx_verdicts_proceeding ON verdicts(proceeding);
CREATE INDEX IF NOT EXISTS idx_verdicts_has_document ON verdicts(has_document);
CREATE INDEX IF NOT EXISTS idx_verdicts_effdate ON verdicts(COALESCE(NULLIF(decision_date,''), filed_date));
CREATE INDEX IF NOT EXISTS idx_verdicts_hasdoc_effdate ON verdicts(has_document, COALESCE(NULLIF(decision_date,''), filed_date));
CREATE INDEX IF NOT EXISTS idx_verdicts_relpath ON verdicts(file_relpath);
CREATE INDEX IF NOT EXISTS idx_verdicts_decision_type ON verdicts(decision_type);
CREATE INDEX IF NOT EXISTS idx_verdicts_case_type ON verdicts(case_type);
CREATE INDEX IF NOT EXISTS idx_verdicts_is_supreme ON verdicts(is_supreme);
-- מיון ברירת המחדל ('רלוונטיות', ראו search._RELEVANCE_TYPE_CASE) וגם
-- 'לפי אורך טקסט' דורשים מיון על-פני כל הטבלה בלי אינדקס תואם - במיוחד
-- חמור מול Turso (אין ANALYZE, ראו README.md): נמדד בפועל 4.4 שניות
-- וסריקה כפולה (~1.35M שורות) עבור עמוד תוצאות ראשון בודד. עם האינדקסים
-- האלה: 8ms. אינדקס-ביטוי (CASE בתוך CREATE INDEX) - נתמך גם ב-Turso.
CREATE INDEX IF NOT EXISTS idx_verdicts_relevance ON verdicts(
    has_document,
    (CASE WHEN decision_type IN ('פסק דין', 'גזר דין', 'הכרעת דין') THEN 0 ELSE 1 END),
    text_length DESC, id DESC
);
CREATE INDEX IF NOT EXISTS idx_verdicts_hasdoc_textlen ON verdicts(has_document, text_length DESC, id DESC);
"""

# מטמון קבוע לסיכומי AI — לא נמחק בכל בנייה (בין אם מלאה או אינקרementלית),
# כך שסיכום שכבר חושב לא מחושב שוב (וממילא לא משלם עליו שוב) בהרצות הבאות.
CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ai_summaries (
    stem TEXT PRIMARY KEY,
    structural_summary TEXT,
    created_at TEXT
);
"""


def _resolve_columns(header: list[str]) -> dict[str, str]:
    """מוצא לכל שדה לוגי את שם העמודה בפועל ב-CSV."""
    clean = {h.strip(): h for h in header}
    resolved: dict[str, str] = {}
    for logical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in clean:
                resolved[logical] = clean[alias]
                break
    return resolved


def _index_by_ext(docs_dir: Path) -> dict[str, dict[str, Path]]:
    """ממפה 'שם קובץ ללא סיומת' -> {סיומת: נתיב}, לכל הסיומות שנמצאו לאותו
    שם (docx/pdf/וכו') — כך שאפשר גם לבחור את הגרסה הכי טובה לטקסט וגם
    להציג קישורי הורדה נפרדים לכל סיומת. סורק גם תת-תיקיות (כמו תיקיות
    התאריך שיוצר סקריפט ההורדה)."""
    index: dict[str, dict[str, Path]] = {}
    if not docs_dir.exists():
        return index
    for f in docs_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in _EXT_PRIORITY:
            index.setdefault(f.stem, {})[f.suffix.lower()] = f
    return index


def _best_doc(exts: dict[str, Path]) -> Path | None:
    """בוחר את הקובץ הכי מתאים לחילוץ טקסט מתוך כל הסיומות שנמצאו לאותו שם."""
    if not exts:
        return None
    return min(exts.items(), key=lambda kv: _EXT_PRIORITY[kv[0]])[1]


def _read_best_text(exts: dict) -> tuple[str, Path | None]:
    """מנסה לחלץ טקסט מהקובץ המועדף (docx בד"כ), ואם זה נכשל (מחזיר ריק)
    — עובר לנסות את שאר הסיומות הזמינות לפי סדר עדיפות, לפני שמוותרים.

    נמצא בפועל: חלק מארכיון בית המשפט העליון ('HebrewVerdicts') מכיל
    קבצים עם סיומת .docx שהם בפועל לא OOXML תקין (כנראה .doc ישן ששונה
    שמו) — python-docx נכשל בשקט ומחזיר טקסט ריק, בעוד ה-PDF המקביל של
    אותו מסמך תקין לגמרי. בלי הנפילה-חזרה הזו, אלפי מסמכים כאלה היו
    מדולגים לחלוטין (has_document=0) למרות שיש להם טקסט קריא בפורמט אחר."""
    for _ext, path in sorted(exts.items(), key=lambda kv: _EXT_PRIORITY[kv[0]]):
        text = _read_text_with_timeout(path)
        if text:
            return text, path
    return "", _best_doc(exts)


def _dir_date(path: Path) -> str:
    """מחזיר תאריך ISO משם תיקיית-האב אם הוא **בדיוק** בפורמט YYYY-M-D (תיקיות
    ההורדה היומית של decisions.court.gov.il). fullmatch (לא match) חשוב:
    תיקיות בית המשפט העליון נקראות למשל '2024-10-1648-1-1' — עם match
    בלבד זה היה מזוהה בטעות כתאריך 2024-10-1648 (יום לא תקין)."""
    m = _DATE_DIR_RE.fullmatch(path.parent.name)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return f"{y:04d}-{mo:02d}-{d:02d}"
        except Exception:
            return ""
    return ""


def _schema_matches(conn: sqlite3.Connection) -> bool:
    """בודק אם טבלת verdicts כבר קיימת עם בדיוק העמודות הצפויות. אם לא
    (הטבלה לא קיימת, או שמבנה הקוד השתנה מאז הבנייה האחרונה) — צריך
    בנייה מלאה מחדש, לא ניתן להסתפק בהוספה אינקרementלית."""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(verdicts)").fetchall()]
    if not cols:
        return False
    return cols == ["id"] + _VERDICT_COLUMNS


def _insert_verdict(conn: sqlite3.Connection, values: dict) -> int:
    """מכניס רשומה אחת ל-verdicts (בלי טקסט מלא - רק text_length, ראו SCHEMA)
    וגם, עם אותו rowid, לאינדקס הטקסט המלא (verdicts_fts, contentless) —
    כך שאין צורך ב'rebuild' גורף בסיום, גם כשמוסיפים רשומות בודדות
    אינקרementלית. הטקסט המלא עצמו (values['full_text']) לא נשמר כאן -
    הקורא אחראי להעלות אותו ל-R2 (ראו build(): pending_uploads) עם ה-rowid
    שמוחזר, במקביל ולא בתוך הטרנזקציה הזו - כדי שהעלאה איטית/כושלת לרשת
    לא תאט את קצב הכתיבה ל-DB המקומי."""
    full_text = values.get("full_text", "")
    row_values = dict(values)
    row_values["text_length"] = len(full_text)
    # proceeding ('סוג הליך') מגיע רק מעמודת ה-CSV המקורית - ריק כמעט
    # תמיד עבור מסמכים שלא כוסו בה (הורדות יומיות, ארכיון העליון). ממלאים
    # אותו מ-case_type כשידוע מיפוי אמין (ראו case_types.py:
    # PROCEEDING_BY_CASE_TYPE) - לא דורסים ערך אמיתי שכבר קיים.
    if not row_values.get("proceeding"):
        row_values["proceeding"] = proceeding_for_case_type(row_values.get("case_type", ""))
    # is_supreme: תיוג ודאי-ככל האפשר של 'ארכיון העליון' (ראו zot/search.py:
    # _SUPREME_PATH_COND להסבר המלא) - נתיב קובץ שמתחיל ב-supreme/ (הארכיון
    # ההיסטורי הנפרד) *או* שדה court מלא ('בית המשפט העליון', מגיע מההורדה
    # היומית הרגילה - court עשוי גם להישאר ריק, לכן זה תנאי OR ולא תחליף
    # לבדיקת הנתיב). מחושב פעם אחת כאן ולא ב-runtime בכל שאילתה, עם אינדקס.
    row_values["is_supreme"] = 1 if (
        (row_values.get("file_relpath") or "").startswith("supreme/")
        or (row_values.get("file_relpath_pdf") or "").startswith("supreme/")
        or (row_values.get("file_relpath_docx") or "").startswith("supreme/")
        or "עליון" in (row_values.get("court") or "")
    ) else 0
    placeholders = ",".join("?" * len(_VERDICT_COLUMNS))
    cur = conn.execute(
        f"INSERT INTO verdicts ({','.join(_VERDICT_COLUMNS)}) VALUES ({placeholders})",
        [row_values[c] for c in _VERDICT_COLUMNS],
    )
    rowid = cur.lastrowid
    conn.execute(
        """INSERT INTO verdicts_fts(rowid, parties, judge, court, case_number,
           matter, decision_type, full_text) VALUES (?,?,?,?,?,?,?,?)""",
        (rowid, values["parties"], values["judge"], values["court"],
         values["case_number"], values["matter"], values["decision_type"],
         full_text),
    )
    return rowid


def build(metadata_path: Path | None = None, docs_dir: Path | None = None,
          db_path: Path | None = None, verbose: bool = True,
          extra_sources: list[tuple[Path, str]] | None = None,
          docs_prefix: str = "") -> dict:
    """extra_sources: מקורות מסמכים נוספים מעבר לארכיון הראשי (decisions.
    court.gov.il) — למשל בית המשפט העליון. כל איבר הוא (תיקיית-מקור,
    תחילית-מפתח-R2), כדי שקישורי ההורדה (file_relpath_pdf/docx) יצביעו
    לקובץ הנכון בדלי (שם כל מקור מועלה תחת תחילית משלו — ראו zot.storage).

    docs_prefix: אותו רעיון, אבל עבור המקור הראשי (docs_dir) עצמו - נדרש
    כשקוראים ל-build() בנפרד עם docs_dir שאינו config.DOCS_DIR (למשל ארכיון
    היסטורי נוסף שמקבל תחילית-R2 משלו, ראו _ingest_nethamishpat.py)."""
    metadata_path = Path(metadata_path or config.METADATA_PATH)
    docs_dir = Path(docs_dir or config.DOCS_DIR)
    db_path = Path(db_path or config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    extra_sources = extra_sources or []

    conn = sqlite3.connect(str(db_path))
    conn.executescript(CACHE_SCHEMA)
    summary_cache = dict(conn.execute("SELECT stem, structural_summary FROM ai_summaries").fetchall())

    def _log(msg: str) -> None:
        if verbose:
            print(msg, flush=True)

    # מסמכים שנוספו מאז ה-flush האחרון וטרם הועלו ל-R2 (ראו _insert_verdict:
    # ההעלאה עצמה קורית כאן, לא בתוך הטרנזקציה של ה-INSERT, כדי שרשת
    # איטית/כושלת לא תאט את קצב הכתיבה ל-DB המקומי). מועלים במקביל
    # (ThreadPoolExecutor, ראו storage.upload_fulltexts) בכל נקודת commit —
    # כך שגם אם התהליך נעצר באמצע, מה שכבר הועלה תואם את מה ש-commit-ה.
    pending_uploads: list[tuple[int, str]] = []

    def _flush_uploads() -> None:
        if pending_uploads:
            storage.upload_fulltexts(pending_uploads)
            pending_uploads.clear()

    incremental = _schema_matches(conn)
    if incremental:
        _log("שולף רשימת קבצים כבר-מאונדקסים (existing_stems)...")
        existing_stems = {r[0] for r in conn.execute("SELECT filename FROM verdicts").fetchall()}
        _log(f"אינדקס קיים ותואם מבנה — מוסיף רק קבצים חדשים "
             f"({len(existing_stems)} כבר מאונדקסים).")
    else:
        conn.execute("DROP TABLE IF EXISTS verdicts")
        conn.execute("DROP TABLE IF EXISTS verdicts_fts")
        conn.executescript(SCHEMA)
        existing_stems = set()
        _log("אין אינדקס תואם (ראשון, או שמבנה הקוד השתנה) — בונה הכול מחדש.")

    conn.executescript(INDEX_SCHEMA)

    _log(f"סורק את תיקיית המקור הראשית ({docs_dir})...")
    by_ext = _index_by_ext(docs_dir)
    _log(f"נמצאו {len(by_ext)} שמות-קבצים ייחודיים במקור הראשי.")

    def _relpaths(stem: str) -> tuple[str, str]:
        exts = by_ext.get(stem, {})
        pdf = exts.get(".pdf")
        docx = exts.get(".docx") or exts.get(".doc")
        return (docs_prefix + pdf.relative_to(docs_dir).as_posix() if pdf else "",
                docs_prefix + docx.relative_to(docs_dir).as_posix() if docx else "")

    # מקורות נוספים (כמו בית המשפט העליון): stem -> (תיקיית-מקור,
    # תחילית-R2, {סיומת: נתיב}). המקור הראשי מטופל בנפרד למעלה (גם
    # ל-CSV וגם לתאריך-מתיקייה), אז כאן רק המקורות הנוספים.
    extra_by_source = []
    for src_dir, prefix in extra_sources:
        _log(f"סורק מקור נוסף ({src_dir})...")
        src_map = _index_by_ext(src_dir)
        _log(f"נמצאו {len(src_map)} שמות-קבצים ייחודיים במקור {src_dir}.")
        extra_by_source.append((src_dir, prefix, src_map))

    def _relpaths_extra(src_dir: Path, prefix: str, exts: dict) -> tuple[str, str]:
        pdf = exts.get(".pdf")
        docx = exts.get(".docx") or exts.get(".doc")
        return (prefix + pdf.relative_to(src_dir).as_posix() if pdf else "",
                prefix + docx.relative_to(src_dir).as_posix() if docx else "")

    rows_inserted = 0
    docs_matched = 0
    covered_stems: set[str] = set()

    # קובץ ה-CSV אופציונלי: אם אינו קיים, בונים את המאגר מהמסמכים בלבד.
    if metadata_path.exists():
      with metadata_path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        cols = _resolve_columns(header)
        idx = {logical: header.index(actual) for logical, actual in cols.items()}

        def cell(row, logical):
            i = idx.get(logical)
            if i is None or i >= len(row):
                return ""
            return (row[i] or "").strip()

        for row in reader:
            if not row or not any(row):
                continue
            case_number = cell(row, "case_number")
            file_path = cell(row, "file_path")
            stem = Path(file_path.replace("\\", "/")).stem if file_path else ""

            if stem in covered_stems:
                continue
            covered_stems.add(stem)
            if stem in existing_stems:
                continue

            full_text, doc = _read_best_text(by_ext.get(stem, {}))
            judge = ""
            decision_date = ""
            has_doc = 0
            file_relpath = ""
            if doc is not None:
                file_relpath = doc.relative_to(docs_dir).as_posix()
                if full_text:
                    has_doc = 1
                    docs_matched += 1
                    judge = extract_judge(full_text)
                    decision_date = extract_decision_date(full_text)

            filed = cell(row, "meta_date") or filed_date_from_case(case_number)
            relpath_pdf, relpath_docx = _relpaths(stem)

            rowid = _insert_verdict(conn, {
                "case_number": case_number, "parties": cell(row, "parties"),
                "court": _normalize_court(cell(row, "court")), "proceeding": cell(row, "proceeding"),
                "case_type": normalize_case_type(cell(row, "case_type")), "matter": cell(row, "matter"),
                "decision_type": cell(row, "decision_type"),
                "decision_nature": cell(row, "decision_nature"),
                "filed_date": filed, "decision_date": decision_date, "judge": judge,
                "filename": stem, "file_relpath": file_relpath,
                "file_relpath_pdf": relpath_pdf, "file_relpath_docx": relpath_docx,
                "has_document": has_doc, "full_text": full_text,
                "structural_summary": summary_cache.get(stem, ""),
            })
            if full_text:
                pending_uploads.append((rowid, full_text))
            rows_inserted += 1
            if rows_inserted % _COMMIT_EVERY == 0:
                conn.commit()
                _flush_uploads()

    def _ingest_plain(stem: str, base_dir: Path, exts: dict, file_relpath_prefix: str,
                      relpath_pdf: str, relpath_docx: str) -> bool:
        """מחלץ מטא-דאטה מגוף המסמך ומכניס רשומה, עבור קובץ שאינו מכוסה
        ב-CSV (הורדות יומיות/בית המשפט העליון). מחזיר True אם הוכנס.

        מנסה את כל הסיומות הזמינות (לא רק את המועדפת) — ראו _read_best_text.

        חשוב: גם כשחילוץ הטקסט נכשל לגמרי (has_document=0) חייבים להכניס
        שורה (ולא רק לוותר) — אחרת ה-stem לא נכנס ל-existing_stems, וכל
        ריצה עתידית (כל 10 דקות, ללא הגבלת זמן) תנסה לקרוא את אותו קובץ
        התקוע מחדש שוב ושוב, לנצח. נמצא בפועל: כמה עשרות קובצי PDF גדולים
        וכבדים בארכיון העליון (למשל PediVerdicts) גורמים ל-timeout של 30s
        בכל ניסיון — בלי השורה הזו כל ריצה הייתה מבזבזת דקות ארוכות על
        אותם קבצים בדיוק בלי שום התקדמות."""
        nonlocal rows_inserted, docs_matched
        full_text, path = _read_best_text(exts)
        if path is None:
            return False
        md = extract_metadata(full_text) if full_text else {
            "case_number": "", "parties": "", "court": "", "case_type": "",
            "decision_type": "", "decision_date": "", "judge": "",
        }
        filed = _dir_date(path) or filed_date_from_case(md["case_number"])
        file_relpath = file_relpath_prefix + path.relative_to(base_dir).as_posix()
        rowid = _insert_verdict(conn, {
            "case_number": md["case_number"], "parties": md["parties"],
            "court": md["court"], "proceeding": "", "case_type": md["case_type"],
            "matter": "", "decision_type": md["decision_type"], "decision_nature": "",
            "filed_date": filed, "decision_date": md["decision_date"],
            "judge": md["judge"], "filename": stem, "file_relpath": file_relpath,
            "file_relpath_pdf": relpath_pdf, "file_relpath_docx": relpath_docx,
            "has_document": 0 if _PEDI_ADMIN_RE.search(file_relpath) else (1 if full_text else 0),
            "full_text": full_text,
            "structural_summary": summary_cache.get(stem, ""),
        })
        if full_text:
            pending_uploads.append((rowid, full_text))
        rows_inserted += 1
        if full_text:
            docs_matched += 1
        if rows_inserted % _COMMIT_EVERY == 0:
            conn.commit()
            _flush_uploads()
        return True

    # ===== קבצים שאינם ב-CSV (למשל הורדות יומיות בשמות hash) =====
    # מחלצים את המטא-דאטה ישירות מגוף פסק הדין ומוסיפים אותם למאגר.
    # heartbeat מבוסס-זמן (לא רק כל 20000 קבצים) — כדי שהפסקה שקטה בין
    # checkpoints (למשל תיקייה עם פחות מ-20000 קבצים נותרים) לא תיראה
    # כתקיעה כשבודקים את הלוג; מדפיס גם את השם הנוכחי לצורך אבחון.
    _HEARTBEAT_SEC = 60
    _scanned = 0
    _last_heartbeat = time.monotonic()
    for stem, exts in by_ext.items():
        _scanned += 1
        _now = time.monotonic()
        if verbose and (_scanned % 20000 == 0 or _now - _last_heartbeat >= _HEARTBEAT_SEC):
            _log(f"  ...נסרקו {_scanned} קבצים במקור הראשי (מתוכם {rows_inserted} חדשים) — נוכחי: {stem}")
            _last_heartbeat = _now
        if stem in covered_stems or stem in existing_stems:
            continue
        relpath_pdf, relpath_docx = _relpaths(stem)
        _ingest_plain(stem, docs_dir, exts, "", relpath_pdf, relpath_docx)

    # ===== מקורות נוספים (בית המשפט העליון וכד') =====
    documents_found = len(by_ext)
    for src_dir, prefix, src_by_ext in extra_by_source:
        documents_found += len(src_by_ext)
        _scanned = 0
        _last_heartbeat = time.monotonic()
        for stem, exts in src_by_ext.items():
            _scanned += 1
            _now = time.monotonic()
            if verbose and (_scanned % 20000 == 0 or _now - _last_heartbeat >= _HEARTBEAT_SEC):
                _log(f"  ...נסרקו {_scanned} קבצים במקור {src_dir} (מתוכם {rows_inserted} חדשים סה\"כ) — נוכחי: {stem}")
                _last_heartbeat = _now
            if stem in covered_stems or stem in existing_stems:
                continue
            relpath_pdf, relpath_docx = _relpaths_extra(src_dir, prefix, exts)
            _ingest_plain(stem, src_dir, exts, prefix, relpath_pdf, relpath_docx)

    conn.commit()
    _flush_uploads()
    total_rows = conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    conn.close()

    stats = {"rows": rows_inserted, "documents_matched": docs_matched,
             "documents_found": documents_found, "total_rows": total_rows}
    if verbose:
        verb = "נוספו" if incremental else "נבנה אינדקס:"
        print(f"{verb} {rows_inserted} רשומות חדשות "
              f"({docs_matched} מתוכן עם טקסט פסק דין מלא). "
              f"סה\"כ במאגר כעת: {total_rows}. DB: {db_path}")
    return stats


if __name__ == "__main__":
    # חובה להעביר extra_sources גם כאן: בלעדיו, הרצה ישירה של המודול
    # (כפי שמתועד למעלה: "python -m zot.ingest") מדלגת בשקט על כל ארכיון
    # בית המשפט העליון — נתגלה בפועל אחרי שקריאה כזו לא הוסיפה קבצי עליון
    # שהורדו זה עתה, בניגוד ל-ingest_loop.py ו-fetch_daily.py ששני אלה
    # כן מעבירים את הפרמטר.
    SUPREME_DOCS_DIR = Path(__file__).resolve().parent.parent / "documents_supreme"
    build(extra_sources=[(SUPREME_DOCS_DIR, "supreme/")])
