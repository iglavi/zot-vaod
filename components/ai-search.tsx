"use client"

import Link from "next/link"
import { useEffect, useRef, useState } from "react"
import { Search, Sparkles } from "lucide-react"
import { ThinkingStages } from "@/components/thinking-stages"
import { AnswerPanel } from "@/components/answer-panel"
import { SAMPLE_QUESTIONS } from "@/lib/demo-data"

type Phase = "idle" | "thinking" | "answered"

/** How long the demo "search" takes. Replace with the real request. */
const DEMO_SEARCH_MS = 10500

export function AiSearch() {
  const [query, setQuery] = useState("")
  const [phase, setPhase] = useState<Phase>("idle")
  const [asked, setAsked] = useState("")
  const resultsRef = useRef<HTMLDivElement>(null)

  function submit(q: string) {
    const trimmed = q.trim()
    if (!trimmed || phase === "thinking") return
    setAsked(trimmed)
    setQuery(trimmed)
    setPhase("thinking")
  }

  // TODO: swap this timer for the real search request.
  useEffect(() => {
    if (phase !== "thinking") return
    const t = setTimeout(() => setPhase("answered"), DEMO_SEARCH_MS)
    return () => clearTimeout(t)
  }, [phase])

  useEffect(() => {
    if (phase !== "idle") resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
  }, [phase])

  return (
    <div className="flex flex-col">
      <section className="mx-auto flex w-full max-w-3xl flex-col items-center px-4 pt-14 text-center sm:px-6 sm:pt-20">
        <p className="rounded-full bg-secondary px-4 py-1.5 text-xs font-medium text-secondary-foreground">
          לא עוד תשלום מנוי כדי לקבל מידע ציבורי
        </p>

        <h1 className="mt-6 text-4xl font-extrabold leading-[1.15] tracking-tight text-primary text-balance sm:text-5xl md:text-6xl">
          פסקי הדין של ישראל,
          <br />
          בחינם.
        </h1>

        <p className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground text-pretty sm:text-lg">
          גילוי נאות הוא מאגר מידע משפטי שמנגיש החלטות ופסקי דין מבתי המשפט. שאלו כל שאלה בשפה חופשית — וקבלו תשובה
          מבוססת פסיקה.
        </p>

        {/* search box */}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            submit(query)
          }}
          className="mt-9 w-full"
        >
          <label htmlFor="ai-query" className="sr-only">
            שאלו שאלה משפטית בשפה חופשית
          </label>
          <div className="flex flex-col items-stretch gap-2 rounded-2xl border border-border bg-card p-2 shadow-sm transition-shadow focus-within:shadow-md sm:flex-row sm:items-center sm:rounded-full">
            <input
              id="ai-query"
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.nativeEvent.isComposing && e.keyCode !== 229) {
                  e.preventDefault()
                  submit(query)
                }
              }}
              placeholder="מהו פסק הדין העדכני ביותר של השופט כפכפי?"
              disabled={phase === "thinking"}
              className="min-w-0 flex-1 bg-transparent px-4 py-3 text-base text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-60 sm:py-2.5"
            />
            <button
              type="submit"
              disabled={phase === "thinking" || !query.trim()}
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50 sm:rounded-full sm:py-2.5"
            >
              <Search className="size-4" aria-hidden="true" />
              {phase === "thinking" ? "מחפש…" : "שאלו את ה-AI"}
            </button>
          </div>
        </form>

        <p className="mt-4 text-sm text-muted-foreground">
          {`רוצים לחפש לפי שם בעל דין, שם השופט או מספר הליך? `}
          <Link href="/search" className="font-medium text-accent underline underline-offset-4 hover:no-underline">
            מעבר לחיפוש מתקדם ומובנה
          </Link>
        </p>

        {/* sample questions */}
        {phase === "idle" && (
          <div className="mt-10 w-full">
            <p className="flex items-center justify-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              <Sparkles className="size-3.5" aria-hidden="true" />
              נסו לשאול
            </p>
            <ul className="mt-3 flex flex-wrap justify-center gap-2">
              {SAMPLE_QUESTIONS.map((q) => (
                <li key={q}>
                  <button
                    type="button"
                    onClick={() => submit(q)}
                    className="rounded-full border border-border bg-card px-4 py-2 text-start text-sm text-foreground transition-colors hover:border-primary/40 hover:bg-secondary"
                  >
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* results area */}
      <div ref={resultsRef} className="mx-auto w-full max-w-3xl scroll-mt-24 px-4 sm:px-6">
        {phase === "thinking" && <ThinkingStages className="mt-12" />}
        {phase === "answered" && (
          <div className="mt-12 rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
            <AnswerPanel question={asked} />
          </div>
        )}
      </div>
    </div>
  )
}
