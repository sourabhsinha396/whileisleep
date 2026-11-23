"use client";

import { Copy, ExternalLink } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { ColorPicker } from "@/components/color-picker";
import { Button, ErrorText, Field, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Member, type Workspace } from "@/lib/api";
import { usePoll } from "@/lib/use-poll";

export default function SettingsPage() {
  const { workspace, reload } = useWorkspace();
  const router = useRouter();
  const owner = workspace.role === "owner";
  const [form, setForm] = useState({
    name: workspace.name,
    slug: workspace.slug,
    website: workspace.website,
    color: workspace.color,
    greeting: workspace.greeting,
    timezone: workspace.timezone,
  });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  // Workspace pages render only in the browser (the layout waits for the API first).
  const origin = typeof window === "undefined" ? "" : window.location.origin;

  const snippet = `<script src="${origin}/widget.js" data-workspace="${workspace.public_key}" async></script>`;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const saved = await api<Workspace>(`/workspaces/${workspace.id}`, { method: "PATCH", body: form });
      await reload();
      setMessage("Saved.");
      // A new address: this page now lives there.
      if (saved.slug !== workspace.slug) router.replace(`/w/${saved.slug}/settings`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <PageHeader title="Settings & widget" description="Install the widget, brand it, and manage your team." />
      <div className="mx-auto max-w-3xl space-y-8 p-8">
        <section className="space-y-3 rounded-lg border bg-surface p-6 shadow-sm">
          <h2 className="text-base font-bold tracking-tight">Install the chat widget</h2>
          <p className="text-sm text-muted-foreground">Paste this before <code>&lt;/body&gt;</code> on every page of your site.</p>
          <div className="flex gap-2">
            <code className="block flex-1 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs whitespace-nowrap text-gray-100">{snippet}</code>
            <Button variant="secondary" onClick={() => navigator.clipboard.writeText(snippet).then(() => setMessage("Snippet copied."))}>
              <Copy size={15} /> Copy
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">
            Signed-in users? Call <code>window.whileisleep.identify({"{ name, email }"})</code> so conversations show who they are. To let
            tools look up a user&apos;s own data, prove who they are with a signed token (below).
          </p>
          <a className="inline-flex items-center gap-1 text-sm font-medium text-primary-text hover:underline" href={`/demo?key=${workspace.public_key}`} target="_blank">
            Open a test page with the widget <ExternalLink size={14} />
          </a>
        </section>

        <form onSubmit={save} className="space-y-4 rounded-lg border bg-surface p-6 shadow-sm">
          <h2 className="text-base font-bold tracking-tight">Workspace</h2>
          <Field label="Name">
            <input className={inputClass} disabled={!owner} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Dashboard address" hint={`This workspace's pages are at /w/${form.slug || "…"}/. Lowercase letters, digits and hyphens. Changing it breaks old bookmarks.`}>
            <input
              className={`${inputClass} font-mono`}
              disabled={!owner}
              required
              pattern="[a-z0-9]+(-[a-z0-9]+)*"
              minLength={2}
              maxLength={60}
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })}
            />
          </Field>
          <Field label="Website">
            <input className={inputClass} disabled={!owner} type="url" value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} />
          </Field>
          <Field label="Greeting" hint="The first message visitors see.">
            <input className={inputClass} disabled={!owner} value={form.greeting} onChange={(e) => setForm({ ...form, greeting: e.target.value })} />
          </Field>
          <Field label="Timezone" hint="Rules read the hour and weekday in this timezone, e.g. Europe/Berlin or Asia/Kolkata.">
            <input className={inputClass} disabled={!owner} value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value.trim() })} />
          </Field>
          <ColorPicker value={form.color} saved={workspace.color} disabled={!owner} onChange={(color) => setForm({ ...form, color })} />
          <ErrorText>{error}</ErrorText>
          {owner && (
            <div className="flex items-center gap-3">
              <Button>Save</Button>
              <span className="text-sm text-success">{message}</span>
            </div>
          )}
        </form>

        {owner && <IdentitySecret />}
        <Members canEdit={owner} />
      </div>
    </>
  );
}

/** The secret the site's server signs identity tokens with. Fetched only when asked for. */
function IdentitySecret() {
  const { workspace } = useWorkspace();
  const base = `/workspaces/${workspace.id}/identity-secret`;
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");

  async function load(path: string, method: "GET" | "POST") {
    setError("");
    try {
      setSecret((await api<{ secret: string }>(path, { method })).secret);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function rotate() {
    if (window.confirm("Replace the secret? Tokens signed with the current one stop working at once.")) load(`${base}/rotate`, "POST");
  }

  return (
    <section className="space-y-3 rounded-lg border bg-surface p-6 shadow-sm">
      <h2 className="text-base font-bold tracking-tight">Verified identity</h2>
      <p className="text-sm text-muted-foreground">
        What a page says about its user can be typed into a browser console, so tools only use a visitor&apos;s details once your server
        has vouched for them. Sign a short-lived HS256 token with this secret on your server (claims: <code>sub</code> your user&apos;s id,{" "}
        <code>exp</code>, plus <code>email</code>, <code>name</code> and anything else) and call{" "}
        <code>window.whileisleep.identify({"{ token }"})</code>. Keep the secret on the server; never put it in the page.
      </p>
      {secret ? (
        <div className="flex gap-2">
          <code className="block flex-1 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs whitespace-nowrap text-gray-100">{secret}</code>
          <Button variant="secondary" onClick={() => navigator.clipboard.writeText(secret)}>
            <Copy size={15} /> Copy
          </Button>
        </div>
      ) : (
        <Button variant="secondary" onClick={() => load(base, "GET")}>
          Show the secret
        </Button>
      )}
      {secret && (
        <Button variant="danger" onClick={rotate}>
          Replace the secret
        </Button>
      )}
      <ErrorText>{error}</ErrorText>
    </section>
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
    <section className="space-y-4 rounded-lg border bg-surface p-6 shadow-sm">
      <h2 className="text-base font-bold tracking-tight">Team</h2>
      <ul className="divide-y divide-border text-sm">
        {(data ?? []).map((m) => (
          <li key={m.user_id} className="flex justify-between py-2">
            <span>
              {m.name} <span className="text-muted-foreground">{m.email}</span>
            </span>
            <span className="text-muted-foreground capitalize">{m.role}</span>
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
