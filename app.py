"""גילוי נאות — אפליקציית חיפוש הליכים משפטיים.

חיפוש במאגר החלטות ופסקי דין של בתי המשפט בישראל (מאתר נט-המשפט):
  • חיפוש חכם (AI) — שיחה בשפה חופשית עם תשובה מנומקת והפניות לתיקים.
  • חיפוש רגיל — לפי שם צד, שופט, מספר תיק, בית משפט, תאריכים וטקסט חופשי.
  • משחקים לילדים — גילויים משעשעים מתוך המאגר.

הפעלה:  streamlit run app.py
"""
from __future__ import annotations

import html as _html
import os
import re
import sqlite3
from datetime import date

import streamlit as st


def safe_db_call(fn, *args, **kwargs):
    """מריץ שאילתת מסד-נתונים; במקרה של תקלה טכנית (למשל אי-התאמת סכימה
    זמנית בין קוד לנתונים) מציג הודעה ידידותית במקום stack trace גולמי."""
    try:
        return fn(*args, **kwargs)
    except sqlite3.Error:
        st.error("אירעה תקלה זמנית בטעינת הנתונים. נסו לרענן את הדף בעוד רגע.")
        st.stop()

st.set_page_config(page_title="גילוי נאות — חיפוש הליכים משפטיים",
                   page_icon="⚖️", layout="centered")


def _bridge_secrets():
    """מעביר סודות של Streamlit Cloud למשתני סביבה (שאותם קורא ה-SDK של Anthropic)."""
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ZOT_MODEL",
                "R2_PUBLIC_BASE_URL", "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID",
                "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        if os.environ.get(key):
            continue
        try:
            val = st.secrets[key]  # type: ignore[index]
        except Exception:
            val = None
        if val:
            os.environ[key] = str(val)


_bridge_secrets()

from zot import config, search  # noqa: E402
from zot import ai_search  # noqa: E402
from zot.ingest import build as build_index  # noqa: E402
from zot.summarize import _CATEGORIES as SUMMARY_CATEGORIES  # noqa: E402

# ============================ עיצוב ============================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rubik:wght@300;400;500;600;700&display=swap');
:root{
  --cream:#FAF6F0; --warm-white:#F5EFE6; --blush:#E8C9B8; --dusty-rose:#D4A5A0;
  --sage:#A8B89C; --dusty-blue:#8FAAB8; --caramel:#C4956A; --bark:#7A5C44;
  --charcoal:#3D3530; --soft-shadow:rgba(122,92,68,.12);
}
html,body,.stApp,*{font-family:'Rubik',sans-serif !important;}
.stApp{background-color:var(--cream); direction:rtl;}
.main-header{text-align:center; padding:2rem 1rem .5rem;}
.main-header h1{font-size:1.9rem; font-weight:600; color:var(--bark); margin:0;}
.main-header p{color:var(--caramel); font-size:.95rem; margin:.4rem 0 0;}
a.header-link{text-decoration:none;}
.stTextInput input, .stTextArea textarea, .stDateInput input{
  direction:rtl; text-align:right; background:var(--warm-white) !important;
  border:1.5px solid var(--blush) !important; border-radius:8px !important;
  color:var(--charcoal) !important;}
.stTextInput input:focus, .stTextArea textarea:focus{
  border-color:var(--dusty-blue) !important;
  box-shadow:0 0 0 3px rgba(143,170,184,.2) !important;}
.stButton>button{background:var(--caramel) !important; color:#fff !important;
  border:none !important; border-radius:8px !important; font-weight:500 !important;
  padding:.5rem 1.4rem !important; transition:all .2s ease !important;}
.stButton>button:hover{background:var(--bark) !important; transform:translateY(-1px);}
.result-card{background:var(--warm-white); border-radius:12px;
  border:1.5px solid var(--blush); padding:1.1rem 1.4rem; margin-bottom:.8rem;
  box-shadow:0 2px 8px var(--soft-shadow); direction:rtl;}
.result-number{font-size:.72rem; font-weight:600; color:var(--caramel);
  letter-spacing:.05em; margin-bottom:.25rem; display:flex; justify-content:space-between;}
