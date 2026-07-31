import type { Metadata } from "next"
import Link from "next/link"
import { PageShell, Prose } from "@/components/page-shell"

export const metadata: Metadata = {
  title: "הצהרת נגישות",
  description: "הצהרת הנגישות של אתר גילוי נאות ודרכי הפנייה לרכז הנגישות.",
}

export default function AccessibilityPage() {
  return (
    <PageShell
      title="הצהרת נגישות"
      lead="גילוי נאות נבנה מתוך הנחה שמידע ציבורי צריך להיות זמין לכולם — כולל מי שמשתמש בטכנולוגיה מסייעת."
    >
      <Prose>
        <h2 className="text-xl font-bold text-primary">מה יישמנו</h2>
        <ul className="flex list-inside list-disc flex-col gap-2 text-muted-foreground">
          <li>מבנה סמנטי ותגיות כותרת היררכיות בכל עמוד.</li>
          <li>אפשרות ניווט מלאה באמצעות מקלדת, כולל סימון ברור של הפוקוס.</li>
          <li>תיאורים חלופיים לתמונות ותוויות מפורשות לכל שדה טופס.</li>
          <li>ניגודיות צבעים העומדת בתקן AA, וטקסט שניתן להגדיל ללא שבירת הפריסה.</li>
          <li>הודעות מצב (כמו התקדמות חיפוש) המוכרזות לקוראי מסך.</li>
        </ul>

        <h2 className="mt-4 text-xl font-bold text-primary">מגבלות ידועות</h2>
        <p className="text-muted-foreground">
          חלק מפסקי הדין במאגר הם קבצים סרוקים שהופקו על ידי גורמים חיצוניים, ולכן רמת הנגישות שלהם אינה בשליטתנו. אנו
          עובדים על המרתם לטקסט נגיש.
        </p>

        <h2 className="mt-4 text-xl font-bold text-primary">נתקלתם בבעיה?</h2>
        <p className="text-muted-foreground">
          אם נתקלתם ברכיב שאינו נגיש, נשמח שתדווחו לנו כדי שנתקן אותו.{" "}
          <Link href="/contact" className="font-medium text-accent underline underline-offset-4 hover:no-underline">
            לפנייה לרכז הנגישות
          </Link>
          .
        </p>
      </Prose>
    </PageShell>
  )
}
