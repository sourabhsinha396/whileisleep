"use client";

import clsx from "clsx";
import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { inputClass } from "@/components/ui";
import type { LlmModel } from "@/lib/api";
import { opensAbove } from "@/lib/dropdown";
import { matchingModels, TIERS } from "@/lib/llm";

/** A model id: pick one of the offered models or type any other. Not a <datalist>, which each
 * browser draws in its own way and which hides every choice once a model is picked. */
export function ModelPicker({
  label,
  models,
  placeholder,
  value,
  onChange,
}: {
  label: string;
  /** The models to offer, tier by tier. */
  models: LlmModel[];
  placeholder: string;
  value: string;
  onChange: (model: string) => void;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const [above, setAbove] = useState(false);
  // What was typed since the list opened. Until then it shows everything, whatever is picked.
  const [typed, setTyped] = useState("");
  // -1: nothing in the list, so Enter saves what is typed.
  const [active, setActive] = useState(-1);
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const choices = matchingModels(models, typed);
  const shown = open && choices.length > 0;

  useEffect(() => {
    if (shown && active >= 0) list.current?.querySelector(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [shown, active]);

  function show(at: number) {
    setAbove(opensAbove(root.current?.getBoundingClientRect(), window.innerHeight));
    setTyped("");
    setActive(at);
    setOpen(true);
  }

  const picked = models.findIndex((m) => m.id === value.trim());

  function pick(model: LlmModel) {
    onChange(model.id);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    const last = choices.length - 1;
    if (!shown) {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      show(Math.max(picked, 0));
    } else if (e.key === "ArrowDown") setActive(Math.min(active + 1, last));
    else if (e.key === "ArrowUp") setActive(Math.max(active - 1, 0));
    else if (e.key === "Enter" && active >= 0) pick(choices[Math.min(active, last)]);
    else if (e.key === "Escape") setOpen(false);
    else return;
    e.preventDefault();
  }

  return (
    <div ref={root} className="relative" onBlur={(e) => !root.current?.contains(e.relatedTarget) && setOpen(false)}>
      <input
        role="combobox"
        aria-label={label}
        aria-autocomplete="list"
        aria-expanded={shown}
        aria-controls={`${id}-list`}
        aria-activedescendant={shown && active >= 0 ? `${id}-${active}` : undefined}
        autoComplete="off"
        spellCheck={false}
        className={clsx(inputClass, "pr-9 font-mono")}
        placeholder={placeholder}
        value={value}
        onClick={() => !open && show(picked)}
        onKeyDown={onKeyDown}
        onChange={(e) => {
          if (!open) show(-1);
          setTyped(e.target.value);
          setActive(-1);
          onChange(e.target.value);
        }}
      />
      <ChevronDown
        size={16}
        aria-hidden
        className={clsx("pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-muted-foreground transition-transform", shown && "rotate-180")}
      />
      {shown && (
        <div
          // Keeps focus in the field, so clicking a model isn't a blur.
          onMouseDown={(e) => e.preventDefault()}
          className={clsx(
            "absolute left-0 z-20 w-full overflow-hidden rounded-lg border bg-surface shadow-lg",
            above ? "bottom-full mb-1.5" : "top-full mt-1.5",
          )}
        >
          <div ref={list} id={`${id}-list`} role="listbox" aria-label={label} className="max-h-64 overflow-y-auto p-1">
            {choices.map((model, i) => (
              <div key={model.id}>
                {model.tier && model.tier !== choices[i - 1]?.tier && (
                  <p role="presentation" className="px-2 pt-2 pb-1 text-[11px] font-semibold text-muted-foreground">
                    {TIERS[model.tier]}
                  </p>
                )}
                <div
                  id={`${id}-${i}`}
                  data-index={i}
                  role="option"
                  aria-selected={i === active}
                  onMouseMove={() => setActive(i)}
                  onClick={() => pick(model)}
                  className={clsx("flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5", i === active && "bg-muted")}
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm">{model.name}</span>
                    {model.name !== model.id && <span className="block truncate font-mono text-xs text-muted-foreground">{model.id}</span>}
                  </span>
                  {model.id === value.trim() && <Check size={15} aria-hidden className="shrink-0 text-primary-text" />}
                </div>
              </div>
            ))}
          </div>
          <p className="border-t px-3 py-2 text-xs text-muted-foreground">Or type any other model&apos;s id.</p>
        </div>
      )}
    </div>
  );
}
