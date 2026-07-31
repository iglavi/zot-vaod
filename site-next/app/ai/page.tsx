import { Suspense } from "react";
import { AiChat } from "./AiChat";

export default function AiPage() {
  return (
    <Suspense>
      <AiChat />
    </Suspense>
  );
}
