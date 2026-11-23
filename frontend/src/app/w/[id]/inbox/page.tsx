"use client";

import clsx from "clsx";
import { Bot, Check, Globe, Mail, Monitor, RotateCcw, UserRound } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { A2uiPreview } from "@/components/a2ui-preview";
import { Avatar, Button } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type ConversationDetail, type ConversationRow, type Message } from "@/lib/api";
import { ago, browserName, clock } from "@/lib/format";
import { usePoll } from "@/lib/use-poll";

type Filter = "open" | "resolved" | "all";

export default function InboxPage() {
  return (
    <Suspense>
      <Inbox />
    </Suspense>
  );
}

function Inbox() {
  const { workspace } = useWorkspace();
  const params = useSearchParams();
  const [filter, setFilter] = useState<Filter>("open");
  const [selected, setSelected] = useState<number | null>(params.get("c") ? Number(params.get("c")) : null);
  const base = `/workspaces/${workspace.id}/conversations`;
  const list = usePoll(useCallback(() => api<ConversationRow[]>(`${base}?status=${filter}`), [base, filter]), 4000);

  const rows = list.data ?? [];
  const current = selected ?? rows[0]?.id ?? null;

  return (
    <div className="flex h-full">
      <section className="flex w-[340px] shrink-0 flex-col border-r border-gray-200 bg-white">
        <div className="flex items-center gap-2 border-b border-gray-100 px-4 py-3">
          <select
            aria-label="Filter conversations"
            className="rounded-md bg-transparent py-1 text-base font-semibold outline-none"
            value={filter}
            onChange={(e) => setFilter(e.target.value as Filter)}
          >
            <option value="open">Open</option>
            <option value="resolved">Resolved</option>
            <option value="all">All</option>
          </select>
          <span className="text-sm text-gray-500">{rows.length}</span>
        </div>
        <div className="flex-1 overflow-y-auto">
          {rows.length === 0 && <p className="p-6 text-sm text-gray-500">No conversations here yet. Add the widget to your site from Settings.</p>}
          {rows.map((row) => (
            <button
              key={row.id}
              onClick={() => setSelected(row.id)}
              className={clsx(
                "flex w-full gap-3 border-b border-gray-100 px-4 py-4 text-left hover:bg-gray-50",
                row.id === current && "bg-brand-soft/70 shadow-[inset_3px_0_0] shadow-brand",
              )}
            >
              <Avatar name={row.visitor.name} online={row.visitor.online} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  {row.unread && <span className="h-2 w-2 rounded-full bg-brand" aria-label="Unread" />}
                  <span className={clsx("truncate text-sm", row.unread ? "font-bold" : "font-semibold")}>{row.visitor.name}</span>
                  <span className="ml-auto text-xs text-gray-500">{ago(row.last_message_at)}</span>
                </span>
                <span className="mt-1 line-clamp-2 text-sm text-gray-600">{row.preview || "…"}</span>
                {row.human_requested && row.status === "open" && (
                  <span className="mt-1.5 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800">Needs a person</span>
                )}
              </span>
            </button>
          ))}
        </div>
      </section>
      {current ? (
        <Conversation key={current} id={current} onChange={list.reload} />
      ) : (
        <div className="grid flex-1 place-items-center text-sm text-gray-500">Select a conversation</div>
      )}
    </div>
  );
}

