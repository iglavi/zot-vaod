"""הרצה חד-פעמית (ראו README.md: "תכנון ארכיטקטורה עתידי"): מעלה את הטקסט
המלא של כל פסקי הדין הקיימים ל-R2 (fulltext/{id}.txt.gz), ואז בונה עותק
חדש של האינדקס (data/index_turso.db) בסכמה החדשה - בלי עמודת full_text,
עם text_length, ו-verdicts_fts כטבלה contentless (content='') - משמר את
כל ה-id-ים הקיימים בדיוק כפי שהם (הכרחי: מפתחות ה-R2 תלויים ב-id).

data/index.db המקורי לא נוגע כלל - העותק החדש נבנה בקובץ נפרד, כדי
שתקלה באמצע התהליך לא תסכן את המאגר הקיים.

לאחר שהסקריפט מסתיים בהצלחה, מעלים את data/index_turso.db ל-Turso:
    turso db shell giluy-naot < (ייצוא) / turso db import data/index_turso.db

הרצה: python _migrate_to_r2_turso.py
"""
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, ".")
from zot import storage  # noqa: E402

SRC_DB = Path("data/index.db")
DST_DB = Path("data/index_turso.db")
MANIFEST = Path("data/.migration_fulltext_uploaded.txt")
UPLOAD_WORKERS = 40


def _load_manifest() -> set[int]:
    if MANIFEST.exists():
        return {int(x) for x in MANIFEST.read_text(encoding="utf-8").split() if x.strip()}
    return set()


def upload_all_fulltext() -> int:
    """מעלה ל-R2 את הטקסט המלא של כל הרשומות (בלי לגעת ב-DB) - עמיד
    להפרעה: manifest עוקב אחרי מה שכבר הועלה, אז הרצה חוזרת ממשיכה מאיפה
    שנעצרה במקום להתחיל הכול מחדש."""
    conn = sqlite3.connect(f"file:{SRC_DB.as_posix()}?mode=ro", uri=True)
    done = _load_manifest()
    rows = conn.execute(
        "SELECT id, full_text FROM verdicts WHERE full_text IS NOT NULL AND full_text != ''"
    ).fetchall()
    conn.close()
    todo = [(id_, text) for id_, text in rows if id_ not in done]
    print(f"{len(rows)} רשומות עם טקסט מלא, {len(done)} כבר הועלו, {len(todo)} נותרו.", flush=True)
    if not todo:
        return 0

    client = storage._client()
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    manifest_fh = MANIFEST.open("a", encoding="utf-8")
    uploaded = errors = 0
    t0 = time.monotonic()
    try:
        with ThreadPoolExecutor(max_workers=UPLOAD_WORKERS) as pool:
            futures = {pool.submit(storage.upload_fulltext, id_, text, client): id_
                       for id_, text in todo}
            for i, fut in enumerate(as_completed(futures), 1):
                id_ = futures[fut]
                ok = fut.result()
                if ok:
                    uploaded += 1
                    manifest_fh.write(f"{id_}\n")
                else:
                    errors += 1
                if i % 2000 == 0 or i == len(todo):
                    manifest_fh.flush()
                    elapsed = time.monotonic() - t0
                    rate = i / elapsed if elapsed else 0
                    print(f"  ...{i}/{len(todo)} ({uploaded} הועלו, {errors} שגיאות) "
                          f"- {elapsed:.0f}s, {rate:.1f}/s", flush=True)
    finally:
        manifest_fh.close()
    print(f"העלאה הסתיימה: {uploaded} הועלו, {errors} שגיאות.", flush=True)
    return errors


def _snapshot(src: Path, dst: Path) -> None:
    """יוצר עותק עקבי דרך ה-backup API (כמו storage._snapshot_db) - לא
    open/copy גולמי, כדי לא להסתכן בעותק פגום אם תהליך אחר כותב ל-DB
    באותו רגע."""
    if dst.exists():
        dst.unlink()
    s = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    d = sqlite3.connect(str(dst))
    try:
        s.backup(d)
    finally:
        d.close()
        s.close()


def migrate_schema() -> None:
    """בונה את data/index_turso.db מעותק של data/index.db, וממיר את הסכמה
    שלו: verdicts_fts הופך ל-contentless, נוספת text_length, ו-full_text
    יורדת - כל זאת תוך שמירה מדויקת על ה-id-ים הקיימים (ALTER TABLE/DROP
    COLUMN לא משנים rowid)."""
    print(f"יוצר עותק {SRC_DB} -> {DST_DB}...", flush=True)
    _snapshot(SRC_DB, DST_DB)

    conn = sqlite3.connect(str(DST_DB))
    print("בונה מחדש את verdicts_fts כ-contentless...", flush=True)
    conn.execute("DROP TABLE verdicts_fts")
    conn.executescript("""
        CREATE VIRTUAL TABLE verdicts_fts USING fts5(
            parties, judge, court, case_number, matter, decision_type, full_text,
            content='',
            tokenize='unicode61 remove_diacritics 2'
        );
    """)
    conn.execute("""
        INSERT INTO verdicts_fts(rowid, parties, judge, court, case_number,
                                  matter, decision_type, full_text)
        SELECT id, parties, judge, court, case_number, matter, decision_type,
               full_text
        FROM verdicts
    """)
    conn.commit()

    print("מוסיף text_length ומוריד full_text...", flush=True)
    conn.execute("ALTER TABLE verdicts ADD COLUMN text_length INTEGER DEFAULT 0")
    conn.execute("UPDATE verdicts SET text_length = LENGTH(COALESCE(full_text, ''))")
    conn.commit()
    conn.execute("ALTER TABLE verdicts DROP COLUMN full_text")
    conn.commit()

    cols = [r[1] for r in conn.execute("PRAGMA table_info(verdicts)").fetchall()]
    total = conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0]
    fts_total = conn.execute("SELECT COUNT(*) FROM verdicts_fts").fetchone()[0]
    conn.close()
    print(f"סכמה חדשה: {cols}", flush=True)
    print(f"סה\"כ רשומות: {total}, רשומות ב-FTS: {fts_total}.", flush=True)
    if total != fts_total:
        print("אזהרה: מספר הרשומות ב-verdicts וב-verdicts_fts לא תואם!", flush=True)


if __name__ == "__main__":
    errors = upload_all_fulltext()
    if errors:
        print(f"אזהרה: {errors} העלאות נכשלו - בדקו/הריצו שוב לפני שממשיכים "
              f"ל-turso db import.", flush=True)
    migrate_schema()
    print("סיום. השלב הבא: turso db import של data/index_turso.db (ראו README).",
          flush=True)
