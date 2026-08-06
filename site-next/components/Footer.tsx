import { Wordmark, LogoIcon } from "./Logo";

export function Footer() {
  return (
    <footer className="border-t border-border mt-12">
      <div className="container-page py-14 grid gap-10 md:grid-cols-2">
        <div className="text-sm text-muted leading-relaxed max-w-md space-y-1">
          <p>המידע המוצג באתר אינו מהווה ייעוץ משפטי או תחליף לייעוץ כזה.</p>
          <p>כל שימוש במידע ובשירותי האתר הינו באחריות המשתמש בלבד.</p>
        </div>
        <div className="md:text-left">
          <div className="flex md:justify-end flex-wrap gap-x-6 gap-y-2 text-sm text-ink/70 mb-4">
            <a href="/terms" className="hover:text-green-800 inline-flex items-center min-h-[44px]">תנאי שימוש</a>
            <a href="/privacy" className="hover:text-green-800 inline-flex items-center min-h-[44px]">מדיניות פרטיות</a>
            <a href="/accessibility" className="hover:text-green-800 inline-flex items-center min-h-[44px]">הצהרת נגישות</a>
          </div>
          <div className="flex md:justify-end items-center gap-2">
            <LogoIcon size={26} />
            <Wordmark />
          </div>
        </div>
      </div>
    </footer>
  );
}
