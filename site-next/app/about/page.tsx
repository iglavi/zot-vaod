import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

export const metadata = { title: "אודות — גילוי נאות" };

function Section({ title, children, id }: { title: string; children: React.ReactNode; id?: string }) {
  return (
    <section id={id} className="container-page py-8 scroll-mt-24">
      <h2 className="text-xl font-semibold text-green-900 mb-3">{title}</h2>
      <div className="text-sm text-ink/80 leading-relaxed max-w-3xl space-y-3">{children}</div>
    </section>
  );
}

export default function AboutPage() {
  return (
    <>
      <Header active="/about" />
      <main id="main-content">
        <div className="container-page pt-16 pb-4">
          <h1 className="font-display text-3xl text-green-900 mb-2">אודות גילוי נאות</h1>
        </div>

        <Section title="מה זה">
          <p>גילוי נאות הוא מאגר חופשי של החלטות ופסקי דין מבתי המשפט בישראל.</p>
          <p>
            אפשר לחפש בו לפי שם בעל דין, מספר תיק, שם שופט או מילים מתוך גוף
            פסק הדין — או פשוט לשאול שאלה בעברית ולקבל תשובה שמבוססת על
            פסקי הדין שבמאגר.
          </p>
          <p>אין מנוי, אין הרשמה, אין תשלום.</p>
        </Section>

        <Section title="למה">
          <p>
            פסקי דין הם מידע ציבורי. סעיף 6 לחוק זכות יוצרים קובע במפורש
            שאין בהם זכות יוצרים — הם שייכים לכולם. לכולנו.
          </p>
          <p>
            אבל מי שרוצה באמת לחפש בתוכם צריך מנוי למאגר מסחרי. בפסקי דין
            של בית המשפט העליון המצב יחסית סביר, אבל בפסקי דין של שאר בתי
            המשפט, פשוט אין אפשרות מעשית לחפש בהם.
          </p>
          <p>
            מבקר המדינה עמד על הפער הזה{" "}
            <a
              href="https://library.mevaker.gov.il/sites/DigitalLibrary/Pages/Reports/7413-17.aspx"
              target="_blank"
              rel="noopener noreferrer"
              className="text-green-700 underline hover:text-green-900"
            >
              בדוח משנת 2022
            </a>
            , והמליץ שהמידע בנט המשפט יונגש לציבור עם יכולות חיפוש, אחזור
            וייצוא - כך שכל אזרח יוכל להשתמש בו בלי להיות תלוי בתשלום מנוי
            לגורם מסחרי.
          </p>
          <p>האתר הזה הוא ניסיון לעשות את זה בפועל.</p>

          <div className="bg-green-700 text-white rounded-xl2 py-12 px-8 text-center mt-6">
            <div className="font-display text-4xl mb-4">4.5 מיליון ש&quot;ח</div>
            <p className="max-w-xl mx-auto text-green-50 text-sm leading-relaxed">
              הרשות השופטת שילמה בעצמה בשנים 2016–2019 לספק אחד כ-1.1 מיליון
              ש&quot;ח בממוצע לשנה, ולספק שני כ-200,000 ש&quot;ח בממוצע לשנה, עבור
              שירותי &quot;רכישת רישיונות גישה ומתן שירותי אחזור מידע במאגרי
              מידע משפטיים למשתמשי מערכת בתי המשפט&quot; - כלומר בארבע שנים
              שילמה הרשות השופטת מיליוני שקלים לגורמים מסחריים עבור גישה
              למידע שמגיע מהמערכות שלה עצמה.
            </p>
            <p className="text-xs text-green-200 mt-3">
              מקור: דו&quot;ח מבקר המדינה, 2022 (עמ&apos; 831)
            </p>
          </div>
        </Section>

        <Section title="מאיפה המידע">
          <p>
            המסמכים נאספים מהפרסומים באתר הרשות השופטת (נט המשפט) ובאתר
            בית המשפט העליון:
          </p>
          <ul className="list-disc pr-5 space-y-1">
            <li>
              <a
                href="https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx"
                target="_blank"
                rel="noopener noreferrer"
                className="text-green-700 underline hover:text-green-900"
              >
                אתר נט המשפט
              </a>
            </li>
            <li>
              <a
                href="https://supreme.court.gov.il/Pages/HomePage.aspx"
                target="_blank"
                rel="noopener noreferrer"
                className="text-green-700 underline hover:text-green-900"
              >
                אתר בית המשפט העליון
              </a>
            </li>
          </ul>
        </Section>

        <Section title="חיפוש ה-AI">
          <p>
            החיפוש החכם פועל באמצעות מודלי Claude של Anthropic: מודל קל
            ומהיר מנתח תחילה את השאלה כדי לאתר את פסקי הדין הרלוונטיים
            במאגר, ולאחר מכן מודל מתקדם יותר מנסח את התשובה עצמה - אך ורק
            על סמך פסקי הדין שאותרו לשאלה הספציפית, לא על סמך ידע כללי.
            כל תשובה מלווה ברשימת המקורות שעליהם היא מבוססת, כדי שתוכלו
            לבדוק אותם בעצמכם.
          </p>
        </Section>

        <Section title="מי עומד מאחורי זה">
          <p>
            אני עורך דין ודוקטורנט למשפטים. זה פרויקט אזרחי ללא מטרות
            רווח, בלי מימון ממשלתי ובלי מימון מסחרי. הוקם ומתוחזק
            בהתנדבות, פשוט כי המצב היום לא צודק, ויש AI שמאפשר לעשות הרבה
            דברים שפעם היו הרבה יותר מורכבים.
          </p>
        </Section>

        <Section id="coverage" title="מה יש במאגר, ומה אין בו">
          <p>מאגר משפטי שלא אומר לכם מה חסר בו הוא מאגר שאי אפשר לסמוך עליו. אז הנה, בגילוי נאות.</p>
          <p>
            <strong>מאיפה המידע מגיע:</strong> המידע מגיע מפרסומים של הרשות
            השופטת. הושקעו שעות רבות באיתור והורדת כל המסמכים שבאתר, אבל
            אפשר לומר בוודאות שישנם פסקי דין שלא מופיעים באתר - בגלל
            מגבלות מובנות באתר נט המשפט, שפשוט לא מאפשר להגיע לכל פסקי
            הדין הקיימים אם אתה לא יודע מראש מה מספר ההליך. אם אתם צריכים
            כיסוי של 100%, אולי יש במאגרי המידע שבתשלום - מוזמנים לבדוק.
          </p>
          <p>
            <strong>מה יש כאן:</strong> פסקי דין, גזרי דין והכרעות דין
            מכל הערכאות.
          </p>
          <p>
            <a href="/coverage" className="text-green-700 underline hover:text-green-900">
              נתוני כיסוי מלאים ומתעדכנים, כולל פילוח לפי בית משפט ולפי שנה ←
            </a>
          </p>
          <p>
            <strong>מה אין כאן:</strong>
          </p>
          <ul className="list-disc pr-5 space-y-1">
            <li>
              לא כל החלטות הביניים מכל ההליכים מופיעות עדיין באתר. מדובר
              בדרך כלל בהחלטות קצרות מאוד שעוסקות בניהול התיק. אנחנו
              עובדים על ההשלמה שלהן כך שגם הן תופענה לבסוף באתר.
            </li>
            <li>פרוטוקולים וכתבי טענות. הם לא מתפרסמים לציבור - רק פסקי דין והחלטות.</li>
            <li>ספרות משפטית.</li>
          </ul>
          <p className="font-medium">
            וחשוב מכל: העדר תוצאות בחיפוש אינו ראיה לכך שאין פסיקה בנושא.
            ייתכן שהיא קיימת ולא הגיעה אלינו, או שהיא קיימת והחיפוש לא
            מצא אותה.
          </p>
          <p>
            זה לא ייעוץ משפטי ולא תחליף לעורך דין. אנחנו מנגישים מסמכים
            כפי שהגיעו אלינו מהרשות השופטת. מנוע ה-AI מנסח תשובות על בסיס
            פסקי דין שאותרו במאגר, והוא עלול לטעות - הוא עשוי לסכם לא
            במדויק, לפספס פסיקה רלוונטית, או להציג טענה של צד לתיק כאילו
            הייתה קביעה של בית המשפט. לפני שאתם מסתמכים על משהו - פתחו את
            פסק הדין המקורי ותקראו.
          </p>
        </Section>

        <Section title="תקלות שאנחנו יודעים עליהן">
          <p>אנחנו מפרסמים את אלה כדי שתדעו מתי לא לסמוך עלינו:</p>
          <ul className="list-disc pr-5 space-y-1">
            <li>בחלק מהרשומות שדה שמות הצדדים ריק או מכיל ערך שגוי.</li>
            <li>תאריכים מוצגים במספר פורמטים שונים, ולפעמים שגויים.</li>
            <li>ספירת התוצאות בחיפוש מוגבלת ל-5,000. כשמוצג המספר הזה, המשמעות היא &quot;5,000 ומעלה&quot;.</li>
          </ul>
          <p>
            אנחנו עוקבים באופן צמוד אחר החלטות שקובעות צו איסור פרסום או
            חסיון, ומעדכנים מיד את המאגר בהתאם. אם אתם סבורים שמופיע
            במאגר פסק דין או החלטה שלא צריכים להופיע שם בגלל החלטה שיפוטית
            - עדכנו אותנו ונסיר בהקדם.
          </p>
        </Section>

        <Section title="מצאתם טעות?">
          <p>זה עוזר לנו יותר מכל דבר אחר. שלחו לנו את מספר התיק ומה לא נכון:</p>
          <p>
            <a href="mailto:support@giluy-naot.org.il" className="text-green-700 underline hover:text-green-900">
              support@giluy-naot.org.il
            </a>
          </p>
          <p>אנחנו מתקנים ומעדכנים.</p>
          <p>אתם סטודנטים, חוקרים, עיתונאים או מפתחים ורוצים גישה לנתונים הגולמיים? דברו איתנו.</p>
        </Section>

        <Section title="איך אפשר לעזור">
          <p>אם מצאתם טעות במאגר - נשמח שתפנו ותעדכנו.</p>
          <p>
            תחזוק האתר כרוך בעלויות, ואם יעמוד לרשותנו תקציב נוסף ניתן
            יהיה לשפר ולשכלל את האתר.{" "}
            <strong>נשמח לקבל חסות, תמיכה או סיוע - צרו קשר.</strong>
          </p>
          <p>אם אתם רוצים להציע שיתוף פעולה או שיש לכם רעיון מעניין - גם תפנו.</p>
          <p>
            יצירת קשר:{" "}
            <a href="mailto:support@giluy-naot.org.il" className="text-green-700 underline hover:text-green-900">
              support@giluy-naot.org.il
            </a>
          </p>
          <p className="text-muted text-xs pt-2">ועוד משהו - בבקשה אל תתבעו אותי.</p>
        </Section>
      </main>
      <Footer />
    </>
  );
}
