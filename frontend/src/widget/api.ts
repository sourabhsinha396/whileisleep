import type { A2uiMessage, ActionEvent } from "@/lib/a2ui/surface";
import type { ChatFile } from "@/lib/chat-file";
import { errorMessage } from "./limits";

export interface WidgetConfig {
  name: string;
  website: string;
  max_message_length: number;
  color: string;
  /** The pattern behind the messages. */
  background?: string;
  /** "light", "dark", or "auto" for what the visitor's device is set to. */
  color_mode?: string;
  /** Empty without one; initials show instead. */
  logo_url: string;
  greeting: string;
  ai_enabled: boolean;
  /** Visitors can send files. */
  uploads_enabled?: boolean;
  /** A few teammates with photos. */
  team?: { name: string; photo_url: string }[];
}

export interface ChatMessage {
  id: number;
  sender: "visitor" | "agent" | "bot" | "system";
  author_name: string;
  author_photo?: string;
  body: string;
  a2ui: A2uiMessage[] | null;
  /** Its form was sent; show it disabled. */
  form_submitted?: boolean;
  attachments?: ChatFile[];
  created_at: string;
}

/** What the live stream sends (apps/realtime on the server). */
export type StreamEvent =
  | { event: "message"; data: { conversation_id: number; message: ChatMessage } }
  | { event: "conversation"; data: { id: number; human_requested: boolean } }
  | { event: "status"; data: { conversation_id: number; text: string } }
  | { event: "typing"; data: { conversation_id: number; sender: "agent" | "visitor"; name: string; photo?: string } };

export interface MessagesResponse {
  conversation_id: number | null;
  human_requested: boolean;
  messages: ChatMessage[];
}

/** What a host-site button says the visitor wants, sent with the message it typed in. */
export interface Intent {
  intent: string;
  data?: Record<string, string | number | boolean>;
}

/** What identify() accepts. Without `token` these are the page's word for it: shown to the
 * team, but not proof. `token` is a short-lived JWT your server signed with the workspace's
 * identity secret; its claims become verified attributes. */
export interface Identity {
  name?: string;
  email?: string;
  attributes?: Record<string, string | number | boolean>;
  token?: string;
}

export interface Article {
  id: number;
  title: string;
  body: string;
}

/** Talks to /api/v1/widget/{key}. Keeps the visitor token in localStorage per workspace. */
export class WidgetApi {
  private readonly base: string;
  private readonly storageKey: string;
  token: string;

  constructor(apiOrigin: string, readonly key: string) {
    this.base = `${apiOrigin.replace(/\/$/, "")}/api/v1/widget/${encodeURIComponent(key)}`;
    this.storageKey = `whileisleep:${key}`;
    this.token = readStorage(this.storageKey);
  }

  private async call<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(this.base + path, {
      ...init,
      headers: {
        // A form (a file upload) is sent as it is: the browser writes its content type.
        ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(this.token ? { "X-Visitor-Token": this.token } : {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(errorMessage(data, response.status));
    return data as T;
  }

  /** Drops the visitor token; the next session() starts a new visitor. */
  forget() {
    this.token = "";
    try {
      localStorage.removeItem(this.storageKey);
    } catch {
      /* ignore */
    }
  }

  config() {
    return this.call<WidgetConfig>("/config");
  }

  async session(identity: Identity = {}) {
    const { token, ...details } = identity;
    const data = await this.call<{ token: string; conversation_id: number | null; last_message_id: number | null }>(
      "/session",
      {
        method: "POST",
        body: JSON.stringify({
          url: location.href,
          title: document.title,
          referrer: document.referrer,
          ...details,
          ...(token ? { identity_token: token } : {}),
        }),
      },
    );
    // A signed-in user may already have a visitor record (from another device): the server
    // answers with that one's token, and we continue as them.
    this.token = data.token;
    writeStorage(this.storageKey, data.token);
    return data;
  }

  /** Starts a new chat for this visitor; the old one stays in the team's inbox. */
  restart() {
    return this.call<{ ok: boolean }>("/restart", { method: "POST" });
  }

  messages(after: number) {
    return this.call<MessagesResponse>(`/messages?after=${after}`);
  }

  /** The live stream (server-sent events); read with lib/live-stream, token in the header. */
  get streamUrl() {
    return `${this.base}/stream`;
  }

  streamHeaders(): Record<string, string> {
    return this.token ? { "X-Visitor-Token": this.token } : {};
  }

  /** The visitor is typing; the team's inbox shows it. Callers throttle it. */
  typing() {
    return this.call<{ ok: boolean }>("/typing", { method: "POST" });
  }

  send(body: string, intent?: Intent, attachments: number[] = []) {
    return this.call<MessagesResponse>("/messages", {
      method: "POST",
      body: JSON.stringify({ body, ...(attachments.length ? { attachments } : {}), ...(intent ? { intent: intent.intent, data: intent.data ?? {} } : {}) }),
    });
  }

  /** Stores a file the visitor is about to send; `send` with its id attaches it. */
  upload(file: File) {
    const body = new FormData();
    body.append("file", file);
    return this.call<ChatFile>("/attachments", { method: "POST", body });
  }

  action(event: ActionEvent) {
    return this.call<{ article?: Article }>("/actions", { method: "POST", body: JSON.stringify(event) });
  }

  articles(q: string) {
    return this.call<{ id: number; title: string; excerpt: string }[]>(`/articles?q=${encodeURIComponent(q)}`);
  }

  article(id: number) {
    return this.call<Article>(`/articles/${id}`);
  }
}

// Storage can be blocked (private mode, sandboxed iframes); the widget still works for the page view.
function readStorage(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function writeStorage(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}
