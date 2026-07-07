"""מנוע החיפוש החכם (AI): הבנת שאלה בשפה חופשית, אחזור פסקי דין רלוונטיים,
ומתן תשובה מנומקת עם הפניות למספרי התיקים — באמצעות Claude.

זרימת RAG בשני שלבים:
1. ניתוח השאלה -> מילות חיפוש + טווח תאריכים (מיפוי "החודש האחרון" וכו').
2. אחזור פסקי הדין הרלוונטיים והעברתם למודל למתן תשובה מבוססת-מקורות.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date

from . import config, search

_SYSTEM_ANSWER = (
    "אתה עוזר מחקר משפטי הבקיא בפסיקת בתי המשפט בישראל. "
    "ענה בעברית, בבהירות ובדיוק, אך ורק על סמך פסקי הדין שסופקו לך למטה. "
    "בכל קביעה הפנה למספר התיק הרלוונטי (למשל: 'ראו ת\"א 4934-07-24'), "
    "וציין את בית המשפט והשופט/ת כשהדבר רלוונטי. "
    "אם התשובה אינה מצויה בפסקי הדין שסופקו — אמור זאת במפורש ואל תמציא מידע. "
    "סכם בסוף אילו תיקים שימשו למענה."
)

_ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "search_terms": {
            "type": "array", "items": {"type": "string"},
            "description": "מילות מפתח בעברית לחיפוש בטקסט פסקי הדין (מונחים משפטיים, נושאים).",
        },
        "parties": {
            "type": "array", "items": {"type": "string"},
            "description": "שמות של צדדים/אנשים/חברות שהוזכרו בשאלה, אם יש.",
        },
        "judge": {"type": "string", "description": "שם שופט/ת אם הוזכר, אחרת ריק."},
        "date_from": {"type": "string", "description": "תאריך התחלה בפורמט YYYY-MM-DD, או ריק."},
        "date_to": {"type": "string", "description": "תאריך סיום בפורמט YYYY-MM-DD, או ריק."},
    },
    "required": ["search_terms", "parties", "judge", "date_from", "date_to"],
    "additionalProperties": False,
}


def has_ai_credentials() -> bool:
    """בודק אם קיים מפתח API של Anthropic בסביבה."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def get_client():
    import anthropic
    return anthropic.Anthropic()


def _fts_from_terms(terms: list[str]) -> str:
    tokens: list[str] = []
    for term in terms:
        for tok in re.findall(r"[\w֐-׿]+", term or "", flags=re.UNICODE):
            if len(tok) >= 2:
                tokens.append(tok)
    seen: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.append(t)
    return " OR ".join(f'"{t}"' for t in seen)


def analyze_query(client, question: str, today: str | None = None) -> dict:
    """שלב 1: הפיכת שאלה חופשית למילות חיפוש + טווח תאריכים."""
    today = today or date.today().isoformat()
    prompt = (
        f"התאריך היום הוא {today}.\n"
        "להלן שאלה של משתמש על פסקי דין של בתי המשפט בישראל. "
        "חלץ ממנה מילות חיפוש בעברית לאיתור פסקי הדין הרלוונטיים, "
        "וכן טווח תאריכים אם השאלה מתייחסת לזמן (לדוגמה: 'בשנה האחרונה', "
        "'בחודש שעבר') — המר אותו לתאריכי YYYY-MM-DD יחסית להיום.\n\n"
        f"השאלה: {question}"
    )
    try:
        resp = client.messages.create(
            model=config.AI_MODEL,
            max_tokens=600,
            output_config={"format": {"type": "json_schema", "schema": _ANALYZE_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        data = json.loads(text)
    except Exception:
        # גיבוי: משתמשים בשאלה עצמה כמילות חיפוש
        data = {"search_terms": [question], "parties": [], "judge": "",
                "date_from": "", "date_to": ""}
    data.setdefault("search_terms", [])
    data.setdefault("parties", [])
    data.setdefault("judge", "")
    data.setdefault("date_from", "")
    data.setdefault("date_to", "")
    return data


def retrieve(analysis: dict):
    """שלב 2א: אחזור פסקי הדין הרלוונטיים לפי הניתוח."""
    all_terms = list(analysis.get("search_terms", [])) + list(analysis.get("parties", []))
    if analysis.get("judge"):
        all_terms.append(analysis["judge"])
    fts = _fts_from_terms(all_terms)
    return search.retrieve_for_ai(
        fts_query=fts,
        date_from=analysis.get("date_from", ""),
        date_to=analysis.get("date_to", ""),
        limit=config.AI_MAX_DOCS,
    )


def _build_context(verdicts) -> str:
    blocks = []
    for v in verdicts:
        text = (v["full_text"] or "")[: config.AI_MAX_CHARS_PER_DOC]
        header = (
            f"מספר תיק: {v['case_number']}\n"
            f"צדדים: {v['parties']}\n"
            f"בית משפט: {v['court']}\n"
            f"שופט/ת: {v['judge']}\n"
            f"תאריך החלטה: {v['decision_date'] or v['filed_date']}\n"
            f"סוג החלטה: {v['decision_type']}"
        )
        blocks.append(f"<פסק_דין>\n{header}\n---\n{text}\n</פסק_דין>")
    return "\n\n".join(blocks)


def answer_stream(client, question: str, verdicts):
    """שלב 2ב: מחזיר גנרטור של קטעי טקסט (streaming) עם התשובה המנומקת."""
    context = _build_context(verdicts)
    user_content = (
        f"פסקי הדין הרלוונטיים:\n\n{context}\n\n"
        f"===\n\nהשאלה: {question}\n\n"
        "ענה על השאלה על סמך פסקי הדין שלמעלה בלבד, עם הפניות למספרי התיקים."
    )
    with client.messages.stream(
        model=config.AI_MODEL,
        max_tokens=4000,
        system=_SYSTEM_ANSWER,
        messages=[{"role": "user", "content": user_content}],
    ) as stream:
        for chunk in stream.text_stream:
            yield chunk
