import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { HeroSearchBar } from "@/components/HeroSearchBar";
import { DocCountStats } from "@/components/DocCountStats";

export default function HomePage() {
  return (
    <>
      <Header active="/" />
      <main id="main-content">
        <section className="container-page pt-12 pb-4 text-center">
          <h1 className="font-display text-4xl md:text-6xl text-green-900 leading-[1.15] max-w-4xl mx-auto">
            פסקי הדין של ישראל, בחינם
          </h1>
          <p className="text-muted max-w-2xl mx-auto mt-5 mb-8 leading-relaxed">
            גילוי נאות הוא מאגר המידע המשפטי היחיד שמנגיש החלטות ופסקי דין
            ללא תשלום וללא הרשמה.
            <br />
            שאלו כל שאלה משפטית בשפה חופשית וקבלו תשובה.
          </p>
          <HeroSearchBar />
          <DocCountStats />
        </section>
      </main>
      <Footer />
    </>
  );
}
