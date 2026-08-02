import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

export const metadata = { title: "מדיניות פרטיות — גילוי נאות" };

export default function PrivacyPage() {
  return (
    <>
      <Header active="/privacy" />
      <main className="container-page py-16 max-w-3xl">
        <h1 className="font-display text-3xl text-green-900 mb-6">מדיניות פרטיות</h1>
        <div className="space-y-5 text-sm leading-relaxed text-ink/80">
          <p>
            &quot;גילוי נאות&quot; הוא פרויקט אזרחי ללא מטרות רווח. האתר אינו דורש
            הרשמה או יצירת חשבון משתמש, ואינו אוסף מידע מזהה על המבקרים בו
            מעבר לרישום הטכני הרגיל שכל שירות אינטרנט מבצע (כגון כתובת IP
            ותאריך גישה, לצורכי אבטחה ותפעול השרתים).
          </p>
          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">
              שימוש בחיפוש החכם (AI)
            </h2>
            <p>
              כאשר אתם מקלידים שאלה בטאב החיפוש החכם, תוכן השאלה (וההקשר
              המיידי של השיחה, אם יש) נשלח לצורך עיבוד לספק מודל השפה
              (Anthropic). מומלץ לא לכלול בשאלות פרטים מזהים או רגישים
              שאינם נחוצים לצורך השאלה המשפטית עצמה. היסטוריית השיחה
              נשמרת רק בזיכרון הדפדפן שלכם למשך הביקור הנוכחי, ואינה נשמרת
              בשרתי האתר.
            </p>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">
              עוגיות (Cookies) ומעקב
            </h2>
            <p>
              האתר אינו משתמש בעוגיות מעקב ואינו כולל כלי ניתוח שיווקי או
              פרסומי מצד שלישי.
            </p>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">מקור המידע</h2>
            <p>
              פסקי הדין וההחלטות המוצגים באתר מבוססים על מידע ציבורי שאינו
              מסווג, המתפרסם באתרי הרשות השופטת ובית המשפט העליון. האתר אינו
              אחראי לדיוק או לעדכניות המידע המקורי, ואינו מהווה תחליף לעיון
              במקור הרשמי.
            </p>
          </div>
          <p className="text-xs text-muted pt-4 border-t border-border">
            מדיניות זו עשויה להתעדכן מעת לעת. לשאלות ניתן לפנות דרך פרטי
            הקשר המופיעים באתר.
          </p>
        </div>
      </main>
      <Footer />
    </>
  );
}
