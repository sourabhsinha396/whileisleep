"use client";

import clsx from "clsx";
import { FlaskConical, Plus, X } from "lucide-react";
import { useState } from "react";
import { Select } from "@/components/select";
import { Button, ErrorText, Field, inputClass, Segmented } from "@/components/ui";
import { api, type Rule } from "@/lib/api";
import { ago } from "@/lib/format";
import {
  type Action,
  type Condition,
  FIELDS,
  fieldOption,
  type Group,
  newRow,
  opLabel,
  opsFor,
  type Row,
  takesList,
  takesNoValue,
  toGroup,
  toTree,
  WEEKDAYS,
} from "@/lib/rules";

export type RuleDraft = Omit<Rule, "id" | "match_count" | "last_matched_at"> & { id?: number };

export const NEW_RULE: RuleDraft = {
  name: "",
  enabled: true,
  position: 0,
  conditions: { all: [{ field: "message.text", op: "contains_any", value: [] }] },
  actions: [{ type: "reply", text: "" }],
  also_when_human: false,
};

interface Backtest {
  checked: number;
  matched: number;
  samples: { message_id: number; conversation_id: number; text: string; created_at: string }[];
}

type AttributeAction = Extract<Action, { type: "set_attribute" }>;
type ReplyMode = "reply" | "instruct" | "none";

/** The parts of `actions` the form edits one by one. */
function splitActions(actions: Action[]) {
  const text = actions.find((a) => a.type === "reply" || a.type === "instruct") as { type: ReplyMode; text: string } | undefined;
  return {
    mode: (text?.type ?? "none") as ReplyMode,
    text: text?.text ?? "",
    tag: (actions.find((a) => a.type === "tag") as { value: string } | undefined)?.value ?? "",
    handoff: actions.some((a) => a.type === "handoff"),
    attributes: actions.filter((a): a is AttributeAction => a.type === "set_attribute"),
  };
}

