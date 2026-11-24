import type { Metadata } from "next";
import { siteOrigin } from "./origin";

export const SITE_NAME = "whileisleep";

/** What search engines and link previews show for a public page. The title gets the site's name after it. */
export async function publicMetadata({
  title,
  description,
  path,
  absoluteTitle = false,
  markdown,
}: {
  title: string;
  description: string;
  path: string;
  /** The title already has the site's name. */
  absoluteTitle?: boolean;
  /** Where the page is as Markdown. */
  markdown?: string;
}): Promise<Metadata> {
  const origin = await siteOrigin();
  const url = `${origin}${path}`;
  const image = { url: `${origin}/og.png`, width: 1200, height: 630, alt: "whileisleep: AI answers, while you sleep" };
  return {
    title: absoluteTitle ? { absolute: title } : title,
    description,
    alternates: { canonical: url, ...(markdown ? { types: { "text/markdown": `${origin}${markdown}` } } : {}) },
    openGraph: { type: "website", siteName: SITE_NAME, locale: "en_US", title, description, url, images: [image] },
    twitter: { card: "summary_large_image", title, description, images: [image.url] },
  };
}

/** The software, for the homepage. */
export function softwareData(description: string, origin: string) {
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: SITE_NAME,
    description,
    url: origin,
    image: `${origin}/og.png`,
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
  };
}

/** Where a page of the docs stands: Docs, then the page. */
export function breadcrumbData(title: string, slug: string, origin: string) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Docs", item: `${origin}/docs` },
      { "@type": "ListItem", position: 2, name: title, item: `${origin}/docs/${slug}` },
    ],
  };
}

/** JSON that can't end the script tag it is in. */
export function jsonLd(data: object): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}
