import GithubSlugger from "github-slugger";

/** A page of the docs as it is written in its file: content/docs/<slug>.md. */
export interface DocFile {
  title: string;
  description: string;
  body: string;
}

export interface Heading {
  id: string;
  text: string;
  level: number;
}

/** Splits a file into the lines between its two `---` and the Markdown below them. */
export function readDocFile(text: string): DocFile {
  const match = /^---\n([\s\S]*?)\n---\n+([\s\S]*)$/.exec(text.replace(/\r\n?/g, "\n"));
  if (!match) throw new Error("A page of the docs starts with its title and description between two --- lines.");
  const field = (name: string) => new RegExp(`^${name}:\\s*(.+)$`, "m").exec(match[1])?.[1].trim() ?? "";
  return { title: field("title"), description: field("description"), body: match[2].trim() };
}

/** The headings for "On this page", with the ids they get in the page. */
export function headings(markdown: string): Heading[] {
  const slugger = new GithubSlugger();
  const found: Heading[] = [];
  let fence = false;
  for (const line of markdown.split("\n")) {
    if (/^\s*```/.test(line)) fence = !fence;
    const match = fence ? null : /^(#{1,6})\s+(.*\S)\s*$/.exec(line);
    if (!match) continue;
    const text = match[2].replace(/\[([^\]]+)\]\([^)]*\)/g, "$1").replace(/\*\*|`/g, "");
    // Every heading counts towards the ids, also those that aren't listed.
    const id = slugger.slug(text);
    if (match[1].length === 2 || match[1].length === 3) found.push({ id, text, level: match[1].length });
  }
  return found;
}

/**
 * Where a link in a page goes. Pages link to each other as files ("webhooks.md#anchor"), so the
 * links also work on GitHub; "../" leads to another file of the repository.
 */
export function docHref(href: string, repoUrl: string): string {
  const page = /^(?:\.\/)?([a-z0-9-]+)\.md(#.*)?$/.exec(href);
  if (page) return `/docs/${page[1]}${page[2] ?? ""}`;
  if (href.startsWith("../")) return repoUrl ? `${repoUrl.replace(/\/$/, "")}/blob/main/${href.replace(/^(\.\.\/)+/, "")}` : "";
  return href;
}
