import { renderSurface } from "@/lib/a2ui/render";
import { applyMessages, type ActionEvent } from "@/lib/a2ui/surface";
import { inkOf, isBright, textOn } from "@/lib/contrast";
import { openLiveStream, throttle, type LiveStream } from "@/lib/live-stream";
import { formatArticle } from "./article";
import { WidgetApi, type ChatMessage, type Identity, type Intent, type StreamEvent, type WidgetConfig } from "./api";
import { styles } from "./styles";
import { counterText } from "./limits";
import { formatText } from "./text";
import { chimeFor, playChime, unlockAudio } from "./sound";

const ICONS = {
  // Solid bubble, tilted a little so the launcher reads as friendly rather than a generic icon.
  chat: '<svg viewBox="0 0 24 24"><g transform="rotate(-12 12 12)"><path fill="currentColor" d="M5 3.5h14a3.5 3.5 0 0 1 3.5 3.5v8A3.5 3.5 0 0 1 19 18.5h-7.6l-4.9 3.7A.9.9 0 0 1 5 21.5v-3h0A3.5 3.5 0 0 1 1.5 15V7A3.5 3.5 0 0 1 5 3.5z"/><g fill="var(--od-color)"><circle cx="7.5" cy="11" r="1.35"/><circle cx="12" cy="11" r="1.35"/><circle cx="16.5" cy="11" r="1.35"/></g></g></svg>',
  restart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>',
  chevronDown: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
  send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>',
  bot: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2M20 14h2M15 13v2M9 13v2"/></svg>',
  book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  chevronRight: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>',
  back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" width="15" height="15"><path d="m15 6-6 6 6 6"/></svg>',
};

/** "Acme Store" -> "AS". */
function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "?") + (parts[1]?.[0] ?? "")).toUpperCase();
}

