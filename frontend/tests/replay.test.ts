import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";

const posthog = vi.hoisted(() => ({ init: vi.fn(), identify: vi.fn(), reset: vi.fn() }));
vi.mock("posthog-js", () => ({ default: posthog }));

const at = (path: string) => window.history.replaceState({}, "", `http://localhost:3000${path}`);
const settle = () => new Promise((resolve) => setTimeout(resolve, 20));

/** A fresh copy: it starts once per page load. */
async function load() {
  vi.resetModules();
  return import("@/lib/replay");
}

beforeEach(() => {
  vi.clearAllMocks();
  posthog.init.mockReturnValue(posthog);
  window.location.href = "http://localhost:3000/";
  at("/");
});

describe("starting", () => {
  it("needs a key and a host", async () => {
    const replay = await load();
    replay.startReplay("", "https://h.test");
    replay.startReplay("phc_x", "");
    replay.identifyUser(1);
    replay.forgetUser();
    await settle();
    expect(posthog.init).not.toHaveBeenCalled();
    expect(posthog.identify).not.toHaveBeenCalled();
  });

  it("happens once, and says whose it is by number until they log out", async () => {
    const replay = await load();
    replay.startReplay("phc_x", "https://h.test");
    replay.startReplay("phc_x", "https://h.test");
    replay.identifyUser(7);
    replay.forgetUser();
    await settle();
    expect(posthog.init).toHaveBeenCalledTimes(1);
    expect(posthog.identify).toHaveBeenCalledWith("whileisleep-7");
    expect(posthog.reset).toHaveBeenCalled();
  });

  it.each(["/integrations/callback?code=secret", "/demo?key=ws_1"])("stays off on %s", async (path) => {
    at(path);
    (await load()).startReplay("phc_x", "https://h.test");
    await settle();
    expect(posthog.init).not.toHaveBeenCalled();
  });
});

describe("what a recording can show", () => {
  it.each(["/w/acme/settings/general", "/w/acme/inbox", "/app", "/new"])("masks text and telling attributes on %s", async (path) => {
    const { maskText, maskAttribute } = await load();
    at(path);
    const element = document.createElement("p");
    expect(maskText("Jo, jo@x.test", element)).toBe("*** *********");
    expect(maskAttribute("href", "mailto:jo@x.test", element)).toBe("*");
    expect(maskAttribute("class", "flex", element)).toBe("flex");
  });

  it("keeps the menus and the page's styles", async () => {
    const { maskText, maskAttribute } = await load();
    at("/w/acme/ai/rules");
    const nav = document.createElement("nav");
    const item = nav.appendChild(document.createElement("a"));
    expect(maskText("Settings", item)).toBe("Settings");
    const style = document.head.appendChild(document.createElement("link"));
    expect(maskAttribute("href", "/app.css", style)).toBe("/app.css");
  });

  it.each(["/", "/pricing", "/docs/rules", "/widgets"])("shows %s as it is", async (path) => {
    const { maskText, maskAttribute } = await load();
    at(path);
    expect(maskText("Pricing")).toBe("Pricing");
    expect(maskAttribute("href", "/docs")).toBe("/docs");
  });

  it("masks every input, and no request's headers or body is recorded", async () => {
    const config = (await load()).replayConfig("https://h.test");
    expect(config.session_recording).toMatchObject({ maskAllInputs: true, maskTextSelector: "*", recordHeaders: false, recordBody: false });
    expect(config).toMatchObject({ autocapture: false, persistence: "localStorage", respect_dnt: true });
  });

  it.each(["inbox", "visitors"])("leaves out the %s", (page) => {
    expect(readFileSync(`src/app/w/[slug]/${page}/layout.tsx`, "utf8")).toContain("ph-no-capture");
  });

  it("sends addresses without their query", async () => {
    const { withoutQueries } = await load();
    const event = {
      properties: { $current_url: "https://a.test/w/x?code=1#y", $referrer: "$direct", n: 1 },
      $set_once: { $initial_current_url: "https://a.test/?t=1" },
    };
    expect(withoutQueries(event)).toEqual({
      properties: { $current_url: "https://a.test/w/x", $referrer: "$direct", n: 1 },
      $set_once: { $initial_current_url: "https://a.test/" },
    });
    expect(withoutQueries(null)).toBeNull();
  });
});

it("the widget doesn't have it", () => {
  const widget = ["api", "widget", "index"].map((name) => readFileSync(`src/widget/${name}.ts`, "utf8")).join();
  expect(widget).not.toMatch(/posthog|lib\/replay|@\/lib\/api"/);
});
