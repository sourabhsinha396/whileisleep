// @vitest-environment happy-dom
import type { Editor } from "@tiptap/react";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatFiles, ChatText } from "@/components/chat-message";
import { Composer } from "@/components/composer";
import type { ChatFile } from "@/lib/chat-file";

let container: HTMLElement;
let root: Root;

beforeEach(() => {
  (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  document.body.replaceChildren();
});

const saved = (name: string): ChatFile => ({ id: 7, name, url: `https://files.example.com/${name}`, content_type: "application/pdf", size: 10, width: null, height: null });

async function open({ uploadsEnabled = true, onSend = vi.fn(async () => {}), onUpload = vi.fn(async (file: File) => saved(file.name)) } = {}) {
  const onTyping = vi.fn();
  await act(async () =>
    root.render(<Composer visitorName="Ana" aiEnabled uploadsEnabled={uploadsEnabled} onUpload={onUpload} onSend={onSend} onTyping={onTyping} />),
  );
  const box = container.querySelector<HTMLElement & { editor: Editor }>("[role=textbox]")!;
  const button = (label: string) => container.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!;
  const tab = (text: string) => Array.from(container.querySelectorAll("button")).find((each) => each.textContent === text)!;
  return {
    onSend,
    onTyping,
    button,
    tab,
    write: (html: string) => act(async () => void box.editor.commands.setContent(html, { emitUpdate: true })),
    press: (key: KeyboardEventInit) => act(async () => void box.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...key }))),
    click: (node: HTMLElement) => act(async () => node.click()),
    text: () => box.textContent,
    attach: async (...files: File[]) => {
      const input = container.querySelector<HTMLInputElement>("input[type=file]")!;
      Object.defineProperty(input, "files", { configurable: true, value: files });
      await act(async () => void input.dispatchEvent(new Event("change", { bubbles: true })));
    },
  };
}

