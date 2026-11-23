/**
 * whileisleep chat widget. Add to any site:
 *
 *   <script src="https://YOUR-WHILEISLEEP-HOST/widget.js" data-workspace="ws_..." async></script>
 *
 * Optional: data-api="https://api.example.com" when the API isn't on the script's origin.
 *
 * window.whileisleep, once the script has run (it fires a "whileisleep:ready" event on window):
 *   open(message?, intent?)   open the chat, optionally with a message typed in, ready to send;
 *                       intent ({ intent: "exam_request", data: {...} }) labels it for rules
 *   close()
 *   hide() / show()     remove the bubble from pages where it would be in the way
 *   identify({ name, email, attributes })   say who the signed-in user is (shown to the team)
 *   identify({ token })   prove it: a JWT your server signed with the workspace's identity
 *                       secret; its claims become verified attributes, which tools can rely on
 *   restart()           clear the chat and start a new conversation (same visitor)
 *   reset()             forget this visitor, e.g. on sign-out
 */

import { WidgetApi, type Identity, type Intent } from "./api";
import { Widget } from "./widget";

export interface WhileisleepApi {
  open(message?: string, intent?: Intent): Promise<void>;
  close(): Promise<void>;
  hide(): void;
  show(): void;
  identify(details: Identity): Promise<void>;
  restart(): Promise<void>;
  reset(): Promise<void>;
}

declare global {
  interface Window {
    whileisleep?: WhileisleepApi;
  }
}

function boot(current: HTMLScriptElement | null) {
  const script = current ?? document.querySelector<HTMLScriptElement>("script[data-workspace][src*='widget']");
  const key = script?.dataset.workspace;
  if (!script || !key || window.whileisleep) return;
  const apiOrigin = script.dataset.api || new URL(script.src, location.href).origin;

  const host = document.createElement("div");
  host.id = "whileisleep-widget";
  document.body.appendChild(host);

  const widget = new Widget(new WidgetApi(apiOrigin, key), host);
  window.whileisleep = {
    open: (message, intent) => widget.openWith(message, intent),
    close: () => widget.close(),
    hide: () => widget.setHidden(true),
    show: () => widget.setHidden(false),
    identify: (details) => widget.identify(details),
    restart: () => widget.restart(),
    reset: () => widget.reset(),
  };
  window.dispatchEvent(new Event("whileisleep:ready"));
  widget.start().catch((error) => console.warn("whileisleep widget failed to start:", error));
}

// currentScript is only set while the script first runs, so read it now.
const current = document.currentScript as HTMLScriptElement | null;
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => boot(current));
} else {
  boot(current);
}
