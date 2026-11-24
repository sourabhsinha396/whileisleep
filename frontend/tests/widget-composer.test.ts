// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WidgetApi } from "@/widget/api";
import { continues, timeOf } from "@/widget/groups";
import { Widget } from "@/widget/widget";

const BASE = "https://chat.example.com/api/v1/widget/ws_1";
const FACE = "https://cdn.example.com/users/1/photo/a.png";
const settle = () => new Promise((resolve) => setTimeout(resolve, 10));

type Json = Record<string, unknown>;

/** The widget on a fake server. `messages` is the chat so far. */
async function start({ config = {}, messages = [] as Json[], sendStatus = 200, uploadStatus = 200 } = {}) {
  const sent: Json[] = [];
  const uploaded: string[] = [];
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const path = url.replace(BASE, "").split("?")[0];
      if (path === "/config") return json({ name: "Acme Store", website: "", color: "#2563eb", logo_url: "", greeting: "Hi!", ai_enabled: false, max_message_length: 50, ...config });
      if (path === "/session") return json({ token: "vt_1", visitor_id: 1, conversation_id: messages.length ? 5 : null, last_message_id: null });
      if (path === "/attachments") {
        if (uploadStatus !== 200) return json({ detail: "The file couldn't be saved." }, uploadStatus);
        const file = (init.body as FormData).get("file") as File;
        uploaded.push(file.name);
        return json({ id: uploaded.length, name: file.name, url: `https://files.example.com/${file.name}`, content_type: "application/pdf", size: 10, width: null, height: null });
      }
      if (path === "/messages" && init.method === "POST") {
        const body = JSON.parse(init.body as string);
        sent.push(body);
        if (sendStatus !== 200) return json({ detail: "Too fast" }, sendStatus);
        return json({ conversation_id: 5, human_requested: false, messages: [{ id: 100 + sent.length, sender: "visitor", body: body.body, author_name: "", a2ui: null, created_at: new Date().toISOString() }] });
      }
      if (path === "/messages") return json({ conversation_id: 5, human_requested: false, messages });
      if (path === "/typing") return json({ ok: true });
      return json({}, 404);
    }),
  );
  const host = document.createElement("div");
  document.body.appendChild(host);
  const widget = new Widget(new WidgetApi("https://chat.example.com", "ws_1"), host);
  await widget.start();
  widget.toggle(true);
  const root = host.shadowRoot!;
  const input = root.querySelector("textarea")!;
  return {
    widget,
    root,
    sent,
    uploaded,
    input,
    write: (text: string) => {
      input.value = text;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    },
    enter: async () => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
      await settle();
    },
    attach: async (...files: File[]) => {
      const picker = root.querySelector<HTMLInputElement>("input[type=file]")!;
      Object.defineProperty(picker, "files", { configurable: true, value: files });
      picker.dispatchEvent(new Event("change"));
      await settle();
    },
    send: root.querySelector<HTMLButtonElement>(".send")!,
    error: () => root.querySelector(".error")!.textContent,
    chips: () => Array.from(root.querySelectorAll(".file-name")).map((node) => node.textContent),
    rows: () => Array.from(root.querySelectorAll<HTMLElement>(".msg")),
  };
}

const message = (id: number, sender: string, body: string, extra: Json = {}) => ({ id, sender, body, author_name: "", a2ui: null, created_at: "2026-11-23T10:00:00Z", ...extra });
const pdf = (name = "a.pdf") => new File(["x"], name, { type: "application/pdf" });

beforeEach(() => localStorage.clear());
afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
});

describe("the widget's message box", () => {
  it("sends with Enter and empties", async () => {
    const { write, enter, sent, input, send } = await start();
    expect(send.disabled).toBe(true);
    write("Hello");
    expect(send.disabled).toBe(false);
    await enter();
    expect(sent).toEqual([{ body: "Hello" }]);
    expect(input.value).toBe("");
  });

  it("puts a message that failed back, before what was typed since", async () => {
    const { write, enter, input, error } = await start({ sendStatus: 429 });
    write("Hello");
    const done = enter();
    write("and");
    await done;
    expect(input.value).toBe("Hello\nand");
    expect(error()).toContain("Too fast");
  });

  it("sends files, with or without words", async () => {
    const { attach, write, enter, sent, chips, send } = await start({ config: { uploads_enabled: true } });
    await attach(pdf("a.pdf"), pdf("b.pdf"));
    expect(chips()).toEqual(["a.pdf", "b.pdf"]);
    expect(send.disabled).toBe(false);
    await enter();
    expect(sent).toEqual([{ body: "", attachments: [1, 2] }]);
    expect(chips()).toEqual([]);
    write("no files now");
    await enter();
    expect(sent[1]).toEqual({ body: "no files now" });
  });

  it("offers files only when the workspace takes them", async () => {
    const { root } = await start();
    expect(root.querySelector("input[type=file]")).toBeNull();
    expect(root.querySelector("[aria-label='Send a file']")).toBeNull();
  });

  it("says why a file can't be sent", async () => {
    const { attach, uploaded, error, chips } = await start({ config: { uploads_enabled: true }, uploadStatus: 502 });
    await attach(pdf("a.exe"));
    expect(uploaded).toEqual([]);
    expect(error()).toContain("picture");
    await attach(pdf());
    expect(error()).toBe("The file couldn't be saved.");
    expect(chips()).toEqual([]);
  });

  it("takes at most five files, and gives one back when it is removed", async () => {
    const { attach, chips, error, root } = await start({ config: { uploads_enabled: true } });
    await attach(...["1", "2", "3", "4", "5", "6"].map((n) => pdf(`${n}.pdf`)));
    expect(chips()).toHaveLength(5);
    expect(error()).toContain("5 files");
    root.querySelector<HTMLButtonElement>("[aria-label='Remove 2.pdf']")!.click();
    expect(chips()).toEqual(["1.pdf", "3.pdf", "4.pdf", "5.pdf"]);
  });

  it("keeps the host page's text within the limit", async () => {
    const { widget, input } = await start();
    await widget.openWith("x".repeat(80));
    expect(input.value).toHaveLength(50);
  });

  it("puts emoji where the cursor is", async () => {
    const { root, write, input } = await start();
    write("ab");
    input.setSelectionRange(1, 1);
    const picker = root.querySelector<HTMLElement>(".emoji")!;
    root.querySelector<HTMLButtonElement>("[aria-label=Emoji]")!.click();
    expect(picker.hidden).toBe(false);
    Array.from(picker.querySelectorAll("button")).find((each) => each.textContent === "👍")!.click();
    expect(input.value).toBe("a👍b");
    expect(picker.hidden).toBe(true);
  });

  it("forgets the draft when the person signs out", async () => {
    const { widget, write, input } = await start();
    write("private");
    await widget.reset();
    expect(input.value).toBe("");
  });
});

