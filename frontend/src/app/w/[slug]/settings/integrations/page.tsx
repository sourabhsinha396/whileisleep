"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useCallback } from "react";
import { PluginIcon } from "@/components/plugin-fields";
import { Badge, EmptyState, ErrorText, Notice, PageHeader, Spinner } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Integration } from "@/lib/api";
import { summaryOf } from "@/lib/integrations";
import { usePoll } from "@/lib/use-poll";

export default function IntegrationsPage() {
  const { workspace } = useWorkspace();
  return (
    <>
      <PageHeader title="Integrations" description="Connect the tools your team already uses." />
      <div className="mx-auto max-w-3xl p-8">
        {workspace.role === "owner" ? <List /> : <Notice>Only the workspace&apos;s owners can change this.</Notice>}
      </div>
    </>
  );
}

function List() {
  const { workspace } = useWorkspace();
  const { data, error } = usePoll(
    useCallback(() => api<Integration[]>(`/workspaces/${workspace.id}/integrations`), [workspace.id]),
    60000,
  );
  if (!data) return error ? <ErrorText>{error}</ErrorText> : <Spinner />;
  if (!data.length) return <EmptyState title="No integrations on this server" />;
  return (
    <ul className="divide-y overflow-hidden rounded-lg border bg-surface shadow-sm">
      {data.map((integration) => {
        const status = summaryOf(integration);
        const names = integration.connections.map((connection) => connection.account_name).join(", ");
        return (
          <li key={integration.plugin}>
            <Link
              href={`/w/${workspace.slug}/settings/integrations/${integration.plugin}`}
              className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-muted/60"
            >
              <PluginIcon svg={integration.icon} />
              <span className="min-w-0 flex-1">
                <span className="block font-semibold">{integration.name}</span>
                <span className="block truncate text-sm text-muted-foreground">{names ? `Connected to ${names}` : integration.description}</span>
              </span>
              {status && <Badge tone={status.tone}>{status.label}</Badge>}
              <ChevronRight size={16} aria-hidden className="shrink-0 text-muted-foreground" />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
