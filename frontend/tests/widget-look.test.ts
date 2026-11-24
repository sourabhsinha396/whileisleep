// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { previewWidget } from "@/widget/preview";
import { styles } from "@/widget/styles";

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
  it.each(["dots", "grid", "stripes", "bubbles"])("draws %s", (background) => {
    expect(show({ background }).look.contains(`bg-${background}`)).toBe(true);
    expect(styles).toContain(`.bg-${background} .body`);
  });

  it.each(["plain", undefined, "x y"])("draws nothing for %s", (background) => {
    expect(Array.from(show({ background }).look).some((name) => name.startsWith("bg-"))).toBe(false);
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
