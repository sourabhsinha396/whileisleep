"use client";

import clsx from "clsx";
import Link from "next/link";
import { useState } from "react";
import { LimitInput } from "@/components/limit-input";
import { Button, ErrorText, Field, inputClass, PageHeader, Switch } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { useSaveWorkspace } from "@/lib/use-save-workspace";

export default function BehaviorPage() {
  const { workspace } = useWorkspace();
  return (
    <>
      <PageHeader title="Behavior" docs="how-it-works" description="Whether the agent answers visitors, and how." />
      <div className="mx-auto max-w-3xl p-8">
        <AgentSettings key={workspace.id} canEdit={workspace.role === "owner"} />
      </div>
    </>
  );
}

function AgentSettings({ canEdit }: { canEdit: boolean }) {
  const { workspace } = useWorkspace();
  const [enabled, setEnabled] = useState(workspace.ai_enabled);
  const [instructions, setInstructions] = useState(workspace.ai_instructions);
  const [perVisitor, setPerVisitor] = useState(String(workspace.ai_replies_per_visitor));
  const [perDay, setPerDay] = useState(String(workspace.ai_replies_per_day));
  const { save, message, error } = useSaveWorkspace();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    save({ ai_enabled: enabled, ai_instructions: instructions, ai_replies_per_visitor: Number(perVisitor), ai_replies_per_day: Number(perDay) });
  }

  return (
    <form onSubmit={submit} className="space-y-4 rounded-lg border bg-surface p-6 shadow-sm">
      {!workspace.llm_ready && (
        <p className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning">
          No LLM yet, so the agent only matches help articles by keyword and can&apos;t use tools.{" "}
          {workspace.is_organization_owner ? (
            <Link className="font-medium underline" href={`/w/${workspace.slug}/settings/ai-model`}>
              Add a provider key and pick a model
            </Link>
          ) : (
            "Ask the organization owner to add a provider key and pick a model."
          )}
        </p>
      )}
      <label className="flex items-center gap-3 text-sm">
        <Switch disabled={!canEdit} checked={enabled} onChange={setEnabled} />
        Answer visitors automatically. It hands over to your team when asked, or when it can&apos;t answer.
      </label>
      <Field label="Instructions" hint="Tone, scope, and facts that don't fit an article. The agent always answers from your tools and articles, not its own knowledge.">
        <textarea
          className={clsx(inputClass, "min-h-32")}
          disabled={!canEdit}
          placeholder="Be friendly and brief. We only sell practice tests, not exam vouchers. Offer a person for refund questions."
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
        />
      </Field>
      <fieldset>
        <legend className="mb-1.5 text-sm font-medium">Daily limits</legend>
        <p className="mb-3 text-xs text-muted-foreground">How many replies the AI may write a day. Past that, chats go to your team. The count starts again at midnight UTC.</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Per visitor">
            <LimitInput value={perVisitor} onChange={setPerVisitor} disabled={!canEdit} required />
          </Field>
          <Field label="All visitors of this workspace">
            <LimitInput value={perDay} onChange={setPerDay} disabled={!canEdit} required />
          </Field>
        </div>
      </fieldset>
      <ErrorText>{error}</ErrorText>
      {canEdit && (
        <div className="flex items-center gap-3">
          <Button>Save</Button>
          <span className="text-sm text-success">{message}</span>
        </div>
      )}
    </form>
  );
}
