/**
 * The formatting help articles can have: headings, **bold**, lists, links, images and line
 * breaks, written as Markdown. The widget and the dashboard's editor both read it with
 * `parse`, so the editor shows what visitors see. Anything else (tables, HTML, code) is
 * plain text: shown as written, and never changed by opening and saving an article.
 */

export type Inline =
  | { type: "text"; text: string; bold?: boolean; href?: string }
  | { type: "image"; alt: string; src: string }
  | { type: "break" };

export interface ListItem {
  content: Inline[];
  lists: List[];
}

export interface List {
  type: "list";
  ordered: boolean;
  start: number;
  items: ListItem[];
}

export type Block = { type: "heading"; level: number; content: Inline[] } | { type: "paragraph"; content: Inline[] } | List;

const HEADING = /^(#{1,6})\s+(.*\S)\s*$/;
const LIST_LINE = /^(\s*)(?:[-*]|(\d{1,9})[.)])\s+(\S.*)$/;
const FENCE = /^\s*```/;
const INLINE =
  /!\[([^\]\n]*)\]\((https?:\/\/[^)\s]+)\)|\[([^\]\n]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*|(https?:\/\/[^\s<]+[^\s<.,;:!?)\]'"*])/g;

// --- Reading ---

export function parse(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const heading = HEADING.exec(line);
    if (!line.trim()) {
      i++;
    } else if (FENCE.test(line)) {
      // Code: kept together and untouched, blank lines included.
      let end = i + 1;
      while (end < lines.length && !FENCE.test(lines[end])) end++;
      blocks.push({ type: "paragraph", content: joinLines(lines.slice(i, end + 1).map(literal)) });
      i = end + 1;
    } else if (heading) {
      blocks.push({ type: "heading", level: heading[1].length, content: parseInline(heading[2]) });
      i++;
    } else if (LIST_LINE.test(line)) {
      const rows = listRows(lines, i);
      i = rows.next;
      blocks.push(...nest(rows.rows));
    } else {
      const start = i;
      while (i < lines.length && lines[i].trim() && !HEADING.test(lines[i]) && !FENCE.test(lines[i]) && !(i > start && LIST_LINE.test(lines[i]))) i++;
      blocks.push({ type: "paragraph", content: joinLines(lines.slice(start, i).map((text) => parseInline(text))) });
    }
  }
  return blocks;
}

interface Row {
  indent: number;
  ordered: boolean;
  number: number;
  lines: string[];
}

/** The list lines from `start`, each with the indented lines that continue it. */
function listRows(lines: string[], start: number): { rows: Row[]; next: number } {
  const rows: Row[] = [];
  let i = start;
  while (i < lines.length) {
    const match = LIST_LINE.exec(lines[i]);
    if (match) {
      rows.push({ indent: match[1].replace(/\t/g, "    ").length, ordered: match[2] !== undefined, number: Number(match[2] ?? 1), lines: [match[3]] });
    } else if (!lines[i].trim()) {
      // A blank line between two items doesn't end the list.
      let next = i;
      while (next < lines.length && !lines[next].trim()) next++;
      if (next >= lines.length || !LIST_LINE.test(lines[next])) return { rows, next };
      i = next;
      continue;
    } else if (/^\s/.test(lines[i]) && !FENCE.test(lines[i])) {
      rows[rows.length - 1].lines.push(lines[i].trim());
    } else {
      break;
    }
    i++;
  }
  return { rows, next: i };
}

/** Rows as lists, with more indented rows inside the item above them. */
function nest(rows: Row[]): List[] {
  const lists: List[] = [];
  let i = 0;
  while (i < rows.length) {
    const row = rows[i];
    let end = i + 1;
    while (end < rows.length && rows[end].indent > row.indent) end++;
    const item: ListItem = { content: joinLines(row.lines.map((text) => parseInline(text))), lists: nest(rows.slice(i + 1, end)) };
    const last = lists[lists.length - 1];
    if (last && last.ordered === row.ordered) last.items.push(item);
    else lists.push({ type: "list", ordered: row.ordered, start: row.number, items: [item] });
    i = end;
  }
  return lists;
}

function literal(text: string): Inline[] {
  return text ? [{ type: "text", text }] : [];
}

function joinLines(lines: Inline[][]): Inline[] {
  return lines.flatMap((line, i): Inline[] => (i > 0 ? [{ type: "break" }, ...line] : line));
}

export function parseInline(text: string, marks: { bold?: boolean; href?: string } = {}): Inline[] {
  const nodes: Inline[] = [];
  let last = 0;
  const plain = (value: string) => value && nodes.push({ type: "text", text: value, ...marks });
  for (const match of text.matchAll(INLINE)) {
    const [whole, alt, src, linkText, href, bold, url] = match;
    // A link can't be inside a link.
    if (marks.href && (linkText !== undefined || url !== undefined)) continue;
    plain(text.slice(last, match.index));
    if (src !== undefined) nodes.push({ type: "image", alt, src });
    else if (linkText !== undefined) nodes.push(...parseInline(linkText, { ...marks, href }));
    else if (bold !== undefined) nodes.push(...parseInline(bold, { ...marks, bold: true }));
    else nodes.push({ type: "text", text: url, ...marks, href: url });
    last = match.index + whole.length;
  }
  plain(text.slice(last));
  return nodes;
}

// --- Writing ---

export function serialize(blocks: Block[]): string {
  return blocks
    .map((block) => {
      if (block.type === "list") return serializeList(block, "");
      const text = serializeInline(block.content);
      if (block.type === "paragraph") return text.trim() ? text : "";
      // A heading is one line.
      return text.trim() ? `${"#".repeat(block.level)} ${text.replace(/\s*\n\s*/g, " ").trim()}` : "";
    })
    .filter(Boolean)
    .join("\n\n");
}

function serializeList(list: List, indent: string): string {
  return list.items
    .map((item, i) => {
      const marker = list.ordered ? `${list.start + i}. ` : "- ";
      const inner = indent + " ".repeat(marker.length);
      // A blank line would end the item.
      const text = serializeInline(item.content).split("\n").filter((line) => line.trim()).join(`\n${inner}`);
      if (!text && !item.lists.length) return "";
      return [`${indent}${marker}${text || "…"}`, ...item.lists.map((child) => serializeList(child, inner))].join("\n");
    })
    .filter(Boolean)
    .join("\n");
}

export function serializeInline(nodes: Inline[]): string {
  let out = "";
  for (let i = 0; i < nodes.length; ) {
    const node = nodes[i];
    if (node.type === "break") {
      out += "\n";
      i++;
    } else if (node.type === "image") {
      out += `![${node.alt.replace(/[[\]\n]/g, " ").trim()}](${node.src})`;
      i++;
    } else {
      // Pieces of one link are written as one link, bold parts inside it.
      let end = i + 1;
      while (end < nodes.length && sameLink(node.href, nodes[end])) end++;
      const run = nodes.slice(i, end) as Extract<Inline, { type: "text" }>[];
      const text = serializeBold(run);
      const plain = run.map((piece) => piece.text).join("");
      if (!node.href || plain === node.href) out += text;
      else if (/[[\]]/.test(plain) || /[\s)]/.test(node.href)) out += `${text} (${node.href})`;
      else out += `[${text}](${node.href})`;
      i = end;
    }
  }
  return out;
}

function sameLink(href: string | undefined, node: Inline): boolean {
  return node.type === "text" && node.href === href;
}

function serializeBold(run: { text: string; bold?: boolean }[]): string {
  let out = "";
  for (let i = 0; i < run.length; ) {
    let end = i + 1;
    while (end < run.length && !run[end].bold === !run[i].bold) end++;
    const text = run.slice(i, end).map((piece) => piece.text).join("");
    // Spaces go outside the stars: "**bold **" is not bold.
    const [, before, core, after] = /^(\s*)([\s\S]*?)(\s*)$/.exec(text)!;
    out += run[i].bold && core ? `${before}**${core}**${after}` : text;
    i = end;
  }
  return out;
}
