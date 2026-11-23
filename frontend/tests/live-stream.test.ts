import { afterEach, describe, expect, it, vi } from "vitest";
import { openLiveStream, SseParser, throttle, type LiveEvent } from "@/lib/live-stream";

describe("SseParser", () => {
  it("reads events, ids and JSON data", () => {
    const parser = new SseParser();
    const events = parser.feed('id: 41\nevent: message\ndata: {"body":"hi"}\n\nevent: typing\ndata: {"sender":"agent"}\n\n');
    expect(events).toEqual([
      { event: "message", id: "41", data: { body: "hi" } },
      { event: "typing", data: { sender: "agent" } },
    ]);
  });

  it("puts back together text split anywhere", () => {
    const parser = new SseParser();
    const text = 'event: status\ndata: {"text":"Searching the help center"}\n\n';
    const events: LiveEvent[] = [];
    for (const piece of [text.slice(0, 3), text.slice(3, 20), text.slice(20, -1), text.slice(-1)]) {
      events.push(...parser.feed(piece));
    }
    expect(events).toEqual([{ event: "status", data: { text: "Searching the help center" } }]);
  });

  it("skips comments and the retry hint", () => {
    const parser = new SseParser();
    expect(parser.feed("retry: 3000\n: connected\n\n: ping\n\n")).toEqual([]);
  });

  it("accepts CRLF line ends and multi-line data", () => {
    const parser = new SseParser();
    expect(parser.feed("data: one\r\ndata: two\r\n\r\n")).toEqual([{ event: "message", data: "one\ntwo" }]);
  });
});

/** A fetch whose responses are scripted: each call takes the next one. A stream response
 * stays open until `end()`; `push()` sends text on it. */
function fakeServer() {
  const calls: { url: string; headers: Record<string, string> }[] = [];
  const script: (() => Response | Promise<Response>)[] = [];
  let controller: ReadableStreamDefaultController<Uint8Array> | null = null;
  const encoder = new TextEncoder();
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, headers: init.headers as Record<string, string> });
    const next = script.shift();
    if (!next) return new Promise<Response>(() => {}); // hang: no more scripted answers
    return next();
  });
  return {
    calls,
    fetch: fetch as unknown as typeof globalThis.fetch,
    stream() {
      script.push(
        () =>
          new Response(
            new ReadableStream<Uint8Array>({
              start(c) {
                controller = c;
              },
            }),
            { status: 200, headers: { "Content-Type": "text/event-stream" } },
          ),
      );
    },
    status(code: number) {
      script.push(() => new Response("{}", { status: code }));
    },
    networkError() {
      script.push(() => Promise.reject(new TypeError("Failed to fetch")));
    },
    push(text: string) {
      controller!.enqueue(encoder.encode(text));
    },
    end() {
      controller!.close();
    },
  };
}

const tick = (ms = 5) => new Promise((resolve) => setTimeout(resolve, ms));

describe("openLiveStream", () => {
  let close = () => {};
  afterEach(() => close());

  it("sends the token in a header and delivers events", async () => {
    const server = fakeServer();
    server.stream();
    const events: LiveEvent[] = [];
    const states: boolean[] = [];
    const stream = openLiveStream({
      url: "https://chat.example.com/api/v1/widget/ws_1/stream",
      headers: () => ({ "X-Visitor-Token": "vt_secret" }),
      onEvent: (e) => events.push(e),
      onLive: (live) => states.push(live),
      fetch: server.fetch,
    });
    close = stream.close;
    await tick();
    expect(server.calls[0].url).toBe("https://chat.example.com/api/v1/widget/ws_1/stream");
    expect(server.calls[0].url).not.toContain("vt_secret");
    expect(server.calls[0].headers["X-Visitor-Token"]).toBe("vt_secret");
    expect(server.calls[0].headers).not.toHaveProperty("Last-Event-ID");
    expect(stream.live).toBe(true);

    server.push('retry: 3000\n: connected\n\nid: 7\nevent: message\ndata: {"message":{"id":7}}\n\n');
    await tick();
    expect(events).toEqual([{ event: "message", id: "7", data: { message: { id: 7 } } }]);
    expect(states).toEqual([true]);
  });

  it("reconnects at once when the server ends the stream, from the last message it has", async () => {
    const server = fakeServer();
    server.stream();
    let lastId = 7;
    const opened = vi.fn();
    const stream = openLiveStream({
      url: "/stream",
      headers: () => ({}),
      lastEventId: () => lastId,
      onEvent: () => {},
      onOpen: opened,
      fetch: server.fetch,
    });
    close = stream.close;
    await tick();
    lastId = 12;
    server.stream();
    server.end();
    await tick();
    expect(server.calls.map((c) => c.headers["Last-Event-ID"])).toEqual(["7", "12"]);
    expect(opened).toHaveBeenCalledTimes(2);
    expect(stream.live).toBe(true);
  });

  it("goes to polling while the connection fails, and back when it returns", async () => {
    const server = fakeServer();
    server.stream();
    const states: boolean[] = [];
    const stream = openLiveStream({
      url: "/stream",
      headers: () => ({}),
      onEvent: () => {},
      onLive: (live) => states.push(live),
      retryDelays: [10],
      fetch: server.fetch,
    });
    close = stream.close;
    await tick();
    server.networkError();
    server.stream();
    server.end(); // dropped; the reconnect then fails, and the one after works
    await tick(40);
    expect(states).toEqual([true, false, true]);
    expect(server.calls).toHaveLength(3);
  });

  it("gives up when the server refuses the token", async () => {
    const server = fakeServer();
    server.status(401);
    const states: boolean[] = [];
    const stream = openLiveStream({
      url: "/stream",
      headers: () => ({}),
      onEvent: () => {},
      onLive: (live) => states.push(live),
      retryDelays: [5],
      fetch: server.fetch,
    });
    close = stream.close;
    await tick(30);
    expect(server.calls).toHaveLength(1);
    expect(stream.live).toBe(false);
  });

  it("stays on polling when the server has no live updates (503)", async () => {
    const server = fakeServer();
    server.status(503);
    const stream = openLiveStream({ url: "/stream", headers: () => ({}), onEvent: () => {}, retryDelays: [5], fetch: server.fetch });
    close = stream.close;
    await tick(30);
    // It tries again only after a long wait.
    expect(server.calls).toHaveLength(1);
    expect(stream.live).toBe(false);
  });

  it("treats a silent connection as dead", async () => {
    const server = fakeServer();
    server.stream();
    const stream = openLiveStream({
      url: "/stream",
      headers: () => ({}),
      onEvent: () => {},
      silenceMs: 20,
      retryDelays: [5],
      fetch: server.fetch,
    });
    close = stream.close;
    await tick(60);
    expect(server.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("stops delivering once closed", async () => {
    const server = fakeServer();
    server.stream();
    const onEvent = vi.fn();
    const stream = openLiveStream({ url: "/stream", headers: () => ({}), onEvent, fetch: server.fetch });
    await tick();
    stream.close();
    await tick();
    expect(stream.live).toBe(false);
    expect(server.calls).toHaveLength(1);
    expect(onEvent).not.toHaveBeenCalled();
  });
});

describe("throttle", () => {
  it("sends at most once per window", () => {
    let now = 0;
    const send = vi.fn();
    const typing = throttle(send, 3000, () => now);
    typing();
    typing();
    now = 2999;
    typing();
    expect(send).toHaveBeenCalledTimes(1);
    now = 3000;
    typing();
    expect(send).toHaveBeenCalledTimes(2);
  });
});
