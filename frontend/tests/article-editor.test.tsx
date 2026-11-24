// @vitest-environment happy-dom
import { Editor } from "@tiptap/react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ArticleEditor, withProtocol } from "@/components/article-editor";
import { parse, serialize } from "@/lib/article";
import { articleExtensions, fromDoc, toDoc } from "@/lib/article-doc";

/** What a real editor makes of the article when nothing is changed. */
function throughEditor(markdown: string): string {
  const editor = new Editor({ extensions: articleExtensions, content: toDoc(markdown) });
  const result = fromDoc(editor.getJSON());
  editor.destroy();
  return result;
}

describe("the editor's document", () => {
  it.each([
    "Plain text.\n\nSecond paragraph.",
    "One\ntwo lines",
    "# H1\n\n## H2\n\n### H3",
    "**bold** [link](https://a.example.com/x?y=1&z=2) [a **bold** link](/exams/x)",
    "- one\n  - nested\n- two",
    "3. three\n4. four",
    "- one\n  more of one",
    "Text ![alt](https://cdn.example.com/a.png) inline",
    "See https://a.example.com/x for more",
    "| a | b |\n|---|---|\n| 1 | 2 |",
    "```yaml\nkey:\n    - x\n\n\n# comment\n```",
    "5 * 3 and snake_case and [brackets] & `x < 3` *italic* <b>html</b>",
    "",
  ])("gives back %j unchanged", (markdown) => {
    expect(throughEditor(markdown)).toBe(markdown);
  });

  it("agrees with the parser on everything else", () => {
    for (const markdown of ["* a\n\n* b", "**bold with [a link](/x) inside**", "Steps:\n1) x\n2) y", "1. a\n\n   para"]) {
      expect(throughEditor(markdown)).toBe(serialize(parse(markdown)));
    }
  });

  it("drops what articles can't have from pasted pages, keeping the text", () => {
    const editor = new Editor({ extensions: articleExtensions, content: "" });
    editor.commands.setContent(
      '<h2>T</h2><p><em>i</em> <u>u</u> <a href="javascript:alert(1)">x</a><script>alert(1)</script></p>' +
        '<table><tr><td>cell</td></tr></table><img src="data:image/png;base64,AAAA"><blockquote>q</blockquote>',
    );
    const markdown = fromDoc(editor.getJSON());
    editor.destroy();
    expect(markdown).toContain("## T");
    expect(markdown).toContain("i u x");
    expect(markdown).toContain("cell");
    expect(markdown).toContain("q");
    expect(markdown).not.toMatch(/javascript|data:|<|alert/);
  });

  it("several paragraphs in a list item become its lines", () => {
    const item = { type: "listItem", content: ["a", "b"].map((text) => ({ type: "paragraph", content: [{ type: "text", text }] })) };
    expect(fromDoc({ type: "doc", content: [{ type: "bulletList", content: [item] }] })).toBe("- a\n  b");
  });
});

describe("withProtocol", () => {
  it.each([
    ["example.com", "https://example.com"],
    ["localhost:3000/x", "https://localhost:3000/x"],
    [" https://a.example.com ", "https://a.example.com"],
    ["/exams/x", "/exams/x"],
    ["javascript:alert(1)", ""],
    ["", ""],
  ])("%j -> %j", (typed, href) => expect(withProtocol(typed)).toBe(href));
});

describe("<ArticleEditor>", () => {
  let root: Root;
  let host: HTMLDivElement;
  const changes: string[] = [];
  const onUpload = vi.fn(async () => "https://cdn.example.com/workspaces/1/articles/2/a.png");

  beforeEach(() => {
    vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
    changes.length = 0;
    onUpload.mockClear();
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
    vi.unstubAllGlobals();
  });

  async function show(value: string, uploadsEnabled = true) {
    await act(async () => root.render(<ArticleEditor value={value} onChange={(markdown) => changes.push(markdown)} onUpload={onUpload} uploadsEnabled={uploadsEnabled} />));
  }
  const button = (label: string) => host.querySelector<HTMLButtonElement>(`button[aria-label^="${label}"]`)!;

  async function choose(...files: File[]) {
    const input = host.querySelector<HTMLInputElement>('input[type="file"]')!;
    Object.defineProperty(input, "files", { value: files, configurable: true });
    await act(async () => {
      input.dispatchEvent(new Event("change", { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
  }

  it("has six controls", async () => {
    await show("Hi");
    const labels = Array.from(host.querySelectorAll('[role="toolbar"] button')).map((b) => b.getAttribute("aria-label"));
    expect(labels).toEqual(["Bold", "Heading", "Bullet list", "Numbered list", "Link", "Image"]);
  });

  it("shows the article formatted and doesn't rewrite it by opening it", async () => {
    await show("## Title\n\n* item with **bold**");
    expect(host.querySelector("h2")!.textContent).toBe("Title");
    expect(host.querySelector("li strong")!.textContent).toBe("bold");
    expect(changes).toEqual([]);
  });

  it("formats, and reports Markdown", async () => {
    await show("Title");
    await act(async () => button("Heading").click());
    expect(changes.at(-1)).toBe("## Title");
    expect(button("Heading").getAttribute("aria-pressed")).toBe("true");
    await act(async () => button("Heading").click());
    expect(changes.at(-1)).toBe("Title");
    await act(async () => button("Bullet list").click());
    expect(changes.at(-1)).toBe("- Title");
    await act(async () => button("Numbered list").click());
    expect(changes.at(-1)).toBe("1. Title");
  });

  it("uploads a picked image and puts it in the text", async () => {
    await show("");
    await choose(new File(["x"], "reset-button.png", { type: "image/png" }));
    expect(onUpload).toHaveBeenCalledOnce();
    expect(changes.at(-1)).toBe("![reset button](https://cdn.example.com/workspaces/1/articles/2/a.png)");
  });

  it("refuses other files without uploading them", async () => {
    await show("Text");
    await choose(new File(["<svg/>"], "a.svg", { type: "image/svg+xml" }));
    expect(onUpload).not.toHaveBeenCalled();
    expect(host.querySelector('[role="alert"]')!.textContent).toContain("PNG, JPEG or WebP");
    expect(changes).toEqual([]);
  });

  it("says why an upload failed and keeps the text", async () => {
    onUpload.mockRejectedValueOnce(new Error("This workspace has reached its limit."));
    await show("Text");
    await choose(new File(["x"], "a.png", { type: "image/png" }));
    expect(host.querySelector('[role="alert"]')!.textContent).toContain("reached its limit");
    expect(changes).toEqual([]);
  });

  it("turns images off without storage", async () => {
    await show("Text", false);
    expect(button("Image").disabled).toBe(true);
  });
});
