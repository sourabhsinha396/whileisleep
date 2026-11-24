// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET as fullText } from "@/app/llms-full.txt/route";
import { GET as index } from "@/app/llms.txt/route";
import { GET as markdown } from "@/app/docs/[page]/markdown/route";
import robots from "@/app/robots";
import sitemap from "@/app/sitemap";
import { CopyPage } from "@/components/docs/copy-page";
import { pageMarkdown } from "@/lib/doc-llm";
import { DOC_SLUGS, docFile } from "@/lib/docs";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
vi.mock("next/headers", () => ({ headers: async () => new Headers({ host: "chat.example.com", "x-forwarded-proto": "https, http" }) }));

const ORIGIN = "https://chat.example.com";
const get = (page: string) => markdown(new Request(`${ORIGIN}/docs/${page}.md`), { params: Promise.resolve({ page }) });

beforeEach(() => void vi.stubGlobal("fetch", async () => Response.json({ body: "", youtube_id: "" })));
afterEach(() => vi.unstubAllGlobals());

describe("a page as Markdown", () => {
  it("has its title, and full links", () => {
    const text = pageMarkdown({ title: "T", description: "D", body: "[a](webhooks.md#x) [b](https://e.com) [c](/docs/rules)\n\n```md\n[d](rules.md)\n```" }, ORIGIN, "");
    expect(text).toBe(`# T\n\n> D\n\n[a](${ORIGIN}/docs/webhooks.md#x) [b](https://e.com) [c](${ORIGIN}/docs/rules.md)\n\n\`\`\`md\n[d](rules.md)\n\`\`\`\n`);
  });

  it("is served, with what was edited", async () => {
    const plain = await get("install");
    expect(plain.headers.get("content-type")).toContain("text/markdown");
    expect(await plain.text()).toContain("data-workspace");
    vi.stubGlobal("fetch", async () => Response.json({ body: "Edited", youtube_id: "" }));
    expect(await (await get("install")).text()).toBe("# Install the chat\n\n> Put the widget on your site with one line of code.\n\nEdited\n");
  });

  it("is only there for pages of the docs", async () => {
    expect((await get("../../package")).status).toBe(404);
  });
});

it("llms.txt lists every page", async () => {
  const text = await (await index()).text();
  expect(text).toMatch(/^# whileisleep\n\n> /);
  for (const slug of DOC_SLUGS) expect(text).toContain(`](${ORIGIN}/docs/${slug}.md)`);
});

it("llms-full.txt holds every page", async () => {
  const text = await (await fullText()).text();
  for (const slug of DOC_SLUGS) expect(text).toContain(`# ${docFile(slug).title}\n`);
});

it("robots.txt keeps the API out, and points to the sitemap", async () => {
  const { rules, sitemap: address } = await robots();
  expect(rules).toMatchObject({ disallow: expect.arrayContaining(["/admin/", "/api/"]) });
  expect(address).toBe(`${ORIGIN}/sitemap.xml`);
  expect((await sitemap()).map(({ url }) => url)).toContain(`${ORIGIN}/docs/install`);
});

it("copies the page", async () => {
  const writeText = vi.fn(async () => {});
  vi.stubGlobal("navigator", { clipboard: { writeText } });
  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  await act(async () => root.render(<CopyPage slug="install" markdown="# Install" />));
  await act(async () => host.querySelector("button")!.click());
  expect(writeText).toHaveBeenCalledWith("# Install");
  expect(host.textContent).toContain("Copied");
  act(() => root.unmount());
});
