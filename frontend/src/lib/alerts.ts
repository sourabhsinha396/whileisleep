import type { ConversationRow, Message } from "./api";

type Row = Pick<ConversationRow, "id" | "status" | "unread" | "human_requested" | "last_message_at">;

/** An unread open chat that nobody but the team will answer. */
export function waitsForTeam(row: Row, aiEnabled: boolean): boolean {
  return row.status === "open" && row.unread && (row.human_requested || !aiEnabled);
}

/** Decides which changes to a workspace's chats are worth an alert: each piece of activity at most once. */
export class AlertTracker {
  // When each chat last had activity we know of. Server times only: the laptop's clock may be off.
  private seen = new Map<number, number>();
  private start: number | null = null;

  /** The open chats, as loaded. The first load is what was already there; later ones are catching up. */
  load<T extends Row>(rows: T[], aiEnabled: boolean): T[] {
    if (this.start !== null) return rows.filter((row) => this.changed(row, aiEnabled));
    this.start = Math.max(0, ...rows.map((row) => Date.parse(row.last_message_at)));
    for (const row of rows) this.seen.set(row.id, Date.parse(row.last_message_at));
    return [];
  }

  /** A chat changed. True when someone new is waiting for the team. */
  changed(row: Row, aiEnabled: boolean): boolean {
    if (this.start === null) return false;
    const at = Date.parse(row.last_message_at);
    if (at <= (this.seen.get(row.id) ?? this.start)) return false;
    this.seen.set(row.id, at);
    return waitsForTeam(row, aiEnabled);
  }

  /** What the AI or a teammate writes is activity, but not something to alert about. */
  message(conversationId: number, message: Pick<Message, "sender" | "created_at">) {
    if (message.sender !== "bot" && message.sender !== "agent") return;
    this.seen.set(conversationId, Math.max(this.seen.get(conversationId) ?? this.start ?? 0, Date.parse(message.created_at)));
  }
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage blocked: the choice lasts until the page is closed */
  }
}

/** True for the first of this browser's tabs to claim an alert, so only one of them rings. */
export function claimAlert(workspaceId: number, row: Row): boolean {
  const key = `wis_alerted_${workspaceId}`;
  let claimed: Record<string, number> = {};
  try {
    claimed = JSON.parse(read(key) ?? "{}") ?? {};
  } catch {
    /* not ours; start over */
  }
  const at = Date.parse(row.last_message_at);
  if ((claimed[row.id] ?? 0) >= at) return false;
  claimed[row.id] = at;
  const newest = Object.entries(claimed).sort((a, b) => b[1] - a[1]).slice(0, 50);
  write(key, JSON.stringify(Object.fromEntries(newest)));
  return true;
}

export type AlertKind = "sound" | "popup";

/** Sound is on until switched off; popups need the browser's permission too, so they start off. */
export function alertOn(kind: AlertKind): boolean {
  const on = read(`wis_alert_${kind}`) ?? (kind === "sound" ? "1" : "0");
  if (on !== "1") return false;
  return kind === "sound" || ("Notification" in window && Notification.permission === "granted");
}

export function setAlert(kind: AlertKind, on: boolean) {
  write(`wis_alert_${kind}`, on ? "1" : "0");
}

// The chat open in this tab's inbox.
let viewing: number | null = null;

export function setViewing(id: number | null) {
  viewing = id;
}

export function isLookingAt(id: number): boolean {
  return viewing === id && document.visibilityState === "visible" && document.hasFocus();
}
