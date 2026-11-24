import { describe, expect, it, vi } from "vitest";
import { generateMetadata as docs } from "@/app/docs/page";
import { generateMetadata as login } from "@/app/login/layout";
import { generateMetadata as home } from "@/app/page";
import { generateMetadata as pricing } from "@/app/pricing/page";
import { DOC_SLUGS, docFile } from "@/lib/docs";
import { breadcrumbData, jsonLd, publicMetadata } from "@/lib/seo";

vi.mock("next/headers", () => ({ headers: async () => new Headers({ host: "chat.example.com", "x-forwarded-proto": "https" }) }));

const SUFFIX = " | whileisleep";

async function pages() {
  const all = await Promise.all([home(), pricing(), docs(), login()]);
  const documents = DOC_SLUGS.map((slug) => docFile(slug)).map(({ seoTitle, seoDescription }) => ({ title: seoTitle, description: seoDescription }));
  return [...all, ...documents].map(({ title, description }) => ({
    title: title && typeof title === "object" && "absolute" in title ? String(title.absolute) : `${title}${SUFFIX}`,
    description: String(description),
  }));
}

describe("every public page", () => {
  it("has a title and description that fit in a search result", async () => {
    for (const { title, description } of await pages()) {
      expect(title.length, title).toBeLessThanOrEqual(60);
      expect(description.length, description).toBeGreaterThanOrEqual(100);
      expect(description.length, description).toBeLessThanOrEqual(160);
    }
  });

  it("has its own", async () => {
    const all = await pages();
    expect(new Set(all.map(({ title }) => title)).size).toBe(all.length);
    expect(new Set(all.map(({ description }) => description)).size).toBe(all.length);
  });

  it("says its one address, and what a shared link shows", async () => {
    const data = await publicMetadata({ title: "T", description: "D", path: "/docs/x", markdown: "/docs/x.md" });
    expect(data.alternates).toEqual({ canonical: "https://chat.example.com/docs/x", types: { "text/markdown": "https://chat.example.com/docs/x.md" } });
    expect(data.openGraph).toMatchObject({ url: "https://chat.example.com/docs/x", images: [{ url: "https://chat.example.com/og.png" }] });
  });
});

it("structured data can't end its script tag", () => {
  expect(jsonLd(breadcrumbData("</script><b>", "x", "https://a.example.com"))).not.toContain("<");
});
