import type { Workspace } from "@/lib/api";

/** "off": this installation doesn't sell plans, so nothing is limited. */
export type BillingState = "off" | "trial" | "active" | "paused";
export type Interval = "monthly" | "yearly";

/** The organization's plan (GET /billing). */
export interface Billing {
  state: BillingState;
  trial_days_left: number | null;
  trial_ends_at: string | null;
  /** They have paid before, so there is a portal to open. */
  can_manage: boolean;
  subscription: {
    status: string;
    interval: Interval;
    paid_until: string | null;
    cancels_at_period_end: boolean;
  } | null;
  /** In US cents, before tax. */
  prices: Record<Interval, number>;
}

export interface Headline {
  tone: "success" | "primary" | "warning" | "danger";
  text: string;
}

function day(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
}

export function daysLeft(days: number): string {
  return days === 1 ? "1 day" : `${days} days`;
}

/** Where they stand, in one line. */
export function headline(billing: Billing): Headline {
  const { state, subscription } = billing;
  if (state === "active" && subscription) {
    const until = subscription.paid_until && day(subscription.paid_until);
    if (subscription.status === "past_due") {
      return { tone: "warning", text: "Your last payment failed. Update your card, or the AI will pause." };
    }
    if (subscription.status === "cancelled" || subscription.cancels_at_period_end) {
      return { tone: "warning", text: until ? `Your plan is cancelled. The AI keeps answering until ${until}.` : "Your plan is cancelled." };
    }
    return { tone: "success", text: until ? `Your plan is active and renews on ${until}.` : "Your plan is active." };
  }
  if (subscription?.status === "on_hold") {
    const trial = state === "trial";
    return { tone: "danger", text: trial ? "Your payment failed. Update your card." : "Your payment failed, so the AI is paused. Update your card to bring it back." };
  }
  if (subscription?.status === "paused" && state === "paused") {
    return { tone: "warning", text: "Your plan is paused, and the AI with it. Resume it under Manage plan." };
  }
  if (state === "trial") {
    return { tone: "primary", text: `${daysLeft(billing.trial_days_left ?? 0)} left in your free trial.` };
  }
  const ended = subscription ? "Your plan has ended" : "Your free trial has ended";
  return { tone: "danger", text: `${ended}, so the AI is paused. New chats go to your team.` };
}

/** Whether to offer plans: not while one is running or only needs a new card. */
export function canSubscribe(billing: Billing): boolean {
  const status = billing.subscription?.status;
  return billing.state !== "off" && !["active", "past_due", "on_hold", "paused"].includes(status ?? "");
}

/** The sidebar says something only when it matters: the AI is paused, or the trial is nearly over. */
export function sidebarNotice(workspace: Pick<Workspace, "billing_state" | "trial_days_left">): string {
  if (workspace.billing_state === "paused") return "The AI is paused until a plan is active.";
  const left = workspace.trial_days_left;
  if (workspace.billing_state === "trial" && left !== null && left <= 5) return `${daysLeft(left)} left in the free trial.`;
  return "";
}

/** What Dodo adds to the address when it sends someone back from checkout. */
export function checkoutResult(search: string): { subscriptionId: string; failed: boolean } | null {
  const params = new URLSearchParams(search);
  const subscriptionId = params.get("subscription_id") ?? "";
  const status = params.get("status") ?? "";
  if (!subscriptionId && !status) return null;
  return { subscriptionId: /^sub_[A-Za-z0-9]+$/.test(subscriptionId) ? subscriptionId : "", failed: ["failed", "cancelled"].includes(status) };
}
