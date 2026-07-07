"""הגדרות מרכזיות לאפליקציית חיפוש הליכים משפטיים (זכות ואוד).

כל הנתיבים ניתנים לעדכון דרך משתני סביבה, כדי שאותו קוד ירוץ גם על מחשב
מקומי (Windows) וגם בענן.
"""
from __future__ import annotations

import os
from pathlib import Path

# שורש הפרויקט (התיקייה שמעל חבילת zot)
BASE_DIR = Path(__file__).resolve().parent.parent

# ---- נתיבי נתונים (ניתן לעקוף עם משתני סביבה) ----
METADATA_PATH = Path(os.environ.get("ZOT_METADATA", BASE_DIR / "data" / "metadata.csv"))
DOCS_DIR = Path(os.environ.get("ZOT_DOCS", BASE_DIR / "documents"))
DB_PATH = Path(os.environ.get("ZOT_DB", BASE_DIR / "data" / "index.db"))

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
