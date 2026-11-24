"use client";

import type { Editor } from "@tiptap/react";
import clsx from "clsx";
import { useState } from "react";
import { Button, inputClass } from "@/components/ui";

/** Where a link in an editor points: typed here, applied to the selected text. */
export function LinkRow({ editor, close, className }: { editor: Editor; close: () => void; className?: string }) {
  const [href, setHref] = useState<string>(() => editor.getAttributes("link").href ?? "");
  const [problem, setProblem] = useState("");

  function apply() {
    const target = withProtocol(href);
    if (!target) return remove();
    const chain = editor.chain().focus().extendMarkRange("link");
    // With nothing selected there is no text to link, so the address is the text.
    const done =
      editor.state.selection.empty && !editor.isActive("link")
        ? chain.insertContent({ type: "text", text: target, marks: [{ type: "link", attrs: { href: target } }] }).run()
        : chain.setLink({ href: target }).run();
    if (done) close();
    else setProblem("That address can't be linked.");
  }

  function remove() {
    editor.chain().focus().extendMarkRange("link").unsetLink().run();
    close();
  }

  return (
    <div className={clsx("flex items-center gap-2 border-b p-2", className)}>
      <input
        autoFocus
        className={clsx(inputClass, "py-1.5 text-sm")}
        placeholder="https://example.com or /page"
        aria-label="Link address"
        value={href}
        onChange={(e) => setHref(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            apply();
          }
          if (e.key === "Escape") close();
        }}
      />
      {problem && <span className="text-xs whitespace-nowrap text-danger">{problem}</span>}
      <Button type="button" size="sm" onClick={apply}>
        Apply
      </Button>
      {editor.isActive("link") && (
        <Button type="button" size="sm" variant="secondary" onClick={remove}>
          Remove
        </Button>
      )}
    </div>
  );
}

/** "example.com" means https://example.com; "/page" stays a path on the workspace's website. */
export function withProtocol(href: string): string {
  const trimmed = href.trim();
  if (!trimmed || trimmed.startsWith("/") || /^https?:\/\//i.test(trimmed)) return trimmed;
  return /^[a-z][a-z0-9+.-]*:(?!\d)/i.test(trimmed) ? "" : `https://${trimmed}`;
}
