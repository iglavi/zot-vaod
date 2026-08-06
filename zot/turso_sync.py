"""מסנכרן רשומות מטא-דאטה+FTS חדשות מהאינדקס המקומי (data/index.db, שנבנה
ע"י zot.ingest) אל Turso - ההרצה היומית הרגילה (לא ההעברה החד-פעמית, ראו
_migrate_to_r2_turso.py). מדלג בשקט אם TURSO_DATABASE_URL לא מוגדר.

משתמש ב-HTTP API של Turso (Hrana over HTTP, /v2/pipeline) דרך requests
במקום בחבילת libsql - כי הסקריפט הזה רץ מקומית דרך Windows Task Scheduler
(fetch_daily.py/ingest_loop.py) על Python 3.14, שעבורו אין wheel בנוי
מראש ל-libsql (ורק ל-requests, שכבר תלות קיימת בפרויקט). zot/search.py
(שרץ ב-Streamlit Cloud, עם גרסת Python תואמת) ממשיך להשתמש ב-libsql עצמו.

בניגוד להעלאת index.db השלמה (כפי שהיה עם R2 לפני המעבר), כאן דוחפים רק
את הרשומות *החדשות* מאז ההרצה הקודמת - זיהוי לפי marker מקומי (מקסימום
id שכבר סונכרן), לא replace גורף. הטקסט המלא של הרשומות החדשות כבר הועלה
ל-R2 ע"י zot.ingest.build() עצמו (ראו pending_uploads שם) - כאן רק נשלף
בחזרה משם כדי להזין את אינדקס ה-FTS המרוחק (contentless - חייב לקבל את
הטקסט בזמן ה-INSERT, לא רק את ה-rowid).

הרצה (אחרי ingest.build()):  python -m zot.turso_sync
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from . import config, storage

_MARKER = Path(config.DATA_DIR) / ".turso_synced_max_id"
_CHUNK_SIZE = 300  # רשומות לכל בקשת HTTP (כל רשומה = 2 statements: verdicts + fts)

# נעילה בין-תהליכית: sync() קורא/כותב את _MARKER בלי טרנזקציה, אז שתי
# הרצות בו-זמנית (fetch_daily.py + ingest_and_cleanup.py, למשל) יכולות
# לקרוא את אותו since_id, לחשב טווחי-id חופפים, ולהתנגש ב-INSERT השני
# (UNIQUE constraint על verdicts.id בטורסו - נצפה בפועל). קובץ-נעילה
# בלעדי (O_EXCL) מבטיח ריצה טורית בין קוראים ל-sync(); "גונבים" נעילה
# תקועה אחרי _LOCK_STALE_SEC כדי לא להיתקע לצמיתות אם מחזיק-הנעילה קרס.
_LOCK = Path(config.DATA_DIR) / ".turso_sync.lock"
_LOCK_STALE_SEC = 1800
_LOCK_WAIT_SEC = 120


def _acquire_lock() -> None:
    _LOCK.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + _LOCK_WAIT_SEC
    while True:
        try:
            fd = os.open(_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return
        except FileExistsError:
            try:
                if time.time() - _LOCK.stat().st_mtime > _LOCK_STALE_SEC:
                    _LOCK.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(
                    "turso_sync: לא הצליח לקבל נעילה תוך זמן סביר - תהליך אחר מסנכרן"
                )
            time.sleep(1)


def _release_lock() -> None:
    _LOCK.unlink(missing_ok=True)

_VERDICT_COLUMNS = [
    "id", "case_number", "parties", "court", "proceeding", "case_type", "matter",
    "decision_type", "decision_nature", "filed_date", "decision_date", "judge",
    "filename", "file_relpath", "file_relpath_pdf", "file_relpath_docx",
    "has_document", "text_length", "structural_summary", "is_supreme",
]


def _last_synced_id() -> int:
    if _MARKER.exists():
        try:
            return int(_MARKER.read_text(encoding="utf-8").strip())
        except ValueError:
            return 0
    return 0


def _typed_arg(v) -> dict:
    """ממיר ערך פייתון לפורמט ה-typed-value של Hrana (פרוטוקול ה-HTTP של
    Turso) - מספרים שלמים מועברים כמחרוזת (כך ש-JSON לא יאבד דיוק ב-int64
    גדולים), לא כמספר JSON גולמי."""
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    return {"type": "text", "value": str(v)}


def _http_url() -> str:
    # libsql://xxx.turso.io -> https://xxx.turso.io/v2/pipeline
    base = config.TURSO_DATABASE_URL
    if base.startswith("libsql://"):
        base = "https://" + base[len("libsql://"):]
    return base.rstrip("/") + "/v2/pipeline"


def _run_batch(statements: list[tuple[str, list]]) -> None:
    """שולח קבוצת statements אחת ל-Turso (עטופה ב-BEGIN/COMMIT לאטומיות),
    ובודק שאף statement לא נכשל (ה-HTTP status הוא תמיד 200 - כשלים
    מדווחים per-statement בגוף התשובה)."""
    import requests

    reqs = [{"type": "execute", "stmt": {"sql": "BEGIN"}}]
    for sql, args in statements:
        reqs.append({"type": "execute",
                     "stmt": {"sql": sql, "args": [_typed_arg(a) for a in args]}})
    reqs.append({"type": "execute", "stmt": {"sql": "COMMIT"}})
    reqs.append({"type": "close"})

    # Turso's underlying SQLite engine can return SQLITE_BUSY ("database is
    # locked") under concurrent writers (e.g. two sync callers racing, or a
    # heavy batch from one still committing) - transient, so retry with
    # backoff instead of failing the whole batch. Same class of fix as the
    # local index.db lock handling in 65a0f07.
    delay = 1.0
    for attempt in range(6):
        resp = requests.post(
            _http_url(),
            headers={"Authorization": f"Bearer {config.TURSO_AUTH_TOKEN}",
                     "Content-Type": "application/json"},
            json={"requests": reqs},
            timeout=120,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        errors = [r for r in results if r.get("type") == "error"]
        if not errors:
            return
        busy = any("locked" in str(e.get("error", "")).lower()
                    or (e.get("error") or {}).get("code") == "SQLITE_BUSY"
                    for e in errors)
        if not busy or attempt == 5:
            raise RuntimeError(f"Turso sync statement failed: {errors[0]['error']}")
        time.sleep(delay)
        delay = min(delay * 2, 20)


def delete_verdicts(rows: list[dict]) -> int:
    """מוחק רשומות מ-Turso (משמש ע"י confidentiality_bot.py, בנוסף למחיקה
    המקומית) - כל dict ב-rows צריך להכיל id, parties, judge, court,
    case_number, matter, decision_type, full_text (הערכים ה'ישנים', לפני
    המחיקה - נדרשים כדי למחוק מ-verdicts_fts, שהיא טבלה contentless: לא
    ניתן לבצע בה DELETE רגיל, רק INSERT...VALUES('delete', ...) עם הערכים
    הישנים במפורש - ראו zot/ingest.py: SCHEMA). מדלג בשקט אם Turso לא מוגדר.

    חשוב מבחינת חיסיון: בלי הפונקציה הזו, תיק שהוסר מקומית (למשל בעקבות
    הודעת חיסיון) היה נשאר גלוי וניתן לחיפוש באתר החי (שמדבר עם Turso,
    לא עם הקובץ המקומי) - המחיקה המקומית לבדה לא מספיקה."""
    if not config.TURSO_DATABASE_URL or not rows:
        return 0
    statements: list[tuple[str, list]] = []
    for r in rows:
        statements.append((
            "INSERT INTO verdicts_fts(verdicts_fts, rowid, parties, judge, court, "
            "case_number, matter, decision_type, full_text) VALUES ('delete',?,?,?,?,?,?,?,?)",
            [r["id"], r["parties"], r["judge"], r["court"], r["case_number"],
             r["matter"], r["decision_type"], r["full_text"]],
        ))
        statements.append(("DELETE FROM verdicts WHERE id = ?", [r["id"]]))
    _run_batch(statements)
    return len(rows)


def sync(db_path: Path | None = None, verbose: bool = True) -> dict:
    """דוחף ל-Turso כל רשומה מקומית עם id > הסימון האחרון. מחזיר סטטיסטיקה.

    נעול בין-תהליכית (ראו _acquire_lock) - קריאה מקבילית שנייה ל-sync()
    (למשל fetch_daily.py מול ingest_and_cleanup.py הרץ ברקע) ממתינה, לא
    רצה בו-זמנית, כדי לא לחשב since_id חופף פעמיים ולהתנגש ב-INSERT."""
    if not config.TURSO_DATABASE_URL:
        if verbose:
            print("Turso לא מוגדר - מדלג על סנכרון מרוחק.")
        return {"configured": False, "synced": 0}

    import sqlite3

    _acquire_lock()
    try:
        local_path = Path(db_path or config.DB_PATH)
        since_id = _last_synced_id()

        local = sqlite3.connect(f"file:{local_path.as_posix()}?mode=ro", uri=True)
        cols = ",".join(_VERDICT_COLUMNS)
        v_cols = ("id", "parties", "judge", "court", "case_number", "matter", "decision_type")
        rows = local.execute(
            f"SELECT {cols} FROM verdicts WHERE id > ? ORDER BY id", (since_id,)
        ).fetchall()
        ft_rows = {r[0]: r for r in local.execute(
            f"SELECT {','.join(v_cols)} FROM verdicts WHERE id > ? ORDER BY id", (since_id,)
        ).fetchall()}
        local.close()

        if not rows:
            if verbose:
                print(f"אין רשומות חדשות מאז id={since_id} - כלום לסנכרן.")
            return {"configured": True, "synced": 0}

        if verbose:
            print(f"{len(rows)} רשומות חדשות (id > {since_id}) - שולף טקסט מלא מ-R2 ומסנכרן ל-Turso...")

        ids = [r[0] for r in rows]
        texts = storage.fetch_fulltexts(ids)

        v_placeholders = ",".join("?" * len(_VERDICT_COLUMNS))
        synced = 0
        for start in range(0, len(rows), _CHUNK_SIZE):
            chunk = rows[start:start + _CHUNK_SIZE]
            statements: list[tuple[str, list]] = []
            max_id_in_chunk = since_id
            for row in chunk:
                # OR IGNORE (not plain INSERT): a chunk can partially commit on
                # Turso's side and then the HTTP response never arrive (seen live -
                # requests.exceptions.ConnectionError mid-batch) - the marker then
                # never advances for that chunk, so the NEXT sync() attempt re-sends
                # the exact same rows and would otherwise hard-fail on
                # UNIQUE constraint failed: verdicts.id instead of just re-confirming
                # what's already there and moving the marker forward.
                statements.append(
                    (f"INSERT OR IGNORE INTO verdicts ({cols}) VALUES ({v_placeholders})", list(row))
                )
                id_ = row[0]
                ft = ft_rows[id_]
                statements.append((
                    "INSERT OR IGNORE INTO verdicts_fts(rowid, parties, judge, court, case_number, "
                    "matter, decision_type, full_text) VALUES (?,?,?,?,?,?,?,?)",
                    [id_, ft[1], ft[2], ft[3], ft[4], ft[5], ft[6], texts.get(id_, "")],
                ))
                # מחזיק את distinct_values מעודכן גם ב-Turso (ראו search._distinct_values
                # ו-ingest._insert_verdict - אותו רעיון, גם כאן) - בלעדיו ערך חדש
                # לגמרי לא יופיע בתפריטי הסינון עד לבאקפיל ידני נוסף.
                for field, val in (("court", row[3]), ("proceeding", row[4]), ("case_type", row[5])):
                    if val:
                        statements.append((
                            "INSERT OR IGNORE INTO distinct_values(field, value) VALUES (?,?)",
                            [field, val],
                        ))
                max_id_in_chunk = max(max_id_in_chunk, id_)
            _run_batch(statements)
            synced += len(chunk)
            _MARKER.parent.mkdir(parents=True, exist_ok=True)
            _MARKER.write_text(str(max_id_in_chunk), encoding="utf-8")
            if verbose and len(rows) > _CHUNK_SIZE:
                print(f"  ...{synced}/{len(rows)} סונכרנו", flush=True)

        if verbose:
            print(f"סונכרנו {synced} רשומות ל-Turso.")
        return {"configured": True, "synced": synced}
    finally:
        _release_lock()


if __name__ == "__main__":
    sync()
