#!/usr/bin/env python3
"""הורדה יומית של פסקי דין ממאגר הרשות השופטת (decisions.court.gov.il) ועדכון המאגר.

האתגר: השרת מוגן ב-WAF שמזהה לקוחות שאינם דפדפן (לפי טביעת אצבע של TLS) ומחזיר
דף חסימה, וגם דורש אימות Windows (NTLM). לכן המנוע המרכזי משלב את שניהם:
  • curl_cffi — מתחזה לטביעת האצבע של Chrome ועובר את ה-WAF.
  • spnego — מבצע את לחיצת היד של NTLM ידנית מעל אותו חיבור.
כגיבוי מנסים גם requests_ntlm ו-curl.exe --ntlm, ובוחרים את המנוע שמחזיר את
רשימת הקבצים האמיתית (ולא דף חסימה).

לאחר ההתחברות, מוריד את כל קבצי ה-PDF/Word החדשים מכל תיקיות התאריך ומריץ
בניית אינדקס, כך שהמאגר מתעדכן אוטומטית.

פרטי הגישה נקראים ממשתני סביבה או מקובץ .env מקומי:
  DECISIONS_USER, DECISIONS_PASSWORD   — שם המשתמש והסיסמה
  DECISIONS_DOMAIN — דומיין NTLM (אופציונלי; ברירת מחדל: ריק)
  DECISIONS_URL    — כתובת הבסיס (ברירת מחדל: https://decisions.court.gov.il/)
  DECISIONS_DAYS   — כמה תיקיות תאריך אחרונות להוריד (0 = כל הקיימות)

הרצה:  python fetch_daily.py
"""
from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urljoin

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from zot import config  # noqa: E402
from zot.ingest import build as build_index  # noqa: E402

_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_FILE_EXT = (".pdf", ".docx", ".doc")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
_BROWSER_HEADERS = {
    "User-Agent": _UA,
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
}
_TMP = Path(tempfile.gettempdir())


def load_dotenv() -> None:
    envf = ROOT / ".env"
    if not envf.exists():
        return
    for line in envf.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _extract_ntlm_challenge(header_value: str):
    for part in (header_value or "").split(","):
        part = part.strip()
        if part.upper().startswith("NTLM"):
            token = part[4:].strip()
            if token:
                try:
                    return base64.b64decode(token)
                except Exception:  # noqa: BLE001
                    return None
    return None


# ---------- מנועי רשת ----------
def _curl_cffi_ntlm_engine(user, password, domain):
    """המנוע המרכזי: curl_cffi (מתחזה ל-Chrome) + NTLM ידני דרך spnego."""
    try:
        from curl_cffi import CurlHttpVersion
        from curl_cffi import requests as creq
        import spnego
    except ImportError:
        return None
    session = creq.Session(impersonate="chrome", timeout=120)
    session.headers.update(_BROWSER_HEADERS)
    userspec = f"{domain}\\{user}" if domain else user
    # NTLM דורש חיבור HTTP/1.1 יציב (הוא נשבר מעל HTTP/2 של Chrome). כפיית 1.1
    # אינה משנה את טביעת האצבע (JA3) שה-WAF בודק — סוגי ההרחבות זהים.
    _h1 = CurlHttpVersion.V1_1

    def fetch(url, out_path):
        try:
            client = spnego.client(userspec, password, protocol="ntlm")
            type1 = client.step()
            r1 = session.get(
                url, allow_redirects=False, http_version=_h1,
                headers={"Authorization": "NTLM " + base64.b64encode(type1).decode()})
            if r1.status_code != 401:
                out_path.write_bytes(r1.content)
                return r1.status_code, ""
            challenge = _extract_ntlm_challenge(
                r1.headers.get("WWW-Authenticate") or r1.headers.get("www-authenticate") or "")
            if challenge is None:
                return None, "no NTLM challenge in 401"
            type3 = client.step(challenge)
            r2 = session.get(
                url, allow_redirects=False, http_version=_h1,
                headers={"Authorization": "NTLM " + base64.b64encode(type3).decode()})
            out_path.write_bytes(r2.content)
            return r2.status_code, ""
        except Exception as e:  # noqa: BLE001
            return None, str(e)

    return "curl_cffi+ntlm", fetch


def _requests_ntlm_engine(user, password, domain):
    try:
        import requests
        from requests_ntlm import HttpNtlmAuth
    except ImportError:
        return None
    session = requests.Session()
    session.headers.update(_BROWSER_HEADERS)
    session.auth = HttpNtlmAuth(f"{domain}\\{user}" if domain else user, password)

    def fetch(url, out_path):
        try:
            r = session.get(url, timeout=300)
        except Exception as e:  # noqa: BLE001
            return None, str(e)
        out_path.write_bytes(r.content)
        return r.status_code, ""

    return "requests_ntlm", fetch


