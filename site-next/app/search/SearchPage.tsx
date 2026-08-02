"use client";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { VerdictCard, CaseGroupCard } from "@/components/VerdictCard";
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

const PER_PAGE = 10;
// כמה "עמודי API" גולמיים (10 שורות כל אחד) מותר לצרוך כדי למלא עמוד
// מוצג אחד של 10 קבוצות - גבול-בטיחות מול תיק-ענק בודד (נצפה בפועל: עד
// 882 שורות תחת אותו מספר תיק) שהיה יכול לגרום ללולאה לצרוך עמודים
// רבים מדי בלי להתקדם במספר הקבוצות בכלל.
const MAX_RAW_PAGES_PER_DISPLAY_PAGE = 8;

/** מקבצת שורות גולמיות לפי (בית משפט, מספר תיק) - מספר תיק לבדו אינו
 * ייחודי-גלובלית (אותו מספר תיק חוזר על עצמו בבתי משפט שונים). */
function groupByCase(rows: Verdict[]): Verdict[][] {
  const order: string[] = [];
  const groups = new Map<string, Verdict[]>();
  for (const v of rows) {
    const key = `${v.court} ${v.case_number}`;
    if (!groups.has(key)) {
      groups.set(key, []);
      order.push(key);
    }
    groups.get(key)!.push(v);
  }
  return order.map((key) => groups.get(key)!);
}

