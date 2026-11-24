/**
 * Help articles as DOM nodes, without innerHTML. Unlike chat messages (text.ts) they can show
 * images: articles are written by the team, while a chat message may come from a visitor or
 * the AI, and loading an image whose address they chose could send data to another site.
 */

import { type Inline, type List, parse } from "@/lib/article";
import { safeHref } from "./text";

export function formatArticle(markdown: string, base?: string): HTMLElement[] {
  return parse(markdown).map((block) => {
    if (block.type === "list") return list(block, base);
    // The article's title is an h3.
    const node = document.createElement(block.type === "paragraph" ? "p" : block.level <= 2 ? "h4" : "h5");
    node.append(...block.content.map((piece) => inline(piece, base)));
    return node;
  });
}

function list(source: List, base?: string): HTMLElement {
  const node = document.createElement(source.ordered ? "ol" : "ul");
  if (source.ordered && source.start !== 1) node.setAttribute("start", String(source.start));
  for (const item of source.items) {
    const li = document.createElement("li");
    li.append(...item.content.map((piece) => inline(piece, base)), ...item.lists.map((child) => list(child, base)));
    node.appendChild(li);
  }
  return node;
}

function inline(piece: Inline, base?: string): Node {
  if (piece.type === "break") return document.createElement("br");
  if (piece.type === "image") return image(piece.src, piece.alt);
  let node: Node = document.createTextNode(piece.text);
  if (piece.bold) {
    const strong = document.createElement("strong");
    strong.appendChild(node);
    node = strong;
  }
  const href = piece.href && safeHref(piece.href, base);
  return href ? link(href, node) : node;
}

function link(href: string, child: Node): HTMLAnchorElement {
  const a = document.createElement("a");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.appendChild(child);
  return a;
}

/** Opens full size in a new tab. Only https: the site around the widget may be on https. */
function image(src: string, alt: string): Node {
  const href = safeHref(src);
  if (!href?.startsWith("https://")) return document.createTextNode(alt);
  const img = document.createElement("img");
  img.alt = alt;
  img.loading = "lazy";
  img.referrerPolicy = "no-referrer";
  img.src = href;
  return link(href, img);
}
