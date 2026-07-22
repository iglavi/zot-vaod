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
    "אין צורך בסיכום נפרד בסוף של אילו תיקים שימשו למענה — האתר כבר "
    "מציג רשימה נפרדת של פסקי הדין שנשלפו, ליד התשובה; הפניות מספר-תיק "
    "בתוך גוף התשובה (כנדרש למעלה) מספיקות.\n\n"
    "לגבי שאלות 'כמה'/סטטיסטיקה: אם ניתן לך למטה 'מספר תוצאות כולל' "
    "מפורש — זהו המספר האמיתי (ספירה ישירה במסד הנתונים), וזה המספר "
    "שיש לצטט.\n\n"
    "חשוב מאוד לגבי ניסוח, ואנא הקפד על כך בכל תשובה: אל תרמוז, בשום "
    "ניסוח, שמדובר בתת-קבוצה, מדגם, דוגמאות, או חומר שנבחר/הוצג/סופק/ניתן "
    "לך — למשל 'פסקי הדין שהוצגו לי', 'מבין החומר שסופק', 'בפסקי הדין "
    "המוצגים/שניתנו/העומדים לרשותי', 'מהדוגמאות הבאות', 'אלו הרלוונטיים "
    "ביותר' — כל ניסוח כזה אסור, גם כשאין בו ציון מספר. "
    "יחד עם זאת, אל תרמוז גם את ההפך — אל תציג את פסקי הדין שלמטה כאילו "
    "הם *כל* פסקי הדין הקיימים בנושא (זה עצמו מצג לא-מדויק). פשוט הימנע "
    "כליל מהתייחסות לשלמות/חלקיות הרשימה בכל כיוון: לא 'מדגם' ולא 'כל "
    "הפסיקה בנושא'. התייחס לפסקי הדין ישירות ובאופן ענייני, כאילו אתה "
    "פשוט מתאר את הפסיקה עצמה, בלי טענת שלמות: 'להלן פסקי דין העוסקים "
    "בנושא X:' / 'נמצאו החלטות הדנות ב-X, ובהן:' / 'בעניין זה נפסק:' — "
    "לא 'פסקי הדין העוסקים בנושא X הם' (משתמע ככל הרשימה) ולא 'להלן "
    "דוגמאות/מדגם שהוצגו לי' (משתמע כחלקי-ומצוין-ככזה). קרא את מה שכתבת "
    "לפני שליחתו ווודא שאין בו רמז לא לשלמות ולא לחלקיות של הרשימה.\n\n"
    "לגבי אורך: היה תמציתי במידה מתונה - הימנע ממשפטי פתיחה/סיכום "
    "גנריים שלא מוסיפים מידע (למשל חזרה כללית על השאלה לפני שעונים "
    "עליה), וצמצם ניסוחים חוזרים. אל תקצר את התוכן המשפטי המהותי עצמו -"
    " מספרי תיקים, שמות שופטים, נימוקים, ותוצאות ההליך צריכים להישאר "
    "מלאים ומדויקים כפי שהיו. המטרה היא תשובה קצת יותר דחוסה, לא תשובה "
    "שטחית יותר."
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
        "court_scope": {
            "type": "string", "enum": ["", "supreme", "general"],
            "description": (
                "'supreme' אם השאלה מתייחסת ספציפית לבית המשפט העליון "
                "(או בג\"ץ), 'general' אם היא מתייחסת לבתי משפט אחרים "
                "בלבד (שלום/מחוזי/עבודה וכו', לא העליון), אחרת ריק."
            ),
        },
        "is_followup": {
            "type": "boolean",
            "description": (
                "true אם השאלה הנוכחית היא המשך ישיר לשיחה הקודמת (מתייחסת "
                "במשתמע לאותו נושא/מסמכים שכבר עלו, למשל 'תן דוגמה נוספת', "
                "'תרחיב', 'מדגם רחב יותר' — בלי לפרט מחדש את הנושא) — במקרה "
                "כזה יש לשאוב את הנושא/מונחי החיפוש מהשיחה הקודמת, לא רק "
                "מהמשפט הנוכחי. false אם זו שאלה עצמאית בנושא חדש/אחר."
            ),
        },
        "date_sort": {
            "type": "string", "enum": ["relevance", "oldest", "newest"],
            "description": (
                "כיוון המיון הרצוי - עצמאי לגמרי מהשאלה 'האם יש נושא "
                "לחיפוש' (search_terms יכול להיות מלא גם כש-date_sort אינו "
                "'relevance'). 'oldest': השאלה מבקשת את המוקדם/הראשון "
                "ביותר - בין אם שאלת-מטא גורפת בלי נושא ('מה ההחלטה הישנה "
                "ביותר במאגר?', search_terms ריק), ובין אם מתייחסת לנושא "
                "ספציפי ('מתי הפעם הראשונה ש-X קרה?' - כאן יש לחלץ גם "
                "מילות-חיפוש רגילות לנושא X ב-search_terms, לא להשאיר "
                "ריק!). 'newest' באופן דומה עבור החדש/האחרון ביותר. אחרת "
                "(רוב השאלות) - 'relevance' (מיון לפי רלוונטיות-תוכן "
                "רגילה)."
            ),
        },
    },
    "required": ["search_terms", "parties", "judge", "date_from", "date_to",
                 "court_scope", "is_followup", "date_sort"],
    "additionalProperties": False,
}


