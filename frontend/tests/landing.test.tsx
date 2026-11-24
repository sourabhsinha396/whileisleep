import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PricingPlans } from "@/components/landing/pricing-plans";
import { Ripple } from "@/components/landing/ripple";

function render(node: React.ReactNode): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML = renderToStaticMarkup(node);
  return root;
}

describe("pricing plans", () => {
  const headings = (node: React.ReactNode, tag: string) => [...render(node).querySelectorAll(tag)].map((h) => h.textContent);

  it("are second-level headings on their own page", () => {
    expect(headings(<PricingPlans />, "h2")).toEqual(["Self-hosted", "Cloud"]);
  });

  it("sit one level lower under a section title", () => {
    expect(headings(<PricingPlans heading="h3" />, "h3")).toEqual(["Self-hosted", "Cloud"]);
    expect(headings(<PricingPlans heading="h3" />, "h2")).toEqual([]);
  });
});

describe("hero ripple", () => {
  it("is hidden from assistive tech and never takes clicks", () => {
    const ripple = render(<Ripple />).firstElementChild;
    expect(ripple?.getAttribute("aria-hidden")).toBe("true");
    expect(ripple?.className).toContain("pointer-events-none");
    expect(ripple?.querySelectorAll(".land-ripple").length).toBeGreaterThan(0);
  });
});
