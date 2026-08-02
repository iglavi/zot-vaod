import type { MetadataRoute } from "next";

const BASE_URL = "https://www.giluy-naot.org.il";
const ROUTES = ["", "/ai", "/search", "/about", "/privacy", "/terms"];

export default function sitemap(): MetadataRoute.Sitemap {
  return ROUTES.map((route) => ({
    url: `${BASE_URL}${route}`,
    lastModified: new Date(),
  }));
}
