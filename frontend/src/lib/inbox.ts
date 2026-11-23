import type { ConversationDetail, ConversationRow, Message } from "./api";

export type Filter = "open" | "resolved" | "all";

/** The inbox list after a live `conversation` event: the row replaced or added, or dropped
 * when it no longer matches the filter, newest activity first. */
export function applyConversation(rows: ConversationRow[] | null, row: ConversationRow, filter: Filter): ConversationRow[] | null {
  if (rows === null) return rows;
  const others = rows.filter((r) => r.id !== row.id);
  const matches = filter === "all" || row.status === filter;
  const next = matches ? [...others, row] : others;
  return next.sort((a, b) => b.last_message_at.localeCompare(a.last_message_at));
}

/** A conversation with a live message added, unless it already has it. */
export function addMessage(detail: ConversationDetail | null, message: Message): ConversationDetail | null {
  if (!detail || detail.messages.some((m) => m.id === message.id)) return detail;
  return { ...detail, messages: [...detail.messages, message].sort((a, b) => a.id - b.id) };
}

type WithVisitor = { visitor: { id: number; online: boolean; last_seen: string } };

/** The visitor after a presence event. Leaving means they were last seen just now. */
export function withPresence<V extends WithVisitor["visitor"]>(visitor: V, online: boolean, now = new Date()): V {
  return { ...visitor, online, ...(online ? {} : { last_seen: now.toISOString() }) };
}

/** Rows with one visitor's presence changed. */
export function setOnline<T extends WithVisitor>(rows: T[] | null, visitorId: number, online: boolean) {
  if (!rows?.some((r) => r.visitor.id === visitorId)) return rows;
  return rows.map((r) => (r.visitor.id === visitorId ? { ...r, visitor: withPresence(r.visitor, online) } : r));
}