function Conversation({ id, onChange }: { id: number; onChange: () => void }) {
  const { workspace } = useWorkspace();
  const path = `/workspaces/${workspace.id}/conversations/${id}`;
  const { data, setData, reload } = usePoll(useCallback(() => api<ConversationDetail>(path), [path]), 2500);
  const [mode, setMode] = useState<"reply" | "note">("reply");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const count = data?.messages.length ?? 0;

  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [count]);

  if (!data) return <div className="flex-1" />;

  async function send() {
    if (!draft.trim()) return;
    setBusy(true);
    try {
      await api<Message>(`${path}/messages`, { method: "POST", body: { body: draft, is_note: mode === "note" } });
      setDraft("");
      await reload();
      onChange();
    } finally {
      setBusy(false);
    }
  }

  async function patch(body: object) {
    const row = await api<ConversationRow>(path, { method: "PATCH", body });
    setData({ ...data!, ...row });
    onChange();
  }

  const v = data.visitor;
  return (
    <>
      <section className="flex min-w-0 flex-1 flex-col bg-white">
        <header className="flex items-center gap-3 border-b border-gray-200 px-6 py-3">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-lg font-semibold">{v.name}</h2>
            <p className="text-sm text-gray-500">
              Chat · opened {ago(data.messages[0]?.created_at ?? data.last_message_at)} ago ·{" "}
              {data.human_requested ? "handled by your team" : workspace.ai_enabled ? "AI agent answering" : "waiting for your team"}
            </p>
          </div>
          {data.human_requested && workspace.ai_enabled && (
            <Button variant="secondary" onClick={() => patch({ human_requested: false })} title="Let the AI agent answer the next visitor message">
              <Bot size={16} /> Hand back to AI
            </Button>
          )}
          {data.status === "open" ? (
            <Button className="bg-green-600 hover:bg-green-700" onClick={() => patch({ status: "resolved" })}>
              <Check size={16} /> Resolve
            </Button>
          ) : (
            <Button variant="secondary" onClick={() => patch({ status: "open" })}>
              <RotateCcw size={16} /> Reopen
            </Button>
          )}
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          {data.messages.map((m) => (
            <MessageBubble key={m.id} message={m} visitorName={v.name} />
          ))}
          <div ref={end} />
        </div>

        <div className="m-4 rounded-2xl border border-gray-200 shadow-sm">
          <div className="flex gap-1 border-b border-gray-100 p-2">
            {(["reply", "note"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={clsx("rounded-md px-3 py-1.5 text-sm", mode === m ? "bg-gray-100 font-semibold" : "text-gray-600")}
              >
                {m === "reply" ? "Reply" : "Internal note"}
              </button>
            ))}
          </div>
          <textarea
            aria-label={mode === "reply" ? "Reply" : "Internal note"}
            className={clsx("block w-full resize-none px-4 py-3 text-sm outline-none", mode === "note" && "bg-amber-50")}
            rows={3}
            placeholder={mode === "reply" ? "Write a reply. The AI agent pauses once you answer." : "Only your team sees notes"}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <div className="flex items-center justify-between px-4 pb-3 text-xs text-gray-500">
            <span>
              <kbd className="rounded border px-1">Enter</kbd> to send, <kbd className="rounded border px-1">Shift</kbd>+<kbd className="rounded border px-1">Enter</kbd> for a new line
            </span>
            <Button onClick={send} disabled={busy || !draft.trim()}>
              {mode === "reply" ? "Send" : "Add note"}
            </Button>
          </div>
        </div>
      </section>

      <aside className="w-80 shrink-0 overflow-y-auto border-l border-gray-200 bg-white p-5">
        <div className="flex items-center gap-3">
          <Avatar name={v.name} online={v.online} size={48} />
          <div className="min-w-0">
            <p className="truncate font-semibold">{v.name}</p>
            <p className="text-sm text-gray-500">{v.online ? "Online now" : `Last seen ${ago(v.last_seen)} ago`}</p>
          </div>
        </div>
        <dl className="mt-6 space-y-3 text-sm">
          <Detail icon={Mail} label="Email">{v.email || <span className="text-gray-400">Not shared yet</span>}</Detail>
          <Detail icon={Globe} label="Current page">
            {v.current_url ? (
              <a className="break-all text-brand hover:underline" href={v.current_url} target="_blank" rel="noreferrer">
                {v.page_title || v.current_url}
              </a>
            ) : (
              "—"
            )}
          </Detail>
          <Detail icon={Monitor} label="Browser">{browserName(v.user_agent)}</Detail>
          <Detail icon={UserRound} label="First seen">{new Date(v.first_seen).toLocaleString()}</Detail>
        </dl>
        <h3 className="mt-8 text-xs font-semibold tracking-wider text-gray-500 uppercase">This conversation</h3>
        <ul className="mt-3 space-y-2 text-sm">
          <li>Status: {data.status}</li>
          <li>Bot: {data.human_requested ? "paused, a person is handling it" : workspace.ai_enabled ? "answering" : "off"}</li>
          <li>ID: #{data.id}</li>
        </ul>
      </aside>
    </>
  );
}

function Detail({ icon: Icon, label, children }: { icon: typeof Mail; label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <Icon size={16} className="mt-0.5 shrink-0 text-gray-400" />
      <div className="min-w-0">
        <dt className="text-xs text-gray-500">{label}</dt>
        <dd>{children}</dd>
      </div>
    </div>
  );
}

function MessageBubble({ message: m, visitorName }: { message: Message; visitorName: string }) {
  if (m.sender === "system") {
    return (
      <div className="mx-auto max-w-[80%] rounded-lg bg-gray-50 px-3 py-2 text-xs whitespace-pre-wrap text-gray-600">
        {m.body}
        <span className="ml-2 text-gray-400">{clock(m.created_at)}</span>
      </div>
    );
  }
  const mine = m.sender !== "visitor";
  const who = m.sender === "visitor" ? visitorName : m.sender === "bot" ? "AI agent" : m.author_name;
  return (
    <div className={clsx("flex flex-col", mine ? "items-end" : "items-start")}>
      <p className="mb-1 flex items-center gap-2 text-sm">
        <span className="font-semibold">{who}</span>
        <span className="text-gray-500">{clock(m.created_at)}</span>
        {m.sender === "bot" && <span className="rounded bg-green-100 px-1.5 py-0.5 text-[11px] font-bold text-green-800">AI AUTO REPLY</span>}
        {m.is_note && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-bold text-amber-800">NOTE</span>}
      </p>
      <div
        className={clsx(
          "max-w-[75%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed whitespace-pre-wrap",
          m.is_note ? "bg-amber-50 ring-1 ring-amber-200" : mine ? "bg-brand text-white" : "bg-gray-100",
        )}
      >
        {m.body}
        {m.a2ui && <A2uiPreview messages={m.a2ui} />}
      </div>
    </div>
  );
}
