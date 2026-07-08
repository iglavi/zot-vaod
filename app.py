"""גילוי נאות — אפליקציית חיפוש הליכים משפטיים.

חיפוש במאגר החלטות ופסקי דין של בתי המשפט בישראל (מאתר נט-המשפט):
  • חיפוש רגיל — לפי שם צד, שופט, מספר תיק, בית משפט, תאריכים וטקסט חופשי.
  • חיפוש חכם (AI) — שאלות בשפה חופשית עם תשובה מנומקת והפניות לתיקים.

הפעלה:  streamlit run app.py
"""
from __future__ import annotations

import os
from datetime import date

import streamlit as st

st.set_page_config(page_title="גילוי נאות — חיפוש הליכים משפטיים",
                   page_icon="⚖️", layout="centered")


def _bridge_secrets():
    """מעביר סודות של Streamlit Cloud למשתני סביבה (שאותם קורא ה-SDK של Anthropic)."""
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ZOT_MODEL",
                "R2_PUBLIC_BASE_URL"):
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
  letter-spacing:.05em; margin-bottom:.25rem;}
.result-name{font-size:1.05rem; font-weight:600; color:var(--charcoal); margin-bottom:.4rem;}
.result-meta{font-size:.82rem; color:#7A6A62; display:flex; gap:1rem;
  flex-wrap:wrap; direction:rtl;}
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
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="main-header">
  <h1>⚖️ גילוי נאות</h1>
  <p>חיפוש במאגר החלטות ופסקי דין של בתי המשפט בישראל</p>
