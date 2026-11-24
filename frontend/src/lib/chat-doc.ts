/** A chat message being written, as a document of the Tiptap editor. */

import type { JSONContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { type Block, type Inline, serialize } from "./chat-text";

/** Only what messages can have (lib/chat-text.ts), so nothing pasted in adds more. */
export const chatExtensions = [
  StarterKit.configure({
    blockquote: false,
    code: false,
    codeBlock: false,
    heading: false,
    horizontalRule: false,
    strike: false,
    underline: false,
    link: { openOnClick: false, defaultProtocol: "https" },
    // An empty line after a list would be sent with the message.
    trailingNode: false,
  }),
];

export function fromDoc(doc: JSONContent): string {
  return serialize((doc.content ?? []).map(nodeToBlock));
}

function nodeToBlock(node: JSONContent): Block {
  if (node.type === "bulletList" || node.type === "orderedList") {
    return { type: "list", ordered: node.type === "orderedList", start: node.attrs?.start ?? 1, items: itemsOf(node) };
  }
  return { type: "paragraph", content: inlineOf(node.content) };
}

/** Lists in messages are flat: one inside another becomes items of its own. */
function itemsOf(list: JSONContent): Inline[][] {
  return (list.content ?? []).flatMap((item) => {
    const items: Inline[][] = [[]];
    for (const child of item.content ?? []) {
      if (child.type === "paragraph") {
        if (items[0].length) items[0].push({ type: "break" });
        items[0].push(...inlineOf(child.content));
      } else {
        items.push(...itemsOf(child));
      }
    }
    return items;
  });
}

function inlineOf(nodes: JSONContent[] = []): Inline[] {
  return nodes.flatMap((node): Inline[] => {
    if (node.type === "hardBreak") return [{ type: "break" }];
    if (!node.text) return [];
    const has = (type: string) => node.marks?.some((mark) => mark.type === type);
    const href = node.marks?.find((mark) => mark.type === "link")?.attrs?.href as string | undefined;
    return [
      {
        type: "text",
        text: node.text,
        ...(has("bold") ? { bold: true } : {}),
        ...(has("italic") ? { italic: true } : {}),
        ...(href ? { href } : {}),
      },
    ];
  });
}