describe("the widget's messages", () => {
  it("shows pictures as pictures, and as files when the site blocks them", async () => {
    const picture = { id: 1, name: "a.png", url: "https://files.example.com/a.png", content_type: "image/png", size: 10, width: 440, height: 220 };
    const { root } = await start({ messages: [message(1, "agent", "", { attachments: [picture] })] });
    const img = root.querySelector<HTMLImageElement>(".photo img")!;
    expect([img.width, img.height]).toEqual([220, 110]);
    expect(root.querySelector<HTMLAnchorElement>(".photo")!.rel).toBe("noopener noreferrer");
    img.dispatchEvent(new Event("error"));
    expect(root.querySelector(".photo")).toBeNull();
    expect(root.querySelector(".file-card")!.textContent).toContain("a.png");
  });

  it("names a person once for what they said in a row", async () => {
    const { rows } = await start({
      messages: [
        message(1, "agent", "a", { author_name: "Maya" }),
        message(2, "agent", "b", { author_name: "Maya" }),
        message(3, "agent", "c", { author_name: "Sam" }),
        message(4, "visitor", "d"),
      ],
    });
    // The first row is the greeting.
    expect(rows().slice(1).map((row) => row.querySelector(".who")?.firstChild?.textContent ?? null)).toEqual(["Maya", null, "Sam", "You"]);
    expect(rows().slice(1, 4).map((row) => row.querySelector(".av")!.classList.contains("none"))).toEqual([true, false, false]);
  });

  it("marks the AI by its icon alone", async () => {
    const { rows } = await start({ messages: [message(1, "bot", "a")] });
    expect(rows()[1].querySelector(".who")!.firstChild!.textContent).toBe("Acme Store");
    expect(rows()[1].querySelector(".av")!.getAttribute("aria-label")).toBe("AI assistant");
  });

  it("shows the visitor's own message as typed", async () => {
    const { rows } = await start({ messages: [message(1, "visitor", "**hi**"), message(2, "agent", "**hi**")] });
    expect(rows()[1].querySelector("strong")).toBeNull();
    expect(rows()[2].querySelector("strong")!.textContent).toBe("hi");
  });

  it("groups by person and time", () => {
    const one = { sender: "agent" as const, author_name: "Maya", created_at: "2026-11-23T10:00:00Z" };
    expect(continues(one, { ...one, created_at: "2026-11-23T10:04:00Z" })).toBe(true);
    expect(continues(one, { ...one, created_at: "2026-11-23T10:06:00Z" })).toBe(false);
    expect(continues(one, { ...one, author_name: "Sam" })).toBe(false);
    expect(continues({ ...one, created_at: undefined }, one)).toBe(false);
    expect(continues(undefined, one)).toBe(false);
  });

  it("says the day of older messages", () => {
    const now = new Date("2026-11-24T12:00:00");
    expect(timeOf("2026-11-24T10:32:00", now)).not.toContain(",");
    expect(timeOf("2026-11-20T10:32:00", now)).toContain("20");
  });
});

describe("the widget's header", () => {
  it("shows the logo and the team's photos, and no text", async () => {
    const { root } = await start({ config: { team: [{ name: "Maya", photo_url: FACE }, { name: "Sam", photo_url: `${FACE}?2` }] } });
    const faces = root.querySelector(".faces")!;
    expect(Array.from(faces.querySelectorAll(".face img")).map((img) => img.getAttribute("src"))).toEqual([FACE, `${FACE}?2`]);
    expect(faces.textContent).toBe("AS");
    expect(root.querySelector(".panel")!.getAttribute("aria-label")).toBe("Chat with Acme Store");
  });

  it("leaves out a photo that can't load", async () => {
    const { root } = await start({ config: { team: [{ name: "Maya", photo_url: FACE }] } });
    root.querySelector(".face img")!.dispatchEvent(new Event("error"));
    expect(root.querySelector(".face")).toBeNull();
  });
});
