// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WidgetApi } from "@/widget/api";
import { Widget } from "@/widget/widget";

const BASE = "https://chat.example.com/api/v1/widget/ws_1";

/** The widget's API, with a live stream the test writes to. */
function fakeServer({ streamStatus = 200 } = {}) {
  const calls: { method: string; path: string; headers: Record<string, string> }[] = [];
  const encoder = new TextEncoder();
  let stream: ReadableStreamDefaultController<Uint8Array> | null = null;
  const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const path = url.replace(BASE, "").split("?")[0];
      calls.push({ method: init.method ?? "GET", path, headers: (init.headers ?? {}) as Record<string, string> });
      if (path === "/config") return json({ name: "Acme", website: "", color: "#2563eb", greeting: "Hi!", ai_enabled: true, max_message_length: 500 });
      if (path === "/session") return json({ token: "vt_1", visitor_id: 1, conversation_id: 5, last_message_id: 10 });
      if (path === "/messages") {
        return json({ conversation_id: 5, human_requested: false, messages: [message(10, "visitor", "Where is my order?")] });
      }
      if (path === "/typing") return json({ ok: true });
      if (path === "/stream") {
        if (streamStatus !== 200) return new Response("{}", { status: streamStatus });
        return new Response(new ReadableStream({ start: (c) => void (stream = c) }), { status: 200 });
      }
      return new Response("{}", { status: 404 });
    }),
  );
  return {
    calls,
    send(event: string, data: unknown) {
      stream!.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
    },
  };
}

function message(id: number, sender: string, body: string, author_name = "") {
  return { id, sender, body, author_name, a2ui: null, created_at: "2026-11-23T10:00:00Z" };
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 10));

async function startWidget() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const widget = new Widget(new WidgetApi("https://chat.example.com", "ws_1"), host);
  await widget.start();
  await settle();
  widget.toggle(true);
  const root = host.shadowRoot!;
  return {
    widget,
    root,
    bubbles: () => Array.from(root.querySelectorAll(".bubble:not(.typing)")).map((b) => b.textContent),
    activity: () => root.querySelector(".activity")?.textContent ?? null,
  };
}

describe("the widget on a live stream", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  it("opens the stream with the visitor token in a header, resuming after the newest message", async () => {
    const server = fakeServer();
    await startWidget();
    const opened = server.calls.find((c) => c.path === "/stream")!;
    expect(opened.headers["X-Visitor-Token"]).toBe("vt_1");
    expect(opened.headers["Last-Event-ID"]).toBe("10");
  });

  it("shows what the AI is doing, then its reply", async () => {
    const server = fakeServer();
    const ui = await startWidget();

    server.send("status", { conversation_id: 5, text: "Searching the help center" });
    await settle();
    expect(ui.activity()).toBe("Searching the help center");

    server.send("message", { conversation_id: 5, message: message(11, "bot", "It shipped yesterday.") });
    await settle();
    expect(ui.bubbles()).toContain("It shipped yesterday.");
    expect(ui.activity()).toBeNull();
  });

  it("shows a teammate typing", async () => {
    const server = fakeServer();
    const ui = await startWidget();
    server.send("typing", { conversation_id: 5, sender: "agent", name: "Priya" });
    await settle();
    expect(ui.activity()).toBe("Priya is typing");
  });

  it("ignores a message it already has", async () => {
    const server = fakeServer();
    const ui = await startWidget();
    server.send("message", { conversation_id: 5, message: message(10, "visitor", "Where is my order?") });
    await settle();
    expect(ui.bubbles().filter((b) => b === "Where is my order?")).toHaveLength(1);
  });

  it("sends typing at most every few seconds", async () => {
    const server = fakeServer();
    const ui = await startWidget();
    const input = ui.root.querySelector("textarea")!;
    for (const text of ["W", "Wh", "Whe"]) {
      input.value = text;
      input.dispatchEvent(new Event("input"));
    }
    await settle();
    expect(server.calls.filter((c) => c.path === "/typing")).toHaveLength(1);
  });

  it("doesn't poll while the stream is live, and no longer sends a heartbeat", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "setInterval", "clearTimeout", "clearInterval"] });
    try {
      const server = fakeServer();
      const start = startWidget();
      await vi.advanceTimersByTimeAsync(20);
      await start;
      const before = server.calls.length;
      await vi.advanceTimersByTimeAsync(60000);
      const later = server.calls.slice(before).map((c) => c.path);
      expect(later.filter((p) => p === "/messages" || p === "/session")).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("polls when the server has no live updates", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "setInterval", "clearTimeout", "clearInterval"] });
    try {
      const server = fakeServer({ streamStatus: 503 });
      const start = startWidget();
      await vi.advanceTimersByTimeAsync(20);
      await start;
      const before = server.calls.length;
      await vi.advanceTimersByTimeAsync(10000);
      expect(server.calls.slice(before).filter((c) => c.path === "/messages").length).toBeGreaterThanOrEqual(3);
    } finally {
      vi.useRealTimers();
    }
  });
});
