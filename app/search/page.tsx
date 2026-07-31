import type { Metadata } from "next"
import { AdvancedSearch } from "@/components/advanced-search"

export const metadata: Metadata = {
  title: "חיפוש מתקדם",
  description: "חיפוש מובנה במאגר פסקי הדין לפי שופט, בית משפט, מספר תיק, סוג הליך וטווח תאריכים.",
}

export default function SearchPage() {
  return <AdvancedSearch />
}
