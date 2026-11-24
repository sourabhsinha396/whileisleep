"use client";

import clsx from "clsx";
import { Check, Copy } from "lucide-react";
import { createContext, useContext, useEffect, useRef, useState } from "react";

/** Inside tabs, the tabs are the block's title. */
const InTabs = createContext(false);

export function CodeBlock({ label, children }: { label: string; children: React.ReactNode }) {
  const tabbed = useContext(InTabs);
  const ref = useRef<HTMLPreElement>(null);
  return (
    <div className={clsx("doc-code relative", !tabbed && "my-5 overflow-hidden rounded-lg")}>
      {!tabbed && label && <p className="doc-code-title">{label}</p>}
      <CopyButton text={() => ref.current?.textContent ?? ""} />
      <pre ref={ref} tabIndex={0}>
        {children}
      </pre>
    </div>
  );
}

/** The same thing in several languages. */
export function CodeTabs({ labels, children }: { labels: string[]; children: React.ReactNode[] }) {
  const [open, setOpen] = useState(0);
  return (
    <InTabs.Provider value>
      <div className="doc-code my-5 overflow-hidden rounded-lg">
        <div className="doc-code-title flex gap-1 !py-1.5 !pl-2" role="group" aria-label="Language">
          {labels.map((label, i) => (
            <button
              key={i}
              aria-pressed={i === open}
              onClick={() => setOpen(i)}
              className={clsx("rounded-md px-2.5 py-1 transition-colors", i === open ? "bg-white/15 text-white" : "hover:text-white")}
            >
              {label || "Code"}
            </button>
          ))}
        </div>
        {children.map((child, i) => (
          <div key={i} hidden={i !== open}>
            {child}
          </div>
        ))}
      </div>
    </InTabs.Provider>
  );
}

function CopyButton({ text }: { text: () => string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);
  return (
    <button
      aria-label={copied ? "Copied" : "Copy code"}
      title={copied ? "Copied" : "Copy"}
      onClick={() => navigator.clipboard?.writeText(text().replace(/\n$/, "")).then(() => setCopied(true), () => {})}
      className="absolute top-2 right-2 z-10 grid size-8 place-items-center rounded-md bg-gray-900 text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
    >
      {copied ? <Check size={15} /> : <Copy size={15} />}
    </button>
  );
}
