// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AlertTracker, alertOn, claimAlert, isLookingAt, setAlert, setViewing } from "@/lib/alerts";

const row = (id: number, minute: number, more = {}) => ({
  id,
  status: "open" as const,
  unread: true,
  human_requested: true,
  last_message_at: `2026-11-25T10:0${minute}:00Z`,
  ...more,
});

beforeEach(() => localStorage.clear());

describe("AlertTracker", () => {
  function started() {
    const tracker = new AlertTracker();
    expect(tracker.load([row(1, 1)], true)).toEqual([]);
    return tracker;
  }

  it("stays quiet about what was already there", () => {
    expect(started().changed(row(1, 1), true)).toBe(false);
  });

  it("alerts once for new activity", () => {
    const tracker = started();
    expect(tracker.changed(row(1, 2), true)).toBe(true);
    expect(tracker.changed(row(1, 2), true)).toBe(false);
    expect(tracker.changed(row(1, 3), true)).toBe(true);
  });

  it("alerts for a new chat", () => {
    expect(started().changed(row(2, 2), true)).toBe(true);
  });

  it("leaves chats to the AI while it answers them", () => {
    expect(started().changed(row(1, 2, { human_requested: false }), true)).toBe(false);
    expect(started().changed(row(1, 2, { human_requested: false }), false)).toBe(true);
  });

  it("ignores read and resolved chats", () => {
    expect(started().changed(row(1, 2, { unread: false }), true)).toBe(false);
    expect(started().changed(row(1, 2, { status: "resolved" }), true)).toBe(false);
  });

  it("does not alert for a reply from the AI or the team", () => {
    const tracker = started();
    tracker.message(1, { sender: "bot", created_at: row(1, 2).last_message_at });
    expect(tracker.changed(row(1, 2), true)).toBe(false);
  });

  it("alerts for the visitor's message and the hand-off note", () => {
    const tracker = started();
    tracker.message(1, { sender: "system", created_at: row(1, 2).last_message_at });
    expect(tracker.changed(row(1, 2), true)).toBe(true);
  });

  it("catches up after a lost connection", () => {
    expect(started().load([row(1, 1), row(2, 2)], true).map((r) => r.id)).toEqual([2]);
  });

  it("waits for the first load", () => {
    expect(new AlertTracker().changed(row(1, 1), true)).toBe(false);
  });
});

it("lets one tab ring per alert", () => {
  expect(claimAlert(7, row(1, 1))).toBe(true);
  expect(claimAlert(7, row(1, 1))).toBe(false);
  expect(claimAlert(8, row(1, 1))).toBe(true);
  expect(claimAlert(7, row(1, 2))).toBe(true);
  localStorage.setItem("wis_alerted_7", "{broken");
  expect(claimAlert(7, row(1, 1))).toBe(true);
});

it("starts with sound on and popups off, and popups need permission", () => {
  expect([alertOn("sound"), alertOn("popup")]).toEqual([true, false]);
  setAlert("sound", false);
  setAlert("popup", true);
  expect(alertOn("sound")).toBe(false);
  vi.stubGlobal("Notification", { permission: "denied" });
  expect(alertOn("popup")).toBe(false);
  vi.stubGlobal("Notification", { permission: "granted" });
  expect(alertOn("popup")).toBe(true);
  vi.unstubAllGlobals();
});

it("knows the chat being looked at only while the tab has focus", () => {
  const focus = vi.spyOn(document, "hasFocus").mockReturnValue(true);
  setViewing(3);
  expect([isLookingAt(3), isLookingAt(4)]).toEqual([true, false]);
  focus.mockReturnValue(false);
  expect(isLookingAt(3)).toBe(false);
});
