"use client";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { useEffect, useState } from "react";

type Coverage = {
  total: number;
  with_documents: number;
  by_year: { label: string; count: number }[];
  supreme: number;
  general: number;
};

export default function CoveragePage() {
  const [data, setData] = useState<Coverage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/coverage")
      .then((r) => r.json())
      .then((d) => (d.error ? setError(d.error) : setData(d)))
      .catch(() => setError("שגיאה בטעינת נתוני הכיסוי."));
  }, []);

  const maxYearCount = data ? Math.max(...data.by_year.map((y) => y.count), 1) : 1;

  return (
    <>
      <Header active="/coverage" />
      <main id="main-content" className="container-page py-16 max-w-3xl">
        <h1 className="font-display text-3xl text-green-900 mb-4">שקיפות המאגר</h1>
        <p className="text-sm text-ink/80 leading-relaxed mb-8">
          נתוני כיסוי חיים, מתעדכנים ישירות מהמאגר בכל טעינת העמוד - לא
          תמונת-מצב קבועה. ראו גם{" "}
          <a href="/about#coverage" className="text-green-700 underline hover:text-green-900">
            הצהרת המגבלות
          </a>{" "}
          בעמוד אודות.
        </p>

        {error && <p className="text-sm text-red-600">{error}</p>}
        {!data && !error && <p className="text-sm text-muted">טוען נתונים…</p>}

        {data && (
          <div className="space-y-8">
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="card p-5">
                <div className="text-xs text-muted mb-1">סה&quot;כ החלטות עם מסמך מלא</div>
                <div className="font-display text-3xl text-green-900">
                  {data.with_documents.toLocaleString("he")}
                </div>
              </div>
              <div className="card p-5">
                <div className="text-xs text-muted mb-1">מתוכן בבית המשפט העליון</div>
                <div className="font-display text-3xl text-green-900">
                  {data.supreme.toLocaleString("he")}
                </div>
              </div>
            </div>

            <div className="card p-5">
              <div className="text-sm font-medium text-green-900 mb-3">פילוח לפי תקופה</div>
              <div className="space-y-2">
                {data.by_year.map((y) => (
                  <div key={y.label} className="flex items-center gap-3">
                    <span className="text-xs text-muted w-24 shrink-0">{y.label}</span>
                    <div className="flex-1 bg-cream rounded-full h-4 overflow-hidden">
                      <div
                        className="bg-green-600 h-full rounded-full"
                        style={{ width: `${Math.max(2, (y.count / maxYearCount) * 100)}%` }}
                      />
                    </div>
                    <span className="text-xs text-ink/70 w-16 text-left">
                      {y.count.toLocaleString("he")}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div id="coverage" className="card p-5">
              <div className="text-sm font-medium text-green-900 mb-2">מה ידוע כחסר</div>
              <p className="text-sm text-ink/80 leading-relaxed">
                המאגר ממשיך להיבנות: חלק מטווחי התאריכים עדיין בהשלמה,
                חלק מההחלטות כלל אינן מתפרסמות על ידי בתי המשפט עצמם
                (למשל בשל צווי איסור פרסום), והכיסוי אינו מדגם מייצג
                סטטיסטית של כלל ההליכים המשפטיים בישראל - רק מה שפורסם
                בפועל באתרי הרשות השופטת ובית המשפט העליון.
              </p>
            </div>
          </div>
        )}
      </main>
      <Footer />
    </>
  );
}
