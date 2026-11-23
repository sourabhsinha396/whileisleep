"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, ErrorText, Field, inputClass } from "@/components/ui";
import { api, type Workspace } from "@/lib/api";

export default function NewWorkspacePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const workspace = await api<Workspace>("/workspaces", { method: "POST", body: { name, website } });
      router.push(`/w/${workspace.id}/settings`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center p-4">
      <form onSubmit={submit} className="w-full max-w-md space-y-4 rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold">New workspace</h1>
        <p className="text-sm text-gray-600">One workspace per website. Each gets its own inbox, help center, AI tools and widget snippet.</p>
        <Field label="Name">
          <input className={inputClass} required placeholder="Acme Store" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Website" hint="Relative links in AI answers resolve against this.">
          <input className={inputClass} type="url" placeholder="https://acme.com" value={website} onChange={(e) => setWebsite(e.target.value)} />
        </Field>
        <ErrorText>{error}</ErrorText>
        <div className="flex gap-2">
          <Button>Create workspace</Button>
          <Button type="button" variant="ghost" onClick={() => router.back()}>
            Cancel
          </Button>
        </div>
      </form>
    </main>
  );
}
