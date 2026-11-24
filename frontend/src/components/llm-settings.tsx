"use client";

import clsx from "clsx";
import { CheckCircle2, KeyRound, XCircle } from "lucide-react";
import { useCallback, useState } from "react";
import { ModelPicker } from "@/components/model-picker";
import { Select } from "@/components/select";
import { Badge, Button, Card, ErrorText, inputClass } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type KeyCheck, type LlmModel, type LlmProvider, type Organization, type ProviderId } from "@/lib/api";
import { KEY_EXAMPLES, keyRemovalWarning, llmStatus, matchingModels, MODEL_EXAMPLES, providerOf } from "@/lib/llm";
import { usePoll } from "@/lib/use-poll";

type Request = { path: string; method: string; body?: unknown };

export function LlmSettings({ org, onSaved }: { org: Organization; onSaved: (org: Organization) => void }) {
  const { reload } = useWorkspace();
  const status = llmStatus(org);

  /** Sends a change; everything on the page then shows the organization as saved. */
  async function save({ path, method, body }: Request) {
    onSaved(await api<Organization>(path, { method, body }));
    await reload();
  }

  return (
    <div className="space-y-6">
      <div
        role="status"
        className={clsx(
          "flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm",
          status.ok ? "bg-success-soft text-success" : "bg-warning-soft text-warning",
        )}
      >
        {status.ok ? <CheckCircle2 size={16} className="mt-0.5 shrink-0" /> : <XCircle size={16} className="mt-0.5 shrink-0" />}
        {status.text}
      </div>

      <Card
        title="API keys"
        description={
          <>
            Every workspace in <strong>{org.name}</strong> ({org.workspace_count}) uses these, and each provider bills your account with them
            directly. You only need the ones you use.
          </>
        }
      >
        <ul className="divide-y">
          {org.providers.map((provider) => (
            <KeyRow key={provider.id} org={org} provider={provider} save={save} />
          ))}
        </ul>
      </Card>

      <Card title="Model" description="Writes every answer. It must support tool calling.">
        <ModelForm
          org={org}
          label="model"
          provider={org.llm_provider}
          model={org.llm_model}
          onSave={(provider, model) => save({ path: "/organization", method: "PATCH", body: { llm_provider: provider, llm_model: model } })}
        />
      </Card>

      <Card
        title="Fallback"
        description="Takes over a reply when the model above fails: its provider is down, the key stops working or the credits run out. Pick another provider, so one outage can't take both."
      >
        <ModelForm
          org={org}
          label="fallback"
          optional
          provider={org.fallback_provider}
          model={org.fallback_model}
          onSave={(provider, model) =>
            save({ path: "/organization", method: "PATCH", body: { fallback_provider: provider, fallback_model: provider && model } })
          }
        />
      </Card>
    </div>
  );
}

/** Runs one thing at a time and keeps what it said, good or bad. */
function useAction() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function run(work: () => Promise<string>) {
    setBusy(true);
    setMessage("");
    setError("");
    try {
      setMessage(await work());
    } catch (e) {
      setError((e as Error).message);
    }
    setBusy(false);
  }

  return { busy, message, error, run };
}

function KeyRow({ org, provider, save }: { org: Organization; provider: LlmProvider; save: (request: Request) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [key, setKey] = useState("");
  const { busy, message, error, run } = useAction();
  const path = `/organization/keys/${provider.id}`;

  const saveKey = () =>
    run(async () => {
      await save({ path, method: "PUT", body: { api_key: key.trim() } });
      setKey("");
      setEditing(false);
      return "Key saved.";
    });

  const test = () =>
    run(async () => {
      const check = await api<KeyCheck>(`${path}/check`, { method: "POST" });
      if (!check.ok) throw new Error(check.message);
      return check.limit_remaining === null ? check.message : `${check.message} ${check.limit_remaining} credits left on it.`;
    });

  function remove() {
    if (!window.confirm(keyRemovalWarning(org, provider))) return;
    run(async () => {
      await save({ path, method: "DELETE" });
      return "Key removed.";
    });
  }

  return (
    <li className="space-y-3 py-3.5 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold">{provider.name}</span>
        {provider.has_key ? <Badge tone="success">Key {provider.key_hint || "saved"}</Badge> : <Badge>No key</Badge>}
        <div className="ml-auto flex flex-wrap gap-2">
          {provider.has_key && (
            <>
              <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={test}>
                Test
              </Button>
              <Button type="button" size="sm" variant="ghost" disabled={busy} onClick={remove}>
                Remove
              </Button>
            </>
          )}
          <Button type="button" size="sm" variant="secondary" aria-expanded={editing} onClick={() => setEditing(!editing)}>
            {editing ? "Cancel" : provider.has_key ? "Replace" : "Add key"}
          </Button>
        </div>
      </div>
      {editing && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (key.trim()) saveKey();
          }}
        >
          <div className="flex gap-2">
            <input
              autoFocus
              aria-label={`${provider.name} API key`}
              className={clsx(inputClass, "font-mono")}
              type="password"
              autoComplete="off"
              placeholder={KEY_EXAMPLES[provider.id]}
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
            <Button disabled={busy || !key.trim()}>
              <KeyRound size={15} /> Save key
            </Button>
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground">
            Make one at{" "}
            <a className="text-primary-text hover:underline" href={provider.keys_url} target="_blank" rel="noreferrer">
              {provider.keys_url.replace("https://", "")}
            </a>
            . It is stored encrypted and never shown again.
          </p>
        </form>
      )}
      {message && <p className="text-sm text-success">{message}</p>}
      <ErrorText>{error}</ErrorText>
    </li>
  );
}

