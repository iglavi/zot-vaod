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

SORT_OPTIONS = ("newest", "oldest", "longest")


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


_SORT_SQL = {
    "newest": "COALESCE(NULLIF(decision_date,''), filed_date) DESC, id DESC",
    "oldest": "COALESCE(NULLIF(decision_date,''), filed_date) ASC, id ASC",
    "longest": "length(full_text) DESC, id DESC",
}


def simple_search(*, name: str = "", judge: str = "", court: str = "",
                  case_number: str = "", free_text: str = "", match_mode: str = "any",
                  proceeding: str = "", date_from: str = "", date_to: str = "",
                  sort: str = "newest",
                  limit: int = config.RESULTS_PER_PAGE, offset: int = 0,
                  db_path: Path | None = None) -> tuple[list[sqlite3.Row], int]:
    """חיפוש לפי שדות מובנים. מחזיר (רשומות בעמוד, סך הכל)."""
    conn = get_conn(db_path)
    where: list[str] = []
    params: list = []

    if name:
        where.append("parties LIKE ?")
        params.append(f"%{name.strip()}%")
    if judge:
        where.append("judge LIKE ?")
        params.append(f"%{judge.strip()}%")
    if court:
        where.append("court LIKE ?")
        params.append(f"%{court.strip()}%")
    if case_number:
        where.append("case_number LIKE ?")
        params.append(f"%{case_number.strip()}%")
    if proceeding:
        where.append("proceeding = ?")
        params.append(proceeding.strip())
    if date_from:
        where.append("COALESCE(NULLIF(decision_date,''), filed_date) >= ?")
        params.append(date_from)
    if date_to:
        where.append("COALESCE(NULLIF(decision_date,''), filed_date) <= ?")
        params.append(date_to)

    fts = _fts_query(free_text, match_mode)
    if fts:
        where.append("id IN (SELECT rowid FROM verdicts_fts WHERE verdicts_fts MATCH ?)")
        params.append(fts)

    clause = (" WHERE " + " AND ".join(where)) if where else ""
    cols = ", ".join(_FIELDS)
    order = _SORT_SQL.get(sort, _SORT_SQL["newest"])

    total = conn.execute(f"SELECT COUNT(*) FROM verdicts{clause}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT {cols} FROM verdicts{clause} "
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


def distinct_courts(db_path: Path | None = None) -> list[str]:
    conn = get_conn(db_path)
    rows = conn.execute(
        "SELECT DISTINCT court FROM verdicts WHERE court != '' ORDER BY court"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


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
