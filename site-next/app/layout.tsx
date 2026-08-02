import type { Metadata } from "next";
import localFont from "next/font/local";
import { Rubik } from "next/font/google";
import "./globals.css";

const rubik = Rubik({
  subsets: ["hebrew", "latin"],
  weight: ["300", "400", "500", "600", "700"],
  variable: "--font-rubik",
  display: "swap",
});

const telaviv = localFont({
  src: "../public/fonts/telaviv-modernistbold.woff2",
  variable: "--font-telaviv",
  weight: "700",
  display: "swap",
});

const SITE_URL = "https://www.giluy-naot.org.il";
const TITLE = "גילוי נאות — פסקי הדין של ישראל, בחינם";
const DESCRIPTION =
  "גילוי נאות הוא מאגר מידע משפטי שמנגיש החלטות ופסקי דין מאתר הרשות השופטת. שאלו כל שאלה משפטית בשפה חופשית וקבלו תשובה.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  icons: { icon: "/logo-icon.png" },
  robots: { index: true, follow: true },
  openGraph: {
    type: "website",
    locale: "he_IL",
    url: SITE_URL,
    siteName: "גילוי נאות",
    title: TITLE,
    description: DESCRIPTION,
    images: [{ url: "/logo-icon.png" }],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl" className={`${rubik.variable} ${telaviv.variable}`}>
      <body className="bg-cream text-ink font-sans antialiased">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:right-2 focus:z-50 focus:bg-green-700 focus:text-white focus:rounded-lg focus:px-4 focus:py-2"
        >
          דלג לתוכן הראשי
        </a>
        {children}
      </body>
    </html>
  );
}