</div>
""", unsafe_allow_html=True)


# ============================ אינדקס ============================
@st.cache_resource(show_spinner=False)
def _auto_build_index():
    """בונה את האינדקס פעם אחת לכל הרצת שרת (למשל בעלייה ראשונה בענן)."""
    return build_index(verbose=False)


def ensure_index_ui() -> bool:
    """מוודא שקיים אינדקס; אם חסר — בונה אותו אוטומטית. מחזיר True אם מוכן."""
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


def sidebar():
    with st.sidebar:
        st.markdown("### ⚖️ גילוי נאות")
        if search.db_exists():
            s = search.stats()
            st.caption(f"{s['total']:,} החלטות · {s['with_documents']:,} עם טקסט מלא")
        st.caption("מנוע חכם: " + ("✅ פעיל" if ai_search.has_ai_credentials()
                                    else "🔒 דורש מפתח API"))


def fmt_meta(row) -> str:
    bits = []
    if row["court"]:
        bits.append(f"🏛️ {row['court']}")
    if row["judge"]:
        bits.append(f"⚖️ {row['judge']}")
    d = row["decision_date"] or row["filed_date"]
    if d:
        bits.append(f"📅 {d}")
    if row["decision_type"]:
        bits.append(f"📄 {row['decision_type']}")
    return "".join(f"<span>{b}</span>" for b in bits)


def render_card(row):
    st.markdown(
        f"""<div class="result-card">
          <div class="result-number">תיק מס׳ {row['case_number']}</div>
          <div class="result-name">{row['parties'] or '—'}</div>
          <div class="result-meta">{fmt_meta(row)}</div>
        </div>""", unsafe_allow_html=True)
    if row["has_document"]:
        with st.expander("📖 הצג את פסק הדין המלא"):
            full = search.get_verdict(row["id"])
            st.text_area("טקסט פסק הדין", value=full["full_text"], height=300,
                         key=f"txt_{row['id']}", label_visibility="collapsed")
            st.download_button(
                "⬇️ הורדה כקובץ טקסט",
                data=(full["full_text"] or "").encode("utf-8"),
                file_name=f"{row['case_number'] or row['id']}.txt",
                mime="text/plain", key=f"dl_{row['id']}")
            if config.R2_PUBLIC_BASE_URL and row["file_relpath"]:
                from urllib.parse import quote
                url = config.R2_PUBLIC_BASE_URL + "/" + quote(row["file_relpath"])
                st.link_button("📄 הורדת הקובץ המקורי (PDF/Word)", url)
    else:
        st.caption("ℹ️ קובץ פסק הדין המלא אינו זמין במאגר המקומי (קיימים רק פרטי המטא-דאטה).")


# ============================ טאב חיפוש רגיל ============================
def tab_simple():
    if not ensure_index_ui():
        return
    s = search.stats()
    st.caption(f"במאגר: {s['total']:,} החלטות ({s['with_documents']:,} עם טקסט מלא)")

    courts = [""] + search.distinct_courts()
    proceedings = [""] + search.distinct_proceedings()

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
        c7, c8 = st.columns(2)
        date_from = c7.date_input("מתאריך", value=None, format="DD/MM/YYYY")
        date_to = c8.date_input("עד תאריך", value=None, format="DD/MM/YYYY")
        submitted = st.form_submit_button("🔍 חיפוש")

    if submitted:
        st.session_state["simple_page"] = 0
        st.session_state["simple_query"] = dict(
            name=name, case_number=case_number, judge=judge, court=court,
            proceeding=proceeding, free_text=free_text,
            date_from=date_from.isoformat() if date_from else "",
            date_to=date_to.isoformat() if date_to else "")

    query = st.session_state.get("simple_query")
    if not query:
        return
    if not any(query.values()):
        st.info("מלאו לפחות שדה חיפוש אחד.")
        return

    page = st.session_state.get("simple_page", 0)
    per = config.RESULTS_PER_PAGE
    rows, total = search.simple_search(**query, limit=per, offset=page * per)

    if total == 0:
        st.warning("לא נמצאו תיקים תואמים.")
        return

    pages = (total - 1) // per + 1
    st.markdown(f'<div class="page-info">נמצאו <b>{total}</b> תיקים — '
                f'עמוד {page + 1} מתוך {pages}</div>', unsafe_allow_html=True)
    for row in rows:
        render_card(row)

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


# ============================ טאב חיפוש חכם ============================
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

    st.markdown("שאלו שאלה בשפה חופשית על פסקי הדין במאגר:")
    question = st.text_area("שאלה", height=90, label_visibility="collapsed",
                            placeholder="למשל: " + EXAMPLES[0])
    st.caption("דוגמאות: " + "  •  ".join(EXAMPLES))
    go = st.button("✨ שאל/י")

    if not (go and question.strip()):
        return

    try:
        client = ai_search.get_client()
    except Exception as e:  # noqa: BLE001
        st.error(f"שגיאה באתחול מנוע ה-AI: {e}")
        return

    with st.spinner("מנתח את השאלה ומאתר פסקי דין רלוונטיים..."):
        analysis = ai_search.analyze_query(client, question, today=date.today().isoformat())
        verdicts = ai_search.retrieve(analysis)

    if not verdicts:
        st.warning("לא נמצאו פסקי דין רלוונטיים לשאלה זו במאגר.")
        return

    st.markdown("#### התשובה")
    answer_box = st.empty()
    collected = []
    try:
        for chunk in ai_search.answer_stream(client, question, verdicts):
            collected.append(chunk)
            answer_box.markdown(
                f'<div class="ai-answer">{"".join(collected)}▌</div>',
                unsafe_allow_html=True)
        answer_box.markdown(f'<div class="ai-answer">{"".join(collected)}</div>',
                            unsafe_allow_html=True)
    except Exception as e:  # noqa: BLE001
        st.error(f"שגיאה בקבלת תשובה מהמודל: {e}")
        return

    st.markdown("#### פסקי הדין ששימשו למענה")
    for v in verdicts:
        render_card(v)


# ============================ פריסה ============================
sidebar()
tab1, tab2 = st.tabs(["🔍 חיפוש רגיל", "✨ חיפוש חכם (AI)"])
with tab1:
    tab_simple()
with tab2:
    tab_ai()
