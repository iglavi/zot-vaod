"""הרצה חד-פעמית מקיפה (ראו README.md): עוברת על *כל* המאגר (לא רק ארכיון
העליון כמו _fix_case_type_and_parties.py) ומתקנת:

1. parties: מריצה מחדש extract.extract_metadata() על כל מסמך עם
   has_document=1, עם כל תיקוני זיהוי-הצדדים העדכניים (_VS_RE מוגבל-מרחק,
   _LIST_ITEM_START_RE הפוך, _BARE_ROLE_NUM_RE ללא ה"א-הידיעה). מתעדת
   *בפירוש* למה שורות מדולגות (קובץ לא נמצא / כשל קריאה / טקסט ריק) -
   בניגוד לסקריפט הקודם, שדילג בשקט על 42,164 מתוך 152,357 (כ-28%!)
   בלי שום אבחון - כאן כל דילוג נרשם ללוג כדי לוודא שהריצה הזו באמת
   מכסה הכול (או שידוע במדויק למה לא).

2. כפילויות: מרחיבה את הזיהוי גם למקרים שבהם לכל עותק יש case_number
   *שונה* (תיק מאוחד שבו כל עותק תויג לפי מספר-התיק המוביל בכותרת שלו,
   ראו ע"פ 5582/09 שדווח) - מתאימה לפי (court, judge, decision_date,
   text_length) בלבד, בלי case_number. עדיין דורשת text_length זהה
   ו-text_length>1500 (לא רק מטא-דאטה תואמת) כדי לא לבלבל בין כפילות
   אמיתית לבין שתי החלטות שונות באותו יום (ראו README: הבדיקה המקורית
   שדרשה רק מטא-דאטה מצאה 47,807 "כפילויות" מדומות).

הרצה: python _fix_all_parties_and_duplicates.py
"""
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from zot import config, extract, storage, turso_sync  # noqa: E402

LOG_SKIPPED = Path("fix_all_skipped.log")


def resolve_path(relpath: str):
    if not relpath:
        return None
    if relpath.startswith("supreme/"):
        p = Path("documents_supreme") / relpath[len("supreme/"):]
    else:
        p = Path(config.DOCS_DIR) / relpath
    return p if p.exists() else None


def fix_parties(conn: sqlite3.Connection) -> list[tuple[int, dict, str]]:
    rows = conn.execute(
        "SELECT id, case_number, parties, judge, court, matter, decision_type, "
        "file_relpath, file_relpath_pdf, file_relpath_docx "
        "FROM verdicts WHERE has_document=1"
    ).fetchall()
    print(f"parties: {len(rows)} רשומות בסה\"כ להערכה...", flush=True)

    changes = []
    checked = skipped_no_path = skipped_read_err = skipped_empty = 0
    t0 = time.time()
    skip_log = LOG_SKIPPED.open("w", encoding="utf-8")
    for i, (id_, case_number, old_parties, judge, court, matter, decision_type,
            rel, rel_pdf, rel_docx) in enumerate(rows, 1):
        path = resolve_path(rel_docx) or resolve_path(rel_pdf) or resolve_path(rel)
        if path is None:
            skipped_no_path += 1
            skip_log.write(f"NO_PATH id={id_} rel={rel!r} pdf={rel_pdf!r} docx={rel_docx!r}\n")
            continue
        try:
            text = extract.read_text(path)
        except Exception as e:  # noqa: BLE001
            skipped_read_err += 1
            skip_log.write(f"READ_ERR id={id_} path={path} err={e}\n")
            continue
        if not text:
            skipped_empty += 1
            skip_log.write(f"EMPTY_TEXT id={id_} path={path}\n")
            continue

        md = extract.extract_metadata(text)
        checked += 1
        new_parties = md["parties"]
        if new_parties != (old_parties or ""):
            changes.append((id_, {
                "case_number": case_number, "old_parties": old_parties or "",
                "judge": judge, "court": court, "matter": matter,
                "decision_type": decision_type, "full_text": text,
            }, new_parties))
        if i % 20000 == 0:
            elapsed = time.time() - t0
            print(f"  ...{i}/{len(rows)} עובדו ({elapsed:.0f}s) - נבדקו={checked} "
                  f"שונו={len(changes)} דילוגים(no_path={skipped_no_path} "
                  f"read_err={skipped_read_err} empty={skipped_empty})", flush=True)
    skip_log.close()

    print(f"parties: {checked} נבדקו, {len(changes)} ישתנו. "
          f"דילוגים: no_path={skipped_no_path} read_err={skipped_read_err} "
          f"empty={skipped_empty} (פירוט מלא: {LOG_SKIPPED})", flush=True)

    for i, (id_, old, new_parties) in enumerate(changes, 1):
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
        if i % 500 == 0:
            conn.commit()
    conn.commit()
    return changes


