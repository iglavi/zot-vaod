import Link from "next/link"
import { BookOpenText, Scale, SlidersHorizontal, Wallet } from "lucide-react"
import { AiSearch } from "@/components/ai-search"

const FEATURES = [
  {
    icon: Wallet,
    title: "חופשי לגמרי",
    body: "בלי מנוי, בלי תשלום לכל שאילתה ובלי הרשמה. מידע ציבורי צריך להיות נגיש לכולם.",
  },
  {
    icon: BookOpenText,
    title: "בשפה שלכם",
    body: "אין צורך לדעת מונחים משפטיים. שואלים שאלה רגילה — ומקבלים תשובה מוסברת עם הפניות למקורות.",
  },
  {
    icon: SlidersHorizontal,
    title: "גם חיפוש מדויק",
    body: "מי שיודע מה הוא מחפש יכול לסנן לפי שופט, בית משפט, מספר תיק, סוג הליך וטווח תאריכים.",
  },
  {
    icon: Scale,
    title: "מבוסס מקורות",
    body: "כל תשובה מלווה בפסקי הדין שעליהם היא נשענת, כולל אפשרות להוריד את המסמך המקורי.",
  },
]

export default function HomePage() {
  return (
    <>
      <AiSearch />

      {/* why */}
      <section className="mx-auto mt-24 max-w-6xl px-4 sm:px-6">
        <div className="grid items-center gap-10 md:grid-cols-2 md:gap-14">
          <div className="order-2 md:order-1">
            <div className="rounded-2xl border border-border bg-muted/50 p-8">
              <blockquote className="border-e-4 border-primary pe-5 text-base leading-relaxed text-foreground text-pretty">
                דוח מבקר המדינה קבע כי המידע באתר נט-המשפט שמנוהל בידי הרשות השופטת אינו זמין במלואו, וכי לא ניתן מתן
                אפשרויות חיפוש מלאות וביצוע איחזור ועיבוד מידע מתקדם.
              </blockquote>
              <p className="mt-4 text-sm font-medium text-muted-foreground">— מבקר המדינה, 2022</p>
            </div>
          </div>

          <div className="order-1 md:order-2">
            <h2 className="text-3xl font-extrabold tracking-tight text-primary text-balance sm:text-4xl">
              למה צריך את זה?
            </h2>
            <p className="mt-5 text-base leading-relaxed text-muted-foreground text-pretty">
              פסקי דין הם מידע ציבורי. בפועל, מי שרוצה לחפש בהם באמת נדרש למאגרים מסחריים בתשלום, ומי שאינו עורך דין
              נשאר בחוץ.
            </p>
            <p className="mt-4 text-base leading-relaxed text-muted-foreground text-pretty">
              גילוי נאות נותן גישה מלאה למידע המשפטי שאינו מסווג, כך שכל אזרח יוכל ליהנות מהמידע המצוי באתר — ללא תלות
              ברכישת מנוי בתשלום מגורמים מסחריים.
            </p>
            <Link
              href="/about"
              className="mt-7 inline-flex items-center gap-2 rounded-lg border border-primary px-5 py-2.5 text-sm font-semibold text-primary transition-colors hover:bg-primary hover:text-primary-foreground"
            >
              אודות היוזמה
            </Link>
          </div>
        </div>
      </section>

      {/* features */}
      <section className="mx-auto mt-24 max-w-6xl px-4 sm:px-6">
        <h2 className="text-center text-3xl font-extrabold tracking-tight text-primary text-balance sm:text-4xl">
          מה אפשר לעשות כאן
        </h2>

        <ul className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <li key={title} className="rounded-2xl border border-border bg-card p-6">
              <span className="flex size-11 items-center justify-center rounded-xl bg-secondary text-primary">
                <Icon className="size-5" aria-hidden="true" />
              </span>
              <h3 className="mt-4 text-lg font-bold text-foreground">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground text-pretty">{body}</p>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}
