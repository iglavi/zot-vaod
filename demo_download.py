"""
דמו להורדת פסקי דין — מריץ חיפוש אחד ומוריד עד 3 קבצים לתיקיית demo_output.

הרצה:
    python demo_download.py

ניתן לשנות את DATE, COURT_ID, MAX_DOCS למטה.
"""

from __future__ import annotations

import base64
import html as html_lib
import io
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

try:
    import httpx
    from bs4 import BeautifulSoup
    from PIL import Image
except ImportError:
    print("חסרות תלויות. הרץ קודם:")
    print("  pip install httpx beautifulsoup4 pillow")
    raise SystemExit(1)

# ── הגדרות ──────────────────────────────────────────────────
DATE       = "01/01/2023"   # תאריך לחיפוש (DD/MM/YYYY)
COURT_ID   = "18"           # 18 = הארצי לעבודה
MAX_DOCS   = 3              # כמה קבצים להוריד (לדמו)
OUTPUT_DIR = Path("demo_output")
# ────────────────────────────────────────────────────────────

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


@dataclass
class DecisionRow:
    case_id: int
    document_id: int
    decision_id: int
    case_display_identifier: str
    decision_signature_date: str
    case_name: str
    court_name: str
    is_published: bool

    @classmethod
    def from_dict(cls, row: dict) -> "DecisionRow":
        return cls(
            case_id=int(row["CaseID"]),
            document_id=int(row["DocumentID"]),
            decision_id=int(row["DecisionID"]),
            case_display_identifier=str(row.get("CaseDisplayIdentifier", "")),
            decision_signature_date=str(row.get("DecisionSignatureDate", "")),
            case_name=str(row.get("CaseName", "")),
            court_name=str(row.get("CourtName", "")),
            is_published=bool(row.get("IsIDCPublished")),
        )


def decode_text(response: httpx.Response) -> str:
    encoding = response.encoding or "windows-1255"
    try:
        return response.content.decode(encoding)
    except UnicodeDecodeError:
        return response.content.decode("windows-1255", errors="replace")


def parse_form_fields(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", {"id": "Form1"}) or soup.find("form", {"name": "Form1"})
    if form is None:
        raise RuntimeError("לא נמצא Form1 בדף")
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


def parse_results(html: str) -> list[DecisionRow]:
    soup = BeautifulSoup(html, "html.parser")
    store = soup.find("input", {"id": "LocateDecisionsGridArrayStore"})
    if store is None or not store.get("value"):
        return []
    rows = json.loads(html_lib.unescape(store["value"]))
    return [DecisionRow.from_dict(r) for r in rows]


def search(client: httpx.Client, date: str, court_id: str) -> tuple[list[DecisionRow], str]:
    print(f"  פותח דף הבית...")
    r = client.get(HOME_URL)
    r.raise_for_status()
    fields = parse_form_fields(decode_text(r))
    fields["__EVENTTARGET"] = "Header1$UpperMenu1$btnVerdictLocalization"
    fields["__EVENTARGUMENT"] = ""

    print(f"  עובר לדף חיפוש...")
    r = client.post(HOME_URL, data=fields)
    r.raise_for_status()
    search_html = decode_text(r)

    fields = parse_form_fields(search_html)
    fields["hdnSelectedTab"] = "1"
    fields["LocateByParameters1:ddlSelectCourt"] = court_id
    fields["LocateByParameters1:ddlSelectProceeding"] = "-1"
    fields["LocateByParameters1:ddlSelectCaseType"] = "-1"
    fields["LocateByParameters1:ddlSelectCaseInterest"] = "-1"
    fields["LocateByParameters1:ddlDecisionType"] = "-1"
    fields["LocateByParameters1:dateFrom"] = date
    fields["LocateByParameters1:DateTo"] = date
    fields["__EVENTTARGET"] = "ButtonsGroup1$btnLocate"
    fields["__EVENTARGUMENT"] = ""

    print(f"  מחפש...")
    r = client.post(SEARCH_URL, data=fields)
    r.raise_for_status()
    html = decode_text(r)
    rows = parse_results(html)
    return rows, html


def get_document_number(client: httpx.Client, results_html: str, row: DecisionRow) -> str:
    fields = parse_form_fields(results_html)
    fields["__EVENTTARGET"] = "btnDocument"
    fields["__EVENTARGUMENT"] = f"{row.case_id}&{row.document_id}&1"

    soup = BeautifulSoup(results_html, "html.parser")
    form = soup.find("form", {"id": "Form1"}) or soup.find("form", {"name": "Form1"})
    action = urljoin(OUTPUT_URL, form.get("action") if form else None or "")

    r = client.post(action or OUTPUT_URL, data=fields)
    r.raise_for_status()
    html = decode_text(r)
    final_url = str(r.url)

    query = parse_qs(urlparse(final_url).query)
    doc_num = (query.get("DocumentNumber") or [None])[0]
    if not doc_num:
        match = re.search(r"DocumentNumber=([0-9a-f]{32})", f"{final_url}\n{html}", re.I)
        doc_num = match.group(1) if match else None
    if not doc_num:
        raise RuntimeError(f"לא נמצא DocumentNumber עבור מסמך {row.document_id}")
    return doc_num


def download_pdf(client: httpx.Client, doc_num: str, dest: Path) -> int:
    viewer_url = f"{VIEWER_URL}?DocumentNumber={doc_num}"
    client.get(viewer_url).raise_for_status()

    def viewer_post(method: str, payload: dict) -> Any:
        r = client.post(
            f"{VIEWER_URL}/{method}",
            json=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": viewer_url,
            },
        )
        r.raise_for_status()
        body = r.json()
        return body.get("d", body)

    images_data = viewer_post("GetAllImages", {"documentNumber": doc_num})
    if not isinstance(images_data, list) or not images_data:
        raise RuntimeError("GetAllImages לא החזיר נתונים")

    pil_images = []
    for item in images_data:
        _, encoded = (item if isinstance(item, str) else str(item)).split(",", 1)
        encoded += "=" * (-len(encoded) % 4)
        pil_images.append(Image.open(io.BytesIO(base64.b64decode(encoded))))

    dest.parent.mkdir(parents=True, exist_ok=True)
    first, rest = pil_images[0].convert("RGB"), [img.convert("RGB") for img in pil_images[1:]]
    if rest:
        first.save(dest, save_all=True, append_images=rest)
    else:
        first.save(dest)

    for img in pil_images:
        img.close()
    return len(pil_images)


