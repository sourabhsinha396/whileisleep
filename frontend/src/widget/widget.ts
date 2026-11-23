import { renderSurface } from "@/lib/a2ui/render";
import { applyMessages, type ActionEvent } from "@/lib/a2ui/surface";
import { WidgetApi, type ChatMessage, type Intent, type WidgetConfig } from "./api";
import { styles } from "./styles";
import { counterText } from "./limits";
import { formatText } from "./text";

const ICONS = {
  chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>',
};

const POLL_OPEN_MS = 2500;
const POLL_CLOSED_MS = 15000;
const HEARTBEAT_MS = 20000;
const TYPING_TIMEOUT_MS = 45000;

type Tab = "chat" | "help";

/** The chat bubble and panel. All DOM lives in a shadow root on `host`. */
export class Widget {
  private root: ShadowRoot;
  private config!: WidgetConfig;
  private messages: ChatMessage[] = [];
  private lastId = 0;
  private seenId = 0;
  private open = false;
  private tab: Tab = "chat";
  private waitingForReply = 0;
  private humanRequested = false;
  // Surfaces whose buttons were used; they render disabled so they can't fire twice.
  private usedSurfaces = new Set<string>();
  private pollTimer?: ReturnType<typeof setTimeout>;
  // Label from open(message, intent), sent with the next message unless the visitor clears the box.
  private pendingIntent?: Intent;
  private el: { [name: string]: HTMLElement } = {};

  // Resolves once the panel is built; calls made before then wait for it.
  private ready: Promise<void>;
  private markReady!: () => void;

  constructor(
    private api: WidgetApi,
    private host: HTMLElement,
  ) {
    this.root = host.attachShadow({ mode: "open" });
    this.ready = new Promise((resolve) => (this.markReady = resolve));
  }

  async start() {
    this.config = await this.api.config();
    const session = await this.api.session();
    this.seenId = Number(readSeen(this.api.key)) || 0;
    this.build();
    this.markReady();
    if (session.conversation_id) await this.poll(false);
    this.schedulePoll();
    setInterval(() => this.api.session().catch(() => {}), HEARTBEAT_MS);
  }

  // --- public API (window.whileisleep) ---

  /** Opens the chat; with `message`, types it in ready to send. `intent` labels that message
   * for the workspace's rules (e.g. {intent: "exam_request", data: {exam_code: "SY0-401"}}). */
  async openWith(message?: string, intent?: Intent) {
    await this.ready;
    this.switchTab("chat");
    this.toggle(true);
    const input = this.el.input as HTMLTextAreaElement;
    // A host page's message can't skip the limit either.
    if (message) input.value = message.slice(0, input.maxLength > 0 ? input.maxLength : undefined);
    this.pendingIntent = message && intent?.intent ? intent : undefined;
  }

  async close() {
    await this.ready;
    this.toggle(false);
  }

  /** Hides the bubble entirely, e.g. on pages where it would cover the work. */
  setHidden(hidden: boolean) {
    this.host.style.display = hidden ? "none" : "";
    if (hidden && this.open) this.close();
  }

  async identify(details: { name?: string; email?: string }) {
    await this.ready;
    await this.api.session(details);
  }

  /** Forgets this visitor (call on sign-out) so the next person here starts a new chat. */
  async reset() {
    await this.ready;
    this.api.forget();
    writeSeen(this.api.key, "");
    this.messages = [];
    this.lastId = this.seenId = 0;
    this.humanRequested = false;
    this.waitingForReply = 0;
    this.usedSurfaces.clear();
    await this.api.session();
    this.renderBody();
    this.renderBadge();
  }

  toggle(force?: boolean) {
    this.open = force ?? !this.open;
    this.el.panel.hidden = !this.open;
    this.el.launcher.innerHTML = this.open ? ICONS.close : ICONS.chat;
    this.el.launcher.setAttribute("aria-label", this.open ? "Close chat" : "Open chat");
    if (this.open) {
      this.markSeen();
      this.renderBody();
      this.poll(true);
      (this.el.input as HTMLTextAreaElement).focus();
    }
    this.renderBadge();
  }


  // --- building ---