.result-name{font-size:1.05rem; font-weight:600; color:var(--charcoal); margin-bottom:.4rem;
  overflow-wrap:break-word;}
.result-meta{font-size:.82rem; color:#7A6A62; display:flex; gap:1rem;
  flex-wrap:wrap; direction:rtl;}
.result-name mark, .result-meta mark{background:var(--sage); color:#fff; border-radius:3px; padding:0 .15em;}
.page-info{text-align:center; color:var(--caramel); font-size:.85rem; margin:.5rem 0;}
.ai-answer{background:var(--warm-white); border-radius:12px;
  border:1.5px solid var(--sage); padding:1.2rem 1.5rem; direction:rtl;
  line-height:1.9; color:var(--charcoal);}
.stMarkdown,p,div,label{direction:rtl; text-align:right;}
#MainMenu,footer,header{visibility:hidden;}
.stTabs [data-baseweb="tab-list"]{direction:rtl; gap:.5rem;}
hr{border-color:var(--blush) !important; opacity:.5;}
.hint{background:var(--warm-white); border:1.5px dashed var(--dusty-rose);
  border-radius:10px; padding:1rem 1.2rem; color:var(--bark); font-size:.9rem;}
[data-testid="stChatMessage"]{direction:rtl;}
.about-box{background:var(--warm-white); border-radius:12px; border:1.5px solid var(--blush);
  padding:1.2rem 1.5rem; direction:rtl; line-height:1.8; color:var(--charcoal); margin-bottom:1rem;}
.about-box h4{color:var(--bark); margin-top:0;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<a class="header-link" href="/">
<div class="main-header">
  <h1>⚖️ גילוי נאות</h1>
  <p>חיפוש במאגר החלטות ופסקי דין של בתי המשפט בישראל</p>
</div>
</a>
""", unsafe_allow_html=True)


# ============================ אינדקס ============================
@st.cache_resource(show_spinner=False, ttl=3600)
def _sync_index_from_r2():
    """מוריד/מעדכן את index.db מ-R2 (הקובץ גדול מדי בשביל git). מטמון
    לשעה כדי לא לבדוק מול R2 בכל אינטראקציה של כל משתמש."""
    from zot.storage import sync_index
    return sync_index()


@st.cache_resource(show_spinner=False)
def _auto_build_index():
    """בונה את האינדקס פעם אחת לכל הרצת שרת (למשל בעלייה ראשונה בענן)."""
    return build_index(verbose=False)


def ensure_index_ui() -> bool:
    """מוודא שקיים אינדקס עדכני; מנסה קודם להוריד/לעדכן מ-R2, ורק אם זה
    לא זמין נופל לבניה מקומית מהמסמכים הגולמיים. מחזיר True אם מוכן."""
    _sync_index_from_r2()
    if search.db_exists():
        return True
    if not config.METADATA_PATH.exists():
        st.markdown('<div class="hint">לא נמצא קובץ <code>data/metadata.csv</code>. '
                    'ודאו שקובץ המטא-דאטה וקבצי פסקי הדין (<code>documents/</code>) '
                    'קיימים בפרויקט.</div>', unsafe_allow_html=True)
        return False
    try:
        with st.spinner("בונה את אינדקס החיפוש בפעם הראשונה — כמה שניות..."):
            _auto_build_index()
        return True
    except Exception as e:  # noqa: BLE001
        st.error(f"שגיאה בבניית האינדקס: {e}")
        return False


# ============================ תצוגת פסקי דין ============================
_MAX_DISPLAY_CHARS = 60_000


def _esc(text) -> str:
    return _html.escape(str(text or ""))


def _highlight(text: str, terms: list[str]) -> str:
    """עוטף התאמות של מילות החיפוש ב-<mark>, אחרי escaping בטוח."""
    escaped = _esc(text)
    clean_terms = [t.strip() for t in terms if t and len(t.strip()) >= 2]
    if not clean_terms:
        return escaped
    pattern = "|".join(re.escape(_esc(t)) for t in clean_terms)
    try:
        return re.sub(f"({pattern})", r"<mark>\1</mark>", escaped, flags=re.IGNORECASE)
    except re.error:
        return escaped


def fmt_meta(row, terms: list[str] | None = None) -> str:
    terms = terms or []
    bits = []
    if row["court"]:
        bits.append(f"🏛️ {_highlight(row['court'], terms)}")
    if row["judge"]:
        bits.append(f"⚖️ {_highlight(row['judge'], terms)}")
    d = row["decision_date"] or row["filed_date"]
    if d:
        bits.append(f"📅 {_esc(d)}")
    if row["decision_type"]:
        bits.append(f"📄 {_esc(row['decision_type'])}")
    return "".join(f"<span>{b}</span>" for b in bits)


def render_card(row, highlight_terms: list[str] | None = None):
    terms = highlight_terms or []
    parties_html = _highlight(row["parties"], terms) if row["parties"] else "—"
    st.markdown(
        f'<div class="result-card">'
        f'<div class="result-number">'
        f'<span>תיק מס\' {_esc(row["case_number"])}</span>'
        f'<a href="?verdict={row["id"]}" style="color:var(--caramel);">🔗</a>'
        f'</div>'
        f'<div class="result-name">{parties_html}</div>'
        f'<div class="result-meta">{fmt_meta(row, terms)}</div>'
        f'</div>', unsafe_allow_html=True)
    if row["has_document"]:
        full = safe_db_call(search.get_verdict, row["id"])
        approx_pages = max(1, len(full["full_text"] or "") // 2000)
        with st.expander(f"📖 הצג את פסק הדין המלא (כ-{approx_pages} עמודים)"):
            if full["structural_summary"]:
                import json
                try:
                    summary = json.loads(full["structural_summary"])
                except Exception:
                    summary = {}
                if summary:
                    st.markdown("**🗂️ תמצית מובנית**")
                    for key, label in SUMMARY_CATEGORIES.items():
                        if summary.get(key):
                            st.markdown(f"**{label}:** {summary[key]}")
                    st.markdown("---")
            full_text = full["full_text"] or ""
            display_text = full_text
            if len(full_text) > _MAX_DISPLAY_CHARS:
                display_text = (full_text[:_MAX_DISPLAY_CHARS] +
                                "\n\n[... הטקסט קוצר לתצוגה; הורידו את הקובץ המלא למטה ...]")
            st.text_area("טקסט פסק הדין", value=display_text, height=300,
                         key=f"txt_{row['id']}", label_visibility="collapsed")
            st.download_button(
                "⬇️ הורדה כקובץ טקסט",
                data=full_text.encode("utf-8"),
                file_name=f"{row['case_number'] or row['id']}.txt",
                mime="text/plain", key=f"dl_{row['id']}")
            if config.R2_PUBLIC_BASE_URL:
                from urllib.parse import quote
                c1, c2 = st.columns(2)
                if row["file_relpath_pdf"]:
                    url = config.R2_PUBLIC_BASE_URL + "/" + quote(row["file_relpath_pdf"])
                    c1.link_button("📄 הורדת PDF", url)
                if row["file_relpath_docx"]:
                    url = config.R2_PUBLIC_BASE_URL + "/" + quote(row["file_relpath_docx"])
                    c2.link_button("📝 הורדת Word", url)
    else:
        st.caption("ℹ️ קובץ פסק הדין המלא אינו זמין במאגר המקומי (קיימים רק פרטי המטא-דאטה).")


def _direct_verdict_link_ui():
    """אם יש בכתובת פרמטר ?verdict=ID — מציגים את פסק הדין הזה למעלה,
    לפני שאר העמוד (תמיכה בקישור ישיר לפסק דין ספציפי)."""
    vid = st.query_params.get("verdict")
    if not vid:
        return
    try:
        row = safe_db_call(search.get_verdict, int(vid))
    except (ValueError, TypeError):
        row = None
    if row is None:
        st.warning("פסק הדין המבוקש לא נמצא.")
        return
    st.markdown("#### 🔗 פסק דין לפי קישור ישיר")
    render_card(row)
    st.markdown("---")


# ============================ טאב חיפוש רגיל ============================
_MATCH_MODE_LABELS = {"any": "כל מילה בנפרד", "exact": "ביטוי מדויק", "near": "צמוד (מילים קרובות)"}
_SORT_LABELS = {"newest": "חדש ← ישן", "oldest": "ישן ← חדש", "longest": "לפי אורך טקסט"}


def tab_simple():
    if not ensure_index_ui():
        return
    s = safe_db_call(search.stats)
    st.caption(f"במאגר: {s['total']:,} החלטות ({s['with_documents']:,} עם טקסט מלא)")

    courts = [""] + safe_db_call(search.distinct_courts)
    proceedings = [""] + safe_db_call(search.distinct_proceedings)

    with st.form("simple_search"):
        c1, c2 = st.columns(2)
        name = c1.text_input("שם צד לתיק", placeholder="למשל: מקייס")
        case_number = c2.text_input("מספר תיק", placeholder="למשל: 4934-07-24")
        c3, c4 = st.columns(2)
        judge = c3.text_input("שם שופט/ת", placeholder="למשל: רוני סלע")
        court = c4.selectbox("בית משפט", courts,
                             format_func=lambda x: x or "— הכול —")
        c5, c6 = st.columns(2)
        proceeding = c5.selectbox("סוג הליך", proceedings,
                                  format_func=lambda x: x or "— הכול —")
        free_text = c6.text_input("חיפוש חופשי בטקסט", placeholder="מילים בגוף פסק הדין")
        match_mode = st.radio("סוג ההתאמה לחיפוש החופשי", list(_MATCH_MODE_LABELS),
                              format_func=lambda x: _MATCH_MODE_LABELS[x],
                              horizontal=True, index=0)
        c7, c8 = st.columns(2)
        date_from = c7.date_input("מתאריך", value=None, format="DD/MM/YYYY")
        date_to = c8.date_input("עד תאריך", value=None, format="DD/MM/YYYY")
        submitted = st.form_submit_button("🔍 חיפוש")

    if submitted:
        st.session_state["simple_page"] = 0
        st.session_state["simple_query"] = dict(
            name=name, case_number=case_number, judge=judge, court=court,
            proceeding=proceeding, free_text=free_text, match_mode=match_mode,
            date_from=date_from.isoformat() if date_from else "",
            date_to=date_to.isoformat() if date_to else "")

    query = st.session_state.get("simple_query")
    if not query:
        return
    if not any(v for k, v in query.items() if k != "match_mode"):
        st.info("מלאו לפחות שדה חיפוש אחד.")
        return

    sort = st.selectbox("מיון", list(_SORT_LABELS), format_func=lambda x: _SORT_LABELS[x],
                        key="simple_sort")

    page = st.session_state.get("simple_page", 0)
    per = config.RESULTS_PER_PAGE
    rows, total = safe_db_call(search.simple_search, **query, sort=sort,
                               limit=per, offset=page * per)

    if total == 0:
        st.warning("לא נמצאו תיקים תואמים.")
        return

    pages = (total - 1) // per + 1
    st.markdown(f'<div class="page-info">נמצאו <b>{total}</b> תיקים — '
                f'עמוד {page + 1} מתוך {pages}</div>', unsafe_allow_html=True)
    highlight_terms = [query["name"], query["judge"], query["court"], query["free_text"]]
    for row in rows:
        render_card(row, highlight_terms)

    if pages > 1:
        p1, p2, p3 = st.columns([1, 2, 1])
        if page > 0 and p1.button("→ הקודם", key="s_prev"):
            st.session_state["simple_page"] = page - 1
            st.rerun()
        p2.markdown(f'<div class="page-info">{page + 1} / {pages}</div>',
                    unsafe_allow_html=True)
        if page < pages - 1 and p3.button("הבא ←", key="s_next"):
            st.session_state["simple_page"] = page + 1
            st.rerun()


# ============================ טאב חיפוש חכם (צ'אט) ============================
EXAMPLES = [
    "אילו פסקי דין מהשנה האחרונה עסקו בסכסוכי עבודה?",
    "האם יש החלטות שבהן התביעה נדחתה לאחר שהצדדים הגיעו להסכמות?",
    "מה נפסק בתיקים בנושא נפגעי עבודה מול המוסד לביטוח לאומי?",
]


def tab_ai():
    if not ensure_index_ui():
        return

    if not ai_search.has_ai_credentials():
        st.markdown(
            '<div class="hint">🔑 <b>החיפוש החכם דורש מפתח API של Anthropic.</b><br>'
            'הגדירו את משתנה הסביבה <code>ANTHROPIC_API_KEY</code> לפני הפעלת '
            'האפליקציה (בשורת הפקודה: <code>set ANTHROPIC_API_KEY=...</code> ב-Windows). '
            'החיפוש הרגיל פועל גם ללא מפתח.</div>', unsafe_allow_html=True)
        return

    if "ai_chat" not in st.session_state:
        st.session_state["ai_chat"] = []  # [{"role", "text", "verdicts"?}]

    if not st.session_state["ai_chat"]:
        st.caption("שאלו שאלה בשפה חופשית על פסקי הדין במאגר. אפשר גם לשאול שאלות המשך.")
        st.caption("דוגמאות: " + "  •  ".join(EXAMPLES))

    for turn in st.session_state["ai_chat"]:
        with st.chat_message("user" if turn["role"] == "user" else "assistant",
                             avatar="🙋" if turn["role"] == "user" else "⚖️"):
            st.markdown(turn["text"])
            if turn.get("verdicts"):
                with st.expander(f"פסקי הדין ששימשו למענה ({len(turn['verdicts'])})"):
                    for v in turn["verdicts"]:
                        render_card(v)

    question = st.chat_input("שאלו שאלה על פסקי הדין... (Enter לשליחה, Shift+Enter לשורה חדשה)")
    if not question:
        return

    st.session_state["ai_chat"].append({"role": "user", "text": question})
    with st.chat_message("user", avatar="🙋"):
        st.markdown(question)

    try:
        client = ai_search.get_client()
    except Exception as e:  # noqa: BLE001
        st.error(f"שגיאה באתחול מנוע ה-AI: {e}")
        return

    with st.chat_message("assistant", avatar="⚖️"):
        with st.spinner("מנתח את השאלה ומאתר פסקי דין רלוונטיים..."):
            analysis = ai_search.analyze_query(client, question, today=date.today().isoformat())
            verdicts = safe_db_call(ai_search.retrieve, analysis)

        if not verdicts:
            msg = "לא נמצאו פסקי דין רלוונטיים לשאלה זו במאגר."
            st.warning(msg)
            st.session_state["ai_chat"].append({"role": "assistant", "text": msg, "verdicts": []})
            return

        # היסטוריית שיחה קומפקטית (שאלה+תשובה בלבד, בלי הקשר פסקי-הדין
        # המלא של תורות קודמות) — כדי לאפשר שיחת המשך בעלות סבירה.
        history = [
            {"role": "user" if t["role"] == "user" else "assistant", "content": t["text"]}
            for t in st.session_state["ai_chat"][:-1]
        ]

        answer_box = st.empty()
        collected = []
        try:
            for chunk in ai_search.answer_stream(client, question, verdicts, history=history):
                collected.append(chunk)
                answer_box.markdown("".join(collected) + "▌")
            answer_box.markdown("".join(collected))
        except Exception as e:  # noqa: BLE001
            st.error(f"שגיאה בקבלת תשובה מהמודל: {e}")
            st.session_state["ai_chat"].pop()
            return

        answer_text = "".join(collected)
        with st.expander(f"פסקי הדין ששימשו למענה ({len(verdicts)})"):
            for v in verdicts:
                render_card(v)

    st.session_state["ai_chat"].append(
        {"role": "assistant", "text": answer_text, "verdicts": verdicts})


# ============================ טאב משחקים לילדים ============================
_GAME_OPTIONS = [
    ("🎲 פסק דין רנדומלי", "random"),
    ("🕰️ פסק דין היסטורי", "historic"),
    ("🏛️ פסק דין מרכזי", "landmark"),
    ("🆕 הפסק הכי עדכני במאגר", "latest"),
    ("🤖 פסק דין שמדבר על AI", "ai_related"),
]


def tab_games():
    if not ensure_index_ui():
        return
    st.caption("כמה דרכים משעשעות לגלות פסקי דין מהמאגר — כל לחיצה מפתיעה.")
    cols = st.columns(2)
    for i, (label, key) in enumerate(_GAME_OPTIONS):
        if cols[i % 2].button(label, key=f"game_{key}", use_container_width=True):
            st.session_state["game_pick"] = key

    pick = st.session_state.get("game_pick")
    if not pick:
        return

    row = None
    if pick == "random":
        row = safe_db_call(search.random_verdict)
    elif pick == "historic":
        row = safe_db_call(search.oldest_verdict)
    elif pick == "landmark":
        row = safe_db_call(search.landmark_verdict)
        st.caption("⚠️ בחירה אקראית מתוך פסקי דין של בית המשפט העליון — לא ניתוח אמיתי של חשיבות תקדימית.")
    elif pick == "latest":
        row = safe_db_call(search.latest_verdict)
    elif pick == "ai_related":
        row = safe_db_call(search.keyword_verdict,
                           ["בינה מלאכותית", "AI", "צ׳אט", "אלגוריתם", "ChatGPT"])

    if row is None:
        st.warning("לא נמצא פסק דין מתאים הפעם — נסו שוב.")
        return
    render_card(row)


# ============================ טאב אודות ============================
def tab_about():
    st.markdown("""
<div class="about-box">
<h4>מודל ה-AI</h4>
<p>החיפוש החכם באתר משתמש במודלים של Anthropic (משפחת Claude) לניתוח שאלות
ולניסוח תשובות מבוססות על פסקי הדין שנמצאו במאגר.</p>

<h4>מקור המסמכים</h4>
<p>המסמכים במאגר מגיעים משני אתרים ציבוריים של הרשות השופטת בישראל: מאגר
ההחלטות הכללי (decisions.court.gov.il) ומאגר פסקי הדין וההחלטות של בית
המשפט העליון (supremedecisions.court.gov.il).</p>

<h4>הבהרה וכתב ויתור</h4>
<p>האתר מוצע כשירות התנדבותי, "as is", ללא כל אחריות מכל סוג. אין להסתמך
על המידע באתר כייעוץ משפטי, ואין בו כדי להחליף בדיקה עצמאית מול המקורות
הרשמיים. השימוש באתר ובתוצאותיו הוא באחריות המשתמש/ת בלבד.</p>

<h4>המאגר אינו מלא</h4>
<p>איסוף המסמכים נעשה באופן אוטומטי ואינו הרמטי — ייתכן שיש החלטות ופסקי
דין שאינם מופיעים במאגר, בין אם בגלל מגבלות טכניות באתרי המקור ובין אם
מסיבות אחרות. אין להניח שהיעדר תוצאה לחיפוש מסוים משמעו שאין פסיקה
בנושא.</p>

<h4>פרטיות</h4>
<p>האתר אינו דורש הרשמה, אינו אוסף פרטים אישיים, ואינו שומר עוגיות (cookies)
כלשהן. משמעות הדבר, בין השאר, שהאתר אינו זוכר את היסטוריית החיפושים שלכם
בין ביקור לביקור.</p>

<h4>למה האתר פורסם</h4>
<p>האתר נבנה ופורסם כפרויקט אישי, מתוך אמונה בחשיבות הנגישות הציבורית
למידע משפטי. אם אתם זקוקים לכלי מדויק, מקיף ואמין יותר — קיימים שירותים
מסחריים בתשלום שמציעים רמת שירות גבוהה יותר.</p>
</div>
""", unsafe_allow_html=True)


# ============================ פריסה ============================
_direct_verdict_link_ui()
tab1, tab2, tab3, tab4 = st.tabs(
    ["✨ חיפוש חכם (AI)", "🔍 חיפוש רגיל", "🎲 משחקים לילדים", "ℹ️ אודות"])
with tab1:
    tab_ai()
with tab2:
    tab_simple()
with tab3:
    tab_games()
with tab4:
    tab_about()
