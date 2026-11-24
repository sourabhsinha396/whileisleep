import { renderSurface } from "@/lib/a2ui/render";
import { applyMessages, type ActionEvent, type Surface } from "@/lib/a2ui/surface";
import { type ChatFile, fitted, isPicture } from "@/lib/chat-file";
import { inkOf, isBright, textOn } from "@/lib/contrast";
import { openLiveStream, throttle, type LiveStream } from "@/lib/live-stream";
import { isPattern, patternSvg } from "@/lib/patterns";
import { isAtEnd, stayAtEnd } from "@/lib/stay-at-end";
import { formatArticle } from "./article";
import { WidgetApi, type ChatMessage, type Identity, type Intent, type StreamEvent, type WidgetConfig } from "./api";
import { styles } from "./styles";
import { Composer, fileCard } from "./composer";
import { button, div } from "./dom";
import { continues, timeOf } from "./groups";
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
/** The greeting is shown like a message, but was never sent. */
type Shown = Omit<ChatMessage, "id" | "created_at"> & { id?: number; created_at?: string };

/** Buttons that answer the bot's question (apps/agent/choices.py on the server). */
function isChoices(surface: Surface): boolean {
  const root = surface.components.get("root");
  return root?.component === "Row" && root.variant === "choices";
}

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
  private composer!: Composer;
  // The newest message already on screen; only later ones slide in.
  private shownId = 0;

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

  /** The panel alone, to look at in the dashboard: nothing is fetched, sent or kept. */
  showPreview(config: WidgetConfig, messages: ChatMessage[]) {
    this.config = config;
    this.messages = messages;
    this.lastId = this.shownId = messages[messages.length - 1]?.id ?? 0;
    this.build();
    this.root.querySelector(".od")!.classList.add("preview");
    this.open = true;
    this.el.panel.hidden = false;
    this.composer.refresh();
    this.renderBody(true);
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
    if (message) this.composer.text = message;
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
    this.composer.clear();
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
    this.composer.clear();
    this.pendingIntent = undefined;
    this.switchTab("chat");
    this.renderBadge();
  }

  private clearLocal() {
    writeStored(this.api.key, "seen", "");
    this.messages = [];
    this.lastId = this.seenId = this.shownId = 0;
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
      this.renderBody(true);
      if (!this.live) this.poll(true);
      this.composer.refresh();
      this.composer.focus();
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
    this.applyMode(wrap);
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
    if (isPattern(this.config.background)) head.innerHTML = patternSvg(this.config.background, "od-pattern");
    const headRow = div("head-row");
    const faces = this.faces();
    const restart = button("icon-btn", "", () => {
      if (confirm("Start a new chat? This conversation will be cleared from this window.")) this.restart();
    });
    restart.innerHTML = ICONS.restart;
    restart.setAttribute("aria-label", "Start a new chat");
    restart.title = "Start a new chat";
    const close = button("icon-btn", "", () => this.toggle(false));
    close.innerHTML = ICONS.close;
    close.setAttribute("aria-label", "Close chat");
    headRow.append(restart, faces, close);

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
    this.composer = new Composer({
      maxLength: this.config.max_message_length || 500,
      uploads: !!this.config.uploads_enabled,
      upload: (file) => this.api.upload(file),
      onSend: () => this.send(),
      onInput: (text) => {
        if (!text.trim()) this.pendingIntent = undefined;
        else this.sendTyping();
      },
      onError: (message) => (this.el.error.textContent = message),
    });
    const compose = this.composer.el;
    const powered = div("powered");
    powered.append("Powered by ");
    const poweredLink = document.createElement("a");
    poweredLink.href = "https://whileisleep.chat";
    poweredLink.target = "_blank";
    poweredLink.rel = "noopener";
    poweredLink.textContent = "whileisleep";
    powered.append(poweredLink);

    const drop = div("drop");
    drop.textContent = "Drop files to send";
    drop.hidden = true;
    panel.append(head, body, error, compose, powered, drop);
    if (this.config.uploads_enabled) this.takeDrops(panel, drop);
    wrap.append(launcher, panel);
    this.root.append(style, wrap);
    this.el = { launcher, panel, tabs, body, error, compose, restart };
    stayAtEnd(body);
    this.switchTab("chat");
  }

  /** Light, dark, or whichever the visitor's device is set to, also when that changes. */
  private applyMode(wrap: HTMLElement) {
    const mode = this.config.color_mode;
    if (mode !== "auto") {
      wrap.classList.toggle("dark", mode === "dark");
      return;
    }
    const device = window.matchMedia("(prefers-color-scheme: dark)");
    const follow = () => wrap.classList.toggle("dark", device.matches);
    device.addEventListener("change", follow);
    follow();
  }

  /** The workspace's logo, with the photos of a few teammates tucked behind it. */
  private faces(): HTMLElement {
    const faces = div("faces");
    faces.setAttribute("aria-hidden", "true");
    const team = div("team");
    team.textContent = initialsOf(this.config.name);
    if (this.config.logo_url) team.appendChild(picture(this.config.logo_url));
    const dot = document.createElement("span");
    dot.className = "dot";
    team.appendChild(dot);
    faces.appendChild(team);
    for (const { name, photo_url } of this.config.team ?? []) {
      const face = div("face");
      face.title = name;
      const photo = picture(photo_url);
      // No initials under this one: without its photo there is nothing to show.
      photo.addEventListener("error", () => face.remove());
      face.appendChild(photo);
      faces.appendChild(face);
    }
    return faces;
  }

  /** Files dragged over the panel are sent from the chat. */
  private takeDrops(panel: HTMLElement, drop: HTMLElement) {
    panel.addEventListener("dragover", (e) => {
      if (!e.dataTransfer?.types.includes("Files")) return;
      e.preventDefault();
      drop.hidden = false;
    });
    panel.addEventListener("dragleave", (e) => {
      if (!panel.contains(e.relatedTarget as Node)) drop.hidden = true;
    });
    panel.addEventListener("drop", (e) => {
      drop.hidden = true;
      const files = Array.from(e.dataTransfer?.files ?? []);
      if (!files.length) return;
      e.preventDefault();
      this.switchTab("chat");
      this.composer.add(files);
    });
  }

  private switchTab(tab: Tab) {
    this.tab = tab;
    for (const node of Array.from(this.el.tabs.children) as HTMLElement[]) {
      node.setAttribute("aria-selected", String(node.dataset.tab === tab));
    }
    this.el.compose.hidden = tab !== "chat";
    if (tab === "chat") this.composer.refresh();
    this.renderBody(true);
  }

  // --- chat ---

  private async send() {
    const { composer } = this;
    const { text, files, restore } = composer.take();
    this.el.error.textContent = "";
    composer.setBusy(true);
    try {
      const data = await this.api.send(text, this.pendingIntent, files.map((file) => file.id));
      this.pendingIntent = undefined;
      this.humanRequested = data.human_requested;
      this.merge(data.messages);
      if (this.config.ai_enabled && !this.humanRequested && !data.messages.some((m) => m.sender !== "visitor")) {
        this.waitingForReply = Date.now();
      }
      this.renderBody(true);
      if (!this.live) this.poll(true);
    } catch (error) {
      restore();
      this.el.error.textContent = `Couldn't send: ${(error as Error).message}`;
    } finally {
      composer.setBusy(false);
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
    const choosing = event.name === "choose";
    if (choosing && this.usedSurfaces.has(event.surfaceId)) return; // a second, quick press
    this.usedSurfaces.add(event.surfaceId);
    this.el.error.textContent = "";
    if (choosing) {
      // Its words go out as a message: a reply is coming, as after sending one.
      if (this.config.ai_enabled && !this.humanRequested) this.waitingForReply = Date.now();
      this.renderBody(true);
    }
    try {
      const result = await this.api.action(event);
      if (result.article) {
        this.switchTab("help");
        this.showArticle(result.article);
        return;
      }
      await this.poll(false);
      this.renderBody(choosing);
    } catch (error) {
      this.usedSurfaces.delete(event.surfaceId);
      if (choosing) this.waitingForReply = 0;
      this.el.error.textContent = (error as Error).message;
      this.renderBody();
    }
  }

  /** `down` goes to the newest message. Otherwise someone reading further up stays there. */
  private renderBody(down = false) {
    this.el.restart.hidden = this.messages.length === 0;
    if (this.tab === "help") return this.renderHelp();
    const body = this.el.body;
    const at = body.scrollTop;
    const atEnd = isAtEnd(body);
    body.replaceChildren();
    body.appendChild(this.renderMessage({ sender: "bot", body: this.config.greeting, author_name: "", a2ui: null }));
    this.messages.forEach((message, i) => {
      const row = this.renderMessage(message, this.messages[i - 1], this.messages[i + 1]);
      if (message.id > this.shownId) row.classList.add("new");
      body.appendChild(row);
    });
    this.shownId = this.lastId;
    const activity = this.activity();
    if (activity) body.appendChild(activity);
    body.scrollTop = down || atEnd ? body.scrollHeight : at;
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

  private renderMessage(message: Shown, previous?: ChatMessage, next?: ChatMessage): HTMLElement {
    if (message.sender === "system") {
      const node = div("system");
      const pill = document.createElement("span");
      pill.textContent = message.body;
      node.appendChild(pill);
      return node;
    }
    const mine = message.sender === "visitor";
    const first = !continues(previous, message);
    const last = !next || !continues(message, next);
    const row = div(`msg${mine ? " me" : ""}${first ? " first" : ""}${last ? " last" : ""}`);
    const node = div("msg-main");
    // One avatar for what one person said in a row.
    if (!mine) row.appendChild(last ? this.avatar(message.sender, message.author_name, message.author_photo) : div("av none"));
    row.appendChild(node);
    if (first) {
      const who = div("who");
      if (mine) {
        who.textContent = "You";
      } else {
        who.textContent = message.author_name || this.config.name;
      }
      if (message.created_at) {
        const time = document.createElement("time");
        time.dateTime = message.created_at;
        time.textContent = timeOf(message.created_at);
        who.append(time);
      }
      node.appendChild(who);
    }
    if (message.body) {
      const bubble = div("bubble");
      bubble.append(...formatText(message.body, this.config.website || undefined, mine));
      node.appendChild(bubble);
    }
    for (const file of message.attachments ?? []) node.appendChild(isPicture(file) ? this.photo(file) : fileCard(file));
    if (message.a2ui?.length) {
      for (const surface of applyMessages(message.a2ui).values()) {
        const used = this.usedSurfaces.has(surface.surfaceId);
        // Choices go away once the question is answered.
        if (isChoices(surface) && (used || this.answered(message))) continue;
        node.appendChild(
          renderSurface(surface, {
            disabled: used || !!message.form_submitted,
            onAction: (event) => this.onAction(event),
          }),
        );
      }
    }
    return row;
  }

  /** Whether the visitor or a teammate has written since. The server refuses a choice then too. */
  private answered(message: Shown): boolean {
    return this.messages.some((m) => m.id > (message.id ?? 0) && (m.sender === "visitor" || m.sender === "agent"));
  }

  /** A picture someone sent; opens full size. A site's own rules may block images from
   * elsewhere, and then it shows as a file. */
  private photo(file: ChatFile): HTMLElement {
    const a = document.createElement("a");
    a.className = "photo";
    a.href = file.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    const img = document.createElement("img");
    img.alt = file.name;
    img.referrerPolicy = "no-referrer";
    Object.assign(img, fitted(file.width!, file.height!, 220, 220));
    img.addEventListener("error", () => a.replaceWith(fileCard(file)));
    img.src = file.url;
    a.appendChild(img);
    return a;
  }

  /** A bot icon for the AI agent, a photo or initials for a teammate. */
  private avatar(sender: ChatMessage["sender"], author = "", photo = ""): HTMLElement {
    const av = div("av");
    if (sender === "bot") {
      // The icon alone says this is the AI, so it has a name for screen readers.
      av.innerHTML = ICONS.bot;
      av.setAttribute("role", "img");
      av.setAttribute("aria-label", "AI assistant");
    } else {
      av.setAttribute("aria-hidden", "true");
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
