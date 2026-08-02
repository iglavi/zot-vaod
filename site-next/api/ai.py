"""נקודת קצה לחיפוש החכם (AI), עם הזרמת שלבי-חשיבה + תשובה בזמן אמת
(Server-Sent Events) - עוטפת את zot.ai_search הקיים בלי לשנות אותו.

גוף הבקשה (POST JSON): {"question": str, "history": [...], "citizen_mode":
bool} - citizen_mode (F-13) מבקש ניסוח פשוט ופרקטי במקום ניסוח משפטי
(ראו zot/ai_search.py: _SYSTEM_ANSWER_CITIZEN).

אירועים שנשלחים ללקוח (כל אחד שורת 'data: {...json...}\n\n'):
  step       -> {"step": "received"|"analyzing"|"retrieving"|"answering"}
  sources    -> {"verdicts": [...]}   (נשלח לפני תחילת התשובה, כמו בעיצוב)
  delta      -> {"text": "..."}       (חלק מהתשובה, מוזרם token-by-token)
  suggestions-> {"questions": [...]}  (עד 3 שאלות המשך מוצעות, אחרי סיום התשובה)
  done       -> {}
  error      -> {"message": "..."}
"""
import json
import os
import sys
import time
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, Response, request  # noqa: E402

from zot import ai_search  # noqa: E402
from _util import add_download_urls  # noqa: E402

app = Flask(__name__)

# תקרת זמן-ריצה של הפונקציה (vercel.json: functions."api/*.py".maxDuration).
# תשובות ארוכות לבד כבר לוקחות עד 40-48 שניות סטרימינג בפועל - קריאת
# suggest_followups המתווספת רק *אחרי* שהתשובה הסתיימה עלולה, במקרים כאלה,
# לדחוף את הריצה הכוללת מעבר לתקרה ולגרום ל-Vercel להרוג את הפונקציה
# באמצע (בלי אירוע error, בלי done) - נצפה בפועל בבדיקות. פס-ביטחון: אם לא
# נשאר מספיק זמן, פשוט מדלגים על שאלות ההמשך (done עדיין נשלח כרגיל) במקום
# להמר על התקרה.
_MAX_DURATION_S = 60
_SUGGESTIONS_MIN_HEADROOM_S = 10

# בדיקה נוספת, חמורה יותר: גם *בלי* שאלות ההמשך, תשובה ארוכה מספיק
# (נצפה בפועל: מעל 60 שניות סטרימינג לבדו) עלולה לחרוג מהתקרה בעצמה ולהיהרג
# באמצע - בלי אירוע done, בלי הודעת שגיאה, סתם חיבור שנקטע (בדיוק התקלה
# המקורית "נתקע באמצע משפט" שתוקנה בתחילת העבודה על האתר, שמתבררת כחוזרת
# עבור השאלות הרחבות/מורכבות ביותר). פס-ביטחון פרו-אקטיבי: עוצרים ביוזמתנו
# לפני התקרה, עם הודעת-חיתוך ברורה ואירוע done תקין, במקום לתת ל-Vercel
# להרוג את הפונקציה בלי שהלקוח יקבל סיום מסודר.
#
# חשוב: start נמדד מתחילת הבקשה כולה (received), לא רק משלב answering -
# ניתוח+אחזור לבד כבר לוקחים כ-14 שניות בפועל (נצפה: sources לא מגיע
# לפני ~14s). מרווח-ביטחון גדול מדי (היה 8s) קוצץ מזמן הכתיבה בפועל של
# התשובה יותר מהנדרש וגורם לחיתוך תכוף מדי גם לתשובות סבירות-אורך; 5s
# משאיר עדיין מספיק זמן לשלוח את הודעת-החיתוך ו-done לפני התקרה בפועל.
_ANSWER_DEADLINE_S = _MAX_DURATION_S - 5
_TRUNCATION_NOTE = "\n\n_(התשובה נקטעה בשל אורך - נסו לשאול שאלה ממוקדת יותר לתשובה מלאה.)_"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.route("/api/ai", methods=["POST"])
def ai_endpoint():
    body = request.get_json(force=True, silent=True) or {}
    question = (body.get("question") or "").strip()
    history = body.get("history") or []
    citizen_mode = bool(body.get("citizen_mode"))

    def stream():
        start = time.monotonic()
        if not question:
            yield _sse("error", {"message": "לא התקבלה שאלה."})
            return
        if not ai_search.has_ai_credentials():
            yield _sse("error", {"message": "החיפוש החכם אינו מוגדר כרגע (חסר מפתח API)."})
            return
        yield _sse("step", {"step": "received"})
        try:
            client = ai_search.get_client()
        except Exception as e:  # noqa: BLE001
            yield _sse("error", {"message": f"שגיאה באתחול מנוע ה-AI: {e}"})
            return

        yield _sse("step", {"step": "analyzing"})
        try:
            analysis = ai_search.analyze_query(
                client, question, today=date.today().isoformat(), history=history
            )
        except Exception as e:  # noqa: BLE001
            yield _sse("error", {"message": f"שגיאה בניתוח השאלה: {e}"})
            return

        yield _sse("step", {"step": "retrieving"})
        try:
            verdicts, total_count = ai_search.retrieve(analysis)
        except Exception as e:  # noqa: BLE001
            yield _sse("error", {"message": f"שגיאה באחזור פסקי דין: {e}"})
            return

        if not verdicts:
            yield _sse("sources", {"verdicts": []})
            yield _sse("delta", {"text": "לא נמצאו פסקי דין רלוונטיים לשאלה זו במאגר."})
            yield _sse("done", {})
            return

        yield _sse("sources", {"verdicts": add_download_urls(verdicts)})
        yield _sse("step", {"step": "answering"})
        answer_text = ""
        truncated = False
        try:
            for chunk in ai_search.answer_stream(
                client, question, verdicts, total_count=total_count,
                court_scope=analysis.get("court_scope", ""),
                court_type=analysis.get("court_type", ""),
                history=history,
                citizen_mode=citizen_mode,
            ):
                answer_text += chunk
                yield _sse("delta", {"text": chunk})
                if time.monotonic() - start > _ANSWER_DEADLINE_S:
                    truncated = True
                    break
        except Exception as e:  # noqa: BLE001
            yield _sse("error", {"message": f"שגיאה בקבלת תשובה מהמודל: {e}"})
            return

        if truncated:
            answer_text += _TRUNCATION_NOTE
            yield _sse("delta", {"text": _TRUNCATION_NOTE})
            yield _sse("done", {})
            return

        # שאלות המשך מוצעות - קריאה נוספת קצנה ונפרדת, אחרי שהתשובה עצמה
        # כבר הושלמה; כשל כאן לא אמור לפגוע בתשובה שכבר התקבלה בהצלחה.
        # מדלגים אם לא נשאר מספיק זמן לפני תקרת הריצה של הפונקציה (ראו
        # _MAX_DURATION_S למעלה) - עדיף לוותר על השאלות המוצעות מאשר לסכן
        # הריגת הפונקציה באמצע לפני שנספיק לשלוח done.
        elapsed = time.monotonic() - start
        if elapsed < _MAX_DURATION_S - _SUGGESTIONS_MIN_HEADROOM_S:
            questions = ai_search.suggest_followups(client, question, answer_text)
            if questions:
                yield _sse("suggestions", {"questions": questions})
        yield _sse("done", {})

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
