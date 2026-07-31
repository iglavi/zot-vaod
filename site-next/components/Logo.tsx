"use client";

/**
 * סמל "גילוי נאות" — גרסה וקטורית בהשראת שרטוט החותמת המקורי (טבעת כפולה
 * + טבעות פנימיות + פס אמצעי ריק), בגוון הירוק של עיצוב הפיגמה. props.spin
 * מפעיל סיבוב איטי — משמש בזמן טעינה/חיפוש.
 */
export function LogoIcon({ size = 40, spin = false, className = "" }:
  { size?: number; spin?: boolean; className?: string }) {
  const rings = [];
  for (let r = 10; r <= 82; r += 5.2) rings.push(r);
  return (
    <svg
      viewBox="0 0 200 200"
      width={size}
      height={size}
      className={`${spin ? "animate-spin-slow" : ""} ${className}`}
      aria-hidden="true"
    >
      <circle cx="100" cy="100" r="94" fill="none" stroke="#295C4C" strokeWidth="5" />
      <circle cx="100" cy="100" r="86" fill="none" stroke="#295C4C" strokeWidth="1.5" />
      {rings.map((r) => (
        <circle key={r} cx="100" cy="100" r={r} fill="none" stroke="#295C4C" strokeWidth="1.4" opacity={0.8} />
      ))}
      <rect x="4" y="84" width="192" height="32" fill="#FAF7F1" />
      <line x1="4" y1="84" x2="196" y2="84" stroke="#295C4C" strokeWidth="4" />
      <line x1="4" y1="116" x2="196" y2="116" stroke="#295C4C" strokeWidth="4" />
    </svg>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return <span className={`font-display text-2xl text-green-900 ${className}`}>גילוי נאות</span>;
}

export function Logo({ iconSize = 36 }: { iconSize?: number }) {
  return (
    <a href="/" className="flex items-center gap-2">
      <Wordmark />
      <LogoIcon size={iconSize} />
    </a>
  );
}
