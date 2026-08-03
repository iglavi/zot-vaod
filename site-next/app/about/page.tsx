import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

export const metadata = { title: "אודות — גילוי נאות" };

export default function AboutPage() {
  return (
    <>
      <Header active="/about" />
      <main id="main-content" className="container-page py-16">
        <h1 className="font-display text-3xl text-green-900 mb-4">למה צריך את זה?</h1>
        <p className="text-sm leading-relaxed text-ink/80 max-w-3xl">
          דו&quot;ח מבקר המדינה משנת 2022 קבע כי מומלץ שהמידע באתר נט-המשפט
          שמנהלת הרשות השופטת יונגש בכלים ואפשרויות חיפוש מתקדמים, תוך מתן
          אפשרות אחזור, ייצוא וניתוח מידע מתקדם, אשר יבטיחו לציבור גישה
          מלאה למידע המשפטי שאינו מסווג, כך שכל אזרח יוכל ליהנות מהמידע
          המצוי באתר, ללא תלות ברכישת תוכנה מגורמים מסחריים.{" "}
          <a
            href="https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2022/2022.3/2022.3-304-NET.pdf"
            target="_blank"
            rel="noopener noreferrer"
            className="text-green-700 underline hover:text-green-900"
          >
            לדוח המלא
          </a>
        </p>
      </main>
      <section className="container-page pb-16 grid md:grid-cols-2 gap-12">
        <div>
          <h2 className="text-xl font-semibold text-green-900 mb-2">מודל ה-AI</h2>
          <p className="text-sm text-ink/80 leading-relaxed">
            החיפוש החכם מבוסס על מודלי השפה של Anthropic (משפחת Claude).
            כשאתם שואלים שאלה בשפה חופשית, המערכת מאתרת תחילה את פסקי הדין
            הרלוונטיים ביותר במאגר, ורק לאחר מכן מבקשת מהמודל לנסח תשובה
            המתבססת על המקורות שנמצאו ומפנה למספרי התיקים - התשובה אינה
            ייעוץ משפטי, ותמיד כפופה למקורות המצוטטים.
          </p>
        </div>
        <div>
          <h2 className="text-xl font-semibold text-green-900 mb-2">מקור המסמכים</h2>
          <p className="text-sm text-ink/80 leading-relaxed">
            המאגר נבנה מהחלטות ופסקי דין המתפרסמים באתרי הרשות השופטת
            (נט-המשפט ומערכת NGCS) ובאתר בית המשפט העליון - אותו מידע ציבורי
            שאינו מסווג העומד ממילא לרשות כל אזרח, רק מרוכז כאן במקום אחד
            עם חיפוש נגיש וחינמי.
          </p>
        </div>
      </section>
      <section id="coverage" className="container-page pb-16 scroll-mt-24">
        <h2 className="text-xl font-semibold text-green-900 mb-2">היקף הכיסוי ומגבלותיו</h2>
        <p className="text-sm text-ink/80 leading-relaxed max-w-3xl">
          המאגר מתעדכן באופן שוטף ומורחב לאחור בהדרגה, אך הכיסוי אינו
          מלא: חלק מהחלטות ופסקי הדין כלל אינם מתפרסמים על ידי בתי המשפט
          עצמם (למשל בשל צווי איסור פרסום), וייתכנו טווחי תאריכים או
          ערכאות שהכיסוי לגביהם עדיין חלקי בזמן שהמאגר ממשיך להיבנות.
          המידע מבוסס על מה שפורסם בפועל באתרי הרשות השופטת ובית המשפט
          העליון - לא על מדגם מייצג סטטיסטית של כלל ההליכים המשפטיים
          בישראל.
        </p>
        <a href="/coverage" className="inline-block mt-3 text-sm text-green-700 underline hover:text-green-900">
          לנתוני כיסוי חיים ומספרים מלאים ←
        </a>
      </section>
      <section className="container-page pb-20">
        <div className="bg-green-700 text-white rounded-xl2 py-16 px-8 text-center">
          <div className="font-display text-5xl mb-4">4.2 מיליון ש&quot;ח</div>
          <p className="max-w-xl mx-auto text-green-50 text-sm leading-relaxed">
            הסכום ששילמה הרשות השופטת לגורמים מסחריים עבור גישה למידע
            שהיא עצמה מייצרת, בשנים 2016–2019
          </p>
          <p className="text-xs text-green-200 mt-3">
            מקור:{" "}
            <a
              href="https://library.mevaker.gov.il/sites/DigitalLibrary/Documents/2022/2022.3/2022.3-304-NET.pdf"
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-white"
            >
              דו&quot;ח מבקר המדינה, 2022
            </a>
          </p>
        </div>
      </section>
      <Footer />
    </>
  );
}
