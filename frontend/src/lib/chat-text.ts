/**
 * The formatting chat messages can have: **bold**, *italic*, [links](https://x), bare URLs and
 * lists, written as Markdown. The inbox's editor writes it, and the inbox and the widget both
 * read it with `parse`. Never images: a message may come from the AI, and loading an image
 * whose address it chose could send data to another site.
 *
 * This runs on customers' sites in any browser: no regular expression lookbehind, which older
 * Safari refuses to load at all.
 */

export interface Text {
  type: "text";
  text: string;
  bold?: boolean;
  italic?: boolean;
  href?: string;
}

export type Inline = Text | { type: "break" };
type Marks = Omit<Text, "type" | "text">;

export interface List {
  type: "list";
  ordered: boolean;
  start: number;
  items: Inline[][];
}

export type Block = { type: "paragraph"; content: Inline[] } | List;

const LIST_LINE = /^\s*(?:[-*•]|(\d{1,3})[.)])\s+(\S.*)$/;
const URL_PATTERN = "https?:\\/\\/[^\\s<]+[^\\s<.,;:!?)\\]'\"*_]";
const INLINE = new RegExp(
  [
    "\\\\([\\\\*_[\\]])",
    "\\[((?:\\\\.|[^\\]\\\\\\n])+)\\]\\(([^)\\s]+)\\)",
    "\\*\\*\\*(\\S(?:.*?\\S)?)\\*\\*\\*",
    "\\*\\*(\\S(?:.*?\\S)?)\\*\\*",
    "\\*([^\\s*](?:[^*\\n]*[^\\s*])?)\\*",
    "_([^\\s_](?:[^_\\n]*[^\\s_])?)_",
    `(${URL_PATTERN})`,
  ].join("|"),
  "g",
);
const WORD = /[\p{L}\p{N}]/u;

// --- Reading ---

export function parse(text: string): Block[] {
  const blocks: Block[] = [];
  let gap = true;
  for (const line of text.replace(/\r\n?/g, "\n").split("\n")) {
    const last = blocks[blocks.length - 1];
    const item = LIST_LINE.exec(line);
    if (!line.trim()) {
      gap = true;
      continue;
    }
    if (item) {
      const ordered = item[1] !== undefined;
      const content = parseInline(item[2]);
      // A blank line between two items doesn't end the list.
      if (last?.type === "list" && last.ordered === ordered) last.items.push(content);
      else blocks.push({ type: "list", ordered, start: Number(item[1] ?? 1), items: [content] });
    } else if (last?.type === "paragraph" && !gap) {
      last.content.push({ type: "break" }, ...parseInline(line));
    } else {
      blocks.push({ type: "paragraph", content: parseInline(line) });
    }
    gap = false;
  }
  return blocks;
}

/** What a visitor typed: their own characters, with addresses as links. Nothing they write can
 * hide where a link goes. */
export function parsePlain(text: string): Block[] {
  return text
    .replace(/\r\n?/g, "\n")
    .split(/\n{2,}/)
    .filter((paragraph) => paragraph.trim())
    .map((paragraph) => ({
      type: "paragraph",
      content: paragraph.split("\n").flatMap((line, i): Inline[] => (i > 0 ? [{ type: "break" }, ...linked(line)] : linked(line))),
    }));
}

function linked(line: string): Text[] {
  const nodes: Text[] = [];
  let last = 0;
  for (const match of line.matchAll(new RegExp(URL_PATTERN, "g"))) {
    if (match.index > last) nodes.push({ type: "text", text: line.slice(last, match.index) });
    nodes.push({ type: "text", text: match[0], href: match[0] });
    last = match.index + match[0].length;
  }
  if (last < line.length) nodes.push({ type: "text", text: line.slice(last) });
  return nodes;
}

