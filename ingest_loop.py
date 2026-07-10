#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""מריץ את בניית האינדקס (zot.ingest) בלולאה מתמשכת, כדי שמסמכים חדשים
(מהשלמת decisions.court.gov.il, ומהורדת בית המשפט העליון) יאונדקסו
אוטומטית תוך כדי זמן, בלי להריץ ידנית כל פעם. הודות לעיצוב האינקרementלי,
ריצה חוזרת זולה — מעבדת רק קבצים חדשים מאז הריצה הקודמת.

הרצה:  python ingest_loop.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from zot import ingest  # noqa: E402

SLEEP_BETWEEN_PASSES_SEC = 600  # 10 דקות

# מסמכי בית המשפט העליון: תיקייה נפרדת, מועלים ל-R2 תחת תחילית 'supreme/'
# (ראו upload_supreme_to_r2.py) — צריך את אותה תחילית כאן כדי שקישורי
# ההורדה בממשק יצביעו לקובץ הנכון בדלי.
SUPREME_DOCS_DIR = ROOT / "documents_supreme"
SUPREME_PREFIX = "supreme/"


def _other_ingest_running() -> bool:
    """בודק שאין כבר הרצה חד-פעמית של zot.ingest פעילה (כדי לא לכתוב
    במקביל לאותו קובץ SQLite משני תהליכים)."""
    import os
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object { $_.CommandLine -like '*zot.ingest*' -and "
         f"$_.ProcessId -ne {os.getpid()} }} | Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True,
    )
    return bool(out.stdout.strip())


def main() -> int:
    while _other_ingest_running():
        print("ריצת אינדוקס חד-פעמית כבר פעילה — ממתין שתסתיים לפני תחילת הלולאה...")
        time.sleep(30)

    while True:
        try:
            ingest.build(extra_sources=[(SUPREME_DOCS_DIR, SUPREME_PREFIX)])
        except Exception as e:  # noqa: BLE001
            print(f"שגיאה בבניית האינדקס: {e}")
        time.sleep(SLEEP_BETWEEN_PASSES_SEC)


if __name__ == "__main__":
    raise SystemExit(main())
