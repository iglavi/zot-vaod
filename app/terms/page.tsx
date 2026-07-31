import type { Metadata } from "next"
import { AlertTriangle } from "lucide-react"
import { PageShell, Prose } from "@/components/page-shell"

export const metadata: Metadata = {
  title: "תנאי שימוש",
  description: "תנאי השימוש באתר גילוי נאות, לרבות הבהרה כי המידע באתר אינו ייעוץ משפטי.",
}

export default function TermsPage() {
  return (
    <PageShell title="תנאי שימוש" lead="השימוש באתר גילוי נאות כפוף לתנאים שלהלן.">
      <div className="flex items-start gap-3 rounded-xl border border-accent/25 bg-accent/5 p-5">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-accent" aria-hidden="true" />
        <p className="text-sm font-medium leading-relaxed text-foreground">
          המידע באתר אינו ייעוץ משפטי. אין להסתמך עליו כתחליף לייעוץ מקצועי מעורך דין המכיר את נסיבות המקרה שלכם.
        </p>
      </div>

      <Prose>
        <h2 className="text-xl font-bold text-primary">אופי השירות</h2>
        <p className="text-muted-foreground">
          גילוי נאות הוא כלי חיפוש והנגשה למסמכים משפטיים פומביים. האתר אינו מספק שירותים משפטיים, אינו מייצג משתמשים,
          ואין בשימוש בו כדי ליצור יחסי עורך דין–לקוח.
        </p>

        <h2 className="mt-4 text-xl font-bold text-primary">דיוק המידע</h2>
        <p className="text-muted-foreground">
          אנו משתדלים שהמאגר יהיה מדויק ומעודכן, אך ייתכנו שגיאות, השמטות או עיכובים בעדכון. תשובות שנוצרו בעזרת בינה
          מלאכותית הן תמצית ממוכנת ועשויות לכלול אי־דיוקים. באחריות המשתמש לאמת כל מסמך מול המקור הרשמי ולבדוק אם ניתן
          פסק דין מאוחר או ערעור שמשנה את המצב המשפטי.
        </p>

        <h2 className="mt-4 text-xl font-bold text-primary">שימוש מותר</h2>
        <ul className="flex list-inside list-disc flex-col gap-2 text-muted-foreground">
          <li>השימוש באתר מותר לצרכים אישיים, מקצועיים, מחקריים ועיתונאיים.</li>
          <li>אין לבצע שאיבה אוטומטית בקצב הפוגע ביציבות השירות עבור משתמשים אחרים.</li>
          <li>אין לעשות שימוש במידע לצורך פגיעה, הטרדה או הפרת צווי איסור פרסום.</li>
        </ul>

        <h2 className="mt-4 text-xl font-bold text-primary">הגבלת אחריות</h2>
        <p className="text-muted-foreground">
          השירות מסופק כמו שהוא (AS IS), ללא אחריות מכל סוג. מפעילי האתר לא יישאו באחריות לכל נזק ישיר או עקיף שייגרם
          כתוצאה משימוש במידע המוצג בו או מהסתמכות עליו.
        </p>

        <h2 className="mt-4 text-xl font-bold text-primary">שינויים בתנאים</h2>
        <p className="text-muted-foreground">
          אנו רשאים לעדכן את תנאי השימוש מעת לעת. המשך השימוש באתר לאחר עדכון מהווה הסכמה לתנאים המעודכנים.
        </p>
      </Prose>
    </PageShell>
  )
}
