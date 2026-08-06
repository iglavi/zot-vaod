"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { ThinkingSteps, STEP_LABELS } from "@/components/ThinkingSteps";
import { SourceCard } from "@/components/VerdictCard";
import { EXAMPLE_QUESTIONS } from "@/lib/exampleQuestions";

type Source = {
  id: number; case_number: string; parties: string; court: string;
  decision_date: string; filed_date: string;
  docx_url?: string | null; pdf_url?: string | null;
};
type Turn = {
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
  suggestions?: string[];
};
type Conversation = { id: string; title: string; turns: Turn[]; updatedAt: number };

const HISTORY_KEY = "giluy-naot-ai-history";
const MAX_SAVED_CONVERSATIONS = 20;
const SIDEBAR_OPEN_KEY = "giluy-naot-ai-sidebar-open";
const SIDEBAR_WIDTH_KEY = "giluy-naot-ai-sidebar-width";
const SIDEBAR_MIN_WIDTH = 200;
const SIDEBAR_MAX_WIDTH = 420;
const SIDEBAR_DEFAULT_WIDTH = 260;

// localStorage בלבד (לא שרת) - אין מערכת חשבונות/התחברות באתר הזה, אז
// זו הדרך היחידה כרגע לשמר היסטוריית שיחות בין טעינות-דף בלי לבנות
// backend חדש. נכשל בשקט (try/catch) - מצב פרטי/quota לא אמור להפיל
// את הצ'אט עצמו, רק את השמירה.
function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveConversations(list: Conversation[]) {
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, MAX_SAVED_CONVERSATIONS)));
  } catch {
    // אין מקום/פרטי - מתעלמים, זו לא שגיאה שהמשתמש צריך לראות
  }
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** מפצל קטע-טקסט (לא כל התשובה - ראו renderAnswerWithFormatting) לפי
 * הופעות של מספר-תיק שמופיע גם ברשימת המקורות, והופך כל הופעה לקישור-
 * עוגן לכרטיס המקור המתאים (id="source-{turnIndex}-{s.id}"). מיון לפי
 * אורך יורד לפני בניית ה-regex - מונע התאמה-חלקית שגויה כשמספר תיק אחד
 * הוא תת-מחרוזת של אחר. */
function linkCitations(text: string, sources: Source[] | undefined, turnIndex: number, keyPrefix: string) {
  const withNumbers = (sources ?? []).filter((s) => s.case_number);
  if (withNumbers.length === 0) return text;
  const byNumber = new Map(withNumbers.map((s) => [s.case_number, s]));
  const sorted = [...byNumber.keys()].sort((a, b) => b.length - a.length);
  const pattern = new RegExp(`(${sorted.map(escapeRegExp).join("|")})`, "g");
  const parts = text.split(pattern);
  return parts.map((part, i) => {
    const source = byNumber.get(part);
    if (!source) return part;
    return (
      <a
        key={`${keyPrefix}-${i}`}
        href={`#source-${turnIndex}-${source.id}`}
        onClick={(e) => {
          e.preventDefault();
          document.getElementById(`source-${turnIndex}-${source.id}`)
            ?.scrollIntoView({ behavior: "smooth", block: "center" });
        }}
        className="text-green-700 underline hover:text-green-900"
      >
        {part}
      </a>
    );
  });
}

const _CLAIM_TAG_RE = /<טענה>([\s\S]*?)<\/טענה>/g;

/** F-7: מפריד חזותית בין "מה נטען" (בתוך <טענה>...</טענה>, ראו
 * _SYSTEM_ANSWER) לבין שאר התשובה (קביעות/ניסוח כללי) - מוצג עם עיצוב
 * שונה בבירור, לא רק ניסוח מילולי (M-03). בזמן streaming, תגית עדיין
 * לא-סגורה פשוט לא תואמת את ה-regex ומוצגת כטקסט רגיל עד שהתשובה
 * מסתיימת - חוסר-עיצוב זמני, לא שגיאה. */
function renderAnswerWithFormatting(text: string, sources: Source[] | undefined, turnIndex: number) {
  const segments = text.split(_CLAIM_TAG_RE);
  // split עם קבוצת-לכידה מחזיר לסירוגין: [רגיל, טענה, רגיל, טענה, ...]
  return segments.map((seg, i) => {
    const isClaim = i % 2 === 1;
    const linked = linkCitations(seg, sources, turnIndex, `seg${i}`);
    if (!isClaim) return <span key={i}>{linked}</span>;
    return (
      <span key={i} className="bg-amber-50 border-r-2 border-amber-400 pr-2 inline-block my-0.5">
        <span className="text-[10px] text-amber-700 align-super">טענה</span> {linked}
      </span>
    );
  });
}

