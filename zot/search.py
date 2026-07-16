"""שאילתות חיפוש מול אינדקס ה-SQLite: חיפוש רגיל (שדות) וחיפוש טקסט מלא."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import config

_FIELDS = ("id", "case_number", "parties", "court", "proceeding", "case_type",
           "matter", "decision_type", "decision_nature", "filed_date",
           "decision_date", "judge", "filename", "file_relpath",
           "file_relpath_pdf", "file_relpath_docx", "has_document")


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    if not path.exists():
        raise FileNotFoundError(f"האינדקס לא נבנה עדיין: {path}")
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def db_exists(db_path: Path | None = None) -> bool:
    return Path(db_path or config.DB_PATH).exists()


_TOKEN_RE = re.compile(r"[\w֐-׿]+", flags=re.UNICODE)

# מצבי התאמה לחיפוש חופשי בטקסט:
#   any    — כל מילה בנפרד, מחוברות ב-OR (הכי סלחני, ברירת המחדל)
#   exact  — הביטוי המדויק כמחרוזת אחת (FTS5 phrase query)
#   near   — המילים קרובות זו לזו בטקסט (FTS5 NEAR, מרחק 6 מילים)
MATCH_MODES = ("any", "exact", "near")

SORT_OPTIONS = ("relevance", "newest", "oldest", "longest")


def _fts_query(text: str, mode: str = "any") -> str:
    """הופך טקסט חופשי לביטוי FTS5 בטוח, לפי מצב ההתאמה שנבחר."""
    tokens = [t for t in _TOKEN_RE.findall(text or "") if len(t) >= 2]
    if not tokens:
        return ""
    if mode == "exact":
        return '"' + " ".join(tokens) + '"'
    if mode == "near":
        if len(tokens) < 2:
            return f'"{tokens[0]}"'
        quoted = " ".join(f'"{t}"' for t in tokens)
        return f"NEAR({quoted}, 6)"
    return " OR ".join(f'"{t}"' for t in tokens)


# מיון 'רלוונטיות' (ברירת המחדל): פסק דין/גזר דין/הכרעת דין (תוכן מהותי)
# לפני החלטה סתמית, ואז טקסט ארוך לפני קצר — בהנחה שרוב המשתמשים מחפשים
# פסקי דין משמעותיים ולא החלטות ביניים קצרות. כשיש גם חיפוש חופשי בטקסט,
# איכות ההתאמה (bm25, ראו _order_sql) קודמת לזה — ראו שם למה.
_RELEVANCE_TYPE_CASE = (
    "CASE WHEN verdicts.decision_type IN ('פסק דין', 'גזר דין', 'הכרעת דין') "
    "THEN 0 ELSE 1 END"
)

_SORT_SQL = {
    "relevance": f"{_RELEVANCE_TYPE_CASE}, length(verdicts.full_text) DESC, verdicts.id DESC",
    "newest": "COALESCE(NULLIF(verdicts.decision_date,''), verdicts.filed_date) DESC, verdicts.id DESC",
    "oldest": "COALESCE(NULLIF(verdicts.decision_date,''), verdicts.filed_date) ASC, verdicts.id ASC",
    "longest": "length(verdicts.full_text) DESC, verdicts.id DESC",
}


def _order_sql(sort: str, use_bm25: bool) -> str:
    """בונה את ביטוי ה-ORDER BY. כשיש גם חיפוש חופשי בטקסט וגם מיון
    לפי 'רלוונטיות', bm25 (איכות ההתאמה למילות החיפוש) קודם לסוג
    המסמך/אורך הטקסט — מי שהקליד מילות חיפוש כנראה מתעניין בהתאמה
    הטובה ביותר להן, לא רק ב'פסק דין ארוך כלשהו'."""
    base = _SORT_SQL.get(sort, _SORT_SQL["relevance"])
    if use_bm25 and sort == "relevance":
        return f"bm25(verdicts_fts), {base}"
    return base

# מפצל את השדה הטקסטואלי-מלא court (המשמש להצגה, ולא משתנה) לשני ממדי
# סינון נפרדים — סוג ("ערכאה") ועיר/מחוז ("יישוב") — התואמים למבנה
# הסינון של נבו (nevo.co.il): שם בית המשפט לבדו מערבב "מהו בית המשפט"
# עם "היכן הוא" לתפריט סינון אחד מבלבל. לא שדה DB נפרד: נגזר מ-court
# בזמן שאילתה, כך שתיקון עתידי יחיד ב-_normalize_court (ראו extract.py)
# ממשיך להזין את שני הממדים בלי סנכרון כפול. הסדר קובע: תבניות ספציפיות
# יותר (כמו 'לעניינים מנהליים') חייבות להיבדק *לפני* תבניות כלליות יותר
# שעלולות להתאים חלקית לאותה מחרוזת.
_COURT_TYPE_PATTERNS = [
    ("עליון", re.compile(r"^בית\s*[-–]?\s*ה?משפט\s+העליון$")),
    ("מחוזי", re.compile(r"^בית\s*[-–]?\s*ה?משפט\s+המחוזי\s+ב?(.+)$")),
    ("עבודה", re.compile(r"^בית\s*[-–]?\s*ה?דין\s+ה?(?:אזורי|ארצי)\s+לעבודה\s*(.*)$")),
    ("תעבורה", re.compile(r"^בית\s*[-–]?\s*ה?משפט\s+לתעבורה\s+(?:במחוז\s+|מחוז\s+|ב)(.+)$")),
    ("מנהלי", re.compile(r"^בית\s*[-–]?\s*ה?משפט\s+לעניינים\s+מ[יי]?נהליים\s+ב(.+)$")),
    ("משפחה", re.compile(r"^בית\s*[-–]?\s*ה?משפט\s+לענייני\s+משפחה\s+ב(.+)$")),
    ("עניינים מקומיים", re.compile(r"^בית\s*[-–]?\s*ה?משפט\s+לעניינים\s+מקומיים\s+ב(.+)$")),
    ("תביעות קטנות", re.compile(r"^בית\s*[-–]?\s*ה?משפט\s+לתביעות\s+קטנות\s+ב(.+)$")),
    ("שלום", re.compile(r"^בית\s*[-–]?\s*ה?משפט\s+השלום\s+ב(.+)$")),
    ("בית הדין לענייני מים", re.compile(r"^בית\s+הדין\s+לענייני\s+מים\s+ב(.+)$")),
    ("בית המשפט לימאות", re.compile(r"^בית\s+המשפט\s+לימאות\s+ב(.+)$")),
    ("בית דין לשכירות", re.compile(r"^בית\s+דין\s+לשכירות\s+ב(.+)$")),
]


def split_court(court: str) -> tuple[str, str]:
    """מפצל שם בית משפט קנוני (court) ל(סוג, עיר/מחוז). מוסדות ייחודיים
    בודדים שאין להם עוד דוגמה במאגר (ועדות ערר, צבאי מנהלי וכד') מוחזרים
    כמו שהם כ'סוג' בלי עיר — הכינוי המלא שלהם הוא-הוא הסוג היחיד שלהם."""
    s = (court or "").strip()
    if not s:
        return "", ""
    for type_name, pat in _COURT_TYPE_PATTERNS:
        m = pat.match(s)
        if m:
            city = m.group(1).strip() if m.groups() else ""
            return type_name, city
    return s, ""


def court_type_options(db_path: Path | None = None) -> list[str]:
    """סוגי בית המשפט ('ערכאה') שקיימים בפועל במאגר, למיון בתפריט
    הסינון — לא כל 13 הסוגים תמיד קיימים (תלוי בהרכב הארכיון)."""
    conn = get_conn(db_path)
    rows = conn.execute("SELECT DISTINCT court FROM verdicts WHERE court != ''").fetchall()
    conn.close()
    types = {split_court(r[0])[0] for r in rows}
    return sorted(types)


def court_city_options(court_type: str = "", db_path: Path | None = None) -> list[str]:
    """ערים/מחוזות ('יישוב') שקיימים בפועל במאגר — אם court_type ניתן,
    רק הערים שיש להן בית משפט מהסוג הזה (למניעת רשימת ערים שלא רלוונטיות
    לסוג שכבר נבחר בתפריט השני)."""
    conn = get_conn(db_path)
    rows = conn.execute("SELECT DISTINCT court FROM verdicts WHERE court != ''").fetchall()
    conn.close()
    cities = set()
    for (court,) in rows:
        t, city = split_court(court)
        if city and (not court_type or t == court_type):
            cities.add(city)
    return sorted(cities)


def _courts_matching(court_type: str, city: str, db_path: Path | None = None) -> list[str]:
    """מחזיר את כל מחרוזות court הקיימות שתואמות את (סוג, עיר) שנבחרו —
    כדי לבנות סינון 'court IN (...)' בלי לשמור סוג/עיר כעמודות DB
    נפרדות (ראו split_court)."""
    conn = get_conn(db_path)
    rows = conn.execute("SELECT DISTINCT court FROM verdicts WHERE court != ''").fetchall()
    conn.close()
    matches = []
    for (court,) in rows:
        t, c = split_court(court)
        if (not court_type or t == court_type) and (not city or c == city):
            matches.append(court)
    return matches


def simple_search(*, name: str = "", judge: str = "", court_type: str = "", city: str = "",
                  case_number: str = "", free_text: str = "", match_mode: str = "any",
                  proceeding: str = "", date_from: str = "", date_to: str = "",
                  sort: str = "relevance",
                  limit: int = config.RESULTS_PER_PAGE, offset: int = 0,
                  db_path: Path | None = None) -> tuple[list[sqlite3.Row], int]:
    """חיפוש לפי שדות מובנים. מחזיר (רשומות בעמוד, סך הכל)."""
    conn = get_conn(db_path)
    where: list[str] = []
    params: list = []

    if name:
        where.append("verdicts.parties LIKE ?")
        params.append(f"%{name.strip()}%")
    if judge:
        where.append("verdicts.judge LIKE ?")
        params.append(f"%{judge.strip()}%")
    if court_type or city:
        # 'court' עצמו נשאר תיאורי-מלא (לתצוגה) — סוג ועיר הם ממדים
        # נגזרים (ראו split_court), אז מסננים לפי רשימת ערכי court
        # שתואמים, לא לפי עמודה נפרדת ב-DB.
        matching = _courts_matching(court_type, city, db_path)
        if not matching:
            matching = ["\0no_match\0"]  # לא קיים אף בית משפט מהצירוף הזה — 0 תוצאות בבטחה
        placeholders = ",".join("?" * len(matching))
        where.append(f"verdicts.court IN ({placeholders})")
        params.extend(matching)
    if case_number:
        where.append("verdicts.case_number LIKE ?")
        params.append(f"%{case_number.strip()}%")
    if proceeding:
        where.append("verdicts.proceeding = ?")
        params.append(proceeding.strip())
    if date_from:
        where.append("COALESCE(NULLIF(verdicts.decision_date,''), verdicts.filed_date) >= ?")
        params.append(date_from)
    if date_to:
        where.append("COALESCE(NULLIF(verdicts.decision_date,''), verdicts.filed_date) <= ?")
        params.append(date_to)

    # כשיש חיפוש חופשי בטקסט וגם מיון 'רלוונטיות', מצטרפים ל-verdicts_fts
    # (JOIN, לא subquery) כדי ש-bm25() יהיה זמין למיון — פונקציית bm25 של
    # FTS5 דורשת שהטבלה הוירטואלית תהיה נתונה ל-MATCH באותה שאילתה עצמה,
    # לא בתת-שאילתה נפרדת. בכל מקרה אחר (אין חיפוש חופשי, או שנבחר מיון
    # אחר במפורש) ה-IN/subquery הרגיל מספיק ופשוט יותר.
    fts = _fts_query(free_text, match_mode)
    use_bm25 = bool(fts) and sort == "relevance"
    if fts:
        if use_bm25:
            where.append("verdicts_fts MATCH ?")
        else:
            where.append("verdicts.id IN (SELECT rowid FROM verdicts_fts WHERE verdicts_fts MATCH ?)")
        params.append(fts)

    from_clause = "verdicts JOIN verdicts_fts ON verdicts_fts.rowid = verdicts.id" if use_bm25 else "verdicts"
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    cols = ", ".join(f"verdicts.{f}" for f in _FIELDS)
    order = _order_sql(sort, use_bm25)

    total = conn.execute(f"SELECT COUNT(*) FROM {from_clause}{clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT {cols} FROM {from_clause}{clause} "
        f"ORDER BY {order} "
        f"LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return rows, total


def get_verdict(verdict_id: int, db_path: Path | None = None) -> sqlite3.Row | None:
    conn = get_conn(db_path)
    row = conn.execute("SELECT * FROM verdicts WHERE id = ?", (verdict_id,)).fetchone()
    conn.close()
    return row


def random_verdict(db_path: Path | None = None) -> sqlite3.Row | None:
    """פסק דין אקראי (עם טקסט מלא)."""
    conn = get_conn(db_path)
    cols = ", ".join(_FIELDS)
    row = conn.execute(
        f"SELECT {cols} FROM verdicts WHERE has_document=1 "
        f"ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    conn.close()
    return row


def latest_verdict(db_path: Path | None = None) -> sqlite3.Row | None:
    """פסק הדין הכי עדכני שיש במאגר (לפי תאריך החלטה)."""
    conn = get_conn(db_path)
    cols = ", ".join(_FIELDS)
    row = conn.execute(
        f"SELECT {cols} FROM verdicts WHERE has_document=1 "
        f"AND COALESCE(NULLIF(decision_date,''), filed_date) != '' "
        f"ORDER BY COALESCE(NULLIF(decision_date,''), filed_date) DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return row


def oldest_verdict(db_path: Path | None = None) -> sqlite3.Row | None:
    """פסק הדין הכי ותיק שיש במאגר — 'פסק דין היסטורי'."""
    conn = get_conn(db_path)
    cols = ", ".join(_FIELDS)
    row = conn.execute(
        f"SELECT {cols} FROM verdicts WHERE has_document=1 "
        f"AND COALESCE(NULLIF(decision_date,''), filed_date) != '' "
        f"ORDER BY COALESCE(NULLIF(decision_date,''), filed_date) ASC LIMIT 1"
    ).fetchone()
    conn.close()
    return row


def keyword_verdict(terms: list[str], db_path: Path | None = None) -> sqlite3.Row | None:
    """פסק דין אקראי מתוך אלה שמכילים לפחות אחת ממילות המפתח (חיפוש
    טקסט חופשי) — משמש לאופציות כמו 'פסק דין על שימוש ב-AI'."""
    conn = get_conn(db_path)
    cols = ", ".join(f"v.{c}" for c in _FIELDS)
    fts = " OR ".join(f'"{t}"' for t in terms)
    row = conn.execute(
        f"SELECT {cols} FROM verdicts_fts f JOIN verdicts v ON v.id = f.rowid "
        f"WHERE f.verdicts_fts MATCH ? AND v.has_document=1 "
        f"ORDER BY RANDOM() LIMIT 1",
        (fts,),
    ).fetchone()
    conn.close()
    return row


def landmark_verdict(db_path: Path | None = None) -> sqlite3.Row | None:
    """פסק דין 'מרכזי' — best-effort: נבחר אקראית מתוך פסקי דין של בית
    המשפט העליון (לא ניתוח אמיתי של חשיבות/תקדימיות, רק קירוב סביר).

    משתמש ב-_SUPREME_PATH_COND (נתיב קובץ, ודאי) ולא בשדה court הטקסטואלי
    כמו קודם — court עשוי להישאר ריק גם עבור פסקי דין של העליון (חילוץ
    best-effort), ו-'court LIKE %עליון%' דורש סריקה מלאה (לא ניתן
    לאינדקס עם תו-בר פותח); LIKE 'supreme/%' הוא prefix match שכן."""
    conn = get_conn(db_path)
    cols = ", ".join(_FIELDS)
    row = conn.execute(
        f"SELECT {cols} FROM verdicts WHERE has_document=1 "
        f"AND {_SUPREME_PATH_COND} AND decision_type = 'פסק דין' "
        f"ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    conn.close()
    return row


def distinct_proceedings(db_path: Path | None = None) -> list[str]:
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT DISTINCT proceeding FROM verdicts WHERE proceeding != '' ORDER BY proceeding"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def stats(db_path: Path | None = None) -> dict:
    conn = get_conn(db_path)
    total = conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    with_docs = conn.execute("SELECT COUNT(*) FROM verdicts WHERE has_document=1").fetchone()[0]
    conn.close()
    return {"total": total, "with_documents": with_docs}


def retrieve_for_ai(*, fts_query: str = "", court_scope: str = "",
                    date_from: str = "", date_to: str = "",
                    limit: int = config.AI_MAX_DOCS,
                    db_path: Path | None = None) -> list[sqlite3.Row]:
    """אחזור פסקי דין עבור מנוע ה-AI: דירוג BM25 על הטקסט המלא + סינון תאריכים
    ו-court_scope (לפי נתיב קובץ ודאי, ראו _SUPREME_PATH_COND — לא לפי שדה
    court הטקסטואלי, שעשוי להיות ריק).

    מחזיר רק פסקי דין שיש להם טקסט מלא (has_document=1)."""
    conn = get_conn(db_path)
    where = ["v.has_document = 1"]
    params: list = []

    if court_scope == "supreme":
        where.append(_SUPREME_PATH_COND)
    elif court_scope == "general":
        where.append("NOT " + _SUPREME_PATH_COND)

    if date_from:
        where.append("COALESCE(NULLIF(v.decision_date,''), v.filed_date) >= ?")
        params.append(date_from)
    if date_to:
        where.append("COALESCE(NULLIF(v.decision_date,''), v.filed_date) <= ?")
        params.append(date_to)

    if fts_query:
        sql = (
            "SELECT v.* FROM verdicts_fts f JOIN verdicts v ON v.id = f.rowid "
            "WHERE f.verdicts_fts MATCH ? AND " + " AND ".join(where) +
            " ORDER BY bm25(f.verdicts_fts) LIMIT ?"
        )
        rows = conn.execute(sql, [fts_query] + params + [limit * 3]).fetchall()
    else:
        rows = []

    # גיבוי: אם אין תוצאות טקסטואליות, מחזירים את החדשים ביותר (בטווח התאריכים)
    if not rows:
        sql = (
            "SELECT v.* FROM verdicts v WHERE " + " AND ".join(where) +
            " ORDER BY COALESCE(NULLIF(v.decision_date,''), v.filed_date) DESC LIMIT ?"
        )
        rows = conn.execute(sql, params + [limit * 3]).fetchall()

    conn.close()

    # הסרת כפילויות (רשומות מטא-דאטה שונות המצביעות לאותו פסק דין) — בלי
    # הגבלה ל-limit כאן עדיין, כדי ש-_diversify_supreme יוכל לבחור מתוך
    # כל המועמדים שנשלפו (limit*3), לא רק מתוך ה-top-K הגולמי.
    seen: set = set()
    unique = []
    for r in rows:
        key = (r["case_number"], r["full_text"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    if not court_scope:
        unique = _diversify_supreme(unique, limit)
    return unique[:limit]


def _is_supreme_row(row: sqlite3.Row) -> bool:
    return any((row[c] or "").startswith("supreme/")
               for c in ("file_relpath", "file_relpath_pdf", "file_relpath_docx"))


def _diversify_supreme(rows: list, limit: int) -> list:
    """מוודא ייצוג של פסיקת בית המשפט העליון במדגם המוצג ל-AI, גם כשדירוג
    BM25 הגולמי מעדיף פסקי דין שגרתיים מערכאות נמוכות (שלעיתים חוזרים על
    מילות החיפוש בצפיפות גבוהה יותר, בלי שזה משקף משמעות משפטית רבה
    יותר) — כדי שתשובה על שאלה רחבה לא תתבסס רק על תקדימים שוליים בעוד
    פסיקה מנחה של העליון על אותו נושא כלל לא נכנסת ל-top-K. פועל רק
    כש-court_scope ריק (המשתמש לא ביקש במפורש עליון/לא-עליון בלבד) —
    אחרת זה יסתור את מה שהמשתמש ביקש בפירוש."""
    supreme_idx = [i for i, r in enumerate(rows) if _is_supreme_row(r)]
    if not supreme_idx:
        return rows
    n_supreme = min(len(supreme_idx), max(1, limit // 2))
    keep = set(supreme_idx[:n_supreme])
    for i in range(len(rows)):
        if len(keep) >= limit:
            break
        keep.add(i)
    return [rows[i] for i in sorted(keep)]


# תיוג ודאי של 'ארכיון העליון' לפי נתיב הקובץ (supreme/...), לא לפי שדה
# court הטקסטואלי — כי court עשוי להישאר ריק גם עבור פסקי דין של העליון
# (חילוץ מטא-דאטה best-effort שלא תמיד מוצא כותרת), בעוד שנתיב הקובץ
# נקבע ודאית בזמן ה-ingest (ראו zot/ingest.py: extra_sources=[(...,'supreme/')]).
_SUPREME_PATH_COND = (
    "(file_relpath LIKE 'supreme/%' OR file_relpath_pdf LIKE 'supreme/%' "
    "OR file_relpath_docx LIKE 'supreme/%')"
)


def count_verdicts(*, court_scope: str = "", fts_query: str = "",
                    date_from: str = "", date_to: str = "",
                    db_path: Path | None = None) -> int:
    """סופר במדויק (COUNT, לא מוגבל ל-top-K) כמה פסקי דין תואמים — עבור
    מנוע ה-AI, כדי שיוכל לענות על שאלות 'כמה' בלי לבלבל בין מדגם המסמכים
    שהוצג לו לבין המספר האמיתי במאגר. court_scope: 'supreme' (בית המשפט
    העליון, לפי נתיב קובץ) / 'general' (שאר בתי המשפט) / '' (הכול)."""
    conn = get_conn(db_path)
    where = ["v.has_document = 1"]
    params: list = []

    if court_scope == "supreme":
        where.append(_SUPREME_PATH_COND)
    elif court_scope == "general":
        where.append("NOT " + _SUPREME_PATH_COND)

    if date_from:
        where.append("COALESCE(NULLIF(v.decision_date,''), v.filed_date) >= ?")
        params.append(date_from)
    if date_to:
        where.append("COALESCE(NULLIF(v.decision_date,''), v.filed_date) <= ?")
        params.append(date_to)

    if fts_query:
        sql = (
            "SELECT COUNT(*) FROM verdicts_fts f JOIN verdicts v ON v.id = f.rowid "
            "WHERE f.verdicts_fts MATCH ? AND " + " AND ".join(where)
        )
        n = conn.execute(sql, [fts_query] + params).fetchone()[0]
    else:
        sql = "SELECT COUNT(*) FROM verdicts v WHERE " + " AND ".join(where)
        n = conn.execute(sql, params).fetchone()[0]

    conn.close()
    return n
