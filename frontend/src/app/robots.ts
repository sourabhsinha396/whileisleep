import type { MetadataRoute } from "next";
import { siteOrigin } from "@/lib/origin";

/** The dashboard isn't listed: it says "noindex" itself (next.config.ts), which a crawler must be able to read. */
export default async function robots(): Promise<MetadataRoute.Robots> {
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/admin/", "/api/"] },
    sitemap: `${await siteOrigin()}/sitemap.xml`,
  };
}
