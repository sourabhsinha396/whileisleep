import type { MetadataRoute } from "next";
import { headers } from "next/headers";
import { DOC_SLUGS } from "@/lib/docs";

/** The public pages, at the address this installation is reached under. */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const sent = await headers();
  const origin = `${sent.get("x-forwarded-proto") ?? "http"}://${sent.get("host")}`;
  return ["", "/pricing", "/docs", ...DOC_SLUGS.map((slug) => `/docs/${slug}`)].map((path) => ({ url: `${origin}${path}` }));
}
