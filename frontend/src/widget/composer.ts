/** The widget's message box: grows with the text, and takes emoji and files. */

import { ACCEPT, type ChatFile, fileProblem, fileSize, MAX_FILES } from "@/lib/chat-file";
import { EMOJI } from "@/lib/emoji";
import { counterText } from "./limits";
import { button, div } from "./dom";

const icon = (paths: string) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;

const ICONS = {
  send: icon('<path d="M12 19V5M5 12l7-7 7 7"/>'),
  smile: icon('<circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9h.01M15 9h.01"/>'),
  clip: icon('<path d="m21.4 11-9.2 9.2a6 6 0 0 1-8.5-8.5l9.2-9.2a4 4 0 0 1 5.7 5.7l-9.2 9.2a2 2 0 0 1-2.8-2.8l8.5-8.5"/>'),
  file: icon('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>'),
  remove: icon('<path d="M18 6 6 18M6 6l12 12"/>'),
};

/** Taller than this, the text scrolls. */
const MAX_HEIGHT = 120;

interface Options {
  maxLength: number;
  /** Whether files can be sent at all. */
  uploads: boolean;
  upload: (file: File) => Promise<ChatFile>;
  onSend: () => void;
  onInput: (text: string) => void;
  onError: (message: string) => void;
}

interface Pending {
  node: HTMLElement;
  /** Set once it is uploaded. */
  file?: ChatFile;
  preview?: string;
}

export class Composer {
  readonly el = div("compose");
  readonly input = document.createElement("textarea");
  private files = div("files");
  private counter = div("counter");
  private emoji = div("emoji");
  private sendButton: HTMLButtonElement;
  private pending: Pending[] = [];
  private busy = false;

  constructor(private options: Options) {
    const { input } = this;
    input.rows = 1;
    input.placeholder = "Write a message…";
    input.setAttribute("aria-label", "Message");
    // Same limit the server enforces; pasting past it is cut off here instead of failing on send.
    input.maxLength = options.maxLength;
    this.counter.setAttribute("aria-live", "polite");
    input.addEventListener("input", () => {
      this.refresh();
      options.onInput(input.value);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        this.trySend();
      }
    });
    input.addEventListener("paste", (e) => {
      const files = Array.from(e.clipboardData?.files ?? []);
      // Copied from a document, there is text too: that is what was meant.
      if (!options.uploads || !files.length || e.clipboardData?.getData("text/plain")) return;
      e.preventDefault();
      this.add(files);
    });

