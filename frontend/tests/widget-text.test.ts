import { describe, expect, it } from "vitest";
import { formatText, safeHref } from "@/widget/text";

function html(text: string, base?: string) {
  const div = document.createElement("div");
  div.append(...formatText(text, base));
  return div;
}

describe("formatText", () => {
  it("splits paragraphs and lines", () => {
    const node = html("One\ntwo\n\nThree");
    expect(node.querySelectorAll("p")).toHaveLength(2);
    expect(node.querySelectorAll("br")).toHaveLength(1);
  });

  it("links markdown links and bare urls", () => {
    const node = html("See [pricing](https://shop.example.com/pricing) or https://shop.example.com/faq.");
    const links = Array.from(node.querySelectorAll("a"));
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "https://shop.example.com/pricing",
      "https://shop.example.com/faq",
    ]);
    expect(links[0].rel).toBe("noopener noreferrer");
  });

  it("resolves relative links against the workspace website", () => {
    const node = html("Try [AZ-104](/exams/az-104)", "https://examgrill.com");
    expect(node.querySelector("a")!.getAttribute("href")).toBe("https://examgrill.com/exams/az-104");
  });

  it("bolds", () => {
    expect(html("**5 to 8 business days**").querySelector("strong")!.textContent).toBe("5 to 8 business days");
  });

  it("drops unsafe link targets and never parses html", () => {
    const node = html('[click](javascript:alert(1)) <b onclick="x">hi</b>');
    expect(node.querySelector("a")).toBeNull();
    expect(node.querySelector("b")).toBeNull();
    expect(node.textContent).toContain("<b onclick=");
  });
});

describe("safeHref", () => {
  it("allows http(s) only", () => {
    expect(safeHref("https://a.example.com")).toBe("https://a.example.com/");
    expect(safeHref("mailto:a@b.c")).toBeNull();
    expect(safeHref("data:text/html,x")).toBeNull();
  });
});
