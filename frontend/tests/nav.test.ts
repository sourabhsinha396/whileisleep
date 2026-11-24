import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { AI_NAV, isActive, MAIN_NAV, type NavGroup, SETTINGS_LINK, settingsNav } from "@/lib/nav";
import nextConfig from "../next.config";

const hrefs = (groups: NavGroup[]) => groups.flatMap((g) => g.items.map((i) => i.href));
const hasPage = (href: string) => existsSync(join(process.cwd(), "src/app/w/[slug]", href, "page.tsx"));

const ORG_OWNER = { role: "owner", is_organization_owner: true } as const;
const OWNER = { role: "owner", is_organization_owner: false } as const;
const AGENT = { role: "agent", is_organization_owner: false } as const;

describe("navigation", () => {
  it("only links to pages that exist", () => {
    const all = [...MAIN_NAV.map((i) => i.href), SETTINGS_LINK.href, ...hrefs(AI_NAV), ...hrefs(settingsNav(ORG_OWNER))];
    expect(all.filter((href) => !hasPage(href))).toEqual([]);
  });

  it("keeps daily work in the sidebar and settings behind one entry", () => {
    expect(MAIN_NAV.map((i) => i.label)).toEqual(["Inbox", "Visitors", "Knowledge base", "AI agent"]);
    expect(SETTINGS_LINK.label).toBe("Settings");
  });

  it("opens each area on a page its own panel lists", () => {
    expect(hrefs(AI_NAV)).toContain(MAIN_NAV.find((i) => i.area === "ai")?.href);
    for (const person of [ORG_OWNER, OWNER, AGENT]) expect(hrefs(settingsNav(person))).toContain(SETTINGS_LINK.href);
  });
});

describe("settings by role", () => {
  const labels = (groups: NavGroup[]) => groups.map((g) => g.label);

  it("shows the organization only to its owner", () => {
    expect(labels(settingsNav(ORG_OWNER))).toEqual(["Workspace", "Chat widget", "Organization"]);
    expect(labels(settingsNav(OWNER))).toEqual(["Workspace", "Chat widget"]);
  });

  it("shows the identity secret only to workspace owners", () => {
    expect(hrefs(settingsNav(OWNER))).toContain("settings/identity");
    expect(hrefs(settingsNav(AGENT))).not.toContain("settings/identity");
  });
});

describe("isActive", () => {
  const ai = MAIN_NAV.find((i) => i.area === "ai")!;
  const inbox = MAIN_NAV[0];

  it("marks an area on any of its pages", () => {
    expect(isActive("/w/acme/ai/rules", "acme", ai)).toBe(true);
    expect(isActive("/w/acme/settings/team", "acme", SETTINGS_LINK)).toBe(true);
    expect(isActive("/w/acme/settings/ai-model", "acme", ai)).toBe(false);
  });

  it("matches whole path segments", () => {
    expect(isActive("/w/acme/inbox", "acme", inbox)).toBe(true);
    expect(isActive("/w/acme/inbox-old", "acme", inbox)).toBe(false);
    expect(isActive("/w/acme-2/inbox", "acme", inbox)).toBe(false);
  });
});

describe("redirects", () => {
  it("sends old and area addresses to pages that exist", async () => {
    const redirects = await nextConfig.redirects!();
    expect(redirects.map((r) => r.source)).toEqual(["/w/:slug/ai", "/w/:slug/settings", "/w/:slug/automation", "/w/:slug/organization"]);
    for (const { source, destination } of redirects) {
      expect(hasPage(destination.replace("/w/:slug/", ""))).toBe(true);
      // Temporary: browsers keep a permanent redirect even after the address gets a page again.
      expect(redirects.find((r) => r.source === source)).toMatchObject({ permanent: false });
    }
  });
});
