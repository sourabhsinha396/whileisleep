/**
 * Turns message text into DOM nodes without innerHTML (lib/chat-text.ts says what it can have).
 * Links open in a new tab and must be http(s) or relative.
 */

import { type Inline, parse, parsePlain } from "@/lib/chat-text";

export function safeHref(href: string, base?: string): string | null {
  try {
    const url = new URL(href, base ?? "https://invalid.local/");
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return href.startsWith("/") && !base ? href : url.href;
  } catch {
    return null;
  }
}

/** `base` resolves relative links (the workspace website), so "/exams/x" works in the widget.
 * `plain` is for what the visitor typed: shown as typed. */
export function formatText(text: string, base?: string, plain = false): HTMLElement[] {
  return (plain ? parsePlain(text) : parse(text)).map((block) => {
    if (block.type === "paragraph") return filled("p", block.content, base);
    const list = document.createElement(block.ordered ? "ol" : "ul");
    if (block.ordered && block.start !== 1) list.setAttribute("start", String(block.start));
    list.append(...block.items.map((item) => filled("li", item, base)));
    return list;
  });
}

function filled(tag: string, content: Inline[], base?: string): HTMLElement {
  const node = document.createElement(tag);
  node.append(...content.map((piece) => inline(piece, base)));
  return node;
}

function inline(piece: Inline, base?: string): Node {
  if (piece.type === "break") return document.createElement("br");
  let node: Node = document.createTextNode(piece.text);
  if (piece.italic) node = wrapped("em", node);
  if (piece.bold) node = wrapped("strong", node);
  const href = piece.href && safeHref(piece.href, base);
  if (!href) return node;
  const a = wrapped("a", node) as HTMLAnchorElement;
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

function wrapped(tag: string, child: Node): HTMLElement {
  const node = document.createElement(tag);
  node.appendChild(child);
  return node;
}
