// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { WidgetApi } from "@/widget/api";
import { Widget } from "@/widget/widget";

const BASE = "https://chat.example.com/api/v1/widget/ws_1";
const PHOTO = "https://cdn.example.com/users/1/photo/a.png";
const LOGO = "https://cdn.example.com/workspaces/1/logo/a.png";

/** The widget with one teammate's reply, and a logo if given. */
async function start({ logo = "", photo = "" } = {}) {
  const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const path = url.replace(BASE, "").split("?")[0];
      if (path === "/config") return json({ name: "Acme Store", website: "", color: "#2563eb", logo_url: logo, greeting: "Hi!", ai_enabled: true, max_message_length: 500 });
      if (path === "/session") return json({ token: "vt_1", visitor_id: 1, conversation_id: 5, last_message_id: 10 });
      if (path === "/messages") {
        const message = { id: 10, sender: "agent", body: "Hello", author_name: "Priya Rao", author_photo: photo, a2ui: null, created_at: "2026-11-23T10:00:00Z" };
        return json({ conversation_id: 5, human_requested: true, messages: [message] });
      }
      return new Response("{}", { status: 404 });
    }),
  );
  const host = document.createElement("div");
  document.body.appendChild(host);
  const widget = new Widget(new WidgetApi("https://chat.example.com", "ws_1"), host);
  await widget.start();
  widget.toggle(true);
  const root = host.shadowRoot!;
  const avatars = Array.from(root.querySelectorAll<HTMLElement>(".av"));
  return { team: root.querySelector<HTMLElement>(".team")!, bot: avatars[0], teammate: avatars[avatars.length - 1] };
}

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
});

describe("the widget's pictures", () => {
  it("shows the workspace's logo in the header", async () => {
    const { team } = await start({ logo: LOGO });
    expect(team.querySelector("img")!.getAttribute("src")).toBe(LOGO);
    expect(team.querySelector(".dot")).not.toBeNull();
  });

  it("shows a teammate's photo next to their reply, and never on the AI's", async () => {
    const { teammate, bot } = await start({ photo: PHOTO });
    expect(teammate.querySelector("img")!.getAttribute("src")).toBe(PHOTO);
    expect(bot.querySelector("img")).toBeNull();
  });

  it("shows initials without them", async () => {
    const { team, teammate } = await start();
    expect(team.querySelector("img")).toBeNull();
    expect(team.textContent).toBe("AS");
    expect(teammate.querySelector("img")).toBeNull();
    expect(teammate.textContent).toBe("PR");
  });

  it("goes back to initials when a picture can't load", async () => {
    const { team, teammate } = await start({ logo: LOGO, photo: PHOTO });
    for (const node of [team, teammate]) node.querySelector("img")!.dispatchEvent(new Event("error"));
    expect(team.querySelector("img")).toBeNull();
    expect(team.textContent).toBe("AS");
    expect(teammate.textContent).toBe("PR");
  });
});
