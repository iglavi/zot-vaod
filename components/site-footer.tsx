import Link from "next/link"
import { Seal } from "@/components/seal"

const LINKS = [
  { href: "/about", label: "אודות היוזמה" },
  { href: "/accessibility", label: "הצהרת נגישות" },
  { href: "/privacy", label: "מדיניות פרטיות" },
  { href: "/terms", label: "תנאי שימוש" },
]

export function SiteFooter() {
  return (
    <footer className="mt-20 border-t border-border bg-muted/40">
      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6">
        <div className="flex flex-col gap-8 md:flex-row md:items-start md:justify-between">
          <div className="max-w-xs">
            <div className="flex items-center gap-2.5 text-primary">
              <Seal size={26} />
              <span className="text-lg font-extrabold tracking-tight">גילוי נאות</span>
            </div>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              נגישות חופשית לפסיקה ולהחלטות של בתי המשפט בישראל — בלי תשלום ובלי מנוי.
            </p>
          </div>

          <nav aria-label="ניווט תחתון">
            <ul className="flex flex-wrap gap-x-6 gap-y-3">
              {LINKS.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="text-sm text-muted-foreground transition-colors hover:text-primary">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </div>

        <div className="mt-10 border-t border-border pt-6">
          <p className="text-xs leading-relaxed text-muted-foreground">
            המידע המוצג באתר אינו מהווה ייעוץ משפטי ואין להסתמך עליו כתחליף לייעוץ מקצועי. כל שימוש במידע ובשירותי האתר
            הינו באחריות המשתמש בלבד.
          </p>
          <p className="mt-3 text-xs text-muted-foreground">
            {`\u00A9 ${new Date().getFullYear()} גילוי נאות — פרויקט אזרחי ללא מטרות רווח.`}
          </p>
        </div>
      </div>
    </footer>
  )
}
