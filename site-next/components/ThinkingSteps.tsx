"use client";
import { LogoIcon } from "./Logo";

export const STEP_LABELS: Record<string, string> = {
  received: "קיבלתי את הבקשה…",
  analyzing: "מנתח את השאלה ומאתר מושגי מפתח…",
  retrieving: "מחפש פסיקה רלוונטית במאגר…",
  answering: "מנסח תשובה…",
};

const DEFAULT_ORDER = ["received", "analyzing", "retrieving", "answering"];

export function ThinkingSteps({
  step,
  labels = STEP_LABELS,
  order = DEFAULT_ORDER,
}: {
  step: string | null;
  labels?: Record<string, string>;
  order?: string[];
}) {
  if (!step) return null;
  const idx = Math.max(0, order.indexOf(step));
  return (
    <div className="card flex items-center gap-4 px-5 py-4 max-w-md">
      <LogoIcon size={34} spin />
      <div className="text-sm">
        <div className="font-medium text-green-900">{labels[step] ?? step}</div>
        <div className="flex gap-1.5 mt-2">
          {order.map((s, i) => (
            <span
              key={s}
              className={`h-1.5 w-6 rounded-full ${i <= idx ? "bg-green-600" : "bg-border"}`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
