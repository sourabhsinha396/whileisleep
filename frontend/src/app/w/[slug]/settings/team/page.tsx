"use client";

import { useCallback, useState } from "react";
import { ImageUpload } from "@/components/image-upload";
import { Avatar, Button, ErrorText, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Member, type User } from "@/lib/api";
import { usePoll } from "@/lib/use-poll";

export default function TeamPage() {
  const { workspace } = useWorkspace();
  return (
    <>
      <PageHeader title="Team" description="Who can answer conversations in this workspace." />
      <div className="mx-auto max-w-3xl p-8">
        <TeamSettings canEdit={workspace.role === "owner"} />
      </div>
    </>
  );
}

function TeamSettings({ canEdit }: { canEdit: boolean }) {
  const { me, workspace, reload: reloadWorkspace } = useWorkspace();
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
    <section className="space-y-6 rounded-lg border bg-surface p-6 shadow-sm">
      <ImageUpload<User>
        label="Your photo"
        hint="Visitors see it next to your replies, in every workspace you belong to."
        path="/auth/me/photo"
        src={me.photo_url}
        fallback={me.name}
        enabled={workspace.uploads_enabled}
        onDone={() => Promise.all([reloadWorkspace(), reload()])}
      />
      <ul className="divide-y divide-border text-sm">
        {(data ?? []).map((m) => (
          <li key={m.user_id} className="flex items-center gap-3 py-2">
            <Avatar name={m.name} src={m.photo_url} size={28} />
            <span className="flex-1">
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
