"""בניית האתר הסטטי (גילוי נאות) מתוך אינדקס ה-SQLite.

יוצר קובץ HTML יחיד ועצמאי עם כל הנתונים מוטמעים בתוכו — ניתן להעלאה
לכל אחסון סטטי חינמי (GitHub Pages, Netlify וכו') או לפתיחה ישירות בדפדפן.

הרצה:
    python -m zot.ingest        # קודם בונים את האינדקס
    python site/build.py        # ואז בונים את האתר
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = Path(__file__).resolve().parent.parent / "data" / "index.db"
TEMPLATE = Path(__file__).resolve().parent / "giluy-naot.template.html"
OUTPUT = Path(__file__).resolve().parent / "giluy-naot.html"

FIELDS = ("case_number", "parties", "court", "proceeding", "case_type", "matter",
          "decision_type", "decision_nature", "filed_date", "decision_date",
          "judge", "has_document", "full_text")


def build() -> None:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"SELECT {', '.join(FIELDS)} FROM verdicts "
        "ORDER BY COALESCE(NULLIF(decision_date,''), filed_date) DESC, id DESC"
    ).fetchall()
    conn.close()

    data = []
    for r in rows:
        d = dict(r)
        if not d["has_document"]:
            d["full_text"] = ""  # שולחים רק טקסט שאכן קיים, כדי לצמצם את גודל הקובץ
        data.append(d)

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # הימלטות של '<' מונעת שבירה של תג ה-script (תקין בתוך מחרוזת JSON)
    payload = payload.replace("<", "\\u003c")

    html = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", payload)
    OUTPUT.write_text(html, encoding="utf-8")
    print(f"נבנה האתר: {OUTPUT}  ({len(data)} רשומות, {OUTPUT.stat().st_size:,} בתים)")


if __name__ == "__main__":
    build()
