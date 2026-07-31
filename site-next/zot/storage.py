"""העלאת קבצי פסקי הדין המקוריים (PDF/Word) לאחסון חיצוני (Cloudflare R2),
וכן העלאה/שליפה של טקסט פסק-הדין המלא (מסמך בודד לכל פסק דין, ראו
upload_fulltext/fetch_fulltext(s)) - הטקסט המלא כבר לא חי בתוך index.db
עצמו (ראו zot/ingest.py), אלא נשלף מ-R2 לפי דרישה בלבד.

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


def _fast_client():
    """כמו _client(), אבל עם timeout קצר בהרבה - לשימוש בנתיב אינטראקטיבי
    (שליפת טקסט מלא בזמן שאלת AI חיה, ראו fetch_fulltext/fetch_fulltexts).
    נמדד בפועל: retrieve() בחיפוש ה-AI קפץ מ-1-8 שניות ל-30-85 שניות
    לסירוגין - קריאה בודדת שנתקלת בהאטה חולפת ב-R2 גוררת את ה-adaptive
    retry (עד 3 ניסיונות עם backoff מצטבר) ו-read_timeout=600 של הלקוח
    הרגיל, ותוקעת את כל התשובה למשתמש עד שהיא נגמרת. fetch_fulltext כבר
    סובלני-בכוונה לכישלון בודד (מחזיר מחרוזת ריקה, לא זורק) - אז עדיף
    כישלון מהיר על פני המתנה ארוכה; ה-timeout הארוך נשאר רק ב-_client()
    הרגיל, שם הוא הכרחי (הורדת index.db החד-פעמית, מאות MB)."""
    if not (config.R2_ACCOUNT_ID and config.R2_ACCESS_KEY_ID and config.R2_SECRET_ACCESS_KEY):
        return None
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=Config(connect_timeout=5, read_timeout=10,
                      retries={"max_attempts": 2, "mode": "standard"}),
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


# טקסט פסק-הדין המלא של כל מסמך, כאובייקט בודד ב-R2 (לא בתוך index.db —
# ראו zot/ingest.py) - דחוס gzip, כי טקסט משפטי דחוס היטב וזה חוסך גם
# באחסון וגם בזמן ההעברה. מפתח לפי id (המזהה היציב היחיד שלא תלוי בשם
# קובץ/נתיב מקור, שיכולים להשתנות).
_FULLTEXT_PREFIX = "fulltext/"


def _fulltext_key(id_: int) -> str:
    return f"{_FULLTEXT_PREFIX}{id_}.txt.gz"


def upload_fulltext(id_: int, text: str, client=None) -> bool:
    """מעלה טקסט פסק-דין בודד ל-R2. מחזיר True/False (לא זורק) - כשל
    בהעלאת מסמך בודד לא אמור לעצור אינדוקס של אלפי מסמכים אחרים."""
    client = client or _client()
    if client is None or not config.R2_BUCKET:
        return False
    import gzip
    try:
        client.put_object(
            Bucket=config.R2_BUCKET, Key=_fulltext_key(id_),
            Body=gzip.compress(text.encode("utf-8")),
            ContentType="text/plain; charset=utf-8", ContentEncoding="gzip",
        )
        return True
    except Exception as e:  # noqa: BLE001
        print(f"upload_fulltext: נכשל עבור id={id_}: {type(e).__name__}: {e}")
        return False


def upload_fulltexts(items: list[tuple[int, str]], verbose: bool = True) -> dict:
    """מעלה טקסט מלא לכמה מסמכים במקביל (ThreadPoolExecutor, כמו upload_new/
    fetch_fulltexts) - משמש ע"י zot.ingest.build() כדי שהעלאת מסמכים
    שהוכנסו-זה-עתה לא תאט את קצב הכתיבה ל-DB המקומי (העלאה קורית אחרי
    commit, לא בתוך הטרנזקציה). כשל בהעלאת מסמך בודד לא עוצר את השאר -
    ראו upload_fulltext."""
    client = _client()
    if client is None or not config.R2_BUCKET or not items:
        return {"configured": client is not None, "uploaded": 0, "errors": 0}
    uploaded = errors = 0
    with ThreadPoolExecutor(max_workers=min(_UPLOAD_WORKERS, len(items))) as pool:
        futures = {pool.submit(upload_fulltext, id_, text, client): id_ for id_, text in items}
        for fut in as_completed(futures):
            if fut.result():
                uploaded += 1
            else:
                errors += 1
    if verbose and errors:
        print(f"upload_fulltexts: {uploaded} הועלו, {errors} נכשלו.")
    return {"configured": True, "uploaded": uploaded, "errors": errors}


def delete_fulltext(id_: int, client=None) -> bool:
    """מוחק את אובייקט הטקסט המלא של פסק דין בודד מ-R2 - חובה בכל מחיקת
    רשומה (למשל confidentiality_bot.py: הסרת תיק שחוסה), אחרת הטקסט
    (שעשוי להיות חסוי) נשאר נגיש דרך R2 גם אחרי ש'נמחק' מהמאגר. מחזיר
    True/False (לא זורק) - ראו upload_fulltext."""
    client = client or _client()
    if client is None or not config.R2_BUCKET:
        return False
    try:
        client.delete_object(Bucket=config.R2_BUCKET, Key=_fulltext_key(id_))
        return True
    except Exception as e:  # noqa: BLE001
        print(f"delete_fulltext: נכשל עבור id={id_}: {type(e).__name__}: {e}")
        return False


def fetch_fulltext(id_: int, client=None) -> str:
    """שולף טקסט פסק-דין בודד מ-R2. מחזיר מחרוזת ריקה אם לא קיים/נכשל
    (לא זורק - קריאה בודדת שנכשלת לא אמורה להפיל את כל הדף/התשובה)."""
    client = client or _fast_client()
    if client is None or not config.R2_BUCKET:
        return ""
    import gzip
    try:
        obj = client.get_object(Bucket=config.R2_BUCKET, Key=_fulltext_key(id_))
        return gzip.decompress(obj["Body"].read()).decode("utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"fetch_fulltext: נכשל עבור id={id_}: {type(e).__name__}: {e}")
        return ""


def fetch_fulltexts(ids: list[int]) -> dict[int, str]:
    """שולף טקסט מלא לכמה מסמכים במקביל (ThreadPoolExecutor, כמו
    upload_new) - משמש כשצריך טקסט לכמה מסמכים בבת אחת (חיפוש חכם: עד
    AI_MAX_DOCS מסמכים, לא כל המאגר). מדלג בשקט על מזהים שנכשלו/לא קיימים
    (מחזיר מיפוי חלקי) במקום לזרוק ולהפיל את כל הבקשה."""
    client = _fast_client()
    if client is None or not config.R2_BUCKET or not ids:
        return {}
    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=min(_UPLOAD_WORKERS, len(ids))) as pool:
        futures = {pool.submit(fetch_fulltext, id_, client): id_ for id_ in ids}
        for fut in as_completed(futures):
            id_ = futures[fut]
            text = fut.result()
            if text:
                results[id_] = text
    return results


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
                # מעדכנים את סמן ה-ETag המקומי (ראו sync_index) גם כאן, לא
                # רק אחרי הורדה: בלעדי זה, הרצת sync_index על אותה מכונה
                # אחרי העלאה (למשל בדיקה מקומית של האתר) רואה ETag מרוחק
                # חדש מול סמן מקומי ישן-מהעלאה-הקודמת, ומורידה מ-R2 את מה
                # שהיא-עצמה בדיוק העלתה — בזבוז זמן/רוחב-פס בלבד, אך גם
                # חלון-הזדמנות לקריאה חלקית אם הבדיקה המקומית רצה תוך כדי.
                try:
                    new_etag = client.head_object(Bucket=config.R2_BUCKET, Key=INDEX_KEY)["ETag"]
                    marker = local_path.parent / f".{local_path.name}.synced_etag"
                    marker.write_text(new_etag, encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass  # לא קריטי - sync_index פשוט יוריד שוב בפעם הבאה
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
