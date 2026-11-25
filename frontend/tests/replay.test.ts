import { readFileSync } from "node:fs";
import { beforeEach, describe, expect, it, vi } from "vitest";

const posthog = vi.hoisted(() => ({
  init: vi.fn(),
  identify: vi.fn(),
  reset: vi.fn(),
  opt_out_capturing: vi.fn(),
  opt_in_capturing: vi.fn(),
  has_opted_out_capturing: vi.fn(() => false),
}));
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
  posthog.has_opted_out_capturing.mockReturnValue(false);
  localStorage.clear();
  window.location.href = "http://localhost:3000/";
  at("/");
});

describe("starting", () => {
  it("needs a key and a host", async () => {
    const replay = await load();
    replay.startReplay(false, "", "https://h.test");
    replay.startReplay(false, "phc_x", "");
    replay.identifyUser({ id: 1, is_superuser: false }, "", "");
    replay.forgetUser();
    await settle();
    expect(posthog.init).not.toHaveBeenCalled();
    expect(posthog.identify).not.toHaveBeenCalled();
  });

  it("happens once, and says whose it is by number until they log out", async () => {
    const replay = await load();
    replay.startReplay(false, "phc_x", "https://h.test");
    replay.startReplay(false, "phc_x", "https://h.test");
    replay.identifyUser({ id: 7, is_superuser: false });
    replay.forgetUser();
    await settle();
    expect(posthog.init).toHaveBeenCalledTimes(1);
    expect(posthog.identify).toHaveBeenCalledWith("whileisleep-7");
    expect(posthog.reset).toHaveBeenCalled();
  });

  it.each(["/integrations/callback?code=secret", "/demo?key=ws_1", "/reset-password#key"])("stays off on %s", async (path) => {
    at(path);
    (await load()).startReplay(false, "phc_x", "https://h.test");
    await settle();
    expect(posthog.init).not.toHaveBeenCalled();
  });
});

describe("superusers", () => {
  const KEYS = ["phc_x", "https://h.test"] as const;
  const admin = { id: 1, is_superuser: true };
  const customer = { id: 7, is_superuser: false };

  it("stop being recorded when they log in, and are never identified", async () => {
    const replay = await load();
    replay.startReplay(false, ...KEYS);
    replay.identifyUser(admin, ...KEYS);
    await settle();
    expect(posthog.opt_out_capturing).toHaveBeenCalled();
    expect(posthog.identify).not.toHaveBeenCalled();
  });

  it.each([true, false])("aren't recorded on later visits, logged in or not (%s)", async (signedIn) => {
    const first = await load();
    first.identifyUser(admin, ...KEYS);
    first.forgetUser();
    (await load()).startReplay(signedIn, ...KEYS);
    await settle();
    expect(posthog.init).not.toHaveBeenCalled();
  });

  it("nobody logged in is recorded before we know who it is", async () => {
    const replay = await load();
    replay.startReplay(true, ...KEYS);
    await settle();
    expect(posthog.init).not.toHaveBeenCalled();
    replay.identifyUser(customer, ...KEYS);
    await settle();
    expect(posthog.init).toHaveBeenCalledTimes(1);
    expect(posthog.identify).toHaveBeenCalledWith("whileisleep-7");
  });

  it("a customer is recorded from the start of the next visit", async () => {
    (await load()).identifyUser(customer, ...KEYS);
    await settle();
    posthog.init.mockClear();
    (await load()).startReplay(true, ...KEYS);
    await settle();
    expect(posthog.init).toHaveBeenCalledTimes(1);
  });

  it("a customer who logs in after one, in the same browser, is recorded", async () => {
    posthog.has_opted_out_capturing.mockReturnValue(true);
    const replay = await load();
    replay.identifyUser(admin, ...KEYS);
    replay.forgetUser();
    replay.identifyUser(customer, ...KEYS);
    await settle();
    expect(posthog.opt_in_capturing).toHaveBeenCalledWith({ captureEventName: false });
    expect(posthog.identify).toHaveBeenCalledWith("whileisleep-7");
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
