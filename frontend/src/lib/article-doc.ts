/** An article as a document of the Tiptap editor, and back. */

import Image from "@tiptap/extension-image";
import type { JSONContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { type Block, type Inline, type List, type ListItem, parse, serialize } from "./article";

/** Only what articles can have (lib/article.ts), so nothing pasted in adds more. */
export const articleExtensions = [
  StarterKit.configure({
    blockquote: false,
    code: false,
    codeBlock: false,
    horizontalRule: false,
    italic: false,
    strike: false,
    underline: false,
    link: { openOnClick: false, defaultProtocol: "https" },
  }),
  Image.configure({ inline: true, allowBase64: false }),
];

// --- Markdown to document ---

export function toDoc(markdown: string): JSONContent {
  const content = parse(markdown).map(blockToNode);
  return { type: "doc", content: content.length ? content : [{ type: "paragraph" }] };
}

function blockToNode(block: Block): JSONContent {
  if (block.type === "list") return listToNode(block);
  if (block.type === "heading") return { type: "heading", attrs: { level: block.level }, content: block.content.map(inlineToNode) };
  return { type: "paragraph", content: block.content.map(inlineToNode) };
}

function listToNode(list: List): JSONContent {
  return {
    type: list.ordered ? "orderedList" : "bulletList",
    ...(list.ordered ? { attrs: { start: list.start } } : {}),
    content: list.items.map((item) => ({
      type: "listItem",
      content: [{ type: "paragraph", content: item.content.map(inlineToNode) }, ...item.lists.map(listToNode)],
    })),
  };
}

function inlineToNode(piece: Inline): JSONContent {
  if (piece.type === "break") return { type: "hardBreak" };
  if (piece.type === "image") return { type: "image", attrs: { src: piece.src, alt: piece.alt } };
  const marks = [...(piece.href ? [{ type: "link", attrs: { href: piece.href } }] : []), ...(piece.bold ? [{ type: "bold" }] : [])];
  return { type: "text", text: piece.text, ...(marks.length ? { marks } : {}) };
}

// --- Document to Markdown ---

export function fromDoc(doc: JSONContent): string {
  return serialize((doc.content ?? []).map(nodeToBlock));
}

function nodeToBlock(node: JSONContent): Block {
  if (node.type === "heading") return { type: "heading", level: node.attrs?.level ?? 2, content: nodesToInline(node.content) };
  if (node.type === "bulletList" || node.type === "orderedList") return nodeToList(node);
  return { type: "paragraph", content: nodesToInline(node.content) };
}

function nodeToList(node: JSONContent): List {
  return { type: "list", ordered: node.type === "orderedList", start: node.attrs?.start ?? 1, items: (node.content ?? []).map(nodeToItem) };
}

/** The editor allows several paragraphs in an item; they become its lines. */
function nodeToItem(node: JSONContent): ListItem {
  const item: ListItem = { content: [], lists: [] };
  for (const child of node.content ?? []) {
    if (child.type === "bulletList" || child.type === "orderedList") {
      item.lists.push(nodeToList(child));
    } else {
      const content = nodesToInline(child.content);
      if (item.content.length && content.length) item.content.push({ type: "break" });
      item.content.push(...content);
    }
  }
  return item;
}

function nodesToInline(nodes: JSONContent[] = []): Inline[] {
  return nodes.flatMap((node): Inline[] => {
    if (node.type === "hardBreak") return [{ type: "break" }];
    if (node.type === "image") return [{ type: "image", src: node.attrs?.src ?? "", alt: node.attrs?.alt ?? "" }];
    if (!node.text) return [];
    const href = node.marks?.find((mark) => mark.type === "link")?.attrs?.href as string | undefined;
    const bold = node.marks?.some((mark) => mark.type === "bold");
    return [{ type: "text", text: node.text, ...(bold ? { bold } : {}), ...(href ? { href } : {}) }];
  });
}
