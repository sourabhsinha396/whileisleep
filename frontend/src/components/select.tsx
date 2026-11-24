"use client";

import clsx from "clsx";
import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { inputClass } from "@/components/ui";
import { nextStartingWith, opensAbove } from "@/lib/dropdown";

export interface Option<T extends string> {
  value: T;
  label: string;
  /** Shown before the label, e.g. a color. */
  icon?: React.ReactNode;
  /** A muted word at the end, e.g. "no key". */
  note?: string;
}

/** The app's dropdown. Not a <select>, whose list the browser draws in its own way and can't hold
 * more than text. `className` sizes it. */
export function Select<T extends string>({
  value,
  options,
  onChange,
  label,
  disabled,
  className,
}: {
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
  /** Its name for screen readers, when no <Field> around it gives one. */
  label?: string;
  disabled?: boolean;
  className?: string;
}) {
  const id = useId();
  const picked = Math.max(0, options.findIndex((o) => o.value === value));
  const [open, setOpen] = useState(false);
  const [above, setAbove] = useState(false);
  const [active, setActive] = useState(picked);
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (open) list.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  function show() {
    setAbove(opensAbove(root.current?.getBoundingClientRect(), window.innerHeight));
    setActive(picked);
    setOpen(true);
  }

  function pick(index: number) {
    if (index !== picked) onChange(options[index].value);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    const last = options.length - 1;
    const moves: Record<string, number> = { ArrowDown: Math.min(active + 1, last), ArrowUp: Math.max(active - 1, 0), Home: 0, End: last };
    const letter = e.key.length === 1 && e.key !== " " && !e.ctrlKey && !e.metaKey && !e.altKey;
    if (!open) {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return; // Enter and Space click the button.
      show();
    } else if (e.key in moves) setActive(moves[e.key]);
    else if (letter) setActive(nextStartingWith(options.map((o) => o.label), e.key, active));
    else if (e.key === "Enter" || e.key === " ") pick(active);
    else if (e.key === "Escape") setOpen(false);
    else return;
    e.preventDefault();
  }

  return (
    <div ref={root} className={clsx("relative", className ?? "w-full")} onBlur={(e) => !root.current?.contains(e.relatedTarget) && setOpen(false)}>
      <button
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-label={label && `${label}: ${options[picked]?.label ?? ""}`}
        aria-activedescendant={open ? `${id}-${active}` : undefined}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={onKeyDown}
        className={clsx(inputClass, "flex! items-center gap-2.5 text-left disabled:cursor-not-allowed")}
      >
        {options[picked]?.icon}
        <span className="min-w-0 flex-1 truncate">{options[picked]?.label}</span>
        <ChevronDown size={16} aria-hidden className={clsx("shrink-0 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ul
          ref={list}
          id={`${id}-list`}
          role="listbox"
          aria-label={label}
          // Keeps focus on the button, so clicking an option isn't a blur.
          onMouseDown={(e) => e.preventDefault()}
          // Inside a <label>, a click would also press the button and open the list again.
          onClick={(e) => e.preventDefault()}
          className={clsx(
            "absolute left-0 z-20 max-h-64 w-full min-w-max overflow-y-auto rounded-lg border bg-surface p-1 shadow-lg",
            above ? "bottom-full mb-1.5" : "top-full mt-1.5",
          )}
        >
          {options.map((option, i) => (
            <li
              key={option.value}
              id={`${id}-${i}`}
              role="option"
              aria-selected={i === picked}
              onMouseMove={() => setActive(i)}
              onClick={() => pick(i)}
              className={clsx("flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm font-normal", i === active && "bg-muted")}
            >
              {option.icon}
              <span className="flex-1">{option.label}</span>
              {option.note && <span className="text-xs text-muted-foreground">{option.note}</span>}
              <Check size={15} aria-hidden className={clsx("shrink-0 text-primary-text", i !== picked && "invisible")} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
