"use client";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { VerdictCard } from "@/components/VerdictCard";
import { ThinkingSteps } from "@/components/ThinkingSteps";
import { useState, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";

type Verdict = {
  id: number;
  case_number: string;
  parties: string;
  court: string;
  decision_date: string;
  filed_date: string;
  judge: string;
  decision_type: string;
  docx_url?: string | null;
  pdf_url?: string | null;
  snippet?: string | null;
};

const emptyForm = {
  name: "", judge: "", case_number: "",
  date_from: "", date_to: "", free_text: "", match_mode: "exact", sort: "newest",
};

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: "newest", label: "מהחדש לישן" },
  { value: "oldest", label: "מהישן לחדש" },
  { value: "relevance", label: "רלוונטיות" },
];

export default function SearchPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const startedRef = useRef(false);

  const [form, setForm] = useState(emptyForm);
  const [results, setResults] = useState<Verdict[] | null>(null);
  const [total, setTotal] = useState(0);
  const [capped, setCapped] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  // תמיכה בקישור-שיתוף (deep link): אם הגענו עם פרמטרים ב-query string
  // (למשל מקישור ששותף), נבנה מהם את הטופס ונריץ חיפוש אוטומטית - פעם
  // אחת בלבד עם הטעינה, לא בכל שינוי ב-searchParams.
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    const fromUrl: Partial<typeof emptyForm> = {};
    let hasAny = false;
    for (const key of Object.keys(emptyForm) as (keyof typeof emptyForm)[]) {
      const v = searchParams.get(key);
      if (v) { fromUrl[key] = v; hasAny = true; }
    }
    const urlPage = parseInt(searchParams.get("page") || "1", 10);
    if (hasAny) {
      const nextForm = { ...emptyForm, ...fromUrl };
      setForm(nextForm);
      runSearch(undefined, Number.isFinite(urlPage) && urlPage > 0 ? urlPage : 1, nextForm);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function set<K extends keyof typeof form>(key: K, val: string) {
    setForm((f) => ({ ...f, [key]: val }));
  }

  async function runSearch(e?: React.FormEvent, targetPage = 1, formOverride?: typeof form) {
    e?.preventDefault();
    const activeForm = formOverride ?? form;
    setLoading(true);
    setError(null);
    setStep("received");
    const stepTimer = setTimeout(() => setStep("retrieving"), 400);
    try {
      const params = new URLSearchParams(
        Object.entries(activeForm).filter(([, v]) => v).map(([k, v]) => [k, v])
      );
      params.set("page", String(targetPage));
      const res = await fetch(`/api/search?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "שגיאה בחיפוש");
      setResults(data.results);
      setTotal(data.total);
      setCapped(Boolean(data.capped));
      setPage(targetPage);
      // הקישור בשורת הכתובת משקף תמיד את החיפוש המוצג כרגע - כדי שאפשר
      // יהיה להעתיק/לשתף אותו ולקבל בדיוק את אותן תוצאות (replace, לא
      // push - לא רוצים לצבור היסטוריית-דפדפן על כל חיפוש/דפדוף).
      router.replace(`/search?${params.toString()}`, { scroll: false });
    } catch (err: any) {
      setError(err.message ?? "שגיאה בחיפוש");
    } finally {
      clearTimeout(stepTimer);
      setLoading(false);
      setStep(null);
    }
  }

  const perPage = 10;
  const totalPages = Math.max(1, Math.ceil(total / perPage));

  return (
    <>
      <Header active="/search" />
      <main id="main-content" className="container-page py-12">
        <form onSubmit={runSearch} className="card p-8">
          <h1 className="text-xl font-semibold text-green-900 mb-6">חיפוש מובנה</h1>
          <div className="grid md:grid-cols-3 gap-5">
            <Field label="שם צד לתיק">
              <input className="input-field" placeholder="למשל: מקייס" value={form.name}
                onChange={(e) => set("name", e.target.value)} />
            </Field>
            <Field label="מספר תיק">
              <input className="input-field" placeholder="למשל: 4934-07-24" value={form.case_number}
                onChange={(e) => set("case_number", e.target.value)} />
            </Field>
            <Field label="שם שופט/ת">
              <input className="input-field" placeholder="למשל: רוני סלע" value={form.judge}
                onChange={(e) => set("judge", e.target.value)} />
            </Field>
            <Field label="מתאריך">
              <input type="date" className="input-field" value={form.date_from}
                onChange={(e) => set("date_from", e.target.value)} />
            </Field>
            <Field label="עד תאריך">
              <input type="date" className="input-field" value={form.date_to}
                onChange={(e) => set("date_to", e.target.value)} />
            </Field>
          </div>
          <div className="mt-5">
            <Field label="חיפוש חופשי בטקסט">
              <input className="input-field" placeholder="מילים בגוף פסק הדין" value={form.free_text}
                onChange={(e) => set("free_text", e.target.value)} />
            </Field>
          </div>
          <div className="mt-5">
            <Field label="מיון תוצאות">
              <select className="input-field" value={form.sort} onChange={(e) => set("sort", e.target.value)}>
                {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </Field>
          </div>
          <div className="mt-5">
            <span className="block text-xs text-muted mb-1.5">סוג ההתאמה לחיפוש החופשי</span>
            <div className="flex items-center gap-6 text-sm">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="match_mode"
                  checked={form.match_mode === "exact"}
                  onChange={() => set("match_mode", "exact")}
                  className="accent-green-700"
                />
                התאמה מדויקת
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="match_mode"
                  checked={form.match_mode === "any"}
                  onChange={() => set("match_mode", "any")}
                  className="accent-green-700"
                />
                התאמה חלקית
              </label>
            </div>
          </div>
          <button type="submit" disabled={loading} className="btn-primary mt-6 w-full md:w-auto">
            {loading ? "מחפש…" : "ביצוע חיפוש במאגר"}
          </button>
          {error && <p className="text-sm text-red-600 mt-3">{error}</p>}
          {step && (
            <div className="mt-4">
              <ThinkingSteps step={step} labels={{ received: "קיבלתי את הבקשה…", retrieving: "מחפש בהתאמה למאגר…" }} order={["received", "retrieving"]} />
            </div>
          )}
        </form>

        {results && (
          <div className="mt-10" aria-live="polite">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
              <h2 className="text-sm text-muted">
                נמצאו {capped ? "מעל " : ""}{total.toLocaleString("he")} תוצאות
              </h2>
            </div>
            <div className="space-y-3">
              {results.map((v, i) => {
                const num = (page - 1) * perPage + i + 1;
                return (
                  <div key={v.id} className="flex items-start gap-3">
                    <span className="text-xs text-muted w-7 shrink-0 text-left pt-5 tabular-nums" dir="ltr">
                      {num}.
                    </span>
                    <div className="flex-1 min-w-0">
                      <VerdictCard v={v} />
                    </div>
                  </div>
                );
              })}
              {results.length === 0 && (
                <p className="text-sm text-muted">לא נמצאו תוצאות מתאימות.</p>
              )}
            </div>
            {results.length > 0 && totalPages > 1 && (
              <div className="flex items-center justify-center gap-3 mt-8">
                <button
                  disabled={page <= 1 || loading}
                  onClick={() => runSearch(undefined, page - 1)}
                  className="btn-outline disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  הקודם
                </button>
                <span className="text-sm text-muted">עמוד {page} מתוך {totalPages}</span>
                <button
                  disabled={page >= totalPages || loading}
                  onClick={() => runSearch(undefined, page + 1)}
                  className="btn-outline disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  הבא
                </button>
              </div>
            )}
          </div>
        )}
      </main>
      <Footer />
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs text-muted mb-1.5">{label}</span>
      {children}
    </label>
  );
}
