#!/usr/bin/env python3
"""הורדה יומית של פסקי דין ממאגר הרשות השופטת (decisions.court.gov.il) ועדכון המאגר.

השרת הוא רשימת קבצים של IIS עם התחברות HTTP Basic:
  השורש מכיל תיקיות לפי תאריך (2026-7-7 וכו'), וכל תיקייה מכילה זוגות
  {hash}.docx + {hash}.pdf. הסקריפט מוריד את כל הקבצים החדשים ואז מריץ את
  בניית האינדקס, כך שהמאגר מתעדכן אוטומטית.

פרטי הגישה נקראים ממשתני סביבה (או מקובץ .env מקומי):
  DECISIONS_USER, DECISIONS_PASSWORD   — שם המשתמש והסיסמה
  DECISIONS_URL   — כתובת הבסיס (ברירת מחדל: https://decisions.court.gov.il/)
  DECISIONS_DAYS  — כמה תיקיות תאריך אחרונות להוריד (0 = כל הקיימות; ברירת מחדל 0)

הרצה:  python fetch_daily.py
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urljoin

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from zot import config  # noqa: E402
from zot.ingest import build as build_index  # noqa: E402

_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_DATE_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})/?$")
_FILE_EXT = (".pdf", ".docx", ".doc")


def load_dotenv() -> None:
    """טוען משתני סביבה מקובץ .env מקומי (אם קיים) — כדי לא לשמור סיסמה בקוד."""
    envf = ROOT / ".env"
    if not envf.exists():
        return
    for line in envf.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _list_links(session, url: str) -> list[str]:
    resp = session.get(url, timeout=90)
    resp.raise_for_status()
    return [urljoin(url, h) for h in _HREF_RE.findall(resp.text)]


def main() -> int:
    load_dotenv()
    try:
        import requests
        from requests.auth import HTTPBasicAuth
    except ImportError:
        print("חסרה חבילת requests. התקינו:  pip install -r requirements.txt")
        return 1

    base = os.environ.get("DECISIONS_URL", "https://decisions.court.gov.il/")
    base = base.rstrip("/") + "/"
    user = os.environ.get("DECISIONS_USER", "")
    password = os.environ.get("DECISIONS_PASSWORD", "")
    only_days = int(os.environ.get("DECISIONS_DAYS", "0") or "0")

    if not user or not password:
        print("חסרים פרטי גישה. הגדירו DECISIONS_USER ו-DECISIONS_PASSWORD "
              "(ראו קובץ .env.example).")
        return 1

    session = requests.Session()
    session.auth = HTTPBasicAuth(user, password)
    session.headers["User-Agent"] = "zot-vaod-fetch/1.0"

    print(f"מתחבר אל {base} ...")
    try:
        root_links = _list_links(session, base)
    except Exception as e:  # noqa: BLE001
        print(f"שגיאה בהתחברות/קריאת השורש: {e}")
        print("בדקו שם משתמש/סיסמה (שימו לב לאותיות גדולות/קטנות) ואת הכתובת.")
        return 1

    # איתור תיקיות תאריך בשורש
    folders: dict[str, str] = {}
    for link in root_links:
        m = _DATE_RE.search(link.rstrip("/"))
        if m and link.endswith("/"):
            name = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            folders.setdefault(name, link)

    ordered = sorted(folders.items())
    if only_days > 0:
        ordered = ordered[-only_days:]
    print(f"נמצאו {len(ordered)} תיקיות תאריך להורדה.")

    downloaded = skipped = errors = 0
    for name, url in ordered:
        dest = config.DOCS_DIR / name
        dest.mkdir(parents=True, exist_ok=True)
        try:
            file_links = _list_links(session, url)
        except Exception as e:  # noqa: BLE001
            print(f"  שגיאה בקריאת תיקייה {name}: {e}")
            errors += 1
            continue
        for fl in file_links:
            if not fl.lower().endswith(_FILE_EXT):
                continue
            fname = unquote(fl.rsplit("/", 1)[-1])
            target = dest / fname
            if target.exists() and target.stat().st_size > 0:
                skipped += 1
                continue
            try:
                with session.get(fl, stream=True, timeout=180) as resp:
                    resp.raise_for_status()
                    tmp = target.with_name(target.name + ".part")
                    with open(tmp, "wb") as fo:
                        for chunk in resp.iter_content(65536):
                            fo.write(chunk)
                    tmp.replace(target)
                downloaded += 1
                if downloaded % 25 == 0:
                    print(f"  ...הורדו {downloaded} קבצים")
            except Exception as e:  # noqa: BLE001
                print(f"  שגיאה בהורדת {fname}: {e}")
                errors += 1
        print(f"  תיקייה {name}: הושלמה.")

    print(f"סיכום הורדה: {downloaded} קבצים חדשים, {skipped} כבר קיימים, "
          f"{errors} שגיאות.")

    print("מעדכן את מסד הנתונים (בניית אינדקס)...")
    stats = build_index(verbose=True)
    print(f"בוצע. במאגר כעת {stats['rows']} רשומות "
          f"({stats['documents_matched']} עם טקסט מלא).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
