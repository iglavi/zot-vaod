"use client"

import { useState } from "react"
import { ChevronUp, Info } from "lucide-react"
import { VerdictCard } from "@/components/verdict-card"
import { VERDICTS, DEMO_ANSWER } from "@/lib/demo-data"
import { cn } from "@/lib/utils"

/** Renders **bold** segments without pulling in a markdown dependency. */
function RichText({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i} className="font-bold text-primary">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </>
  )
}

export function AnswerPanel({ question }: { question: string }) {
  const [sourcesOpen, setSourcesOpen] = useState(true)
  const sources = VERDICTS.filter((v) => DEMO_ANSWER.sourceIds.includes(v.id))

  return (
    <div className="fade-rise flex flex-col gap-6">
      {/* the question, echoed back as a chat bubble */}
      <div className="flex justify-start">
        <p className="max-w-2xl rounded-2xl bg-secondary/80 px-5 py-3.5 text-sm leading-relaxed text-secondary-foreground">
          {question}
        </p>
      </div>

      {/* the answer */}
      <div className="flex flex-col gap-4">
        {DEMO_ANSWER.paragraphs.map((p, i) => (
          <p key={i} className="text-[0.95rem] leading-relaxed text-foreground text-pretty">
            <RichText text={p} />
          </p>
        ))}
      </div>

      <p className="flex items-start gap-2 rounded-xl border border-border bg-muted/50 px-4 py-3 text-xs leading-relaxed text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        התשובה נוסחה אוטומטית על בסיס פסקי הדין המצוטטים למטה. היא אינה ייעוץ משפטי — מומלץ לקרוא את המקורות עצמם
        ולהיוועץ בעורך דין.
      </p>

      {/* cited sources */}
      <section className="border-t border-border pt-5">
        <button
          type="button"
          onClick={() => setSourcesOpen((v) => !v)}
          aria-expanded={sourcesOpen}
          aria-controls="cited-sources"
          className="flex w-full items-center justify-between gap-3 text-start"
        >
          <span className="flex items-center gap-2.5">
            <span className="flex size-6 items-center justify-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
              {sources.length}
            </span>
            <span className="text-base font-bold text-foreground">מקורות מצוטטים</span>
          </span>
          <ChevronUp
            className={cn("size-5 text-muted-foreground transition-transform", !sourcesOpen && "rotate-180")}
            aria-hidden="true"
          />
        </button>

        {sourcesOpen && (
          <div id="cited-sources" className="mt-4 flex flex-col gap-4">
            {sources.map((v) => (
              <VerdictCard key={v.id} verdict={v} compact />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
