import type { Metadata } from "next"
import { ContactForm } from "@/components/contact-form"
import { PageShell } from "@/components/page-shell"

export const metadata: Metadata = {
  title: "צור קשר",
  description: "שאלות, הצעות לשיפור, דיווח על תקלה או על מסמך חסר במאגר גילוי נאות.",
}

export default function ContactPage() {
  return (
    <PageShell
      eyebrow="נשמח לשמוע"
      title="צור קשר"
      lead="מצאתם תקלה? חסר לכם מסמך? יש לכם רעיון שישפר את האתר? כתבו לנו — כל הודעה נקראת."
    >
      <ContactForm />
    </PageShell>
  )
}
