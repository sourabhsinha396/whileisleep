"use client";

import { MessageSquare } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { Avatar, Button, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type ConversationRow, type Visitor } from "@/lib/api";
import { ago, browserName } from "@/lib/format";
import { usePoll } from "@/lib/use-poll";

export default function VisitorsPage() {
  const { workspace } = useWorkspace();
  const router = useRouter();
  const [onlineOnly, setOnlineOnly] = useState(true);
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

  const rows = data ?? [];
  return (
    <>
      <PageHeader title="Visitors">
        <Button variant={onlineOnly ? "primary" : "secondary"} onClick={() => setOnlineOnly(true)}>
          Online now
        </Button>
        <Button variant={!onlineOnly ? "primary" : "secondary"} onClick={() => setOnlineOnly(false)}>
          Last 7 days
        </Button>
      </PageHeader>
      <div className="p-8">
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs text-gray-500 uppercase">
              <tr>
                <th className="px-4 py-3 font-medium">Visitor</th>
                <th className="px-4 py-3 font-medium">Page</th>
                <th className="px-4 py-3 font-medium">Browser</th>
                <th className="px-4 py-3 font-medium">Last seen</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-500">
                    {onlineOnly ? "Nobody is on your site right now." : "No visitors in the last 7 days."}
                  </td>
                </tr>
              )}
              {rows.map((v) => (
                <tr key={v.id} className="border-t border-gray-100">
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-3">
                      <Avatar name={v.name} online={v.online} size={32} />
                      <span>
                        <span className="block font-medium">{v.name}</span>
                        {v.email && <span className="text-xs text-gray-500">{v.email}</span>}
                      </span>
                    </span>
                  </td>
                  <td className="max-w-xs truncate px-4 py-3">
                    <a href={v.current_url} target="_blank" rel="noreferrer" className="text-brand hover:underline" title={v.current_url}>
                      {v.page_title || v.current_url}
                    </a>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{browserName(v.user_agent)}</td>
                  <td className="px-4 py-3 text-gray-600">{v.online ? "now" : ago(v.last_seen)}</td>
                  <td className="px-4 py-3 text-right">
                    {v.conversation_id ? (
                      <Link href={`/w/${workspace.id}/inbox?c=${v.conversation_id}`} className="text-brand hover:underline">
                        Open chat
                      </Link>
                    ) : (
                      <Button variant="secondary" onClick={() => message(v)}>
                        <MessageSquare size={15} /> Message
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
