import { Wordmark, LogoIcon } from "./Logo";

export function Footer() {
  return (
    <footer className="border-t border-border mt-24">
      <div className="container-page py-14 grid gap-10 md:grid-cols-2">
        <p className="text-sm text-muted leading-relaxed max-w-md">
          המידע המוצג באתר אינו מהווה ייעוץ משפטי או תחליף לייעוץ כזה. כל שימוש
          במידע ובשירותי האתר הינו באחריות המשתמש בלבד.
        </p>
        <div className="md:text-left">
          <div className="flex md:justify-end items-center gap-2 mb-4">
            <Wordmark />
            <LogoIcon size={26} />
          </div>
          <div className="flex md:justify-end flex-wrap gap-x-6 gap-y-2 text-sm text-ink/70">
            <a href="#" className="hover:text-green-800">תרומות לתמיכה</a>
            <a href="#" className="hover:text-green-800">הצהרת נגישות</a>
            <a href="/coverage" className="hover:text-green-800">שקיפות המאגר</a>
            <a href="/privacy" className="hover:text-green-800">מדיניות פרטיות</a>
            <a href="/terms" className="hover:text-green-800">תנאי שימוש</a>
          </div>
        </div>
      </div>
      <div className="container-page pb-8 text-xs text-muted">
        © 2026 גילוי נאות — פרויקט אזרחי ללא מטרות רווח. כל הזכויות שמורות.
      </div>
    </footer>
  );
}
