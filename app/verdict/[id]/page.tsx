import type { Metadata } from "next"
import Link from "next/link"
import { notFound } from "next/navigation"
import { ArrowRight, CalendarDays, FileText, Gavel, Landmark, Printer } from "lucide-react"
import { VERDICTS } from "@/lib/demo-data"

type Params = { params: Promise<{ id: string }> }

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const { id } = await params
  const verdict = VERDICTS.find((v) => v.id === id)
  if (!verdict) return { title: "פסק דין לא נמצא" }
  return { title: `${verdict.caseNumber} — ${verdict.title}`, description: verdict.summary }
}

export function generateStaticParams() {
  return VERDICTS.map((v) => ({ id: v.id }))
}

function formatDate(iso: string) {
  const [y, m, d] = iso.split("-")
  return `${d}.${m}.${y}`
}

export default async function VerdictPage({ params }: Params) {
  const { id } = await params
  const verdict = VERDICTS.find((v) => v.id === id)
  if (!verdict) notFound()

  return (
    <article className="mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href="/search"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-primary"
      >
        <ArrowRight className="size-4" aria-hidden="true" />
        חזרה לתוצאות החיפוש
      </Link>

      <header className="mt-6 border-b border-border pb-6">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="font-mono text-sm font-semibold text-primary">{verdict.caseNumber}</span>
          <span className="rounded-md bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">
            {verdict.kind}
          </span>
        </div>

        <h1 className="mt-3 text-2xl font-extrabold leading-snug text-primary text-balance sm:text-3xl">
          {verdict.title}
        </h1>

        <dl className="mt-5 flex flex-wrap gap-x-6 gap-y-3 text-sm text-muted-foreground">
          <Meta icon={<Landmark className="size-4" />} label="בית משפט" value={verdict.court} />
          <Meta icon={<Gavel className="size-4" />} label="מותב" value={verdict.judge} />
          <Meta icon={<CalendarDays className="size-4" />} label="תאריך" value={formatDate(verdict.date)} />
        </dl>

        <div className="mt-6 flex flex-wrap gap-2.5">
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <FileText className="size-4" aria-hidden="true" />
            הורדת המסמך המקורי (Word)
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-secondary"
          >
            <FileText className="size-4" aria-hidden="true" />
            PDF
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-secondary"
          >
            <Printer className="size-4" aria-hidden="true" />
            הדפסה
          </button>
        </div>
      </header>

      <section className="mt-8">
        <h2 className="text-lg font-bold text-foreground">תקציר</h2>
        <p className="mt-3 leading-relaxed text-foreground text-pretty">{verdict.summary}</p>
      </section>

      <section className="mt-10">
        <h2 className="text-lg font-bold text-foreground">גוף ההחלטה</h2>
        <div className="mt-3 flex flex-col gap-4 leading-relaxed text-foreground">
          <p className="text-pretty">
            לפני בקשה שהוגשה מטעם הצדדים, ובה נדרשת הכרעה בשאלה המשפטית שבמחלוקת. לאחר שעיינתי בכתבי הטענות, בתצהירים
            ובאסמכתאות שהוצגו, ולאחר ששמעתי את טענות הצדדים בדיון שהתקיים לפניי, באתי לכלל מסקנה כי דין הבקשה להתקבל
            בחלקה.
          </p>
          <p className="text-pretty">
            אקדים ואומר כי המסגרת הנורמטיבית לדיון בסוגיה שלפנינו נקבעה בפסיקה עניפה, ובמרכזה עומד הצורך לאזן בין
            האינטרסים הלגיטימיים של שני הצדדים תוך שמירה על תקנת הציבור ועל עקרון תום הלב במשפט האזרחי.
          </p>
          <p className="text-pretty">
            אשר על כן, ובכפוף לאמור לעיל, אני מקבל את הבקשה בחלקה ומורה כמפורט בסיפא להחלטה זו. בנסיבות העניין, ובשים לב
            לאופן ניהול ההליך, לא מצאתי לעשות צו להוצאות.
          </p>
        </div>

        <p className="mt-8 rounded-xl border border-border bg-muted/50 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
          הטקסט המוצג בעמוד זה הוא דוגמה להמחשת המבנה. בגרסה המחוברת למאגר יוצג כאן הנוסח המלא של ההחלטה כפי שפורסם על
          ידי הרשות השופטת.
        </p>
      </section>
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
