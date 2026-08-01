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
};

export function AiChat() {
  const params = useSearchParams();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [step, setStep] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const startedRef = useRef(false);
  const stepRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const q = params.get("q");
    if (q && !startedRef.current) {
      startedRef.current = true;
      send(q);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // גוללים לאזור "תהליך החשיבה" רק כשהשלב עצמו משתנה (קיבלתי/מנתח/מחפש/
  // מנסח) - לא בכל תו שמוזרם בתשובה. זה מה שמונע מהעמוד "למשוך" את
  // המשתמש למטה כל הזמן בזמן שהתשובה נכתבת, ומאפשר לו לגלול בחופשיות.
  useEffect(() => {
    if (step) {
      stepRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [step]);

  async function send(question: string) {
    if (!question.trim()) return;
    const history = turns.map((t) => ({ role: t.role, content: t.text }));
    setTurns((t) => [...t, { role: "user", text: question }]);
    setInput("");
    setStep("received");

    const res = await fetch("/api/ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
    });
    if (!res.body) return;
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
        if (event === "done" || event === "error") {
          sawTerminalEvent = true;
          setStep(null);
        }
      }
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
          className="text-xs text-green-700 hover:text-green-900 flex items-center gap-1.5 mb-2"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M9 4v16" />
          </svg>
          {sidebarOpen ? "הסתרת היסטוריית שיחות" : "הצגת היסטוריית שיחות"}
        </button>
      </div>
      <div className="container-page pb-8 grid gap-2" style={{ gridTemplateColumns: sidebarOpen ? "260px 1fr" : "1fr" }}>
        {sidebarOpen && (
          <aside className="pl-8 border-l border-border ml-2 hidden md:block">
            <button className="btn-outline w-full mb-4" onClick={() => { setTurns([]); startedRef.current = true; }}>
              שיחה חדשה +
            </button>
            <div className="text-xs text-muted">היסטוריית השיחה הנוכחית תופיע כאן.</div>
          </aside>
        )}
        <main>
          <div className="space-y-5 min-h-[50vh]">
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
                          <SourceCard key={s.id} v={s} />
                        ))}
                      </div>
                    </div>
                  )}
                  <p className="text-sm leading-relaxed whitespace-pre-wrap">{t.text}</p>
                </div>
              </div>
            ))}
            {step && (
              <div ref={stepRef} className="scroll-mt-24">
                <ThinkingSteps step={step} />
              </div>
            )}
          </div>

          <form
            onSubmit={(e) => { e.preventDefault(); send(input); }}
            className="card flex items-center gap-3 p-2 pr-3 mt-8 sticky bottom-6"
          >
            <button type="submit" className="btn-primary shrink-0">שאלה חדשה</button>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="הקלידו שאלה, נוסחו מסמך כאן... (לדוגמה: 'איך מוגדרת עילת הסבירות?')"
              className="flex-1 bg-transparent outline-none text-sm py-2"
            />
          </form>
        </main>
      </div>
      <Footer />
    </>
  );
}
