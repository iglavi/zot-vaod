#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ממתין לסיום ריצת fetch_supreme.py הנוכחית (טווח 2015-2026), ואז ממשיך
אוטומטית להוריד את כל שאר השנים שקיימות במאגר בית המשפט העליון (בדקנו:
יש תיקים עוד מ-1935, ומ-1948 בהיקף משמעותי) — כך שהארכיון המקומי יכסה
את כל טווח השנים הזמין, לא רק 2015 ואילך.

הרצה:  python continue_supreme_download.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# השנה שבה מתחילה הריצה הנוכחית (2015) — ממשיכים מכאן ואחורה עד השנה
# הכי מוקדמת שנמצאה עם תיקים אמיתיים (בדקנו ידנית: יש כבר תוצאות ב-1935,
# ומ-1948 בהיקף גדול; לפני 1925 לא נמצא כלום בבדיקה).
CONTINUE_YEAR_FROM = 1925
CONTINUE_YEAR_TO = 2014


def _supreme_running() -> bool:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object { $_.CommandLine -like '*fetch_supreme.py*' } | "
         "Select-Object -ExpandProperty ProcessId"],
        capture_output=True, text=True,
    )
    return bool(out.stdout.strip())


def main() -> int:
    print(f"ממתין לסיום ריצת fetch_supreme.py הנוכחית (2015-2026)...")
    while _supreme_running():
        time.sleep(30)

    print(f"הריצה הקודמת הסתיימה. ממשיך: {CONTINUE_YEAR_FROM}-{CONTINUE_YEAR_TO}")
    import os
    env = os.environ.copy()
    env["SUPREME_YEAR_FROM"] = str(CONTINUE_YEAR_FROM)
    env["SUPREME_YEAR_TO"] = str(CONTINUE_YEAR_TO)
    subprocess.run([sys.executable, str(ROOT / "fetch_supreme.py")], cwd=str(ROOT), env=env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
