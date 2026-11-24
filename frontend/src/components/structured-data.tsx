import { jsonLd } from "@/lib/seo";

/** What a page is about, for search engines (schema.org). */
export function StructuredData({ data }: { data: object }) {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLd(data) }} />;
}
