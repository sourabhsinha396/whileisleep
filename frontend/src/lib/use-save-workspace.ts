"use client";

import { useState } from "react";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Workspace } from "@/lib/api";

/** Saves some of the workspace's fields, and says how it went. */
export function useSaveWorkspace() {
  const { workspace, reload } = useWorkspace();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function save(fields: Partial<Workspace>): Promise<void> {
    setError("");
    setMessage("");
    try {
      await api<Workspace>(`/workspaces/${workspace.id}`, { method: "PATCH", body: fields });
      await reload();
      setMessage("Saved.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return { save, message, error };
}
