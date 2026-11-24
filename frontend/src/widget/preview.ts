import { WidgetApi, type ChatMessage, type WidgetConfig } from "./api";
import { Widget } from "./widget";

type Look = Pick<WidgetConfig, "name" | "color" | "background" | "color_mode" | "logo_url" | "greeting" | "team">;

const message = (id: number, sender: ChatMessage["sender"], body: string): ChatMessage => ({
  id,
  sender,
  body,
  author_name: "",
  a2ui: null,
  created_at: new Date().toISOString(),
});

const SAMPLE = [
  message(1, "visitor", "Do you ship to Norway?"),
  message(2, "bot", "Yes, in **3 to 5 days**. You'll get a [tracking link](https://example.com) by email."),
];

/** Shows the widget's panel inside `box` with a sample chat, for the dashboard. Returns what
 * removes it. Nothing is sent: there is no server behind it. */
export function previewWidget(box: HTMLElement, look: Look): () => void {
  const host = document.createElement("div");
  host.style.height = "100%";
  box.appendChild(host);
  new Widget(new WidgetApi("", ""), host).showPreview(
    { website: "", max_message_length: 500, ai_enabled: true, uploads_enabled: true, ...look },
    SAMPLE,
  );
  return () => host.remove();
}
