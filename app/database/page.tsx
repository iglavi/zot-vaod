import type { Metadata } from "next"
import Link from "next/link"
import { Database, RefreshCw, Scale, ShieldCheck } from "lucide-react"
import { PageShell, Prose } from "@/components/page-shell"

export const metadata: Metadata = {
  title: "מאגר הידע",
  description: "מה כולל מאגר פסקי הדין וההחלטות של גילוי נאות, ממה הוא מורכב וכל כמה זמן הוא מתעדכן.",
}

const FACTS = [
  {
    icon: Scale,
    title: "פסקי דין והחלטות",
    body: "החלטות ופסקי דין מכלל הערכאות — בית המשפט העליון, מחוזי, שלום, ובתי דין לעבודה.",
  },
  {
    icon: Database,
    title: "טקסט מלא, לא רק תקצירים",
    body: "כל מסמך נשמר בגוף הטקסט המלא, כך שהחיפוש החופשי מוצא ניסוחים מדויקים בתוך ההנמקה עצמה.",
  },
  {
    icon: RefreshCw,
    title: "עדכון שוטף",
    body: "המאגר נסרק ומתעדכן באופן קבוע מול המקורות הפומביים של הרשות השופטת.",
  },
  {
    icon: ShieldCheck,
    title: "מקור פומבי בלבד",
    body: "האתר מסתמך רק על מידע שפורסם לציבור. מסמכים שנאסרו לפרסום או שהוטל עליהם צו איסור אינם נכללים.",
  },
]

export default function DatabasePage() {
  return (
    <PageShell
      eyebrow="שקיפות"
      title="מה יש במאגר?"
      lead="גילוי נאות אינו יוצר מידע חדש. הוא לוקח מידע שכבר שייך לציבור, ומנגיש אותו בצורה שאפשר באמת לחפש בה."
    >
      <ul className="grid gap-4 sm:grid-cols-2">
        {FACTS.map((f) => (
          <li key={f.title} className="rounded-2xl border border-border bg-card p-6">
            <f.icon className="size-6 text-accent" aria-hidden="true" />
            <h2 className="mt-3 font-bold text-primary">{f.title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{f.body}</p>
          </li>
        ))}
      </ul>

      <Prose>
        <h2 className="mt-4 text-xl font-bold text-primary">מה עדיין חסר</h2>
        <p>
          המאגר בבנייה מתמדת. ישנן ערכאות וסוגי הליכים שהכיסוי שלהם עדיין חלקי, ויש מסמכים היסטוריים שטרם נסרקו. אם חיפשתם
          מסמך שאתם יודעים שהוא פומבי ולא מצאתם אותו, נשמח לשמוע.
        </p>
        <p>
          חשוב להדגיש: התוצאות באתר הן נקודת פתיחה למחקר, לא תחליף לו. לפני הסתמכות על פסק דין — כדאי לפתוח את המסמך המקורי
          ולוודא שהוא לא בוטל, שונה או נהפך בערעור.
        </p>
      </Prose>

      <div className="flex flex-wrap gap-3">
        <Link
          href="/search"
          className="inline-flex items-center rounded-lg bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
        >
          לחיפוש במאגר
        </Link>
        <Link
          href="/contact"
          className="inline-flex items-center rounded-lg border border-border bg-card px-5 py-3 text-sm font-semibold text-primary transition-colors hover:bg-secondary"
        >
          דיווח על מסמך חסר
        </Link>
      </div>
    </PageShell>
  )
}
