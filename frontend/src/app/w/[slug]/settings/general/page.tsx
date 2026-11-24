"use client";

import { useState } from "react";
import { Button, ErrorText, Field, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { useSaveWorkspace } from "@/lib/use-save-workspace";

export default function GeneralPage() {
  const { workspace } = useWorkspace();
  const owner = workspace.role === "owner";
  const { save, message, error } = useSaveWorkspace();
  const [form, setForm] = useState({ name: workspace.name, slug: workspace.slug, website: workspace.website, timezone: workspace.timezone });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    // With a new address, the layout moves this page there.
    save(form);
  }

  return (
    <>
      <PageHeader title="General" description="This workspace's name, address and timezone." />
      <div className="mx-auto max-w-3xl p-8">
        <form onSubmit={submit} className="space-y-4 rounded-lg border bg-surface p-6 shadow-sm">
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
          <Field label="Timezone" hint="Rules read the hour and weekday in this timezone, e.g. Europe/Berlin or Asia/Kolkata.">
            <input className={inputClass} disabled={!owner} value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value.trim() })} />
          </Field>
          <ErrorText>{error}</ErrorText>
          {owner && (
            <div className="flex items-center gap-3">
              <Button>Save</Button>
              <span className="text-sm text-success">{message}</span>
            </div>
          )}
        </form>
      </div>
    </>
  );
}
