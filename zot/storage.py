"""העלאת קבצי פסקי הדין המקוריים (PDF/Word) לאחסון חיצוני (Cloudflare R2).

זה מה שמאפשר לאתר הציבורי להציע גם את הקובץ המקורי להורדה, בלי לתלות
את הארכיון כולו במחשב הבית (ובלי לדחוף קבצים כבדים ל-git).

מוגדר דרך משתני סביבה / .env (ראו .env.example):
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET

אם לא מוגדר — פשוט מדלג בשקט (ההעלאה אופציונלית).

מריצים בעצמו לבדיקה:  python -m zot.storage
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import config

# מספר העלאות מקבילות ל-R2. בניגוד להורדות מ-decisions.court.gov.il (ששם
# צריך זהירות בגלל WAF שחוסם התנהגות לא-אנושית), R2 הוא שירות ענן חזק
# שמיועד לעומס מקביל — אין סיבה להעלות קובץ-אחר-קובץ.
_UPLOAD_WORKERS = 10

_MANIFEST = config.DATA_DIR / ".r2_uploaded.txt"
_EXT = (".pdf", ".docx", ".doc")

# קובץ האינדקס (index.db) גדל מעבר למגבלת הגודל של GitHub (100MB) — הוא
# מתארח ב-R2 במקום להידחף ל-git. האתר מוריד אותו מכאן בהפעלה, ובודק
# מדי פעם אם יש גרסה חדשה יותר (לפי ETag) בלי להוריד מחדש שלא לצורך.
INDEX_KEY = "index/index.db"


def _client():
    if not (config.R2_ACCOUNT_ID and config.R2_ACCESS_KEY_ID and config.R2_SECRET_ACCESS_KEY):
        return None
    import boto3  # ייבוא עצל: לא נדרש אם R2 לא מוגדר
    from botocore.config import Config

    # index.db הוא קובץ גדול (מאות MB) — timeout ברירת המחדל של boto3
    # (60 שניות) עלול לא להספיק להורדה שלו מתשתית מוגבלת כמו Streamlit
    # Cloud, מה שגרם לכשל שקט (נתפס כ-Exception ונופל בחזרה לעותק ישן).
    return boto3.client(
        "s3",
        endpoint_url=f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(connect_timeout=60, read_timeout=600,
                      retries={"max_attempts": 3, "mode": "adaptive"}),
    )


def _load_manifest(manifest_path: Path) -> set[str]:
    if manifest_path.exists():
        return set(manifest_path.read_text(encoding="utf-8").splitlines())
    return set()


def upload_new(verbose: bool = True, docs_dir: Path | None = None,
               manifest_path: Path | None = None, key_prefix: str = "") -> dict:
    """מעלה ל-R2 כל קובץ שעדיין לא הועלה, במקביל (כמה קבצים בו-זמנית —
    R2 שירות ענן חזק, לא רגיש לזה כמו אתרים ממשלתיים מוגני-WAF). עוקב
    אחרי מה שכבר הועלה בקובץ manifest נפרד לכל מקור, כדי לאפשר כמה
    מקורות/תהליכים בו-זמנית בלי להתנגש.

    docs_dir/manifest_path/key_prefix מאפשרים להשתמש באותה פונקציה עבור
    מקורות שונים (למשל: החלטות בתי המשפט מול פסקי דין של העליון) — כל
    אחד עם תיקיית מקור, יומן מעקב, ותחילית-נתיב משלו בדלי ה-R2."""
    client = _client()
    if client is None or not config.R2_BUCKET:
        if verbose:
            print("R2 לא מוגדר (חסרים משתני סביבה) — מדלג על העלאה חיצונית.")
        return {"configured": False, "uploaded": 0, "skipped": 0, "errors": 0}

    docs_dir = Path(docs_dir or config.DOCS_DIR)
    manifest_path = Path(manifest_path or _MANIFEST)
    uploaded_set = _load_manifest(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    todo = []
    skipped = 0
    for f in sorted(docs_dir.rglob("*")):
        if not (f.is_file() and f.suffix.lower() in _EXT):
            continue
        rel = f.relative_to(docs_dir).as_posix()
        if rel in uploaded_set:
            skipped += 1
            continue
        todo.append((f, rel))

    uploaded = errors = 0
    lock = threading.Lock()
    manifest_fh = manifest_path.open("a", encoding="utf-8")

    def _upload_one(item):
        f, rel = item
        client.upload_file(str(f), config.R2_BUCKET, key_prefix + rel)
        return rel

    try:
        with ThreadPoolExecutor(max_workers=_UPLOAD_WORKERS) as pool:
            futures = {pool.submit(_upload_one, item): item for item in todo}
            for fut in as_completed(futures):
                f, rel = futures[fut]
                try:
                    fut.result()
                except Exception as e:  # noqa: BLE001
                    with lock:
                        errors += 1
                    if verbose:
                        print(f"  שגיאה בהעלאת {rel}: {e}")
                    continue
                with lock:
                    manifest_fh.write(rel + "\n")
                    manifest_fh.flush()
                    uploaded += 1
    finally:
        manifest_fh.close()

    if verbose:
        print(f"העלאה ל-R2: {uploaded} קבצים חדשים, {skipped} כבר הועלו, {errors} שגיאות.")
    return {"configured": True, "uploaded": uploaded, "skipped": skipped, "errors": errors}


_UPLOAD_INDEX_RETRIES = 4


def _snapshot_db(local_path: Path) -> Path:
    """יוצר עותק עקבי של index.db דרך ה-backup API של sqlite3, גם אם תהליך
    אחר כותב אליו באותו הרגע. בניגוד להעתקת קובץ גולמית (shutil/open) —
    שיכולה להיתקע עם PermissionError לזמן ממושך אם תהליך אחר מחזיק
    טרנזקציית כתיבה פתוחה — ה-backup API הוא המנגנון הרשמי של SQLite
    בדיוק בשביל זה, ומחזיר עותק תקין תמיד. index.db עצמו רץ במצב WAL,
    שמאפשר קריאה מקבילה לכתיבה, אבל העתקה גולמית של הקובץ הראשי בלי
    ה-WAL עדיין לא בטוחה — לכן עדיף backup API על פני shutil.copy2."""
    import sqlite3

    tmp = local_path.with_name(local_path.stem + "_upload_snapshot" + local_path.suffix)
    src = sqlite3.connect(f"file:{local_path.as_posix()}?mode=ro", uri=True, timeout=30)
    dst = sqlite3.connect(str(tmp))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return tmp


def upload_index(local_path: Path | None = None, verbose: bool = True) -> dict:
    """מעלה את קובץ האינדקס (index.db) ל-R2 — משם האתר מוריד אותו בהפעלה,
    במקום דרך git (שחוסם קבצים מעל 100MB).

    לפני ההעלאה יוצר עותק עקבי מקומי (ראו _snapshot_db) ומעלה אותו במקום
    הקובץ החי — כך שאין תלות בכך שאף תהליך אחר לא כותב לאינדקס בדיוק
    באותו רגע. מנסה שוב עם המתנה קצרה בין ניסיונות ההעלאה עצמה, למקרה של
    כשל רשת חולף (ConnectionClosedError וכדומה)."""
    client = _client()
    if client is None or not config.R2_BUCKET:
        if verbose:
            print("R2 לא מוגדר — לא ניתן להעלות את האינדקס.")
        return {"configured": False}
    local_path = Path(local_path or config.DB_PATH)

    snapshot = None
    upload_path = local_path
    try:
        snapshot = _snapshot_db(local_path)
        upload_path = snapshot
    except Exception as e:  # noqa: BLE001
        if verbose:
            print(f"  לא הצלחתי ליצור עותק עקבי ({e}) — מעלה ישירות את הקובץ החי.")

    try:
        last_err = None
        for attempt in range(_UPLOAD_INDEX_RETRIES):
            try:
                client.upload_file(str(upload_path), config.R2_BUCKET, INDEX_KEY)
                if verbose:
                    print(f"האינדקס ({upload_path.stat().st_size / 1e6:.1f}MB) הועלה ל-R2.")
                return {"configured": True}
            except Exception as e:  # noqa: BLE001
                last_err = e
                if verbose:
                    print(f"  ניסיון {attempt + 1}/{_UPLOAD_INDEX_RETRIES} להעלאת "
                          f"האינדקס נכשל ({e}) — מנסה שוב בעוד {5 * (attempt + 1)}s...")
                time.sleep(5 * (attempt + 1))

        if verbose:
            print(f"העלאת האינדקס נכשלה סופית אחרי {_UPLOAD_INDEX_RETRIES} ניסיונות: {last_err}")
        return {"configured": True, "error": str(last_err)}
    finally:
        if snapshot is not None and snapshot.exists():
            snapshot.unlink(missing_ok=True)


def sync_index(local_path: Path | None = None) -> bool:
    """מוריד את index.db מ-R2 אם אין עותק מקומי, או אם ב-R2 יש גרסה חדשה
    יותר (ETag שונה מזו שסונכרנה בפעם הקודמת). מחזיר True אם יש בסיום
    עותק מקומי תקין (חדש או ישן — עדיף משהו על כלום אם ההורדה נכשלה)."""
    local_path = Path(local_path or config.DB_PATH)
    client = _client()
    if client is None or not config.R2_BUCKET:
        return local_path.exists()

    marker = local_path.parent / f".{local_path.name}.synced_etag"
    try:
        remote_etag = client.head_object(Bucket=config.R2_BUCKET, Key=INDEX_KEY)["ETag"]
    except Exception as e:  # noqa: BLE001
        print(f"sync_index: head_object נכשל ({e}) — משתמש בעותק המקומי הקיים אם יש.")
        return local_path.exists()

    local_etag = marker.read_text(encoding="utf-8").strip() if marker.exists() else None
    if local_path.exists() and remote_etag == local_etag:
        return True

    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = local_path.with_name(local_path.name + ".downloading")
        client.download_file(config.R2_BUCKET, INDEX_KEY, str(tmp))
        tmp.replace(local_path)
        marker.write_text(remote_etag, encoding="utf-8")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"sync_index: הורדת index.db מ-R2 נכשלה ({e}) — משתמש בעותק המקומי הישן אם יש.")
        return local_path.exists()


if __name__ == "__main__":
    upload_new()
