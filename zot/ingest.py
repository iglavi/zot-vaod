"""בניית אינדקס החיפוש (SQLite + FTS5) מתוך metadata.csv ותיקיית pסקי הדין.

מריצים פעם אחת (ובכל פעם שמתווספים פסקי דין חדשים):
    python -m zot.ingest
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

SCHEMA = """
DROP TABLE IF EXISTS verdicts;
DROP TABLE IF EXISTS verdicts_fts;
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
    has_document INTEGER DEFAULT 0,
    full_text TEXT
);
CREATE VIRTUAL TABLE verdicts_fts USING fts5(
    parties, judge, court, case_number, matter, decision_type, full_text,
    content='verdicts', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
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


def _index_documents(docs_dir: Path) -> dict[str, Path]:
    """ממפה 'שם קובץ ללא סיומת' -> נתיב הקובץ, לחיבור מהיר מול ה-CSV.

    סורק גם תת-תיקיות (למשל תיקיות לפי תאריך שיוצר סקריפט ההורדה)."""
    index: dict[str, Path] = {}
    if not docs_dir.exists():
        return index
    for f in docs_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in _EXT_PRIORITY:
            cur = index.get(f.stem)
            if cur is None or _EXT_PRIORITY[f.suffix.lower()] < _EXT_PRIORITY[cur.suffix.lower()]:
                index[f.stem] = f
    return index


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


def build(metadata_path: Path | None = None, docs_dir: Path | None = None,
          db_path: Path | None = None, verbose: bool = True) -> dict:
    metadata_path = Path(metadata_path or config.METADATA_PATH)
    docs_dir = Path(docs_dir or config.DOCS_DIR)
    db_path = Path(db_path or config.DB_PATH)

    doc_index = _index_documents(docs_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)

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
            parties = cell(row, "parties")
            court = cell(row, "court")
            file_path = cell(row, "file_path")

            stem = Path(file_path.replace("\\", "/")).stem if file_path else ""
            doc = doc_index.get(stem)

            full_text = ""
            judge = ""
            decision_date = ""
            has_doc = 0
            file_relpath = ""
            if doc is not None:
                covered_stems.add(stem)
                file_relpath = doc.relative_to(docs_dir).as_posix()
                full_text = read_text(doc)
                if full_text:
                    has_doc = 1
                    docs_matched += 1
                    judge = extract_judge(full_text)
                    decision_date = extract_decision_date(full_text)

            filed = cell(row, "meta_date") or filed_date_from_case(case_number)

            conn.execute(
                """INSERT INTO verdicts
                   (case_number, parties, court, proceeding, case_type, matter,
                    decision_type, decision_nature, filed_date, decision_date,
                    judge, filename, file_relpath, has_document, full_text)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (case_number, parties, court, cell(row, "proceeding"),
                 cell(row, "case_type"), cell(row, "matter"),
                 cell(row, "decision_type"), cell(row, "decision_nature"),
                 filed, decision_date, judge, stem, file_relpath, has_doc, full_text),
            )
            rows_inserted += 1

    # ===== קבצים שאינם ב-CSV (למשל הורדות יומיות בשמות hash) =====
    # מחלצים את המטא-דאטה ישירות מגוף פסק הדין ומוסיפים אותם למאגר.
    for stem, path in doc_index.items():
        if stem in covered_stems:
            continue
        full_text = read_text(path)
        if not full_text:
            continue
        md = extract_metadata(full_text)
        filed = _dir_date(path) or filed_date_from_case(md["case_number"])
        file_relpath = path.relative_to(docs_dir).as_posix()
        conn.execute(
            """INSERT INTO verdicts
               (case_number, parties, court, proceeding, case_type, matter,
                decision_type, decision_nature, filed_date, decision_date,
                judge, filename, file_relpath, has_document, full_text)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (md["case_number"], md["parties"], md["court"], "",
             md["case_type"], "", md["decision_type"], "",
             filed, md["decision_date"], md["judge"], stem, file_relpath, 1, full_text),
        )
        rows_inserted += 1
        docs_matched += 1

    # בניית אינדקס הטקסט המלא
    conn.execute("INSERT INTO verdicts_fts(verdicts_fts) VALUES('rebuild')")
    conn.commit()
    conn.close()

    stats = {"rows": rows_inserted, "documents_matched": docs_matched,
             "documents_found": len(doc_index)}
    if verbose:
        print(f"נבנה אינדקס: {rows_inserted} רשומות, "
              f"{docs_matched} מתוכן עם טקסט פסק דין מלא. DB: {db_path}")
    return stats


if __name__ == "__main__":
    build()
