import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import BillingPage from "@/app/w/[slug]/billing/page";
import type { Billing } from "@/lib/billing";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", async (original) => ({ ...(await original<object>()), api }));
vi.mock("@/components/workspace-context", () => ({
  useWorkspace: () => ({ workspace: { slug: "acme", is_organization_owner: true }, reload: async () => {} }),
}));

const TRIAL: Billing = {
  state: "trial",
  trial_days_left: 9,
  trial_ends_at: "2026-12-08T10:00:00Z",
  can_manage: false,
  subscription: null,
  prices: { monthly: 200, yearly: 1200 },
};
const ACTIVE: Billing = {
  ...TRIAL,
  state: "active",
  can_manage: true,
  subscription: { status: "active", interval: "yearly", paid_until: "2027-11-24T10:00:00Z", cancels_at_period_end: false },
};

/** What the server knows, and what it says once it has asked Dodo. */
let known: Billing;
let sync: () => Promise<Billing>;
let checkout: () => Promise<unknown>;
let root: Root;

const asked = () => api.mock.calls.filter(([path]) => path === "/billing/sync").map(([, init]) => init.body);
const text = () => document.body.textContent ?? "";
const wait = (ms: number) => act(async () => vi.advanceTimersByTimeAsync(ms));

async function open(search = "") {
  window.history.replaceState(null, "", `/w/acme/billing${search}`);
  await act(async () => root.render(<BillingPage />));
  await wait(0);
}

beforeEach(() => {
  vi.useFakeTimers();
  known = TRIAL;
  sync = async () => known;
  checkout = async () => ({ url: "" });
  api.mockReset();
  api.mockImplementation(async (path: string) => {
    if (path === "/billing/sync") return sync();
    if (path === "/billing/checkout") return checkout();
    return path === "/billing" ? known : {};
  });
  root = createRoot(document.body.appendChild(document.createElement("div")));
});

afterEach(async () => {
  await act(async () => root.unmount());
  document.body.innerHTML = "";
  vi.useRealTimers();
});

describe("the billing page", () => {
  it("asks for the plan when it opens, for someone who paid and never came back", async () => {
    sync = async () => ACTIVE;
    await open();
    expect(asked()).toEqual([{}]);
    expect(text()).toContain("Your plan is active");
    expect(text()).not.toContain("Subscribe");
  });

  it("shows what is known when it can't be asked", async () => {
    sync = () => Promise.reject(new Error("The payment service didn't answer"));
    await open();
    expect(text()).toContain("9 days left");
    expect(text()).not.toContain("didn't answer");
  });

  it("confirms the payment someone comes back with, and cleans the address", async () => {
    sync = async () => ACTIVE;
    await open("?subscription_id=sub_1&status=active");
    expect(asked()).toEqual([{ subscription_id: "sub_1" }]);
    expect(text()).toContain("Your plan is active");
    expect(text()).not.toContain("Confirming");
    expect(window.location.search).toBe("");
  });

  it("keeps asking about a slow payment until it has gone through", async () => {
    await open("?subscription_id=sub_1&status=pending");
    expect(text()).toContain("Confirming your payment");
    await wait(15000);
    expect(text()).toContain("still being processed");
    sync = async () => ACTIVE;
    await wait(30000);
    expect(text()).toContain("Your plan is active");
    expect(text()).not.toContain("still being processed");
    const before = asked().length;
    await wait(120000);
    expect(asked().length).toBe(before);
  });

  it("shows the plan that was found instead of a second checkout", async () => {
    await open();
    checkout = async () => {
      known = ACTIVE;
      throw new Error("You already have a plan.");
    };
    const subscribe = [...document.querySelectorAll("button")].find((button) => button.textContent === "Subscribe")!;
    await act(async () => subscribe.click());
    await wait(0);
    expect(text()).toContain("You already have a plan.");
    expect(text()).toContain("Your plan is active");
  });
});
