"use client";

import { Plus, RefreshCw, Server, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { Button, ErrorText, Field, inputClass, Notice } from "@/components/ui";
import { api, type McpServer } from "@/lib/api";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/use-poll";

interface SyncResult {
  server: McpServer;
  added: number;
  changed: number;
  removed: number;
}

/** A sentence for what a sync did, e.g. "3 tools added, 1 changed." */
export function syncSummary(result: Pick<SyncResult, "added" | "changed" | "removed">): string {
  const parts = [
    result.added && `${result.added} ${result.added === 1 ? "tool" : "tools"} added`,
    result.changed && `${result.changed} changed`,
    result.removed && `${result.removed} removed`,
  ].filter(Boolean);
  return parts.length ? `${parts.join(", ")}.` : "No changes.";
}

/** MCP servers the workspace connected. Their tools show up in the tools list above, switched off. */
export function McpServers({ workspaceId, canEdit, onChanged }: { workspaceId: number; canEdit: boolean; onChanged: () => void }) {
  const base = `/workspaces/${workspaceId}/mcp-servers`;
  const { data, reload } = usePoll(useCallback(() => api<McpServer[]>(base), [base]), 60000);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", url: "", token: "" });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function run(work: () => Promise<SyncResult | void>) {
    setError("");
    setMessage("");
    try {
      const result = await work();
      if (result) setMessage(result.server.last_error || syncSummary(result));
      reload();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const add = (e: React.FormEvent) => {
    e.preventDefault();
    run(async () => {
      const headers = form.token.trim() ? { Authorization: `Bearer ${form.token.trim()}` } : {};
      const result = await api<SyncResult>(base, { method: "POST", body: { name: form.name, url: form.url, headers } });
      setForm({ name: "", url: "", token: "" });
      setAdding(false);
      return result;
    });
  };

  function remove(server: McpServer) {
    if (window.confirm(`Remove ${server.name} and its ${server.tool_count} tools?`)) run(() => api(`${base}/${server.id}`, { method: "DELETE" }));
  }

  return (
    <div className="space-y-3 border-t pt-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-bold tracking-tight">
            <Server size={16} /> MCP servers
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Connect a Model Context Protocol server to import its tools. They arrive switched off: turn on the ones the agent may use. If a
            server later changes a tool&apos;s description, that tool is paused until you look at it again.
          </p>
        </div>
        {canEdit && !adding && (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            <Plus size={16} /> Connect
          </Button>
        )}
      </div>

      {(data ?? []).length > 0 && (
        <ul className="divide-y overflow-hidden rounded-lg border">
          {(data ?? []).map((server) => (
            <li key={server.id} className="flex items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="font-mono text-sm font-semibold">{server.name}</p>
                <p className="truncate text-xs text-muted-foreground">{server.url}</p>
                <p className="text-xs text-muted-foreground">
                  {server.active_tool_count} of {server.tool_count} tools on
                  {server.last_synced_at && ` · synced ${ago(server.last_synced_at)} ago`}
                </p>
                {server.last_error && <p className="text-xs text-danger">{server.last_error}</p>}
              </div>
              {canEdit && (
                <>
                  <Button variant="secondary" onClick={() => run(() => api<SyncResult>(`${base}/${server.id}/sync`, { method: "POST" }))}>
                    <RefreshCw size={15} /> Sync
                  </Button>
                  <Button variant="ghost" aria-label={`Remove ${server.name}`} onClick={() => remove(server)}>
                    <Trash2 size={15} />
                  </Button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {adding && (
        <form onSubmit={add} className="space-y-3 rounded-lg border border-primary/30 bg-primary-soft/40 p-4">
          <div className="grid grid-cols-[160px_1fr] gap-3">
            <Field label="Name" hint="Lowercase letters and digits. It starts each tool's name.">
              <input className={`${inputClass} font-mono`} required placeholder="shop" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value.trim().toLowerCase() })} />
            </Field>
            <Field label="Server URL">
              <input className={inputClass} required type="url" placeholder="https://mcp.example.com/mcp" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
            </Field>
          </div>
          <Field label="Access token" hint="Sent as a Bearer token. Stored encrypted and never shown again. Leave empty if the server needs none.">
            <input className={inputClass} type="password" autoComplete="off" value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })} />
          </Field>
          <div className="flex gap-2">
            <Button>Connect and import tools</Button>
            <Button type="button" variant="ghost" onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {message && <Notice tone="primary">{message}</Notice>}
      <ErrorText>{error}</ErrorText>
    </div>
  );
}
