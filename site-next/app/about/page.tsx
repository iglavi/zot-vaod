import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

function Placeholder({ label }: { label: string }) {
  return (
    <div className="card border-dashed border-2 border-green-600/40 bg-green-100/40 h-64 flex items-center justify-center text-green-800 text-sm">
      {label}
    </div>
  );
}

export default function AboutPage() {
  return (
    <>
      <Header active="/about" />
      <main className="container-page py-16 grid md:grid-cols-2 gap-12 items-start">
        <Placeholder label="מקום לצילום מסך של אתר נט-המשפט (טרם סופק)" />
        <div>
          <h1 className="font-display text-3xl text-green-900 mb-4">למה צריך את זה?</h1>
          <p className="text-sm leading-relaxed text-ink/80">
            דו&quot;ח מבקר המדינה משנת 2022 קבע שממולץ כי המידע באתר נט-המשפט
            שמנהלת רשות השופטת יונגש בכלואי אפשרויות חיפוש תוך מתן אפשרות
            אחזור וייצוא אחזור וניתוח מידע מתקדם, אשר יבטיחו לציבור גישה
            מלאה למידע המשפטי שאינו מסווג, כך שכל אזרח יוכל ליהנות מהמידע
            המצוי באתר, ללא תלות ברכישת תוכנה מגורמים מסחריים.
          </p>
        </div>
      </main>
      <section className="container-page pb-16 grid md:grid-cols-2 gap-12">
        <div>
          <h2 className="text-xl font-semibold text-green-900 mb-2">מודל ה-AI</h2>
          <p className="text-sm text-muted italic">כאן יואל ישלים מידע.</p>
        </div>
        <div>
          <h2 className="text-xl font-semibold text-green-900 mb-2">מקור המסמכים</h2>
          <p className="text-sm text-muted italic">כאן יואל ישלים מידע.</p>
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
