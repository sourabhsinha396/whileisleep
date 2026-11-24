import { existsSync } from "node:fs";
import { join } from "node:path";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GetStarted, useGuide } from "@/components/get-started";
import type { SetupStep, Workspace } from "@/lib/api";
import { guide, progress, settled } from "@/lib/get-started";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const OWNER = { id: 1, slug: "acme", public_key: "ws_1", role: "owner", is_organization_owner: true } as Workspace;
const KEYS = ["install", "ai", "article", "chat", "storage"];
const REQUIRED = KEYS.slice(0, 4);
const setup = (...done: string[]): SetupStep[] => KEYS.map((key) => ({ key, done: done.includes(key) }));

describe("guide", () => {
  it("keeps the server's order and says what is next", () => {
    const steps = guide(OWNER, setup("install"));
    expect(steps.map((s) => s.key)).toEqual(KEYS);
    expect(progress(steps)).toMatchObject({ done: 1, total: 5, finished: false, dismissible: false, next: { key: "ai" } });
  });

  it("only links to pages that exist", () => {
    for (const { href } of guide(OWNER, setup())) {
      const path = href.replace("/w/acme", "/w/[slug]").split("?")[0];
      expect(existsSync(join(process.cwd(), "src/app", path, "page.tsx"))).toBe(true);
    }
  });

  it("leaves out what the person can't do", () => {
    const keys = guide({ ...OWNER, is_organization_owner: false }, setup()).map((s) => s.key);
    expect(keys).toEqual(["install", "article", "chat"]);
    expect(guide({ ...OWNER, role: "agent" }, setup())).toEqual([]);
  });

  it("leaves out steps it doesn't know", () => {
    expect(guide(OWNER, [...setup(), { key: "from-the-future", done: false }])).toHaveLength(5);
  });

  it("can be put away once only the optional step is left", () => {
    const steps = guide(OWNER, setup(...REQUIRED));
    expect(progress(steps)).toMatchObject({ finished: false, dismissible: true, next: { key: "storage" } });
  });

  it("stops asking once nothing is left for this person", () => {
    expect(settled(setup(...KEYS), true, false)).toBe(true);
    expect(settled(setup(...REQUIRED), true, false)).toBe(false);
    expect(settled(setup(...REQUIRED), true, true)).toBe(true);
    expect(settled(setup("install"), true, true)).toBe(false);
    expect(settled(setup("install", "article", "chat"), false, false)).toBe(true);
  });

  it("is finished when every step is done", () => {
    expect(progress(guide(OWNER, setup(...KEYS)))).toMatchObject({ finished: true, next: undefined });
  });
});

describe("the sidebar row", () => {
  let root: Root;
  let box: HTMLElement;

  beforeEach(() => {
    box = document.body.appendChild(document.createElement("div"));
    root = createRoot(box);
  });
  afterEach(() => {
    act(() => root.unmount());
    box.remove();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  const show = (...done: string[]) => act(() => root.render(<GetStarted steps={guide(OWNER, setup(...done))} workspaceId={1} />));
  const links = () => [...box.querySelectorAll("a")].map((a) => a.getAttribute("href"));

  const row = () => box.querySelector<HTMLButtonElement>("button[aria-haspopup]")!;
  const panel = () => box.querySelector('[role="dialog"]');
  const open = () => {
    show("install");
    act(() => row().click());
  };

  it("is one row with the next step until it is opened", () => {
    show("install");
    expect(row().textContent).toBe("Next: Connect your AI1/5");
    expect(row().getAttribute("aria-label")).toContain("1 of 5 done");
    expect(panel()).toBeNull();
    expect(links()).toEqual([]);
  });

  it("opens the whole guide and points at one next step", () => {
    open();
    expect(links()).toHaveLength(5);
    const bar = box.querySelector('[role="progressbar"]')!;
    expect([bar.getAttribute("aria-valuenow"), bar.getAttribute("aria-valuemax")]).toEqual(["1", "5"]);
    const current = [...box.querySelectorAll('[aria-current="step"]')];
    expect(current.map((a) => a.getAttribute("href"))).toEqual(["/w/acme/settings/ai-model"]);
    expect(document.activeElement).toBe(panel());
  });

  it("closes on Escape and gives the keyboard back to the row", () => {
    open();
    act(() => panel()!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(panel()).toBeNull();
    expect(document.activeElement).toBe(row());
  });

  it("closes on a click outside, and when a step is chosen", () => {
    open();
    act(() => document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true })));
    expect(panel()).toBeNull();
    act(() => row().click());
    const step = box.querySelector("a")!;
    step.addEventListener("click", (e) => e.preventDefault());
    act(() => step.click());
    expect(panel()).toBeNull();
  });

  const hideButton = () => [...box.querySelectorAll("button")].find((b) => b.textContent === "Hide this guide");

  it("offers to hide only when nothing but the optional step is left", () => {
    open();
    expect(hideButton()).toBeUndefined();
    show(...REQUIRED);
    expect(hideButton()).toBeDefined();
  });

  it("stays hidden in this workspace, and only this one", async () => {
    localStorage.clear();
    show(...REQUIRED);
    act(() => row().click());
    act(() => hideButton()!.click());
    expect(box.textContent).toBe("");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(setup(...REQUIRED)))));
    function Count({ workspace }: { workspace: Workspace }) {
      return <>{useGuide(workspace).length}</>;
    }
    await act(async () => root.render(<Count key="a" workspace={OWNER} />));
    expect(box.textContent).toBe("0");
    await act(async () => root.render(<Count key="b" workspace={{ ...OWNER, id: 2 }} />));
    expect(box.textContent).toBe("5");
    localStorage.clear();
  });

  it("goes away when setup is finished, and stops asking", async () => {
    vi.useFakeTimers();
    const answers = [setup("install", "ai", "article"), setup(...KEYS)];
    const fetch = vi.fn(async () => new Response(JSON.stringify(answers.shift())));
    vi.stubGlobal("fetch", fetch);
    function Sidebar() {
      const steps = useGuide(OWNER);
      return steps.length ? <GetStarted steps={steps} workspaceId={1} /> : null;
    }
    await act(async () => root.render(<Sidebar />));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(box.textContent).toContain("3/5");
    await act(() => vi.advanceTimersByTimeAsync(15000));
    expect(box.textContent).toBe("");
    await act(() => vi.advanceTimersByTimeAsync(60000));
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("never asks on behalf of an agent", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const agent = { ...OWNER, role: "agent" } as Workspace;
    function Sidebar() {
      return <>{useGuide(agent).length}</>;
    }
    await act(async () => root.render(<Sidebar />));
    expect(box.textContent).toBe("0");
    expect(fetch).not.toHaveBeenCalled();
  });
});
