"use client";

import { Check } from "lucide-react";
import { colorChoices } from "@/lib/colors";

/** Swatches for the widget color. `saved` is the workspace's stored color, which stays a
 * choice even if it isn't one of the listed ones. Radio inputs, so arrow keys work. */
export function ColorPicker({ value, saved, disabled, onChange }: { value: string; saved: string; disabled?: boolean; onChange: (color: string) => void }) {
  const choices = colorChoices(saved);
  const isPicked = (color: string) => color.toLowerCase() === value.toLowerCase();
  return (
    <fieldset disabled={disabled} className="disabled:opacity-60">
      <legend className="mb-1.5 text-sm font-medium">
        Widget color <span className="font-normal text-muted-foreground">· {choices.find((c) => isPicked(c.value))?.name}</span>
      </legend>
      <div className="flex flex-wrap gap-2.5 p-1">
        {choices.map(({ value: color, name }) => (
          <label
            key={color}
            title={name}
            style={{ background: color }}
            className="relative grid size-9 cursor-pointer place-items-center rounded-full text-white ring-offset-2 ring-offset-surface has-checked:ring-2 has-checked:ring-foreground has-focus-visible:ring-2 has-focus-visible:ring-ring has-disabled:cursor-not-allowed"
          >
            <input type="radio" name="widget-color" className="sr-only" aria-label={name} checked={isPicked(color)} onChange={() => onChange(color)} />
            {isPicked(color) && <Check size={17} strokeWidth={3} aria-hidden />}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
