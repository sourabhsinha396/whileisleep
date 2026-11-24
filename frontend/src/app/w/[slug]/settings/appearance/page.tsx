"use client";

import { useState } from "react";
import { ColorPicker } from "@/components/color-picker";
import { Button, ErrorText, Field, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { useSaveWorkspace } from "@/lib/use-save-workspace";

export default function AppearancePage() {
  const { workspace } = useWorkspace();
  const owner = workspace.role === "owner";
  const { save, message, error } = useSaveWorkspace();
  const [form, setForm] = useState({ greeting: workspace.greeting, color: workspace.color });

  return (
    <>
      <PageHeader title="Appearance" description="How the chat widget looks and greets visitors." />
      <div className="mx-auto max-w-3xl p-8">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save(form);
          }}
          className="space-y-4 rounded-lg border bg-surface p-6 shadow-sm"
        >
          <Field label="Greeting" hint="The first message visitors see.">
            <input className={inputClass} disabled={!owner} value={form.greeting} onChange={(e) => setForm({ ...form, greeting: e.target.value })} />
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
      </div>
    </>
  );
}
