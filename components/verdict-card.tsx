import Link from "next/link"
import { CalendarDays, ExternalLink, FileText, Gavel, Landmark } from "lucide-react"
import type { Verdict } from "@/lib/demo-data"
import { cn } from "@/lib/utils"

function formatDate(iso: string) {
  const [y, m, d] = iso.split("-")
  return `${d}.${m}.${y}`
}

export function VerdictCard({ verdict, compact = false }: { verdict: Verdict; compact?: boolean }) {
  return (
    <article className="rounded-2xl border border-border bg-card p-5 transition-shadow hover:shadow-md sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="font-mono text-sm font-semibold text-primary" dir="rtl">
            {verdict.caseNumber}
          </span>
          <span
            className={cn(
              "rounded-md px-2 py-0.5 text-xs font-medium",
              verdict.kind === "פסק דין"
                ? "bg-secondary text-secondary-foreground"
                : "bg-muted text-muted-foreground",
            )}
          >
            {verdict.kind}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <DocButton label="Word" />
          <DocButton label="PDF" />
          {!compact && (
            <Link
              href={`/verdict/${verdict.id}`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary"
            >
              <ExternalLink className="size-3.5" aria-hidden="true" />
              קריאה
            </Link>
          )}
        </div>
      </div>

      <h3 className="mt-3 text-lg font-bold leading-snug text-pretty">
        <Link href={`/verdict/${verdict.id}`} className="text-accent hover:underline">
          {verdict.title}
        </Link>
      </h3>

      <p className="mt-2 text-sm leading-relaxed text-muted-foreground text-pretty">{verdict.summary}</p>

      <dl className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-border pt-3 text-xs text-muted-foreground">
        <Meta icon={<Landmark className="size-3.5" />} label="בית משפט" value={verdict.court} />
        <Meta icon={<Gavel className="size-3.5" />} label="מותב" value={verdict.judge} />
        <Meta icon={<CalendarDays className="size-3.5" />} label="תאריך" value={formatDate(verdict.date)} />
      </dl>
    </article>
  )
}

function Meta({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span aria-hidden="true" className="text-muted-foreground/70">
        {icon}
      </span>
      <dt className="sr-only">{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

function DocButton({ label }: { label: string }) {
  return (
    <button
      type="button"
      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-secondary"
    >
      <FileText className="size-3.5" aria-hidden="true" />
      {label}
      <span className="sr-only">{` — הורדת המסמך`}</span>
    </button>
  )
}
