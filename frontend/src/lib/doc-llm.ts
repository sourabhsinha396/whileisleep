import { docHref } from "./doc-text";
import type { DocSection } from "./docs";

/** The docs as language models read them: plain Markdown with full addresses. */

const SUMMARY =
  "Open-source customer chat for websites. An AI agent answers visitors from a company's articles, APIs and MCP servers, and hands a chat to a person when one is needed.";

const LINK = /\]\(([^()\s]+)\)/g;

/** One page with its title. Links lead to the other pages' Markdown; code is left alone. */
export function pageMarkdown(page: { title: string; description: string; body: string }, origin: string, repoUrl: string): string {
  let fence = false;
  const body = page.body
    .split("\n")
    .map((line) => {
      if (/^\s*```/.test(line)) fence = !fence;
      return fence ? line : line.replace(LINK, (whole, href: string) => `](${fullAddress(href, origin, repoUrl) || href})`);
    })
    .join("\n");
  return `# ${page.title}\n\n> ${page.description}\n\n${body}\n`;
}

function fullAddress(href: string, origin: string, repoUrl: string): string {
  const target = docHref(href, repoUrl);
  if (!target.startsWith("/")) return target;
  return origin + target.replace(/^(\/docs\/[a-z0-9-]+)(?=#|$)/, "$1.md");
}

/** /llms.txt: what the product is, and where to read about each thing (llmstxt.org). */
export function llmsIndex(sections: DocSection[], origin: string): string {
  const lists = sections.map(
    ({ title, pages }) => `## ${title}\n\n${pages.map((page) => `- [${page.title}](${origin}/docs/${page.slug}.md): ${page.description}`).join("\n")}`,
  );
  return [
    "# whileisleep",
    `> ${SUMMARY}`,
    `All pages in one file: ${origin}/llms-full.txt`,
    ...lists,
    `## Optional\n\n- [Pricing](${origin}/pricing): Self-host for free, or pay for the hosted plan.`,
  ].join("\n\n") + "\n";
}

export function markdownResponse(text: string, type: "text/markdown" | "text/plain" = "text/plain"): Response {
  return new Response(text, {
    headers: {
      "Content-Type": `${type}; charset=utf-8`,
      // For models to read. Search engines already have the page itself.
      ...(type === "text/markdown" ? { "X-Robots-Tag": "noindex" } : {}),
    },
  });
}
