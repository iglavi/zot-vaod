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

export const metadata: Metadata = {
  title: "גילוי נאות — פסקי הדין של ישראל, בחינם",
  description:
    "גילוי נאות הוא מאגר מידע משפטי שמנגיש החלטות ופסקי דין מאתר הרשות השופטת. שאלו כל שאלה משפטית בשפה חופשית וקבלו תשובה.",
  icons: { icon: "/logo-icon.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="he" dir="rtl" className={`${rubik.variable} ${telaviv.variable}`}>
      <body className="bg-cream text-ink font-sans antialiased">{children}</body>
    </html>
  );
}
