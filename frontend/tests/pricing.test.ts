import { describe, expect, it } from "vitest";
import { CLOUD_PRICE, cloudPrice, dollars, yearlySaving } from "@/lib/pricing";

describe("cloud pricing", () => {
  it("is $2 a month paid monthly", () => {
    expect(cloudPrice("monthly")).toEqual({ perMonth: 2, billed: "Billed monthly", savedPerYear: 0 });
  });

  it("is $1 a month paid yearly, billed $12 once", () => {
    expect(cloudPrice("yearly")).toEqual({ perMonth: 1, billed: "Billed $12 once a year", savedPerYear: 12 });
  });

  it("says how much yearly saves", () => {
    expect(yearlySaving()).toBe(50);
    expect(yearlySaving({ monthly: 15, yearlyPerMonth: 12 })).toBe(20);
  });

  it("follows the prices set in one place", () => {
    const price = { ...CLOUD_PRICE, monthly: 9, yearlyPerMonth: 7.5 };
    expect(cloudPrice("yearly", price)).toMatchObject({ perMonth: 7.5, billed: "Billed $90 once a year", savedPerYear: 18 });
  });
});

describe("dollars", () => {
  it("shows cents only when there are some", () => {
    expect(dollars(12)).toBe("$12");
    expect(dollars(7.5)).toBe("$7.50");
  });
});
