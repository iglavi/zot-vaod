#!/usr/bin/env python3
"""הורדה יומית של פסקי דין ממאגר הרשות השופטת (decisions.court.gov.il) ועדכון המאגר.

השרת הוא רשימת קבצים של IIS עם התחברות HTTP Basic:
  השורש מכיל תיקיות לפי תאריך (2026-7-7 וכו'), וכל תיקייה מכילה זוגות
  {hash}.docx + {hash}.pdf. הסקריפט מוריד את כל הקבצים החדשים ואז מריץ את
  בניית האינדקס, כך שהמאגר מתעדכן אוטומטית.

האתר מוגן ב-WAF שמנתק לקוחות שאינם דפדפן; לכן הסקריפט מתחזה ל-Chrome
באמצעות curl_cffi (אם מותקנת) ומוסיף כותרות דפדפן. אם curl_cffi אינה
מותקנת — נופל חזרה ל-requests רגיל (עלול להיחסם על ידי ה-WAF).

פרטי הגישה נקראים ממשתני סביבה או מקובץ .env מקומי:
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

_BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
}


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


def make_session():
    """יוצר Session שנראה כמו Chrome. מחזיר (session, engine_name)."""
    try:
        from curl_cffi import requests as creq  # התחזות לטביעת האצבע של Chrome

        session = creq.Session(impersonate="chrome", timeout=90)
        session.headers.update(_BROWSER_HEADERS)
        return session, "curl_cffi"
    except Exception:
        pass

    import requests

    session = requests.Session()
    session.headers.update(_BROWSER_HEADERS)
    return session, "requests"


def _list_links(session, url: str, auth) -> list[str]:
    resp = session.get(url, timeout=90, auth=auth)
    resp.raise_for_status()
    return [urljoin(url, h) for h in _HREF_RE.findall(resp.text)]


def _download(session, url: str, target: Path, auth) -> None:
    resp = session.get(url, timeout=180, auth=auth)
    resp.raise_for_status()
    tmp = target.with_name(target.name + ".part")
    tmp.write_bytes(resp.content)
    tmp.replace(target)


def main() -> int:
    load_dotenv()

    base = os.environ.get("DECISIONS_URL", "https://decisions.court.gov.il/")
    base = base.rstrip("/") + "/"
    user = os.environ.get("DECISIONS_USER", "")
    password = os.environ.get("DECISIONS_PASSWORD", "")
    only_days = int(os.environ.get("DECISIONS_DAYS", "0") or "0")

    if not user or not password:
        print("חסרים פרטי גישה. הגדירו DECISIONS_USER ו-DECISIONS_PASSWORD "
              "(ראו קובץ .env.example).")
        return 1

    try:
        session, engine = make_session()
    except ImportError:
        print("חסרה חבילת רשת. התקינו:  pip install -r requirements.txt")
        return 1

    if engine != "curl_cffi":
        print("שים לב: curl_cffi אינה מותקנת — ייתכן שהאתר יחסום. "
              "מומלץ להריץ:  pip install curl_cffi")

    auth = (user, password)
    print(f"פרטים שנקראו: משתמש={user}, אורך סיסמה={len(password)}, מנוע={engine}")
    print(f"מתחבר אל {base} ...")

    # --- אבחון: בקשת שורש ראשונה, כולל זיהוי סוג האימות שהשרת דורש ---
    try:
        resp = session.get(base, auth=auth, timeout=90)
    except Exception as e:  # noqa: BLE001
        print(f"שגיאת רשת: {e}")
        print("אם זה ניתוק חיבור (10054) — ודאו ש-curl_cffi מותקנת:  pip install curl_cffi")
        return 1

    wa = resp.headers.get("WWW-Authenticate") or resp.headers.get("www-authenticate")
    print(f"סטטוס תגובה מהשרת: {resp.status_code}")
    if wa:
        print(f"סוג האימות שהשרת דורש (WWW-Authenticate): {wa}")

    if resp.status_code == 401:
        if wa and ("ntlm" in wa.lower() or "negotiate" in wa.lower()):
            print(">> השרת דורש אימות Windows (NTLM/Negotiate), לא Basic. "
                  "שלחו לי את השורה של WWW-Authenticate ואתקן את הקוד בהתאם.")
        else:
            print(">> השרת דחה את פרטי הגישה (401). בדקו שם משתמש/סיסמה.")
        return 1
    if resp.status_code >= 400:
        print(f">> השרת החזיר שגיאה {resp.status_code}.")
        return 1

    root_links = [urljoin(base, h) for h in _HREF_RE.findall(resp.text)]

    folders: dict[str, str] = {}
    for link in root_links:
        m = _DATE_RE.search(link.rstrip("/"))
        if m and link.endswith("/"):
            name = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            folders.setdefault(name, link)

    ordered = sorted(folders.items())
    if only_days > 0:
        ordered = ordered[-only_days:]
    print(f"התחברות הצליחה ({engine}). נמצאו {len(ordered)} תיקיות תאריך.")

    downloaded = skipped = errors = 0
    for name, url in ordered:
        dest = config.DOCS_DIR / name
        dest.mkdir(parents=True, exist_ok=True)
        try:
            file_links = _list_links(session, url, auth)
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
                _download(session, fl, target, auth)
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
