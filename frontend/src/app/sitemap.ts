import type { MetadataRoute } from "next";
import { DOC_SLUGS } from "@/lib/docs";
import { siteOrigin } from "@/lib/origin";

/** The public pages, at the address this installation is reached under. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const origin = await siteOrigin();
  return ["", "/pricing", "/docs", ...DOC_SLUGS.map((slug) => `/docs/${slug}`)].map((path) => ({ url: `${origin}${path}` }));
}
