import Link from "next/link";
import { Logo } from "./Logo";

const NAV = [
  { href: "/", label: "בית" },
  { href: "/ai", label: "חיפוש AI" },
  { href: "/search", label: "חיפוש מתקדם" },
  { href: "/about", label: "אודות היוזמה" },
];

export function Header({ active = "/" }: { active?: string }) {
  return (
    <header className="border-b border-border bg-cream/95 backdrop-blur sticky top-0 z-30">
      <div className="container-page h-[76px] flex items-center justify-between">
        <Logo iconSize={34} />
        <nav className="flex items-center gap-2 text-sm">
          {NAV.map((item) => {
            const isActive = item.href === active;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  isActive
                    ? "bg-green-700 text-white rounded-lg px-4 py-2 font-medium"
                    : "text-ink/80 hover:text-green-800 px-3 py-2 font-medium"
                }
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
