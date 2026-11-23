"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, ErrorText, Field, inputClass, Logo, ThemeToggle } from "@/components/ui";
import { api, type Workspace } from "@/lib/api";

export default function NewWorkspacePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const workspace = await api<Workspace>("/workspaces", { method: "POST", body: { name, website } });
      router.push(`/w/${workspace.slug}/settings`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col bg-muted px-6 py-8">
      <div className="flex items-center justify-between">
        <Logo />
        <ThemeToggle />
      </div>
      <div className="flex flex-1 items-center justify-center py-10">
        <form onSubmit={submit} className="w-full max-w-md space-y-5 rounded-lg border bg-surface p-8 shadow-sm">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">New workspace</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              One workspace per website. Each gets its own inbox, help center, AI tools and widget snippet.
            </p>
          </div>
          <Field label="Name">
            <input className={inputClass} required placeholder="Acme Store" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Website" hint="Relative links in AI answers resolve against this.">
            <input className={inputClass} type="url" placeholder="https://acme.com" value={website} onChange={(e) => setWebsite(e.target.value)} />
          </Field>
          <ErrorText>{error}</ErrorText>
          <div className="flex gap-2">
            <Button disabled={busy}>{busy ? "Creating…" : "Create workspace"}</Button>
            <Button type="button" variant="ghost" onClick={() => router.back()}>
              Cancel
            </Button>
          </div>
        </form>
      </div>
    </main>
  );
}
