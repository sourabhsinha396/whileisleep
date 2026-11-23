import { describe, expect, it } from "vitest";
import { syncSummary } from "@/components/mcp-servers";

describe("syncSummary", () => {
  it("says what a sync did", () => {
    expect(syncSummary({ added: 3, changed: 1, removed: 0 })).toBe("3 tools added, 1 changed.");
    expect(syncSummary({ added: 1, changed: 0, removed: 2 })).toBe("1 tool added, 2 removed.");
  });

  it("says so when nothing changed", () => {
    expect(syncSummary({ added: 0, changed: 0, removed: 0 })).toBe("No changes.");
  });
});
