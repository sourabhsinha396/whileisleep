"use client";

import { Select } from "@/components/select";
import { colorChoices } from "@/lib/colors";

function Swatch({ color }: { color: string }) {
  return <span aria-hidden className="size-5 shrink-0 rounded-full ring-1 ring-foreground/15 ring-inset" style={{ background: color }} />;
}

/** The widget's color. `saved` is the workspace's stored color, which stays a choice even if it isn't a listed one. */
export function ColorPicker({ value, saved, disabled, onChange }: { value: string; saved: string; disabled?: boolean; onChange: (color: string) => void }) {
  const choices = colorChoices(saved);
  const picked = choices.find((c) => c.value.toLowerCase() === value.toLowerCase()) ?? choices[0];
  return (
    <div>
      <span className="mb-1.5 block text-sm font-medium">Widget color</span>
      <Select
        label="Widget color"
        value={picked.value}
        options={choices.map(({ value: color, name }) => ({ value: color, label: name, icon: <Swatch color={color} /> }))}
        disabled={disabled}
        onChange={onChange}
      />
    </div>
  );
}
