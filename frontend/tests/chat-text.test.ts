// @vitest-environment happy-dom
import { Editor } from "@tiptap/react";
import { describe, expect, it } from "vitest";
import { chatExtensions, fromDoc } from "@/lib/chat-doc";
import { fileProblem, fileSize, fitted } from "@/lib/chat-file";
import { parse, parseInline, parsePlain, plainText } from "@/lib/chat-text";

/** What the composer sends for this content. */
function written(html: string): string {
  const editor = new Editor({ extensions: chatExtensions, content: html });
  const result = fromDoc(editor.getJSON());
  editor.destroy();
  return result;
}

const text = (value: string, marks = {}) => ({ type: "text", text: value, ...marks });

describe("reading a message", () => {
  it.each([
    ["**bold**", [text("bold", { bold: true })]],
    ["*i* and _j_", [text("i", { italic: true }), text(" and "), text("j", { italic: true })]],
    ["***both***", [text("both", { bold: true, italic: true })]],
    ["**_both_**", [text("both", { bold: true, italic: true })]],
    ["[a **b**](/x)", [text("a ", { href: "/x" }), text("b", { href: "/x", bold: true })]],
    ["see https://a.example.com/x_y.", [text("see "), text("https://a.example.com/x_y", { href: "https://a.example.com/x_y" }), text(".")]],
  ])("%s", (source, expected) => {
    expect(parseInline(source)).toEqual(expected);
  });

  it.each(["2*3*4", "5 * 3 * 2", "snake_case_name", "a ** b ** c", "* ", "_", "[x]", "C:\\temp", "\u00e9_x_\u00e9"])("leaves %s as it is", (source) => {
    expect(parseInline(source)).toEqual([text(source)]);
  });

  it("finds lists, with the text around them", () => {
    expect(parse("Do this:\n1. one\n2. two\n\n- a\n\n- b\nthen")).toEqual([
      { type: "paragraph", content: [text("Do this:")] },
      { type: "list", ordered: true, start: 1, items: [[text("one")], [text("two")]] },
      { type: "list", ordered: false, start: 1, items: [[text("a")], [text("b")]] },
      { type: "paragraph", content: [text("then")] },
    ]);
  });

  it("keeps a visitor's message as typed, with addresses as links", () => {
    const [block] = parsePlain("**hi** [bank](https://evil.example.com)\n- x");
    const content = block.type === "paragraph" ? block.content : [];
    expect(content.map((piece) => (piece.type === "text" ? piece.text : "\n")).join("")).toBe("**hi** [bank](https://evil.example.com)\n- x");
    expect(content.some((piece) => piece.type === "text" && piece.bold)).toBe(false);
    // The link's text is its address.
    expect(content.flatMap((piece) => (piece.type === "text" && piece.href ? [[piece.text, piece.href]] : []))).toEqual([
      ["https://evil.example.com", "https://evil.example.com"],
    ]);
  });

  it("gives the words alone for previews", () => {
    expect(plainText("**Hi** [you](/x)\n- a\n- b")).toBe("Hi you a, b");
  });
});

describe("writing a message in the editor", () => {
  it.each([
    ["<p>Hello</p>", "Hello"],
    ["<p>one</p><p>two</p><p></p><p>three</p>", "one\ntwo\n\nthree"],
    ["<p><strong>b</strong> <em>i</em> <strong><em>bi</em></strong></p>", "**b** _i_ **_bi_**"],
    ["<p>a<strong> b </strong>c</p>", "a **b** c"],
    ['<p><a href="https://a.example.com/x">here</a></p>', "[here](https://a.example.com/x)"],
    ['<p><a href="https://a.example.com/x_y">https://a.example.com/x_y</a></p>', "https://a.example.com/x_y"],
    ['<p><a href="https://a.example.com/(x)">here</a></p>', "[here](https://a.example.com/%28x%29)"],
    ["<p>Do:</p><ul><li><p>a</p></li><li><p>b</p></li></ul>", "Do:\n- a\n- b"],
    ["<ol start='3'><li><p>a</p></li><li><p>b</p></li></ol>", "3. a\n4. b"],
    ["<ul><li><p>a</p><ul><li><p>n</p></li></ul></li><li><p></p></li></ul>", "- a\n- n"],
    ["<p></p>", ""],
    ["<p>2*3*4 snake_case C:\\temp</p>", "2*3*4 snake_case C:\\temp"],
  ])("%s", (html, expected) => {
    expect(written(html)).toBe(expected);
  });

  it.each(["*not italic*", "**not bold**", "_x_", "[a](https://b.example.com)", "\\*", "*a* https://x.example.com/a_b_c *d*"])(
    "shows %s as it was typed",
    (typed) => {
      const doc = { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: typed }] }] };
      const [block] = parse(fromDoc(doc));
      const pieces = block.type === "paragraph" ? block.content : [];
      expect(pieces.map((piece) => (piece.type === "text" ? piece.text : "")).join("")).toBe(typed);
      expect(pieces.some((piece) => piece.type === "text" && (piece.bold || piece.italic))).toBe(false);
    },
  );

  it("drops what messages can't have from pasted pages, keeping the text", () => {
    const html = '<h2>T</h2><blockquote>q</blockquote><img src="https://x.example.com/a.png"><p><a href="javascript:alert(1)">x</a></p>';
    expect(written(html)).toBe("T\nq\nx");
  });
});

describe("files", () => {
  it("says no before uploading", () => {
    expect(fileProblem({ name: "a.PNG", size: 10 })).toBe("");
    expect(fileProblem({ name: "a.pdf", size: 10 })).toBe("");
    expect(fileProblem({ name: "a.svg", size: 10 })).not.toBe("");
    expect(fileProblem({ name: "a.png.exe", size: 10 })).not.toBe("");
    expect(fileProblem({ name: "noextension", size: 10 })).not.toBe("");
    expect(fileProblem({ name: "a.pdf", size: 0 })).toContain("empty");
    expect(fileProblem({ name: "a.pdf", size: 11 * 1024 * 1024 })).toContain("10 MB");
  });

  it("shows sizes people can read", () => {
    expect([fileSize(900), fileSize(2048), fileSize(3.5 * 1024 * 1024)]).toEqual(["900 B", "2 KB", "3.5 MB"]);
  });

  it("fits pictures without making them bigger", () => {
    expect(fitted(2000, 1000, 200, 200)).toEqual({ width: 200, height: 100 });
    expect(fitted(40, 20, 200, 200)).toEqual({ width: 40, height: 20 });
  });
});
