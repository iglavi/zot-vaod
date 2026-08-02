import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

export const metadata = { title: "תנאי שימוש — גילוי נאות" };

export default function TermsPage() {
  return (
    <>
      <Header active="/terms" />
      <main id="main-content" className="container-page py-16 max-w-3xl">
        <h1 className="font-display text-3xl text-green-900 mb-6">תנאי שימוש</h1>
        <div className="space-y-5 text-sm leading-relaxed text-ink/80">
          <p>
            &quot;גילוי נאות&quot; הוא פרויקט אזרחי ללא מטרות רווח, המנגיש
            מידע ציבורי (פסקי דין והחלטות) מאתרי הרשות השופטת. השימוש באתר
            כפוף לתנאים הבאים.
          </p>
          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">
              לא ייעוץ משפטי
            </h2>
            <p>
              המידע והתשובות המוצגים באתר, לרבות תשובות שנוצרו על ידי החיפוש
              החכם (AI), הם לצרכי מידע כללי בלבד ואינם מהווים ייעוץ משפטי,
              חוות דעת מקצועית, או תחליף להיוועצות עם עורך/ת דין. אין להסתמך
              על האמור באתר לצורך קבלת החלטות משפטיות מבלי לקבל ייעוץ מקצועי
              מתאים.
            </p>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">
              דיוק המידע
            </h2>
            <p>
              המידע באתר מבוסס על נתונים ציבוריים המתפרסמים על ידי הרשות
              השופטת, ומעובד באופן אוטומטי. ייתכנו אי-דיוקים, השמטות, או
              עיכובים בעדכון המידע ביחס למקור הרשמי. תשובות שמפיק החיפוש
              החכם עלולות להכיל טעויות או אי-דיוקים, ויש לאמת כל מידע קריטי
              מול פסק הדין המקורי ומול המקור הרשמי באתרי הרשות השופטת.
            </p>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">
              אחריות המשתמש
            </h2>
            <p>
              השימוש באתר ובשירותיו הוא באחריות המשתמש בלבד. מפעילי האתר לא
              יישאו באחריות לכל נזק, ישיר או עקיף, שייגרם כתוצאה משימוש
              במידע המוצג בו.
            </p>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">
              זמינות השירות
            </h2>
            <p>
              האתר מסופק &quot;כפי שהוא&quot; (AS IS), ללא התחייבות לזמינות
              רציפה או להיעדר תקלות. השירות עשוי להשתנות, להיפסק זמנית, או
              להתעדכן ללא הודעה מראש.
            </p>
          </div>
          <p className="text-xs text-muted pt-4 border-t border-border">
            תנאים אלה עשויים להתעדכן מעת לעת. המשך השימוש באתר לאחר עדכון
            מהווה הסכמה לתנאים המעודכנים.
          </p>
        </div>
      </main>
      <Footer />
    </>
  );
}
