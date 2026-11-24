import { countries, hasFlag } from "country-flag-icons";
import type { Attribute } from "./api";

export interface Country {
  /** ISO 3166 alpha-2, upper case. Empty when we don't know which country the text means. */
  code: string;
  name: string;
}

const names = new Intl.DisplayNames("en", { type: "region" });

// How sites also write a country, beyond its code and English name.
const ALIASES: Record<string, string> = {
  usa: "US",
  "united states of america": "US",
  uk: "GB",
  "great britain": "GB",
  england: "GB",
  uae: "AE",
  "czech republic": "CZ",
  turkey: "TR",
  "ivory coast": "CI",
  "hong kong": "HK",
  macau: "MO",
  myanmar: "MM",
  palestine: "PS",
};

const simple = (text: string) => text.trim().toLowerCase().replace(/&/g, "and");

// In the package's list but not on flagcdn.com, where CountryFlag gets its images.
const NOT_ON_FLAGCDN = ["AC", "IC", "TA", "XA", "XC", "XO"];
const isCountry = (code: string) => /^[A-Z]{2}$/.test(code) && hasFlag(code) && !NOT_ON_FLAGCDN.includes(code);

const byName = new Map<string, string>();
for (const code of countries) {
  if (isCountry(code)) byName.set(simple(names.of(code) ?? code), code);
}
for (const [alias, code] of Object.entries(ALIASES)) byName.set(alias, code);

/** The country a "country" attribute means: a code ("IN", "in") or an English name ("India").
 * Text we don't recognise is kept as the name, without a code. Null when there is none. */
export function countryOf(attributes: Attribute[]): Country | null {
  const value = attributes.find((a) => a.key === "country")?.value;
  if (typeof value !== "string" || !value.trim()) return null;
  const text = value.trim();
  const upper = text.toUpperCase();
  // Names first: "UK" is an alias, not a code.
  const code = byName.get(simple(text)) ?? (isCountry(upper) ? upper : "");
  return { code, name: code ? (names.of(code) ?? text) : text };
}
