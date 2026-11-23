import type { A2uiMessage, ActionEvent } from "@/lib/a2ui/surface";

export interface WidgetConfig {
  name: string;
  website: string;
  color: string;
  greeting: string;
  ai_enabled: boolean;
}

export interface ChatMessage {
  id: number;
  sender: "visitor" | "agent" | "bot" | "system";
  author_name: string;
  body: string;
  a2ui: A2uiMessage[] | null;
  created_at: string;
}

export interface MessagesResponse {
  conversation_id: number | null;
  human_requested: boolean;
  messages: ChatMessage[];
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
        "Content-Type": "application/json",
        ...(this.token ? { "X-Visitor-Token": this.token } : {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error((data as { detail?: string }).detail ?? `HTTP ${response.status}`);
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

  async session(extra: { name?: string; email?: string } = {}) {
    const data = await this.call<{ token: string; conversation_id: number | null; last_message_id: number | null }>(
      "/session",
      {
        method: "POST",
        body: JSON.stringify({ url: location.href, title: document.title, referrer: document.referrer, ...extra }),
      },
    );
    this.token = data.token;
    writeStorage(this.storageKey, data.token);
    return data;
  }

  messages(after: number) {
    return this.call<MessagesResponse>(`/messages?after=${after}`);
  }

  send(body: string) {
    return this.call<MessagesResponse>("/messages", { method: "POST", body: JSON.stringify({ body }) });
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
