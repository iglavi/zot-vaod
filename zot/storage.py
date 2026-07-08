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


def _load_manifest() -> set[str]:
    if _MANIFEST.exists():
        return set(_MANIFEST.read_text(encoding="utf-8").splitlines())
    return set()


def upload_new(verbose: bool = True) -> dict:
    """מעלה ל-R2 כל קובץ שעדיין לא הועלה (עוקב אחרי זה בקובץ manifest מקומי)."""
    client = _client()
    if client is None or not config.R2_BUCKET:
        if verbose:
            print("R2 לא מוגדר (חסרים משתני סביבה) — מדלג על העלאה חיצונית.")
        return {"configured": False, "uploaded": 0, "skipped": 0, "errors": 0}

    uploaded_set = _load_manifest()
    docs_dir = config.DOCS_DIR
    uploaded = skipped = errors = 0
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    with _MANIFEST.open("a", encoding="utf-8") as manifest_fh:
        for f in sorted(docs_dir.rglob("*")):
            if not (f.is_file() and f.suffix.lower() in _EXT):
                continue
            rel = f.relative_to(docs_dir).as_posix()
            if rel in uploaded_set:
                skipped += 1
                continue
            try:
                client.upload_file(str(f), config.R2_BUCKET, rel)
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


if __name__ == "__main__":
    upload_new()
