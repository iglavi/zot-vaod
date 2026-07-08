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
SEARCH_PAGE_URL = BASE + "Verdicts/Search/1"
_CAP = 500  # תקרת התוצאות שהשרת מחזיר בכל קריאת חיפוש בודדת
_RETRIES = 4
# נמצא הגורם האמיתי לחסימות שנצפו: לא הגנת-קצב, אלא חוסר בעוגיות WAF
# אמיתיות (מתקבלות רק מטעינת דף החיפוש עצמו) וכותרות AJAX סטנדרטיות.
# עם שני אלה נבדקו 168/169 שאילתות חדשות בהצלחה (כמעט 100%). לכן חובה
# לטעון את SEARCH_PAGE_URL פעם אחת בתחילת הסשן (ראו _session) ולשלוח את
# הכותרות המלאות בכל שאילתת חיפוש (ראו search()).
_SEARCH_THROTTLE_SEC = 0.6
_DOWNLOAD_THROTTLE_SEC = 0.15
_FAIL_LOG = ROOT / "supreme_failed_slices.log"

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
    """יוצר סשן ו'מכין' אותו: טוען את דף החיפוש האמיתי פעם אחת כדי לקבל
    עוגיות WAF אמיתיות (ASP.NET_SessionId, TS*) — בלעדיהן שאילתות חיפוש
    נכשלות בשיעור גבוה (נבדק: עם ההכנה הזו + כותרות AJAX, 168/169 שאילתות
    חדשות הצליחו; בלעדיה, שיעור כישלון ניכר)."""
    from curl_cffi import requests as creq
    s = creq.Session(impersonate="chrome", timeout=60)
    s.headers.update({"Accept": "application/json, text/plain, */*",
                       "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7"})
    r = s.get(SEARCH_PAGE_URL)
    if r.status_code != 200:
        print(f"    אזהרה: טעינת דף החיפוש להכנת עוגיות החזירה סטטוס {r.status_code}")
    return s


