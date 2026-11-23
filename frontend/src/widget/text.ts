/**
 * Turns message text into DOM nodes without innerHTML: paragraphs, line breaks, **bold**,
 * [markdown](links) and bare URLs. Links open in a new tab and must be http(s) or relative.
 */

const TOKEN = /\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*|(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"])/g;

export function safeHref(href: string, base?: string): string | null {
  try {
    const url = new URL(href, base ?? "https://invalid.local/");
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return href.startsWith("/") && !base ? href : url.href;
  } catch {
    return null;
  }
}

function link(text: string, href: string, base?: string): Node {
  const safe = safeHref(href, base);
  if (!safe) return document.createTextNode(text);
  const a = document.createElement("a");
  a.href = safe;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.textContent = text;
  return a;
}

function inline(line: string, base?: string): Node[] {
  const nodes: Node[] = [];
  let last = 0;
  for (const match of line.matchAll(TOKEN)) {
    if (match.index! > last) nodes.push(document.createTextNode(line.slice(last, match.index)));
    const [whole, linkText, linkHref, bold, url] = match;
    if (linkText !== undefined) nodes.push(link(linkText, linkHref, base));
    else if (bold !== undefined) {
      const strong = document.createElement("strong");
      strong.textContent = bold;
      nodes.push(strong);
    } else nodes.push(link(url, url, base));
    last = match.index! + whole.length;
  }
  if (last < line.length) nodes.push(document.createTextNode(line.slice(last)));
  return nodes;
}

/** `base` resolves relative links (the workspace website), so "/exams/x" works in the widget. */
export function formatText(text: string, base?: string): HTMLElement[] {
  return text
    .split(/\n{2,}/)
    .filter((p) => p.trim())
    .map((paragraph) => {
      const p = document.createElement("p");
      paragraph.split("\n").forEach((line, i) => {
        if (i > 0) p.appendChild(document.createElement("br"));
        p.append(...inline(line.replace(/^\s*[-*]\s+/, "• "), base));
      });
      return p;
    });
}
