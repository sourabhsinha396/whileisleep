import type { MetadataRoute } from "next";
import { DOC_SLUGS } from "@/lib/docs";
import { operator } from "@/lib/operator";
import { siteOrigin } from "@/lib/origin";
import { sitePages } from "@/lib/site-pages";

/** The public pages, at the address this installation is reached under. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const origin = await siteOrigin();
  return ["", "/pricing", ...sitePages(operator()).map(({ slug }) => `/${slug}`), "/docs", ...DOC_SLUGS.map((slug) => `/docs/${slug}`)].map((path) => ({ url: `${origin}${path}` }));
}
