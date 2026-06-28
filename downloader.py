"""
מוריד פסקי דין על בסיס metadata.csv.

הרצה:
    python downloader.py config_download.json

קובץ קונפיג לדוגמה (config_download.json):
{
  "metadata_file": "D:\\Giluy_Naot\\2020\\metadata.csv",
  "output_dir":    "D:\\Giluy_Naot\\2020\\pdfs",
  "progress_file": "D:\\Giluy_Naot\\2020\\download_progress.json",
  "log_file":      "D:\\Giluy_Naot\\2020\\download_log.txt",
  "year_filter":   2020,
  "workers":       4
}
"""

from __future__ import annotations

import base64
import csv
import html as html_lib
import io
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

try:
    import httpx
    from bs4 import BeautifulSoup
    from PIL import Image
except ImportError:
    print("חסרות תלויות. הרץ: pip install httpx beautifulsoup4 pillow")
    raise SystemExit(1)

# ── קונפיג ──────────────────────────────────────────────────
_config_path = sys.argv[1] if len(sys.argv) > 1 else "config_download.json"
_cfg = json.loads(Path(_config_path).read_text(encoding="utf-8"))

METADATA_FILE = Path(_cfg["metadata_file"])
OUTPUT_DIR    = Path(_cfg["output_dir"])
PROGRESS_FILE = Path(_cfg.get("progress_file", OUTPUT_DIR / "download_progress.json"))
LOG_FILE      = Path(_cfg.get("log_file",      OUTPUT_DIR / "download_log.txt"))
YEAR_FILTER   = _cfg.get("year_filter", None)
WORKERS       = int(_cfg.get("workers", 4))

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── URL-ים ──────────────────────────────────────────────────
BASE_URL   = "https://www.court.gov.il/NGCS.Web.Site"
HOME_URL   = f"{BASE_URL}/HomePage.aspx"
SEARCH_URL = f"{BASE_URL}/LocateDecisions/LocateDecisionQuering.aspx"
OUTPUT_URL = f"{BASE_URL}/LocateDecisions/LocateDecisionOutput.aspx"
VIEWER_URL = f"{BASE_URL}/Viewer/NGCSViewerPage.aspx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
}

# ── לוג ─────────────────────────────────────────────────────
_log_handle = LOG_FILE.open("a", encoding="utf-8")

def log(msg: str, error: bool = False):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    _log_handle.write(line + "\n")
    _log_handle.flush()

# ── פרוגרס ──────────────────────────────────────────────────
def load_progress() -> set[str]:
    if PROGRESS_FILE.exists() and PROGRESS_FILE.stat().st_size > 0:
        try:
            data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            return set(data.get("done", []))
        except Exception:
            pass
    return set()

def save_progress(done: set[str]):
    tmp = PROGRESS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"done": sorted(done)}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PROGRESS_FILE)

# ── HTTP helpers ─────────────────────────────────────────────
def decode_text(response: httpx.Response) -> str:
    enc = response.encoding or "windows-1255"
    try:
        return response.content.decode(enc)
    except UnicodeDecodeError:
        return response.content.decode("windows-1255", errors="replace")

