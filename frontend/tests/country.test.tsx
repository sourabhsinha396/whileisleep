import { existsSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CountryFlag } from "@/components/country-flag";
import type { Attribute } from "@/lib/api";
import { countryOf } from "@/lib/country";

const country = (value: Attribute["value"]): Attribute[] => [
  { key: "plan", value: "pro", source: "host" },
  { key: "country", value, source: "host" },
];

describe("countryOf", () => {
  it.each([
    ["IN", "IN", "India"],
    ["in", "IN", "India"],
    [" India ", "IN", "India"],
    ["united states", "US", "United States"],
    ["USA", "US", "United States"],
    ["UK", "GB", "United Kingdom"],
    ["Trinidad and Tobago", "TT", "Trinidad & Tobago"],
  ])("reads %j", (value, code, name) => {
    expect(countryOf(country(value))).toEqual({ code, name });
  });

  it.each(["Atlantis", "ZZ", "constructor", "../x"])("keeps %j as text, without a flag", (value) => {
    expect(countryOf(country(value))).toEqual({ code: "", name: value });
  });

  it("is null without a usable value", () => {
    expect(countryOf([])).toBeNull();
    expect(countryOf(country("  "))).toBeNull();
    expect(countryOf(country(91))).toBeNull();
  });
});

describe("CountryFlag", () => {
  it("shows the flag, named for screen readers", () => {
    const html = renderToStaticMarkup(<CountryFlag country={{ code: "IN", name: "India" }} />);
    expect(html).toContain('src="/flags/IN.svg"');
    expect(html).toContain('alt="India"');
    // Where scripts/flags.mjs copies it from.
    expect(existsSync("node_modules/country-flag-icons/3x2/IN.svg")).toBe(true);
  });

  it("shows nothing for an unknown country", () => {
    expect(renderToStaticMarkup(<CountryFlag country={null} />)).toBe("");
    expect(renderToStaticMarkup(<CountryFlag country={{ code: "", name: "Atlantis" }} />)).toBe("");
  });
});
