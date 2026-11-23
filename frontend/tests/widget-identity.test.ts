// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WidgetApi } from "@/widget/api";

/** Answers every request with a session for `token`, and records what was sent. */
function fakeServer(token = "vt_first") {
  const sent: { url: string; body: Record<string, unknown>; headers: Record<string, string> }[] = [];
  const state = { token };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      sent.push({ url, body: JSON.parse(String(init.body ?? "{}")), headers: init.headers as Record<string, string> });
      return new Response(JSON.stringify({ token: state.token, conversation_id: null, last_message_id: null }), { status: 200 });
    }),
  );
  return { sent, state };
}

describe("identify through the session request", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("sends what the page says as plain details", async () => {
    const { sent } = fakeServer();
    await new WidgetApi("https://chat.example.com", "ws_1").session({ name: "Sofia", email: "s@example.com", attributes: { plan: "pro" } });
    expect(sent[0].url).toBe("https://chat.example.com/api/v1/widget/ws_1/session");
    expect(sent[0].body).toMatchObject({ name: "Sofia", email: "s@example.com", attributes: { plan: "pro" } });
    expect(sent[0].body).not.toHaveProperty("identity_token");
  });

  it("sends a signed token under the name the API expects", async () => {
    const { sent } = fakeServer();
    await new WidgetApi("https://chat.example.com", "ws_1").session({ token: "header.payload.signature" });
    expect(sent[0].body.identity_token).toBe("header.payload.signature");
    // Not also as `token`, which would be an unknown field.
    expect(sent[0].body).not.toHaveProperty("token");
  });

  it("continues as the visitor the server answers with", async () => {
    const { sent, state } = fakeServer("vt_anonymous");
    const api = new WidgetApi("https://chat.example.com", "ws_1");
    await api.session();
    expect(api.token).toBe("vt_anonymous");

    // Signing in: this user already has a visitor record from another device.
    state.token = "vt_known_user";
    await api.session({ token: "header.payload.signature" });

    expect(sent[1].headers["X-Visitor-Token"]).toBe("vt_anonymous");
    expect(api.token).toBe("vt_known_user");
    expect(localStorage.getItem("whileisleep:ws_1")).toBe("vt_known_user");
  });

  it("a plain heartbeat carries no identity", async () => {
    const { sent } = fakeServer();
    await new WidgetApi("https://chat.example.com", "ws_1").session();
    expect(Object.keys(sent[0].body).sort()).toEqual(["referrer", "title", "url"]);
  });
});
