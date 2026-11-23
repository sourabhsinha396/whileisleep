"use client";

import clsx from "clsx";
import { Plus } from "lucide-react";
import { useCallback, useState } from "react";
import { Button, ErrorText, Field, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Article } from "@/lib/api";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/use-poll";

type Draft = Pick<Article, "title" | "body" | "published"> & { id?: number };

export default function KnowledgePage() {
  const { workspace } = useWorkspace();
  const base = `/workspaces/${workspace.id}/articles`;
  const { data, reload } = usePoll(useCallback(() => api<Article[]>(base), [base]), 60000);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState("");

  async function save() {
    if (!draft) return;
    setError("");
    try {
      const body = { title: draft.title, body: draft.body, published: draft.published };
      const saved = draft.id
        ? await api<Article>(`${base}/${draft.id}`, { method: "PUT", body })
        : await api<Article>(base, { method: "POST", body });
      setDraft(saved);
      reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove() {
    if (!draft?.id || !window.confirm(`Delete "${draft.title}"? This can't be undone.`)) return;
    await api(`${base}/${draft.id}`, { method: "DELETE" });
    setDraft(null);
    reload();
  }

  return (
    <>
      <PageHeader title="Knowledge base" description="Articles show in the widget's Help tab, and the AI agent searches them to answer questions.">
        <Button onClick={() => setDraft({ title: "", body: "", published: true })}>
          <Plus size={16} /> New article
        </Button>
      </PageHeader>
      <div className="grid grid-cols-[320px_1fr] gap-6 p-8">
        <div className="space-y-2">
          {(data ?? []).map((a) => (
            <button
              key={a.id}
              onClick={() => setDraft(a)}
              className={clsx(
                "block w-full rounded-lg border bg-surface p-3 text-left shadow-sm transition-colors",
                draft?.id === a.id ? "border-primary ring-2 ring-ring/30" : "hover:border-primary/40",
              )}
            >
              <span className="block font-medium">{a.title}</span>
              <span className="text-xs text-muted-foreground">
                {a.published ? "Published" : "Draft"} · updated {ago(a.updated_at)} ago
              </span>
            </button>
          ))}
          {data?.length === 0 && <p className="text-sm text-muted-foreground">No articles yet.</p>}
        </div>
        {draft ? (
          <div className="space-y-4 rounded-lg border bg-surface p-6 shadow-sm">
            <Field label="Title">
              <input className={inputClass} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
            </Field>
            <Field label="Body" hint="Markdown: **bold**, [links](https://…), blank line between paragraphs.">
              <textarea className={clsx(inputClass, "min-h-80 font-mono")} value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={draft.published} onChange={(e) => setDraft({ ...draft, published: e.target.checked })} />
              Published (visible in the widget and to the AI agent)
            </label>
            <ErrorText>{error}</ErrorText>
            <div className="flex gap-2">
              <Button onClick={save}>Save</Button>
              {draft.id && (
                <Button variant="danger" onClick={remove}>
                  Delete
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="grid place-items-center rounded-lg border border-dashed p-10 text-sm text-muted-foreground">
            Pick an article or create a new one.
          </div>
        )}
      </div>
    </>
  );
}
