import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const theme = vi.hoisted(() => ({ resolvedTheme: "light" }));
vi.mock("next-themes", () => ({ useTheme: () => theme }));

interface Options {
  sitekey: string;
  theme: string;
  callback: (token: string) => void;
  "expired-callback": () => void;
}

let root: Root;
let host: HTMLElement;
let scripts: HTMLScriptElement[];
const draw = vi.fn<(box: HTMLElement, options: Options) => number>(() => 0);
const options = () => draw.mock.calls.at(-1)![1];
const settle = () => act(async () => void (await new Promise((resolve) => setTimeout(resolve, 5))));

async function show(siteKey: string, onChange: (token: string) => void = () => {}) {
  vi.stubGlobal("fetch", async () => Response.json({ site_key: siteKey }));
  const { Captcha } = await import("@/components/captcha");
  const element = (key: number) => <Captcha key={key} onChange={onChange} />;
  await act(async () => root.render(element(1)));
  await settle();
  return { again: () => act(async () => root.render(element(2))) };
}

async function load() {
  Object.assign(window, { grecaptcha: { ready: (done: () => void) => done(), render: draw } });
  await act(async () => scripts.at(-1)!.onload?.(new Event("load")));
  await settle();
}

beforeEach(() => {
  vi.resetModules();
  draw.mockClear();
  theme.resolvedTheme = "light";
  scripts = [];
  // The page never really asks Google.
  vi.spyOn(document.head, "appendChild").mockImplementation((node) => {
    scripts.push(node as unknown as HTMLScriptElement);
    return node;
  });
  host = document.body.appendChild(document.createElement("div"));
  root = createRoot(host);
});

afterEach(async () => {
  await act(async () => root.unmount());
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("loads nothing where the server has none", async () => {
  await show("");
  expect(scripts).toEqual([]);
  expect(host.innerHTML).toBe("");
});

it("gives the form what a ticked box stands for, until it expires", async () => {
  const tokens: string[] = [];
  await show("site-key", (token) => tokens.push(token));
  await load();
  expect(scripts[0].src).toMatch(/^https:\/\/www\.google\.com\/recaptcha\/api\.js/);
  expect(options()).toMatchObject({ sitekey: "site-key", theme: "light" });
  act(() => options().callback("t1"));
  act(() => options()["expired-callback"]());
  expect(tokens).toEqual(["t1", ""]);
});

it("is drawn again, unticked, after a try", async () => {
  const tokens: string[] = [];
  const { again } = await show("site-key", (token) => tokens.push(token));
  await load();
  act(() => options().callback("t1"));
  await again();
  await settle();
  expect(tokens.at(-1)).toBe("");
  expect(draw).toHaveBeenCalledTimes(2);
  expect(draw.mock.calls[0][0]).not.toBe(draw.mock.calls[1][0]);
  expect(scripts).toHaveLength(1);
});

it("follows the dark theme", async () => {
  theme.resolvedTheme = "dark";
  await show("site-key");
  await load();
  expect(options().theme).toBe("dark");
});

it("says so when it can't load", async () => {
  await show("site-key");
  await act(async () => scripts[0].onerror?.(new Event("error")));
  await settle();
  expect(host.querySelector('[role="alert"]')?.textContent).toContain("couldn't load");
});
