"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { EXAMPLE_QUESTIONS } from "@/lib/exampleQuestions";

// אנימציית הקלדה שמחזירה מחרוזת-ה-placeholder הנוכחית: מקלידה כל שאלה
// תו-אחר-תו, משהה, מוחקת תו-אחר-תו, ועוברת לשאלה הבאה (בלולאה) - ראו
// Tikunim.txt סעיף 5. מיושם כ-hook קטן ומקומי (לא placeholder קבוע) כדי
// שלא יידרש state/effect כפול בכל מקום שמשתמש ברשימת השאלות.
function useTypingPlaceholder(questions: string[]) {
  const [text, setText] = useState("");
  useEffect(() => {
    if (questions.length === 0) return;
    let qIndex = 0;
    let charIndex = 0;
    let deleting = false;
    let timer: ReturnType<typeof setTimeout>;

    function tick() {
      const current = questions[qIndex];
      if (!deleting) {
        charIndex++;
        setText(current.slice(0, charIndex));
        if (charIndex === current.length) {
          deleting = true;
          timer = setTimeout(tick, 1800); // השהיה על שאלה שלמה לפני המחיקה
          return;
        }
        timer = setTimeout(tick, 45);
      } else {
        charIndex--;
        setText(current.slice(0, charIndex));
        if (charIndex === 0) {
          deleting = false;
          qIndex = (qIndex + 1) % questions.length;
          timer = setTimeout(tick, 300);
          return;
        }
        timer = setTimeout(tick, 20);
      }
    }
    timer = setTimeout(tick, 45);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return text;
}

export function HeroSearchBar() {
  const [q, setQ] = useState("");
  const router = useRouter();
  const typedPlaceholder = useTypingPlaceholder(EXAMPLE_QUESTIONS);

  function submit() {
    if (!q.trim()) return;
    router.push(`/ai?q=${encodeURIComponent(q.trim())}`);
  }

  return (
    <div className="w-full max-w-[820px] mx-auto">
      <form
        onSubmit={(e) => { e.preventDefault(); submit(); }}
        className="card flex items-center gap-3 p-2 pr-3"
      >
        <label htmlFor="hero-question" className="sr-only">השאלה שלכם</label>
        <input
          id="hero-question"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={typedPlaceholder}
          className="flex-1 bg-transparent outline-none focus-visible:ring-2 focus-visible:ring-green-500/40 rounded-md text-base py-2"
        />
        <button type="submit" className="btn-primary flex items-center gap-2 shrink-0">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          שאלו
        </button>
      </form>
      <div className="card mt-3 flex flex-col sm:flex-row items-center justify-center gap-3 p-4 text-center">
        <p className="text-sm text-ink/80">
          יודעים מה אתם מחפשים? עברו לחיפוש מובנה — לפי שם בעל דין, מספר תיק או שופט
        </p>
        <a href="/search" className="btn-outline shrink-0">חיפוש מובנה</a>
      </div>
    </div>
  );
}
