import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SiteChat } from "@/components/site-chat";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const nav = vi.hoisted(() => ({ path: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => nav.path }));

let root: Root;
const chat = { hide: vi.fn(), show: vi.fn() };
const scripts = () => [...document.querySelectorAll<HTMLScriptElement>("script[data-workspace]")];

async function visit(path: string, workspace = "ws_1") {
  nav.path = path;
  await act(async () => root.render(<SiteChat key="chat" workspace={workspace} />));
}

beforeEach(() => {
  vi.clearAllMocks();
  // Nothing is fetched: only what is put on the page matters here.
  const append = document.body.appendChild.bind(document.body);
  vi.spyOn(document.body, "appendChild").mockImplementation((node) => {
    if (node instanceof HTMLScriptElement) node.type = "text/plain";
    return append(node);
  });
  root = createRoot(document.createElement("div"));
});

afterEach(async () => {
  await act(async () => root.unmount());
  scripts().forEach((script) => script.remove());
  delete window.whileisleep;
  vi.restoreAllMocks();
});

it.each(["/", "/pricing", "/docs/install", "/login", "/privacy", "/widgets"])("is on %s, once", async (path) => {
  await visit(path);
  await visit("/about");
  expect(scripts().map((script) => [script.getAttribute("src"), script.dataset.workspace])).toEqual([["/widget.js", "ws_1"]]);
});

it.each(["/w/acme/inbox", "/app", "/new", "/demo", "/integrations/callback", "/reset-password", "/login/google"])("isn't on %s", async (path) => {
  await visit(path);
  expect(scripts()).toEqual([]);
});

it("needs a workspace", async () => {
  await visit("/", "");
  expect(scripts()).toEqual([]);
});

it("hides in the dashboard and comes back, also when it loads late", async () => {
  await visit("/");
  await visit("/app");
  window.whileisleep = chat as unknown as Window["whileisleep"];
  window.dispatchEvent(new Event("whileisleep:ready"));
  expect(chat.hide).toHaveBeenCalledTimes(1);
  expect(chat.show).not.toHaveBeenCalled();
  await visit("/pricing");
  expect(chat.show).toHaveBeenCalledTimes(1);
});
