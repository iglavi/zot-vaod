import { useState } from "react";
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
  /** HTML קטן (רק &lt;mark&gt; מותר, escape-ed בשרת) - ראו api/search.py: _build_snippet. */
  snippet?: string | null;
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
        <a
          href={v.docx_url}
          target="_blank"
          rel="noopener noreferrer"
          className={cls}
          aria-label={`פתחו את פסק הדין בתיק ${v.case_number} — קובץ Word (נפתח בחלון חדש)`}
        >
          <span aria-hidden="true">📝</span> Word
        </a>
      )}
      {v.pdf_url && (
        <a
          href={v.pdf_url}
          target="_blank"
          rel="noopener noreferrer"
          className={cls}
          aria-label={`פתחו את פסק הדין בתיק ${v.case_number} — קובץ PDF (נפתח בחלון חדש)`}
        >
          <span aria-hidden="true">📄</span> PDF
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
      <h3 className="font-medium text-ink">{v.parties || "ללא שם צדדים"}</h3>
      <div className="text-xs text-muted mt-1 flex items-center gap-1 flex-wrap">
        <span>{v.court}</span>
        {v.court && <span>·</span>}
        <DateLtr value={v.decision_date || v.filed_date} />
        {v.judge && <span>·</span>}
        <span>{v.judge}</span>
      </div>
      {v.snippet && (
        <p
          className="text-xs text-ink/70 mt-2 leading-relaxed [&_mark]:bg-green-200 [&_mark]:text-green-900 [&_mark]:rounded-sm [&_mark]:px-0.5"
          dangerouslySetInnerHTML={{ __html: v.snippet }}
        />
      )}
    </div>
  );
}

const _CASE_GROUP_TIMELINE_CAP = 40;

/** כרטיס-קיבוץ לכמה החלטות שחולקות אותו (בית משפט, מספר תיק) - למשל
 * החלטת-ביניים + פסק דין, או תיק פשיטת-רגל/פירוק עם עשרות-מאות החלטות
 * דיוניות. הקיבוץ מתבצע רק בתוך עמוד התוצאות הנוכחי (ראו SearchPage.tsx) -
 * לא שאילתת-DB חדשה - כדי לא לחזור על מלכודת ה-GROUP BY המלא שכבר נצפתה
 * (ראו הערה ב-zot/search.py: _distinct_values). items ממוינים כאן לפי
 * תאריך יורד; item[0] (העדכני ביותר) משמש לכותרת הקבוצה. */
export function CaseGroupCard({ items }: { items: Verdict[] }) {
  const [open, setOpen] = useState(false);
  const sorted = [...items].sort((a, b) =>
    (b.decision_date || b.filed_date || "").localeCompare(a.decision_date || a.filed_date || "")
  );
  const head = sorted[0];
  const shown = sorted.slice(0, _CASE_GROUP_TIMELINE_CAP);
  const hidden = sorted.length - shown.length;

  return (
    <div className="card p-5">
      <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
        <div className="flex items-center gap-2 text-xs">
          <span className="bg-amber-100 text-amber-800 rounded-full px-3 py-1 font-medium">
            {sorted.length} החלטות בתיק זה
          </span>
          <span className="text-muted">{head.case_number}</span>
        </div>
      </div>
      <h3 className="font-medium text-ink">{head.parties || "ללא שם צדדים"}</h3>
      <div className="text-xs text-muted mt-1 flex items-center gap-1 flex-wrap">
        <span>{head.court}</span>
      </div>

      <button
        onClick={() => setOpen((o) => !o)}
        className="mt-3 text-xs text-green-700 underline hover:text-green-900 min-h-[44px] inline-flex items-center"
        aria-expanded={open}
      >
        {open ? "הסתר ציר זמן" : "הצג ציר זמן של כל ההחלטות בתיק"}
      </button>

      {open && (
        <div className="mt-2 border-t border-border pt-3 space-y-2">
          {shown.map((v) => (
            <div key={v.id} className="flex items-center justify-between gap-3 text-xs flex-wrap">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="bg-green-100 text-green-800 rounded-full px-2.5 py-0.5 font-medium">
                  {v.decision_type || "החלטה"}
                </span>
                <DateLtr value={v.decision_date || v.filed_date} />
              </div>
              <DocLinks v={v} size="small" />
            </div>
          ))}
          {hidden > 0 && (
            <p className="text-xs text-muted pt-1">
              ועוד {hidden.toLocaleString("he")} החלטות נוספות בתיק זה - חפשו לפי מספר תיק ({head.case_number}) לצפייה בכולן.
            </p>
          )}
        </div>
      )}
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
