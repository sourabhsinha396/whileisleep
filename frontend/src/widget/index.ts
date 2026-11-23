/**
 * whileisleep chat widget. Add to any site:
 *
 *   <script src="https://YOUR-WHILEISLEEP-HOST/widget.js" data-workspace="ws_..." async></script>
 *
 * Optional: data-api="https://api.example.com" when the API isn't on the script's origin.
 * Then: window.whileisleep.open(), .close(), .identify({ name, email }).
 */

import { WidgetApi } from "./api";
import { Widget } from "./widget";

declare global {
  interface Window {
    whileisleep?: {
      open(): void;
      close(): void;
      identify(details: { name?: string; email?: string }): Promise<void>;
    };
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
    open: () => widget.toggle(true),
    close: () => widget.toggle(false),
    identify: (details) => widget.identify(details),
  };
  widget.start().catch((error) => console.warn("whileisleep widget failed to start:", error));
}

// currentScript is only set while the script first runs, so read it now.
const current = document.currentScript as HTMLScriptElement | null;
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => boot(current));
} else {
  boot(current);
}
