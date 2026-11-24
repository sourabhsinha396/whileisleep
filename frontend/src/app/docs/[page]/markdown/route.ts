import { markdownResponse, pageMarkdown } from "@/lib/doc-llm";
import { DOC_SLUGS, docPage } from "@/lib/docs";
import { siteOrigin } from "@/lib/origin";
import { REPO_URL } from "@/lib/pricing";

/** /docs/<page>.md (next.config.ts sends it here). */
export async function GET(_request: Request, { params }: { params: Promise<{ page: string }> }) {
  const { page } = await params;
  if (!DOC_SLUGS.includes(page)) return new Response("Not found", { status: 404 });
  const origin = await siteOrigin();
  return markdownResponse(pageMarkdown(await docPage(page), origin, REPO_URL), "text/markdown");
}
