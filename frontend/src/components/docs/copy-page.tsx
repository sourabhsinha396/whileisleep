"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui";

/** Copies a page of the docs as Markdown, to paste into a chat with an LLM. */
export function CopyPage({ slug, markdown }: { slug: string; markdown: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);

  function copy() {
    const show = () => window.open(`/docs/${slug}.md`, "_blank");
    // Without access to the clipboard, the text can still be copied by hand.
    if (!navigator.clipboard) return show();
    navigator.clipboard.writeText(markdown).then(() => setCopied(true), show);
  }

  return (
    <div className="mt-4 flex items-center gap-3">
      <Button size="sm" variant="secondary" onClick={copy} title="Copy as Markdown, for an LLM">
        {copied ? <Check size={14} /> : <Copy size={14} />}
        <span aria-live="polite">{copied ? "Copied" : "Copy page"}</span>
      </Button>
      <a href={`/docs/${slug}.md`} target="_blank" className="text-xs text-muted-foreground hover:text-foreground hover:underline">
        View as Markdown
      </a>
    </div>
  );
}
