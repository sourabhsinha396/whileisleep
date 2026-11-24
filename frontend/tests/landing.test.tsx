import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Faq } from "@/components/landing/faq";
import { NightPanel } from "@/components/landing/night-panel";
import { PricingPlans } from "@/components/landing/pricing-plans";
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

describe("night panel", () => {
  const panel = render(<NightPanel><p>inbox</p></NightPanel>);

  it("shows what it frames", () => {
    expect(panel.textContent).toBe("inbox");
    expect(panel.querySelector("p")?.closest("[aria-hidden]")).toBeNull();
  });

  it("keeps the sky away from assistive tech and clicks", () => {
    for (const svg of panel.querySelectorAll("svg")) {
      expect(svg.closest("[aria-hidden=true].pointer-events-none")).not.toBeNull();
    }
  });
});