def parse_form_fields(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", {"id": "Form1"}) or soup.find("form", {"name": "Form1"})
    if form is None:
        raise RuntimeError("לא נמצא Form1")
    fields: dict[str, str] = {}
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not name:
            continue
        if el.name == "input":
            t = (el.get("type") or "text").lower()
            if t in {"submit", "button", "image", "file"}:
                continue
            if t in {"radio", "checkbox"}:
                if el.has_attr("checked"):
                    fields[name] = el.get("value", "on")
                continue
            fields[name] = el.get("value", "")
        elif el.name == "select":
            opt = el.find("option", selected=True) or el.find("option")
            if opt:
                fields[name] = opt.get("value", "")
        elif el.name == "textarea":
            fields[name] = el.get_text()
    return fields

def get_court_options(html: str) -> dict[str, str]:
    """מחזיר מיפוי שם_ערכאה -> ערך_dropdown"""
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", {"name": "LocateByParameters1:ddlSelectCourt"})
    if not sel:
        return {}
    return {opt.get_text(strip=True): opt.get("value", "") for opt in sel.find_all("option")}

def parse_results(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    store = soup.find("input", {"id": "LocateDecisionsGridArrayStore"})
    if not store or not store.get("value"):
        return []
    return json.loads(html_lib.unescape(store["value"]))


# ── קריאות API ───────────────────────────────────────────────
class NgcsSession:
    def __init__(self):
        self.client = httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60)
        self.court_map: dict[str, str] = {}
        self._search_html: str = ""

    def close(self):
        self.client.close()

    def init(self):
        """טוען את דף החיפוש ומיפוי ערכאות"""
        r = self.client.get(HOME_URL)
        r.raise_for_status()
        fields = parse_form_fields(decode_text(r))
        fields["__EVENTTARGET"] = "Header1$UpperMenu1$btnVerdictLocalization"
        fields["__EVENTARGUMENT"] = ""
        r = self.client.post(HOME_URL, data=fields)
        r.raise_for_status()
        self._search_html = decode_text(r)
        self.court_map = get_court_options(self._search_html)
        log(f"נטענו {len(self.court_map)} ערכאות")

    def search(self, date_str: str, court_id: str) -> tuple[list[dict], str]:
        """חיפוש לפי תאריך וערכאה. date_str בפורמט DD/MM/YYYY"""
        fields = parse_form_fields(self._search_html)
        fields["hdnSelectedTab"] = "1"
        fields["LocateByParameters1:ddlSelectCourt"] = court_id
        fields["LocateByParameters1:ddlSelectProceeding"] = "-1"
        fields["LocateByParameters1:ddlSelectCaseType"] = "-1"
        fields["LocateByParameters1:ddlSelectCaseInterest"] = "-1"
        fields["LocateByParameters1:ddlDecisionType"] = "-1"
        fields["LocateByParameters1:dateFrom"] = date_str
        fields["LocateByParameters1:DateTo"] = date_str
        fields["__EVENTTARGET"] = "ButtonsGroup1$btnLocate"
        fields["__EVENTARGUMENT"] = ""
        r = self.client.post(SEARCH_URL, data=fields)
        r.raise_for_status()
        html = decode_text(r)
        # שמור לשימוש בפתיחת מסמכים
        self._search_html = html
        return parse_results(html), html

    def get_document_number(self, results_html: str, case_id: int, document_id: int) -> str:
        fields = parse_form_fields(results_html)
        fields["__EVENTTARGET"] = "btnDocument"
        fields["__EVENTARGUMENT"] = f"{case_id}&{document_id}&1"
        soup = BeautifulSoup(results_html, "html.parser")
        form = soup.find("form", {"id": "Form1"}) or soup.find("form", {"name": "Form1"})
        action = urljoin(OUTPUT_URL, form.get("action") if form else "")
        r = self.client.post(action or OUTPUT_URL, data=fields)
        r.raise_for_status()
        html = decode_text(r)
        final_url = str(r.url)
        query = parse_qs(urlparse(final_url).query)
        doc_num = (query.get("DocumentNumber") or [None])[0]
        if not doc_num:
            match = re.search(r"DocumentNumber=([0-9a-f]{32})", f"{final_url}\n{html}", re.I)
            doc_num = match.group(1) if match else None
        if not doc_num:
            raise RuntimeError(f"לא נמצא DocumentNumber למסמך {document_id}")
        return doc_num

    def download_pdf(self, doc_num: str, dest: Path) -> int:
        viewer_url = f"{VIEWER_URL}?DocumentNumber={doc_num}"
        self.client.get(viewer_url).raise_for_status()

        r = self.client.post(
            f"{VIEWER_URL}/GetAllImages",
            json={"documentNumber": doc_num},
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": viewer_url,
            },
        )
        r.raise_for_status()
        body = r.json()
        images_data = body.get("d", body)
        if not isinstance(images_data, list) or not images_data:
            raise RuntimeError("GetAllImages לא החזיר נתונים")

        pil_images = []
        for item in images_data:
            s = item if isinstance(item, str) else str(item)
            match = re.search(r"src=['\"]([^'\"]+)['\"]", s)
            data_url = match.group(1) if match else s
            _, encoded = data_url.split(",", 1)
            encoded += "=" * (-len(encoded) % 4)
            pil_images.append(Image.open(io.BytesIO(base64.b64decode(encoded))))

        dest.parent.mkdir(parents=True, exist_ok=True)
        first = pil_images[0].convert("RGB")
        rest = [img.convert("RGB") for img in pil_images[1:]]
        if rest:
            first.save(dest, save_all=True, append_images=rest)
        else:
            first.save(dest)
        for img in pil_images:
            img.close()
        return len(pil_images)


