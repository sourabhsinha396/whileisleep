/**
 * A page of the docs as a document of the Tiptap editor, and back. Articles' converter does the
 * text (lib/article-doc.ts); this adds code. What the editor has no button for (tables, tips)
 * is plain text in it, and comes back as it was.
 */

import type { JSONContent } from "@tiptap/react";
import CodeBlock from "@tiptap/extension-code-block";
import StarterKit from "@tiptap/starter-kit";
import { fromDoc, toDoc } from "./article-doc";

export const docExtensions = [
  StarterKit.configure({
    blockquote: false,
    codeBlock: false,
    horizontalRule: false,
    italic: false,
    strike: false,
    underline: false,
    // Addresses stay as they are written; only the Link button makes links.
    link: { openOnClick: false, autolink: false, linkOnPaste: false, defaultProtocol: "https" },
  }),
  // Its typing shortcut reads a language from "```js "; the attribute keeps whatever followed the fence.
  CodeBlock.configure({ languageClassPrefix: "language-" }),
];

const FENCED = /^```([^\n`]*)\n([\s\S]*?)\n?^```[ \t]*$/gm;

export function docToEditor(markdown: string): JSONContent {
  const text = markdown.replace(/\r\n?/g, "\n");
  const content: JSONContent[] = [];
  let last = 0;
  const prose = (part: string) => part.trim() && content.push(...(toDoc(part).content ?? []).map((node) => mapText(node, readCode)));
  for (const match of text.matchAll(FENCED)) {
    prose(text.slice(last, match.index));
    const [whole, language, code] = match;
    content.push({ type: "codeBlock", attrs: { language: language.trim() || null }, ...(code ? { content: [{ type: "text", text: code }] } : {}) });
    last = match.index + whole.length;
  }
  prose(text.slice(last));
  return { type: "doc", content: content.length ? content : [{ type: "paragraph" }] };
}

export function editorToDoc(doc: JSONContent): string {
  const parts: string[] = [];
  let prose: JSONContent[] = [];
  const flush = () => {
    const text = fromDoc({ type: "doc", content: prose.map((node) => mapText(node, writeCode)) });
    if (text) parts.push(text);
    prose = [];
  };
  for (const node of doc.content ?? []) {
    if (node.type !== "codeBlock") {
      prose.push(node);
      continue;
    }
    flush();
    const code = (node.content ?? []).map((piece) => piece.text ?? "").join("");
    // A fence inside the code would end it.
    parts.push(`\`\`\`${node.attrs?.language ?? ""}\n${code.replace(/^```/gm, " ```")}\n\`\`\``);
  }
  flush();
  return parts.join("\n\n");
}

function mapText(node: JSONContent, change: (text: JSONContent) => JSONContent[]): JSONContent {
  if (!node.content) return node;
  return { ...node, content: node.content.flatMap((child) => (child.type === "text" ? change(child) : [mapText(child, change)])) };
}

/** "Run `x` now" as three pieces, the middle one marked as code. */
function readCode(node: JSONContent): JSONContent[] {
  const text = node.text ?? "";
  // The editor can't have code inside a link or bold text, so there it stays as written.
  if (node.marks?.length) return [node];
  return text
    .split(/(`[^`\n]+`)/)
    .filter(Boolean)
    .map((piece) => (/^`[^`\n]+`$/.test(piece) ? { type: "text", text: piece.slice(1, -1), marks: [{ type: "code" }] } : { type: "text", text: piece }));
}

function writeCode(node: JSONContent): JSONContent[] {
  if (!node.marks?.some((mark) => mark.type === "code")) return [node];
  return [{ ...node, text: `\`${(node.text ?? "").replace(/`/g, "")}\``, marks: node.marks.filter((mark) => mark.type !== "code") }];
}
