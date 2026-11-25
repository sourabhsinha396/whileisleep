import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ForgotPasswordPage from "@/app/forgot-password/page";
import ResetPasswordPage from "@/app/reset-password/page";
import { ForgotLink } from "@/components/forgot-link";
import { getToken, setToken } from "@/lib/api";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const router = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("next-themes", () => ({ useTheme: () => ({ resolvedTheme: "light" }) }));

let root: Root;
let host: HTMLElement;
let sent: [string, unknown][];

const settle = () => act(async () => void (await new Promise((resolve) => setTimeout(resolve, 5))));

async function show(element: React.ReactNode, answer: Response) {
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    if (url.endsWith("/auth/captcha")) return Response.json({ site_key: "" });
    sent.push([url, init?.body ? JSON.parse(String(init.body)) : undefined]);
    return answer.clone();
  });
  await act(async () => root.render(element));
  await settle();
}

async function fill(value: string) {
  const input = host.querySelector("input")!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => void host.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  await settle();
}

beforeEach(() => {
  sent = [];
  router.replace.mockClear();
  setToken("");
  host = document.body.appendChild(document.createElement("div"));
  root = createRoot(host);
});

afterEach(async () => {
  await act(async () => root.unmount());
  window.location.hash = "";
  vi.unstubAllGlobals();
});

describe("the link on the log-in page", () => {
  it.each([true, false])("is there when emails can be sent (%s)", async (can_reset) => {
    await show(<ForgotLink />, Response.json({ can_reset }));
    expect(Boolean(host.querySelector('a[href="/forgot-password"]'))).toBe(can_reset);
  });
});

describe("asking for a link", () => {
  it("doesn't say whether there is an account", async () => {
    await show(<ForgotPasswordPage />, Response.json({ ok: true }));
    await fill("ana@example.com");
    expect(sent).toEqual([["/api/v1/auth/password/forgot", { email: "ana@example.com", captcha: "" }]]);
    expect(host.textContent).toContain("If ana@example.com has an account");
  });

  it("says what went wrong, and keeps the form", async () => {
    await show(<ForgotPasswordPage />, Response.json({ detail: "Too many tries." }, { status: 429 }));
    await fill("ana@example.com");
    expect(host.querySelector('[role="alert"]')?.textContent).toBe("Too many tries.");
    expect(host.querySelector("form")).not.toBeNull();
  });
});

describe("choosing a new password", () => {
  it("sends what follows the #, and logs in", async () => {
    window.location.hash = "MQ.abc-123";
    await show(<ResetPasswordPage />, Response.json({ token: "at_9", user: {} }));
    await fill("a-new-password");
    expect(sent).toEqual([["/api/v1/auth/password/reset", { key: "MQ.abc-123", password: "a-new-password" }]]);
    expect(getToken()).toBe("at_9");
    expect(router.replace).toHaveBeenCalledWith("/app");
  });

  it("offers a new link when this one is no good", async () => {
    window.location.hash = "MQ.old";
    await show(<ResetPasswordPage />, Response.json({ detail: "This link has expired." }, { status: 400 }));
    await fill("a-new-password");
    expect(host.textContent).toContain("This link has expired.");
    expect(host.querySelector('a[href="/forgot-password"]')).not.toBeNull();
    expect(getToken()).toBe("");
  });

  it("needs a link", async () => {
    await show(<ResetPasswordPage />, Response.json({}));
    expect(host.textContent).toContain("This link isn't complete");
    expect(host.querySelector("form")).toBeNull();
  });
});
