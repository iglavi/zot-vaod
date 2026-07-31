"use client"

import { useEffect, useRef, useState } from "react"
import { Search, SlidersHorizontal } from "lucide-react"
import { Seal } from "@/components/seal"
import { VerdictCard } from "@/components/verdict-card"
import { COURTS, MATCH_TYPES, PROCEEDING_TYPES, VERDICTS } from "@/lib/demo-data"

type Phase = "idle" | "searching" | "results"

const DEMO_SEARCH_MS = 2200

export function AdvancedSearch() {
  const [phase, setPhase] = useState<Phase>("idle")
  const [sort, setSort] = useState("newest")
  const resultsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (phase !== "searching") return
    const t = setTimeout(() => setPhase("results"), DEMO_SEARCH_MS)
    return () => clearTimeout(t)
  }, [phase])

  useEffect(() => {
    if (phase === "results") resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
  }, [phase])

  const results = [...VERDICTS].sort((a, b) =>
    sort === "newest" ? b.date.localeCompare(a.date) : a.date.localeCompare(b.date),
  )

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-14">
      <h1 className="sr-only">חיפוש מתקדם במאגר פסקי הדין</h1>

      {/* filter card */}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          setPhase("searching")
        }}
        className="rounded-2xl border border-border bg-card p-5 shadow-sm sm:p-7"
      >
        <div className="flex items-center gap-2.5 border-b border-border pb-4">
          <SlidersHorizontal className="size-5 text-primary" aria-hidden="true" />
          <h2 className="text-lg font-bold text-foreground">סינון וחיפוש מובנה</h2>
        </div>

        <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="מספר תיק" id="case-number">
            <Input id="case-number" placeholder="למשל: 4934-07-24" />
          </Field>

          <Field label="שם צד שני" id="party-b">
            <Input id="party-b" placeholder="הקלידו שם של הצד שכנגד…" />
          </Field>

          <Field label="שם צד לתיק" id="party-a">
            <Input id="party-a" placeholder="הקלידו שם של בעל דין…" />
          </Field>

          <Field label="שם השופט/ת" id="judge">
            <Input id="judge" placeholder="למשל: רוני סלע" />
          </Field>

          <Field label="סוג הליך" id="proceeding">
            <Select id="proceeding" options={PROCEEDING_TYPES} placeholder="- הכול -" />
          </Field>

          <Field label="בית משפט" id="court">
            <Select id="court" options={COURTS} placeholder="- הכול -" />
          </Field>

          <Field label="סוג התאמה לחיפוש החופשי" id="match">
            <Select id="match" options={MATCH_TYPES} />
          </Field>

          <Field label="חיפוש חופשי בטקסט" id="fulltext">
            <Input id="fulltext" placeholder="מילים בגוף פסק הדין" />
          </Field>

          <Field label="מתאריך" id="from-date">
            <Input id="from-date" type="date" />
          </Field>

          <Field label="עד תאריך" id="to-date">
            <Input id="to-date" type="date" />
          </Field>

          <Field label="מיון" id="sort">
            <Select
              id="sort"
              value={sort}
              onChange={setSort}
              optionValues={[
                { value: "newest", label: "חדש ← ישן" },
                { value: "oldest", label: "ישן ← חדש" },
              ]}
            />
          </Field>
        </div>

        <button
          type="submit"
          disabled={phase === "searching"}
          className="mt-7 flex w-full items-center justify-center gap-2.5 rounded-xl bg-primary px-6 py-3.5 text-base font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-70"
        >
          {phase === "searching" ? (
            <>
              <Seal size={18} spinning />
              מחפש במאגר…
            </>
          ) : (
            <>
              <Search className="size-4" aria-hidden="true" />
              ביצוע חיפוש במאגר
            </>
          )}
        </button>
      </form>

      {/* results */}
      <div ref={resultsRef} className="scroll-mt-24">
        {phase === "searching" && (
          <p
            aria-live="polite"
            aria-busy="true"
            className="mt-10 flex items-center justify-center gap-3 text-sm text-muted-foreground"
          >
            <span className="text-primary">
              <Seal size={22} spinning />
            </span>
            מריץ את השאילתה על המאגר…
          </p>
        )}

        {phase === "results" && (
          <section className="fade-rise mt-10">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-bold text-foreground">
                {`נמצאו ${results.length} החלטות ופסקי דין`}
              </h2>
              <p className="text-sm text-muted-foreground">
                {`ממוין לפי: ${sort === "newest" ? "חדש ← ישן" : "ישן ← חדש"}`}
              </p>
            </div>

            <div className="mt-5 flex flex-col gap-4">
              {results.map((v) => (
                <VerdictCard key={v.id} verdict={v} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

/* ── small form primitives ─────────────────────────────────────────────── */

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-foreground">
        {label}
      </label>
      {children}
    </div>
  )
}

function Input({
  id,
  placeholder,
  type = "text",
}: {
  id: string
  placeholder?: string
  type?: string
}) {
  return (
    <input
      id={id}
      name={id}
      type={type}
      placeholder={placeholder}
      className="w-full rounded-lg border border-border bg-input px-3 py-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/20"
    />
  )
}

function Select({
  id,
  options,
  optionValues,
  placeholder,
  value,
  onChange,
}: {
  id: string
  options?: readonly string[]
  optionValues?: { value: string; label: string }[]
  placeholder?: string
  value?: string
  onChange?: (v: string) => void
}) {
  const items = optionValues ?? (options ?? []).map((o) => ({ value: o, label: o }))

  return (
    <select
      id={id}
      name={id}
      value={value}
      onChange={onChange ? (e) => onChange(e.target.value) : undefined}
      defaultValue={value === undefined ? "" : undefined}
      className="w-full appearance-none rounded-lg border border-border bg-input px-3 py-2.5 text-sm text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/20"
    >
      {placeholder && <option value="">{placeholder}</option>}
      {items.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}