# ── טעינת מטאדאטא ────────────────────────────────────────────
def load_metadata(year_filter: int | None) -> list[dict]:
    rows = []
    with METADATA_FILE.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_raw = row.get("תאריך מתן החלטה", "").strip()
            if not date_raw:
                continue
            try:
                dt = datetime.strptime(date_raw, "%d/%m/%Y %H:%M:%S")
            except ValueError:
                try:
                    dt = datetime.strptime(date_raw, "%d/%m/%Y")
                except ValueError:
                    continue
            if year_filter and dt.year != year_filter:
                continue
            rows.append({
                "date_str": dt.strftime("%d/%m/%Y"),
                "court":    row.get("בית משפט", "").strip(),
                "case_num": row.get("מספר תיק", "").strip(),
                "case_name": row.get("שם תיק", "").strip(),
                "dec_type": row.get("סוג החלטה", "").strip(),
            })
    return rows

def safe_name(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text.strip())[:80] or "document"

def progress_key(date_str: str, case_num: str, document_id: int) -> str:
    return f"{date_str}|{case_num}|{document_id}"


# ── לוגיקה ראשית ─────────────────────────────────────────────
def main():
    log("=" * 60)
    log(f"downloader.py — שנה: {YEAR_FILTER or 'כל'}, workers: {WORKERS}")

    done = load_progress()
    log(f"קבצים שכבר הורדו: {len(done)}")

    log("טוען מטאדאטא...")
    rows = load_metadata(YEAR_FILTER)
    log(f"שורות לטיפול: {len(rows)}")

    # מקבץ לפי (תאריך, ערכאה)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["date_str"], r["court"])].append(r)
    log(f"קבוצות (תאריך × ערכאה): {len(groups)}")

    sess = NgcsSession()
    sess.init()

    stats = {"downloaded": 0, "skipped": 0, "not_found": 0, "errors": 0}

    def sort_key(item):
        ds = item[0][0]  # DD/MM/YYYY
        return datetime.strptime(ds, "%d/%m/%Y"), item[0][1]

    for (date_str, court_name), group_rows in sorted(groups.items(), key=sort_key):
        court_id = sess.court_map.get(court_name)
        if not court_id:
            log(f"  ⚠ לא נמצא court_id עבור '{court_name}' — דילוג על {len(group_rows)} שורות", error=True)
            stats["not_found"] += len(group_rows)
            continue

        log(f"\n{date_str} | {court_name} ({len(group_rows)} שורות)")

        try:
            results, results_html = sess.search(date_str, court_id)
        except Exception as e:
            log(f"  שגיאת חיפוש: {e}", error=True)
            stats["errors"] += len(group_rows)
            time.sleep(5)
            continue

        if len(results) == 100:
            log(f"  ⚠ בדיוק 100 תוצאות — ייתכן חיתוך!")

        # בנה אינדקס לפי מספר תיק
        results_by_case: dict[str, dict] = {}
        for res in results:
            key = str(res.get("CaseDisplayIdentifier", "")).strip()
            results_by_case[key] = res

        for meta_row in group_rows:
            case_num = meta_row["case_num"]
            res = results_by_case.get(case_num)
            if not res:
                log(f"  ✗ לא נמצא בחיפוש: {case_num}")
                stats["not_found"] += 1
                continue

            doc_id = int(res.get("DocumentID", 0))
            case_id = int(res.get("CaseID", 0))
            pkey = progress_key(date_str, case_num, doc_id)

            if pkey in done:
                stats["skipped"] += 1
                continue

            if not res.get("IsIDCPublished"):
                log(f"  — לא פורסם: {case_num}")
                done.add(pkey)
                continue

            filename = f"{safe_name(case_num)}_{doc_id}.pdf"
            dest = OUTPUT_DIR / date_str.replace("/", "-") / filename

            try:
                doc_num = sess.get_document_number(results_html, case_id, doc_id)
                # חיפוש מחדש כדי לרענן את ה-results_html לפתיחת מסמך הבא
                results, results_html = sess.search(date_str, court_id)
                pages = sess.download_pdf(doc_num, dest)
                log(f"  ✓ {case_num} → {dest.name} ({pages} עמ')")
                done.add(pkey)
                stats["downloaded"] += 1
                save_progress(done)
                time.sleep(0.5)
            except Exception as e:
                log(f"  ✗ שגיאה ב-{case_num}: {e}", error=True)
                stats["errors"] += 1

    log("\n" + "=" * 60)
    log(f"סיכום:")
    log(f"  הורדו:        {stats['downloaded']}")
    log(f"  דולגו (כבר קיים): {stats['skipped']}")
    log(f"  לא נמצאו:    {stats['not_found']}")
    log(f"  שגיאות:       {stats['errors']}")
    log("=" * 60)

    sess.close()
    _log_handle.close()


if __name__ == "__main__":
    main()
