"use client"

import { useEffect, useState } from "react"
import { Check } from "lucide-react"
import { Seal } from "@/components/seal"
import { cn } from "@/lib/utils"

export const THINKING_STAGES = [
  { label: "קיבלתי את הבקשה", hint: "מנתח את השאלה שלך" },
  { label: "מאתר מושגי מפתח", hint: "מזהה את הסוגיה המשפטית והמונחים הרלוונטיים" },
  { label: "מחפש פסיקה רלוונטית", hint: "סורק את המאגר אחר החלטות ופסקי דין" },
  { label: "קורא את פסקי הדין", hint: "מאתר את הקטעים שעונים על השאלה" },
  { label: "מנסח תשובה", hint: "מסכם ומצרף הפניות למקורות" },
] as const

/** ms spent on each stage before advancing (the last one holds until results arrive) */
const STAGE_MS = [900, 1600, 2600, 2400, 3000]

export function ThinkingStages({ className }: { className?: string }) {
  const [active, setActive] = useState(0)

  useEffect(() => {
    if (active >= THINKING_STAGES.length - 1) return
    const t = setTimeout(() => setActive((i) => i + 1), STAGE_MS[active])
    return () => clearTimeout(t)
  }, [active])

  return (
    <section
      aria-live="polite"
      aria-busy="true"
      aria-label="מתבצע חיפוש"
      className={cn(
        "rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8",
        className,
      )}
    >
      <div className="flex items-center gap-4">
        <span className="relative flex size-12 items-center justify-center text-primary">
          <Seal size={48} spinning />
        </span>
        <div>
          <p className="text-base font-bold text-primary">מחפש עבורך במאגר…</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            החיפוש עשוי להימשך מספר שניות. אין צורך לרענן את הדף.
          </p>
        </div>
      </div>

      <ol className="mt-6 flex flex-col gap-1">
        {THINKING_STAGES.map((stage, i) => {
          const done = i < active
          const current = i === active
          const pending = i > active

          return (
            <li
              key={stage.label}
              className={cn(
                "flex items-start gap-3 rounded-xl px-3 py-2.5 transition-colors",
                current && "bg-secondary/70",
                pending && "opacity-40",
              )}
            >
              <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center">
                {done ? (
                  <Check className="size-4 text-primary" aria-hidden="true" />
                ) : current ? (
                  <span className="seal-pulse size-2.5 rounded-full bg-primary" aria-hidden="true" />
                ) : (
                  <span className="size-2.5 rounded-full border border-muted-foreground/50" aria-hidden="true" />
                )}
              </span>

              <span className="flex flex-col">
                <span
                  className={cn(
                    "text-sm leading-6",
                    current ? "font-bold text-primary" : done ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {stage.label}
                </span>
                {current && <span className="text-xs leading-5 text-muted-foreground">{stage.hint}</span>}
              </span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
