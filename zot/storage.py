"""העלאת קבצי פסקי הדין המקוריים (PDF/Word) לאחסון חיצוני (Cloudflare R2).

זה מה שמאפשר לאתר הציבורי להציע גם את הקובץ המקורי להורדה, בלי לתלות
את הארכיון כולו במחשב הבית (ובלי לדחוף קבצים כבדים ל-git).

מוגדר דרך משתני סביבה / .env (ראו .env.example):
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET

אם לא מוגדר — פשוט מדלג בשקט (ההעלאה אופציונלית).

מריצים בעצמו לבדיקה:  python -m zot.storage
"""
from __future__ import annotations

from pathlib import Path

from . import config

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
    return boto3.client(
        "s3",
        endpoint_url=f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=config.R2_ACCESS_KEY_ID,
        aws_secret_access_key=config.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def _load_manifest(manifest_path: Path) -> set[str]:
    if manifest_path.exists():
        return set(manifest_path.read_text(encoding="utf-8").splitlines())
    return set()


def upload_new(verbose: bool = True, docs_dir: Path | None = None,
               manifest_path: Path | None = None, key_prefix: str = "") -> dict:
    """מעלה ל-R2 כל קובץ שעדיין לא הועלה (עוקב אחרי זה בקובץ manifest נפרד
    לכל מקור, כדי לאפשר כמה מקורות/תהליכים בו-זמנית בלי להתנגש).

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
    uploaded = skipped = errors = 0
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with manifest_path.open("a", encoding="utf-8") as manifest_fh:
        for f in sorted(docs_dir.rglob("*")):
            if not (f.is_file() and f.suffix.lower() in _EXT):
                continue
            rel = f.relative_to(docs_dir).as_posix()
            if rel in uploaded_set:
                skipped += 1
                continue
            key = key_prefix + rel
            try:
                client.upload_file(str(f), config.R2_BUCKET, key)
            except Exception as e:  # noqa: BLE001
                errors += 1
                if verbose:
                    print(f"  שגיאה בהעלאת {rel}: {e}")
                continue
            manifest_fh.write(rel + "\n")
            uploaded_set.add(rel)
            uploaded += 1

    if verbose:
        print(f"העלאה ל-R2: {uploaded} קבצים חדשים, {skipped} כבר הועלו, {errors} שגיאות.")
    return {"configured": True, "uploaded": uploaded, "skipped": skipped, "errors": errors}


def upload_index(local_path: Path | None = None, verbose: bool = True) -> dict:
    """מעלה את קובץ האינדקס (index.db) ל-R2 — משם האתר מוריד אותו בהפעלה,
    במקום דרך git (שחוסם קבצים מעל 100MB)."""
    client = _client()
    if client is None or not config.R2_BUCKET:
        if verbose:
            print("R2 לא מוגדר — לא ניתן להעלות את האינדקס.")
        return {"configured": False}
    local_path = Path(local_path or config.DB_PATH)
    client.upload_file(str(local_path), config.R2_BUCKET, INDEX_KEY)
    if verbose:
        print(f"האינדקס ({local_path.stat().st_size / 1e6:.1f}MB) הועלה ל-R2.")
    return {"configured": True}


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
    except Exception:
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
    except Exception:
        return local_path.exists()


if __name__ == "__main__":
    upload_new()
