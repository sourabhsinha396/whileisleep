import { markdownResponse, pageMarkdown } from "@/lib/doc-llm";
import { DOC_SLUGS, docPage } from "@/lib/docs";
import { siteOrigin } from "@/lib/origin";
import { REPO_URL } from "@/lib/pricing";

/** Every page of the docs in one file. */
export async function GET() {
  const origin = await siteOrigin();
  const pages = await Promise.all(DOC_SLUGS.map(docPage));
  return markdownResponse(pages.map((page) => pageMarkdown(page, origin, REPO_URL)).join("\n---\n\n"));
}
