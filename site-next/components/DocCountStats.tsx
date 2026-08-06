"use client";
import { useEffect, useState } from "react";

type Stats = { with_documents: number; earliest_year: number | null };

// D3 (Tikunim.txt): שורת נתונים חיה מתחת לאזור הפתיחה בדף הבית - נשלפת
// מ-/api/coverage (אותו מקור שמזין את דף "שקיפות המאגר") כדי שהמספרים
// יישארו מדויקים ומתעדכנים, ולא יקפאו כטקסט קבוע בקוד.
export function DocCountStats() {
  const [data, setData] = useState<Stats | null>(null);

  useEffect(() => {
    fetch("/api/coverage")
      .then((r) => r.json())
      .then((d) => (d && !d.error ? setData(d) : null))
      .catch(() => {});
  }, []);

  const docsLabel = data
    ? `${(data.with_documents / 1_000_000).toLocaleString("he", { maximumFractionDigits: 1 })} מיליון`
    : "3.7 מיליון";
  const fromYear = data?.earliest_year ?? 1997;

  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-xs text-muted mt-4">
      <span>{docsLabel} מסמכים</span>
      <span aria-hidden="true">·</span>
      <span>{`מ-${fromYear} ועד היום`}</span>
      <span aria-hidden="true">·</span>
      <span>מתעדכן מדי יום</span>
    </div>
  );
}