def has_ai_credentials() -> bool:
    """בודק אם קיים מפתח API של Anthropic בסביבה."""
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def get_client():
    import anthropic
    return anthropic.Anthropic()


_CASE_NUMBER_RE = re.compile(r"\d+[-/]\d+[-/]?\d*")


def _fts_from_terms(terms: list[str]) -> str:
    """מפרק כל מונח למילים נפרדות ומחבר ב-OR (למשל 'לשון הרע' -> "לשון" OR
    "הרע") - מגדיל recall למונחים משפטיים חופשיים. אבל מספר תיק (למשל
    '963-04-26', גם כשמגיע מעורבב בתוך מונח ארוך יותר כמו 'בגץ 963/04')
    חייב להישאר ביטוי אחד רצוף, לא להתפרק לרסיסים - אחרת "963" OR "04" OR
    "26" מתאים למאות אלפי מסמכים לא-קשורים (כל שברירי התאריך/המספר
    הסידורי שכיחים בכל מספרי התיק בארכיון), וההתאמות הספציפיות טובעות
    בהצפה הזו לפני שמגיעות ל-top-K של הדירוג (נבדק בפועל: '"963" OR "04"
    OR "26"' החזיר 510,015 שורות, לעומת 12 עם הביטוי השלם). מאותה סיבה,
    שברי-מספר בני 1-3 ספרות שנשארים אחרי חילוץ מספר-התיק (או שמגיעים בלי
    הקשר מספר-תיק כלל) לא סלקטיביים מספיק כדי לתרום לחיפוש - רק מציפים."""
    phrases: list[str] = []
    tokens: list[str] = []
    for term in terms:
        term = (term or "").strip()
        remainder = term
        for m in _CASE_NUMBER_RE.finditer(term):
            phrases.append(m.group())
            remainder = remainder.replace(m.group(), " ")
        for tok in re.findall(r"[\w֐-׿]+", remainder, flags=re.UNICODE):
            if len(tok) < 2:
                continue
            if tok.isdigit() and len(tok) < 4:
                continue
            tokens.append(tok)
    seen: list[str] = []
    for t in phrases + tokens:
        if t not in seen:
            seen.append(t)
    return " OR ".join(f'"{t}"' for t in seen)


