import { describe, expect, it } from "vitest";
import { type Billing, canSubscribe, checkoutResult, headline, sidebarNotice } from "@/lib/billing";

const TRIAL: Billing = {
  state: "trial",
  trial_days_left: 9,
  trial_ends_at: "2026-12-08T10:00:00Z",
  can_manage: false,
  subscription: null,
  prices: { monthly: 200, yearly: 1200 },
};

function paid(status: string, state: Billing["state"] = "active", cancels = false): Billing {
  return {
    ...TRIAL,
    state,
    trial_days_left: null,
    can_manage: true,
    subscription: { status, interval: "yearly", paid_until: "2027-11-24T10:00:00Z", cancels_at_period_end: cancels },
  };
}

describe("headline", () => {
  it("counts down the trial", () => {
    expect(headline(TRIAL).text).toBe("9 days left in your free trial.");
    expect(headline({ ...TRIAL, trial_days_left: 1 }).text).toBe("1 day left in your free trial.");
  });

  it("says why the AI is paused", () => {
    expect(headline({ ...TRIAL, state: "paused" }).text).toContain("free trial has ended");
    expect(headline(paid("expired", "paused")).text).toContain("plan has ended");
    expect(headline(paid("on_hold", "paused")).text).toContain("Update your card");
    expect(headline(paid("paused", "paused")).text).toContain("Resume");
  });

  it("doesn't say the AI is paused when the trial still runs", () => {
    expect(headline({ ...paid("on_hold", "trial"), trial_days_left: 3 }).text).not.toContain("paused");
  });

  it("tells renewing, cancelled and failing plans apart", () => {
    expect(headline(paid("active"))).toMatchObject({ tone: "success" });
    expect(headline(paid("active")).text).toContain("2027");
    for (const billing of [paid("active", "active", true), paid("cancelled")]) {
      expect(headline(billing).text).toContain("cancelled");
      expect(headline(billing).text).toContain("2027");
    }
    expect(headline(paid("past_due"))).toMatchObject({ tone: "warning" });
  });
});

describe("offering plans", () => {
  it("offers them in the trial and after it, but never next to a running plan", () => {
    expect(canSubscribe(TRIAL)).toBe(true);
    expect(canSubscribe({ ...TRIAL, state: "paused" })).toBe(true);
    expect(canSubscribe(paid("expired", "paused"))).toBe(true);
    expect(canSubscribe(paid("cancelled"))).toBe(true);
    for (const status of ["active", "past_due", "on_hold", "paused"]) expect(canSubscribe(paid(status))).toBe(false);
    expect(canSubscribe({ ...TRIAL, state: "off" })).toBe(false);
  });
});

describe("sidebar notice", () => {
  it("speaks up only when it matters", () => {
    expect(sidebarNotice({ billing_state: "off", trial_days_left: null })).toBe("");
    expect(sidebarNotice({ billing_state: "active", trial_days_left: null })).toBe("");
    expect(sidebarNotice({ billing_state: "trial", trial_days_left: 6 })).toBe("");
    expect(sidebarNotice({ billing_state: "trial", trial_days_left: 5 })).toBe("5 days left in the free trial.");
    expect(sidebarNotice({ billing_state: "paused", trial_days_left: null })).toContain("paused");
  });
});

describe("back from checkout", () => {
  it("reads what Dodo adds to the address", () => {
    expect(checkoutResult("?subscription_id=sub_abc1&status=active&email=a%40b.c")).toEqual({ subscriptionId: "sub_abc1", failed: false });
    expect(checkoutResult("?subscription_id=sub_abc1&status=failed")).toMatchObject({ failed: true });
    expect(checkoutResult("?status=cancelled")).toEqual({ subscriptionId: "", failed: true });
  });

  it("ignores an ordinary visit and odd ids", () => {
    expect(checkoutResult("")).toBeNull();
    expect(checkoutResult("?subscription_id=../../x&status=active")).toEqual({ subscriptionId: "", failed: false });
  });
});
