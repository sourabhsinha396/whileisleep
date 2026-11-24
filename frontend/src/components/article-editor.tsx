"use client";

import { type Editor, EditorContent, useEditor, useEditorState } from "@tiptap/react";
import clsx from "clsx";
import { Bold, Heading2, ImagePlus, Link2, List, ListOrdered } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button, ErrorText, inputClass } from "@/components/ui";
import { articleExtensions, fromDoc, toDoc } from "@/lib/article-doc";
import { altFromName, IMAGE_TYPES, imageProblem } from "@/lib/image-file";

/** Styled like the widget's Help tab, so writing shows what visitors will read. */
const CONTENT =
  "min-h-80 px-4 py-3 text-[15px] leading-relaxed outline-none " +
  "[&_p]:my-2.5 [&_h1]:mt-5 [&_h1]:mb-2 [&_h1]:text-lg [&_h1]:font-bold [&_h2]:mt-5 [&_h2]:mb-2 [&_h2]:text-lg [&_h2]:font-bold " +
  "[&_:is(h3,h4,h5,h6)]:mt-4 [&_:is(h3,h4,h5,h6)]:mb-2 [&_:is(h3,h4,h5,h6)]:font-bold " +
  "[&_ul]:my-2.5 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:my-2.5 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:my-1 [&_li_p]:my-0 " +
  "[&_a]:text-primary-text [&_a]:underline " +
  "[&_img]:my-1.5 [&_img]:inline-block [&_img]:max-h-96 [&_img]:max-w-full [&_img]:rounded-lg [&_img]:ring-1 [&_img]:ring-border " +
  "[&_img.ProseMirror-selectednode]:ring-2 [&_img.ProseMirror-selectednode]:ring-ring";

/**
 * A small what-you-see-is-what-you-get editor for Markdown: bold, heading, lists, link, image.
 * Give it a `key` per article; `value` is only read when it starts. An article that is opened
 * and not edited is never rewritten.
 */