    const row = div("compose-row");
    row.append(input, this.emojiButton());
    if (options.uploads) row.append(this.attachButton());
    this.sendButton = button("send", "", () => this.trySend());
    this.sendButton.innerHTML = ICONS.send;
    this.sendButton.setAttribute("aria-label", "Send");
    row.append(this.sendButton);
    this.el.append(this.emoji, this.files, row, this.counter);
    this.refresh();
  }

  get text(): string {
    return this.input.value;
  }

  set text(value: string) {
    // A host page's message can't skip the limit either.
    this.input.value = value.slice(0, this.options.maxLength);
    this.refresh();
  }

  /** What is in the box, which is empty after this. `restore` puts it back when sending fails,
   * before anything typed since. */
  take(): { text: string; files: ChatFile[]; restore: () => void } {
    const text = this.input.value;
    const pending = this.pending;
    this.empty();
    return {
      text: text.trim(),
      files: pending.flatMap((each) => each.file ?? []),
      restore: () => {
        this.pending = [...pending, ...this.pending];
        this.files.prepend(...pending.map((each) => each.node));
        this.text = [text, this.input.value].filter(Boolean).join("\n");
      },
    };
  }

  /** Throws away what is in the box. */
  clear() {
    for (const each of this.pending) if (each.preview) URL.revokeObjectURL(each.preview);
    this.empty();
  }

  private empty() {
    this.input.value = "";
    this.pending = [];
    this.files.replaceChildren();
    this.refresh();
  }

  /** While a message is being sent. */
  setBusy(busy: boolean) {
    this.busy = busy;
    this.refresh();
  }

  focus() {
    this.input.focus();
  }

  /** The box fits its text. Call it when the panel opens: a hidden box has no height. */
  refresh() {
    const { input } = this;
    input.style.height = "auto";
    if (input.scrollHeight) input.style.height = `${Math.min(input.scrollHeight, MAX_HEIGHT)}px`;
    input.style.overflowY = input.scrollHeight > MAX_HEIGHT ? "auto" : "hidden";
    this.counter.textContent = counterText(input.value.length, this.options.maxLength);
    this.counter.classList.toggle("full", input.value.length >= this.options.maxLength);
    this.sendButton.disabled = !this.ready;
  }

  private get ready(): boolean {
    const something = !!this.input.value.trim() || this.pending.length > 0;
    return something && !this.busy && this.pending.every((each) => each.file);
  }

  private trySend() {
    if (this.ready) this.options.onSend();
  }

  // --- files ---

  add(files: File[]) {
    this.options.onError("");
    for (const file of files) {
      const problem = this.pending.length >= MAX_FILES ? `A message can have ${MAX_FILES} files.` : fileProblem(file);
      if (problem) this.options.onError(problem);
      else this.upload(file);
    }
  }

  private async upload(file: File) {
    const node = div("file uploading");
    const each: Pending = { node };
    // Shown from the visitor's own copy, so there is no wait for it.
    if (file.type.startsWith("image/")) {
      each.preview = URL.createObjectURL(file);
      const img = document.createElement("img");
      img.alt = "";
      img.src = each.preview;
      node.append(img);
    } else {
      node.insertAdjacentHTML("beforeend", ICONS.file);
    }
    const name = document.createElement("span");
    name.className = "file-name";
    name.textContent = file.name;
    const remove = button("file-remove", "", () => this.remove(each));
    remove.innerHTML = ICONS.remove;
    remove.setAttribute("aria-label", `Remove ${file.name}`);
    node.append(name, remove);
    this.pending.push(each);
    this.files.append(node);
    this.refresh();
    try {
      each.file = await this.options.upload(file);
      node.classList.remove("uploading");
    } catch (error) {
      // Removed meanwhile: nobody is waiting for it.
      if (this.pending.includes(each)) this.options.onError((error as Error).message);
      this.remove(each);
    }
    this.refresh();
  }

  private remove(each: Pending) {
    this.pending = this.pending.filter((other) => other !== each);
    if (each.preview) URL.revokeObjectURL(each.preview);
    each.node.remove();
    this.refresh();
  }

  private attachButton(): HTMLElement {
    const picker = document.createElement("input");
    picker.type = "file";
    picker.multiple = true;
    picker.accept = ACCEPT;
    picker.hidden = true;
    picker.setAttribute("aria-label", "Files to send");
    picker.addEventListener("change", () => {
      this.add(Array.from(picker.files ?? []));
      picker.value = "";
    });
    const open = this.tool("Send a file", ICONS.clip, () => picker.click());
    this.el.append(picker);
    return open;
  }

  // --- emoji ---

  private emojiButton(): HTMLElement {
    this.emoji.hidden = true;
    const open = this.tool("Emoji", ICONS.smile, () => show(this.emoji.hidden));
    const show = (visible: boolean) => {
      this.emoji.hidden = !visible;
      open.setAttribute("aria-expanded", String(visible));
    };
    show(false);
    for (const emoji of EMOJI) {
      this.emoji.append(
        button("", emoji, () => {
          const { input } = this;
          if (input.value.length + emoji.length <= this.options.maxLength) {
            input.setRangeText(emoji, input.selectionStart, input.selectionEnd, "end");
          }
          show(false);
          this.refresh();
          this.options.onInput(input.value);
          input.focus();
        }),
      );
    }
    this.el.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || this.emoji.hidden) return;
      show(false);
      this.input.focus();
    });
    // Clicks stay inside the widget's shadow root, so listen on it.
    this.el.addEventListener("focusout", (e) => {
      if (e.relatedTarget && !this.el.contains(e.relatedTarget as Node)) show(false);
    });
    this.input.addEventListener("focus", () => show(false));
    return open;
  }

  private tool(label: string, svg: string, onClick: () => void): HTMLButtonElement {
    const node = button("tool", "", onClick);
    node.innerHTML = svg;
    node.setAttribute("aria-label", label);
    node.title = label;
    return node;
  }
}

/** A sent file that isn't a picture. */
export function fileCard(file: ChatFile): HTMLAnchorElement {
  const a = document.createElement("a");
  a.className = "file-card";
  a.href = file.url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.innerHTML = ICONS.file;
  const text = document.createElement("span");
  const name = document.createElement("strong");
  name.textContent = file.name;
  const size = document.createElement("small");
  size.textContent = fileSize(file.size);
  text.append(name, size);
  a.append(text);
  return a;
}

