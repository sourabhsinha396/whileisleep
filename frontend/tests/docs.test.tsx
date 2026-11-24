// @vitest-environment happy-dom
import { readdirSync } from "node:fs";
import { Editor } from "@tiptap/react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DocBody } from "@/components/docs/doc-body";
import { DocMarkdown } from "@/components/docs/markdown";
import { DocVideo } from "@/components/docs/video";
import { docExtensions, docToEditor, editorToDoc } from "@/lib/doc-editor";
import { docHref, headings, readDocFile } from "@/lib/doc-text";
import { DOC_SLUGS, docEdits, docFile } from "@/lib/docs";

const refresh = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

// No test opens a real page.
(window as unknown as { happyDOM: { settings: { disableIframePageLoading: boolean } } }).happyDOM.settings.disableIframePageLoading = true;
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const markup = (markdown: string) => renderToStaticMarkup(<DocMarkdown>{markdown}</DocMarkdown>);

/** What a real editor makes of a page when nothing is changed. */
function throughEditor(markdown: string): string {
  const editor = new Editor({ extensions: docExtensions, content: docToEditor(markdown) });
  const result = editorToDoc(editor.getJSON());
  editor.destroy();
  return result;
}

describe("the pages", () => {
  it("lists every file, once", () => {
    const files = readdirSync("content/docs").map((name) => name.replace(/\.md$/, ""));
    expect([...DOC_SLUGS].sort()).toEqual(files.sort());
  });

  it.each(DOC_SLUGS)("%s has a title and a description, and links only to what exists", (slug) => {
    const { title, description, body } = docFile(slug);
    expect(title).not.toBe("");
    expect(description).not.toBe("");
    const root = document.createElement("div");
    root.innerHTML = markup(body);
    const ids = (page: string) => headings(docFile(page).body).map(({ id }) => id);
    for (const link of root.querySelectorAll("a")) {
      const [path, anchor] = link.getAttribute("href")!.split("#");
      if (!path.startsWith("/docs/")) continue;
      const target = path.replace("/docs/", "");
      expect(DOC_SLUGS).toContain(target);
      if (anchor) expect(ids(target)).toContain(anchor);
    }
    // "On this page" leads to headings that are there.
    for (const { id } of headings(body)) expect(root.querySelector(`[id="${id}"]`), id).not.toBeNull();
  });

  it.each(DOC_SLUGS)("%s reads the same after it was saved in the editor", (slug) => {
    const { body } = docFile(slug);
    const saved = throughEditor(body);
    expect(markup(saved)).toBe(markup(body));
    expect(throughEditor(saved)).toBe(saved);
  });
});

describe("reading a file", () => {
  it("splits title, description and text", () => {
    expect(readDocFile("---\r\ntitle: A: b\r\ndescription: c\r\n---\r\n\r\nText\r\n")).toMatchObject({ title: "A: b", description: "c", seoTitle: "A: b", seoDescription: "c", body: "Text" });
  });

  it("refuses a file without them", () => {
    expect(() => readDocFile("Text")).toThrow();
  });

  it("finds headings, but not comments in code", () => {
    expect(headings("## One `x`\n```sh\n# no\n```\n### [Two](a.md)\n## One `x`")).toEqual([
      { id: "one-x", text: "One x", level: 2 },
      { id: "two", text: "Two", level: 3 },
      { id: "one-x-1", text: "One x", level: 2 },
    ]);
  });

  it("turns links between files into links between pages", () => {
    expect(docHref("webhooks.md#x", "")).toBe("/docs/webhooks#x");
    expect(docHref("../../../backend/a.json", "https://git.example.com/me/w/")).toBe("https://git.example.com/me/w/blob/main/backend/a.json");
    expect(docHref("../../../backend/a.json", "")).toBe("");
    expect(docHref("https://example.com", "")).toBe("https://example.com");
  });
});

describe("the text", () => {
  it("never renders HTML or scripts", () => {
    const html = markup('<script>alert(1)</script>\n\n[x](javascript:alert(1))\n\n<img src=x onerror="alert(1)">');
    expect(html).not.toContain("<script");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("javascript:");
  });

  it("makes tabs of code in several languages", () => {
    const html = markup("```js\na\n```\n\n```python\nb\n```\n\n```php\nc\n```\n\nText\n\n```sh\nd\n```");
    const root = document.createElement("div");
    root.innerHTML = html;
    expect([...root.querySelectorAll("[role=group] button")].map((b) => b.textContent)).toEqual(["JavaScript", "Python", "PHP"]);
    expect(root.querySelectorAll("[hidden]")).toHaveLength(2);
    expect(root.querySelectorAll("pre")).toHaveLength(4);
  });

  it("shows tips", () => {
    const html = markup("> [!TIP]\n> Do this");
    expect(html).toContain('role="note"');
    expect(html).not.toContain("[!TIP]");
  });
});

