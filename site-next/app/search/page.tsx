"use client";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { VerdictCard } from "@/components/VerdictCard";
import { ThinkingSteps } from "@/components/ThinkingSteps";
import { useState, useEffect, useRef } from "react";

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
};

const emptyForm = {
  name: "", judge: "", case_number: "", city: "", court_type: "",
  case_type: "", date_from: "", date_to: "", free_text: "", match_mode: "exact",
};

export default function SearchPage() {
  const [form, setForm] = useState(emptyForm);
  const [results, setResults] = useState<Verdict[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<string | null>(null);

  function set<K extends keyof typeof form>(key: K, val: string) {
    setForm((f) => ({ ...f, [key]: val }));
  }

  async function runSearch(e?: React.FormEvent) {
    e?.preventDefault();
    setLoading(true);
    setError(null);
    setStep("received");
    const stepTimer = setTimeout(() => setStep("retrieving"), 400);
    try {
      const params = new URLSearchParams(
        Object.entries(form).filter(([, v]) => v).map(([k, v]) => [k, v])
      );
      const res = await fetch(`/api/search?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "שגיאה בחיפוש");
      setResults(data.results);
      setTotal(data.total);
    } catch (err: any) {
      setError(err.message ?? "שגיאה בחיפוש");
    } finally {
      clearTimeout(stepTimer);
      setLoading(false);
      setStep(null);
    }
  }

  return (
    <>
      <Header active="/search" />
      <main className="container-page py-12">
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
            <Field label="עיר / מחוז">
              <input className="input-field" value={form.city} onChange={(e) => set("city", e.target.value)} />
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
          <div className="mt-10">
            <h2 className="text-sm text-muted mb-4">נמצאו {total.toLocaleString("he")} תוצאות</h2>
            <div className="space-y-3">
              {results.map((v) => (
                <VerdictCard key={v.id} v={v} />
              ))}
              {results.length === 0 && (
                <p className="text-sm text-muted">לא נמצאו תוצאות מתאימות.</p>
              )}
            </div>
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
