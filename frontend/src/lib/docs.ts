import { readFileSync } from "node:fs";
import path from "node:path";
import { type DocFile, readDocFile } from "./doc-text";

/** The docs, in the order they are listed. Each page is content/docs/<slug>.md. Server only. */
export const DOC_SECTIONS = [
  { title: "Get started", pages: ["how-it-works", "install", "connect-ai", "test-chat"] },
  { title: "Your AI agent", pages: ["knowledge-base", "rules", "playbooks", "tools"] },
  { title: "Daily work", pages: ["inbox", "visitors", "team"] },
  { title: "Integrations", pages: ["slack", "webhooks"] },
  { title: "Developers", pages: ["widget-api", "verified-identity", "self-hosting"] },
];

export interface DocLink {
  slug: string;
  title: string;
  description: string;
}

export interface DocSection {
  title: string;
  pages: DocLink[];
}

/** What a superuser changed on a page. */
export interface DocEdits {
  body: string;
  youtube_id: string;
}

export const DOC_SLUGS = DOC_SECTIONS.flatMap((section) => section.pages);

export function docFile(slug: string): DocFile {
  return readDocFile(readFileSync(path.join(process.cwd(), "content", "docs", `${slug}.md`), "utf8"));
}

export function docSections(): DocSection[] {
  return DOC_SECTIONS.map(({ title, pages }) => ({
    title,
    pages: pages.map((slug) => {
      const file = docFile(slug);
      return { slug, title: file.title, description: file.description };
    }),
  }));
}

/** Never fails: without the API a page shows the text it came with. */
export async function docEdits(slug: string): Promise<DocEdits> {
  try {
    const response = await fetch(`${process.env.API_URL ?? "http://localhost:8004"}/api/v1/docs/${slug}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
      // Django only believes it is on https when told so, and this is our own network.
      headers: { "X-Forwarded-Proto": "https" },
    });
    if (response.ok) return (await response.json()) as DocEdits;
  } catch {
    /* Shown as it came. */
  }
  return { body: "", youtube_id: "" };
}
