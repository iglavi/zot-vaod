import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

export default function AboutPage() {
  return (
    <>
      <Header active="/about" />
      <main id="main-content" className="container-page py-16">
        <h1 className="font-display text-3xl text-green-900 mb-4">למה צריך את זה?</h1>
        <p className="text-sm leading-relaxed text-ink/80 max-w-3xl">
          דו&quot;ח מבקר המדינה משנת 2022 קבע שממולץ כי המידע באתר נט-המשפט
          שמנהלת רשות השופטת יונגש בכלואי אפשרויות חיפוש תוך מתן אפשרות
          אחזור וייצוא אחזור וניתוח מידע מתקדם, אשר יבטיחו לציבור גישה
          מלאה למידע המשפטי שאינו מסווג, כך שכל אזרח יוכל ליהנות מהמידע
          המצוי באתר, ללא תלות ברכישת תוכנה מגורמים מסחריים.
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
      <section className="container-page pb-20">
        <div className="bg-green-700 text-white rounded-xl2 py-16 px-8 text-center">
          <div className="font-display text-5xl mb-4">4.2 מיליון ש&quot;ח</div>
          <p className="max-w-xl mx-auto text-green-50 text-sm leading-relaxed">
            הסכום ששילמה הרשות השופטת בתי המשפט לגורמים מסחריים עבור גישה
            למידע שמעורכתיתה מעצמה בשנים 2016–2019
          </p>
          <p className="text-xs text-green-200 mt-3">מקור: דו&quot;ח מבקר המדינה, 2022</p>
        </div>
      </section>
      <Footer />
    </>
  );
}
