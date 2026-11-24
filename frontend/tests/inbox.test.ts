import { describe, expect, it } from "vitest";
import type { ConversationDetail, ConversationRow, Message } from "@/lib/api";
import { addMessage, applyConversation, setOnline, withPresence } from "@/lib/inbox";

function row(id: number, last: string, status: "open" | "resolved" = "open", visitorId = id): ConversationRow {
  return {
    id,
    status,
    unread: false,
    human_requested: false,
    tags: [],
    attributes: [],
    assignee_id: null,
    last_message_at: last,
    preview: "",
    visitor: {
      id: visitorId,
      name: `Visitor ${visitorId}`,
      email: "",
      verified: false,
      attributes: [],
      online: false,
      current_url: "",
      page_title: "",
      referrer: "",
      user_agent: "",
      first_seen: last,
      last_seen: last,
      conversation_id: id,
    },
  };
}

function message(id: number): Message {
  return { id, sender: "visitor", author_name: "", author_photo: "", body: `m${id}`, a2ui: null, is_note: false, intent: "", created_at: "" };
}

describe("applyConversation", () => {
  const rows = [row(1, "2026-11-23T10:05:00Z"), row(2, "2026-11-23T10:00:00Z")];

  it("moves a conversation with new activity to the top", () => {
    const next = applyConversation(rows, { ...row(2, "2026-11-23T10:09:00Z"), preview: "new" }, "open")!;
    expect(next.map((r) => r.id)).toEqual([2, 1]);
    expect(next[0].preview).toBe("new");
  });

  it("adds a conversation it hadn't listed", () => {
    expect(applyConversation(rows, row(3, "2026-11-23T10:01:00Z"), "open")!.map((r) => r.id)).toEqual([1, 3, 2]);
  });

  it("drops a conversation that leaves the filter", () => {
    expect(applyConversation(rows, row(1, "2026-11-23T10:05:00Z", "resolved"), "open")!.map((r) => r.id)).toEqual([2]);
    expect(applyConversation(rows, row(1, "2026-11-23T10:05:00Z", "resolved"), "all")!.map((r) => r.id)).toEqual([1, 2]);
  });

  it("waits for the first load", () => {
    expect(applyConversation(null, row(1, "2026-11-23T10:05:00Z"), "open")).toBeNull();
  });
});

describe("addMessage", () => {
  const detail = { ...row(1, "2026-11-23T10:00:00Z"), messages: [message(1), message(2)] } as ConversationDetail;

  it("appends a new message", () => {
    expect(addMessage(detail, message(3))!.messages.map((m) => m.id)).toEqual([1, 2, 3]);
  });

  it("keeps the same object when the message is already there", () => {
    expect(addMessage(detail, message(2))).toBe(detail);
  });
});

describe("setOnline", () => {
  it("changes only that visitor", () => {
    const rows = [row(1, "x", "open", 7), row(2, "x", "open", 8)];
    const next = setOnline(rows, 7, true)!;
    expect(next.map((r) => r.visitor.online)).toEqual([true, false]);
    expect(next[0].visitor.last_seen).toBe("x");
    expect(setOnline(rows, 99, true)).toBe(rows);
  });
});

describe("withPresence", () => {
  it("marks a visitor who left as last seen now", () => {
    const visitor = { ...row(1, "2026-11-23T09:00:00.000Z").visitor, online: true };
    const left = withPresence(visitor, false, new Date("2026-11-23T10:30:00.000Z"));
    expect(left).toMatchObject({ online: false, last_seen: "2026-11-23T10:30:00.000Z" });
  });
});
