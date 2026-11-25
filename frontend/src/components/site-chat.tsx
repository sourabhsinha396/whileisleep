"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

/** The dashboard, the widget's test page, and pages with a code in their address, which the chat would report. */
const OFF = /^\/(w|app|new|integrations|demo|reset-password|login\/google)(\/|$)/;

const SCRIPT_ID = "site-chat";

/** Our own chat on the public pages, only where a workspace for it is set. */
export function SiteChat({ workspace = process.env.NEXT_PUBLIC_CHAT_WORKSPACE }: { workspace?: string }) {
  const off = OFF.test(usePathname());

  useEffect(() => {
    if (!workspace) return;
    // The script stays through page changes, so on the other pages its bubble is hidden.
    const apply = () => (off ? window.whileisleep?.hide() : window.whileisleep?.show());
    if (!off && !document.getElementById(SCRIPT_ID)) {
      const script = document.createElement("script");
      script.id = SCRIPT_ID;
      script.src = "/widget.js";
      script.async = true;
      script.dataset.workspace = workspace;
      document.body.appendChild(script);
    }
    if (!document.getElementById(SCRIPT_ID)) return;
    apply();
    window.addEventListener("whileisleep:ready", apply);
    return () => window.removeEventListener("whileisleep:ready", apply);
  }, [workspace, off]);

  return null;
}
