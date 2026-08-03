import { Suspense } from "react";
import { AiChat } from "./AiChat";

export const metadata = { title: "חיפוש AI בפסקי דין — גילוי נאות" };

export default function AiPage() {
  return (
    <Suspense>
      <AiChat />
    </Suspense>
  );
}
