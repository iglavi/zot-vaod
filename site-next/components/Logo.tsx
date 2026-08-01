"use client";

/**
 * סמל "גילוי נאות" - הנכס המקורי מפיגמה (חותמת מעוצבת), לא שחזור ידני.
 */
export function LogoIcon({ size = 40, spin = false, className = "" }:
  { size?: number; spin?: boolean; className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/logo-icon.png"
      alt=""
      width={size}
      height={size * (44 / 40)}
      className={`${spin ? "animate-spin-slow" : ""} ${className}`}
      style={{ width: size, height: "auto" }}
      aria-hidden="true"
    />
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
