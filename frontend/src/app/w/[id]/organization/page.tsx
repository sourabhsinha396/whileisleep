"use client";

import clsx from "clsx";
import { CheckCircle2, KeyRound, XCircle } from "lucide-react";
import { useCallback, useState } from "react";
import { Button, ErrorText, Field, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type KeyCheck, type Organization } from "@/lib/api";
import { usePoll } from "@/lib/use-poll";

/** Your organization: its name and the OpenRouter key and model every workspace's AI agent uses. */
export default function OrganizationPage() {
  const { data: org, setData } = usePoll(useCallback(() => api<Organization>("/organization"), []), 60000);
  if (!org) return null;
  return (
    <>
      <PageHeader title="Organization & LLM" />
      <div className="mx-auto max-w-3xl space-y-8 p-8">
        <LlmSettings key={org.id} org={org} onSaved={setData} />
        <NameForm org={org} onSaved={setData} />
      </div>
    </>
  );
}

function LlmSettings({ org, onSaved }: { org: Organization; onSaved: (org: Organization) => void }) {
  const { reload } = useWorkspace();
  const [key, setKey] = useState("");
  const [model, setModel] = useState(org.llm_model);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [check, setCheck] = useState<KeyCheck | null>(null);
  const models = usePoll(useCallback(() => api<{ id: string; name: string }[]>("/organization/models"), []), 3600000);

  async function save(body: { openrouter_api_key?: string; llm_model?: string }, note: string) {
    setError("");
    setMessage("");
    try {
      const saved = await api<Organization>("/organization", { method: "PATCH", body });
      onSaved(saved);
      setKey("");
      setMessage(note);
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function runCheck() {
    setCheck(null);
    setCheck(await api<KeyCheck>("/organization/check-key", { method: "POST" }));
  }

  const known = models.data?.some((m) => m.id === model.trim());

  return (
    <section className="space-y-5 rounded-xl border border-gray-200 bg-white p-6">
      <div>
        <h2 className="text-lg font-semibold">AI model (OpenRouter)</h2>
        <p className="mt-1 text-sm text-gray-600">
          Every workspace in <strong>{org.name}</strong> ({org.workspace_count}) answers visitors with this key and model. Create a key at{" "}
          <a className="text-brand hover:underline" href="https://openrouter.ai/keys" target="_blank" rel="noreferrer">
            openrouter.ai/keys
          </a>
          ; usage is billed to that OpenRouter account.
        </p>
      </div>

      <div
        className={clsx(
          "flex items-center gap-2 rounded-lg px-3 py-2 text-sm",
          org.llm_ready ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-800",
        )}
      >
        {org.llm_ready ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
        {org.llm_ready
          ? `Ready: ${org.llm_model}`
          : !org.has_openrouter_key
            ? "Add a key and pick a model. Until then the agent only matches help articles by keyword."
            : "Pick a model to finish."}
      </div>

      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (key.trim()) save({ openrouter_api_key: key.trim() }, "Key saved.");
        }}
      >
        <Field
          label="API key"
          hint={org.has_openrouter_key ? `A key ending ${org.key_hint || "(short)"} is saved. Paste a new one to replace it.` : "Stored on the server; never shown again."}
        >
          <div className="flex gap-2">
            <input
              className={clsx(inputClass, "font-mono")}
              type="password"
              autoComplete="off"
              placeholder={org.has_openrouter_key ? `•••••••• ${org.key_hint}` : "sk-or-v1-…"}
              value={key}
              onChange={(e) => setKey(e.target.value)}
            />
            <Button disabled={!key.trim()}>
              <KeyRound size={15} /> Save key
            </Button>
          </div>
        </Field>
        {org.has_openrouter_key && (
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="secondary" onClick={runCheck}>
              Test key
            </Button>
            <Button
              type="button"
              variant="danger"
              onClick={() => window.confirm("Remove the key? The agent falls back to keyword answers.") && save({ openrouter_api_key: "" }, "Key removed.")}
            >
              Remove key
            </Button>
            {check && (
              <span className={clsx("text-sm", check.ok ? "text-green-700" : "text-red-700")}>
                {check.message}
                {check.ok && check.limit_remaining !== null && ` ${check.limit_remaining} credits left on this key.`}
              </span>
            )}
          </div>
        )}
      </form>

      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          save({ llm_model: model.trim() }, "Model saved.");
        }}
      >
        <Field label="Model" hint="An OpenRouter model id that supports tool calling, e.g. one from openrouter.ai/models.">
          <div className="flex gap-2">
            <input
              className={clsx(inputClass, "font-mono")}
              list="openrouter-models"
              placeholder="provider/model"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            />
            <Button disabled={model.trim() === org.llm_model}>Save model</Button>
          </div>
        </Field>
        <datalist id="openrouter-models">
          {(models.data ?? []).map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
        </datalist>
        {models.error && <p className="text-xs text-gray-500">Couldn&apos;t load the model list ({models.error}). You can still type an id.</p>}
        {model.trim() && models.data && !known && <p className="text-xs text-amber-700">Not in OpenRouter&apos;s list of tool-capable models.</p>}
      </form>

      <p className="text-sm text-green-700">{message}</p>
      <ErrorText>{error}</ErrorText>
    </section>
  );
}

function NameForm({ org, onSaved }: { org: Organization; onSaved: (org: Organization) => void }) {
  const [name, setName] = useState(org.name);
  const [saved, setSaved] = useState(false);
  return (
    <form
      className="space-y-3 rounded-xl border border-gray-200 bg-white p-6"
      onSubmit={async (e) => {
        e.preventDefault();
        onSaved(await api<Organization>("/organization", { method: "PATCH", body: { name } }));
        setSaved(true);
      }}
    >
      <h2 className="text-lg font-semibold">Organization</h2>
      <Field label="Name">
        <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <div className="flex items-center gap-3">
        <Button>Save</Button>
        {saved && <span className="text-sm text-green-700">Saved.</span>}
      </div>
    </form>
  );
}
