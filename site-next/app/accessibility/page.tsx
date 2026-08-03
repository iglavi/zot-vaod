import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

export const metadata = { title: "הצהרת נגישות — גילוי נאות" };

export default function AccessibilityPage() {
  return (
    <>
      <Header active="/accessibility" />
      <main id="main-content" className="container-page py-16 max-w-3xl">
        <h1 className="font-display text-3xl text-green-900 mb-6">הצהרת נגישות</h1>
        <div className="space-y-5 text-sm leading-relaxed text-ink/80">
          <p>
            &quot;גילוי נאות&quot; רואה חשיבות רבה במתן שירות שוויוני ונגיש לכלל
            הציבור, לרבות אנשים עם מוגבלות. האתר תוכנן ונבדק בהתאם לתקן
            הישראלי ת&quot;י 5568 (התאמות נגישות לתכנים באינטרנט) ברמה AA,
            המבוסס על WCAG 2.0, מכוח תקנה 35(ה) לתקנות שוויון זכויות לאנשים
            עם מוגבלות (התאמות נגישות לשירות), תשע&quot;ג-2013.
          </p>
          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">
              אופן הבדיקה
            </h2>
            <p>
              נגישות האתר נבדקה באופן ידני על ארבעת הדפים המרכזיים (בית,
              חיפוש מובנה, חיפוש חכם, ואודות), כולל ניווט מלא במקלדת, בדיקת
              ניגודיות צבעים, בדיקה עם קורא מסך, והרצת כלים אוטומטיים
              (axe DevTools / Lighthouse) כבדיקת-עזר בלבד.
            </p>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">
              מגבלות ידועות
            </h2>
            <p>
              חלק מתוכני האתר (למשל טקסטים מלאים של פסקי דין המקוריים, כאשר
              אלה מוצגים כקובצי PDF/Word סרוקים) מגיעים ממקור חיצוני - אתרי
              הרשות השופטת - ואינם בשליטת האתר. ייתכנו רכיבים או מקרי-קצה
              שטרם אותרו; ראו פירוט בהמשך לגבי דיווח על תקלות.
            </p>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">
              פניות בנושא נגישות
            </h2>
            <p>
              נתקלתם בבעיית נגישות באתר, או שיש לכם הצעה לשיפור? נשמח שתפנו
              אלינו בכתובת{" "}
              <a href="mailto:support@giluy-naot.org.il" className="text-green-700 underline hover:text-green-900">
                support@giluy-naot.org.il
              </a>
              . נשתדל להשיב ולטפל בפנייה בהקדם האפשרי.
            </p>
          </div>
          <p className="text-xs text-muted pt-4 border-t border-border">
            הצהרה זו עודכנה לאחרונה ב-3 באוגוסט 2026.
          </p>
        </div>
      </main>
      <Footer />
    </>
  );
}
