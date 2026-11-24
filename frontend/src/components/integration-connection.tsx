"use client";

import { Copy, Eye, EyeOff, RotateCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { PluginFields, PluginIcon } from "@/components/plugin-fields";
import { Badge, Button, ErrorText, Notice, Spinner } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type ConnectionDetail, type Delivery, type IntegrationDetail } from "@/lib/api";
import { ago } from "@/lib/format";
import { complete, initialValues, run, statusOf, type Values } from "@/lib/integrations";
import { useConnect } from "@/lib/use-connect";
import { usePoll } from "@/lib/use-poll";

type Options = Record<string, { value: string; label: string }[]>;

interface Props {
  integration: IntegrationDetail;
  connection: ConnectionDetail;
  /** The integration's address in the API. */
  path: string;
  onChanged: () => Promise<void>;
}

/** One connection: its settings, what to copy into the service, and what was sent lately. */
export function IntegrationConnection({ integration, connection, path, onChanged }: Props) {
  const { workspace } = useWorkspace();
  const base = `${path}/${connection.id}`;
  const status = statusOf(integration.available, connection);
  const { options, error: optionsError } = useOptions(integration, base, connection.last_error);
  const [values, setValues] = useState<Values>(initialValues(integration.settings_fields, connection.settings));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const reconnect = useConnect(path, onChanged);

  async function work(action: () => Promise<unknown>, note = "") {
    setBusy(true);
    setMessage("");
    setError("");
    try {
      await action();
      await onChanged();
      setMessage(note);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function save(e: React.FormEvent) {
    e.preventDefault();
    work(async () => {
      await run(base, { method: "PUT", body: { values } });
      // Typed secrets are saved now; they shouldn't stay on the page.
      const secrets = integration.settings_fields.filter((field) => field.kind === "secret");
      setValues((now) => ({ ...now, ...Object.fromEntries(secrets.map((field) => [field.name, ""])) }));
    }, "Saved.");
  }

  function disconnect() {
    const question = `Disconnect ${connection.account_name} from ${workspace.name}?`;
    if (window.confirm(question)) work(() => api(base, { method: "DELETE" }));
  }

  const fields = integration.settings_fields.map((field) => (field.kind === "select" ? { ...field, options: options?.[field.name] ?? [] } : field));
  return (
    <section className="space-y-5 rounded-lg border bg-surface p-6 shadow-sm">
      <div className="flex items-center gap-3">
        <PluginIcon svg={integration.icon} size={32} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold">{connection.account_name}</p>
          <p className="text-sm text-muted-foreground">{integration.name}</p>
        </div>
        <Badge tone={status.tone}>{status.label}</Badge>
      </div>
      {connection.last_error && <Notice tone="danger">{connection.last_error}</Notice>}
      {connection.shown.map((item) => (
        <Shown key={item.label} {...item} />
      ))}

      <form onSubmit={save} className="space-y-5">
        {options || optionsError ? (
          !optionsError && <PluginFields id={`${connection.id}-`} fields={fields} values={values} onChange={setValues} secrets={connection.secrets} />
        ) : (
          <Spinner label={`Asking ${integration.name}…`} />
        )}
        <ErrorText>{optionsError}</ErrorText>
        <div className="flex flex-wrap items-center gap-2 border-t pt-5">
          {options && (
            <Button disabled={busy || !complete(integration.settings_fields, values, connection.secrets)}>
              {busy ? "Working…" : integration.save_label}
            </Button>
          )}
          {integration.has_page && integration.available && (connection.last_error || optionsError) && (
            <Button type="button" variant="secondary" disabled={reconnect.busy} onClick={() => reconnect.connect()}>
              Connect again
            </Button>
          )}
          <Button type="button" variant="danger" disabled={busy} onClick={disconnect}>
            Disconnect
          </Button>
          <span role="status" className="text-sm text-success">
            {message}
          </span>
        </div>
        <ErrorText>{error || reconnect.error}</ErrorText>
      </form>
      {integration.keeps_log && <Log base={base} />}
    </section>
  );
}

/** What each dropdown offers. The server asks the service, which may take a moment. */
function useOptions(integration: IntegrationDetail, base: string, lastError: string) {
  const needed = integration.settings_fields.some((field) => field.kind === "select");
  const [options, setOptions] = useState<Options | null>(needed ? null : {});
  const [error, setError] = useState("");
  useEffect(() => {
    if (!needed) return;
    let gone = false;
    run<{ options: Options }>(`${base}/options`, { method: "POST" })
      .then((result) => !gone && (setOptions(result.options), setError("")))
      .catch((e: Error) => !gone && setError(e.message));
    return () => {
      gone = true;
    };
    // Asked again once what was wrong has been put right.
  }, [needed, base, lastError]);
  return { options, error };
}

function Shown({ label, value, secret, help }: ConnectionDetail["shown"][number]) {
  const [visible, setVisible] = useState(!secret);
  return (
    <div>
      <p className="mb-1.5 text-sm font-medium">{label}</p>
      <div className="flex gap-2">
        <code className="block min-w-0 flex-1 overflow-x-auto rounded-md border bg-muted px-3 py-2 text-xs whitespace-nowrap">
          {visible ? value : "•".repeat(24)}
        </code>
        {secret && (
          <Button type="button" variant="secondary" size="sm" aria-label={visible ? `Hide ${label}` : `Show ${label}`} onClick={() => setVisible(!visible)}>
            {visible ? <EyeOff size={14} /> : <Eye size={14} />}
          </Button>
        )}
        <Button type="button" variant="secondary" size="sm" aria-label={`Copy ${label}`} onClick={() => navigator.clipboard.writeText(value)}>
          <Copy size={14} />
        </Button>
      </div>
      {help && <p className="mt-1.5 text-xs text-muted-foreground">{help}</p>}
    </div>
  );
}

const TONES = { sent: "success", failed: "danger", pending: "warning" } as const;
const LABELS = { sent: "Sent", failed: "Failed", pending: "Waiting" } as const;

function Log({ base }: { base: string }) {
  const { workspace } = useWorkspace();
  const { data, reload } = usePoll(useCallback(() => api<Delivery[]>(`${base}/deliveries`), [base]), 10000);
  const [error, setError] = useState("");

  async function again(delivery: Delivery) {
    setError("");
    try {
      await api(`${base}/deliveries/${delivery.id}/again`, { method: "POST" });
      await reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <details className="border-t pt-4">
      <summary className="cursor-pointer text-sm font-medium">Sent lately</summary>
      <ErrorText>{error}</ErrorText>
      {data && !data.length && <p className="mt-3 text-sm text-muted-foreground">Nothing in the last 7 days.</p>}
      <ul className="mt-3 divide-y text-sm">
        {(data ?? []).map((delivery) => (
          <li key={delivery.id} className="flex items-center gap-3 py-2">
            <Badge tone={TONES[delivery.status]}>{LABELS[delivery.status]}</Badge>
            <span className="min-w-0 flex-1">
              <Link href={`/w/${workspace.slug}/inbox?c=${delivery.conversation_id}`} className="hover:underline">
                {delivery.event}
              </Link>
              <span className="block truncate text-xs text-muted-foreground">
                {ago(delivery.created_at)} · {delivery.detail || "On its way"}
              </span>
            </span>
            {delivery.status !== "pending" && (
              <Button type="button" variant="ghost" size="sm" onClick={() => again(delivery)}>
                <RotateCw size={13} /> Send again
              </Button>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
