"""הרצה חד-פעמית: מנקה כפילויות אמיתיות - אותו פסק דין בדיוק (בד"כ פסק
דין מאוחד של כמה ערעורים, כמו ע"א 4584/10 + ע"א 4699/10) שהתארכן פעמיים
בארכיון בית המשפט העליון תחת יותר ממספר-תיק אחד, ולכן נכנס למאגר כשתי
(או יותר) רשומות נפרדות עם אותו case_number, decision_date, court, judge
וגם text_length זהה (מחייבים גם התאמת text_length - לא רק שאר השדות -
כדי לא לזהות בטעות כ'כפילות' שתי החלטות שונות ולגיטימיות שניתנו לאותו
תיק באותו יום, שקורה בפועל הרבה יותר: 47,807 שורות "תואמות" כשלא דורשים
גם text_length זהה, לעומת 170 בלבד כשדורשים - ואומת ידנית שההבדלים
בטקסט המלא בין ה"כפילויות" האלה זניחים/עיצוביים, לא תוכן שונה).

מחזיקה את הרשומה עם הטקסט המלא הארוך ביותר בקבוצה (הכי סביר להיות שלם),
מוחקת את השאר - גם מ-verdicts/verdicts_fts (מקומי+Turso) וגם את אובייקט
הטקסט המלא שלהן מ-R2 (storage.delete_fulltext).

הרצה: python _fix_duplicate_verdicts.py
"""
import sqlite3
import sys

sys.path.insert(0, ".")
from zot import config, storage, turso_sync  # noqa: E402


def find_duplicate_groups(conn: sqlite3.Connection) -> list[list[int]]:
    rows = conn.execute("""
        SELECT case_number, decision_date, court, judge, text_length, GROUP_CONCAT(id)
        FROM verdicts
        WHERE has_document=1 AND case_number != '' AND decision_date != '' AND text_length > 1500
        GROUP BY case_number, decision_date, court, judge, text_length
        HAVING COUNT(*) > 1
    """).fetchall()
    return [[int(x) for x in r[5].split(",")] for r in rows]


def pick_survivor(conn: sqlite3.Connection, ids: list[int]) -> tuple[int, list[int]]:
    """שומרת את הרשומה עם ה-full_text הארוך ביותר בפועל (לא רק text_length
    המאוחסן, שיכול להיות זהה - צריך את האורך האמיתי כדי לבחור בין
    כפילויות עם text_length שווה)."""
    lengths = {id_: len(storage.fetch_fulltext(id_)) for id_ in ids}
    survivor = max(lengths, key=lengths.get)
    to_delete = [id_ for id_ in ids if id_ != survivor]
    return survivor, to_delete


def delete_one(conn: sqlite3.Connection, id_: int) -> None:
    """מוחקת רשומה בודדת: קוראת את הערכים הישנים (נדרשים למחיקת ה-FTS
    contentless, ראו zot/ingest.py: SCHEMA) פעם אחת, ואז מוחקת מקומית,
    מ-Turso, ומ-R2 (אובייקט הטקסט המלא)."""
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


if __name__ == "__main__":
    conn = sqlite3.connect(str(config.DB_PATH))
    groups = find_duplicate_groups(conn)
    print(f"{len(groups)} קבוצות כפילויות נמצאו.", flush=True)

    total_deleted = 0
    for ids in groups:
        survivor, to_delete = pick_survivor(conn, ids)
        for id_ in to_delete:
            delete_one(conn, id_)
            total_deleted += 1
        conn.commit()
    conn.close()
    print(f"סיום: {total_deleted} רשומות כפולות נמחקו (מקומי + Turso + R2 fulltext).", flush=True)
