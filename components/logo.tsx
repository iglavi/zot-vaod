import Link from "next/link"
import { Seal } from "@/components/seal"
import { cn } from "@/lib/utils"

export function Logo({ className }: { className?: string }) {
  return (
    <Link
      href="/"
      aria-label="גילוי נאות — לעמוד הבית"
      className={cn(
        "group flex items-center gap-2.5 text-primary transition-opacity hover:opacity-80",
        className,
      )}
    >
      <Seal size={30} />
      <span className="text-xl font-extrabold tracking-tight">גילוי נאות</span>
    </Link>
  )
}
