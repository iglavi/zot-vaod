import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { HeroSearchBar } from "@/components/HeroSearchBar";

export default function HomePage() {
  return (
    <>
      <Header active="/" />
      <main>
        <section className="container-page pt-24 pb-16 text-center">
          <span className="inline-block bg-green-100 text-green-800 text-xs font-medium rounded-full px-4 py-1.5 mb-6">
            לא עוד תשלום מנוי כדי לקבל מידע ציבורי
          </span>
          <h1 className="font-display text-4xl md:text-6xl text-green-900 leading-[1.15] max-w-4xl mx-auto">
            פסקי הדין של ישראל, בחינם
          </h1>
          <p className="text-muted max-w-2xl mx-auto mt-6 mb-10 leading-relaxed">
            גילוי נאות הוא מאגר מידע משפטי שמנגיש החלטות ופסקי דין מאתר הרשות
            השופטת. שאלו כל שאלה משפטית בשפה חופשית וקבלו תשובה.
          </p>
          <HeroSearchBar />
        </section>
      </main>
      <Footer />
    </>
  );
}
