import type { ReactNode } from "react"

export function PageShell({
  eyebrow,
  title,
  lead,
  children,
}: {
  eyebrow?: string
  title: string
  lead?: string
  children: ReactNode
}) {
  return (
    <main className="mx-auto max-w-3xl px-4 py-14 sm:px-6 sm:py-20">
      <header>
        {eyebrow && (
          <p className="text-sm font-semibold uppercase tracking-wide text-accent">{eyebrow}</p>
        )}
        <h1 className="mt-2 text-balance text-3xl font-extrabold tracking-tight text-primary sm:text-4xl">
          {title}
        </h1>
        {lead && <p className="mt-4 text-pretty text-lg leading-relaxed text-muted-foreground">{lead}</p>}
      </header>

      <div className="mt-10 flex flex-col gap-6">{children}</div>
    </main>
  )
}

export function Prose({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-4 text-base leading-relaxed text-foreground">{children}</div>
}
