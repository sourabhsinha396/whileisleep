import { llmsIndex, markdownResponse } from "@/lib/doc-llm";
import { docSections } from "@/lib/docs";
import { siteOrigin } from "@/lib/origin";

export async function GET() {
  return markdownResponse(llmsIndex(docSections(), await siteOrigin()));
}
