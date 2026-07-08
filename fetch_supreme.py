#!/usr/bin/env python3
"""הורדה ממאגר פסקי הדין וההחלטות של בית המשפט העליון
(supremedecisions.court.gov.il) — מאגר נפרד מזה של fetch_daily.py.

בניגוד למאגר decisions.court.gov.il, האתר הזה **פתוח לחלוטין** (אין NTLM,
אין WAF חוסם) ומספק API פשוט מבוסס JSON:
  • חיפוש:  POST Home/SearchVerdicts  — עד 500 תוצאות בכל קריאה (אין "עמוד הבא"
    אמיתי — צריך לחתוך את השאילתה לפי מימדים עד שכל פרוסה קטנה מ-500).
  • הורדה:  GET Home/Download?path=...&fileName=...&type=4  (PDF) / type=5 (Word)

אסטרטגיית המניה (כדי לא לפספס תוצאות מוסתרות מעבר לגבול 500):
  שנה -> אם עדיין 500 בדיוק (סימן שיש עוד) -> חודש -> סוג הליך -> מדור ->
  (נדיר) מספר תיק בודד. בכל שלב, אם התוצאה קטנה מ-500 — זו הרשימה המלאה
  לאותה פרוסה, ואין צורך לחתוך עמוק יותר.

הרצה:  python fetch_supreme.py
משתני סביבה (מוגדרים ב-.env):
  SUPREME_YEAR_FROM, SUPREME_YEAR_TO — טווח שנים (ברירת מחדל: השנה הנוכחית בלבד)
  SUPREME_DOCS_DIR — תיקיית יעד (ברירת מחדל: documents_supreme/)

הרצה חוזרת (resume) בטוחה: קבצים שכבר ירדו מדולגים אוטומטית (בדיקת קיום קובץ),
כך שאפשר להפסיק ולהריץ מחדש בלי לאבד התקדמות או להוריד כפול.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from zot import config  # noqa: E402

BASE = "https://supremedecisions.court.gov.il/"
_CAP = 500  # תקרת התוצאות שהשרת מחזיר בכל קריאת חיפוש בודדת
_RETRIES = 3
_THROTTLE_SEC = 0.15  # השהיה קטנה בין קריאות — נימוס כלפי השרת

DOCS_DIR = Path(os.environ.get("SUPREME_DOCS_DIR", ROOT / "documents_supreme"))
YEAR_FROM = int(os.environ.get("SUPREME_YEAR_FROM", str(date.today().year)))
YEAR_TO = int(os.environ.get("SUPREME_YEAR_TO", str(date.today().year)))

_SEARCH_TEXT_EMPTY = [{"Text": "", "textOperator": 1, "option": "2",
                       "Inverted": False, "Synonym": False, "NearDistance": 3,
                       "MatchOrder": False}]
_PARTIES_EMPTY = [{"Text": "", "textOperator": 2, "option": "2",
                   "Inverted": False, "Synonym": False, "NearDistance": 3,
                   "MatchOrder": False}]


def _base_filters() -> dict:
    return {
        "Year": None, "Month": None, "CaseNum": None, "Technical": None,
        "fromPages": None, "toPages": None, "dateType": 1,
        "PublishFrom": None, "PublishTo": None, "publishDate": 8,
        "translationDateType": 1, "translationPublishFrom": None,
        "translationPublishTo": None, "translationPublishDate": 8,
        "SearchText": _SEARCH_TEXT_EMPTY, "Judges": None,
        "Parties": _PARTIES_EMPTY, "Counsel": _PARTIES_EMPTY,
        "Mador": None, "CodeMador": [], "TypeCourts": None, "TypeCourts1": None,
        "TerrestrialCourts": None, "LastInyan": None, "LastCourtsYear": None,
        "LastCourtsMonth": None, "LastCourtCaseNum": None, "Old": False,
        "JudgesOperator": 2, "Judgment": None, "Type": None, "CodeTypes": [],
        "CodeJudges": [], "Inyan": None, "CodeInyan": [],
        "AllSubjects": [{"Subject": None, "SubSubject": None, "SubSubSubject": None}],
        "CodeSub2": [], "Category1": None, "Category2": None, "Category3": None,
        "CodeCategory3": [], "OldMainNumFormat": False,
    }


def _session():
    from curl_cffi import requests as creq
    s = creq.Session(impersonate="chrome", timeout=60)
    s.headers.update({"Accept": "application/json"})
    return s


def _request_with_retry(fn, *args, **kwargs):
    last_err = None
    for attempt in range(_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.0 * (attempt + 1))
    raise last_err


def search(session, filters: dict) -> list[dict]:
    def _do():
        r = session.post(
            BASE + "Home/SearchVerdicts",
            data=json.dumps({"document": filters, "lan": 1}),
            headers={"Content-Type": "application/json;charset=UTF-8"},
        )
        time.sleep(_THROTTLE_SEC)
        return r.json()["data"]
    return _request_with_retry(_do)


def get_type_codes(session) -> list[int]:
    def _do():
        r = session.get(BASE + "Home/GetTypeDocument?lan=1")
        return [item["value"] for item in r.json()]
    return _request_with_retry(_do)


def get_mador_codes(session) -> list[int]:
    def _do():
        r = session.get(BASE + "Home/GetMadors?lan=1")
        return [item["value"] for item in r.json()]
    return _request_with_retry(_do)


def get_max_case_num(session, year: int) -> int:
    def _do():
        r = session.get(BASE + "Home/GetCasesYearNum?lan=1")
        for item in r.json():
            if item["parent"] == year:
                return item["value"]
        return 0
    return _request_with_retry(_do)


def enumerate_year(session, year: int, type_codes: list[int], mador_codes: list[int]):
    """מחזיר (generator) את כל התוצאות לשנה נתונה, חותך לפי מימדים רק
    כשיש צורך (כלומר רק כשפרוסה מסוימת עדיין מחזירה בדיוק 500 — סימן שיש עוד)."""
    base = _base_filters()
    base["Year"] = year
    results = search(session, base)
    if len(results) < _CAP:
        yield from results
        return

    print(f"    שנה {year}: >={_CAP} תוצאות, חותך לפי חודש...")
    for month in range(1, 13):
        f = dict(base)
        f["Month"] = month
        month_results = search(session, f)
        if len(month_results) < _CAP:
            yield from month_results
            continue

        print(f"      {year}-{month:02d}: עדיין >={_CAP}, חותך לפי סוג הליך...")
        seen_ids = set()
        for tcode in type_codes:
            f2 = dict(f)
            f2["CodeTypes"] = [tcode]
            type_results = search(session, f2)
            if len(type_results) < _CAP:
                for item in type_results:
                    if item["Id"] not in seen_ids:
                        seen_ids.add(item["Id"])
                        yield item
                continue

            print(f"        {year}-{month:02d} סוג {tcode}: עדיין >={_CAP}, חותך לפי מדור...")
            for mcode in mador_codes:
                f3 = dict(f2)
                f3["CodeMador"] = [mcode]
                mador_results = search(session, f3)
                if len(mador_results) >= _CAP:
                    print(f"          אזהרה: {year}-{month:02d} סוג {tcode} מדור {mcode} "
                          f"עדיין >={_CAP} — ייתכן פספוס תוצאות (נדיר, לא טופל אוטומטית).")
                for item in mador_results:
                    if item["Id"] not in seen_ids:
                        seen_ids.add(item["Id"])
                        yield item


def download_one(session, item: dict) -> tuple[int, int]:
    """מוריד PDF ו-Word עבור פריט אחד. מחזיר (הורדו, כבר קיימים).

    חלק מהרשומות (בעיקר תיקים ישנים) הן רשומות אינדקס בלבד, ללא קובץ
    דיגיטלי מצורף (Path/FileName ריקים) — מדלגים עליהן בשקט."""
    path = item.get("PathForWeb")
    fname = item.get("FileName")
    if not path or not fname or not item.get("Path"):
        return 0, 0
    dest_dir = DOCS_DIR / item["Path"].replace("\\", "/")
    dest_dir.mkdir(parents=True, exist_ok=True)

    downloaded = skipped = 0
    for type_code, ext in ((4, "pdf"), (5, "docx")):
        target = dest_dir / f"{fname}.{ext}"
        if target.exists() and target.stat().st_size > 0:
            skipped += 1
            continue
        url = (BASE + "Home/Download?path=" + quote(path) +
               "&fileName=" + quote(fname) + f"&type={type_code}")

        def _do():
            return session.get(url)
        try:
            r = _request_with_retry(_do)
        except Exception as e:  # noqa: BLE001
            print(f"    שגיאה בהורדת {fname}.{ext}: {e}")
            continue
        time.sleep(_THROTTLE_SEC)
        if r.status_code == 200 and r.content:
            target.write_bytes(r.content)
            downloaded += 1
        else:
            print(f"    שגיאה בהורדת {fname}.{ext}: סטטוס {r.status_code}")
    return downloaded, skipped


def main() -> int:
    print(f"טווח שנים: {YEAR_FROM}-{YEAR_TO}. יעד: {DOCS_DIR}")
    session = _session()
    type_codes = get_type_codes(session)
    mador_codes = get_mador_codes(session)
    print(f"סוגי הליך: {type_codes}, מדורים: {mador_codes}")

    total_items = total_downloaded = total_skipped = total_errors = 0
    for year in range(YEAR_FROM, YEAR_TO + 1):
        print(f"--- שנה {year} ---")
        year_items = 0
        for item in enumerate_year(session, year, type_codes, mador_codes):
            year_items += 1
            total_items += 1
            try:
                dl, sk = download_one(session, item)
                total_downloaded += dl
                total_skipped += sk
            except Exception as e:  # noqa: BLE001
                print(f"  שגיאה בפריט {item.get('Id')}: {e}")
                total_errors += 1
            if total_items % 100 == 0:
                print(f"  ...טופלו {total_items} פריטים סה\"כ "
                      f"({total_downloaded} קבצים חדשים)")
        print(f"  שנה {year}: {year_items} פריטים.")

    print(f"\nסיכום: {total_items} פריטים, {total_downloaded} קבצים חדשים, "
          f"{total_skipped} כבר קיימים, {total_errors} שגיאות.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
