"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { finish, type Values } from "@/lib/integrations";

/** Connects an integration: opens the service's own page, or waits for the server to try what was typed. */
export function useConnect(path: string, onConnected: () => Promise<void>) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function connect(values: Values = {}) {
    setBusy(true);
    setError("");
    try {
      const { url, job } = await api<{ url: string; job: string }>(`${path}/connect`, { method: "POST", body: { values } });
      if (url) {
        // Elsewhere on the web, so not a page of ours to route to. Stays busy until the page is left.
        window.location.assign(url);
        return;
      }
      await finish(job);
      await onConnected();
    } catch (e) {
      setError((e as Error).message);
    }
    setBusy(false);
  }

  return { connect, busy, error };
}
