"""נקודת קצה לחיפוש המובנה (Vercel Python function, Flask/WSGI).
עוטפת את zot.search.simple_search הקיים בלי לשנות את הלוגיקה שלו."""
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, jsonify, request  # noqa: E402

from zot import search as zot_search  # noqa: E402
from _util import add_download_urls  # noqa: E402

app = Flask(__name__)

_SNIPPET_CONTEXT_CHARS = 160
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _build_snippet(text: str, terms: list[str]) -> str | None:
    """קטע-תצוגה (HTML) סביב ההתאמה הראשונה של אחת ממילות החיפוש בגוף
    המסמך, עם <mark> סביב ההתאמה. escape ידני לשאר הטקסט (לא ל-<mark>
    עצמו) - הטקסט מקורו במסמך פסק-הדין עצמו (לא קלט משתמש גולמי), אבל
    עדיין עלול להכיל תווי HTML מקריים (למשל ציטוט בתוך הטקסט)."""
    if not text or not terms:
        return None
    lower = text.lower()
    match_start = None
    match_len = 0
    for term in terms:
        idx = lower.find(term.lower())
        if idx != -1:
            match_start = idx
            match_len = len(term)
            break
    if match_start is None:
        return None
    start = max(0, match_start - _SNIPPET_CONTEXT_CHARS)
    end = min(len(text), match_start + match_len + _SNIPPET_CONTEXT_CHARS)
    before = html.escape(text[start:match_start])
    matched = html.escape(text[match_start:match_start + match_len])
    after = html.escape(text[match_start + match_len:end])
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{before}<mark>{matched}</mark>{after}{suffix}"


@app.route("/api/search", methods=["GET"])
def do_search():
    try:
        # תקרה עליונה שפויה (לא רק page<1): total עצמו כבר מוגבל ל-
        # _BROAD_FILTER_CAP (5,000 / 10-לעמוד = עמוד 500 לכל היותר), אז
        # page גדול בהרבה ממילא לא יחזיר תוצאות - אבל page ענק-קיצוני
        # (page=10**30 למשל) עלול לחרוג מתחום ה-INTEGER 64-בית של SQLite
        # ב-OFFSET ולהיכשל בשגיאת DB במקום סתם להחזיר רשימה ריקה.
        page = min(1_000_000, max(1, int(request.args.get("page", "1"))))
    except ValueError:
        page = 1
    limit = 10
    try:
        rows, total = zot_search.simple_search(
            name=request.args.get("name", ""),
            judge=request.args.get("judge", ""),
            court_type=request.args.get("court_type", ""),
            city=request.args.get("city", ""),
            case_number=request.args.get("case_number", ""),
            free_text=request.args.get("free_text", ""),
            match_mode=request.args.get("match_mode", "any"),
            proceeding=request.args.get("proceeding", ""),
            case_type=request.args.get("case_type", ""),
            date_from=request.args.get("date_from", ""),
            date_to=request.args.get("date_to", ""),
            sort=request.args.get("sort", "newest"),
            limit=limit,
            offset=(page - 1) * limit,
        )
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500

    # תקציר עם הדגשה - רק כשיש חיפוש חופשי בטקסט (בלעדיו אין מה להדגיש),
    # ורק לעשרת התוצאות של העמוד הנוכחי (לא כל ההתאמות). full_text כן חי
    # בטבלת verdicts עצמה (verdicts_fts הוא contentless, אבל v.* ב-JOIN
    # מביא אותו מהטבלה הרגילה - ראו retrieve_for_ai) - שאילתה נוספת קטנה
    # ב-DB, לא קריאת R2.
    free_text = request.args.get("free_text", "")
    terms = [t for t in _TOKEN_RE.findall(free_text) if len(t) >= 2]
    if terms and rows:
        try:
            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" * len(ids))
            conn = zot_search.get_conn()
            cur = conn.execute(f"SELECT id, full_text FROM verdicts WHERE id IN ({placeholders})", ids)
            texts = {r["id"]: r["full_text"] for r in zot_search._rows(cur, cur.fetchall())}
        except Exception as e:  # noqa: BLE001
            print(f"snippet fetch failed: {type(e).__name__}: {e}")
            texts = {}
        for r in rows:
            r["snippet"] = _build_snippet(texts.get(r["id"]) or "", terms)

    # total מוגבל בפועל ל-_BROAD_FILTER_CAP עבור חיפושים רחבים-מדי (ראו
    # ההערה המפורטת ב-zot/search.py: simple_search) - כשמגיעים לתקרה הזו,
    # total אינו הספירה האמיתית אלא רק "לפחות כמה" (ה-UI מציג "מעל X").
    capped = total >= zot_search._BROAD_FILTER_CAP
    return jsonify({"results": add_download_urls(rows), "total": total, "capped": capped,
                    "page": page, "per_page": limit})


@app.route("/api/search/options", methods=["GET"])
def options():
    try:
        return jsonify({
            "court_types": zot_search.court_type_options(),
            "case_types": zot_search.distinct_case_types(),
        })
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
