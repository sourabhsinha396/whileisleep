"use client";

import { useCallback, useState } from "react";
import { Button, ErrorText, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Member } from "@/lib/api";
import { usePoll } from "@/lib/use-poll";

export default function TeamPage() {
  const { workspace } = useWorkspace();
  return (
    <>
      <PageHeader title="Team" description="Who can answer conversations in this workspace." />
      <div className="mx-auto max-w-3xl p-8">
        <Members canEdit={workspace.role === "owner"} />
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
    <section className="space-y-4 rounded-lg border bg-surface p-6 shadow-sm">
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