export default function SearchPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const startedRef = useRef(false);

  const [form, setForm] = useState(emptyForm);
  // כל עמוד-תצוגה שכבר נבנה (עד 10 קבוצות כל אחד) - נשמר במטמון כדי
  // ש"הקודם" לא יצטרך לשלוף מחדש. cursor הוא נקודת-ההמשך לצריכת עוד
  // עמודי-API גולמיים (10 שורות כל אחד) כשצריך לבנות את העמוד הבא.
  const [pageCache, setPageCache] = useState<{ groups: Verdict[][]; total: number; capped: boolean }[]>([]);
  const [pageIndex, setPageIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState<string | null>(null);

  type Cursor = { pendingRows: Verdict[]; nextRawPage: number; hasMore: boolean; lastTotal: number; lastCapped: boolean };
  const FRESH_CURSOR: Cursor = { pendingRows: [], nextRawPage: 1, hasMore: true, lastTotal: 0, lastCapped: false };
  const cursorRef = useRef<Cursor>(FRESH_CURSOR);

  function set<K extends keyof typeof form>(key: K, val: string) {
    setForm((f) => ({ ...f, [key]: val }));
  }

  async function fetchApiPage(activeForm: typeof form, apiPage: number) {
    const params = new URLSearchParams(
      Object.entries(activeForm).filter(([, v]) => v).map(([k, v]) => [k, v])
    );
    params.set("page", String(apiPage));
    const res = await fetch(`/api/search?${params.toString()}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "שגיאה בחיפוש");
    return data as { results: Verdict[]; total: number; capped: boolean };
  }

  /** בונה עמוד-תצוגה אחד (עד 10 קבוצות - החלטות מאותו הליך מקובצות יחד,
   * ראו groupByCase) מתוך נקודת-המשך נתונה. ממשיך לצרוך עמודי-API
   * גולמיים (10 שורות כל אחד) עד שמצטברות 10 קבוצות, או שנגמרות
   * התוצאות, או שמגיעים לתקרת-בטיחות MAX_RAW_PAGES_PER_DISPLAY_PAGE -
   * הגנה מפני תיק-ענק בודד (נצפה בפועל: עד 882 שורות תחת מספר תיק אחד)
   * שהיה גורם ללולאה לצרוך עמודים רבים בלי להתקדם במספר הקבוצות בכלל.
   * שורות-עודפות מעבר ל-10 הקבוצות המוצגות נשמרות ב-pendingRows של
   * הסמן המוחזר, כך שהן יוצגו בעמוד הבא ולא "יאבדו". */
  async function fetchDisplayPage(activeForm: typeof form, startCursor: Cursor) {
    let collected = startCursor.pendingRows;
    let nextRawPage = startCursor.nextRawPage;
    let hasMoreData = startCursor.hasMore;
    let total = startCursor.lastTotal;
    let capped = startCursor.lastCapped;
    let iterations = 0;
    let grouped = groupByCase(collected);

    while (grouped.length < PER_PAGE && hasMoreData && iterations < MAX_RAW_PAGES_PER_DISPLAY_PAGE) {
      const data = await fetchApiPage(activeForm, nextRawPage);
      total = data.total;
      capped = data.capped;
      collected = collected.concat(data.results);
      hasMoreData = nextRawPage * PER_PAGE < data.total && data.results.length === PER_PAGE;
      nextRawPage += 1;
      iterations += 1;
      grouped = groupByCase(collected);
    }

    const shown = grouped.slice(0, PER_PAGE);
    const shownIds = new Set(shown.flat().map((v) => v.id));
    const pendingRows = collected.filter((v) => !shownIds.has(v.id));
    const cursor: Cursor = {
      pendingRows, nextRawPage, hasMore: hasMoreData || pendingRows.length > 0,
      lastTotal: total, lastCapped: capped,
    };
    return { display: { groups: shown, total, capped }, cursor };
  }

  function updateUrlPage(activeForm: typeof form, displayPageNumber: number) {
    const params = new URLSearchParams(
      Object.entries(activeForm).filter(([, v]) => v).map(([k, v]) => [k, v])
    );
    params.set("page", String(displayPageNumber));
    // replace, לא push - לא רוצים לצבור היסטוריית-דפדפן על כל דפדוף.
    router.replace(`/search?${params.toString()}`, { scroll: false });
  }

  async function startNewSearch(e?: React.FormEvent, formOverride?: typeof form) {
    e?.preventDefault();
    const activeForm = formOverride ?? form;
    setLoading(true);
    setError(null);
    setStep("received");
    const stepTimer = setTimeout(() => setStep("retrieving"), 400);
    try {
      const { display, cursor } = await fetchDisplayPage(activeForm, FRESH_CURSOR);
      setPageCache([display]);
      setPageIndex(0);
      cursorRef.current = cursor;
      updateUrlPage(activeForm, 1);
    } catch (err: any) {
      setError(err.message ?? "שגיאה בחיפוש");
    } finally {
      clearTimeout(stepTimer);
      setLoading(false);
      setStep(null);
    }
  }

  async function goNext() {
    if (pageIndex + 1 < pageCache.length) {
      setPageIndex((i) => i + 1);
      updateUrlPage(form, pageIndex + 2);
      return;
    }
    if (!cursorRef.current.hasMore) return;
    setLoading(true);
    setError(null);
    try {
      const { display, cursor } = await fetchDisplayPage(form, cursorRef.current);
      setPageCache((prev) => [...prev, display]);
      setPageIndex((i) => i + 1);
      cursorRef.current = cursor;
      updateUrlPage(form, pageCache.length + 1);
    } catch (err: any) {
      setError(err.message ?? "שגיאה בחיפוש");
    } finally {
      setLoading(false);
    }
  }

  function goPrev() {
    if (pageIndex === 0) return;
    setPageIndex((i) => i - 1);
    updateUrlPage(form, pageIndex);
  }

  // תמיכה בקישור-שיתוף (deep link): אם הגענו עם פרמטרים ב-query string
  // (למשל מקישור ששותף), נבנה מהם את הטופס ונריץ חיפוש אוטומטית - פעם
  // אחת בלבד עם הטעינה, לא בכל שינוי ב-searchParams. עמוד>1: משחזרים
  // ברצף (לא ניתן "לקפוץ" ישירות - מספר-הקבוצות בכל עמוד תלוי בקיבוץ
  // דינמי) - עלות מקובלת עבור מקרה-קצה נדיר.
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
      (async () => {
        setLoading(true);
        setError(null);
        setStep("received");
        const stepTimer = setTimeout(() => setStep("retrieving"), 400);
        try {
          const targetDisplayPage = Number.isFinite(urlPage) && urlPage > 0 ? urlPage : 1;
          let cursor = FRESH_CURSOR;
          const pages: { groups: Verdict[][]; total: number; capped: boolean }[] = [];
          for (let i = 0; i < targetDisplayPage; i++) {
            const { display, cursor: nextCursor } = await fetchDisplayPage(nextForm, cursor);
            pages.push(display);
            cursor = nextCursor;
            if (!cursor.hasMore && i < targetDisplayPage - 1) break;
          }
          setPageCache(pages);
          setPageIndex(pages.length - 1);
          cursorRef.current = cursor;
        } catch (err: any) {
          setError(err.message ?? "שגיאה בחיפוש");
        } finally {
          clearTimeout(stepTimer);
          setLoading(false);
          setStep(null);
        }
      })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const current = pageCache[pageIndex];
  const totalPagesApprox = current ? Math.max(1, Math.ceil(current.total / PER_PAGE)) : 1;

  return (
    <>
      <Header active="/search" />
      <main id="main-content" className="container-page py-12">
        <form onSubmit={startNewSearch} className="card p-8">
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

        {current && (
          <div className="mt-10" aria-live="polite">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
              <h2 className="text-sm text-muted">
                נמצאו {current.capped ? "מעל " : ""}{current.total.toLocaleString("he")} תוצאות
              </h2>
            </div>
            <div className="space-y-3">
              {current.groups.map((group) => (
                <div key={`${group[0].court} ${group[0].case_number}`}>
                  {group.length > 1 ? <CaseGroupCard items={group} /> : <VerdictCard v={group[0]} />}
                </div>
              ))}
              {current.groups.length === 0 && (
                <p className="text-sm text-muted">לא נמצאו תוצאות מתאימות.</p>
              )}
            </div>
            {current.groups.length > 0 && (pageIndex > 0 || pageIndex + 1 < pageCache.length || cursorRef.current.hasMore) && (
              <div className="flex items-center justify-center gap-3 mt-8">
                <button
                  disabled={pageIndex <= 0 || loading}
                  onClick={goPrev}
                  className="btn-outline disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  הקודם
                </button>
                <span className="text-sm text-muted">עמוד {pageIndex + 1} מתוך {totalPagesApprox}~</span>
                <button
                  disabled={(pageIndex + 1 >= pageCache.length && !cursorRef.current.hasMore) || loading}
                  onClick={goNext}
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
