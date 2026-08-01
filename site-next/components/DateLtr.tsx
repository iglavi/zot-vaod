/** מציג תאריך משמאל לימין בפורמט D.M.YYYY, גם בתוך עמוד RTL. מקבל תאריך
 * בפורמט YYYY-MM-DD (כפי שמגיע מהמסד) ומחזיר "23.5.2025". */
export function formatDateDMY(iso?: string | null): string {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(iso);
  if (!m) return iso;
  const [, y, mo, d] = m;
  return `${parseInt(d, 10)}.${parseInt(mo, 10)}.${y}`;
}

export function DateLtr({ value }: { value?: string | null }) {
  const formatted = formatDateDMY(value);
  if (!formatted) return null;
  return (
    <span dir="ltr" style={{ unicodeBidi: "isolate" }}>
      {formatted}
    </span>
  );
}
