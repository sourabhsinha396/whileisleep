import { readdirSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SitePage, { generateMetadata } from "@/app/[page]/page";
import sitemap from "@/app/sitemap";
import { SiteFooter } from "@/components/site-footer";
import { operator } from "@/lib/operator";
import { SITE_PAGES } from "@/lib/site-pages";

vi.mock("next/headers", () => ({ headers: async () => new Headers({ host: "chat.example.com", "x-forwarded-proto": "https" }) }));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not found");
  },
}));
vi.mock("@/components/ui", () => ({ Logo: () => null, ThemeToggle: () => null }));

const SLUGS = ["about", "contact", "privacy", "terms", "refunds"];
const props = (page: string) => ({ params: Promise.resolve({ page }) });

async function render(slug: string): Promise<HTMLElement> {
  const root = document.createElement("div");
  root.innerHTML = renderToStaticMarkup(await SitePage(props(slug)));
  return root;
}

function settings(name: string, email: string, address = "", jurisdiction = "") {
  vi.stubEnv("COMPANY_NAME", name);
  vi.stubEnv("COMPANY_EMAIL", email);
  vi.stubEnv("COMPANY_ADDRESS", address);
  vi.stubEnv("COMPANY_JURISDICTION", jurisdiction);
}

const footer = () => renderToStaticMarkup(<SiteFooter />);

beforeEach(() => settings("Acme Ltd", "hello@acme.test", "1 High Street", "Utopia"));
afterEach(() => vi.unstubAllEnvs());

it("has the pages a site needs, and none that another route already is", () => {
  expect(Object.keys(SITE_PAGES)).toEqual(SLUGS);
  expect(readdirSync("src/app").filter((name) => SLUGS.includes(name))).toEqual([]);
});

describe.each(SLUGS)("/%s", (slug) => {
  it("shows its title and text", async () => {
    const page = await render(slug);
    expect(page.querySelector("h1")?.textContent).toBe(SITE_PAGES[slug].title);
    expect(page.querySelectorAll("main h2").length).toBeGreaterThan(1);
    expect(page.textContent).not.toMatch(/undefined|null/);
  });

  it("links only to pages that are there", async () => {
    const known = ["/", "/#demo", "/pricing", "/docs", "/docs/self-hosting", "/login", ...SLUGS.map((one) => `/${one}`)];
    for (const link of (await render(slug)).querySelectorAll("a")) {
      const href = link.getAttribute("href") ?? "";
      if (href !== "mailto:hello@acme.test") expect(known).toContain(href);
    }
  });

  it("is in the sitemap and the footer, under its own address", async () => {
    expect((await sitemap()).map(({ url }) => url)).toContain(`https://chat.example.com/${slug}`);
    expect(footer()).toContain(`href="/${slug}"`);
    expect((await generateMetadata(props(slug))).alternates?.canonical).toBe(`https://chat.example.com/${slug}`);
  });
});

describe("the footer", () => {
  const titles = () => [...footer().matchAll(/<h2[^>]*>([^<]+)</g)].map(([, title]) => title);

  it("groups its links", () => {
    expect(titles()).toEqual(["Product", "Resources", "Company", "Legal"]);
  });

  it("leaves out a group with no pages", () => {
    settings("", "");
    expect(titles()).toEqual(["Product", "Resources", "Company"]);
  });
});

it("contact says who runs the site", async () => {
  const page = await render("contact");
  for (const text of ["Acme Ltd", "1 High Street", "hello@acme.test"]) expect(page.textContent).toContain(text);
});

it("refunds duplicates and the rest of a year, not a month", async () => {
  const rules = [...(await render("refunds")).querySelectorAll("main li")].map((li) => li.textContent);
  expect(rules).toHaveLength(3);
  expect(rules[0]).toMatch(/^Monthly plan:.*isn't refunded/);
  expect(rules[1]).toMatch(/^Yearly plan:.*months you haven't started/);
  expect(rules[2]).toMatch(/^Duplicate payment.*in full/);
});

it("terms name a law only when there is one", async () => {
  expect((await render("terms")).textContent).toContain("law of Utopia");
  settings("Acme Ltd", "hello@acme.test");
  expect((await render("terms")).textContent).not.toContain("law of");
});

describe("when nobody said who runs it", () => {
  it.each([["", ""], ["Acme Ltd", ""], ["", "hello@acme.test"]])("(%j, %j) only About is there", async (name, email) => {
    settings(name, email);
    expect(operator()).toBeNull();
    const about = await render("about");
    expect(about.textContent).toContain("Open source");
    expect(about.querySelector('a[href="/contact"]')).toBeNull();
    for (const slug of SLUGS.slice(1)) {
      await expect(SitePage(props(slug))).rejects.toThrow("not found");
      expect(footer()).not.toContain(`href="/${slug}"`);
    }
    expect((await sitemap()).map(({ url }) => url)).not.toContain("https://chat.example.com/privacy");
  });

  it("development shows stand-ins", () => {
    settings("", "");
    vi.stubEnv("NODE_ENV", "development");
    expect(operator()?.name).toBe("Example Company");
  });
});

it.each(["nothing-here", "constructor"])("/%s is not found", async (slug) => {
  await expect(SitePage(props(slug))).rejects.toThrow("not found");
});
