import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { AI_NAV, bottomNav, isActive, mainNav, type NavGroup, SETTINGS_LINK, settingsNav } from "@/lib/nav";
import nextConfig from "../next.config";

const hrefs = (groups: NavGroup[]) => groups.flatMap((g) => g.items.map((i) => i.href));
const hasPage = (href: string) => existsSync(join(process.cwd(), "src/app/w/[slug]", href, "page.tsx"));

const ORG_OWNER = { role: "owner", is_organization_owner: true, billing_state: "trial" } as const;
const OWNER = { role: "owner", is_organization_owner: false, billing_state: "trial" } as const;
const AGENT = { role: "agent", is_organization_owner: false, billing_state: "trial" } as const;

describe("navigation", () => {
  it("only links to pages that exist", () => {
    const all = [...mainNav(ORG_OWNER).map((i) => i.href), ...bottomNav(ORG_OWNER).map((i) => i.href), ...hrefs(AI_NAV), ...hrefs(settingsNav(ORG_OWNER))];
    expect(all.filter((href) => !hasPage(href))).toEqual([]);
  });

  it("keeps daily work in the sidebar and settings behind one entry", () => {
    expect(mainNav(OWNER).map((i) => i.label)).toEqual(["Inbox", "Visitors", "Knowledge base", "AI agent", "Integrations"]);
    expect(bottomNav(AGENT).map((i) => i.label)).toEqual(["Settings"]);
  });

  it("opens each area on a page its own panel lists", () => {
    expect(hrefs(AI_NAV)).toContain(mainNav(AGENT).find((i) => i.area === "ai")?.href);
    for (const person of [ORG_OWNER, OWNER, AGENT]) expect(hrefs(settingsNav(person))).toContain(SETTINGS_LINK.href);
  });
});

describe("billing in the sidebar", () => {
  it("is above settings for the organization's owner, where plans are sold", () => {
    expect(bottomNav(ORG_OWNER).map((i) => i.label)).toEqual(["Billing", "Settings"]);
    expect(bottomNav(OWNER)).toEqual([SETTINGS_LINK]);
    expect(bottomNav({ ...ORG_OWNER, billing_state: "off" })).toEqual([SETTINGS_LINK]);
  });
});

describe("settings by role", () => {
  const labels = (groups: NavGroup[]) => groups.map((g) => g.label);

  it("shows the organization only to its owner", () => {
    expect(labels(settingsNav(ORG_OWNER))).toEqual(["Workspace", "Chat widget", "Organization"]);
    expect(labels(settingsNav(OWNER))).toEqual(["Workspace", "Chat widget"]);
  });

  it("shows integrations only to workspace owners, on every page of theirs", () => {
    expect(mainNav(AGENT).map((i) => i.label)).not.toContain("Integrations");
    const item = mainNav(OWNER).find((i) => i.href === "integrations")!;
    expect(isActive("/w/acme/integrations/slack", "acme", item)).toBe(true);
    expect(isActive("/w/acme/integrations/slack", "acme", SETTINGS_LINK)).toBe(false);
  });

  it("shows the identity secret only to workspace owners", () => {
    expect(hrefs(settingsNav(OWNER))).toContain("settings/identity");
    expect(hrefs(settingsNav(AGENT))).not.toContain("settings/identity");
  });
});

describe("isActive", () => {
  const ai = mainNav(AGENT).find((i) => i.area === "ai")!;
  const inbox = mainNav(AGENT)[0];

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
    expect(redirects.map((r) => r.source)).toEqual(["/w/:slug/ai", "/w/:slug/settings", "/w/:slug/automation", "/w/:slug/organization", "/w/:slug/settings/billing"]);
    for (const { source, destination } of redirects) {
      expect(hasPage(destination.replace("/w/:slug/", ""))).toBe(true);
      // Temporary: browsers keep a permanent redirect even after the address gets a page again.
      expect(redirects.find((r) => r.source === source)).toMatchObject({ permanent: false });
    }
  });
});
