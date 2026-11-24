"use client";

import { type Editor, EditorContent, useEditor, useEditorState } from "@tiptap/react";
import clsx from "clsx";
import { Bold, FileText, Italic, Link2, List, ListOrdered, LoaderCircle, MessageSquare, Paperclip, SendHorizontal, Smile, StickyNote, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { LinkRow } from "@/components/link-row";
import { Button } from "@/components/ui";
import { chatExtensions, fromDoc } from "@/lib/chat-doc";
import { ACCEPT, type ChatFile, fileProblem, isPicture, MAX_FILES } from "@/lib/chat-file";
import { EMOJI } from "@/lib/emoji";
import { useDismiss } from "@/lib/use-dismiss";

export interface Draft {
  body: string;
  is_note: boolean;
  attachments: number[];
}

/** A file in the box: uploading until `file` is there. */
interface Upload {
  key: number;
  name: string;
  file?: ChatFile;
}

const CONTENT =
  "max-h-48 min-h-9 overflow-y-auto py-1.5 pl-3.5 text-sm leading-6 outline-none " +
  "[&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_a]:text-primary-text [&_a]:underline";

/**
 * Where a teammate writes: a reply or a note, with bold, italic, links, lists, emoji and files.
 * It starts one line high and grows with the text. Enter sends, except in a list.
 */
export function Composer({
  visitorName,
  aiEnabled,
  uploadsEnabled,
  onUpload,
  onSend,
  onTyping,
}: {
  visitorName: string;
  aiEnabled: boolean;
  uploadsEnabled: boolean;
  onUpload: (file: File) => Promise<ChatFile>;
  onSend: (draft: Draft) => Promise<unknown>;
  /** A reply is being written. Not for notes: the visitor never hears about those. */
  onTyping: () => void;
}) {
  const [mode, setMode] = useState<"reply" | "note">("reply");
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [linking, setLinking] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const nextKey = useRef(0);
  const note = mode === "note";

  const editor = useEditor({
    extensions: chatExtensions,
    immediatelyRender: false,
    onUpdate: ({ editor }) => {
      if (!editor.isEmpty) latest.current.typed();
    },
    editorProps: {
      attributes: { class: CONTENT, role: "textbox", "aria-multiline": "true", "aria-label": "Message" },
      handleKeyDown: (_view, event) => latest.current.onKey(event),
      handlePaste: (_view, event) => {
        const files = Array.from(event.clipboardData?.files ?? []);
        // Copied from a document, there is text too: that is what was meant.
        if (!files.length || event.clipboardData?.getData("text/plain")) return false;
        latest.current.add(files);
        return true;
      },
      // The box around it takes dropped files.
      handleDrop: (_view, event) => !!event.dataTransfer?.files.length,
    },
  });
  const state = useEditorState({ editor, selector: ({ editor }) => ({ empty: !editor || editor.isEmpty }) });
  const ready = (!state?.empty || uploads.length > 0) && uploads.every((each) => each.file) && !busy;

  async function send() {
    if (!editor || !ready) return;
    const doc = editor.getJSON();
    const body = fromDoc(doc);
    if (!body && !uploads.length) return;
    setBusy(true);
    setError("");
    // Emptied at once: what is typed while this is on its way belongs to the next message.
    editor.commands.clearContent();
    setUploads([]);
    setLinking(false);
    try {
      await onSend({ body, is_note: note, attachments: uploads.map((each) => each.file!.id) });
    } catch (err) {
      if (editor.isEmpty) editor.commands.setContent(doc);
      else editor.commands.insertContentAt(0, doc.content ?? []);
      setUploads((now) => [...uploads, ...now]);
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /** True when the key is dealt with. */
  function onKey(event: KeyboardEvent): boolean {
    if (!editor || event.key !== "Enter" || event.isComposing) return false;
    const inList = editor.isActive("listItem");
    if (inList && !event.ctrlKey && !event.metaKey) {
      // A new item, or out of the list from an empty one.
      return event.shiftKey ? editor.commands.splitListItem("listItem") || editor.commands.liftListItem("listItem") : false;
    }
    if (event.shiftKey) return editor.commands.splitBlock();
    send();
    return true;
  }

  async function add(files: File[]) {
    if (!uploadsEnabled) return setError("Connect your storage in Settings › Storage to send files.");
    setError("");
    const room = MAX_FILES - uploads.length;
    if (files.length > room) setError(`A message can have ${MAX_FILES} files.`);
    await Promise.all(
      files.slice(0, Math.max(0, room)).map(async (file) => {
        const problem = fileProblem(file);
        if (problem) return setError(problem);
        const key = nextKey.current++;
        setUploads((now) => [...now, { key, name: file.name }]);
        try {
          const saved = await onUpload(file);
          setUploads((now) => now.map((each) => (each.key === key ? { ...each, file: saved } : each)));
        } catch (err) {
          setUploads((now) => now.filter((each) => each.key !== key));
          setError((err as Error).message);
        }
      }),
    );
  }

  // The editor keeps the handlers it is made with; this reaches the newest ones.
  const latest = useRef({ onKey, add, typed: () => {} });
  useEffect(() => {
    latest.current = { onKey, add, typed: () => !note && onTyping() };
  });

  return (
    <div
      className={clsx(
        "relative mx-4 mb-4 rounded-xl border bg-surface shadow-sm transition-colors focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/20",
        note && "border-warning/40 bg-warning-soft focus-within:border-warning focus-within:ring-warning/20",
      )}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
      }}
      onDrop={(e) => {
        setDragging(false);
        const files = Array.from(e.dataTransfer.files);
        if (!files.length) return;
        e.preventDefault();
        add(files);
      }}
    >
      <div className="flex items-center justify-between gap-2 px-2 pt-1.5">
        <div className="flex gap-0.5">
          {(["reply", "note"] as const).map((each) => (
            <button
              key={each}
              type="button"
              aria-pressed={mode === each}
              onClick={() => {
                setMode(each);
                editor?.commands.focus();
              }}
              className={clsx(
                "flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap transition-colors",
                mode !== each ? "text-muted-foreground hover:bg-muted" : each === "note" ? "bg-warning/15 text-warning" : "bg-primary-soft text-primary-text",
              )}
            >
              {each === "reply" ? <MessageSquare size={13} /> : <StickyNote size={13} />}
              {each === "reply" ? "Reply" : "Internal note"}
            </button>
          ))}
        </div>
        {editor && <Formatting editor={editor} linking={linking} setLinking={setLinking} />}
      </div>
      {editor && linking && <LinkRow editor={editor} close={() => setLinking(false)} className="mt-1.5 border-t" />}
      {uploads.length > 0 && (
        <ul className="flex flex-wrap gap-2 px-3 pt-2">
          {uploads.map((each) => (
            <Chip key={each.key} upload={each} onRemove={() => setUploads((now) => now.filter((other) => other.key !== each.key))} />
          ))}
        </ul>
      )}
      <div className="flex items-end gap-1 pr-2 pb-1.5">
        <div className="relative min-w-0 flex-1">
          {state?.empty && (
            <p aria-hidden className="pointer-events-none absolute inset-x-0 top-1.5 truncate pl-3.5 text-sm leading-6 text-muted-foreground">
              {note ? "Only your team sees notes" : `Reply to ${visitorName}${aiEnabled ? ". The AI agent pauses once you answer." : ""}`}
            </p>
          )}
          <EditorContent editor={editor} />
        </div>
        <EmojiButton onPick={(emoji) => editor?.chain().focus().insertContent(emoji).run()} />
        <ToolButton label={uploadsEnabled ? "Attach files" : "Attach files (connect your storage first)"} disabled={!uploadsEnabled} onClick={() => fileInput.current?.click()}>
          <Paperclip size={16} />
        </ToolButton>
        <Button
          type="button"
          onClick={send}
          disabled={!ready}
          size="sm"
          aria-label={note ? "Add note" : "Send"}
          className={clsx("ml-1 h-8", note && "bg-warning hover:bg-warning/90")}
        >
          {note ? "Add" : "Send"} <SendHorizontal size={14} />
        </Button>
      </div>
      {error && (
        <p role="alert" className="px-3.5 pb-2 text-xs text-danger">
          {error}
        </p>
      )}
      <input
        ref={fileInput}
        type="file"
        multiple
        accept={ACCEPT}
        aria-label="Files to attach"
        className="hidden"
        onChange={(e) => {
          add(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
      {dragging && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center rounded-xl border-2 border-dashed border-primary bg-primary-soft/90 text-sm font-semibold text-primary-text">
          Drop files to attach
        </div>
      )}
    </div>
  );
}

function Formatting({ editor, linking, setLinking }: { editor: Editor; linking: boolean; setLinking: (open: boolean) => void }) {
  const active = useEditorState({
    editor,
    selector: ({ editor }) => ({
      bold: editor.isActive("bold"),
      italic: editor.isActive("italic"),
      bullets: editor.isActive("bulletList"),
      numbers: editor.isActive("orderedList"),
      link: editor.isActive("link"),
    }),
  });
  const chain = () => editor.chain().focus();
  const items = [
    { label: "Bold", icon: Bold, on: active.bold, run: () => chain().toggleBold().run() },
    { label: "Italic", icon: Italic, on: active.italic, run: () => chain().toggleItalic().run() },
    { label: "Link", icon: Link2, on: active.link || linking, run: () => setLinking(!linking) },
    { label: "Bullet list", icon: List, on: active.bullets, run: () => chain().toggleBulletList().run() },
    { label: "Numbered list", icon: ListOrdered, on: active.numbers, run: () => chain().toggleOrderedList().run() },
  ];
  return (
    <div role="toolbar" aria-label="Formatting" className="flex">
      {items.map(({ label, icon: Icon, on, run }) => (
        <ToolButton key={label} label={label} on={on} onClick={run}>
          <Icon size={15} />
        </ToolButton>
      ))}
    </div>
  );
}

function ToolButton({ label, on, children, ...props }: { label: string; on?: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={on}
      // Keeps the text selected while the button is pressed.
      onMouseDown={(e) => e.preventDefault()}
      className={clsx(
        "grid size-8 shrink-0 place-items-center rounded-md transition-colors disabled:opacity-40",
        on ? "bg-primary-soft text-primary-text" : "text-muted-foreground hover:bg-foreground/5 hover:text-foreground",
      )}
      {...props}
    >
      {children}
    </button>
  );
}

function EmojiButton({ onPick }: { onPick: (emoji: string) => void }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const box = useDismiss(open, close);
  return (
    <div ref={box} className="relative">
      <ToolButton label="Emoji" on={open} aria-expanded={open} onClick={() => setOpen(!open)}>
        <Smile size={16} />
      </ToolButton>
      {open && (
        <div className="absolute right-0 bottom-full z-20 mb-2 grid w-max grid-cols-8 gap-0.5 rounded-xl border bg-surface p-2 shadow-lg">
          {EMOJI.map((emoji) => (
            <button
              key={emoji}
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                onPick(emoji);
                close();
              }}
              className="grid size-8 place-items-center rounded-md text-lg hover:bg-muted"
            >
              {emoji}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Chip({ upload, onRemove }: { upload: Upload; onRemove: () => void }) {
  const { file, name } = upload;
  return (
    <li className="flex max-w-56 items-center gap-2 rounded-lg border bg-background py-1 pr-1 pl-2 text-xs">
      {!file ? (
        <LoaderCircle size={15} className="shrink-0 animate-spin text-muted-foreground" aria-label="Uploading" />
      ) : isPicture(file) ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={file.url} alt="" className="size-6 shrink-0 rounded object-cover" />
      ) : (
        <FileText size={15} className="shrink-0 text-primary-text" />
      )}
      <span className="truncate font-medium">{name}</span>
      <button type="button" aria-label={`Remove ${name}`} onClick={onRemove} className="grid size-5 shrink-0 place-items-center rounded text-muted-foreground hover:bg-muted hover:text-foreground">
        <X size={13} />
      </button>
    </li>
  );
}
