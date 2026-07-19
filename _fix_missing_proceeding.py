"""הרצה חד-פעמית: ממלא proceeding ('סוג הליך') לרשומות קיימות שבהן הוא ריק,
לפי case_type ('סוג עניין') - ראו zot/case_types.py: PROCEEDING_BY_CASE_TYPE.

proceeding הגיע היסטורית רק מעמודת ה-CSV המקורית ("הליך"), שקיימת רק לחלק
זעיר מהמאגר - נמצא בפועל 227 מתוך 678,397 רשומות (0.03%). כל מסמך שנוסף
מאז (הורדות יומיות, ארכיון העליון) קיבל proceeding ריק, כי הוא מעולם לא
נגזר מ-case_type בזמן ה-ingest (תוקן כעת ב-zot/ingest.py: _insert_verdict,
עבור רשומות עתידיות - הסקריפט הזה מטפל ברשומות שכבר קיימות).

מעדכן גם את הקובץ המקומי (data/index.db) וגם את Turso (אם מוגדר).

הרצה: python _fix_missing_proceeding.py
"""
import sqlite3
import sys

sys.path.insert(0, ".")
from zot import config, turso_sync  # noqa: E402
from zot.case_types import PROCEEDING_BY_CASE_TYPE  # noqa: E402


def fix_local() -> int:
    conn = sqlite3.connect(str(config.DB_PATH))
    total = 0
    for case_type, proceeding in PROCEEDING_BY_CASE_TYPE.items():
        cur = conn.execute(
            "UPDATE verdicts SET proceeding = ? WHERE proceeding = '' AND case_type = ?",
            (proceeding, case_type),
        )
        total += cur.rowcount
    conn.commit()
    conn.close()
    print(f"מקומי: עודכנו {total} רשומות.", flush=True)
    return total


def fix_turso() -> int:
    if not config.TURSO_DATABASE_URL:
        print("Turso לא מוגדר - מדלג.", flush=True)
        return 0
    statements = [
        ("UPDATE verdicts SET proceeding = ? WHERE proceeding = '' AND case_type = ?",
         [proceeding, case_type])
        for case_type, proceeding in PROCEEDING_BY_CASE_TYPE.items()
    ]
    turso_sync._run_batch(statements)
    print(f"Turso: הורצו {len(statements)} עדכוני UPDATE (batch יחיד).", flush=True)
    return len(statements)


if __name__ == "__main__":
    fix_local()
    fix_turso()
    print("סיום.", flush=True)
