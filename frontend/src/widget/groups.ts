import type { ChatMessage } from "./api";

/** Messages this close together by one person read as one. */
const GAP_MS = 5 * 60 * 1000;

type Grouped = Pick<ChatMessage, "sender" | "author_name"> & { created_at?: string };

/** Whether `next` continues `previous`, so their name needn't be said again. */
export function continues(previous: Grouped | undefined, next: Grouped): boolean {
  if (!previous || previous.sender !== next.sender || previous.author_name !== next.author_name || next.sender === "system") return false;
  // The greeting was never sent, so it has no time.
  if (!previous.created_at || !next.created_at) return false;
  return Date.parse(next.created_at) - Date.parse(previous.created_at) < GAP_MS;
}

/** "10:32", with the day when it isn't today. */
export function timeOf(created: string, now = new Date()): string {
  const date = new Date(created);
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (date.toDateString() === now.toDateString()) return time;
  return `${date.toLocaleDateString([], { day: "numeric", month: "short" })}, ${time}`;
}
