// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { PATTERNS, patternSvg } from "@/lib/patterns";
import { previewWidget } from "@/widget/preview";

const LOOK = { name: "Acme Store", color: "#2563eb", logo_url: "", greeting: "Hi there!", team: [] };

function show(look: { background?: string; color_mode?: string } = {}) {
  const fetched = vi.fn(async () => new Response("{}"));
  vi.stubGlobal("fetch", fetched);
  const box = document.createElement("div");
  document.body.appendChild(box);
  const remove = previewWidget(box, { ...LOOK, ...look });
  const root = box.firstElementChild!.shadowRoot!;
  return { box, remove, fetched, root, look: root.querySelector(".od")!.classList };
}

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
});

describe("the widget's look", () => {
  it.each(PATTERNS)("draws %s on the header, and nowhere else", (background) => {
    const { root } = show({ background });
    expect(root.querySelectorAll(".pattern")).toHaveLength(1);
    expect(root.querySelector(".head > .pattern pattern")!.children.length).toBeGreaterThan(1);
  });

  it.each(["plain", undefined, "x y", "constructor"])("draws nothing for %s", (background) => {
    expect(show({ background }).root.querySelector(".pattern")).toBeNull();
  });

  it("draws in the text's color, so it suits every widget color", () => {
    for (const name of PATTERNS) expect(patternSvg(name, "x")).not.toMatch(/#[0-9a-f]{3}|NaN|undefined/i);
  });

  it("is light unless it is told otherwise", () => {
    expect(show().look.contains("dark")).toBe(false);
    expect(show({ color_mode: "light" }).look.contains("dark")).toBe(false);
    expect(show({ color_mode: "dark" }).look.contains("dark")).toBe(true);
  });

  it("follows the visitor's device, also when that changes", () => {
    let changed = () => {};
    const device = { matches: true, addEventListener: (_: string, handler: () => void) => (changed = handler) };
    vi.stubGlobal("matchMedia", () => device);
    window.matchMedia = (() => device) as never;
    const { look } = show({ color_mode: "auto" });
    expect(look.contains("dark")).toBe(true);
    device.matches = false;
    changed();
    expect(look.contains("dark")).toBe(false);
  });
});

describe("the preview", () => {
  it("is the real panel with a sample chat, and calls no server", () => {
    const { root, fetched, box, remove } = show();
    expect(root.querySelector<HTMLElement>(".panel")!.hidden).toBe(false);
    expect(root.querySelector(".bubble")!.textContent).toBe("Hi there!");
    expect(root.querySelectorAll(".msg").length).toBeGreaterThan(1);
    expect(fetched).not.toHaveBeenCalled();
    remove();
    expect(box.children).toHaveLength(0);
  });
});
