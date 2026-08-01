"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";

export function HeroSearchBar() {
  const [q, setQ] = useState("");
  const router = useRouter();
  function submit() {
    if (!q.trim()) return;
    router.push(`/ai?q=${encodeURIComponent(q.trim())}`);
  }
  return (
    <div className="w-full max-w-[820px] mx-auto">
      <div className="card flex items-center gap-3 p-2 pr-3">
        <button onClick={submit} className="btn-primary flex items-center gap-2 shrink-0">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          שאלו את ה-AI
        </button>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="מהו פסק הדין העדכני ביותר של השופט כפכפי?"
          className="flex-1 bg-transparent outline-none text-sm py-2"
        />
      </div>
      <div className="text-center mt-3 text-sm text-muted">
        <a href="/search" className="text-green-700 underline hover:text-green-900">
          מעבר לחיפוש מתקדם ומובנה
        </a>
        {" — "}רוצים לחפש לפי שם בעל דין, שם השופט או מספר הליך?
      </div>
    </div>
  );
}