def _curl_engine(user, password, domain):
    exe = shutil.which("curl")
    if not exe:
        return None
    userpwd = f"{domain}\\{user}:{password}" if domain else f"{user}:{password}"

    def fetch(url, out_path):
        args = [exe, "--ntlm", "-u", userpwd, "-s", "-A", _UA,
                "--connect-timeout", "30", "--max-time", "300",
                "-w", "%{http_code}", "-o", str(out_path), url]
        try:
            r = subprocess.run(args, capture_output=True, text=True)
        except Exception as e:  # noqa: BLE001
            return None, str(e)
        if r.returncode != 0:
            return None, (r.stderr.strip() or f"curl exit {r.returncode}")
        code = r.stdout.strip()[-3:]
        return (int(code), "") if code.isdigit() else (None, r.stdout.strip())

    return "curl.exe --ntlm", fetch


def find_date_folders(base: str, html: str) -> dict[str, str]:
    """מזהה קישורי תיקיות בשם תאריך (YYYY-M-D), עם או בלי לוכסן מסיים."""
    folders: dict[str, str] = {}
    for h in _HREF_RE.findall(html):
        link = urljoin(base, h)
        seg = unquote(link.rstrip("/").rsplit("/", 1)[-1])
        m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", seg)
        if m:
            name = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            folders.setdefault(name, link if link.endswith("/") else link + "/")
    return folders


def select_engine(user, password, domain, base):
    """מנסה כל מנוע מול השורש ובוחר את הראשון שמחזיר רשימת קבצים אמיתית."""
    candidates = [e for e in (
        _curl_cffi_ntlm_engine(user, password, domain),
        _requests_ntlm_engine(user, password, domain),
        _curl_engine(user, password, domain),
    ) if e]
    if not candidates:
        print("לא נמצא מנוע רשת. התקינו:  pip install -r requirements.txt")
        return None
    saw_401 = saw_block = False
    last_html = ""
    for name, fetch in candidates:
        probe = _TMP / "zot_probe.html"
        status, err = fetch(base, probe)
        folders = {}
        if status == 200 and probe.exists():
            last_html = probe.read_text(encoding="utf-8", errors="ignore")
            folders = find_date_folders(base, last_html)
        print(f"מנוע {name}: סטטוס={status}, תיקיות שזוהו={len(folders)}"
              + (f"  ({err})" if err else ""))
        if status == 200 and folders:
            return name, fetch, folders
        if status == 200:
            saw_block = True
        elif status == 401:
            saw_401 = True

    if saw_401:
        print(">> התחברנו אך האימות נדחה (401). בדקו סיסמה, ואולי צריך "
              "DECISIONS_DOMAIN ב-.env.")
    elif saw_block:
        dbg = ROOT / "debug_root.html"
        dbg.write_text(last_html, encoding="utf-8")
        print(f">> התקבל דף חסימה מה-WAF (נשמר ל-{dbg}).")
    else:
        print(">> כל המנועים נכשלו/נחסמו בחיבור.")
    return None


def list_links(fetch, url):
    tmp = _TMP / "zot_list.html"
    status, err = fetch(url, tmp)
    if status != 200:
        raise RuntimeError(f"סטטוס {status} {err}")
    text = tmp.read_text(encoding="utf-8", errors="ignore")
    return [urljoin(url, h) for h in _HREF_RE.findall(text)]


def main() -> int:
    load_dotenv()
    base = os.environ.get("DECISIONS_URL", "https://decisions.court.gov.il/").rstrip("/") + "/"
    user = os.environ.get("DECISIONS_USER", "")
    password = os.environ.get("DECISIONS_PASSWORD", "")
    domain = os.environ.get("DECISIONS_DOMAIN", "")
    only_days = int(os.environ.get("DECISIONS_DAYS", "0") or "0")

    if not user or not password:
        print("חסרים פרטי גישה. הגדירו DECISIONS_USER ו-DECISIONS_PASSWORD (ראו .env.example).")
        return 1

    print(f"פרטים שנקראו: משתמש={user}, אורך סיסמה={len(password)}"
          + (f", דומיין={domain}" if domain else ""))
    print(f"מתחבר אל {base} (WAF + NTLM) ...")

    selected = select_engine(user, password, domain, base)
    if not selected:
        return 1
    engine, fetch, folders = selected

    ordered = sorted(folders.items())
    if only_days > 0:
        ordered = ordered[-only_days:]
    print(f"התחברות הצליחה ({engine}). נמצאו {len(ordered)} תיקיות תאריך.")

    downloaded = skipped = errors = 0
    for name, url in ordered:
        dest = config.DOCS_DIR / name
        dest.mkdir(parents=True, exist_ok=True)
        try:
            file_links = list_links(fetch, url)
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
            part = target.with_name(target.name + ".part")
            status, err = fetch(fl, part)
            if status == 200 and part.exists() and part.stat().st_size > 0:
                part.replace(target)
                downloaded += 1
                if downloaded % 25 == 0:
                    print(f"  ...הורדו {downloaded} קבצים")
            else:
                part.unlink(missing_ok=True)
                print(f"  שגיאה בהורדת {fname}: סטטוס {status} {err}")
                errors += 1
        print(f"  תיקייה {name}: הושלמה ({len(file_links)} פריטים).")

    print(f"סיכום הורדה: {downloaded} קבצים חדשים, {skipped} כבר קיימים, {errors} שגיאות.")
    print("מעדכן את מסד הנתונים (בניית אינדקס)...")
    stats = build_index(verbose=True)
    print(f"בוצע. במאגר כעת {stats['rows']} רשומות "
          f"({stats['documents_matched']} עם טקסט מלא).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
