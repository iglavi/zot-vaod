"""הרצה חד-פעמית: מתקנת שני דברים בבת אחת (שניהם נמצאו ע"י דיווח משתמש)
עבור רשומות קיימות, מקומי + Turso:

1. case_type: מריצה מחדש את normalize_case_type() (ראו zot/case_types.py:
   תיקון קידומת ב/ה שגויה, ודחיית שנים עבריות כמו 'תשפ"ד' שלא-קשורות
   ל-case_type בכלל) על כל הערכים הקיימים - מעדכנת רק שורות שהערך שלהן
   באמת משתנה.

2. parties: מריצה מחדש חילוץ מטא-דאטה (extract.extract_metadata) על כל
   מסמכי ארכיון העליון (documents_supreme) - שם תוקן _VS_RE (ראו
   zot/extract.py) שהיה גורם ל'תיקים מאוחדים' עם שני מספרי-תיק (למשל
   ע"א 4584/10 ו-ע"א 4699/10 יחד) לקבל שם-צד מזוהם מפרוזת גוף ההחלטה,
   או parties ריק לגמרי. נבדק בפועל על מדגם אקראי של כ-3,000 מסמכי עליון:
   131 שינויים, כולם שיפור (רובם ריק->שם אמיתי).

מעדכנת גם את אינדקס ה-FTS (verdicts_fts, contentless - מחייב מחיקה עם
הערכים הישנים במפורש לפני הכנסת החדשים, ראו zot/ingest.py: SCHEMA) וגם
מסנכרנת את השינויים ל-Turso (turso_sync-style batch).

הרצה: python _fix_case_type_and_parties.py
"""
import sqlite3
import sys
import time

sys.path.insert(0, ".")
from zot import config, extract, storage, turso_sync  # noqa: E402
from zot.case_types import normalize_case_type  # noqa: E402

SUPREME_DIR_PREFIX = "supreme/"


def resolve_supreme_path(relpath: str):
    from pathlib import Path
    if not relpath or not relpath.startswith(SUPREME_DIR_PREFIX):
        return None
    p = Path("documents_supreme") / relpath[len(SUPREME_DIR_PREFIX):]
    return p if p.exists() else None


def fix_case_types(conn: sqlite3.Connection) -> list[tuple[int, str, str]]:
    """מחזיר [(id, old, new), ...] לרשומות ש-case_type שלהן השתנה."""
    rows = conn.execute("SELECT id, case_type FROM verdicts WHERE case_type != ''").fetchall()
    changes = []
    for id_, old in rows:
        new = normalize_case_type(old)
        if new != old:
            changes.append((id_, old, new))
    print(f"case_type: {len(rows)} רשומות נבדקו, {len(changes)} ישתנו.", flush=True)
    for id_, old, new in changes:
        conn.execute("UPDATE verdicts SET case_type = ? WHERE id = ?", (new, id_))
    conn.commit()
    return changes