def sync_parties_to_turso(changes: list[tuple[int, dict, str]]) -> None:
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
    chunk = 30
    for i in range(0, len(statements), chunk):
        turso_sync._run_batch(statements[i:i + chunk])
        if (i // chunk) % 50 == 0:
            print(f"  ...Turso parties sync: {i}/{len(statements)} statements", flush=True)
    print(f"Turso: parties סונכרן ({len(changes)} רשומות).", flush=True)


def find_duplicate_groups_cross_case(conn: sqlite3.Connection) -> list[list[int]]:
    """כפילויות שבהן לכל עותק case_number *שונה* (תיק מאוחד, כל עותק
    מתויג לפי מספר-התיק המוביל בכותרת שלו) - מתאימה לפי
    (court, judge, decision_date, text_length) בלבד."""
    rows = conn.execute("""
        SELECT court, judge, decision_date, text_length, GROUP_CONCAT(id)
        FROM verdicts
        WHERE has_document=1 AND decision_date != '' AND text_length > 1500
        GROUP BY court, judge, decision_date, text_length
        HAVING COUNT(*) > 1
    """).fetchall()
    return [[int(x) for x in r[4].split(",")] for r in rows]


def pick_survivor(ids: list[int]) -> tuple[int, list[int]]:
    lengths = {id_: len(storage.fetch_fulltext(id_)) for id_ in ids}
    survivor = max(lengths, key=lengths.get)
    return survivor, [id_ for id_ in ids if id_ != survivor]


def delete_one(conn: sqlite3.Connection, id_: int) -> None:
    row = conn.execute(
        "SELECT parties, judge, court, case_number, matter, decision_type FROM verdicts WHERE id=?",
        (id_,),
    ).fetchone()
    if row is None:
        return
    parties, judge, court, case_number, matter, decision_type = row
    full_text = storage.fetch_fulltext(id_)
    conn.execute(
        "INSERT INTO verdicts_fts(verdicts_fts, rowid, parties, judge, court, "
        "case_number, matter, decision_type, full_text) VALUES ('delete',?,?,?,?,?,?,?,?)",
        (id_, parties, judge, court, case_number, matter, decision_type, full_text),
    )
    conn.execute("DELETE FROM verdicts WHERE id=?", (id_,))
    if config.TURSO_DATABASE_URL:
        turso_sync.delete_verdicts([{
            "id": id_, "case_number": case_number, "parties": parties, "judge": judge,
            "court": court, "matter": matter, "decision_type": decision_type,
            "full_text": full_text,
        }])
    storage.delete_fulltext(id_)


def fix_duplicates(conn: sqlite3.Connection) -> int:
    groups = find_duplicate_groups_cross_case(conn)
    print(f"כפילויות (ללא דרישת case_number זהה): {len(groups)} קבוצות נמצאו.", flush=True)
    total_deleted = 0
    for ids in groups:
        survivor, to_delete = pick_survivor(ids)
        for id_ in to_delete:
            delete_one(conn, id_)
            total_deleted += 1
        conn.commit()
    print(f"כפילויות: {total_deleted} רשומות נמחקו.", flush=True)
    return total_deleted


if __name__ == "__main__":
    conn = sqlite3.connect(str(config.DB_PATH))

    p_changes = fix_parties(conn)
    conn.close()
    sync_parties_to_turso(p_changes)

    # מתחילים חיבור טרי אחרי סנכרון parties, כדי שכפילויות ייבחרו
    # (pick_survivor) מתוך full_text עדכני
    conn = sqlite3.connect(str(config.DB_PATH))
    n_dup = fix_duplicates(conn)
    conn.close()

    print(f"סיום כולל: {len(p_changes)} תיקוני parties, {n_dup} כפילויות הוסרו.", flush=True)
