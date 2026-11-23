"use client";

import clsx from "clsx";
import { BookText, Plus, Zap } from "lucide-react";
import { useCallback, useState } from "react";
import { Button, ErrorText, Field, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Playbook, type Rule } from "@/lib/api";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/use-poll";

export default function AutomationPage() {
  const { workspace } = useWorkspace();
  const canEdit = workspace.role === "owner";
  return (
    <>
      <PageHeader title="Rules & playbooks" />
      <div className="mx-auto max-w-4xl space-y-8 p-8">
        <Rules canEdit={canEdit} />
        <Playbooks canEdit={canEdit} />
      </div>
    </>
  );
}

// --- Rules ---

type RuleDraft = Omit<Rule, "id" | "match_count" | "last_matched_at"> & { id?: number };

const NEW_RULE: RuleDraft = {
  name: "",
  enabled: true,
  position: 0,
  intent: "",
  keywords: "",
  page_contains: "",
  first_message_only: false,
  reply: "",
  ai_instruction: "",
  tag: "",
  handoff: false,
  also_when_human: false,
};

function describe(rule: Rule): string {
  const when = [
    rule.intent && `intent is ${rule.intent}`,
    rule.keywords && `message mentions ${rule.keywords.split("\n").join(" or ")}`,
    rule.page_contains && `page has ${rule.page_contains}`,
    rule.first_message_only && "first message",
  ].filter(Boolean);
  const then = [
    rule.reply && "fixed reply",
    rule.ai_instruction && "instructs the AI",
    rule.tag && `tag ${rule.tag}`,
    rule.handoff && "hand off",
  ].filter(Boolean);
  return `When ${when.join(" and ")} → ${then.join(", ")}`;
}

