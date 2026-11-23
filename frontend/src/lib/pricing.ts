/** Plans on the pricing page. Launch prices: change them here. */

export type Billing = "monthly" | "yearly";

/** The hosted plan, in US dollars. Yearly is billed once for twelve months. */
export const CLOUD_PRICE = { monthly: 2, yearlyPerMonth: 1 };

/** Where the self-hosted card sends people (the public repository). Unset: no button. */
export const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL ?? "";

export interface CloudPrice {
  /** The big number on the card, per month. */
  perMonth: number;
  /** The line under it. */
  billed: string;
  /** Saved per year against paying monthly; 0 when paying monthly. */
  savedPerYear: number;
}

export function cloudPrice(billing: Billing, price = CLOUD_PRICE): CloudPrice {
  if (billing === "monthly") {
    return { perMonth: price.monthly, billed: "Billed monthly", savedPerYear: 0 };
  }
  const yearly = price.yearlyPerMonth * 12;
  return {
    perMonth: price.yearlyPerMonth,
    billed: `Billed ${dollars(yearly)} once a year`,
    savedPerYear: (price.monthly - price.yearlyPerMonth) * 12,
  };
}

/** Percent saved by paying yearly, for the toggle. */
export function yearlySaving(price = CLOUD_PRICE): number {
  return Math.round((1 - price.yearlyPerMonth / price.monthly) * 100);
}

export function dollars(amount: number): string {
  return Number.isInteger(amount) ? `$${amount}` : `$${amount.toFixed(2)}`;
}