  private build() {
    const style = document.createElement("style");
    style.textContent = styles;
    const wrap = document.createElement("div");
    wrap.className = "od";
    wrap.style.setProperty("--od-color", /^#[0-9a-f]{3,8}$/i.test(this.config.color) ? this.config.color : "#2563eb");

    const launcher = button("launcher", "", () => this.toggle());
    launcher.innerHTML = ICONS.chat;
    launcher.setAttribute("aria-label", "Open chat");

    const panel = div("panel");
    panel.hidden = true;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", `Chat with ${this.config.name}`);

    const head = div("head");
    const title = document.createElement("h2");
    title.textContent = this.config.name;
    const sub = document.createElement("span");
    sub.className = "sub";
    sub.textContent = this.config.ai_enabled ? "AI assistant · a person can step in anytime" : "We usually reply in a few minutes";
    title.appendChild(sub);
    const close = button("icon-btn", "", () => this.toggle(false));
    close.innerHTML = ICONS.close;
    close.setAttribute("aria-label", "Close chat");
    head.append(title, close);

    const tabs = div("tabs");
    tabs.setAttribute("role", "tablist");
    for (const [id, label] of [["chat", "Chat"], ["help", "Help articles"]] as const) {
      const tab = button("", label, () => this.switchTab(id));
      tab.setAttribute("role", "tab");
      tab.dataset.tab = id;
      tabs.appendChild(tab);
    }

    const body = div("body");
    body.setAttribute("aria-live", "polite");
    const error = div("error");
    const compose = div("compose");
    const input = document.createElement("textarea");
    input.rows = 1;
    input.placeholder = "Write a message…";
    input.setAttribute("aria-label", "Message");
    // Same limit the server enforces; pasting past it is cut off here instead of failing on send.
    const max = this.config.max_message_length || 500;
    input.maxLength = max;
    const counter = div("counter");
    counter.setAttribute("aria-live", "polite");
    const send = button("send", "Send", () => this.send());
    input.addEventListener("input", () => {
      if (!input.value.trim()) this.pendingIntent = undefined;
      counter.textContent = counterText(input.value.length, max);
      counter.classList.toggle("full", input.value.length >= max);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.send();
      }
    });
    compose.append(input, send);
    const powered = div("powered");
    powered.textContent = "Powered by whileisleep";

    panel.append(head, tabs, body, error, counter, compose, powered);
    wrap.append(launcher, panel);
    this.root.append(style, wrap);
    this.el = { launcher, panel, tabs, body, error, counter, compose, input, send };
    this.switchTab("chat");
  }

  private switchTab(tab: Tab) {
    this.tab = tab;
    for (const node of Array.from(this.el.tabs.children) as HTMLElement[]) {
      node.setAttribute("aria-selected", String(node.dataset.tab === tab));
    }
    this.el.compose.hidden = tab !== "chat";
    this.renderBody();
  }

  // --- chat ---

  private async send() {
    const input = this.el.input as HTMLTextAreaElement;
    const body = input.value.trim();
    if (!body) return;
    input.value = "";
    this.el.counter.textContent = "";
    this.el.error.textContent = "";
    (this.el.send as HTMLButtonElement).disabled = true;
    try {
      const data = await this.api.send(body, this.pendingIntent);
      this.pendingIntent = undefined;
      this.humanRequested = data.human_requested;
      this.merge(data.messages);
      if (this.config.ai_enabled && !this.humanRequested && !data.messages.some((m) => m.sender !== "visitor")) {
        this.waitingForReply = Date.now();
      }
      this.renderBody();
      this.poll(true);
    } catch (error) {
      input.value = body;
      this.el.error.textContent = `Couldn't send: ${(error as Error).message}`;
    } finally {
      (this.el.send as HTMLButtonElement).disabled = false;
    }
  }

  private merge(incoming: ChatMessage[]) {
    for (const message of incoming) {
      if (message.id <= this.lastId) continue;
      this.messages.push(message);
      this.lastId = message.id;
      if (message.sender !== "visitor") this.waitingForReply = 0;
    }
  }

  private async poll(reschedule: boolean) {
    try {
      const data = await this.api.messages(this.lastId);
      this.humanRequested = data.human_requested;
      const before = this.lastId;
      this.merge(data.messages);
      if (this.open) this.markSeen();
      if (this.lastId !== before && this.tab === "chat") this.renderBody();
      this.renderBadge();
    } catch {
      /* offline or server restarting: try again next tick */
    }
    if (reschedule) this.schedulePoll();
  }

  private schedulePoll() {
    clearTimeout(this.pollTimer);
    this.pollTimer = setTimeout(() => this.poll(true), this.open ? POLL_OPEN_MS : POLL_CLOSED_MS);
  }

  private markSeen() {
    this.seenId = this.lastId;
    writeSeen(this.api.key, String(this.seenId));
  }

  private renderBadge() {
    this.el.launcher.querySelector(".badge")?.remove();
    const unread = this.messages.filter((m) => m.id > this.seenId && m.sender !== "visitor").length;
    if (!this.open && unread) {
      const badge = div("badge");
      badge.textContent = String(unread);
      this.el.launcher.appendChild(badge);
    }
  }