def analyze_query(client, question: str, today: str | None = None,
                  history: list[dict] | None = None) -> dict:
    """שלב 1: הפיכת שאלה חופשית למילות חיפוש + טווח תאריכים.

    history (אופציונלי): תורות קודמות בשיחה ({"role", "content"}), כדי
    שהמודל יוכל לפרש נכון שאלת-המשך קצרה שאין בה מספיק הקשר בפני עצמה
    (למשל 'תן לי דוגמה נוספת' אחרי ששאלה קודמת קבעה נושא) — בלעדי זה,
    שלב הניתוח רואה רק את המשפט האחרון, מפיק ממנו מילות-חיפוש גנריות
    שלא קשורות לנושא האמיתי, והאחזור נופל-בחזרה ל'המסמכים העדכניים
    ביותר בכל המאגר' — תוצאה לא-קשורה שנראית כאילו נדגמה אקראית."""
    today = today or date.today().isoformat()
    prompt = (
        f"התאריך היום הוא {today}.\n"
        "להלן שאלה של משתמש על פסקי דין של בתי המשפט בישראל, ובהמשך "
        "לשיחה קודמת (אם קיימת למעלה). חלץ ממנה מילות חיפוש בעברית "
        "לאיתור פסקי הדין הרלוונטיים, וכן טווח תאריכים אם השאלה מתייחסת "
        "לזמן (לדוגמה: 'בשנה האחרונה', 'בחודש שעבר') — המר אותו לתאריכי "
        "YYYY-MM-DD יחסית להיום. ציין גם court_scope אם השאלה מתייחסת "
        "ספציפית לבית המשפט העליון (כולל בג\"ץ) או ספציפית לבתי משפט "
        "אחרים (לא העליון).\n\n"
        "אם השאלה היא המשך קצר של השיחה הקודמת (למשל 'תן דוגמה נוספת', "
        "'הרחב', 'מדגם רחב יותר') וחסר בה הקשר עצמאי — הסק את הנושא "
        "ומילות החיפוש מהשיחה הקודמת, וסמן is_followup=true. אחרת, "
        "is_followup=false.\n\n"
        "שים לב ל-date_sort: אם השאלה מבקשת את המוקדם/הראשון או המאוחר/"
        "האחרון ביותר (בין אם שאלת מטא גורפת כמו 'ההחלטה העדכנית ביותר "
        "במאגר', ובין אם מתייחסת לנושא ספציפי כמו 'מתי הפעם הראשונה ש-X "
        "קרה' - במקרה כזה חלץ גם את מילות החיפוש הרגילות לנושא X, אל "
        "תשאיר search_terms ריק!) - סמן 'oldest'/'newest' בהתאם. אחרת "
        "(רוב השאלות) - 'relevance'.\n\n"
        "אם השאלה מזכירה מספר תיק מפורש (תבנית עם מספרים ומקפים/לוכסנים, "
        "למשל '963-04-26' או '5193/23') - הכנס אותו תמיד ל-search_terms "
        "בדיוק כפי שהוא מופיע בשאלה, גם אם אין עוד מילות-נושא לחלץ.\n\n"
        f"השאלה: {question}"
    )
    messages = list(history or []) + [{"role": "user", "content": prompt}]
    try:
        resp = client.messages.create(
            model=os.environ.get("ZOT_ANALYZE_MODEL") or config.AI_ANALYZE_MODEL,
            max_tokens=600,
            output_config={"format": {"type": "json_schema", "schema": _ANALYZE_SCHEMA}},
            messages=messages,
        )
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        data = json.loads(text)
    except Exception:
        # גיבוי: משתמשים בשאלה עצמה כמילות חיפוש
        data = {"search_terms": [question], "parties": [], "judge": "",
                "date_from": "", "date_to": "", "court_scope": "", "is_followup": False,
                "date_sort": "relevance"}
    data.setdefault("search_terms", [])
    data.setdefault("parties", [])
    data.setdefault("judge", "")
    data.setdefault("date_from", "")
    data.setdefault("date_to", "")
    data.setdefault("court_scope", "")
    data.setdefault("is_followup", False)
    data.setdefault("date_sort", "relevance")
    # רשת ביטחון דטרמיניסטית: מספר תיק מפורש בשאלה עצמה (לא בהיסטוריה -
    # שאלת-המשך שלא מזכירה תיק חדש לא אמורה "לרשת" תיק מתורות קודמות)
    # חייב תמיד להגיע ל-search_terms, בלי תלות בחילוץ ה-LLM - שהתברר לא
    # אמין מספיק למקרה הזה בבדיקה בפועל: באותה שאלה בדיוק, 3 מתוך 5
    # קריאות חזרו עם search_terms ריק לגמרי, למרות שהשאלה נקבה מפורשות
    # במספר תיק ("תן לי את כל ההחלטות של בג"ץ 963-04-26"). בלי הרשת הזו,
    # שאלת "כל ההחלטות בתיק X" עלולה להיכשל לגמרי ברוב הפעמים.
    for m in _CASE_NUMBER_RE.finditer(question):
        if m.group() not in data["search_terms"]:
            data["search_terms"].append(m.group())
    return data


