import { act, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import GoogleLoginPage from "@/app/login/google/page";
import { GoogleButton } from "@/components/google-button";
import { getToken, setToken } from "@/lib/api";
import { loginError } from "@/lib/google";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

const router = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));

let root: Root;
let host: HTMLElement;

async function show(element: React.ReactNode, answer: () => Response) {
  const fetched = vi.fn(async (...args: [string, RequestInit?]) => (void args, answer()));
  vi.stubGlobal("fetch", fetched);
  await act(async () => root.render(<StrictMode>{element}</StrictMode>));
  await act(async () => void (await new Promise((resolve) => setTimeout(resolve, 5))));
  return fetched;
}

beforeEach(() => {
  router.replace.mockClear();
  setToken("");
  host = document.body.appendChild(document.createElement("div"));
  root = createRoot(host);
});

afterEach(async () => {
  await act(async () => root.unmount());
  vi.unstubAllGlobals();
});

describe("the button", () => {
  it("leads to the server, where Google is set up", async () => {
    await show(<GoogleButton />, () => Response.json({ enabled: true }));
    expect(host.querySelector("a")?.getAttribute("href")).toBe("/api/v1/auth/google/start");
    expect(host.textContent).toContain("Continue with Google");
  });

  it("isn't there where it isn't, or when the server can't say", async () => {
    await show(<GoogleButton />, () => Response.json({ enabled: false }));
    expect(host.innerHTML).toBe("");
    await show(<GoogleButton key="2" />, () => Response.json({}, { status: 500 }));
    expect(host.innerHTML).toBe("");
  });
});

describe("coming back", () => {
  it("swaps the cookie for a token, once", async () => {
    const fetched = await show(<GoogleLoginPage />, () => Response.json({ token: "at_1", user: {} }));
    expect(fetched).toHaveBeenCalledTimes(1);
    expect(fetched.mock.calls[0][0]).toBe("/api/v1/auth/google/session");
    expect(getToken()).toBe("at_1");
    expect(router.replace).toHaveBeenCalledWith("/app");
  });

  it("goes back to the form when the cookie is gone", async () => {
    await show(<GoogleLoginPage />, () => Response.json({ detail: "x" }, { status: 401 }));
    expect(getToken()).toBe("");
    expect(router.replace).toHaveBeenCalledWith("/login?error=google_expired");
  });
});

describe("what the form says", () => {
  it("is nothing without an error", () => expect(loginError("")).toBe(""));
  it("is why it didn't work", () => expect(loginError("?error=google_use_password")).toContain("password"));
  it.each(["Call+555-1234", "constructor", "<b>"])("is never someone else's words (%s)", (reason) => {
    expect(loginError(`?error=${reason}`)).toBe("Logging in with Google didn't work. Try again in a minute.");
  });
});
