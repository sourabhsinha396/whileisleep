"use client";

import clsx from "clsx";
import { Plus } from "lucide-react";
import { useCallback, useState } from "react";
import { NEW_RULE, type RuleDraft, RuleEditor } from "@/components/rule-editor";
import { Button, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Rule } from "@/lib/api";
import { ago } from "@/lib/format";
import { describeRule } from "@/lib/rules";
import { usePoll } from "@/lib/use-poll";

export default function RulesPage() {
  const { workspace } = useWorkspace();
  const canEdit = workspace.role === "owner";
  const base = `/workspaces/${workspace.id}/rules`;
  const { data, reload } = usePoll(useCallback(() => api<Rule[]>(base), [base]), 30000);
  const [draft, setDraft] = useState<RuleDraft | null>(null);
  const rules = data ?? [];

  return (
    <>
      <PageHeader title="Rules" docs="rules" description="Route, tag and answer conversations automatically.">
        {canEdit && (
          <Button onClick={() => setDraft({ ...NEW_RULE, position: rules.length })}>
            <Plus size={16} /> Add rule
          </Button>
        )}
      </PageHeader>
      <div className="mx-auto max-w-4xl space-y-4 p-8">
        <p className="text-sm text-muted-foreground">
          Checked on every visitor message, in order, before the AI. The first match acts in code: an exact reply, a tag, a hand-off, something
          to remember, or one extra instruction for the AI. They cost no tokens when they don&apos;t match.
        </p>
        <ul className="divide-y overflow-hidden rounded-lg border bg-surface shadow-sm">
          {rules.length === 0 && <li className="px-4 py-3 text-sm text-muted-foreground">No rules yet.</li>}
          {rules.map((rule) => (
            <li key={rule.id} className="flex items-center gap-3 px-4 py-3">
              <span className="w-6 text-xs text-muted-foreground">{rule.position}</span>
              <div className="min-w-0 flex-1">
                <p className={clsx("font-medium", !rule.enabled && "text-muted-foreground")}>
                  {rule.name} {!rule.enabled && <span className="text-xs font-normal">(off)</span>}
                </p>
                <p className="truncate text-xs text-muted-foreground">{describeRule(rule)}</p>
              </div>
              <span className="text-xs text-muted-foreground" title="Times matched">
                {rule.match_count}× {rule.last_matched_at && `· ${ago(rule.last_matched_at)} ago`}
              </span>
              {canEdit && (
                <Button variant="secondary" onClick={() => setDraft(rule)}>
                  Edit
                </Button>
              )}
            </li>
          ))}
        </ul>
        {draft && <RuleEditor key={draft.id ?? "new"} initial={draft} base={base} onDone={() => (setDraft(null), reload())} />}
      </div>
    </>
  );
}
