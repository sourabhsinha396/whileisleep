"use client";

import { type Editor, EditorContent, useEditor, useEditorState } from "@tiptap/react";
import { Bold, Code, Heading2, Link2, List, ListOrdered, SquareCode } from "lucide-react";
import { useEffect, useState } from "react";
import { ToolbarButtons } from "@/components/article-editor";
import { LinkRow } from "@/components/link-row";
import { Button, inputClass } from "@/components/ui";
import { docExtensions, docToEditor, editorToDoc } from "@/lib/doc-editor";

/** Edits the text of a page of the docs where it stands. */
export function DocEditor({ value, busy, onSave, onCancel }: { value: string; busy: boolean; onSave: (markdown: string) => void; onCancel: () => void }) {
  const [linking, setLinking] = useState(false);
  const [changed, setChanged] = useState(false);
  const editor = useEditor({
    extensions: docExtensions,
    content: docToEditor(value),
    immediatelyRender: false,
    onUpdate: () => setChanged(true),
    editorProps: { attributes: { class: "doc-text min-h-80 px-5 py-1 outline-none", role: "textbox", "aria-multiline": "true", "aria-label": "Text" } },
  });

  // Asks before a reload or a closed tab loses what was written.
  useEffect(() => {
    if (!changed) return;
    const ask = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", ask);
    return () => window.removeEventListener("beforeunload", ask);
  }, [changed]);

  if (!editor) return null;
  return (
    <div className="mt-5 space-y-3">
      <div className="rounded-lg border bg-surface focus-within:border-primary focus-within:ring-2 focus-within:ring-ring/30">
        <div className="sticky top-0 z-20 overflow-hidden rounded-t-lg bg-surface">
          <Toolbar editor={editor} linking={linking} setLinking={setLinking} />
          {linking && <LinkRow editor={editor} close={() => setLinking(false)} />}
        </div>
        <EditorContent editor={editor} />
      </div>
      <div className="flex items-center gap-2">
        <Button disabled={busy || !changed || editor.isEmpty} onClick={() => onSave(editorToDoc(editor.getJSON()))}>
          Save
        </Button>
        <Button variant="ghost" onClick={() => (!changed || window.confirm("Throw away your changes?")) && onCancel()}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function Toolbar({ editor, linking, setLinking }: { editor: Editor; linking: boolean; setLinking: (open: boolean) => void }) {
  const active = useEditorState({
    editor,
    selector: ({ editor }) => ({
      bold: editor.isActive("bold"),
      heading: editor.isActive("heading"),
      bullets: editor.isActive("bulletList"),
      numbers: editor.isActive("orderedList"),
      link: editor.isActive("link"),
      code: editor.isActive("code"),
      block: editor.isActive("codeBlock"),
      language: (editor.getAttributes("codeBlock").language ?? "") as string,
    }),
  });
  const chain = () => editor.chain().focus();
  return (
    <>
      <ToolbarButtons
        items={[
          { label: "Bold", icon: Bold, on: active.bold, run: () => chain().toggleBold().run() },
          {
            label: "Heading",
            icon: Heading2,
            on: active.heading,
            run: () => (active.heading ? chain().setParagraph().run() : chain().setHeading({ level: 2 }).run()),
          },
          { label: "Bullet list", icon: List, on: active.bullets, run: () => chain().toggleBulletList().run() },
          { label: "Numbered list", icon: ListOrdered, on: active.numbers, run: () => chain().toggleOrderedList().run() },
          { label: "Link", icon: Link2, on: active.link || linking, run: () => setLinking(!linking) },
          { label: "Code", icon: Code, on: active.code, run: () => chain().toggleCode().run() },
          { label: "Code block", icon: SquareCode, on: active.block, run: () => chain().toggleCodeBlock().run() },
        ]}
      />
      {active.block && (
        <div className="border-b p-2">
          <input
            className={`${inputClass} py-1.5 text-sm`}
            placeholder="Language: html, js, python, php, sh, json"
            aria-label="Code language"
            value={active.language}
            onChange={(e) => editor.commands.updateAttributes("codeBlock", { language: e.target.value.replace(/[\s`]/g, "") })}
          />
        </div>
      )}
    </>
  );
}
