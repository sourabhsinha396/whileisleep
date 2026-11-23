"use client";

import { Copy, ExternalLink } from "lucide-react";
import { useCallback, useState } from "react";
import { Button, ErrorText, Field, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Member, type Workspace } from "@/lib/api";
import { usePoll } from "@/lib/use-poll";

export default function SettingsPage() {
  const { workspace, reload } = useWorkspace();
  const owner = workspace.role === "owner";
  const [form, setForm] = useState({ name: workspace.name, website: workspace.website, color: workspace.color, greeting: workspace.greeting });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  // Workspace pages render only in the browser (the layout waits for the API first).
  const origin = typeof window === "undefined" ? "" : window.location.origin;

  const snippet = `<script src="${origin}/widget.js" data-workspace="${workspace.public_key}" async></script>`;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api<Workspace>(`/workspaces/${workspace.id}`, { method: "PATCH", body: form });
      await reload();
      setMessage("Saved.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <PageHeader title="Settings & widget" />
      <div className="mx-auto max-w-3xl space-y-8 p-8">
        <section className="space-y-3 rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-lg font-semibold">Install the chat widget</h2>
          <p className="text-sm text-gray-600">Paste this before <code>&lt;/body&gt;</code> on every page of your site.</p>
          <div className="flex gap-2">
            <code className="block flex-1 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs whitespace-nowrap text-gray-100">{snippet}</code>
            <Button variant="secondary" onClick={() => navigator.clipboard.writeText(snippet).then(() => setMessage("Snippet copied."))}>
              <Copy size={15} /> Copy
            </Button>
          </div>
          <p className="text-sm text-gray-600">
            Signed-in users? Call <code>window.whileisleep.identify({"{ name, email }"})</code> so conversations show who they are.
          </p>
          <a className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline" href={`/demo?key=${workspace.public_key}`} target="_blank">
            Open a test page with the widget <ExternalLink size={14} />
          </a>
        </section>

        <form onSubmit={save} className="space-y-4 rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="text-lg font-semibold">Workspace</h2>
          <Field label="Name">
            <input className={inputClass} disabled={!owner} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Website">
            <input className={inputClass} disabled={!owner} type="url" value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} />
          </Field>
          <Field label="Greeting" hint="The first message visitors see.">
            <input className={inputClass} disabled={!owner} value={form.greeting} onChange={(e) => setForm({ ...form, greeting: e.target.value })} />
          </Field>
          <Field label="Widget color">
            <input type="color" disabled={!owner} className="h-10 w-20 rounded border border-gray-300" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} />
          </Field>
          <ErrorText>{error}</ErrorText>
          {owner && (
            <div className="flex items-center gap-3">
              <Button>Save</Button>
              <span className="text-sm text-green-700">{message}</span>
            </div>
          )}
        </form>

        <Members canEdit={owner} />
      </div>
    </>
  );
}

function Members({ canEdit }: { canEdit: boolean }) {
  const { workspace } = useWorkspace();
  const base = `/workspaces/${workspace.id}/members`;
  const { data, reload } = usePoll(useCallback(() => api<Member[]>(base), [base]), 60000);
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api(base, { method: "POST", body: { email, role: "agent" } });
      setEmail("");
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="space-y-4 rounded-xl border border-gray-200 bg-white p-6">
      <h2 className="text-lg font-semibold">Team</h2>
      <ul className="divide-y divide-gray-100 text-sm">
        {(data ?? []).map((m) => (
          <li key={m.user_id} className="flex justify-between py-2">
            <span>
              {m.name} <span className="text-gray-500">{m.email}</span>
            </span>
            <span className="text-gray-500 capitalize">{m.role}</span>
          </li>
        ))}
      </ul>
      {canEdit && (
        <form onSubmit={add} className="flex gap-2">
          <input className={inputClass} type="email" required placeholder="teammate@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          <Button>Add</Button>
        </form>
      )}
      <ErrorText>{error}</ErrorText>
    </section>
  );
}