function Rules({ canEdit }: { canEdit: boolean }) {
  const { workspace } = useWorkspace();
  const base = `/workspaces/${workspace.id}/rules`;
  const { data, reload } = usePoll(useCallback(() => api<Rule[]>(base), [base]), 30000);
  const [draft, setDraft] = useState<RuleDraft | null>(null);
  const rules = data ?? [];

  return (
    <section className="space-y-4 rounded-xl border border-gray-200 bg-white p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Zap size={18} /> Rules
          </h2>
          <p className="mt-1 text-sm text-gray-600">
            Checked on every visitor message, in order, before the AI. The first match acts in code: an exact reply, a tag, a hand-off, or
            one extra instruction for the AI. They cost no tokens when they don&apos;t match.
          </p>
        </div>
        {canEdit && (
          <Button onClick={() => setDraft({ ...NEW_RULE, position: rules.length })}>
            <Plus size={16} /> Add rule
          </Button>
        )}
      </div>
      <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200">
        {rules.length === 0 && <li className="px-4 py-3 text-sm text-gray-500">No rules yet.</li>}
        {rules.map((rule) => (
          <li key={rule.id} className="flex items-center gap-3 px-4 py-3">
            <span className="w-6 text-xs text-gray-400">{rule.position}</span>
            <div className="min-w-0 flex-1">
              <p className={clsx("font-medium", !rule.enabled && "text-gray-400")}>
                {rule.name} {!rule.enabled && <span className="text-xs font-normal">(off)</span>}
              </p>
              <p className="truncate text-xs text-gray-500">{describe(rule)}</p>
            </div>
            <span className="text-xs text-gray-500" title="Times matched">
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
    </section>
  );
}

function RuleEditor({ initial, base, onDone }: { initial: RuleDraft; base: string; onDone: () => void }) {
  const [d, setD] = useState<RuleDraft>(initial);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"reply" | "instruction" | "none">(initial.ai_instruction ? "instruction" : initial.reply || !initial.id ? "reply" : "none");
  const set = (patch: Partial<RuleDraft>) => setD({ ...d, ...patch });

  async function save() {
    setError("");
    const body = { ...d, reply: mode === "reply" ? d.reply : "", ai_instruction: mode === "instruction" ? d.ai_instruction : "" };
    try {
      if (d.id) await api(`${base}/${d.id}`, { method: "PUT", body });
      else await api(base, { method: "POST", body });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove() {
    if (!d.id || !window.confirm(`Delete the rule "${d.name}"?`)) return;
    await api(`${base}/${d.id}`, { method: "DELETE" });
    onDone();
  }

  return (
    <div className="space-y-5 rounded-xl border border-brand/30 bg-brand-soft/30 p-5">
      <div className="grid grid-cols-[1fr_100px_auto] items-end gap-3">
        <Field label="Name">
          <input className={inputClass} placeholder="Exam requests" value={d.name} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label="Order">
          <input className={inputClass} type="number" min={0} value={d.position} onChange={(e) => set({ position: Number(e.target.value) || 0 })} />
        </Field>
        <label className="flex items-center gap-2 pb-2 text-sm">
          <input type="checkbox" checked={d.enabled} onChange={(e) => set({ enabled: e.target.checked })} /> Enabled
        </label>
      </div>

      <fieldset className="space-y-3">
        <legend className="mb-2 text-sm font-semibold">When (all that are set must hold)</legend>
        <Field label="Intent" hint={'Label a button on your site sends: window.whileisleep.open(text, { intent: "exam_request", data: {...} }).'}>
          <input className={clsx(inputClass, "font-mono")} placeholder="exam_request" value={d.intent} onChange={(e) => set({ intent: e.target.value })} />
        </Field>
        <Field label="Message mentions any of" hint="One phrase per line, not case-sensitive.">
          <textarea className={clsx(inputClass, "min-h-16")} placeholder={"refund\nmoney back"} value={d.keywords} onChange={(e) => set({ keywords: e.target.value })} />
        </Field>
        <Field label="Page URL contains">
          <input className={inputClass} placeholder="/pricing" value={d.page_contains} onChange={(e) => set({ page_contains: e.target.value })} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={d.first_message_only} onChange={(e) => set({ first_message_only: e.target.checked })} /> Only the
          visitor&apos;s first message
        </label>
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="mb-2 text-sm font-semibold">Then</legend>
        <div className="flex gap-1 text-sm">
          {(
            [
              ["reply", "Send a fixed reply"],
              ["instruction", "Instruct the AI"],
              ["none", "Neither"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setMode(value)}
              className={clsx("rounded-md px-3 py-1.5", mode === value ? "bg-white font-semibold shadow-sm ring-1 ring-gray-200" : "text-gray-600")}
            >
              {label}
            </button>
          ))}
        </div>
        {mode === "reply" && (
          <Field label="Reply" hint="Sent as is; the AI doesn't answer this message. Fills in {visitor.name}, {visitor.email} and {data.KEY} from the intent's data.">
            <textarea
              className={clsx(inputClass, "min-h-20")}
              placeholder="Thanks! We'll try to add {data.exam_name} within 12 hours and reply here when it's live."
              value={d.reply}
              onChange={(e) => set({ reply: e.target.value })}
            />
          </Field>
        )}
        {mode === "instruction" && (
          <Field label="Instruction for the AI" hint="The AI still writes the answer, following this for this message only.">
            <textarea
              className={clsx(inputClass, "min-h-20")}
              placeholder="Apologise first, then check the order with get_order before answering."
              value={d.ai_instruction}
              onChange={(e) => set({ ai_instruction: e.target.value })}
            />
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Tag the conversation">
            <input className={inputClass} placeholder="exam-request" value={d.tag} onChange={(e) => set({ tag: e.target.value })} />
          </Field>
          <div className="space-y-2 pt-6 text-sm">
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={d.handoff} onChange={(e) => set({ handoff: e.target.checked })} /> Hand off to a person
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={d.also_when_human} onChange={(e) => set({ also_when_human: e.target.checked })} /> Also after a person
              took over
            </label>
          </div>
        </div>
      </fieldset>

      <ErrorText>{error}</ErrorText>
      <div className="flex gap-2">
        <Button onClick={save}>Save rule</Button>
        <Button variant="ghost" onClick={onDone}>
          Cancel
        </Button>
        {d.id && (
          <Button variant="danger" className="ml-auto" onClick={remove}>
            Delete
          </Button>
        )}
      </div>
    </div>
  );
}

// --- Playbooks ---

type PlaybookDraft = Omit<Playbook, "id" | "updated_at"> & { id?: number };

function Playbooks({ canEdit }: { canEdit: boolean }) {
  const { workspace } = useWorkspace();
  const base = `/workspaces/${workspace.id}/playbooks`;
  const { data, reload } = usePoll(useCallback(() => api<Playbook[]>(base), [base]), 60000);
  const [draft, setDraft] = useState<PlaybookDraft | null>(null);
  const [error, setError] = useState("");

  async function save() {
    if (!draft) return;
    setError("");
    const body = { title: draft.title, when_to_use: draft.when_to_use, instructions: draft.instructions, enabled: draft.enabled };
    try {
      if (draft.id) await api(`${base}/${draft.id}`, { method: "PUT", body });
      else await api(base, { method: "POST", body });
      setDraft(null);
      reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove() {
    if (!draft?.id || !window.confirm(`Delete the playbook "${draft.title}"?`)) return;
    await api(`${base}/${draft.id}`, { method: "DELETE" });
    setDraft(null);
    reload();
  }

  return (
    <section className="space-y-4 rounded-xl border border-gray-200 bg-white p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <BookText size={18} /> Playbooks
          </h2>
          <p className="mt-1 text-sm text-gray-600">
            How to handle a kind of conversation, in plain words. The AI always sees each title and &quot;when to use&quot; line, and reads the
            full instructions only when a conversation matches, so you can have many.
          </p>
        </div>
        {canEdit && (
          <Button onClick={() => setDraft({ title: "", when_to_use: "", instructions: "", enabled: true })}>
            <Plus size={16} /> Add playbook
          </Button>
        )}
      </div>
      <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200">
        {(data ?? []).length === 0 && <li className="px-4 py-3 text-sm text-gray-500">No playbooks yet.</li>}
        {(data ?? []).map((p) => (
          <li key={p.id} className="flex items-center gap-3 px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className={clsx("font-medium", !p.enabled && "text-gray-400")}>
                {p.title} {!p.enabled && <span className="text-xs font-normal">(off)</span>}
              </p>
              <p className="truncate text-xs text-gray-500">{p.when_to_use}</p>
            </div>
            {canEdit && (
              <Button variant="secondary" onClick={() => setDraft(p)}>
                Edit
              </Button>
            )}
          </li>
        ))}
      </ul>
      {draft && (
        <div className="space-y-4 rounded-xl border border-brand/30 bg-brand-soft/30 p-5">
          <Field label="Title">
            <input className={inputClass} placeholder="Refund requests" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </Field>
          <Field label="When to use" hint="One line; this is what the AI reads to decide.">
            <input
              className={inputClass}
              placeholder="The visitor asks for a refund or says they failed the exam."
              value={draft.when_to_use}
              onChange={(e) => setDraft({ ...draft, when_to_use: e.target.value })}
            />
          </Field>
          <Field label="Instructions">
            <textarea
              className={clsx(inputClass, "min-h-40")}
              placeholder={"1. Ask for the exam date and score report.\n2. If within 30 days, say a teammate will process it and hand off.\n3. Otherwise explain the 30-day window kindly."}
              value={draft.instructions}
              onChange={(e) => setDraft({ ...draft, instructions: e.target.value })}
            />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} /> Enabled
          </label>
          <ErrorText>{error}</ErrorText>
          <div className="flex gap-2">
            <Button onClick={save}>Save playbook</Button>
            <Button variant="ghost" onClick={() => setDraft(null)}>
              Cancel
            </Button>
            {draft.id && (
              <Button variant="danger" className="ml-auto" onClick={remove}>
                Delete
              </Button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
