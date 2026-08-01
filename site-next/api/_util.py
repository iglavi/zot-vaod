"""עזרי-עזר משותפים לנקודות הקצה (Vercel Python functions)."""
from urllib.parse import quote

from zot import config


def add_download_urls(rows: list[dict]) -> list[dict]:
    """מוסיף pdf_url/docx_url לכל שורה, לפי R2_PUBLIC_BASE_URL + file_relpath
    (אותו נוסחה כמו app.py: render_card). None אם אין R2 מוגדר או שאין קובץ."""
    base = config.R2_PUBLIC_BASE_URL
    for r in rows:
        r["pdf_url"] = (base + "/" + quote(r["file_relpath_pdf"])) if base and r.get("file_relpath_pdf") else None
        r["docx_url"] = (base + "/" + quote(r["file_relpath_docx"])) if base and r.get("file_relpath_docx") else None
    return rows
