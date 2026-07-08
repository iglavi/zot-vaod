#!/usr/bin/env python3
"""מעלה ל-R2 את קבצי בית המשפט העליון (documents_supreme/) — במקביל ונפרד
מהעלאת קבצי decisions.court.gov.il (documents/), עם יומן מעקב ותחילית-נתיב
משלו (supreme/) כדי לא להתנגש.

רץ בלולאה (כי fetch_supreme.py ממשיך להוריד קבצים חדשים): מעלה את מה
שכבר קיים, ישן, ומעלה שוב את החדש שנוסף — עד שעוצרים אותו ידנית.

הרצה:  python upload_supreme_to_r2.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from zot import config  # noqa: E402
from zot.storage import upload_new  # noqa: E402

SUPREME_DOCS_DIR = ROOT / "documents_supreme"
SUPREME_MANIFEST = config.DATA_DIR / ".r2_uploaded_supreme.txt"
SUPREME_PREFIX = "supreme/"
SLEEP_BETWEEN_PASSES_SEC = 60


def main() -> int:
    print(f"מעלה מ-{SUPREME_DOCS_DIR} לדלי R2 תחת התחילית '{SUPREME_PREFIX}'")
    while True:
        stats = upload_new(verbose=True, docs_dir=SUPREME_DOCS_DIR,
                           manifest_path=SUPREME_MANIFEST, key_prefix=SUPREME_PREFIX)
        if not stats["configured"]:
            return 1
        time.sleep(SLEEP_BETWEEN_PASSES_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
