"use client";

import clsx from "clsx";
import { Plus } from "lucide-react";
import { useCallback, useState } from "react";
import { Button, ErrorText, Field, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Playbook } from "@/lib/api";
import { usePoll } from "@/lib/use-poll";

type PlaybookDraft = Omit<Playbook, "id" | "updated_at"> & { id?: number };

export default function PlaybooksPage() {
  const { workspace } = useWorkspace();
  const canEdit = workspace.role === "owner";
  const base = `/workspaces/${workspace.id}/playbooks`;
  const { data, reload } = usePoll(useCallback(() => api<Playbook[]>(base), [base]), 60000);
  const [draft, setDraft] = useState<PlaybookDraft | null>(null);
  const [error, setError] = useState("");

  async function save() {
    if (!draft) return;
    setError("");
    const body = { title: draft.title, when_to_use: draft.when_to_use, instructions: draft.instructions, enabled: draft.enabled };
    try {
      if (draft.id) await api(`${base}/${draft.id}`, { method: "PUT", body });
      else await api(base, { method: "POST", body });
      setDraft(null);
      reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove() {
    if (!draft?.id || !window.confirm(`Delete the playbook "${draft.title}"?`)) return;
    await api(`${base}/${draft.id}`, { method: "DELETE" });
    setDraft(null);
    reload();
  }

  return (
    <>
      <PageHeader title="Playbooks" description="Teach the agent how to handle tricky conversations.">
        {canEdit && (
          <Button onClick={() => setDraft({ title: "", when_to_use: "", instructions: "", enabled: true })}>
            <Plus size={16} /> Add playbook
          </Button>
        )}
      </PageHeader>
      <div className="mx-auto max-w-4xl space-y-4 p-8">
        <p className="text-sm text-muted-foreground">
          How to handle a kind of conversation, in plain words. The AI always sees each title and &quot;when to use&quot; line, and reads the
          full instructions only when a conversation matches, so you can have many.
        </p>
        <ul className="divide-y overflow-hidden rounded-lg border bg-surface shadow-sm">
          {(data ?? []).length === 0 && <li className="px-4 py-3 text-sm text-muted-foreground">No playbooks yet.</li>}
          {(data ?? []).map((p) => (
            <li key={p.id} className="flex items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className={clsx("font-medium", !p.enabled && "text-muted-foreground")}>
                  {p.title} {!p.enabled && <span className="text-xs font-normal">(off)</span>}
                </p>
                <p className="truncate text-xs text-muted-foreground">{p.when_to_use}</p>
              </div>
              {canEdit && (
                <Button variant="secondary" onClick={() => setDraft(p)}>
                  Edit
                </Button>
              )}
            </li>
          ))}
        </ul>
        {draft && (
          <div className="space-y-4 rounded-lg border border-primary/30 bg-primary-soft/40 shadow-sm p-5">
            <Field label="Title">
              <input className={inputClass} placeholder="Refund requests" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
            </Field>
            <Field label="When to use" hint="One line; this is what the AI reads to decide.">
              <input
                className={inputClass}
                placeholder="The visitor asks for a refund or says they failed the exam."
                value={draft.when_to_use}
                onChange={(e) => setDraft({ ...draft, when_to_use: e.target.value })}
              />
            </Field>
            <Field label="Instructions">
              <textarea
                className={clsx(inputClass, "min-h-40")}
                placeholder={"1. Ask for the exam date and score report.\n2. If within 30 days, say a teammate will process it and hand off.\n3. Otherwise explain the 30-day window kindly."}
                value={draft.instructions}
                onChange={(e) => setDraft({ ...draft, instructions: e.target.value })}
              />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} /> Enabled
            </label>
            <ErrorText>{error}</ErrorText>
            <div className="flex gap-2">
              <Button onClick={save}>Save playbook</Button>
              <Button variant="ghost" onClick={() => setDraft(null)}>
                Cancel
              </Button>
              {draft.id && (
                <Button variant="danger" className="ml-auto" onClick={remove}>
                  Delete
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