def safe_name(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text.strip()) or "document"


def main():
    print(f"\n{'='*50}")
    print(f"דמו הורדת פסקי דין")
    print(f"תאריך: {DATE}  |  ערכאה: {COURT_ID}  |  מקסימום: {MAX_DOCS} קבצים")
    print(f"{'='*50}\n")

    OUTPUT_DIR.mkdir(exist_ok=True)

    with httpx.Client(headers=HEADERS, follow_redirects=True, timeout=60) as client:
        print("שלב 1: חיפוש...")
        try:
            rows, results_html = search(client, DATE, COURT_ID)
        except Exception as e:
            print(f"\nשגיאה בחיפוש: {e}")
            print("ייתכן שהאתר חוסם בקשות HTTP ישירות (ללא דפדפן).")
            return

        published = [r for r in rows if r.is_published]
        print(f"\nנמצאו {len(rows)} תוצאות, {len(published)} פורסמו.")
        if len(rows) == 100:
            print("⚠️  בדיוק 100 תוצאות — ייתכן שהאתר חתך את הרשימה!")

        if not published:
            print("אין מסמכים להורדה.")
            return

        to_download = published[:MAX_DOCS]
        print(f"\nשלב 2: מוריד {len(to_download)} מסמכים ל-{OUTPUT_DIR}/\n")

        for i, row in enumerate(to_download, 1):
            print(f"  [{i}/{len(to_download)}] {row.case_display_identifier} (מסמך {row.document_id})")
            try:
                doc_num = get_document_number(client, results_html, row)
                filename = f"{safe_name(row.case_display_identifier)}_{row.document_id}.pdf"
                dest = OUTPUT_DIR / filename
                pages = download_pdf(client, doc_num, dest)
                print(f"    ✓ נשמר: {dest} ({pages} עמודים)")
            except Exception as e:
                print(f"    ✗ שגיאה: {e}")
            if i < len(to_download):
                time.sleep(1)

    print(f"\n{'='*50}")
    print(f"סיום. קבצים נשמרו בתיקיית: {OUTPUT_DIR.resolve()}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
