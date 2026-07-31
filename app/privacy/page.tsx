import type { Metadata } from "next"
import Link from "next/link"
import { PageShell, Prose } from "@/components/page-shell"

export const metadata: Metadata = {
  title: "מדיניות פרטיות",
  description: "איזה מידע גילוי נאות אוסף, למה, ומה אנחנו לא עושים איתו.",
}

export default function PrivacyPage() {
  return (
    <PageShell
      title="מדיניות פרטיות"
      lead="בקצרה: אנחנו לא דורשים הרשמה, לא מוכרים מידע, ולא מקשרים חיפושים לזהות שלכם."
    >
      <Prose>
        <h2 className="text-xl font-bold text-primary">מה אנחנו אוספים</h2>
        <p className="text-muted-foreground">
          השימוש באתר אינו מחייב הרשמה או מסירת פרטים אישיים. אנו אוספים נתוני שימוש מצומצמים ואנונימיים — כמו שאילתות
          חיפוש במנותק מזהות המשתמש, ונתוני ביצועים תפעוליים — במטרה לשפר את איכות תוצאות החיפוש ולזהות תקלות.
        </p>

        <h2 className="mt-4 text-xl font-bold text-primary">מה אנחנו לא עושים</h2>
        <ul className="flex list-inside list-disc flex-col gap-2 text-muted-foreground">
          <li>איננו מוכרים, משכירים או מעבירים מידע לצדדים שלישיים למטרות שיווק.</li>
          <li>איננו בונים פרופיל אישי ואיננו מקשרים היסטוריית חיפוש לזהות מזוהה.</li>
          <li>איננו עושים שימוש בקוקיות פרסום או במעקב חוצה־אתרים.</li>
        </ul>

        <h2 className="mt-4 text-xl font-bold text-primary">מידע שאתם שולחים אלינו</h2>
        <p className="text-muted-foreground">
          אם פניתם אלינו דרך עמוד יצירת הקשר, נשמור את הפרטים שמסרתם לצורך הטיפול בפנייה בלבד. אנא הימנעו משליחת מידע רגיש
          או חסוי.
        </p>

        <h2 className="mt-4 text-xl font-bold text-primary">תוכן המאגר</h2>
        <p className="text-muted-foreground">
          פסקי הדין וההחלטות המוצגים באתר הם מסמכים שפורסמו לציבור על ידי הרשות השופטת. אם אתם סבורים כי מסמך מסוים פורסם
          בטעות או שקיים לגביו צו איסור פרסום,{" "}
          <Link href="/contact" className="font-medium text-accent underline underline-offset-4 hover:no-underline">
            פנו אלינו
          </Link>{" "}
          ונבחן את הבקשה בהקדם.
        </p>
      </Prose>
    </PageShell>
  )
}
