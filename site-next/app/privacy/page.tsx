import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

export const metadata = { title: "מדיניות פרטיות — גילוי נאות" };

export default function PrivacyPage() {
  return (
    <>
      <Header active="/privacy" />
      <main id="main-content" className="container-page py-16 max-w-3xl">
        <h1 className="font-display text-3xl text-green-900 mb-6">מדיניות פרטיות</h1>
        <div className="space-y-5 text-sm leading-relaxed text-ink/80">
          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">בקצרה</h2>
            <p>
              אין צורך להירשם כדי להשתמש באתר. אנחנו לא מוכרים מידע, לא
              מעבירים אותו למפרסמים, ולא בונים עליכם פרופיל. זו זכותכם
              לעיין במסמכים האלה, בלי שיבקשו מכם שום פרט מזהה.
            </p>
            <p className="mt-2">
              הדבר האחד שחשוב שתדעו: כשאתם שואלים שאלה במנוע ה-AI, הטקסט
              שהקלדתם נשלח לספק חיצוני שמפעיל את מודל השפה. הפירוט למטה.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">מה קורה כשאתם שואלים את מנוע ה-AI</h2>
            <p>
              השאלה שהקלדתם נשלחת אל Anthropic, המפעילה את מודל השפה
              (Claude) עבורנו. השרתים שלה נמצאים בארצות הברית, כלומר המידע
              יוצא מגבולות ישראל.
            </p>
            <p className="mt-2">
              המלצה מעשית: אל תכתבו בשאלה פרטים מזהים שלכם או של אחרים -
              שמות מלאים, מספרי זהות, כתובות או פרטים רפואיים. כדי לקבל
              תשובה טובה על סוגיה משפטית אין צורך בהם. תארו את המצב, לא את
              האנשים.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">עוגיות</h2>
            <p>אנחנו לא משתמשים בעוגיות מעקב ולא בעוגיות פרסום.</p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">מידע אישי שמופיע בתוך פסקי הדין</h2>
            <p>
              פסקי דין שמפורסמים על ידי הרשות השופטת כוללים לעיתים שמות של
              בעלי דין, עדים ואנשים אחרים. אנחנו מציגים את המסמכים כפי
              שפורסמו ואיננו מוסיפים להם מידע.
            </p>
            <p className="mt-2">
              אנחנו עוקבים באופן צמוד אחר החלטות שקובעות צו איסור פרסום או
              חסיון, ומעדכנים מיד את המאגר בהתאם. אם אתם סבורים שמופיע
              במאגר פסק דין או החלטה שלא צריכים להופיע שם בגלל החלטה
              שיפוטית - פנו אלינו ונסיר מיד.
            </p>
            <p className="mt-2">
              חשוב - אם אתם סבורים שיש עילה להסרת פסק דין או החלטה מהאתר
              בגלל שהם כוללים פרטים אישיים - הדרך היא לפנות לבית המשפט
              ולבקש חסיון או איסור פרסום. כל עוד פסק הדין מפורסם באתר
              הרשות השופטת הוא יפורסם גם כאן. אתרים אחרים ברשת מציעים
              אפשרות להסיר תוצאות חיפוש תמורת תשלום. עד כמה שהדבר מפתה,
              באתר הזה זה לא יקרה. אין טעם לפנות בנושא.
            </p>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-green-900 mb-2">אבטחה</h2>
            <p>אנחנו נוקטים אמצעים סבירים להגנה על המידע, אבל שום שירות מקוון אינו חסין לחלוטין.</p>
          </div>

          <p className="text-xs text-muted pt-4 border-t border-border">
            אם נעדכן את המדיניות, נציין כאן את תאריך העדכון. עודכן לאחרונה: 6 באוגוסט 2026.
          </p>
          <p className="text-xs text-muted">
            יצירת קשר:{" "}
            <a href="mailto:support@giluy-naot.org.il" className="text-green-700 underline hover:text-green-900">
              support@giluy-naot.org.il
            </a>
          </p>
          <p className="text-xs text-muted">תשתדלו לא לתבוע אותי.</p>
        </div>
      </main>
      <Footer />
    </>
  );
}