export function RuleEditor({ initial, base, onDone }: { initial: RuleDraft; base: string; onDone: () => void }) {
  const [d, setD] = useState<RuleDraft>(initial);
  // Nested trees can't be shown as rows; those are edited as JSON.
  const [group, setGroup] = useState<Group | null>(() => toGroup(initial.conditions));
  const [json, setJson] = useState(() => JSON.stringify(initial.conditions, null, 2));
  const [parts, setParts] = useState(() => splitActions(initial.actions));
  const [error, setError] = useState("");
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const set = (patch: Partial<RuleDraft>) => setD({ ...d, ...patch });

  function conditions(): Condition {
    return group ? toTree(group) : (JSON.parse(json) as Condition);
  }

  function actions(): Action[] {
    const list: Action[] = [];
    if (parts.tag.trim()) list.push({ type: "tag", value: parts.tag.trim() });
    list.push(...parts.attributes.filter((a) => a.key.trim()));
    if (parts.handoff) list.push({ type: "handoff" });
    if (parts.mode !== "none") list.push({ type: parts.mode, text: parts.text });
    return list;
  }

  async function run(work: () => Promise<void>) {
    setError("");
    try {
      await work();
    } catch (e) {
      setError(e instanceof SyntaxError ? "The conditions aren't valid JSON." : (e as Error).message);
    }
  }

  const save = () =>
    run(async () => {
      const body = { ...d, conditions: conditions(), actions: actions() };
      if (d.id) await api(`${base}/${d.id}`, { method: "PUT", body });
      else await api(base, { method: "POST", body });
      onDone();
    });

  const tryIt = () =>
    run(async () => setBacktest(await api<Backtest>(`${base}/backtest`, { method: "POST", body: { conditions: conditions() } })));

  async function remove() {
    if (!d.id || !window.confirm(`Delete the rule "${d.name}"?`)) return;
    await api(`${base}/${d.id}`, { method: "DELETE" });
    onDone();
  }

  return (
    <div className="space-y-5 rounded-lg border border-primary/30 bg-primary-soft/40 p-5 shadow-sm">
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
        <legend className="mb-2 text-sm font-semibold">When</legend>
        {group ? (
          <ConditionRows group={group} onChange={setGroup} />
        ) : (
          <Field label="Conditions (JSON)" hint="This rule nests groups, which the row editor can't show. Edit the tree directly.">
            <textarea className={clsx(inputClass, "min-h-40 font-mono text-xs")} value={json} onChange={(e) => setJson(e.target.value)} />
          </Field>
        )}
        <div className="flex items-center gap-3">
          <Button variant="secondary" onClick={tryIt}>
            <FlaskConical size={16} /> Try on recent messages
          </Button>
          {backtest && (
            <span className="text-sm text-muted-foreground">
              Matches <b className="text-foreground">{backtest.matched}</b> of the last {backtest.checked} visitor messages.
            </span>
          )}
        </div>
        {backtest && backtest.samples.length > 0 && (
          <ul className="divide-y rounded-lg border bg-surface text-sm">
            {backtest.samples.map((sample) => (
              <li key={sample.message_id} className="flex gap-3 px-3 py-2">
                <span className="min-w-0 flex-1 truncate">{sample.text}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{ago(sample.created_at)} ago</span>
              </li>
            ))}
          </ul>
        )}
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="mb-2 text-sm font-semibold">Then</legend>
        <Segmented
          value={parts.mode}
          onChange={(mode) => setParts({ ...parts, mode })}
          options={[
            { value: "reply", label: "Send a fixed reply" },
            { value: "instruct", label: "Instruct the AI" },
            { value: "none", label: "Neither" },
          ]}
        />
        {parts.mode !== "none" && (
          <Field
            label={parts.mode === "reply" ? "Reply" : "Instruction for the AI"}
            hint={
              parts.mode === "reply"
                ? "Sent as is; the AI doesn't answer this message. Fills in {contact.name}, {conversation.KEY} and {message.data.KEY}."
                : "The AI still writes the answer, following this for this message only."
            }
          >
            <textarea
              className={clsx(inputClass, "min-h-20")}
              placeholder={parts.mode === "reply" ? "We're back at 9:00, {contact.name}." : "Apologise first, then check the order before answering."}
              value={parts.text}
              onChange={(e) => setParts({ ...parts, text: e.target.value })}
            />
          </Field>
        )}
        <Field label="Tag the conversation">
          <input className={inputClass} placeholder="billing" value={parts.tag} onChange={(e) => setParts({ ...parts, tag: e.target.value })} />
        </Field>
        <AttributeRows attributes={parts.attributes} onChange={(attributes) => setParts({ ...parts, attributes })} />
        <div className="space-y-2 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={parts.handoff} onChange={(e) => setParts({ ...parts, handoff: e.target.checked })} /> Hand off to a person
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={d.also_when_human} onChange={(e) => set({ also_when_human: e.target.checked })} /> Also run after a
            person took over
          </label>
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

function ConditionRows({ group, onChange }: { group: Group; onChange: (group: Group) => void }) {
  const update = (index: number, row: Row) => onChange({ ...group, rows: group.rows.map((r, i) => (i === index ? row : r)) });
  return (
    <div className="space-y-2">
      <Segmented
        value={group.match}
        onChange={(match) => onChange({ ...group, match })}
        options={[
          { value: "all", label: "All of these hold" },
          { value: "any", label: "Any of these holds" },
        ]}
      />
      {group.rows.map((row, index) => (
        <ConditionRow
          key={index}
          row={row}
          onChange={(next) => update(index, next)}
          onRemove={group.rows.length > 1 ? () => onChange({ ...group, rows: group.rows.filter((_, i) => i !== index) }) : undefined}
        />
      ))}
      <Button variant="ghost" onClick={() => onChange({ ...group, rows: [...group.rows, newRow()] })}>
        <Plus size={16} /> Add condition
      </Button>
    </div>
  );
}

function ConditionRow({ row, onChange, onRemove }: { row: Row; onChange: (row: Row) => void; onRemove?: () => void }) {
  const option = fieldOption(row.field);
  const keyed = option.id.endsWith(".");

  function changeField(id: string) {
    const next = newRow(id);
    // A keyed field ("contact.") starts with an empty key for the author to fill.
    onChange({ ...next, field: id });
  }

  return (
    <div className="flex flex-wrap items-start gap-2">
      <Select label="Field" className="w-56" value={option.id} options={FIELDS.map((f) => ({ value: f.id, label: f.label }))} onChange={changeField} />
      {keyed && (
        <input
          className={clsx(inputClass, "w-36 font-mono")}
          aria-label="Attribute name"
          placeholder="plan"
          value={row.field.slice(option.id.length)}
          onChange={(e) => onChange({ ...row, field: option.id + e.target.value.trim().toLowerCase() })}
        />
      )}
      <Select
        label="Operator"
        className="w-48"
        value={row.op}
        options={opsFor(row.field).map((op) => ({ value: op, label: opLabel(op) }))}
        onChange={(op) => onChange({ ...row, op })}
      />
      <ValueInput row={row} kind={option.kind} onChange={(value) => onChange({ ...row, value })} />
      {onRemove && (
        <Button variant="ghost" aria-label="Remove condition" onClick={onRemove}>
          <X size={16} />
        </Button>
      )}
    </div>
  );
}

function ValueInput({ row, kind, onChange }: { row: Row; kind: string; onChange: (value: string) => void }) {
  if (takesNoValue(row.op)) return null;
  if (kind === "boolean") {
    return (
      <Select
        label="Value"
        className="w-28"
        value={row.value === "false" ? "false" : "true"}
        options={[
          { value: "true", label: "yes" },
          { value: "false", label: "no" },
        ]}
        onChange={onChange}
      />
    );
  }
  if (kind === "weekday") {
    const chosen = new Set(row.value.split(/[\n,]/).map((day) => day.trim()).filter(Boolean));
    const toggle = (day: string) => {
      if (chosen.has(day)) chosen.delete(day);
      else chosen.add(day);
      onChange(WEEKDAYS.filter((d) => chosen.has(d)).join("\n"));
    };
    return (
      <div className="flex gap-1">
        {WEEKDAYS.map((day) => (
          <button
            key={day}
            type="button"
            onClick={() => toggle(day)}
            className={clsx("rounded-md px-2 py-1.5 text-xs capitalize ring-1 ring-border", chosen.has(day) ? "bg-primary text-white" : "bg-surface")}
          >
            {day}
          </button>
        ))}
      </div>
    );
  }
  if (takesList(row.op)) {
    return (
      <textarea
        className={clsx(inputClass, "min-h-16 min-w-48 flex-1")}
        aria-label="Values"
        placeholder={"refund\nmoney back"}
        value={row.value}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <input
      className={clsx(inputClass, "min-w-40 flex-1")}
      aria-label="Value"
      type={kind === "number" ? "number" : "text"}
      value={row.value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function AttributeRows({ attributes, onChange }: { attributes: AttributeAction[]; onChange: (attributes: AttributeAction[]) => void }) {
  const update = (index: number, patch: Partial<AttributeAction>) => onChange(attributes.map((a, i) => (i === index ? { ...a, ...patch } : a)));
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">Remember something</p>
      {attributes.map((attribute, index) => (
        <div key={index} className="flex flex-wrap items-center gap-2">
          <Select
            label="Scope"
            className="w-48"
            value={attribute.scope}
            options={[
              { value: "conversation", label: "On the conversation" },
              { value: "contact", label: "On the visitor" },
            ]}
            onChange={(scope) => update(index, { scope })}
          />
          <input
            className={clsx(inputClass, "w-36 font-mono")}
            aria-label="Attribute name"
            placeholder="topic"
            value={attribute.key}
            onChange={(e) => update(index, { key: e.target.value.trim().toLowerCase() })}
          />
          <span className="text-sm text-muted-foreground">=</span>
          <input
            className={clsx(inputClass, "min-w-32 flex-1")}
            aria-label="Attribute value"
            placeholder="billing"
            value={String(attribute.value)}
            onChange={(e) => update(index, { value: e.target.value })}
          />
          <Button variant="ghost" aria-label="Remove attribute" onClick={() => onChange(attributes.filter((_, i) => i !== index))}>
            <X size={16} />
          </Button>
        </div>
      ))}
      <Button variant="ghost" onClick={() => onChange([...attributes, { type: "set_attribute", scope: "conversation", key: "", value: "" }])}>
        <Plus size={16} /> Set an attribute
      </Button>
      <p className="text-xs text-muted-foreground">
        Later rules can test it (Conversation attribute… is …), so rules build on each other across messages.
      </p>
    </div>
  );
}
