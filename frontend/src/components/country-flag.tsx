import type { Country } from "@/lib/country";

/** A small flag from flagcdn.com, or nothing when we don't know the country. Pass `label={false}` next to the
 * country's written name, so it isn't read out twice. */
export function CountryFlag({ country, label = true }: { country: Country | null; label?: boolean }) {
  if (!country?.code) return null;
  return (
    // A tiny static SVG: nothing for next/image to optimise.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`https://flagcdn.com/${country.code.toLowerCase()}.svg`}
      // flagcdn needn't learn which inbox page asked.
      referrerPolicy="no-referrer"
      alt={label ? country.name : ""}
      title={label ? country.name : undefined}
      width={18}
      height={12}
      className="h-3 w-[18px] shrink-0 rounded-[2px] object-cover ring-1 ring-foreground/10"
    />
  );
}
