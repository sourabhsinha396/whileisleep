"use client";

import clsx from "clsx";
import { Plug, Plus, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { McpServers } from "@/components/mcp-servers";
import { Select } from "@/components/select";
import { Badge, Button, ErrorText, Field, inputClass, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Tool } from "@/lib/api";
import { rowsToSchema, schemaToRows, urlPlaceholders, type InputRow, type InputType } from "@/lib/tool-schema";
import { usePoll } from "@/lib/use-poll";

const EMPTY: ToolDraft = { name: "", description: "", method: "GET", url: "", inputs: [], headers: [], enabled: true };

const METHODS = (["GET", "POST"] as const).map((value) => ({ value, label: value }));
const INPUT_TYPES = (["string", "integer", "number", "boolean"] satisfies InputType[]).map((value) => ({ value, label: value }));

interface ToolDraft {
  id?: number;
  name: string;
  description: string;
  method: "GET" | "POST";
  url: string;
  inputs: InputRow[];
  headers: { key: string; value: string }[];
  savedHeaderNames?: string[];
  enabled: boolean;
}

export default function ToolsPage() {
  const { workspace } = useWorkspace();
  const canEdit = workspace.role === "owner";
  const base = `/workspaces/${workspace.id}/tools`;
  const { data, reload } = usePoll(useCallback(() => api<Tool[]>(base), [base]), 60000);
  const [draft, setDraft] = useState<ToolDraft | null>(null);

  function edit(tool: Tool) {
    setDraft({
      id: tool.id,
      name: tool.name,
      description: tool.description,
      method: tool.method,
      url: tool.url,
      inputs: schemaToRows(tool.input_schema),
      headers: [],
      savedHeaderNames: tool.header_names,
      enabled: tool.enabled,
    });
  }

  /** Turning an MCP tool on approves its definition as the server sends it now. */
  async function approve(tool: Tool, enabled: boolean) {
    await api(`${base}/${tool.id}/approve`, { method: "POST", body: { enabled } });
    reload();
  }

  return (
    <>
      <PageHeader title="Tools" docs="tools" description="APIs on your own systems the agent can call to look things up.">
        {canEdit && (
          <Button onClick={() => setDraft({ ...EMPTY })}>
            <Plus size={16} /> Add tool
          </Button>
        )}
      </PageHeader>
      <div className="mx-auto max-w-4xl space-y-4 p-8">
        <p className="text-sm text-muted-foreground">
          The agent calls these for live data, like product search, stock or order status. It decides when from the description, so say what
          each one returns and when to use it.
        </p>

        <ul className="divide-y overflow-hidden rounded-lg border bg-surface shadow-sm">
          <BuiltIn name="search_knowledge_base" text="Searches your published articles." />
          <BuiltIn name="handoff_to_human" text="Flags the conversation for your team and pauses the agent." />
          {(data ?? []).map((tool) => (
            <li key={tool.id} className="flex items-center gap-3 px-4 py-3">
              <Plug size={16} className={isOn(tool) ? "text-primary-text" : "text-muted-foreground/50"} />
              <div className="min-w-0 flex-1">
                <p className="font-mono text-sm font-semibold">{tool.name}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {tool.mcp_server_id ? tool.description : `${tool.method} ${tool.url}`}
                </p>
              </div>
              {tool.mcp_server_id !== null && !tool.read_only && <Badge tone="warning">Can change data</Badge>}
              {tool.enabled && tool.needs_review && <Badge tone="danger">Changed: review</Badge>}
              {!tool.enabled && <span className="text-xs text-muted-foreground">Off</span>}
              {canEdit && tool.mcp_server_id === null && (
                <Button variant="secondary" onClick={() => edit(tool)}>
                  Edit
                </Button>
              )}
              {canEdit && tool.mcp_server_id !== null && (
                <Button variant="secondary" onClick={() => approve(tool, !isOn(tool))}>
                  {isOn(tool) ? "Turn off" : tool.enabled ? "Approve again" : "Turn on"}
                </Button>
              )}
            </li>
          ))}
        </ul>

        {draft && (
          <ToolEditor
            key={draft.id ?? "new"}
            initial={draft}
            base={base}
            onClose={() => setDraft(null)}
            onSaved={() => {
              reload();
            }}
          />
        )}

        <McpServers workspaceId={workspace.id} canEdit={canEdit} onChanged={reload} />
      </div>
    </>
  );
}

/** Offered to the agent: switched on and, for an MCP tool, approved as it is now. */
function isOn(tool: Tool): boolean {
  return tool.enabled && !tool.needs_review;
}

function BuiltIn({ name, text }: { name: string; text: string }) {
  return (
    <li className="flex items-center gap-3 bg-muted/60 px-4 py-3">
      <Plug size={16} className="text-success" />
      <div className="flex-1">
        <p className="font-mono text-sm font-semibold">{name}</p>
        <p className="text-xs text-muted-foreground">{text}</p>
      </div>
      <span className="text-xs text-muted-foreground">Built in</span>
    </li>
  );
}

function ToolEditor({ initial, base, onClose, onSaved }: { initial: ToolDraft; base: string; onClose: () => void; onSaved: () => void }) {
  const [d, setD] = useState<ToolDraft>(initial);
  const [error, setError] = useState("");
  const [testInputs, setTestInputs] = useState("{}");
  const [testResult, setTestResult] = useState<{ result: string; is_error: boolean } | null>(null);
  const missing = urlPlaceholders(d.url).filter((p) => !d.inputs.some((i) => i.name === p));

  function payload() {
    return {
      name: d.name,
      description: d.description,
      method: d.method,
      url: d.url,
      input_schema: rowsToSchema(d.inputs),
      headers: Object.fromEntries(d.headers.filter((h) => h.key.trim()).map((h) => [h.key.trim(), h.value])),
      enabled: d.enabled,
    };
  }

  async function save(): Promise<Tool | null> {
    setError("");
    try {
      const saved = d.id
        ? await api<Tool>(`${base}/${d.id}`, { method: "PUT", body: payload() })
        : await api<Tool>(base, { method: "POST", body: payload() });
      setD({ ...d, id: saved.id, headers: [], savedHeaderNames: saved.header_names });
      onSaved();
      return saved;
    } catch (e) {
      setError((e as Error).message);
      return null;
    }
  }

  async function test() {
    setTestResult(null);
    let inputs: unknown;
    try {
      inputs = JSON.parse(testInputs || "{}");
    } catch {
      setTestResult({ result: "Test inputs must be JSON, e.g. {\"q\": \"aws\"}", is_error: true });
      return;
    }
    const saved = await save();
    if (!saved) return;
    setTestResult(await api(`${base}/${saved.id}/test`, { method: "POST", body: { inputs } }));
  }

  async function remove() {
    if (!d.id || !window.confirm(`Delete the ${d.name} tool? The agent stops using it at once.`)) return;
    await api(`${base}/${d.id}`, { method: "DELETE" });
    onSaved();
    onClose();
  }

  const setInput = (i: number, patch: Partial<InputRow>) => setD({ ...d, inputs: d.inputs.map((row, j) => (i === j ? { ...row, ...patch } : row)) });

  return (
    <div className="space-y-4 rounded-lg border border-primary/30 bg-primary-soft/40 shadow-sm p-5">
      <h3 className="font-semibold">{d.id ? `Edit ${initial.name}` : "New tool"}</h3>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Name" hint="Lowercase with underscores, e.g. search_products.">
          <input className={clsx(inputClass, "font-mono")} value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} />
        </Field>
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input type="checkbox" checked={d.enabled} onChange={(e) => setD({ ...d, enabled: e.target.checked })} /> Enabled
        </label>
      </div>
      <Field label="Description (what the agent reads)" hint="Say what it returns and when to use it.">
        <textarea
          className={clsx(inputClass, "min-h-20")}
          placeholder="Searches our catalog of practice exams by code or name. Returns code, name, price and URL. Use it whenever someone asks whether we have an exam."
          value={d.description}
          onChange={(e) => setD({ ...d, description: e.target.value })}
        />
      </Field>
      <div className="grid grid-cols-[110px_1fr] gap-3">
        <Field label="Method">
          <Select value={d.method} options={METHODS} onChange={(method) => setD({ ...d, method })} />
        </Field>
        <Field label="URL" hint="{input} fills an input. {visitor.email}, {visitor.name} and {visitor.id} come from the visitor, never from the AI.">
          <input className={clsx(inputClass, "font-mono")} placeholder="https://api.example.com/products" value={d.url} onChange={(e) => setD({ ...d, url: e.target.value })} />
        </Field>
      </div>
      {missing.length > 0 && <p className="text-sm text-warning">Add an input named {missing.join(", ")} for the URL placeholder.</p>}

      <div>
        <p className="mb-1 text-sm font-medium">Inputs the agent fills</p>
        <p className="mb-2 text-xs text-muted-foreground">{d.method === "GET" ? "Sent as query parameters" : "Sent as a JSON body"}, except those used in the URL.</p>
        {d.inputs.map((row, i) => (
          <div key={i} className="mb-2 grid grid-cols-[140px_110px_1fr_auto_auto] items-center gap-2">
            <input aria-label="Input name" className={clsx(inputClass, "font-mono")} placeholder="q" value={row.name} onChange={(e) => setInput(i, { name: e.target.value })} />
            <Select label="Input type" value={row.type} options={INPUT_TYPES} onChange={(type) => setInput(i, { type })} />
            <input aria-label="Input description" className={inputClass} placeholder="What to put here" value={row.description} onChange={(e) => setInput(i, { description: e.target.value })} />
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={row.required} onChange={(e) => setInput(i, { required: e.target.checked })} /> required
            </label>
            <button aria-label="Remove input" className="text-muted-foreground hover:text-danger" onClick={() => setD({ ...d, inputs: d.inputs.filter((_, j) => j !== i) })}>
              <Trash2 size={16} />
            </button>
          </div>
        ))}
        <Button variant="ghost" onClick={() => setD({ ...d, inputs: [...d.inputs, { name: "", type: "string", description: "", required: false }] })}>
          <Plus size={15} /> Add input
        </Button>
      </div>

      <div>
        <p className="mb-1 text-sm font-medium">Headers (secret)</p>
        <p className="mb-2 text-xs text-muted-foreground">
          For API keys. Never shown to visitors or the AI.
          {d.savedHeaderNames?.length ? ` Saved: ${d.savedHeaderNames.join(", ")}. Leave empty to keep them; adding any replaces them all.` : ""}
        </p>
        {d.headers.map((h, i) => (
          <div key={i} className="mb-2 grid grid-cols-[200px_1fr_auto] gap-2">
            <input aria-label="Header name" className={clsx(inputClass, "font-mono")} placeholder="Authorization" value={h.key} onChange={(e) => setD({ ...d, headers: d.headers.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)) })} />
            <input aria-label="Header value" type="password" className={inputClass} placeholder="Bearer …" value={h.value} onChange={(e) => setD({ ...d, headers: d.headers.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)) })} />
            <button aria-label="Remove header" className="text-muted-foreground hover:text-danger" onClick={() => setD({ ...d, headers: d.headers.filter((_, j) => j !== i) })}>
              <Trash2 size={16} />
            </button>
          </div>
        ))}
        <Button variant="ghost" onClick={() => setD({ ...d, headers: [...d.headers, { key: "", value: "" }] })}>
          <Plus size={15} /> Add header
        </Button>
      </div>

      <ErrorText>{error}</ErrorText>
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={save}>Save tool</Button>
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
        {d.id && (
          <Button variant="danger" className="ml-auto" onClick={remove}>
            Delete
          </Button>
        )}
      </div>

      <div className="space-y-2 border-t border-primary/20 pt-4">
        <p className="text-sm font-medium">Try it</p>
        <div className="flex gap-2">
          <input aria-label="Test inputs as JSON" className={clsx(inputClass, "font-mono")} value={testInputs} onChange={(e) => setTestInputs(e.target.value)} />
          <Button variant="secondary" onClick={test}>
            Save &amp; test
          </Button>
        </div>
        {testResult && (
          <pre className={clsx("max-h-64 overflow-auto rounded-lg p-3 text-xs whitespace-pre-wrap", testResult.is_error ? "bg-danger-soft text-danger" : "bg-surface text-foreground")}>
            {testResult.result}
          </pre>
        )}
      </div>
    </div>
  );
}