describe("the composer", () => {
  it("sends formatted text with Enter and empties itself", async () => {
    const { write, press, onSend, text } = await open();
    await write("<p>Hi <strong>there</strong></p>");
    await press({ key: "Enter" });
    expect(onSend).toHaveBeenCalledWith({ body: "Hi **there**", is_note: false, attachments: [] });
    expect(text()).toBe("");
  });

  it("starts a new line with Shift+Enter", async () => {
    const { write, press, onSend } = await open();
    await write("<p>Hi</p>");
    await press({ key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("makes a new item with Enter in a list, and sends with Ctrl+Enter", async () => {
    const { write, press, onSend } = await open();
    await write("<ul><li><p>a</p></li></ul>");
    await press({ key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    expect(container.querySelectorAll("[role=textbox] li")).toHaveLength(2);
    await press({ key: "Enter", ctrlKey: true });
    expect(onSend).toHaveBeenCalledWith({ body: "- a", is_note: false, attachments: [] });
  });

  it("sends nothing when there is nothing", async () => {
    const { press, onSend, button, write } = await open();
    expect(button("Send").disabled).toBe(true);
    await press({ key: "Enter" });
    await write("<p>   </p>");
    await press({ key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("tells the visitor about replies being written, never about notes", async () => {
    const { write, onTyping, click, tab, onSend, button } = await open();
    await write("<p>a</p>");
    expect(onTyping).toHaveBeenCalledTimes(1);
    await click(tab("Internal note"));
    await write("<p>secret</p>");
    expect(onTyping).toHaveBeenCalledTimes(1);
    await click(button("Add note"));
    expect(onSend).toHaveBeenCalledWith({ body: "secret", is_note: true, attachments: [] });
  });

  it("sends a file without words", async () => {
    const { attach, click, button, onSend } = await open();
    await attach(new File(["x"], "a.pdf"));
    expect(container.textContent).toContain("a.pdf");
    await click(button("Send"));
    expect(onSend).toHaveBeenCalledWith({ body: "", is_note: false, attachments: [7] });
    expect(container.textContent).not.toContain("a.pdf");
  });

  it("waits for a file that is still uploading", async () => {
    const { attach, write, button } = await open({ onUpload: vi.fn(() => new Promise<ChatFile>(() => {})) });
    await attach(new File(["x"], "a.pdf"));
    await write("<p>Here</p>");
    expect(button("Send").disabled).toBe(true);
    await act(async () => button("Remove a.pdf").click());
    expect(button("Send").disabled).toBe(false);
  });

  it("says why a file can't be sent, and keeps the rest", async () => {
    const onUpload = vi.fn(async () => {
      throw new Error("Your storage didn't take the file.");
    });
    const { attach } = await open({ onUpload: onUpload as never });
    await attach(new File(["x"], "a.exe"));
    expect(container.querySelector("[role=alert]")!.textContent).toContain("picture");
    expect(onUpload).not.toHaveBeenCalled();
    await attach(new File(["x"], "a.pdf"));
    expect(container.querySelector("[role=alert]")!.textContent).toContain("storage");
    expect(container.querySelector("li")).toBeNull();
  });

  it("offers files only with a bucket", async () => {
    const { button } = await open({ uploadsEnabled: false });
    expect(button("Attach files (connect your storage first)").disabled).toBe(true);
  });

  it("keeps the text when sending fails", async () => {
    const { write, press, text } = await open({ onSend: vi.fn(async () => Promise.reject(new Error("Offline"))) as never });
    await write("<p>Hello</p>");
    await press({ key: "Enter" });
    expect(text()).toBe("Hello");
    expect(container.querySelector("[role=alert]")!.textContent).toBe("Offline");
  });

  it("keeps what is typed while a message is being sent", async () => {
    let done = () => {};
    const { write, press, text, button } = await open({ onSend: vi.fn(() => new Promise<void>((resolve) => (done = resolve))) });
    await write("<p>first</p>");
    await press({ key: "Enter" });
    await write("<p>second</p>");
    expect(button("Send").disabled).toBe(true);
    await act(async () => done());
    expect(text()).toBe("second");
    expect(button("Send").disabled).toBe(false);
  });

  it("puts a failed message back before what was typed since", async () => {
    let fail = () => {};
    const { write, press, text } = await open({ onSend: vi.fn(() => new Promise<void>((_, reject) => (fail = () => reject(new Error("Offline"))))) });
    await write("<p>first</p>");
    await press({ key: "Enter" });
    await write("<p>second</p>");
    await act(async () => fail());
    expect(text()).toBe("firstsecond");
  });

  it("puts emoji in the text", async () => {
    const { click, button, text } = await open();
    await click(button("Emoji"));
    await click(Array.from(container.querySelectorAll("button")).find((each) => each.textContent === "👍")!);
    expect(text()).toBe("👍");
  });
});

describe("messages in the inbox", () => {
  const show = (node: React.ReactNode) => act(async () => root.render(node));

  it("shows formatting", async () => {
    await show(<ChatText text={"**b** _i_ [l](/x)\n- one"} base="https://shop.example.com" />);
    expect(container.querySelector("strong")!.textContent).toBe("b");
    expect(container.querySelector("em")!.textContent).toBe("i");
    expect(container.querySelector("a")!.href).toBe("https://shop.example.com/x");
    expect(container.querySelectorAll("li")).toHaveLength(1);
  });

  it("never links to anything but pages, and shows a visitor's text as typed", async () => {
    await show(<ChatText text="[x](javascript:alert(1))" />);
    expect(container.querySelector("a")).toBeNull();
    await show(<ChatText text="[bank](https://evil.example.com)" plain />);
    expect(container.querySelector("a")!.textContent).toBe("https://evil.example.com");
  });

  it("shows pictures as pictures and other files by name", async () => {
    await show(<ChatFiles files={[{ ...saved("a.png"), content_type: "image/png", width: 560, height: 280 }, { ...saved("b.pdf"), id: 8 }]} />);
    const img = container.querySelector("img")!;
    expect([img.getAttribute("width"), img.getAttribute("height")]).toEqual(["280", "140"]);
    expect(container.textContent).toContain("b.pdf");
  });
});
