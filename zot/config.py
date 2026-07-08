"""הגדרות מרכזיות לאפליקציית חיפוש הליכים משפטיים (גילוי נאות).

כל הנתיבים ניתנים לעדכון דרך משתני סביבה, כדי שאותו קוד ירוץ גם על מחשב
מקומי (Windows) וגם בענן.
"""
from __future__ import annotations

import os
from pathlib import Path

# שורש הפרויקט (התיקייה שמעל חבילת zot)
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """טוען .env מקומי (אם קיים) *לפני* שקוראים משתני סביבה למטה בקובץ הזה.

    נעשה כאן ולא רק ב-fetch_daily.py, כי כל מודול שמייבא את config (כולל
    zot.storage כשמריצים אותו ישירות) צריך לקבל את אותם ערכים — לא משנה
    מאיפה הוא נכנס."""
    envf = BASE_DIR / ".env"
    if not envf.exists():
        return
    for line in envf.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv()

# ---- נתיבי נתונים (ניתן לעקוף עם משתני סביבה) ----
DATA_DIR = Path(os.environ.get("ZOT_DATA_DIR", BASE_DIR / "data"))
METADATA_PATH = Path(os.environ.get("ZOT_METADATA", BASE_DIR / "data" / "metadata.csv"))
DOCS_DIR = Path(os.environ.get("ZOT_DOCS", BASE_DIR / "documents"))
DB_PATH = Path(os.environ.get("ZOT_DB", BASE_DIR / "data" / "index.db"))

# ---- אחסון חיצוני (Cloudflare R2) לקבצי המקור (PDF/Word) ----
# אופציונלי: אם לא מוגדר, פשוט לא מוצג קישור להורדת הקובץ המקורי.
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "")
R2_PUBLIC_BASE_URL = os.environ.get("R2_PUBLIC_BASE_URL", "").rstrip("/")

# ---- הגדרות מנוע ה-AI ----
# ברירת המחדל היא Claude Opus 4.8. אפשר להוזיל עלויות עם claude-sonnet-5.
AI_MODEL = os.environ.get("ZOT_MODEL", "claude-opus-4-8")

# כמה פסקי דין להעביר למודל בכל שאלה, וכמה תווים מכל אחד
AI_MAX_DOCS = int(os.environ.get("ZOT_AI_MAX_DOCS", "8"))
AI_MAX_CHARS_PER_DOC = int(os.environ.get("ZOT_AI_MAX_CHARS", "6000"))

RESULTS_PER_PAGE = 10

# מיפוי חודשים בעברית -> מספר, לחילוץ תאריכים מגוף פסק הדין
HEB_MONTHS = {
    "ינואר": 1, "פברואר": 2, "מרץ": 3, "אפריל": 4,
    "מאי": 5, "יוני": 6, "יולי": 7, "אוגוסט": 8,
    "ספטמבר": 9, "אוקטובר": 10, "נובמבר": 11, "דצמבר": 12,
}
HEB_MONTH_NAMES = {v: k for k, v in HEB_MONTHS.items()}
