"use client";

import clsx from "clsx";
import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { inputClass } from "@/components/ui";
import { colorChoices } from "@/lib/colors";

function Swatch({ color }: { color: string }) {
  return <span aria-hidden className="size-5 shrink-0 rounded-full ring-1 ring-foreground/15 ring-inset" style={{ background: color }} />;
}

/** A dropdown for the widget color. Not a <select>, whose options can't show a swatch.
 * `saved` is the workspace's stored color, which stays a choice even if it isn't a listed one. */
export function ColorPicker({ value, saved, disabled, onChange }: { value: string; saved: string; disabled?: boolean; onChange: (color: string) => void }) {
  const id = useId();
  const choices = colorChoices(saved);
  const picked = Math.max(0, choices.findIndex((c) => c.value.toLowerCase() === value.toLowerCase()));
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(picked);
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (open) list.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  function show() {
    setActive(picked);
    setOpen(true);
  }

  function pick(index: number) {
    onChange(choices[index].value);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    const last = choices.length - 1;
    const moves: Record<string, number> = { ArrowDown: Math.min(active + 1, last), ArrowUp: Math.max(active - 1, 0), Home: 0, End: last };
    if (!open) {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return; // Enter and Space click the button.
      show();
    } else if (e.key in moves) setActive(moves[e.key]);
    else if (e.key === "Enter" || e.key === " ") pick(active);
    else if (e.key === "Escape") setOpen(false);
    else return;
    e.preventDefault();
  }

  return (
    <div ref={root} className="relative" onBlur={(e) => !root.current?.contains(e.relatedTarget) && setOpen(false)}>
      <span id={`${id}-label`} className="mb-1.5 block text-sm font-medium">Widget color</span>
      <button
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-labelledby={`${id}-label ${id}-value`}
        aria-activedescendant={open ? `${id}-${active}` : undefined}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={onKeyDown}
        className={clsx(inputClass, "flex! items-center gap-2.5 text-left disabled:cursor-not-allowed")}
      >
        <Swatch color={choices[picked].value} />
        <span id={`${id}-value`} className="flex-1">{choices[picked].name}</span>
        <ChevronDown size={16} aria-hidden className={clsx("text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ul
          ref={list}
          id={`${id}-list`}
          role="listbox"
          aria-labelledby={`${id}-label`}
          // Keeps focus on the button, so clicking an option isn't a blur.
          onMouseDown={(e) => e.preventDefault()}
          className="absolute top-full left-0 z-20 mt-1.5 max-h-64 w-full overflow-y-auto rounded-lg border bg-surface p-1 shadow-lg"
        >
          {choices.map(({ value: color, name }, i) => (
            <li
              key={color}
              id={`${id}-${i}`}
              role="option"
              aria-selected={i === picked}
              onMouseMove={() => setActive(i)}
              onClick={() => pick(i)}
              className={clsx("flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm", i === active && "bg-muted")}
            >
              <Swatch color={color} />
              <span className="flex-1">{name}</span>
              {i === picked && <Check size={15} aria-hidden className="text-primary-text" />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
