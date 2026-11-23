/**
 * Reads a server-sent event stream with fetch(), for the widget and the dashboard.
 *
 * Not EventSource: that can't send headers, and the visitor and dashboard tokens must go in
 * headers, never the URL. Reconnects by itself, sending `Last-Event-ID` with the last message
 * id the page has so the server sends what was missed. While the stream is down the page is
 * told (`onLive(false)`) and polls instead; the stream keeps trying in the background.
 *
 * Plain TypeScript (no React): the widget bundle uses it too.
 */

export interface LiveEvent {
  event: string;
  data: unknown;
  id?: string;
}

/** Turns SSE text into events. Text can arrive split anywhere, even mid-line. */
export class SseParser {
  private buffer = "";

  feed(text: string): LiveEvent[] {
    this.buffer += text.replace(/\r\n?/g, "\n");
    const events: LiveEvent[] = [];
    let end: number;
    while ((end = this.buffer.indexOf("\n\n")) !== -1) {
      const block = this.buffer.slice(0, end);
      this.buffer = this.buffer.slice(end + 2);
      const event = parseBlock(block);
      if (event) events.push(event);
    }
    return events;
  }
}

function parseBlock(block: string): LiveEvent | null {
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue; // comments: keep-alive pings
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
    else if (field === "id") id = value;
  }
  if (!data.length) return null;
  const text = data.join("\n");
  let parsed: unknown = text;
  try {
    parsed = JSON.parse(text);
  } catch {
    /* not JSON: hand over the text */
  }
  return { event, data: parsed, ...(id !== undefined ? { id } : {}) };
}

export interface LiveStreamOptions {
  url: string;
  /** Read at every (re)connect, so a changed token is picked up. */
  headers: () => Record<string, string>;
  /** The newest message id the page has, sent as Last-Event-ID; null for none. */
  lastEventId?: () => number | null;
  onEvent: (event: LiveEvent) => void;
  /** True once connected; false when the connection fails (poll meanwhile). Called on changes only. */
  onLive?: (live: boolean) => void;
  /** Called after each successful connect, including the first. */
  onOpen?: () => void;
  /** Waits before each retry after a failure, in ms; the last repeats. */
  retryDelays?: number[];
  /** No bytes for this long (the server pings every 15 s) means the connection is dead. */
  silenceMs?: number;
  fetch?: typeof fetch;
}

export interface LiveStream {
  close(): void;
  readonly live: boolean;
}

const RETRY_DELAYS = [1000, 3000, 10000, 30000];
// The server sends 503 when it has no live updates at all; try again rarely.
const UNAVAILABLE_DELAY = 60000;

class StopError extends Error {}

export function openLiveStream(options: LiveStreamOptions): LiveStream {
  const delays = options.retryDelays ?? RETRY_DELAYS;
  const silenceMs = options.silenceMs ?? 45000;
  const doFetch = options.fetch ?? ((input, init) => fetch(input, init));
  let closed = false;
  let live = false;
  let failures = 0;
  let controller: AbortController | null = null;
  let retryTimer: ReturnType<typeof setTimeout> | undefined;

  const setLive = (value: boolean) => {
    if (value === live) return;
    live = value;
    options.onLive?.(value);
  };

  async function connect(): Promise<number | "stop"> {
    controller = new AbortController();
    const abort = controller;
    let silence: ReturnType<typeof setTimeout> | undefined;
    const watch = () => {
      clearTimeout(silence);
      silence = setTimeout(() => abort.abort(), silenceMs);
    };
    try {
      const last = options.lastEventId?.();
      const response = await doFetch(options.url, {
        headers: {
          Accept: "text/event-stream",
          ...options.headers(),
          ...(last !== null && last !== undefined ? { "Last-Event-ID": String(last) } : {}),
        },
        cache: "no-store",
        signal: abort.signal,
      });
      if (response.status === 401 || response.status === 403 || response.status === 404) {
        throw new StopError(`stream refused (${response.status})`);
      }
      if (response.status === 503) return UNAVAILABLE_DELAY;
      if (!response.ok || !response.body) throw new Error(`stream failed (${response.status})`);

      failures = 0;
      setLive(true);
      options.onOpen?.();
      watch();
      const reader = response.body.getReader();
      // Aborting the request doesn't always cancel a body already being read.
      abort.signal.addEventListener("abort", () => reader.cancel().catch(() => {}));
      const decoder = new TextDecoder();
      const parser = new SseParser();
      for (;;) {
        const { done, value } = await reader.read();
        if (closed) return "stop";
        // Cancelled for silence: a dead connection, so a failure (not a normal end).
        if (abort.signal.aborted) throw new Error("stream went silent");
        if (done) break;
        watch();
        for (const event of parser.feed(decoder.decode(value, { stream: true }))) {
          if (closed) return "stop";
          options.onEvent(event);
        }
      }
      // The server ended the stream (it does every few minutes): reconnect at once.
      return 0;
    } catch (error) {
      if (closed || error instanceof StopError) return "stop";
      return delays[Math.min(failures++, delays.length - 1)];
    } finally {
      clearTimeout(silence);
    }
  }

  async function run() {
    while (!closed) {
      const wait = await connect();
      if (closed || wait === "stop") break;
      if (wait > 0) {
        setLive(false);
        await new Promise((resolve) => (retryTimer = setTimeout(resolve, wait)));
      }
    }
    setLive(false);
  }

  run();
  return {
    close() {
      closed = true;
      live = false;
      clearTimeout(retryTimer);
      controller?.abort();
    },
    get live() {
      return live;
    },
  };
}

/** Calls `send` at most once every `everyMs` while it keeps being asked; for typing. */
export function throttle(send: () => void, everyMs: number, now: () => number = Date.now) {
  let last = -Infinity;
  return () => {
    if (now() - last < everyMs) return;
    last = now();
    send();
  };
}
