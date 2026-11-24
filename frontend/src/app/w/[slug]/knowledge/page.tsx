"use client";

import clsx from "clsx";
import { Plus } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { ArticleEditor } from "@/components/article-editor";
import { Button, ErrorText, Field, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Article, upload } from "@/lib/api";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/use-poll";

type Draft = Pick<Article, "title" | "body" | "published"> & { id?: number };

export default function KnowledgePage() {
  const { workspace } = useWorkspace();
  const base = `/workspaces/${workspace.id}/articles`;
  const { data, reload } = usePoll(useCallback(() => api<Article[]>(base), [base]), 60000);
  const [draft, setDraft] = useState<Draft | null>(null);
  // Changes when another article is opened, so the editor starts over with its text.
  const [opened, setOpened] = useState(0);
  const [error, setError] = useState("");

  function open(next: Draft) {
    setDraft(next);
    setOpened((n) => n + 1);
    setError("");
  }

  /** Stores an image in the article's folder, so the article has to exist first: a new one is
   * saved as a draft. */
  async function uploadImage(file: File) {
    let id = draft?.id;
    if (!id) {
      if (!draft?.title.trim()) throw new Error("Give the article a title first, then add images.");
      id = (await api<Article>(base, { method: "POST", body: { title: draft.title, body: draft.body, published: false } })).id;
      setDraft((current) => current && { ...current, id });
      reload();
    }
    return (await upload<{ url: string }>(`${base}/${id}/images`, file)).url;
  }

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
        <Button onClick={() => open({ title: "", body: "", published: true })}>
          <Plus size={16} /> New article
        </Button>
      </PageHeader>
      <div className="grid grid-cols-[320px_1fr] gap-6 p-8">
        <div className="space-y-2">
          {(data ?? []).map((a) => (
            <button
              key={a.id}
              onClick={() => open(a)}
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
            {/* Not a <Field>: its <label> would pass clicks in the text to the first button. */}
            <div>
              <span className="mb-1.5 block text-sm font-medium">Body</span>
              <ArticleEditor
                key={opened}
                value={draft.body}
                onChange={(body) => setDraft((current) => current && { ...current, body })}
                onUpload={uploadImage}
                uploadsEnabled={workspace.article_uploads_enabled}
              />
              <p className="mt-1.5 text-xs text-muted-foreground">
                {workspace.article_uploads_enabled ? (
                  "Paste or drop images into the text. PNG, JPEG or WebP, up to 5 MB each."
                ) : workspace.is_organization_owner ? (
                  <>
                    Want images?{" "}
                    <Link className="font-medium text-primary-text hover:underline" href={`/w/${workspace.slug}/settings/storage`}>
                      Connect your storage
                    </Link>
                    .
                  </>
                ) : (
                  "Images need your organization's storage; its owner can connect it."
                )}
              </p>
            </div>
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