interface ModelFormProps {
  org: Organization;
  /** What is being picked, for screen readers: "model" or "fallback". */
  label: string;
  /** Offers "None". */
  optional?: boolean;
  provider: ProviderId | "";
  model: string;
  onSave: (provider: ProviderId | "", model: string) => Promise<void>;
}

function ModelForm({ org, label, optional = false, ...saved }: ModelFormProps) {
  const [provider, setProvider] = useState(saved.provider);
  const [model, setModel] = useState(saved.model);
  const { busy, message, error, run } = useAction();
  const chosen = providerOf(org, provider);
  const unchanged = provider === saved.provider && (model.trim() === saved.model || !provider);

  function changeProvider(next: ProviderId | "") {
    setProvider(next);
    // Another provider's id would mean nothing here.
    setModel(next === saved.provider ? saved.model : "");
  }

  return (
    <form
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        run(async () => {
          await saved.onSave(provider, model.trim());
          return provider ? "Saved." : "Fallback removed.";
        });
      }}
    >
      <div className="flex flex-wrap items-start gap-2 sm:flex-nowrap">
        <Select<ProviderId | "">
          label={`Provider of the ${label}`}
          className="w-full sm:w-48"
          value={provider}
          options={[
            ...(optional ? [{ value: "" as const, label: "None" }] : []),
            ...org.providers.map((p) => ({ value: p.id, label: p.name, note: p.has_key ? undefined : "no key" })),
          ]}
          onChange={changeProvider}
        />
        {chosen && <ModelInput key={`${chosen.id} ${chosen.key_hint}`} provider={chosen} label={label} value={model} onChange={setModel} />}
        <Button disabled={busy || unchanged || Boolean(provider && !model.trim())}>Save</Button>
      </div>
      {chosen && !chosen.has_key && <p className="text-xs text-warning">Add your {chosen.name} key above to use it.</p>}
      {message && <p className="text-sm text-success">{message}</p>}
      <ErrorText>{error}</ErrorText>
    </form>
  );
}

/** A model id, with the recommended ones to pick from. Any other can be typed. */
function ModelInput({ provider, label, value, onChange }: { provider: LlmProvider; label: string; value: string; onChange: (model: string) => void }) {
  // Only OpenRouter shows its models to anyone.
  const listed = provider.has_key || provider.id === "openrouter";
  const load = useCallback(async () => (listed ? api<LlmModel[]>(`/organization/models/${provider.id}`) : []), [listed, provider.id]);
  const models = usePoll(load, 3600000);
  const offered = (models.data ?? []).filter((m) => m.recommended);
  // Not while what is typed still leads to one of them.
  const unknown =
    listed && value.trim() && models.data && !models.data.some((m) => m.id === value.trim()) && !matchingModels(offered, value).length;

  return (
    <div className="min-w-0 flex-1">
      <ModelPicker
        label={`The ${label}'s id`}
        models={offered}
        placeholder={MODEL_EXAMPLES[provider.id]}
        value={value}
        onChange={onChange}
      />
      {models.error && <p className="mt-1.5 text-xs text-muted-foreground">Couldn&apos;t load the model list. {models.error} You can still type an id.</p>}
      {unknown && <p className="mt-1.5 text-xs text-warning">Not in {provider.name}&apos;s list of models that fit.</p>}
    </div>
  );
}