export function parseInline(text: string, marks: Marks = {}): Text[] {
  const nodes: Text[] = [];
  let pending = "";
  let last = 0;
  const flush = () => {
    if (pending) nodes.push({ type: "text", text: pending, ...marks });
    pending = "";
  };
  const pattern = new RegExp(INLINE.source, "g");
  for (let match = pattern.exec(text); match; match = pattern.exec(text)) {
    const [whole, escaped, linkText, href, both, bold, star, underscore, url] = match;
    const italic = star ?? underscore;
    const inWord = WORD.test(text[match.index - 1] ?? "") || WORD.test(text[match.index + whole.length] ?? "");
    // 2*3*4 and snake_case_name are not italic, and a link can't be inside a link.
    if ((italic !== undefined && inWord) || (marks.href && (linkText !== undefined || url !== undefined))) {
      pattern.lastIndex = match.index + 1;
      continue;
    }
    pending += text.slice(last, match.index);
    last = match.index + whole.length;
    if (escaped !== undefined) {
      pending += escaped;
      continue;
    }
    flush();
    if (linkText !== undefined) nodes.push(...parseInline(linkText, { ...marks, href }));
    else if (both !== undefined) nodes.push(...parseInline(both, { ...marks, bold: true, italic: true }));
    else if (bold !== undefined) nodes.push(...parseInline(bold, { ...marks, bold: true }));
    else if (italic !== undefined) nodes.push(...parseInline(italic, { ...marks, italic: true }));
    else nodes.push({ type: "text", text: url, ...marks, href: url });
  }
  pending += text.slice(last);
  flush();
  return nodes;
}

/** The words alone, for one-line previews. */
export function plainText(text: string): string {
  const words = (content: Inline[]) => content.map((piece) => (piece.type === "break" ? " " : piece.text)).join("");
  return parse(text)
    .map((block) => (block.type === "list" ? block.items.map(words).join(", ") : words(block.content)))
    .join(" ");
}

// --- Writing ---

/** `blocks` as the editor has them: each paragraph is one line, and an empty one a blank line. */
export function serialize(blocks: Block[]): string {
  return blocks
    .map((block) => {
      if (block.type === "paragraph") return serializeInline(block.content);
      return block.items
        .map((item, i) => `${block.ordered ? `${block.start + i}.` : "-"} ${serializeInline(item).replace(/\s*\n\s*/g, " ").trim()}`)
        // An item nobody filled in.
        .filter((line) => /\s\S/.test(line))
        .join("\n");
    })
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function serializeInline(nodes: Inline[]): string {
  return nodes
    .map((node, i) => {
      if (node.type === "break") return "\n";
      // Spaces go outside the marks: "**bold **" is not bold.
      const [, before, core, after] = /^(\s*)([\s\S]*?)(\s*)$/.exec(node.text)!;
      if (!core) return node.text;
      if (node.href === core && !node.bold && !node.italic) return node.text;
      let text = escape(core);
      // Inside a word, stars are read as stars.
      const inWord = (!before && WORD.test(edge(nodes[i - 1], -1))) || (!after && WORD.test(edge(nodes[i + 1], 0)));
      if (node.italic && !inWord) text = `_${text}_`;
      if (node.bold) text = `**${text}**`;
      if (node.href) text = `[${text}](${node.href.replace(/\s/g, "%20").replace(/\(/g, "%28").replace(/\)/g, "%29")})`;
      return before + text + after;
    })
    .join("");
}

function edge(node: Inline | undefined, at: number): string {
  return node?.type === "text" ? (node.text.at(at) ?? "") : "";
}

/** Text that would be read as formatting, written so it is read as it is. */
function escape(text: string): string {
  const read = parseInline(text);
  if (read.every((piece) => !piece.bold && !piece.italic && (!piece.href || piece.href === piece.text)) && read.map((piece) => piece.text).join("") === text) {
    return text;
  }
  return text
    .split(new RegExp(`(${URL_PATTERN})`))
    .map((part, i) => (i % 2 ? part : part.replace(/[\\*_[\]]/g, "\\$&")))
    .join("");
}
