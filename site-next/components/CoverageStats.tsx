"use client";
import { useEffect, useState } from "react";

type Coverage = {
  total: number;
  with_documents: number;
  by_year: { label: string; count: number }[];
  supreme: number;
  general: number;
};

// מוטמע ישירות בעמוד אודות (במקום עמוד /coverage נפרד, שנמחק) - נשלף
// חי מ-/api/coverage בכל טעינת עמוד, כך שהנתונים תמיד עדכניים ולא
// תמונת-מצב קפואה בקוד.
export function CoverageStats() {
  const [data, setData] = useState<Coverage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/coverage")
      .then((r) => r.json())
      .then((d) => (d.error ? setError(d.error) : setData(d)))
      .catch(() => setError("שגיאה בטעינת נתוני הכיסוי."));
  }, []);

  const maxYearCount = data ? Math.max(...data.by_year.map((y) => y.count), 1) : 1;

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!data) return <p className="text-sm text-muted">טוען נתונים…</p>;

  return (
    <div className="space-y-6 not-prose">
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
    </div>
  );
}