// Polling is the fallback for when the live stream is down.
const POLL_OPEN_MS = 2500;
const POLL_CLOSED_MS = 15000;
const TYPING_TIMEOUT_MS = 45000;
// The visitor's typing goes to the team at most this often; a teammate's shows this long.
const TYPING_SEND_MS = 3000;
const AGENT_TYPING_MS = 6000;

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
  // The live stream; while it is connected the widget doesn't poll.
  private stream?: LiveStream;
  private live = false;
  // What the AI is doing ("Searching the help center"), and a teammate typing.
  private botStatus = "";
  private agentTyping: { name: string; photo?: string; until: number } | null = null;
  private agentTypingTimer?: ReturnType<typeof setTimeout>;
  private sendTyping = throttle(() => this.api.typing().catch(() => {}), TYPING_SEND_MS);
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
    this.seenId = Number(readStored(this.api.key, "seen")) || 0;
    this.build();
    this.markReady();
    if (session.conversation_id) await this.poll(false, true);
    // Replies already in the chat when the page loads aren't news; only later ones ring.
    this.recordChimed(this.lastId);
    for (const type of ["pointerdown", "keydown"]) document.addEventListener(type, unlockAudio, { capture: true, passive: true });
    // Polls until the stream connects; the open stream also keeps the visitor online.
    this.schedulePoll();
    this.connect();
  }

  /** (Re)opens the live stream, e.g. after identify() switched to another visitor. */
  private connect() {
    this.stream?.close();
    this.live = false;
    this.stream = openLiveStream({
      url: this.api.streamUrl,
      headers: () => this.api.streamHeaders(),
      // Anything newer than what we show is sent first, so nothing is lost across a reconnect.
      lastEventId: () => this.lastId,
      onEvent: (event) => this.onStreamEvent(event as StreamEvent),
      onLive: (live) => {
        this.live = live;
        if (live) clearTimeout(this.pollTimer);
        else this.schedulePoll();
      },
    });
  }

  private onStreamEvent({ event, data }: StreamEvent) {
    if (event === "message") {
      const before = this.lastId;
      this.merge([data.message]);
      if (this.lastId === before) return;
      this.chime([data.message]);
      if (this.open) this.markSeen();
      this.renderBadge();
    } else if (event === "conversation") {
      this.humanRequested = data.human_requested;
      return;
    } else if (event === "status") {
      this.botStatus = data.text;
      // A reply is on its way, even if this page didn't send the question.
      if (data.text && !this.waitingForReply) this.waitingForReply = Date.now();
    } else if (event === "typing" && data.sender === "agent") {
      this.agentTyping = { name: data.name, photo: data.photo, until: Date.now() + AGENT_TYPING_MS };
      clearTimeout(this.agentTypingTimer);
      this.agentTypingTimer = setTimeout(() => this.tab === "chat" && this.renderBody(), AGENT_TYPING_MS + 50);
    } else {
      return;
    }
    if (this.tab === "chat") this.renderBody();
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

  async identify(details: Identity) {
    await this.ready;
    const before = this.api.token;
    const session = await this.api.session(details);
    if (this.api.token !== before) {
      // Now a different visitor (the signed-in user's own record): show their chat.
      this.clearLocal();
      if (session.conversation_id) await this.poll(false, true);
      this.recordChimed(this.lastId);
      this.renderBody();
      this.renderBadge();
      this.connect();
    }
  }

  /** Forgets this visitor (call on sign-out) so the next person here starts a new chat. */
  async reset() {
    await this.ready;
    this.api.forget();
    this.clearLocal();
    await this.api.session();
    this.renderBody();
    this.renderBadge();
    this.connect();
  }

  /** Clears the chat and starts a new conversation as the same visitor.
   * The old conversation stays in the team's inbox. */
  async restart() {
    await this.ready;
    this.el.error.textContent = "";
    try {
      await this.api.restart();
    } catch (error) {
      this.el.error.textContent = `Couldn't start a new chat: ${(error as Error).message}`;
      return;
    }
    this.clearLocal();
    (this.el.input as HTMLTextAreaElement).value = "";
    this.el.counter.textContent = "";
    this.pendingIntent = undefined;
    this.switchTab("chat");
    this.renderBadge();
  }

  private clearLocal() {
    writeStored(this.api.key, "seen", "");
    this.messages = [];
    this.lastId = this.seenId = 0;
    this.humanRequested = false;
    this.waitingForReply = 0;
    this.botStatus = "";
    this.agentTyping = null;
    this.usedSurfaces.clear();
  }

  toggle(force?: boolean) {
    this.open = force ?? !this.open;
    this.el.panel.hidden = !this.open;
    this.el.launcher.innerHTML = this.open ? ICONS.chevronDown : ICONS.chat;
    this.el.launcher.setAttribute("aria-label", this.open ? "Close chat" : "Open chat");
    if (this.open) {
      this.markSeen();
      this.renderBody();
      if (!this.live) this.poll(true);
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
    const color = /^#[0-9a-f]{3,8}$/i.test(this.config.color) ? this.config.color : "#2563eb";
    wrap.classList.toggle("bright", isBright(color));
    wrap.style.setProperty("--od-color", color);
    wrap.style.setProperty("--od-on", textOn(color));
    wrap.style.setProperty("--od-ink", inkOf(color));

    const launcher = button("launcher", "", () => this.toggle());
    launcher.innerHTML = ICONS.chat;
    launcher.setAttribute("aria-label", "Open chat");

    const panel = div("panel");
    panel.hidden = true;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", `Chat with ${this.config.name}`);

    const head = div("head");
    const headRow = div("head-row");
    const team = div("team");
    team.textContent = initialsOf(this.config.name);
    team.setAttribute("aria-hidden", "true");
    if (this.config.logo_url) team.appendChild(picture(this.config.logo_url));
    const dot = document.createElement("span");
    dot.className = "dot";
    team.appendChild(dot);
    const title = document.createElement("h2");
    title.textContent = this.config.name;
    const sub = document.createElement("span");
    sub.className = "sub";
    sub.textContent = this.config.ai_enabled ? "AI assistant · a person can step in anytime" : "We usually reply in a few minutes";
    title.appendChild(sub);
    const restart = button("icon-btn", "", () => {
      if (confirm("Start a new chat? This conversation will be cleared from this window.")) this.restart();
    });
    restart.innerHTML = ICONS.restart;
    restart.setAttribute("aria-label", "Start a new chat");
    restart.title = "Start a new chat";
    const close = button("icon-btn", "", () => this.toggle(false));
    close.innerHTML = ICONS.close;
    close.setAttribute("aria-label", "Close chat");
    headRow.append(team, title, restart, close);

    const tabs = div("tabs");
    tabs.setAttribute("role", "tablist");
    for (const [id, label, icon] of [["chat", "Chat", ICONS.chat], ["help", "Help", ICONS.book]] as const) {
      const tab = button("", "", () => this.switchTab(id));
      tab.innerHTML = icon;
      tab.append(label);
      tab.setAttribute("role", "tab");
      tab.dataset.tab = id;
      tabs.appendChild(tab);
    }
    head.append(headRow, tabs);

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
    const send = button("send", "", () => this.send());
    send.innerHTML = ICONS.send;
    send.setAttribute("aria-label", "Send");
    input.addEventListener("input", () => {
      if (!input.value.trim()) this.pendingIntent = undefined;
      else this.sendTyping();
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
    powered.append("Powered by ");
    const poweredLink = document.createElement("a");
    poweredLink.href = "https://whileisleep.chat";
    poweredLink.target = "_blank";
    poweredLink.rel = "noopener";
    poweredLink.textContent = "whileisleep";
    powered.append(poweredLink);

    panel.append(head, body, error, counter, compose, powered);
    wrap.append(launcher, panel);
    this.root.append(style, wrap);
    this.el = { launcher, panel, tabs, body, error, counter, compose, input, send, restart };
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
      if (!this.live) this.poll(true);
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
      if (message.sender !== "visitor") {
        // The reply is here: no more dots, status or "is typing".
        this.waitingForReply = 0;
        this.botStatus = "";
        this.agentTyping = null;
      }
    }
  }

  private async poll(reschedule: boolean, quiet = false) {
    try {
      const data = await this.api.messages(this.lastId);
      this.humanRequested = data.human_requested;
      const before = this.lastId;
      this.merge(data.messages);
      if (!quiet) this.chime(data.messages);
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
    if (this.live) return;
    this.pollTimer = setTimeout(() => this.poll(true), this.open ? POLL_OPEN_MS : POLL_CLOSED_MS);
  }

  private markSeen() {
    this.seenId = this.lastId;
    writeStored(this.api.key, "seen", String(this.seenId));
  }

  /** A soft tone when a reply lands while the visitor is on another tab. */
  private chime(incoming: ChatMessage[]) {
    const id = chimeFor(incoming, document.hidden, Number(readStored(this.api.key, "chimed")) || 0);
    if (!id) return;
    this.recordChimed(id);
    playChime();
  }

  private recordChimed(id: number) {
    if (id > (Number(readStored(this.api.key, "chimed")) || 0)) writeStored(this.api.key, "chimed", String(id));
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
    this.el.restart.hidden = this.messages.length === 0;
    if (this.tab === "help") return this.renderHelp();
    const body = this.el.body;
    body.replaceChildren();
    body.appendChild(this.renderMessage({ sender: "bot", body: this.config.greeting, author_name: "", a2ui: null }));
    for (const message of this.messages) body.appendChild(this.renderMessage(message));
    const activity = this.activity();
    if (activity) body.appendChild(activity);
    body.scrollTop = body.scrollHeight;
  }

  /** Dots while a reply is coming: the AI's current step, or a teammate typing. */
  private activity(): HTMLElement | null {
    const teammate = this.agentTyping && this.agentTyping.until > Date.now() ? this.agentTyping : null;
    const waiting = this.waitingForReply && Date.now() - this.waitingForReply < TYPING_TIMEOUT_MS;
    if (!teammate && !this.botStatus && !waiting) return null;
    const label = teammate && !this.botStatus ? `${teammate.name || this.config.name} is typing` : this.botStatus;
    const row = div("msg");
    const main = div("msg-main");
    const dots = div("bubble typing");
    dots.innerHTML = "<span></span><span></span><span></span>";
    dots.setAttribute("aria-label", label || "Assistant is typing");
    main.appendChild(dots);
    if (label) {
      const line = div("activity");
      line.textContent = label;
      main.appendChild(line);
    }
    row.append(teammate && !this.botStatus ? this.avatar("agent", teammate.name, teammate.photo) : this.avatar("bot"), main);
    return row;
  }

  private renderMessage(
    message: Pick<ChatMessage, "sender" | "body" | "author_name" | "author_photo" | "a2ui" | "form_submitted">,
  ): HTMLElement {
    if (message.sender === "system") {
      const node = div("system");
      const pill = document.createElement("span");
      pill.textContent = message.body;
      node.appendChild(pill);
      return node;
    }
    const mine = message.sender === "visitor";
    const row = div(`msg${mine ? " me" : ""}`);
    const node = div("msg-main");
    if (!mine) row.appendChild(this.avatar(message.sender, message.author_name, message.author_photo));
    row.appendChild(node);
    {
      const who = div("who");
      if (mine) {
        who.textContent = "You";
      } else if (message.sender === "bot") {
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
    return row;
  }

  /** A bot icon for the AI agent, a photo or initials for a teammate. */
  private avatar(sender: ChatMessage["sender"], author = "", photo = ""): HTMLElement {
    const av = div("av");
    av.setAttribute("aria-hidden", "true");
    if (sender === "bot") av.innerHTML = ICONS.bot;
    else {
      av.textContent = initialsOf(author || this.config.name);
      if (photo) av.appendChild(picture(photo));
    }
    return av;
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
    const searchWrap = div("search-wrap");
    searchWrap.innerHTML = ICONS.search;
    searchWrap.appendChild(search);
    const list = div("articles");
    const empty = div("empty");
    body.append(searchWrap, list, empty);
    let timer: ReturnType<typeof setTimeout>;
    const load = async (q: string) => {
      const rows = await this.api.articles(q).catch(() => []);
      list.replaceChildren();
      empty.textContent = rows.length ? "" : q ? "No articles match." : "No articles yet.";
      for (const row of rows) {
        const item = button("article-row", "", () => this.api.article(row.id).then((a) => this.showArticle(a)));
        const txt = div("txt");
        const strong = document.createElement("strong");
        strong.textContent = row.title;
        const excerpt = document.createElement("span");
        excerpt.textContent = row.excerpt;
        txt.append(strong, excerpt);
        item.appendChild(txt);
        item.insertAdjacentHTML("beforeend", ICONS.chevronRight);
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
    const back = button("back", "", () => this.renderHelp());
    back.innerHTML = ICONS.back;
    back.append("All articles");
    const wrap = div("article");
    const h = document.createElement("h3");
    h.textContent = article.title;
    wrap.append(h, ...formatArticle(article.body, this.config.website || undefined));
    body.append(back, wrap);
    body.scrollTop = 0;
  }
}

/** Covers the initials under it, which show again if it can't load (a site's own rules may
 * block images from elsewhere). */
function picture(src: string): HTMLImageElement {
  const img = document.createElement("img");
  img.className = "pic";
  img.alt = "";
  img.addEventListener("error", () => img.remove());
  img.src = src;
  return img;
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

function readStored(key: string, name: string): string {
  try {
    return localStorage.getItem(`whileisleep:${key}:${name}`) ?? "";
  } catch {
    return "";
  }
}

function writeStored(key: string, name: string, value: string) {
  try {
    localStorage.setItem(`whileisleep:${key}:${name}`, value);
  } catch {
    /* ignore */
  }
}
