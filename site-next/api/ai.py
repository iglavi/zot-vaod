"""נקודת קצה לחיפוש החכם (AI), עם הזרמת שלבי-חשיבה + תשובה בזמן אמת
(Server-Sent Events) - עוטפת את zot.ai_search הקיים בלי לשנות אותו.

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
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, Response, request  # noqa: E402

from zot import ai_search  # noqa: E402
from _util import add_download_urls  # noqa: E402

app = Flask(__name__)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.route("/api/ai", methods=["POST"])
def ai_endpoint():
    body = request.get_json(force=True, silent=True) or {}
    question = (body.get("question") or "").strip()
    history = body.get("history") or []

    def stream():
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
        try:
            for chunk in ai_search.answer_stream(
                client, question, verdicts, total_count=total_count,
                court_scope=analysis.get("court_scope", ""),
                court_type=analysis.get("court_type", ""),
                history=history,
            ):
                answer_text += chunk
                yield _sse("delta", {"text": chunk})
        except Exception as e:  # noqa: BLE001
            yield _sse("error", {"message": f"שגיאה בקבלת תשובה מהמודל: {e}"})
            return

        # שאלות המשך מוצעות - קריאה נוספת קצנה ונפרדת, אחרי שהתשובה עצמה
        # כבר הושלמה; כשל כאן לא אמור לפגוע בתשובה שכבר התקבלה בהצלחה.
        questions = ai_search.suggest_followups(client, question, answer_text)
        if questions:
            yield _sse("suggestions", {"questions": questions})
        yield _sse("done", {})

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
