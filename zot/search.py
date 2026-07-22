"""שאילתות חיפוש מול אינדקס המטא-דאטה+FTS5 (Turso, אם מוגדר; אחרת קובץ
SQLite מקומי - ראו get_conn) וטקסט מלא (Cloudflare R2, ראו zot/storage.py:
fetch_fulltext/fetch_fulltexts - הטקסט לא חי יותר בטבלת verdicts עצמה)."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from . import config, storage

_FIELDS = ("id", "case_number", "parties", "court", "proceeding", "case_type",
           "matter", "decision_type", "decision_nature", "filed_date",
           "decision_date", "judge", "filename", "file_relpath",
           "file_relpath_pdf", "file_relpath_docx", "has_document")


def get_conn(db_path: Path | None = None):
    """מחזיר חיבור ל-Turso (מרוחק) אם TURSO_DATABASE_URL מוגדר; אחרת נופל
    בחזרה לקובץ SQLite מקומי (כפי שהיה לפני המעבר). שתי הגרסאות תומכות
    ב-execute/fetchall/fetchone/commit/close באותה חתימה (libsql הוא fork
    ישיר של SQLite) - אך בניגוד ל-sqlite3, ל-libsql אין row_factory, ולכן
    כל הפונקציות כאן ממירות שורות למילון בעצמן (ראו _rows/_row) במקום
    להסתמך על sqlite3.Row - כך שאותו קוד עובד מול שני הגיבויים בלי הבדל."""
    if config.TURSO_DATABASE_URL:
        import libsql
        return libsql.connect(database=config.TURSO_DATABASE_URL,
                              auth_token=config.TURSO_AUTH_TOKEN)
    path = Path(db_path or config.DB_PATH)
    if not path.exists():
        raise FileNotFoundError(f"האינדקס לא נבנה עדיין: {path}")
    return sqlite3.connect(str(path))


def _row(cur, row) -> dict | None:
    """ממיר שורה בודדת (tuple, משני הגיבויים) למילון לפי שמות העמודות -
    מאפשר גישה row['field'] כמו שהקוד הקורא (app.py/ai_search.py) כבר
    מצפה, בלי תלות ב-sqlite3.Row (שלא קיים ב-libsql)."""
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _rows(cur, rows) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def db_exists(db_path: Path | None = None) -> bool:
    if config.TURSO_DATABASE_URL:
        return True
    return Path(db_path or config.DB_PATH).exists()


_TOKEN_RE = re.compile(r"[\w֐-׿]+", flags=re.UNICODE)

# מצבי התאמה לחיפוש חופשי בטקסט:
#   any    — כל מילה בנפרד, מחוברות ב-OR (הכי סלחני, ברירת המחדל)
#   exact  — הביטוי המדויק כמחרוזת אחת (FTS5 phrase query)
#   near   — המילים קרובות זו לזו בטקסט (FTS5 NEAR, מרחק 6 מילים)
MATCH_MODES = ("any", "exact", "near")

SORT_OPTIONS = ("relevance", "newest", "oldest", "longest")


def _fts_phrase_for_column(text: str, column: str) -> str:
    """בונה שאילתת FTS5 מוגבלת-עמודה (phrase match) עבור שדה בודד (שם צד/
    שופט/מספר תיק) - במקום LIKE '%x%'. נבדק בפועל מול Turso: LIKE עם
    תו-כללי מוביל (%) הוא תמיד סריקה מלאה (שום אינדקס לא יכול לעזור לו),
    4+ שניות; FTS phrase על אותה עמודה - עשרות מ"ש. המחיר: FTS5 דורש
    התאמת-token שלמה (לא תת-מחרוזת באמצע מילה) - קירוב סביר לחיפוש שם/
    מספר תיק בפועל, שבד"כ מוקלד כמילה/מספר שלמים."""
    tokens = _TOKEN_RE.findall(text or "")
    if not tokens:
        return ""
    quoted = " ".join(tokens)
    return f'{column}:"{quoted}"'


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
    "relevance": f"{_RELEVANCE_TYPE_CASE}, verdicts.text_length DESC, verdicts.id DESC",
    "newest": "COALESCE(NULLIF(verdicts.decision_date,''), verdicts.filed_date) DESC, verdicts.id DESC",
    "oldest": "COALESCE(NULLIF(verdicts.decision_date,''), verdicts.filed_date) ASC, verdicts.id ASC",
    "longest": "verdicts.text_length DESC, verdicts.id DESC",
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
                  proceeding: str = "", case_type: str = "", date_from: str = "", date_to: str = "",
                  sort: str = "relevance",
                  limit: int = config.RESULTS_PER_PAGE, offset: int = 0,
                  db_path: Path | None = None) -> tuple[list[dict], int]:
    """חיפוש לפי שדות מובנים. מחזיר (רשומות בעמוד, סך הכל)."""
    conn = get_conn(db_path)
    # מסננים תמיד רק רשומות עם טקסט מלא זמין: רשומת מטא-דאטה בלבד (בעיקר
    # פסקי דין ישנים של העליון, מלפני שהופצו כקבצים מלאים) אין למשתמש
    # מה לעשות איתה בתוצאות חיפוש — היא רק מטרידה ("קובץ פסק הדין המלא
    # אינו זמין"), לא תוצאה שימושית.
    #
    # has_document נשמר בנפרד משאר התנאים (לא בתוך where) בכוונה: has_document
    # תואם ל-99.9% מהשורות (בלי סלקטיביות כלשהי), וכש-Turso (בלי ANALYZE)
    # רואה אותו יחד עם תנאי סלקטיבי בהרבה (כמו case_type=?) באותה שאילתת
    # COUNT, הוא בפועל בחר לסרוק דרך אינדקס has_document (677K שורות) במקום
    # דרך אינדקס case_type (מאות שורות) - נמדד בפועל 4.3+ שניות. הפתרון:
    # מסננים לפי שאר התנאים קודם (ב-CTE, ראו למטה בחישוב total), ומיישמים
    # את has_document רק אחרי זה כתנאי-JOIN חיצוני.
    has_doc_cond = "verdicts.has_document = 1"
    where: list[str] = []
    params: list = []

    if name:
        fts_name = _fts_phrase_for_column(name, "parties")
        if fts_name:
            where.append("verdicts.id IN (SELECT rowid FROM verdicts_fts WHERE verdicts_fts MATCH ?)")
            params.append(fts_name)
    if judge:
        fts_judge = _fts_phrase_for_column(judge, "judge")
        if fts_judge:
            where.append("verdicts.id IN (SELECT rowid FROM verdicts_fts WHERE verdicts_fts MATCH ?)")
            params.append(fts_judge)
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
        fts_cn = _fts_phrase_for_column(case_number, "case_number")
        if fts_cn:
            where.append("verdicts.id IN (SELECT rowid FROM verdicts_fts WHERE verdicts_fts MATCH ?)")
            params.append(fts_cn)
    if proceeding:
        where.append("verdicts.proceeding = ?")
        params.append(proceeding.strip())
    if case_type:
        where.append("verdicts.case_type = ?")
        params.append(case_type.strip())
    if date_from:
        where.append("COALESCE(NULLIF(verdicts.decision_date,''), verdicts.filed_date) >= ?")
        params.append(date_from)
    if date_to:
        where.append("COALESCE(NULLIF(verdicts.decision_date,''), verdicts.filed_date) <= ?")
        params.append(date_to)

    fts = _fts_query(free_text, match_mode)
    use_bm25 = bool(fts) and sort == "relevance"

    # הספירה הכוללת (total): כש-Turso צריך גם למיין וגם לספור בלי LIMIT,
    # מדידה בפועל הראתה שבחירת האינדקס גרועה בעקביות (בין אם has_document
    # לבד, ביחד עם תנאי אחר, או ביחד עם JOIN ל-verdicts_fts) - סריקה כמעט
    # מלאה גם כשההתאמות מעטות (ראו README.md: "מלכודת ביצועים קריטית").
    # הפתרון האחיד: מסננים לפי כל שאר התנאים (name/judge/court/case_type/
    # proceeding/תאריכים/FTS) קודם, בתוך CTE ממומש (MATERIALIZED - מכריח
    # חישוב מיידי, לא inline), ורק *אחרי* זה מצטרפים לבדוק has_document -
    # כך ש-has_document (הכי לא-סלקטיבי, 99.9% מהשורות) אף פעם לא נבחר
    # כאינדקס-הכניסה. כשאין שום תנאי אחר, הבדיקה הפשוטה על has_document
    # לבדה כבר מהירה (יש לה אינדקס ייעודי) - לא עוטפים ב-CTE בלי צורך.
    count_where = list(where)
    count_params = list(params)
    if fts:
        count_where.append("verdicts.id IN (SELECT rowid FROM verdicts_fts WHERE verdicts_fts MATCH ?)")
        count_params.append(fts)
    if count_where:
        count_clause = " AND ".join(count_where)
        total = conn.execute(
            f"WITH matches AS MATERIALIZED (SELECT id FROM verdicts WHERE {count_clause}) "
            f"SELECT COUNT(*) FROM matches m JOIN verdicts v ON v.id = m.id WHERE {has_doc_cond.replace('verdicts.', 'v.')}",
            count_params,
        ).fetchone()[0]
    else:
        total = conn.execute(f"SELECT COUNT(*) FROM verdicts WHERE {has_doc_cond}").fetchone()[0]

    # כשיש חיפוש חופשי בטקסט וגם מיון 'רלוונטיות', מצטרפים ל-verdicts_fts
    # (JOIN, לא subquery) כדי ש-bm25() יהיה זמין למיון — פונקציית bm25 של
    # FTS5 דורשת שהטבלה הוירטואלית תהיה נתונה ל-MATCH באותה שאילתה עצמה,
    # לא בתת-שאילתה נפרדת. בכל מקרה אחר (אין חיפוש חופשי, או שנבחר מיון
    # אחר במפורש) ה-IN/subquery הרגיל מספיק ופשוט יותר. בניגוד ל-COUNT
    # למעלה, כאן יש LIMIT+ORDER BY — נבדק בפועל שזה כן מהיר מול Turso גם
    # כש-has_document משולב עם תנאים אחרים באותה שאילתה (הבעיה הייתה
    # ספציפית ל-COUNT(*) בלי LIMIT).
    where = [has_doc_cond] + where
    if fts:
        if use_bm25:
            where.append("verdicts_fts MATCH ?")
        else:
            where.append("verdicts.id IN (SELECT rowid FROM verdicts_fts WHERE verdicts_fts MATCH ?)")
        params.append(fts)

    from_clause = "verdicts JOIN verdicts_fts ON verdicts_fts.rowid = verdicts.id" if use_bm25 else "verdicts"
    clause = " WHERE " + " AND ".join(where)
    cols = ", ".join(f"verdicts.{f}" for f in _FIELDS)
    order = _order_sql(sort, use_bm25)

    cur = conn.execute(
        f"SELECT {cols} FROM {from_clause}{clause} "
        f"ORDER BY {order} "
        f"LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    rows = _rows(cur, cur.fetchall())
    conn.close()
    return rows, total


def get_verdict(verdict_id: int, db_path: Path | None = None) -> dict | None:
    """פרטי פסק דין בודד, כולל הטקסט המלא (נשלף מ-R2 - ראו storage.fetch_fulltext,
    לא נשמר יותר בטבלת verdicts עצמה)."""
    conn = get_conn(db_path)
    cur = conn.execute("SELECT * FROM verdicts WHERE id = ?", (verdict_id,))
    row = _row(cur, cur.fetchone())
    conn.close()
    if row is not None:
        row["full_text"] = storage.fetch_fulltext(verdict_id)
    return row


def random_verdict(db_path: Path | None = None) -> dict | None:
    """פסק דין אקראי."""
    conn = get_conn(db_path)
    cols = ", ".join(_FIELDS)
    cur = conn.execute(
        f"SELECT {cols} FROM verdicts WHERE has_document=1 "
        f"ORDER BY RANDOM() LIMIT 1"
    )
    row = _row(cur, cur.fetchone())
    conn.close()
    return row


def latest_verdict(db_path: Path | None = None) -> dict | None:
    """פסק הדין הכי עדכני שיש במאגר (לפי תאריך החלטה)."""
    conn = get_conn(db_path)
    cols = ", ".join(_FIELDS)
    cur = conn.execute(
        f"SELECT {cols} FROM verdicts WHERE has_document=1 "
        f"AND COALESCE(NULLIF(decision_date,''), filed_date) != '' "
        f"ORDER BY COALESCE(NULLIF(decision_date,''), filed_date) DESC LIMIT 1"
    )
    row = _row(cur, cur.fetchone())
    conn.close()
    return row


def oldest_verdict(db_path: Path | None = None) -> dict | None:
    """פסק הדין הכי ותיק שיש במאגר — 'פסק דין היסטורי'."""
    conn = get_conn(db_path)
    cols = ", ".join(_FIELDS)
    cur = conn.execute(
        f"SELECT {cols} FROM verdicts WHERE has_document=1 "
        f"AND COALESCE(NULLIF(decision_date,''), filed_date) != '' "
        f"ORDER BY COALESCE(NULLIF(decision_date,''), filed_date) ASC LIMIT 1"
    )
    row = _row(cur, cur.fetchone())
    conn.close()
    return row


def keyword_verdict(terms: list[str], db_path: Path | None = None) -> dict | None:
    """פסק דין אקראי מתוך אלה שמכילים לפחות אחת ממילות המפתח (חיפוש
    טקסט חופשי) — משמש לאופציות כמו 'פסק דין על שימוש ב-AI'."""
    conn = get_conn(db_path)
    cols = ", ".join(f"v.{c}" for c in _FIELDS)
    fts = " OR ".join(f'"{t}"' for t in terms)
    cur = conn.execute(
        f"SELECT {cols} FROM verdicts_fts f JOIN verdicts v ON v.id = f.rowid "
        f"WHERE f.verdicts_fts MATCH ? AND v.has_document=1 "
        f"ORDER BY RANDOM() LIMIT 1",
        (fts,),
    )
    row = _row(cur, cur.fetchone())
    conn.close()
    return row


def landmark_verdict(db_path: Path | None = None) -> dict | None:
    """פסק דין 'מרכזי' — best-effort: נבחר אקראית מתוך פסקי דין של בית
    המשפט העליון (לא ניתוח אמיתי של חשיבות/תקדימיות, רק קירוב סביר).

    משתמש בעמודת is_supreme (מחושבת ומאונדקסת בזמן ה-ingest, ראו
    zot/ingest.py: _insert_verdict) - לא בבדיקת נתיב-קובץ/court בזמן
    השאילתה: זו האחרונה פספסה בפועל כל פסק דין של העליון שהגיע מההורדה
    היומית הרגילה (רק supreme/... מהארכיון ההיסטורי הנפרד היה מזוהה), וגם
    לא יכלה לכלול את שדה court בלי סריקה מלאה (LIKE עם % מוביל)."""
    conn = get_conn(db_path)
    cols = ", ".join(_FIELDS)
    cur = conn.execute(
        f"SELECT {cols} FROM verdicts WHERE has_document=1 "
        f"AND is_supreme = 1 AND decision_type = 'פסק דין' "
        f"ORDER BY RANDOM() LIMIT 1"
    )
    row = _row(cur, cur.fetchone())
    conn.close()
    return row


def distinct_proceedings(db_path: Path | None = None) -> list[str]:
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT DISTINCT proceeding FROM verdicts WHERE proceeding != '' ORDER BY proceeding"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def distinct_case_types(db_path: Path | None = None) -> list[str]:
    """סוגי-הליך ('סוג עניין', ראו zot/case_types.py) שקיימים בפועל
    במאגר — לא כל ~370 הקודים ברשימת נבו תמיד קיימים (תלוי בהרכב
    הארכיון), אז התפריט גדל בעצמו ברגע שמופיע קוד חדש."""
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT DISTINCT case_type FROM verdicts WHERE case_type != '' ORDER BY case_type"
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
                    limit: int = config.AI_MAX_DOCS, sort: str = "newest",
                    db_path: Path | None = None) -> list[dict]:
    """אחזור פסקי דין עבור מנוע ה-AI: דירוג BM25 על הטקסט המלא + סינון תאריכים
    ו-court_scope (לפי עמודת is_supreme המחושבת-מראש, ראו zot/ingest.py).

    sort ('newest'/'oldest') קובע את כיוון המיון-לפי-תאריך של נתיב הגיבוי
    (כש-fts_query ריק) — משמש גם כ'גיבוי אמיתי' (0 תוצאות טקסטואליות)
    וגם ביודעין לשאלות מטא כמו 'מה ההחלטה העדכנית/הישנה ביותר' (ראו
    zot/ai_search.py: retrieve) — שאלות כאלה אין להן כלל מילות-חיפוש
    תוכניות משמעותיות, ו-BM25 (שאין לו מושג של 'הכי חדש') היה מחזיר
    התאמות אקראיות-למראה למילים גנריות כמו 'עדכני'/'אחרון'.

    מחזיר רק פסקי דין שיש להם טקסט מלא (has_document=1)."""
    conn = get_conn(db_path)
    where = ["v.has_document = 1"]
    params: list = []

    if court_scope == "supreme":
        where.append("v.is_supreme = 1")
    elif court_scope == "general":
        where.append("v.is_supreme = 0")

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
        cur = conn.execute(sql, [fts_query] + params + [limit * 3])
        rows = _rows(cur, cur.fetchall())
    else:
        rows = []

    # גיבוי: אם אין תוצאות טקסטואליות (או כש-fts_query ריק בכוונה, ראו
    # למעלה), מחזירים לפי מיון-תאריך בטווח התאריכים. ל'הישן ביותר' חייבים
    # לסנן רשומות בלי שום תאריך (COALESCE נותן '' — מחרוזת ריקה, שממוינת
    # *ראשונה* ב-ASC לפני כל תאריך אמיתי) — אחרת 'הישן ביותר' מחזיר בטעות
    # רשומות חסרות-תאריך במקום את פסק הדין הישן האמיתי. לא נדרש ב-DESC
    # ('החדש ביותר'): שם מחרוזת ריקה ממילא נופלת לסוף המיון מעצמה.
    if not rows:
        oldest = sort == "oldest"
        direction = "ASC" if oldest else "DESC"
        date_where = list(where)
        if oldest:
            date_where.append("COALESCE(NULLIF(v.decision_date,''), v.filed_date, '') != ''")
        sql = (
            "SELECT v.* FROM verdicts v WHERE " + " AND ".join(date_where) +
            f" ORDER BY COALESCE(NULLIF(v.decision_date,''), v.filed_date) {direction} LIMIT ?"
        )
        cur = conn.execute(sql, params + [limit * 3])
        rows = _rows(cur, cur.fetchall())

    conn.close()

    # הסרת כפילויות (רשומות מטא-דאטה שונות המצביעות לאותו פסק דין) — בלי
    # הגבלה ל-limit כאן עדיין, כדי ש-_diversify_supreme יוכל לבחור מתוך
    # כל המועמדים שנשלפו (limit*3), לא רק מתוך ה-top-K הגולמי. מפתח הכפילות
    # חייב לזהות מסמך בודד, לא תיק שלם: case_number לבדו התברר כשגוי בפועל
    # (ראו בדיקה בשיחה) — תיק עם כמה החלטות/פסקי-דין שחולקים אותו מספר תיק
    # נראה בטעות ככפילות של אותה החלטה, וכל ההחלטות מלבד הראשונה (לפי דירוג
    # BM25) נזרקות לפני שה-AI בכלל רואה אותן. לכן המפתח כולל גם תאריך/סוג/
    # שופט/אורך-טקסט - כך רק רשומות שזהות בכל אלה (כפילות הזרקה אמיתית)
    # מתמזגות, בדומה למפתח המקביל ב-_nethamishpat_ingest.py.
    seen: set = set()
    unique = []
    for r in rows:
        key = (r["case_number"], r["decision_date"], r["decision_type"],
               r["judge"], r["text_length"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    if not court_scope:
        unique = _diversify_supreme(unique, limit)
    final = unique[:limit]

    # טקסט מלא נשלף רק עבור ה-limit הסופי (לא כל limit*3 המועמדים) - במקביל
    # (ThreadPoolExecutor, ראו storage.fetch_fulltexts) כדי שזמן התגובה לא
    # יגדל ליניארית עם AI_MAX_DOCS.
    texts = storage.fetch_fulltexts([r["id"] for r in final])
    for r in final:
        r["full_text"] = texts.get(r["id"], "")
    return final


def _is_supreme_row(row: dict) -> bool:
    return bool(row.get("is_supreme"))


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


def count_verdicts(*, court_scope: str = "", fts_query: str = "",
                    date_from: str = "", date_to: str = "",
                    db_path: Path | None = None) -> int:
    """סופר במדויק (COUNT, לא מוגבל ל-top-K) כמה פסקי דין תואמים — עבור
    מנוע ה-AI, כדי שיוכל לענות על שאלות 'כמה' בלי לבלבל בין מדגם המסמכים
    שהוצג לו לבין המספר האמיתי במאגר. court_scope: 'supreme' (בית המשפט
    העליון, לפי עמודת is_supreme המחושבת-מראש) / 'general' (שאר בתי
    המשפט) / '' (הכול).

    משתמש תמיד ב-IN/subquery (לא JOIN) כשיש fts_query - ראו הערה מקבילה
    ב-simple_search: COUNT(*) על JOIN מול verdicts_fts גורם לתכנון שאילתה
    גרוע במיוחד מול Turso (סריקה מלאה, 22+ שניות בפועל)."""
    conn = get_conn(db_path)
    # has_document נשמר בנפרד משאר התנאים - ראו הערה מקבילה ומפורטת יותר
    # ב-simple_search: כש-Turso רואה has_document (99.9% מהשורות) יחד עם
    # תנאי סלקטיבי בהרבה (טווח תאריכים, court_scope, MATCH) באותה שאילתת
    # COUNT, הוא בעקביות בוחר לסרוק לפי has_document ולא לפי התנאי הטוב
    # יותר - סריקה כמעט מלאה גם כשההתאמות מעטות.
    where: list[str] = []
    params: list = []

    if court_scope == "supreme":
        where.append("is_supreme = 1")
    elif court_scope == "general":
        where.append("is_supreme = 0")

    if date_from:
        where.append("COALESCE(NULLIF(decision_date,''), filed_date) >= ?")
        params.append(date_from)
    if date_to:
        where.append("COALESCE(NULLIF(decision_date,''), filed_date) <= ?")
        params.append(date_to)
    if fts_query:
        where.append("id IN (SELECT rowid FROM verdicts_fts WHERE verdicts_fts MATCH ?)")
        params.append(fts_query)

    if where:
        clause = " AND ".join(where)
        sql = (
            f"WITH matches AS MATERIALIZED (SELECT id FROM verdicts WHERE {clause}) "
            f"SELECT COUNT(*) FROM matches m JOIN verdicts v ON v.id = m.id WHERE v.has_document = 1"
        )
        n = conn.execute(sql, params).fetchone()[0]
    else:
        n = conn.execute("SELECT COUNT(*) FROM verdicts WHERE has_document = 1").fetchone()[0]

    conn.close()
    return n
