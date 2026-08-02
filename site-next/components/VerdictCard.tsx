import { DateLtr } from "./DateLtr";

type Verdict = {
  id: number;
  case_number: string;
  parties: string;
  court: string;
  decision_date?: string;
  filed_date?: string;
  judge?: string;
  decision_type?: string;
  docx_url?: string | null;
  pdf_url?: string | null;
};

function DocLinks({ v, size = "normal" }: { v: Verdict; size?: "normal" | "small" }) {
  const cls =
    size === "small"
      ? "flex items-center gap-1 text-[11px] border border-border rounded-md px-2 py-1 text-ink/70 hover:border-green-700 hover:text-green-800"
      : "flex items-center gap-1.5 text-xs border border-border rounded-md px-2.5 py-1.5 text-ink/70 hover:border-green-700 hover:text-green-800";
  if (!v.docx_url && !v.pdf_url) return null;
  return (
    <div className="flex items-center gap-2 shrink-0">
      {v.docx_url && (
        <a href={v.docx_url} target="_blank" rel="noopener noreferrer" className={cls}>
          📝 Word
        </a>
      )}
      {v.pdf_url && (
        <a href={v.pdf_url} target="_blank" rel="noopener noreferrer" className={cls}>
          📄 PDF
        </a>
      )}
    </div>
  );
}

/** כרטיס תוצאה לחיפוש המובנה: מספר הליך מעל שמות הצדדים, ליד סוג ההחלטה. */
export function VerdictCard({ v }: { v: Verdict }) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
        <div className="flex items-center gap-2 text-xs">
          <span className="bg-green-100 text-green-800 rounded-full px-3 py-1 font-medium">
            {v.decision_type || "החלטה"}
          </span>
          <span className="text-muted">{v.case_number}</span>
        </div>
        <DocLinks v={v} />
      </div>
      <div className="font-medium text-ink">{v.parties || "ללא שם צדדים"}</div>
      <div className="text-xs text-muted mt-1 flex items-center gap-1 flex-wrap">
        <span>{v.court}</span>
        {v.court && <span>·</span>}
        <DateLtr value={v.decision_date || v.filed_date} />
        {v.judge && <span>·</span>}
        <span>{v.judge}</span>
      </div>
    </div>
  );
}

/** כרטיס מקור מצוטט בתשובת ה-AI: מספר ההליך יחד ולפני שמות הצדדים, באותה שורה.
 * id אופציונלי - עוגן לקישור-ציטוט מתוך טקסט התשובה עצמו (ראו AiChat.tsx). */
export function SourceCard({ v, id }: { v: Verdict; id?: string }) {
  return (
    <div id={id} className="text-xs border-t border-border pt-2 first:border-0 first:pt-0 scroll-mt-24">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="font-medium text-ink">
          {v.case_number}
          {v.case_number && v.parties ? " — " : ""}
          {v.parties}
        </div>
        <DocLinks v={v} size="small" />
      </div>
      <div className="text-muted mt-0.5 flex items-center gap-1">
        <span>{v.court}</span>
        {v.court && <span>·</span>}
        <DateLtr value={v.decision_date || v.filed_date} />
      </div>
    </div>
  );
}