const ANSWER_DISCLAIMER =
  "התשובה נוסחה אוטומטית על בסיס פסקי הדין שלמעלה. היא עלולה לסכם לא " +
  "במדויק, לפספס פסיקה, או להציג טענה של צד לתיק כאילו הייתה קביעה של " +
  "בית המשפט. פתחו את פסק הדין ובדקו לפני שאתם מסתמכים.";

const TRUNCATED_MESSAGE = "התשובה נקטעה באמצע. נסו שוב - השאלה שלכם נשמרה.";

export function AiChat() {
  const params = useSearchParams();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [step, setStep] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(SIDEBAR_DEFAULT_WIDTH);
  const [history, setHistoryList] = useState<Conversation[]>([]);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [failedQuestion, setFailedQuestion] = useState<string | null>(null);
  const startedRef = useRef(false);
  const stepRef = useRef<HTMLDivElement>(null);
  const conversationIdRef = useRef<string>("");
  const resizingRef = useRef<{ startX: number; startWidth: number } | null>(null);

  async function copyAnswer(text: string, index: number) {
    try {
      // מסירים תגיות <טענה> (ראו F-7/renderAnswerWithFormatting) - רק
      // עיצוב-תצוגה, לא אמורות להיות חלק מהטקסט המועתק בפועל.
      const plain = text.replace(/<טענה>([\s\S]*?)<\/טענה>/g, "$1");
      await navigator.clipboard.writeText(plain);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex((cur) => (cur === index ? null : cur)), 2000);
    } catch {
      // דפדפן חוסם/HTTP לא מאובטח - אין navigator.clipboard בכלל; לא קריטי
      // מספיק שהמשתמש יבחר-ידנית, לא שווה הצגת שגיאה על זה
    }
  }

  useEffect(() => {
    try {
      const savedOpen = localStorage.getItem(SIDEBAR_OPEN_KEY);
      if (savedOpen !== null) setSidebarOpen(savedOpen === "1");
      const savedWidth = Number(localStorage.getItem(SIDEBAR_WIDTH_KEY));
      if (savedWidth) setSidebarWidth(Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, savedWidth)));
    } catch {
      // פרטי/quota - משאירים ברירת מחדל
    }
    setHistoryList(loadConversations());
    const q = params.get("q");
    if (q && !startedRef.current) {
      startedRef.current = true;
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function toggleSidebar() {
    setSidebarOpen((prev) => {
      const next = !prev;
      try { localStorage.setItem(SIDEBAR_OPEN_KEY, next ? "1" : "0"); } catch { /* לא קריטי */ }
      return next;
    });
  }

  // גרירת הגבול השמאלי של עמודת ההיסטוריה (מימין, ב-RTL) לשינוי רוחבה -
  // ראו Tikunim.txt סעיף 12 ("כמו אפשרות להזיז עמודה בטבלה ב-office").
  function startResize(e: React.MouseEvent) {
    e.preventDefault();
    resizingRef.current = { startX: e.clientX, startWidth: sidebarWidth };
    window.addEventListener("mousemove", onResizeMove);
    window.addEventListener("mouseup", onResizeEnd);
  }
  function onResizeMove(e: MouseEvent) {
    const r = resizingRef.current;
    if (!r) return;
    // ב-RTL העמודה על הימין - גרירה שמאלה (clientX קטן יותר) צריכה להרחיב.
    const delta = r.startX - e.clientX;
    const next = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, r.startWidth + delta));
    setSidebarWidth(next);
  }
  function onResizeEnd() {
    resizingRef.current = null;
    window.removeEventListener("mousemove", onResizeMove);
    window.removeEventListener("mouseup", onResizeEnd);
    try { localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth)); } catch { /* לא קריטי */ }
  }

  // שומר את השיחה הנוכחית ל-localStorage בכל שינוי בתורות - יוצר רשומה
  // חדשה בהודעה הראשונה (עם כותרת = תחילת השאלה), מעדכן אותה בכל תור
  // נוסף. לא שומר שיחה ריקה. שומר את התורות *במלואן* (כולל טקסט התשובה,
  // לא רק השאלה) - ראו openConversation/היסטוריה למטה.
  useEffect(() => {
    if (turns.length === 0) return;
    if (!conversationIdRef.current) {
      conversationIdRef.current = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    }
    const firstUserTurn = turns.find((t) => t.role === "user");
    const title = firstUserTurn ? firstUserTurn.text.slice(0, 60) : "שיחה";
    setHistoryList((prev) => {
      const withoutCurrent = prev.filter((c) => c.id !== conversationIdRef.current);
      const updated: Conversation[] = [
        { id: conversationIdRef.current, title, turns, updatedAt: Date.now() },
        ...withoutCurrent,
      ];
      saveConversations(updated);
      return updated;
    });
  }, [turns]);

  function startNewConversation() {
    conversationIdRef.current = "";
    setTurns([]);
    setFailedQuestion(null);
    startedRef.current = true;
  }

  function openConversation(c: Conversation) {
    conversationIdRef.current = c.id;
    setTurns(c.turns);
    setFailedQuestion(null);
    startedRef.current = true;
  }

  // גוללים לאזור "תהליך החשיבה" רק כשהשלב עצמו משתנה (קיבלתי/מנתח/מחפש/
  // מנסח) - לא בכל תו שמוזרם בתשובה. זה מה שמונע מהעמוד "למשוך" את
  // המשתמש למטה כל הזמן בזמן שהתשובה נכתבת, ומאפשר לו לגלול בחופשיות.
  useEffect(() => {
    if (step) {
      stepRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [step]);

  async function send(question: string) {
    if (!question.trim() || step !== null) return; // מונע שליחה כפולה בזמן ששאלה קודמת עוד בתהליך
    setFailedQuestion(null);
    const history = turns.map((t) => ({ role: t.role, content: t.text }));
    setTurns((t) => [...t, { role: "user", text: question }]);
    setInput("");
    setStep("received");

    let res: Response;
    try {
      res = await fetch("/api/ai", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history }),
      });
    } catch {
      setTurns((t) => [...t, { role: "assistant", text: "שגיאת תקשורת - נסו שוב." }]);
      setFailedQuestion(question);
      setStep(null);
      return;
    }
    if (!res.ok || !res.body) {
      setTurns((t) => [...t, { role: "assistant", text: "אירעה שגיאה בשרת. נסו שוב בעוד רגע." }]);
      setFailedQuestion(question);
      setStep(null);
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let assistantText = "";
    let sources: Source[] = [];
    let sawTerminalEvent = false;
    setTurns((t) => [...t, { role: "assistant", text: "" }]);

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const chunks = buf.split("\n\n");
      buf = chunks.pop() ?? "";
      for (const chunk of chunks) {
        const evMatch = chunk.match(/^event: (.+)$/m);
        const dataMatch = chunk.match(/^data: (.+)$/m);
        if (!evMatch || !dataMatch) continue;
        const event = evMatch[1];
        const data = JSON.parse(dataMatch[1]);
        if (event === "step") setStep(data.step);
        if (event === "sources") {
          sources = data.verdicts;
          setTurns((t) => {
            const copy = [...t];
            copy[copy.length - 1] = { ...copy[copy.length - 1], sources };
            return copy;
          });
        }
        if (event === "delta") {
          assistantText += data.text;
          setTurns((t) => {
            const copy = [...t];
            copy[copy.length - 1] = { ...copy[copy.length - 1], text: assistantText, sources };
            return copy;
          });
        }
        if (event === "error") {
          assistantText = data.message;
          setTurns((t) => {
            const copy = [...t];
            copy[copy.length - 1] = { ...copy[copy.length - 1], text: assistantText };
            return copy;
          });
        }
        if (event === "suggestions" && Array.isArray(data.questions) && data.questions.length > 0) {
          setTurns((t) => {
            const copy = [...t];
            copy[copy.length - 1] = { ...copy[copy.length - 1], suggestions: data.questions };
            return copy;
          });
        }
        if (event === "done" || event === "error") {
          sawTerminalEvent = true;
          setStep(null);
        }
      }
    }

    // האחזור כמעט תמיד מחזיר איזה מועמדים (גם לשאלות לא-משפטיות לגמרי,
    // למשל "מתכון לעוגה") - כשהמודל בפועל לא מצטט אף אחד מהם (0 ממספרי
    // התיקים מופיעים בתשובה), הצגתם כ"מקורות מצוטטים" מטעה. מנקים לגמרי
    // רק כשאין אף ציטוט אחד (all-or-nothing) - כדי לא לפספס ציטוט אמיתי
    // שמנוסח קצת אחרת ממה שמוצג בכרטיס המקור.
    if (sources.length > 0 && !sources.some((s) => s.case_number && assistantText.includes(s.case_number))) {
      sources = [];
      setTurns((t) => {
        const copy = [...t];
        copy[copy.length - 1] = { ...copy[copy.length - 1], sources: [] };
        return copy;
      });
    }

    // ההזרמה נסגרה (חיבור נסגר, למשל timeout של פונקציית ה-serverless)
    // בלי אירוע "done"/"error" מפורש - בלעדי הטיפול הזה נשאר לנצח "מנסח
    // תשובה..." תקוע על המסך עם טקסט חלקי, אף שהחיבור כבר מת בפועל.
    // השאלה המקורית נשמרת (failedQuestion) כדי לאפשר כפתור "נסו שוב"
    // בלחיצה אחת, בלי להקליד אותה מחדש - ראו Tikunim.txt D12.
    if (!sawTerminalEvent) {
      setStep(null);
      setFailedQuestion(question);
      assistantText = assistantText ? `${assistantText}\n\n${TRUNCATED_MESSAGE}` : TRUNCATED_MESSAGE;
      setTurns((t) => {
        const copy = [...t];
        copy[copy.length - 1] = { ...copy[copy.length - 1], text: assistantText };
        return copy;
      });
    }
  }

  const hasStarted = turns.length > 0;

  function questionForm(sticky: boolean) {
    return (
      <form
        onSubmit={(e) => { e.preventDefault(); send(input); }}
        className={`card flex items-center gap-3 p-2 pr-3 ${sticky ? "mt-3 sticky bottom-6" : ""}`}
      >
        <label htmlFor="ai-question" className="sr-only">השאלה שלכם</label>
        <input
          id="ai-question"
          value={input}
          disabled={step !== null}
          onChange={(e) => setInput(e.target.value)}
          placeholder="כתבו את השאלה בשפה חופשית, בלי מונחים משפטיים ובלי מספר הליך"
          className="flex-1 bg-transparent outline-none focus-visible:ring-2 focus-visible:ring-green-500/40 rounded-md text-base py-2 disabled:opacity-60"
        />
        <button type="submit" disabled={step !== null} className="btn-primary shrink-0 disabled:opacity-50 disabled:cursor-not-allowed">
          {step !== null ? "מעבד…" : "שאלו"}
        </button>
      </form>
    );
  }

  return (
    <>
      <Header active="/ai" />
      <div className="container-page pt-6">
        <button
          onClick={toggleSidebar}
          aria-expanded={sidebarOpen}
          aria-controls="chat-history"
          aria-label={sidebarOpen ? "הסתרת היסטוריית שיחות" : "הצגת היסטוריית שיחות"}
          className="text-xs text-green-700 hover:text-green-900 flex items-center gap-1.5 mb-2 min-h-[44px]"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M9 4v16" />
          </svg>
          {sidebarOpen && <span>הסתרת היסטוריית שיחות</span>}
        </button>
      </div>
      <div
        className="container-page pb-8 grid gap-2 grid-cols-1"
        style={sidebarOpen ? { gridTemplateColumns: `${sidebarWidth}px 1fr` } : undefined}
      >
        {sidebarOpen && (
          <aside id="chat-history" className="relative pl-8 border-l border-border ml-2 hidden md:block">
            <button className="btn-outline w-full mb-4" onClick={startNewConversation}>
              שיחה חדשה +
            </button>
            {history.length === 0 ? (
              <div className="text-xs text-muted">היסטוריית השיחות תופיע כאן.</div>
            ) : (
              <div className="space-y-1">
                {history.map((c) => {
                  const firstAnswer = c.turns.find((t) => t.role === "assistant")?.text ?? "";
                  return (
                    <button
                      key={c.id}
                      onClick={() => openConversation(c)}
                      className={`w-full text-right text-xs px-2 py-2 rounded-md truncate ${
                        c.id === conversationIdRef.current
                          ? "bg-green-100 text-green-800 font-medium"
                          : "text-ink/70 hover:bg-cream"
                      }`}
                      title={c.title}
                    >
                      <div className="truncate">{c.title || "שיחה"}</div>
                      {firstAnswer && (
                        <div className="truncate text-[10px] text-ink/50 font-normal">{firstAnswer}</div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
            {/* ידית גרירה לשינוי רוחב העמודה - ראו startResize למעלה */}
            <div
              onMouseDown={startResize}
              role="separator"
              aria-orientation="vertical"
              aria-label="שינוי רוחב עמודת ההיסטוריה"
              className="hidden md:block absolute top-0 bottom-0 left-0 w-2 -ml-1 cursor-col-resize hover:bg-green-100"
            />
          </aside>
        )}
        <main id="main-content">
          <h1 className="sr-only">חיפוש חכם בפסקי דין</h1>
          <p role="status" className="sr-only">
            {step
              ? STEP_LABELS[step] ?? step
              : turns.length > 0 && turns[turns.length - 1].role === "assistant"
              ? "התקבלה תשובה"
              : ""}
          </p>

          {!hasStarted ? (
            <div className="max-w-2xl mx-auto text-center pt-8 pb-4">
              <h2 className="font-display text-2xl text-green-900 mb-6">חיפוש חכם בפסקי דין</h2>
              {questionForm(false)}
              <div className="mt-5 flex flex-wrap justify-center gap-2">
                {EXAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    className="text-xs border border-border rounded-full px-3 py-1.5 min-h-[44px] text-green-800 hover:border-green-700 hover:bg-green-100"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              <div className="space-y-5">
                {turns.map((t, i) => {
                  const isStreamingTurn = Boolean(step) && i === turns.length - 1;
                  return (
                    <div key={i} className={t.role === "user" ? "flex justify-end" : ""}>
                      <div className={
                        t.role === "user"
                          ? "bg-green-700 text-white rounded-2xl px-5 py-3 max-w-xl text-sm"
                          : "max-w-2xl"
                      }>
                        <p className="text-sm leading-relaxed whitespace-pre-wrap">
                          {t.role === "assistant" ? renderAnswerWithFormatting(t.text, t.sources, i) : t.text}
                        </p>

                        {/* T2: המקורות מוצגים *מתחת* לתשובה, ורק אחרי שהיא הושלמה */}
                        {t.role === "assistant" && !isStreamingTurn && t.sources && t.sources.length > 0 && (
                          <div className="card p-4 mt-3">
                            <div className="text-xs font-medium text-green-800 mb-2">
                              פסקי הדין שעליהם מבוססת התשובה ({t.sources.length})
                            </div>
                            <div className="space-y-2">
                              {t.sources.map((s) => (
                                <SourceCard key={s.id} v={s} id={`source-${i}-${s.id}`} />
                              ))}
                            </div>
                          </div>
                        )}
                        {t.role === "assistant" && !isStreamingTurn && t.text && (!t.sources || t.sources.length === 0) && (
                          <div className="text-xs text-muted mt-2">לא מצאנו פסקי דין רלוונטיים לשאלה הזו.</div>
                        )}

                        {t.role === "assistant" && !isStreamingTurn && t.text && (
                          <>
                            <p className="text-[11px] text-ink/50 mt-2 leading-relaxed">{ANSWER_DISCLAIMER}</p>
                            <div className="mt-2 flex items-center gap-3 flex-wrap">
                              <button
                                onClick={() => copyAnswer(t.text, i)}
                                className="text-xs text-ink/50 hover:text-green-800 flex items-center gap-1"
                              >
                                {copiedIndex === i ? "✓ הועתק" : "📋 העתקת התשובה"}
                              </button>
                              <a
                                href={`mailto:support@giluy-naot.org.il?subject=${encodeURIComponent("דיווח על טעות בתוצאה")}`}
                                className="text-xs text-ink/50 hover:text-green-800"
                              >
                                יש טעות בתוצאה הזו? דווחו לנו
                              </a>
                            </div>
                          </>
                        )}

                        {i === turns.length - 1 && failedQuestion && !step && (
                          <button
                            onClick={() => send(failedQuestion)}
                            className="btn-outline mt-3 text-sm"
                          >
                            נסו שוב
                          </button>
                        )}

                        {t.role === "assistant" && t.suggestions && t.suggestions.length > 0 &&
                          i === turns.length - 1 && !step && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {t.suggestions.map((q, qi) => (
                              <button
                                key={qi}
                                onClick={() => send(q)}
                                className="text-xs border border-border rounded-full px-3 py-1.5 min-h-[44px] text-green-800 hover:border-green-700 hover:bg-green-100"
                              >
                                {q}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
                {step && (
                  <div ref={stepRef} className="scroll-mt-24">
                    <ThinkingSteps
                      step={step}
                      labels={
                        step === "answering" && !turns[turns.length - 1]?.text
                          ? {
                              ...STEP_LABELS,
                              answering: `קורא ${turns[turns.length - 1]?.sources?.length ?? "את"} פסקי דין…`,
                            }
                          : STEP_LABELS
                      }
                    />
                  </div>
                )}
              </div>

              {questionForm(true)}
            </>
          )}
        </main>
      </div>
      <Footer />
    </>
  );
}
