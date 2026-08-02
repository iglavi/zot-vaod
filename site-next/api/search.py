"""נקודת קצה לחיפוש המובנה (Vercel Python function, Flask/WSGI).
עוטפת את zot.search.simple_search הקיים בלי לשנות את הלוגיקה שלו."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, jsonify, request  # noqa: E402

from zot import search as zot_search  # noqa: E402
from _util import add_download_urls  # noqa: E402

app = Flask(__name__)


@app.route("/api/search", methods=["GET"])
def do_search():
    try:
        page = max(1, int(request.args.get("page", "1")))
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
