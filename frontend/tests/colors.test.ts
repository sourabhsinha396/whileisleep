import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { colorChoices, WIDGET_COLORS } from "@/lib/colors";
import { contrast, inkOf, textOn } from "@/lib/contrast";

describe("widget colors", () => {
  it("are the ones the server accepts", () => {
    const source = readFileSync("../backend/apps/workspaces/colors.py", "utf8");
    const server = [...source.matchAll(/"(#[0-9a-f]{6})": "([\w ]+)"/g)].map(([, value, name]) => ({ value, name }));
    expect(server.length).toBeGreaterThan(0);
    expect(WIDGET_COLORS).toEqual(server);
  });

  it.each(WIDGET_COLORS)("$name is readable under its text, and as text on white", ({ value }) => {
    expect(contrast(value, textOn(value))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(inkOf(value), "#ffffff")).toBeGreaterThanOrEqual(4.5);
  });

  it("have distinct names", () => {
    expect(new Set(WIDGET_COLORS.map((c) => c.name)).size).toBe(WIDGET_COLORS.length);
  });

  it("put white text on deep colors and dark text on bright ones", () => {
    expect(textOn("#2563eb")).toBe("#ffffff");
    expect(inkOf("#2563eb")).toBe("#2563eb");
    expect(textOn("#39ff14")).toBe("#1b2333");
    expect(textOn("#fff")).toBe("#1b2333");
  });

  it("offer just the list when the workspace's color is in it", () => {
    expect(colorChoices("#2563EB")).toBe(WIDGET_COLORS);
  });

  it("keep a color from before the list as a choice", () => {
    expect(colorChoices("#1e6fd9")[0]).toEqual({ value: "#1e6fd9", name: "Current" });
    expect(colorChoices("#1e6fd9")).toHaveLength(WIDGET_COLORS.length + 1);
  });
});
