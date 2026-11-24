import { describe, expect, it } from "vitest";
import { parse, serialize } from "@/lib/article";
import { formatArticle } from "@/widget/article";
import { formatText } from "@/widget/text";

const again = (markdown: string) => serialize(parse(markdown));

function html(markdown: string, base?: string) {
  const node = document.createElement("div");
  node.append(...formatArticle(markdown, base));
  return node;
}

describe("opening and saving an article", () => {
  it.each([
    "Plain text.\n\nSecond paragraph.",
    "One\ntwo lines",
    "# H1\n\n## H2\n\nText\n\n### H3",
    "**bold** and [link](https://a.example.com/x?y=1&z=2)",
    "[a **bold** link](/exams/x)",
    "- one\n- two\n- three",
    "1. one\n2. two",
    "3. three\n4. four",
    "- one\n  - nested\n    - deeper\n- two",
    "1. one\n   - nested\n2. two",
    "- one\n  more of one\n- two",
    "![alt text](https://cdn.example.com/a.png)",
    "Text ![](https://cdn.example.com/a.png) inline",
    "See https://a.example.com/x for more",
    "Paragraph\n\n- list\n\nParagraph",
  ])("keeps what it supports: %j", (markdown) => {
    expect(again(markdown)).toBe(markdown);
  });

  it.each([
    "| a | b |\n|---|---|\n| 1 | 2 |",
    "```yaml\nkey:\n    - x\n\n\n# comment\n  indented\n```",
    "```\nnever closed\n\n- x",
    "5 * 3 * 2 and snake_case_name and [brackets] and `x < 3` & y > 2",
    "<b>html</b> <script>alert(1)</script>",
    "*italic* and ~~strike~~ and \\*escaped\\*",
    "> quote",
    "---",
    "- [ ] task",
    "& < > \" ' &amp;",
    "[x](javascript:alert(1))",
    "**not closed",
    "![x](data:image/png;base64,AAAA)",
    "Hi #hashtag",
  ])("leaves everything else as written: %j", (markdown) => {
    expect(again(markdown)).toBe(markdown);
  });

  it("tidies spacing without changing the meaning", () => {
    expect(again("a\r\n\r\n\r\n\r\nb\n")).toBe("a\n\nb");
    expect(again("* one\n\n* two")).toBe("- one\n- two");
    expect(again("Steps:\n- one")).toBe("Steps:\n\n- one");
    expect(again("1) one\n2) two")).toBe("1. one\n2. two");
    expect(again("**bold with [a link](/x) inside**")).toBe("**bold with** [**a link**](/x) **inside**");
  });

  it("never loses a word, and settles after one save", () => {
    const pieces = ["# T", "- a **b**", "  - c", "1. d", "text", "", "   cont", "```", "![i](https://x.example.com/i.png)", "**", "[l](/u)", "| t |", "https://u.example.com"];
    const words = (text: string) => text.match(/[a-z]+/gi)!.join(" ");
    let seed = 7;
    const random = (n: number) => (seed = (seed * 1103515245 + 12345) % 2147483648) % n;
    for (let round = 0; round < 500; round++) {
      const markdown = ["start", ...Array.from({ length: 8 }, () => pieces[random(pieces.length)])].join("\n");
      const saved = again(markdown);
      expect(words(saved), markdown).toBe(words(markdown));
      expect(again(saved), markdown).toBe(saved);
    }
  });

  it("drops empty blocks", () => {
    expect(serialize([{ type: "paragraph", content: [] }, { type: "heading", level: 2, content: [] }])).toBe("");
    expect(serialize([])).toBe("");
  });

  it("keeps spaces outside the stars", () => {
    const content = [
      { type: "text" as const, text: "very ", bold: true },
      { type: "text" as const, text: "nice" },
    ];
    expect(serialize([{ type: "paragraph", content }])).toBe("**very** nice");
  });

  it("writes a link it can't express as text and address", () => {
    const content = [{ type: "text" as const, text: "a [b]", href: "https://x.example.com/" }];
    expect(serialize([{ type: "paragraph", content }])).toBe("a [b] (https://x.example.com/)");
  });
});

describe("articles in the widget", () => {
  it("shows headings below the article's title", () => {
    const node = html("## Refunds\n\n### Digital");
    expect(node.querySelector("h4")!.textContent).toBe("Refunds");
    expect(node.querySelector("h5")!.textContent).toBe("Digital");
  });

  it("shows lists, numbered from where they start", () => {
    const node = html("- one\n  - inner\n\nText\n\n3. three");
    expect(node.querySelector("ul > li > ul > li")!.textContent).toBe("inner");
    expect(node.querySelector("ol")!.getAttribute("start")).toBe("3");
  });

  it("shows images, lazily, opening full size", () => {
    const img = html("![The button](https://cdn.example.com/a.png)").querySelector("img")!;
    expect(img.getAttribute("src")).toBe("https://cdn.example.com/a.png");
    expect(img.alt).toBe("The button");
    expect(img.loading).toBe("lazy");
    expect(img.referrerPolicy).toBe("no-referrer");
    expect(img.closest("a")!.rel).toBe("noopener noreferrer");
  });

  it.each(["![x](http://cdn.example.com/a.png)", "![x](javascript:alert(1))", "![x](data:image/svg+xml,<svg>)"])("shows no image for %s", (markdown) => {
    expect(html(markdown).querySelector("img")).toBeNull();
  });

  it("links bold text, and resolves relative links against the website", () => {
    const a = html("[**go**](/exams/x)", "https://shop.example.com").querySelector("a")!;
    expect(a.getAttribute("href")).toBe("https://shop.example.com/exams/x");
    expect(a.querySelector("strong")!.textContent).toBe("go");
  });

  it("drops unsafe links and never parses html", () => {
    const node = html('[click](javascript:alert(1)) <b onclick="x">hi</b>');
    expect(node.querySelector("a, b")).toBeNull();
    expect(node.textContent).toContain("<b onclick=");
  });
});

describe("chat messages", () => {
  it("never load images: a message's author could choose the address", () => {
    const node = document.createElement("div");
    node.append(...formatText("![x](https://evil.example.com/?secret=1)"));
    expect(node.querySelector("img")).toBeNull();
  });
});
