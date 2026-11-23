import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { colorChoices, WIDGET_COLORS } from "@/lib/colors";

describe("widget colors", () => {
  it("are the ones the server accepts", () => {
    const source = readFileSync("../backend/apps/workspaces/colors.py", "utf8");
    const server = [...source.matchAll(/"(#[0-9a-f]{6})": "(\w+)"/g)].map(([, value, name]) => ({ value, name }));
    expect(server.length).toBeGreaterThan(0);
    expect(WIDGET_COLORS).toEqual(server);
  });

  it("offer just the list when the workspace's color is in it", () => {
    expect(colorChoices("#2563EB")).toBe(WIDGET_COLORS);
  });

  it("keep a color from before the list as a choice", () => {
    expect(colorChoices("#1e6fd9")[0]).toEqual({ value: "#1e6fd9", name: "Current" });
    expect(colorChoices("#1e6fd9")).toHaveLength(WIDGET_COLORS.length + 1);
  });
});