describe("the editor", () => {
  it.each([
    "Text with `code` and **bold**.",
    "```js\nconst a = `x`;\n\n# not a heading\n```",
    "```\nplain\n```\n\n```python\nb\n```",
    "- one `a`\n- two",
    "| a | b |\n|---|---|\n| `1` | 2 |",
    "> [!TIP]\n> Do **this**",
    "See [webhooks](webhooks.md#x) and https://example.com",
    "Visit example.com or file.md",
  ])("gives back %j unchanged", (markdown) => {
    expect(throughEditor(markdown)).toBe(markdown);
  });

  it("shows code as code", () => {
    const { content } = docToEditor("Run `x`\n\n```js\na\n```");
    expect(content?.[0].content?.[1]).toEqual({ type: "text", text: "x", marks: [{ type: "code" }] });
    expect(content?.[1]).toMatchObject({ type: "codeBlock", attrs: { language: "js" } });
  });
});

describe("a page without the API", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the text it came with", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new Error("down")));
    expect(await docEdits("install")).toEqual({ body: "", youtube_id: "" });
    vi.stubGlobal("fetch", async () => new Response("no", { status: 500 }));
    expect(await docEdits("install")).toEqual({ body: "", youtube_id: "" });
  });
});

describe("in the browser", () => {
  let host: HTMLDivElement;
  let root: Root;
  const calls: { path: string; body: unknown }[] = [];
  let superuser = true;

  beforeEach(() => {
    host = document.body.appendChild(document.createElement("div"));
    root = createRoot(host);
    calls.length = 0;
    superuser = true;
    localStorage.setItem("whileisleep:token", "at_1");
    vi.stubGlobal("fetch", async (path: string, init: RequestInit) => {
      if (path.endsWith("/auth/me")) return Response.json({ is_superuser: superuser });
      calls.push({ path, body: JSON.parse(String(init.body)) });
      return Response.json({ body: "", youtube_id: "" });
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
    localStorage.clear();
    vi.unstubAllGlobals();
    refresh.mockReset();
  });

  const body = (props: Partial<Parameters<typeof DocBody>[0]> = {}) => (
    <DocBody slug="install" body="Hello" edited={false} youtubeId="" {...props}>
      <p>Hello</p>
    </DocBody>
  );
  const show = (node: React.ReactNode) => act(async () => root.render(node));
  const button = (name: string) => [...host.querySelectorAll("button")].find((b) => (b.getAttribute("aria-label") ?? b.textContent)!.trim().startsWith(name));
  const press = (name: string) => act(async () => button(name)!.click());

  it("loads YouTube's player only when asked", async () => {
    await show(<DocVideo id="dQw4w9WgXcQ" title="Install" />);
    expect(host.querySelector("iframe")).toBeNull();
    await press("Play");
    expect(host.querySelector("iframe")?.src).toContain("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ");
  });

  it("offers readers nothing to edit", async () => {
    superuser = false;
    await show(body({ edited: true }));
    expect(host.querySelectorAll("button")).toHaveLength(0);
    expect(host.textContent).toBe("Hello");
  });

  it("saves a video link", async () => {
    await show(body());
    await press("Add video");
    const input = host.querySelector<HTMLInputElement>("input")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "https://youtu.be/dQw4w9WgXcQ");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => host.querySelector("form")!.requestSubmit());
    expect(calls).toEqual([{ path: "/api/v1/docs/install", body: { video_link: "https://youtu.be/dQw4w9WgXcQ" } }]);
    expect(refresh).toHaveBeenCalled();
  });

  it("removes a video", async () => {
    await show(body({ youtubeId: "dQw4w9WgXcQ" }));
    await press("Change video");
    await press("Remove");
    expect(calls[0].body).toEqual({ video_link: "" });
  });

  it("brings the original back, after asking", async () => {
    window.confirm = () => true;
    await show(body({ edited: true }));
    await press("Restore original");
    expect(calls[0].body).toEqual({ body: "" });
  });

  it("offers to restore only what was edited", async () => {
    await show(body());
    expect(button("Edit text")).toBeDefined();
    expect(button("Restore original")).toBeUndefined();
  });
});
