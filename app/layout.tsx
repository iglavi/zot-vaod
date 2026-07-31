import type { Metadata, Viewport } from "next"
import { Heebo } from "next/font/google"
import { SiteHeader } from "@/components/site-header"
import { SiteFooter } from "@/components/site-footer"
import "./globals.css"

const heebo = Heebo({
  subsets: ["hebrew", "latin"],
  weight: ["300", "400", "500", "700", "800", "900"],
  variable: "--font-heebo",
  display: "swap",
})

export const metadata: Metadata = {
  title: {
    default: "גילוי נאות — פסקי הדין של ישראל, בחינם",
    template: "%s | גילוי נאות",
  },
  description:
    "גילוי נאות הוא מאגר מידע משפטי חופשי שמנגיש החלטות ופסקי דין מבתי המשפט בישראל. שאלו כל שאלה משפטית בשפה חופשית וקבלו תשובה מבוססת פסיקה.",
  keywords: ["פסקי דין", "מאגר משפטי", "פסיקה", "בתי משפט", "חיפוש משפטי", "גילוי נאות"],
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
    shortcut: "/icon.svg",
    apple: "/icon.svg",
  },
  openGraph: {
    title: "גילוי נאות — פסקי הדין של ישראל, בחינם",
    description: "מאגר מידע משפטי חופשי שמנגיש החלטות ופסקי דין מבתי המשפט בישראל.",
    locale: "he_IL",
    type: "website",
  },
}

export const viewport: Viewport = {
  themeColor: "#2d4f43",
  width: "device-width",
  initialScale: 1,
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl" className={`${heebo.variable} bg-background`}>
      <body className="flex min-h-dvh flex-col font-sans antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:right-3 focus:z-[100] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
        >
          דילוג לתוכן הראשי
        </a>
        <SiteHeader />
        <main id="main" className="flex-1">
          {children}
        </main>
        <SiteFooter />
      </body>
    </html>
  )
}