export function ArticleEditor({
  value,
  onChange,
  onUpload,
  uploadsEnabled,
}: {
  value: string;
  onChange: (markdown: string) => void;
  /** Stores an image and returns its address. */
  onUpload: (file: File) => Promise<string>;
  uploadsEnabled: boolean;
}) {
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(0);
  const [linking, setLinking] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  // The editor keeps the handlers it is made with; this reaches the newest ones.
  const latest = useRef({ onChange, onUpload });
  useEffect(() => {
    latest.current = { onChange, onUpload };
  });

  const editor = useEditor({
    extensions: articleExtensions,
    content: toDoc(value),
    // Not while the server renders the page: the first client render must match it.
    immediatelyRender: false,
    onUpdate: ({ editor }) => latest.current.onChange(fromDoc(editor.getJSON())),
    editorProps: {
      attributes: { class: CONTENT, role: "textbox", "aria-multiline": "true", "aria-label": "Body" },
      handlePaste: (_view, event) => take(event.clipboardData),
      handleDrop: (view, event, _slice, moved) => {
        // Moving an image around inside the text is the editor's own business.
        if (moved) return false;
        const at = view.posAtCoords({ left: event.clientX, top: event.clientY });
        return take(event.dataTransfer, at?.pos);
      },
    },
  });

  /** Uploads pasted or dropped image files. False leaves anything else to the editor. */
  function take(data: DataTransfer | null, at?: number): boolean {
    const files = Array.from(data?.files ?? []);
    if (!files.length) return false;
    add(files, at);
    return true;
  }

  async function add(files: File[], at?: number) {
    if (!uploadsEnabled) return setError("Articles are text until you connect your storage (Settings › Storage). Then you can add images.");
    setError("");
    for (const file of files) {
      const problem = imageProblem(file);
      if (problem) {
        setError(problem);
        continue;
      }
      setUploading((n) => n + 1);
      try {
        const src = await latest.current.onUpload(file);
        if (!editor || editor.isDestroyed) return;
        const node = { type: "image", attrs: { src, alt: altFromName(file.name) } };
        // The text may have become shorter while the image uploaded.
        if (at === undefined) editor.chain().focus().insertContent(node).run();
        else editor.chain().focus().insertContentAt(Math.min(at, editor.state.doc.content.size), node).run();
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setUploading((n) => n - 1);
      }
    }
  }

  return (
    <div className="space-y-1.5">
      <div className="overflow-hidden rounded-lg border bg-surface focus-within:border-primary focus-within:ring-2 focus-within:ring-ring/30">
        {editor && <Toolbar editor={editor} linking={linking} setLinking={setLinking} pickImage={() => fileInput.current?.click()} uploadsEnabled={uploadsEnabled} />}
        {editor && linking && <LinkRow editor={editor} close={() => setLinking(false)} />}
        {editor && <AltRow editor={editor} />}
        <EditorContent editor={editor} className="max-h-[60vh] overflow-y-auto" />
      </div>
      <input
        ref={fileInput}
        type="file"
        multiple
        accept={IMAGE_TYPES.join(",")}
        aria-label="Image files"
        className="hidden"
        onChange={(e) => {
          add(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
      {uploading > 0 && (
        <p role="status" className="text-xs text-muted-foreground">
          Uploading image…
        </p>
      )}
      <ErrorText>{error}</ErrorText>
    </div>
  );
}

function Toolbar({
  editor,
  linking,
  setLinking,
  pickImage,
  uploadsEnabled,
}: {
  editor: Editor;
  linking: boolean;
  setLinking: (open: boolean) => void;
  pickImage: () => void;
  uploadsEnabled: boolean;
}) {
  const active = useEditorState({
    editor,
    selector: ({ editor }) => ({
      bold: editor.isActive("bold"),
      heading: editor.isActive("heading"),
      bullets: editor.isActive("bulletList"),
      numbers: editor.isActive("orderedList"),
      link: editor.isActive("link"),
    }),
  });
  const chain = () => editor.chain().focus();
  const items = [
    { label: "Bold", icon: Bold, on: active.bold, run: () => chain().toggleBold().run() },
    {
      label: "Heading",
      icon: Heading2,
      on: active.heading,
      // A heading of any level turns back into text.
      run: () => (active.heading ? chain().setParagraph().run() : chain().setHeading({ level: 2 }).run()),
    },
    { label: "Bullet list", icon: List, on: active.bullets, run: () => chain().toggleBulletList().run() },
    { label: "Numbered list", icon: ListOrdered, on: active.numbers, run: () => chain().toggleOrderedList().run() },
    { label: "Link", icon: Link2, on: active.link || linking, run: () => setLinking(!linking) },
    { label: uploadsEnabled ? "Image" : "Image (connect your storage first)", icon: ImagePlus, on: false, run: pickImage, disabled: !uploadsEnabled },
  ];
  return (
    <div role="toolbar" aria-label="Formatting" className="flex gap-0.5 border-b bg-muted/50 p-1">
      {items.map(({ label, icon: Icon, on, run, disabled }) => (
        <button
          key={label}
          type="button"
          title={label}
          aria-label={label}
          aria-pressed={on}
          disabled={disabled}
          // Keeps the text selected while the button is pressed.
          onMouseDown={(e) => e.preventDefault()}
          onClick={run}
          className={clsx(
            "grid size-8 place-items-center rounded-md transition-colors disabled:opacity-40",
            on ? "bg-primary-soft text-primary-text" : "text-muted-foreground hover:bg-muted hover:text-foreground",
          )}
        >
          <Icon size={16} />
        </button>
      ))}
    </div>
  );
}

function LinkRow({ editor, close }: { editor: Editor; close: () => void }) {
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
    <div className="flex items-center gap-2 border-b p-2">
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

/** Shown while an image is selected. */
function AltRow({ editor }: { editor: Editor }) {
  const image = useEditorState({
    editor,
    selector: ({ editor }) => (editor.isActive("image") ? { alt: (editor.getAttributes("image").alt ?? "") as string } : null),
  });
  if (!image) return null;
  return (
    <div className="border-b p-2">
      <input
        className={clsx(inputClass, "py-1.5 text-sm")}
        placeholder="Describe this image. The AI and screen readers read this instead of it."
        aria-label="Image description"
        value={image.alt}
        onChange={(e) => editor.commands.updateAttributes("image", { alt: e.target.value })}
      />
    </div>
  );
}

/** "example.com" means https://example.com; "/page" stays a path on the workspace's website. */
export function withProtocol(href: string): string {
  const trimmed = href.trim();
  if (!trimmed || trimmed.startsWith("/") || /^https?:\/\//i.test(trimmed)) return trimmed;
  return /^[a-z][a-z0-9+.-]*:(?!\d)/i.test(trimmed) ? "" : `https://${trimmed}`;
}
