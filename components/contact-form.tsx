"use client"

import { useState } from "react"
import { CheckCircle2, Send } from "lucide-react"

const TOPICS = ["שאלה כללית", "דיווח על תקלה", "מסמך חסר במאגר", "הצעה לשיפור", "פנייה עיתונאית"]

const fieldClass =
  "w-full rounded-lg border border-input bg-background px-3.5 py-2.5 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/70 focus:border-ring focus:ring-2 focus:ring-ring/25"

export function ContactForm() {
  const [sent, setSent] = useState(false)

  if (sent) {
    return (
      <div
        role="status"
        className="flex flex-col items-center gap-3 rounded-2xl border border-border bg-card px-6 py-14 text-center"
      >
        <CheckCircle2 className="size-10 text-accent" aria-hidden="true" />
        <h2 className="text-xl font-bold text-primary">ההודעה נשלחה</h2>
        <p className="max-w-sm text-sm leading-relaxed text-muted-foreground">
          תודה שפניתם. נחזור אליכם בהקדם לכתובת שהשארתם.
        </p>
        <button
          type="button"
          onClick={() => setSent(false)}
          className="mt-2 text-sm font-semibold text-accent underline underline-offset-4 hover:no-underline"
        >
          שליחת הודעה נוספת
        </button>
      </div>
    )
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        setSent(true)
      }}
      className="flex flex-col gap-5 rounded-2xl border border-border bg-card p-6 sm:p-8"
    >
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="contact-name" className="text-sm font-medium text-foreground">
            שם
          </label>
          <input id="contact-name" name="name" required autoComplete="name" className={fieldClass} />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="contact-email" className="text-sm font-medium text-foreground">
            דוא״ל
          </label>
          <input
            id="contact-email"
            name="email"
            type="email"
            required
            autoComplete="email"
            dir="ltr"
            className={`${fieldClass} text-right`}
          />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="contact-topic" className="text-sm font-medium text-foreground">
          נושא הפנייה
        </label>
        <select id="contact-topic" name="topic" defaultValue={TOPICS[0]} className={fieldClass}>
          {TOPICS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="contact-message" className="text-sm font-medium text-foreground">
          ההודעה
        </label>
        <textarea id="contact-message" name="message" required rows={6} className={`${fieldClass} resize-y`} />
      </div>

      <p className="text-xs leading-relaxed text-muted-foreground">
        אנא הימנעו משליחת פרטים אישיים רגישים או מסמכים חסויים. הפנייה אינה מהווה בקשה לייעוץ משפטי ואינה יוצרת יחסי
        עורך דין–לקוח.
      </p>

      <button
        type="submit"
        className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
      >
        <Send className="size-4" aria-hidden="true" />
        שליחת ההודעה
      </button>
    </form>
  )
}
