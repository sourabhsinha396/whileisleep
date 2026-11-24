// Copies the country flags to public/flags, so a page loads only the few it shows.
// SVGs, not emoji: Windows has no flag emoji and shows the letters instead.
import { cpSync, mkdirSync, readdirSync } from "node:fs";

const from = "node_modules/country-flag-icons/3x2";
mkdirSync("public/flags", { recursive: true });
for (const file of readdirSync(from)) {
  if (/^[A-Z]{2}\.svg$/.test(file)) cpSync(`${from}/${file}`, `public/flags/${file}`);
}
