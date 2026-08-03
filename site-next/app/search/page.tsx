import { Suspense } from "react";
import SearchPage from "./SearchPage";

export const metadata = { title: "חיפוש מובנה — גילוי נאות" };

export default function Page() {
  return (
    <Suspense>
      <SearchPage />
    </Suspense>
  );
}
