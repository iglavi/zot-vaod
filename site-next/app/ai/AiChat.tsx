"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { ThinkingSteps } from "@/components/ThinkingSteps";
import { SourceCard } from "@/components/VerdictCard";

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
const CITIZEN_MODE_KEY = "giluy-naot-citizen-mode";

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

export function AiChat() {
  const params = useSearchParams();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [step, setStep] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [history, setHistoryList] = useState<Conversation[]>([]);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  // F-13: "הסבר לי כאזרח" - נשמר ב-localStorage כדי שהבחירה תישאר בין
  // ביקורים (כמו היסטוריית השיחות) - לא קשור לשיחה ספציפית אלא להעדפת
  // המשתמש/ת הכללית.
  const [citizenMode, setCitizenMode] = useState(false);
  const startedRef = useRef(false);
  const stepRef = useRef<HTMLDivElement>(null);
  const conversationIdRef = useRef<string>("");

  function toggleCitizenMode() {
    setCitizenMode((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(CITIZEN_MODE_KEY, next ? "1" : "0");
      } catch {
        // פרטי/quota - לא קריטי, פשוט לא יישמר לפעם הבאה
      }
      return next;
    });
  }

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
      setCitizenMode(localStorage.getItem(CITIZEN_MODE_KEY) === "1");
    } catch {
      // פרטי/quota - משאירים ברירת מחדל (כבוי)
    }
    setHistoryList(loadConversations());
    const q = params.get("q");
    if (q && !startedRef.current) {
      startedRef.current = true;
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // שומר את השיחה הנוכחית ל-localStorage בכל שינוי בתורות - יוצר רשומה
  // חדשה בהודעה הראשונה (עם כותרת = תחילת השאלה), מעדכן אותה בכל תור
  // נוסף. לא שומר שיחה ריקה.
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
    startedRef.current = true;
  }

  function openConversation(c: Conversation) {
    conversationIdRef.current = c.id;
    setTurns(c.turns);
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
    const history = turns.map((t) => ({ role: t.role, content: t.text }));
    setTurns((t) => [...t, { role: "user", text: question }]);
    setInput("");
    setStep("received");

    let res: Response;
    try {
      res = await fetch("/api/ai", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history, citizen_mode: citizenMode }),
      });
    } catch {
      setTurns((t) => [...t, { role: "assistant", text: "שגיאת תקשורת - נסו שוב." }]);
      setStep(null);
      return;
    }
    if (!res.ok || !res.body) {
      setTurns((t) => [...t, { role: "assistant", text: "אירעה שגיאה בשרת. נסו שוב בעוד רגע." }]);
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
    if (!sawTerminalEvent) {
      setStep(null);
      assistantText += assistantText
        ? "\n\n⚠️ התשובה נקטעה (החיבור נסגר). נסו לשאול שוב."
        : "⚠️ לא התקבלה תשובה (החיבור נסגר). נסו לשאול שוב.";
      setTurns((t) => {
        const copy = [...t];
        copy[copy.length - 1] = { ...copy[copy.length - 1], text: assistantText };
        return copy;
      });
    }
  }

  return (
    <>
      <Header active="/ai" />
      <div className="container-page pt-6">
        <button
          onClick={() => setSidebarOpen((v) => !v)}
          aria-expanded={sidebarOpen}
          aria-controls="chat-history"
          className="text-xs text-green-700 hover:text-green-900 flex items-center gap-1.5 mb-2 min-h-[44px]"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M9 4v16" />
          </svg>
          {sidebarOpen ? "הסתרת היסטוריית שיחות" : "הצגת היסטוריית שיחות"}
        </button>
      </div>
      <div className={`container-page pb-8 grid gap-2 grid-cols-1 ${sidebarOpen ? "md:grid-cols-[260px_1fr]" : ""}`}>
        <aside id="chat-history" className={sidebarOpen ? "pl-8 border-l border-border ml-2 hidden md:block" : "hidden"}>
          <button className="btn-outline w-full mb-4" onClick={startNewConversation}>
            שיחה חדשה +
          </button>
          {history.length === 0 ? (
            <div className="text-xs text-muted">היסטוריית השיחות תופיע כאן.</div>
          ) : (
            <div className="space-y-1">
              {history.map((c) => (
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
                  {c.title || "שיחה"}
                </button>
              ))}
            </div>
          )}
        </aside>
        <main id="main-content">
          <h1 className="sr-only">חיפוש AI בפסקי דין</h1>
          <div className="space-y-5 min-h-[50vh]" aria-live="polite">
            {turns.length === 0 && (
              <p className="text-muted text-sm">שאלו שאלה בשפה חופשית על פסקי הדין במאגר.</p>
            )}
            {turns.map((t, i) => (
              <div key={i} className={t.role === "user" ? "flex justify-end" : ""}>
                <div className={
                  t.role === "user"
                    ? "bg-green-700 text-white rounded-2xl px-5 py-3 max-w-xl text-sm"
                    : "max-w-2xl"
                }>
                  {t.role === "assistant" && t.sources && t.sources.length > 0 && (
                    <div className="card p-4 mb-3">
                      <div className="text-xs font-medium text-green-800 mb-2">
                        מקורות מצוטטים ({t.sources.length})
                      </div>
                      <div className="space-y-2">
                        {t.sources.map((s) => (
                          <SourceCard key={s.id} v={s} id={`source-${i}-${s.id}`} />
                        ))}
                      </div>
                    </div>
                  )}
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">
                    {t.role === "assistant" ? renderAnswerWithFormatting(t.text, t.sources, i) : t.text}
                  </p>
                  {t.role === "assistant" && t.text && !(step && i === turns.length - 1) && (
                    <button
                      onClick={() => copyAnswer(t.text, i)}
                      className="mt-2 text-xs text-ink/50 hover:text-green-800 flex items-center gap-1"
                    >
                      {copiedIndex === i ? "✓ הועתק" : "📋 העתקת התשובה"}
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
            ))}
            {step && (
              <div ref={stepRef} className="scroll-mt-24">
                <ThinkingSteps step={step} />
              </div>
            )}
          </div>

          <div className="flex items-center justify-end mt-6">
            <label className="flex items-center gap-2 text-xs text-ink/70 cursor-pointer select-none min-h-[44px]">
              <span>הסבר לי כאזרח (ניסוח פשוט, בלי ז&apos;רגון משפטי)</span>
              <span
                role="switch"
                aria-checked={citizenMode}
                onClick={toggleCitizenMode}
                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleCitizenMode(); } }}
                tabIndex={0}
                className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-green-500/40 ${citizenMode ? "bg-green-700" : "bg-border"}`}
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${citizenMode ? "-translate-x-1" : "-translate-x-6"}`} />
              </span>
            </label>
          </div>

          <form
            onSubmit={(e) => { e.preventDefault(); send(input); }}
            className="card flex items-center gap-3 p-2 pr-3 mt-3 sticky bottom-6"
          >
            <button type="submit" disabled={step !== null} className="btn-primary shrink-0 disabled:opacity-50 disabled:cursor-not-allowed">
              {step !== null ? "מעבד…" : "שאלו"}
            </button>
            <label htmlFor="ai-question" className="sr-only">השאלה שלכם</label>
            <input
              id="ai-question"
              value={input}
              disabled={step !== null}
              onChange={(e) => setInput(e.target.value)}
              placeholder="הקלידו שאלה משפטית בשפה חופשית... (לדוגמה: 'איך מוגדרת עילת הסבירות?')"
              className="flex-1 bg-transparent outline-none focus-visible:ring-2 focus-visible:ring-green-500/40 rounded-md text-base py-2 disabled:opacity-60"
            />
          </form>
        </main>
      </div>
      <Footer />
    </>
  );
}