def retrieve(analysis: dict):
    """שלב 2א: אחזור פסקי הדין הרלוונטיים לפי הניתוח, בצירוף ספירה מדויקת
    (לא רק top-K) של כלל התוצאות התואמות — כדי שהתשובה לשאלות 'כמה' תוכל
    להתבסס על מספר אמיתי מהמסד, ולא על גודל המדגם שהוצג למודל.

    date_sort ('relevance'/'oldest'/'newest') עצמאי לגמרי מקיום search_terms:
    שאלת-מטא גורפת ('ההחלטה הישנה ביותר במאגר') מגיעה עם search_terms ריק
    וממילא נופלת ל-fts_query="" (הגיבוי הכרונולוגי הטהור ב-retrieve_for_ai);
    שאלה עם נושא אמיתי שדורש גם מיון-כרונולוגי ('מתי הפעם הראשונה ש-X
    קרה?') מגיעה עם search_terms מלא + date_sort!='relevance', ומטופלת
    ב-retrieve_for_ai כסינון-תוכן-ממוין-לפי-תאריך (לא לפי BM25) - בלי זה,
    intent='oldest'/'latest' הישן היה מרוקן את ה-fts_query גם כשהיה נושא
    אמיתי, ומחזיר תיקים כרונולוגית-ישנים לגמרי לא-קשורים (נבדק בפועל עם
    'מתי הפעם הראשונה שבג"ץ פסל חקיקה' - ראו commit).

    מחזיר (verdicts, total_count)."""
    court_scope = analysis.get("court_scope", "")
    date_from = analysis.get("date_from", "")
    date_to = analysis.get("date_to", "")
    date_sort = analysis.get("date_sort", "relevance")

    all_terms = list(analysis.get("search_terms", [])) + list(analysis.get("parties", []))
    if analysis.get("judge"):
        all_terms.append(analysis["judge"])
    fts = _fts_from_terms(all_terms)
    verdicts = search.retrieve_for_ai(
        fts_query=fts, court_scope=court_scope, date_from=date_from, date_to=date_to,
        limit=config.AI_MAX_DOCS, sort=date_sort,
    )
    total_count = search.count_verdicts(
        court_scope=court_scope, fts_query=fts, date_from=date_from, date_to=date_to,
    )
    return verdicts, total_count


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


_SCOPE_LABEL = {
    "supreme": "עבור בית המשפט העליון בלבד (סינון ודאי לפי ארכיון המקור, לא ניחוש)",
    "general": "עבור בתי משפט שאינם בית המשפט העליון",
    "": "התואם את מילות החיפוש (ללא סינון לפי ערכאה)",
}


def answer_stream(client, question: str, verdicts, total_count: int = 0,
                  court_scope: str = "", history: list[dict] | None = None):
    """שלב 2ב: מחזיר גנרטור של קטעי טקסט (streaming) עם התשובה המנומקת.

    total_count/court_scope: מספר התוצאות הכולל במאגר עבור החיפוש הנוכחי
    (ספירה ישירה, לא top-K) והיקפו — מועברים למודל כעובדה נפרדת מהמסמכים
    המוצגים, כדי שיוכל לענות נכון על שאלות 'כמה' (ראו _SYSTEM_ANSWER).

    history מאפשר שיחת המשך: רשימת תורות קודמות ({"role": "user"/"assistant",
    "content": טקסט}) בלי הקשר פסקי-הדין המלא של תורות קודמות (רק השאלה
    והתשובה) — כדי לשמור את ההיסטוריה קומפקטית וזולה, תוך שהמודל עדיין
    "זוכר" את מהלך השיחה."""
    context = _build_context(verdicts)
    scope_label = _SCOPE_LABEL.get(court_scope, _SCOPE_LABEL[""])
    # בלי לנקוב במספר המסמכים המוצגים (למשל 'מדגם, עד 20 מסמכים') —
    # ראו _SYSTEM_ANSWER: המשתמש/ת לא אמור/ה לדעת/להסיק כמה מסמכים
    # שימשו למענה, לא רק את המספר הכולל האמיתי (total_count, שנשאר).
    user_content = (
        f"מספר התוצאות הכולל במאגר {scope_label} (ספירה מדויקת, לא רק "
        f"המסמכים המוצגים למטה): {total_count}\n\n"
        f"פסקי הדין הרלוונטיים ביותר:\n\n"
        f"{context}\n\n"
        f"===\n\nהשאלה: {question}\n\n"
        "ענה על השאלה על סמך פסקי הדין שלמעלה (ובהתחשב בהקשר השיחה הקודמת, "
        "אם רלוונטי), עם הפניות למספרי התיקים."
    )
    messages = list(history or []) + [{"role": "user", "content": user_content}]
    with client.messages.stream(
        model=config.AI_MODEL,
        max_tokens=4000,
        system=_SYSTEM_ANSWER,
        messages=messages,
    ) as stream:
        for chunk in stream.text_stream:
            yield chunk
