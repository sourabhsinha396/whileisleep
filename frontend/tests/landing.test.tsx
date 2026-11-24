import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Faq } from "@/components/landing/faq";
import { PricingPlans } from "@/components/landing/pricing-plans";
import { FlickeringGrid } from "@/components/magicui/flickering-grid";
import { ShineBorder } from "@/components/magicui/shine-border";
import { HOME_QUESTIONS, PRICING_QUESTIONS } from "@/lib/faq";

function render(node: React.ReactNode): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML = renderToStaticMarkup(node);
  return root;
}

describe("homepage FAQ", () => {
  it("renders every question closed, with its answer", () => {
    const items = [...render(<Faq />).querySelectorAll("details")];
    expect(items.map((d) => d.querySelector("summary")?.textContent)).toEqual(HOME_QUESTIONS.map(({ q }) => q));
    expect(items.map((d) => d.querySelector("p")?.textContent)).toEqual(HOME_QUESTIONS.map(({ a }) => a));
    expect(items.some((d) => d.open)).toBe(false);
  });

  it("asks nothing twice", () => {
    for (const list of [HOME_QUESTIONS, PRICING_QUESTIONS]) {
      expect(new Set(list.map(({ q }) => q)).size).toBe(list.length);
    }
  });
});

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

describe("hero decoration", () => {
  it("renders on the server", () => {
    expect(render(<FlickeringGrid aria-hidden />).querySelector("[aria-hidden] canvas")).not.toBeNull();
  });

  it("never takes clicks from the inbox under it, and stands still for reduced motion", () => {
    const border = render(<ShineBorder />).firstElementChild;
    expect(border?.className).toContain("pointer-events-none");
    expect(border?.className).toContain("motion-safe:animate-shine");
  });
});