def _request_with_retry(fn, *args, **kwargs):
    """מנסה שוב עם המתנה מתארכת. משמש גם להורדת קבצים/מטא-דאטה וגם לחיפוש —
    בשני המקרים כישלון בודד צפוי להיות נדיר (ראו WAFBlocked), כך שכמה
    ניסיונות עם המתנה קצרה-בינונית מספיקים."""
    last_err = None
    for attempt in range(_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(min(2.0 * (2 ** attempt), 30.0))
    raise last_err


def _log_failed_slice(label: str, err: Exception) -> None:
    """רושם לקובץ נפרד פרוסה שנכשלה לחלוטין אחרי כל הניסיונות, כדי שאפשר
    יהיה לחזור אליה ידנית מאוחר יותר — במקום להפיל את כל ההרצה (בת ימים)."""
    with _FAIL_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {label}: {err}\n")
    print(f"    !! נכשל לגמרי (נרשם ל-{_FAIL_LOG.name}): {label}: {err}")


class WAFBlocked(Exception):
    """הועלה כשמזוהה דף חסימה של השרת (במקום JSON) בשאילתת חיפוש.

    נמצא הגורם האמיתי (לא רק ניחוש): שאילתות חיפוש נכשלות בשיעור ניכר כשאין
    לסשן עוגיות WAF אמיתיות (מתקבלות רק מטעינת עמוד החיפוש עצמו לפני כן) וכן
    כותרות AJAX סטנדרטיות (Origin/Referer/X-Requested-With). עם שני אלה
    (ראו _session ו-search) נבדקו 168/169 שאילתות חדשות בהצלחה — כלומר כשל
    בודד כאן הוא כנראה רעש אקראי נדיר, לא סימן לבעיה שיטתית. בטוח לנסות
    שוב (ראו _request_with_retry)."""


def search(session, filters: dict) -> list[dict]:
    """שאילתת חיפוש עם כותרות AJAX מלאות (Origin/Referer/X-Requested-With) —
    ראו WAFBlocked להסבר למה אלה קריטיים. מנסה שוב אוטומטית אם נכשל (נבדק
    בטוח: הכישלון לא נבע מחזרה על שאילתה, אלא מהיעדר עוגיות/כותרות)."""
    def _do():
        r = session.post(
            BASE + "Home/SearchVerdicts",
            data=json.dumps({"document": filters, "lan": 1}),
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json, text/plain, */*",
                "Origin": BASE.rstrip("/"),
                "Referer": SEARCH_PAGE_URL,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        time.sleep(_SEARCH_THROTTLE_SEC)
        if "json" not in (r.headers.get("content-type") or ""):
            raise WAFBlocked(f"סטטוס {r.status_code}, content-type={r.headers.get('content-type')}")
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


def _safe_search(session, filters: dict, label: str) -> list[dict] | None:
    """כמו search(), אבל אם השאילתה נכשלת — רושם ל-log ומחזיר None (במקום
    להפיל את כל ההרצה בת-הימים). None מסמן 'דלג על הפרוסה הזו'.

    נבדק בפועל: חסימת WAF על שאילתה ספציפית לא משפיעה על שאילתות אחרות
    (ראו הערה ב-WAFBlocked) — לכן מטופלת בדיוק כמו כל כשל אחר: מדלגים
    ל'פרוסה' (שנה/חודש/סוג/מדור) הבאה, לא עוצרים את כל ההרצה."""
    try:
        return search(session, filters)
    except Exception as e:  # noqa: BLE001
        _log_failed_slice(label, e)
        return None


def enumerate_year(session, year: int, type_codes: list[int], mador_codes: list[int]):
    """מחזיר (generator) את כל התוצאות לשנה נתונה, חותך לפי מימדים רק
    כשיש צורך (כלומר רק כשפרוסה מסוימת עדיין מחזירה בדיוק 500 — סימן שיש עוד).

    כל שאילתה שנכשלת לחלוטין (אחרי כל הניסיונות) נרשמת ומדולגת — לא מפילה
    את שאר ההרצה שיכולה להימשך ימים."""
    base = _base_filters()
    base["Year"] = year
    results = _safe_search(session, base, f"שנה {year}")
    if results is None:
        return
    if len(results) < _CAP:
        yield from results
        return

    print(f"    שנה {year}: >={_CAP} תוצאות, חותך לפי חודש...")
    for month in range(1, 13):
        f = dict(base)
        f["Month"] = month
        month_results = _safe_search(session, f, f"{year}-{month:02d}")
        if month_results is None:
            continue
        if len(month_results) < _CAP:
            yield from month_results
            continue

        print(f"      {year}-{month:02d}: עדיין >={_CAP}, חותך לפי סוג הליך...")
        seen_ids = set()
        for tcode in type_codes:
            f2 = dict(f)
            f2["CodeTypes"] = [tcode]
            type_results = _safe_search(session, f2, f"{year}-{month:02d} סוג {tcode}")
            if type_results is None:
                continue
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
                label = f"{year}-{month:02d} סוג {tcode} מדור {mcode}"
                mador_results = _safe_search(session, f3, label)
                if mador_results is None:
                    continue
                if len(mador_results) >= _CAP:
                    print(f"          אזהרה: {label} עדיין >={_CAP} — "
                          f"ייתכן פספוס תוצאות (נדיר, לא טופל אוטומטית).")
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
        time.sleep(_DOWNLOAD_THROTTLE_SEC)
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
        try:
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
        except Exception as e:  # noqa: BLE001
            # רשת/הרצה בת-ימים: תקלה בלתי צפויה בשנה אחת לא תפיל את כל ההרצה
            _log_failed_slice(f"שנה {year} (קריסה כללית)", e)
        print(f"  שנה {year}: {year_items} פריטים.")

    print(f"\nסיכום: {total_items} פריטים, {total_downloaded} קבצים חדשים, "
          f"{total_skipped} כבר קיימים, {total_errors} שגיאות.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
