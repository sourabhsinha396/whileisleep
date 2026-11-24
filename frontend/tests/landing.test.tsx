import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Ripple } from "@/components/landing/ripple";

function render(node: React.ReactNode): HTMLElement {
  const root = document.createElement("div");
  root.innerHTML = renderToStaticMarkup(node);
  return root;
}

describe("hero ripple", () => {
  it("is hidden from assistive tech and never takes clicks", () => {
    const ripple = render(<Ripple />).firstElementChild;
    expect(ripple?.getAttribute("aria-hidden")).toBe("true");
    expect(ripple?.className).toContain("pointer-events-none");
    expect(ripple?.querySelectorAll(".land-ripple").length).toBeGreaterThan(0);
  });
});