  private async onAction(event: ActionEvent) {
    this.usedSurfaces.add(event.surfaceId);
    this.el.error.textContent = "";
    try {
      const result = await this.api.action(event);
      if (result.article) {
        this.switchTab("help");
        this.showArticle(result.article);
        return;
      }
      await this.poll(false);
      this.renderBody();
    } catch (error) {
      this.usedSurfaces.delete(event.surfaceId);
      this.el.error.textContent = (error as Error).message;
      this.renderBody();
    }
  }

  private renderBody() {
    if (this.tab === "help") return this.renderHelp();
    const body = this.el.body;
    body.replaceChildren();
    body.appendChild(this.renderMessage({ sender: "bot", body: this.config.greeting, author_name: "", a2ui: null }));
    for (const message of this.messages) body.appendChild(this.renderMessage(message));
    if (this.waitingForReply && Date.now() - this.waitingForReply < TYPING_TIMEOUT_MS) {
      const typing = div("msg");
      const dots = div("bubble typing");
      dots.innerHTML = "<span></span><span></span><span></span>";
      dots.setAttribute("aria-label", "Assistant is typing");
      typing.appendChild(dots);
      body.appendChild(typing);
    }
    body.scrollTop = body.scrollHeight;
  }

  private renderMessage(
    message: Pick<ChatMessage, "sender" | "body" | "author_name" | "a2ui" | "form_submitted">,
  ): HTMLElement {
    const mine = message.sender === "visitor";
    const node = div(`msg${mine ? " me" : ""}`);
    if (!mine) {
      const who = div("who");
      if (message.sender === "bot") {
        const tag = document.createElement("span");
        tag.className = "ai-tag";
        tag.textContent = "AI";
        who.append(tag, document.createTextNode(this.config.name));
      } else {
        who.textContent = message.author_name || this.config.name;
      }
      node.appendChild(who);
    }
    if (message.body) {
      const bubble = div("bubble");
      bubble.append(...formatText(message.body, this.config.website || undefined));
      node.appendChild(bubble);
    }
    if (message.a2ui?.length) {
      for (const surface of applyMessages(message.a2ui).values()) {
        node.appendChild(
          renderSurface(surface, {
            disabled: this.usedSurfaces.has(surface.surfaceId) || !!message.form_submitted,
            onAction: (event) => this.onAction(event),
          }),
        );
      }
    }
    return node;
  }

  // --- help center ---

  private renderHelp(query = "") {
    const body = this.el.body;
    body.replaceChildren();
    const search = document.createElement("input");
    search.className = "search";
    search.placeholder = "Search help articles";
    search.setAttribute("aria-label", "Search help articles");
    search.value = query;
    const list = div("");
    body.append(search, list);
    let timer: ReturnType<typeof setTimeout>;
    const load = async (q: string) => {
      const rows = await this.api.articles(q).catch(() => []);
      list.replaceChildren();
      if (!rows.length) {
        const empty = div("empty");
        empty.textContent = q ? "No articles match." : "No articles yet.";
        list.appendChild(empty);
      }
      for (const row of rows) {
        const item = button("article-row", "", () => this.api.article(row.id).then((a) => this.showArticle(a)));
        const strong = document.createElement("strong");
        strong.textContent = row.title;
        const excerpt = document.createElement("span");
        excerpt.textContent = row.excerpt;
        item.append(strong, excerpt);
        list.appendChild(item);
      }
    };
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => load(search.value), 250);
    });
    load(query);
  }

  private showArticle(article: { title: string; body: string }) {
    const body = this.el.body;
    body.replaceChildren();
    const back = button("back", "← All articles", () => this.renderHelp());
    const wrap = div("article");
    const h = document.createElement("h3");
    h.textContent = article.title;
    wrap.append(h, ...formatText(article.body, this.config.website || undefined));
    body.append(back, wrap);
    body.scrollTop = 0;
  }
}

function div(className: string): HTMLDivElement {
  const node = document.createElement("div");
  node.className = className;
  return node;
}

function button(className: string, label: string, onClick: () => void): HTMLButtonElement {
  const node = document.createElement("button");
  node.type = "button";
  node.className = className;
  node.textContent = label;
  node.addEventListener("click", onClick);
  return node;
}

function readSeen(key: string): string {
  try {
    return localStorage.getItem(`whileisleep:${key}:seen`) ?? "";
  } catch {
    return "";
  }
}

function writeSeen(key: string, value: string) {
  try {
    localStorage.setItem(`whileisleep:${key}:seen`, value);
  } catch {
    /* ignore */
  }
}
