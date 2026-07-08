"""סיכום מובנה (AI) לפסקי דין ארוכים בלבד — בהשראת "Structural Analysis"
של Indian Kanoon, מותאם למונחי המשפט הישראלי.

כדי לא לבזבז טוקנים על "החלטות" טכניות קצרות (הרוב הגדול של המאגר), קודם
בודקים באופן מקומי וחינמי כמה עמודים יש לקובץ ה-PDF המקורי (אין צורך
לשלוח שום דבר ל-AI כדי לדעת את זה) — ורק אם 3 עמודים ומעלה (config.SUMMARY_MIN_PAGES)
שולחים את הטקסט לסיכום.

תוצאה של פסק דין שכבר סוכם נשמרת לצמיתות בטבלת ai_summaries (לא נמחקת
בבנייה מחדש של האינדקס), כך שלעולם לא משלמים פעמיים על אותו מסמך.

מריצים בעצמו:  python -m zot.summarize
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from . import config

_CATEGORIES = {
    "facts": "רקע עובדתי",
    "issues": "השאלות שבמחלוקת",
    "claimant_arguments": "טענות התובע/המערער/העותר",
    "respondent_arguments": "טענות הנתבע/המשיב",
    "legal_analysis": "ניתוח משפטי (כולל אזכור תקדימים, אם רלוונטי)",
    "ruling": "הכרעת בית המשפט ומסקנה",
}

_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string", "description": v} for k, v in _CATEGORIES.items()},
    "required": list(_CATEGORIES),
    "additionalProperties": False,
}

_SYSTEM = (
    "אתה עוזר משפטי המסכם פסקי דין של בתי המשפט בישראל. חלץ מגוף פסק הדין "
    "שלמעלה סיכום מובנה לפי הקטגוריות המבוקשות, בעברית, בקצרה ובדיוק. "
    "אם קטגוריה מסוימת אינה רלוונטית או לא ניתן לזהות אותה בטקסט, השאר אותה "
    "כמחרוזת ריקה — אל תמציא תוכן."
)


def _page_count(pdf_path: Path) -> int:
    """מספר עמודים אמיתי מתוך מבנה קובץ ה-PDF — פעולה מקומית, ללא עלות/טוקנים."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(pdf_path)).pages)
    except Exception:
        return 0


def _estimate_pages_from_text(text: str) -> int:
    """גיבוי גס אם אין PDF זמין: כ-2,500 תווים לעמוד טקסט משפטי בעברית."""
    return max(1, len(text or "") // 2500)


def has_ai_credentials() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _summarize_one(client, full_text: str) -> dict | None:
    try:
        resp = client.messages.create(
            model=config.SUMMARY_MODEL,
            max_tokens=1200,
            system=_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _SUMMARY_SCHEMA}},
            messages=[{"role": "user", "content": full_text[:config.SUMMARY_MAX_CHARS]}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return json.loads(text) if text else None
    except Exception:
        return None


def run(db_path: Path | None = None, docs_dir: Path | None = None, verbose: bool = True) -> dict:
    db_path = Path(db_path or config.DB_PATH)
    docs_dir = Path(docs_dir or config.DOCS_DIR)
    stats = {"summarized": 0, "skipped_short": 0, "skipped_cached": 0, "errors": 0}

    if not has_ai_credentials():
        if verbose:
            print("סיכום AI מדולג: אין ANTHROPIC_API_KEY מוגדר.")
        return stats
    if not db_path.exists():
        return stats

    import anthropic
    client = anthropic.Anthropic()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, filename, full_text, file_relpath_pdf FROM verdicts "
        "WHERE has_document = 1 AND (structural_summary IS NULL OR structural_summary = '')"
    ).fetchall()

    for row in rows:
        stem = row["filename"]
        pdf_rel = row["file_relpath_pdf"]
        pages = _page_count(docs_dir / pdf_rel) if pdf_rel else 0
        if pages == 0:
            pages = _estimate_pages_from_text(row["full_text"])
        if pages < config.SUMMARY_MIN_PAGES:
            stats["skipped_short"] += 1
            continue

        summary = _summarize_one(client, row["full_text"] or "")
        if summary is None:
            stats["errors"] += 1
            continue

        payload = json.dumps(summary, ensure_ascii=False)
        conn.execute(
            "INSERT INTO ai_summaries (stem, structural_summary, created_at) "
            "VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(stem) DO UPDATE SET structural_summary = excluded.structural_summary",
            (stem, payload),
        )
        conn.execute("UPDATE verdicts SET structural_summary = ? WHERE id = ?", (payload, row["id"]))
        stats["summarized"] += 1
        conn.commit()

    conn.close()
    if verbose:
        print(f"סיכום AI: {stats['summarized']} פסקי דין סוכמו, "
              f"{stats['skipped_short']} דולגו (קצרים מדי), {stats['errors']} שגיאות.")
    return stats


if __name__ == "__main__":
    run()
