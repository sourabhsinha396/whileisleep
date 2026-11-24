"use client";

import { ArrowLeft, Plus } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useState } from "react";
import { IntegrationConnection } from "@/components/integration-connection";
import { PluginFields, PluginIcon } from "@/components/plugin-fields";
import { Button, ErrorText, Notice, PageHeader, Spinner } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type IntegrationDetail } from "@/lib/api";
import { complete, initialValues, type Values } from "@/lib/integrations";
import { useConnect } from "@/lib/use-connect";
import { usePoll } from "@/lib/use-poll";

/** One integration: connect it, choose its settings, disconnect it. The plugin says what to ask for. */
export default function IntegrationPage() {
  const { workspace } = useWorkspace();
  const { plugin } = useParams<{ plugin: string }>();
  const path = `/workspaces/${workspace.id}/integrations/${plugin}`;
  const owner = workspace.role === "owner";
  const { data, error, reload } = usePoll(
    useCallback(async () => (owner ? api<IntegrationDetail>(path) : null), [owner, path]),
    60000,
  );
  return (
    <>
      <PageHeader title={data?.name ?? "Integration"} description={data?.description}>
        <Link
          href={`/w/${workspace.slug}/settings/integrations`}
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={15} /> All integrations
        </Link>
      </PageHeader>
      <div className="mx-auto max-w-3xl space-y-5 p-8">
        {!owner && <Notice>Only the workspace&apos;s owners can change this.</Notice>}
        {owner && !data && (error ? <ErrorText>{error}</ErrorText> : <Spinner />)}
        {data && (
          <>
            {data.notice && <p className="text-sm text-muted-foreground">{data.notice}</p>}
            {data.connections.map((connection) => (
              <IntegrationConnection key={connection.id} integration={data} connection={connection} path={path} onChanged={reload} />
            ))}
            {(data.many || !data.connections.length) && <Connect integration={data} path={path} onChanged={reload} />}
          </>
        )}
      </div>
    </>
  );
}

function Connect({ integration, path, onChanged }: { integration: IntegrationDetail; path: string; onChanged: () => Promise<void> }) {
  const first = !integration.connections.length;
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Values>(initialValues(integration.connect_fields));
  const { connect, busy, error } = useConnect(path, async () => {
    setValues(initialValues(integration.connect_fields));
    setOpen(false);
    await onChanged();
  });

  if (!integration.available) {
    return (
      <Notice>
        Whoever runs this server has to set up {integration.name} first. Missing in its settings: {integration.missing_options.join(", ")}.
      </Notice>
    );
  }
  if (!first && !open) {
    return (
      <Button variant="secondary" onClick={() => setOpen(true)}>
        <Plus size={16} /> Add another
      </Button>
    );
  }
  return (
    <form
      className="space-y-5 rounded-lg border bg-surface p-6 shadow-sm"
      onSubmit={(e) => {
        e.preventDefault();
        connect(values);
      }}
    >
      {first && (
        <div className="flex items-center gap-3">
          <PluginIcon svg={integration.icon} size={32} />
          <div>
            <p className="font-semibold">{integration.name}</p>
            <p className="text-sm text-muted-foreground">Not connected</p>
          </div>
        </div>
      )}
      <PluginFields id="new-" fields={integration.connect_fields} values={values} onChange={setValues} />
      <div className="flex items-center gap-2">
        <Button disabled={busy || !complete(integration.connect_fields, values)}>{busy ? "Connecting…" : `Connect ${integration.name}`}</Button>
        {!first && (
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        )}
      </div>
      <ErrorText>{error}</ErrorText>
    </form>
  );
}
