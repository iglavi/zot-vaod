import type { Metadata } from "next"
import Link from "next/link"
import { Seal } from "@/components/seal"

export const metadata: Metadata = {
  title: "אודות היוזמה",
  description:
    "גילוי נאות הוא פרויקט אזרחי ללא מטרות רווח שמנגיש את פסיקת בתי המשפט בישראל לכל אדם, בלי תשלום ובלי צורך בידע משפטי.",
}

const STEPS = [
  {
    n: "01",
    title: "שואלים שאלה",
    body: "כותבים שאלה בשפה רגילה — בדיוק כמו שהייתם שואלים אדם. אין צורך במונחים משפטיים או בשמות של חוקים.",
  },
  {
    n: "02",
    title: "המערכת מחפשת במאגר",
    body: "השאלה מפורקת למושגי מפתח, והמערכת סורקת את פסקי הדין וההחלטות שבמאגר כדי לאתר את המקורות הרלוונטיים.",
  },
  {
    n: "03",
    title: "מקבלים תשובה עם מקורות",
    body: "התשובה מנוסחת בשפה ברורה, ולצידה מוצגים פסקי הדין שעליהם היא מתבססת — כולל אפשרות לקרוא ולהוריד אותם.",
  },
]

export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6 sm:py-20">
      <div className="flex flex-col items-center text-center">
        <span className="text-primary">
          <Seal size={64} />
        </span>
        <h1 className="mt-6 text-3xl font-extrabold tracking-tight text-primary text-balance sm:text-4xl">
          מידע ציבורי צריך להיות ציבורי
        </h1>
        <p className="mt-5 text-base leading-relaxed text-muted-foreground text-pretty sm:text-lg">
          גילוי נאות הוא פרויקט אזרחי ללא מטרות רווח, שמטרתו להנגיש את פסיקת בתי המשפט בישראל לכל אדם — בלי תשלום, בלי
          מנוי ובלי צורך בהשכלה משפטית.
        </p>
      </div>

      <section className="mt-16">
        <h2 className="text-2xl font-extrabold tracking-tight text-primary">הבעיה</h2>
        <div className="mt-4 flex flex-col gap-4 leading-relaxed text-foreground">
          <p className="text-pretty">
            פסקי דין והחלטות של בתי משפט הם, מעצם טיבם, מידע ציבורי. עקרון פומביות הדיון הוא עקרון יסוד בשיטת המשפט
            הישראלית. אלא שבפועל, מי שרוצה לחפש בפסיקה באופן יסודי נדרש כמעט תמיד למאגרים מסחריים שגובים דמי מנוי גבוהים.
          </p>
          <p className="text-pretty">
            התוצאה היא פער נגישות: עורכי דין ומשרדים גדולים מקבלים תמונה מלאה, בעוד שאזרח מן השורה — שרוצה להבין מה
            הזכויות שלו לפני שהוא נכנס להליך, או אחריו — נשאר בחוץ.
          </p>
          <blockquote className="my-2 rounded-xl border-e-4 border-primary bg-muted/50 px-5 py-4 text-sm leading-relaxed text-foreground text-pretty">
            דוח מבקר המדינה משנת 2022 קבע כי המידע באתר נט-המשפט, שמנוהל בידי הרשות השופטת, אינו זמין במלואו, ואינו מאפשר
            חיפוש מלא, איחזור ועיבוד מידע מתקדם.
          </blockquote>
        </div>
      </section>

      <section className="mt-14">
        <h2 className="text-2xl font-extrabold tracking-tight text-primary">איך זה עובד</h2>
        <ol className="mt-6 flex flex-col gap-5">
          {STEPS.map((s) => (
            <li key={s.n} className="flex gap-5 rounded-2xl border border-border bg-card p-5 sm:p-6">
              <span className="font-mono text-2xl font-extrabold text-primary/30" aria-hidden="true">
                {s.n}
              </span>
              <div>
                <h3 className="text-lg font-bold text-foreground">{s.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground text-pretty">{s.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-14">
        <h2 className="text-2xl font-extrabold tracking-tight text-primary">מה חשוב לדעת</h2>
        <ul className="mt-5 flex flex-col gap-3">
          {[
            "האתר אינו מספק ייעוץ משפטי. התשובות הן נקודת פתיחה להבנה, ולא תחליף לעורך דין.",
            "התשובות מנוסחות אוטומטית ועשויות להכיל אי-דיוקים. תמיד כדאי לקרוא את פסק הדין המקורי המצוטט.",
            "המאגר כולל פסיקה שפורסמה בפומבי בלבד. החלטות בדלתיים סגורות, בענייני קטינים או תחת צו איסור פרסום אינן נכללות.",
            "האתר אינו שומר את השאלות שלכם לצורך זיהוי, ואינו דורש הרשמה.",
          ].map((t) => (
            <li key={t} className="flex gap-3 text-sm leading-relaxed text-foreground text-pretty">
              <span aria-hidden="true" className="mt-2 size-1.5 shrink-0 rounded-full bg-primary" />
              {t}
            </li>
          ))}
        </ul>
      </section>

      <div className="mt-14 flex flex-col items-center gap-3 rounded-2xl border border-border bg-muted/50 p-8 text-center">
        <p className="text-base font-bold text-foreground">רוצים לנסות?</p>
        <Link
          href="/"
          className="mt-1 inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
        >
          שאלו את השאלה הראשונה שלכם
        </Link>
      </div>
    </div>
  )
}
