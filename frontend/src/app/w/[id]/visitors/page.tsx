"use client";

import { Eye, MessageSquare, Search, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { Avatar, Button, EmptyState, PageHeader, Segmented } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type ConversationRow, type Visitor } from "@/lib/api";
import { ago, browserName } from "@/lib/format";
import { usePoll } from "@/lib/use-poll";

type Range = "online" | "week";

export default function VisitorsPage() {
  const { workspace } = useWorkspace();
  const router = useRouter();
  const [range, setRange] = useState<Range>("online");
  const [query, setQuery] = useState("");
  const onlineOnly = range === "online";
  const { data } = usePoll(
    useCallback(() => api<Visitor[]>(`/workspaces/${workspace.id}/visitors?online=${onlineOnly}`), [workspace.id, onlineOnly]),
    5000,
  );

  async function message(visitor: Visitor) {
    const body = window.prompt(`Message ${visitor.name}:`, "Hi! Can I help you find anything?");
    if (!body) return;
    const row = await api<ConversationRow>(`/workspaces/${workspace.id}/visitors/${visitor.id}/conversations`, {
      method: "POST",
      body: { body },
    });
    router.push(`/w/${workspace.id}/inbox?c=${row.id}`);
  }

  const all = data ?? [];
  const q = query.trim().toLowerCase();
  const rows = q ? all.filter((v) => [v.name, v.email, v.page_title, v.current_url].some((s) => s?.toLowerCase().includes(q))) : all;
  const online = all.filter((v) => v.online).length;
  const chatting = all.filter((v) => v.conversation_id).length;

  return (
    <>
      <PageHeader
        title="Visitors"
        description={
          <span className="inline-flex items-center gap-1.5">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-success opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-success" />
            </span>
            Live, refreshes every few seconds
          </span>
        }
      >
        <Segmented
          value={range}
          onChange={setRange}
          options={[
            { value: "online", label: "Online now" },
            { value: "week", label: "Last 7 days" },
          ]}
        />
      </PageHeader>
      <div className="space-y-6 p-8">
        <div className="grid gap-4 sm:grid-cols-3">
          <Stat icon={Eye} label={onlineOnly ? "Online now" : "Online of these"} value={online} tone="success" />
          <Stat icon={Users} label={onlineOnly ? "On your site" : "Visitors, last 7 days"} value={all.length} tone="primary" />
          <Stat icon={MessageSquare} label="With a conversation" value={chatting} tone="primary" />
        </div>

        <div className="overflow-hidden rounded-lg border bg-surface shadow-sm">
          <div className="flex items-center justify-between gap-4 border-b px-4 py-3">
            <p className="text-sm font-semibold">{rows.length} {rows.length === 1 ? "visitor" : "visitors"}</p>
            <label className="relative block w-64">
              <Search size={15} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" />
              <input
                aria-label="Filter visitors"
                placeholder="Filter by name, email, page…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="block w-full rounded-full border bg-background py-1.5 pr-3 pl-9 text-sm outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/30"
              />
            </label>
          </div>
          {data && rows.length === 0 ? (
            <div className="p-6">
              <EmptyState icon={Eye} title={q ? "No matches" : onlineOnly ? "Nobody is on your site right now" : "No visitors in the last 7 days"}>
                {!q && "Visitors show up here as soon as a page with your widget loads."}
              </EmptyState>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left text-[11px] tracking-wider text-muted-foreground uppercase">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Visitor</th>
                  <th className="px-4 py-2.5 font-semibold">Page</th>
                  <th className="px-4 py-2.5 font-semibold">Browser</th>
                  <th className="px-4 py-2.5 font-semibold">Last seen</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {rows.map((v) => (
                  <tr key={v.id} className="transition-colors hover:bg-muted/40">
                    <td className="px-4 py-3">
                      <span className="flex items-center gap-3">
                        <Avatar name={v.name} online={v.online} size={34} />
                        <span className="min-w-0">
                          <span className="block font-semibold">{v.name}</span>
                          <span className="block text-xs text-muted-foreground">{v.email || "Anonymous"}</span>
                        </span>
                      </span>
                    </td>
                    <td className="max-w-xs truncate px-4 py-3">
                      <a href={v.current_url} target="_blank" rel="noreferrer" className="text-primary-text hover:underline" title={v.current_url}>
                        {v.page_title || v.current_url}
                      </a>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{browserName(v.user_agent)}</td>
                    <td className="px-4 py-3">
                      {v.online ? <span className="font-medium text-success">Now</span> : <span className="text-muted-foreground">{ago(v.last_seen)} ago</span>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {v.conversation_id ? (
                        <Link
                          href={`/w/${workspace.id}/inbox?c=${v.conversation_id}`}
                          className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-primary-text hover:bg-primary-soft"
                        >
                          Open chat
                        </Link>
                      ) : (
                        <Button variant="secondary" size="sm" onClick={() => message(v)}>
                          <MessageSquare size={14} /> Message
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </>
  );
}

function Stat({ icon: Icon, label, value, tone }: { icon: typeof Eye; label: string; value: number; tone: "success" | "primary" }) {
  return (
    <div className="flex items-center gap-4 rounded-lg border bg-surface p-5 shadow-sm">
      <span className={tone === "success" ? "grid size-11 place-items-center rounded-full bg-success-soft text-success" : "grid size-11 place-items-center rounded-full bg-primary-soft text-primary-text"}>
        <Icon size={20} />
      </span>
      <div>
        <p className="text-2xl leading-none font-bold tracking-tight">{value}</p>
        <p className="mt-1 text-sm text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}
