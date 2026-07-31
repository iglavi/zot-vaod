"use client";
import { LogoIcon } from "./Logo";

export const STEP_LABELS: Record<string, string> = {
  received: "קיבלתי את הבקשה…",
  analyzing: "מנתח את השאלה ומאתר מושגי מפתח…",
  retrieving: "מחפש פסיקה רלוונטית במאגר…",
  answering: "מנסח תשובה…",
};

export function ThinkingSteps({ step }: { step: string | null }) {
  if (!step) return null;
  const order = ["received", "analyzing", "retrieving", "answering"];
  const idx = Math.max(0, order.indexOf(step));
  return (
    <div className="card flex items-center gap-4 px-5 py-4 max-w-md">
      <LogoIcon size={34} spin />
      <div className="text-sm">
        <div className="font-medium text-green-900">{STEP_LABELS[step] ?? step}</div>
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