def fix_parties(conn: sqlite3.Connection) -> list[tuple[int, dict, str]]:
    """מחזיר [(id, old_fts_fields, new_parties), ...] לרשומות ש-parties
    שלהן השתנה, עבור מסמכי ארכיון העליון בלבד."""
    rows = conn.execute(
        "SELECT id, case_number, parties, judge, court, matter, decision_type, "
        "file_relpath, file_relpath_pdf, file_relpath_docx "
        "FROM verdicts WHERE has_document=1 AND "
        "(file_relpath LIKE 'supreme/%' OR file_relpath_pdf LIKE 'supreme/%' OR file_relpath_docx LIKE 'supreme/%')"
    ).fetchall()
    print(f"parties: {len(rows)} רשומות ארכיון עליון להערכה...", flush=True)

    changes = []
    checked = 0
    t0 = time.time()
    for id_, case_number, old_parties, judge, court, matter, decision_type, rel, rel_pdf, rel_docx in rows:
        path = resolve_supreme_path(rel_docx) or resolve_supreme_path(rel_pdf) or resolve_supreme_path(rel)
        if path is None:
            continue
        try:
            text = extract.read_text(path)
        except Exception:
            continue
        if not text:
            continue
        md = extract.extract_metadata(text)
        checked += 1
        new_parties = md["parties"]
        if new_parties != (old_parties or ""):
            # full_text עצמו לא משתנה כאן (רק parties) - אבל ה-FTS delete
            # דורש את הערך המדויק שכבר מאונדקס, כדי לא להשאיר postings
            # יתומים/למחוק את יכולת החיפוש בטקסט המלא של הרשומה הזו
            # (ראו zot/storage.py: fetch_fulltext).
            changes.append((id_, {
                "case_number": case_number, "old_parties": old_parties or "",
                "judge": judge, "court": court, "matter": matter,
                "decision_type": decision_type, "full_text": text,
            }, new_parties))
        if checked % 20000 == 0:
            print(f"  ...{checked}/{len(rows)} נבדקו ({time.time()-t0:.0f}s)", flush=True)

    print(f"parties: {checked} נבדקו, {len(changes)} ישתנו.", flush=True)

    for id_, old, new_parties in changes:
        conn.execute(
            "INSERT INTO verdicts_fts(verdicts_fts, rowid, parties, judge, court, "
            "case_number, matter, decision_type, full_text) VALUES ('delete',?,?,?,?,?,?,?,?)",
            (id_, old["old_parties"], old["judge"], old["court"], old["case_number"],
             old["matter"], old["decision_type"], old["full_text"]),
        )
        conn.execute(
            "INSERT INTO verdicts_fts(rowid, parties, judge, court, case_number, "
            "matter, decision_type, full_text) VALUES (?,?,?,?,?,?,?,?)",
            (id_, new_parties, old["judge"], old["court"], old["case_number"],
             old["matter"], old["decision_type"], old["full_text"]),
        )
        conn.execute("UPDATE verdicts SET parties = ? WHERE id = ?", (new_parties, id_))
    conn.commit()
    return changes


def sync_case_type_to_turso(changes: list[tuple[int, str, str]]) -> None:
    if not config.TURSO_DATABASE_URL or not changes:
        return
    statements = [("UPDATE verdicts SET case_type = ? WHERE id = ?", [new, id_])
                  for id_, old, new in changes]
    for i in range(0, len(statements), 300):
        turso_sync._run_batch(statements[i:i + 300])
    print(f"Turso: case_type סונכרן ({len(statements)} רשומות).", flush=True)


def sync_parties_to_turso(changes: list[tuple[int, dict, str]]) -> None:
    """מחזור-batch קטן במיוחד (10 רשומות = 30 statements) - כל רשומה כאן
    נושאת את הטקסט המלא פעמיים (מחיקה+הכנסה מחדש ב-FTS), אז מטען-ה-HTTP
    לכל בקשה גדול משמעותית מסנכרון רגיל (שאין בו full_text בכלל)."""
    if not config.TURSO_DATABASE_URL or not changes:
        return
    statements = []
    for id_, old, new_parties in changes:
        statements.append((
            "INSERT INTO verdicts_fts(verdicts_fts, rowid, parties, judge, court, "
            "case_number, matter, decision_type, full_text) VALUES ('delete',?,?,?,?,?,?,?,?)",
            [id_, old["old_parties"], old["judge"], old["court"], old["case_number"],
             old["matter"], old["decision_type"], old["full_text"]],
        ))
        statements.append((
            "INSERT INTO verdicts_fts(rowid, parties, judge, court, case_number, "
            "matter, decision_type, full_text) VALUES (?,?,?,?,?,?,?,?)",
            [id_, new_parties, old["judge"], old["court"], old["case_number"],
             old["matter"], old["decision_type"], old["full_text"]],
        ))
        statements.append(("UPDATE verdicts SET parties = ? WHERE id = ?", [new_parties, id_]))
    chunk = 30  # 10 רשומות (3 statements כל אחת)
    for i in range(0, len(statements), chunk):
        turso_sync._run_batch(statements[i:i + chunk])
        if (i // chunk) % 20 == 0:
            print(f"  ...Turso parties sync: {i}/{len(statements)} statements", flush=True)
    print(f"Turso: parties סונכרן ({len(changes)} רשומות).", flush=True)


if __name__ == "__main__":
    conn = sqlite3.connect(str(config.DB_PATH))
    ct_changes = fix_case_types(conn)
    p_changes = fix_parties(conn)
    conn.close()

    sync_case_type_to_turso(ct_changes)
    sync_parties_to_turso(p_changes)
    print("סיום.", flush=True)
