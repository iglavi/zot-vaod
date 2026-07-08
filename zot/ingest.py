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
from pathlib import Path

from . import config
from .extract import (extract_decision_date, extract_judge, extract_metadata,
                      filed_date_from_case, read_text)

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
    "has_document", "full_text", "structural_summary",
]

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
    full_text TEXT,
    structural_summary TEXT
);
CREATE VIRTUAL TABLE verdicts_fts USING fts5(
    parties, judge, court, case_number, matter, decision_type, full_text,
    content='verdicts', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
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


def _dir_date(path: Path) -> str:
    """מחזיר תאריך ISO משם תיקיית-האב אם הוא בפורמט YYYY-M-D (תיקיות ההורדה היומית)."""
    m = _DATE_DIR_RE.match(path.parent.name)
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
    """מכניס רשומה אחת גם ל-verdicts וגם (עם אותו rowid) לאינדקס הטקסט המלא
    (verdicts_fts) — כך שאין צורך ב'rebuild' גורף בסיום, גם כשמוסיפים
    רשומות בודדות אינקרementלית."""
    placeholders = ",".join("?" * len(_VERDICT_COLUMNS))
    cur = conn.execute(
        f"INSERT INTO verdicts ({','.join(_VERDICT_COLUMNS)}) VALUES ({placeholders})",
        [values[c] for c in _VERDICT_COLUMNS],
    )
    rowid = cur.lastrowid
    conn.execute(
        """INSERT INTO verdicts_fts(rowid, parties, judge, court, case_number,
           matter, decision_type, full_text) VALUES (?,?,?,?,?,?,?,?)""",
        (rowid, values["parties"], values["judge"], values["court"],
         values["case_number"], values["matter"], values["decision_type"],
         values["full_text"]),
    )
    return rowid


def build(metadata_path: Path | None = None, docs_dir: Path | None = None,
          db_path: Path | None = None, verbose: bool = True) -> dict:
    metadata_path = Path(metadata_path or config.METADATA_PATH)
    docs_dir = Path(docs_dir or config.DOCS_DIR)
    db_path = Path(db_path or config.DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(CACHE_SCHEMA)
    summary_cache = dict(conn.execute("SELECT stem, structural_summary FROM ai_summaries").fetchall())

    incremental = _schema_matches(conn)
    if incremental:
        existing_stems = {r[0] for r in conn.execute("SELECT filename FROM verdicts").fetchall()}
        if verbose:
            print(f"אינדקס קיים ותואם מבנה — מוסיף רק קבצים חדשים "
                  f"({len(existing_stems)} כבר מאונדקסים).")
    else:
        conn.execute("DROP TABLE IF EXISTS verdicts")
        conn.execute("DROP TABLE IF EXISTS verdicts_fts")
        conn.executescript(SCHEMA)
        existing_stems = set()
        if verbose:
            print("אין אינדקס תואם (ראשון, או שמבנה הקוד השתנה) — בונה הכול מחדש.")

    by_ext = _index_by_ext(docs_dir)

    def _relpaths(stem: str) -> tuple[str, str]:
        exts = by_ext.get(stem, {})
        pdf = exts.get(".pdf")
        docx = exts.get(".docx") or exts.get(".doc")
        return (pdf.relative_to(docs_dir).as_posix() if pdf else "",
                docx.relative_to(docs_dir).as_posix() if docx else "")

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

            doc = _best_doc(by_ext.get(stem, {}))
            full_text = ""
            judge = ""
            decision_date = ""
            has_doc = 0
            file_relpath = ""
            if doc is not None:
                file_relpath = doc.relative_to(docs_dir).as_posix()
                full_text = read_text(doc)
                if full_text:
                    has_doc = 1
                    docs_matched += 1
                    judge = extract_judge(full_text)
                    decision_date = extract_decision_date(full_text)

            filed = cell(row, "meta_date") or filed_date_from_case(case_number)
            relpath_pdf, relpath_docx = _relpaths(stem)

            _insert_verdict(conn, {
                "case_number": case_number, "parties": cell(row, "parties"),
                "court": cell(row, "court"), "proceeding": cell(row, "proceeding"),
                "case_type": cell(row, "case_type"), "matter": cell(row, "matter"),
                "decision_type": cell(row, "decision_type"),
                "decision_nature": cell(row, "decision_nature"),
                "filed_date": filed, "decision_date": decision_date, "judge": judge,
                "filename": stem, "file_relpath": file_relpath,
                "file_relpath_pdf": relpath_pdf, "file_relpath_docx": relpath_docx,
                "has_document": has_doc, "full_text": full_text,
                "structural_summary": summary_cache.get(stem, ""),
            })
            rows_inserted += 1
            if rows_inserted % _COMMIT_EVERY == 0:
                conn.commit()

    # ===== קבצים שאינם ב-CSV (למשל הורדות יומיות בשמות hash) =====
    # מחלצים את המטא-דאטה ישירות מגוף פסק הדין ומוסיפים אותם למאגר.
    for stem, exts in by_ext.items():
        if stem in covered_stems or stem in existing_stems:
            continue
        path = _best_doc(exts)
        full_text = read_text(path)
        if not full_text:
            continue
        md = extract_metadata(full_text)
        filed = _dir_date(path) or filed_date_from_case(md["case_number"])
        file_relpath = path.relative_to(docs_dir).as_posix()
        relpath_pdf, relpath_docx = _relpaths(stem)

        _insert_verdict(conn, {
            "case_number": md["case_number"], "parties": md["parties"],
            "court": md["court"], "proceeding": "", "case_type": md["case_type"],
            "matter": "", "decision_type": md["decision_type"], "decision_nature": "",
            "filed_date": filed, "decision_date": md["decision_date"],
            "judge": md["judge"], "filename": stem, "file_relpath": file_relpath,
            "file_relpath_pdf": relpath_pdf, "file_relpath_docx": relpath_docx,
            "has_document": 1, "full_text": full_text,
            "structural_summary": summary_cache.get(stem, ""),
        })
        rows_inserted += 1
        docs_matched += 1
        if rows_inserted % _COMMIT_EVERY == 0:
            conn.commit()

    conn.commit()
    total_rows = conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    conn.close()

    stats = {"rows": rows_inserted, "documents_matched": docs_matched,
             "documents_found": len(by_ext), "total_rows": total_rows}
    if verbose:
        verb = "נוספו" if incremental else "נבנה אינדקס:"
        print(f"{verb} {rows_inserted} רשומות חדשות "
              f"({docs_matched} מתוכן עם טקסט פסק דין מלא). "
              f"סה\"כ במאגר כעת: {total_rows}. DB: {db_path}")
    return stats


if __name__ == "__main__":
    build()
