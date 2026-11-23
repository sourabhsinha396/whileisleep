import { describe, expect, it } from "vitest";
import { chimeFor } from "@/widget/sound";

describe("chimeFor", () => {
  const replies = [
    { id: 5, sender: "visitor" as const },
    { id: 6, sender: "bot" as const },
    { id: 7, sender: "agent" as const },
  ];

  it("rings for the newest reply while the tab is hidden", () => {
    expect(chimeFor(replies, true, 0)).toBe(7);
  });

  it("stays quiet while the visitor is looking at the page", () => {
    expect(chimeFor(replies, false, 0)).toBe(0);
  });

  it("ignores the visitor's own messages and system notes", () => {
    expect(chimeFor([{ id: 8, sender: "visitor" }, { id: 9, sender: "system" }], true, 0)).toBe(0);
  });

  it("doesn't ring twice for a reply another tab already rang for", () => {
    expect(chimeFor(replies, true, 7)).toBe(0);
    expect(chimeFor(replies, true, 6)).toBe(7);
  });
});
