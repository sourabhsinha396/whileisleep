"use client";

import clsx from "clsx";
import {
  Bot,
  Check,
  ChevronDown,
  CircleCheck,
  Clock,
  Globe,
  Hash,
  Inbox as InboxIcon,
  Mail,
  MessageSquare,
  Monitor,
  RotateCcw,
  Search,
  SendHorizontal,
  Sparkles,
  StickyNote,
  Tag,
  UserRound,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Fragment, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { A2uiPreview } from "@/components/a2ui-preview";
import { Avatar, Badge, Button, Segmented } from "@/components/ui";
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
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<number | null>(params.get("c") ? Number(params.get("c")) : null);
  const base = `/workspaces/${workspace.id}/conversations`;
  const list = usePoll(useCallback(() => api<ConversationRow[]>(`${base}?status=${filter}`), [base, filter]), 4000);

  const all = list.data ?? [];
  const q = query.trim().toLowerCase();
  const rows = q
    ? all.filter((r) => [r.visitor.name, r.visitor.email, r.preview, ...r.tags].some((s) => s?.toLowerCase().includes(q)))
    : all;
  const current = selected ?? rows[0]?.id ?? null;

  return (
    <div className="flex h-full">
      <section className="flex w-[340px] shrink-0 flex-col border-r bg-surface">
        <div className="space-y-3 border-b px-4 pt-4 pb-3">
          <div className="flex items-center justify-between">
            <h1 className="text-lg font-bold tracking-tight">Inbox</h1>
            <span className="text-xs font-medium text-muted-foreground">
              {rows.length} {rows.length === 1 ? "conversation" : "conversations"}
            </span>
          </div>
          <Segmented
            value={filter}
            onChange={setFilter}
            options={[
              { value: "open", label: "Open" },
              { value: "resolved", label: "Resolved" },
              { value: "all", label: "All" },
            ]}
          />
          <label className="relative block">
            <Search size={15} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" />
            <input
              aria-label="Search conversations"
              placeholder="Search by name, email, tag…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="block w-full rounded-full border bg-background py-1.5 pr-3 pl-9 text-sm outline-none placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/30"
            />
          </label>
        </div>
        <div className="flex-1 overflow-y-auto p-2">
          {list.data && rows.length === 0 && (
            <div className="px-4 py-12 text-center">
              <span className="mx-auto mb-3 grid size-11 place-items-center rounded-full bg-primary-soft text-primary-text">
                <InboxIcon size={20} />
              </span>
              <p className="text-sm font-semibold">{q ? "No matches" : filter === "open" ? "All caught up" : "Nothing here yet"}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {q ? "Try another search." : "New chats from your widget land here."}
              </p>
            </div>
          )}
          {rows.map((row) => {
            const active = row.id === current;
            return (
              <button
                key={row.id}
                onClick={() => setSelected(row.id)}
                className={clsx(
                  "mb-0.5 flex w-full gap-3 rounded-lg px-3 py-3 text-left transition-colors",
                  active ? "bg-primary-soft" : "hover:bg-muted",
                )}
              >
                <Avatar name={row.visitor.name} online={row.visitor.online} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className={clsx("truncate text-sm", row.unread ? "font-bold" : "font-semibold")}>{row.visitor.name}</span>
                    <span className="ml-auto shrink-0 text-xs text-muted-foreground">{ago(row.last_message_at)}</span>
                  </span>
                  <span className="mt-0.5 flex items-center gap-2">
                    <span className={clsx("line-clamp-1 flex-1 text-sm", row.unread ? "text-foreground" : "text-muted-foreground")}>
                      {row.preview || "…"}
                    </span>
                    {row.unread ? (
                      <span className="size-2.5 shrink-0 rounded-full bg-primary" aria-label="Unread" />
                    ) : row.status === "resolved" ? (
                      <CircleCheck size={16} className="shrink-0 text-success" aria-label="Resolved" />
                    ) : null}
                  </span>
                  {((row.human_requested && row.status === "open") || row.tags.length > 0) && (
                    <span className="mt-1.5 flex flex-wrap gap-1">
                      {row.human_requested && row.status === "open" && <Badge tone="warning">Needs a person</Badge>}
                      {row.tags.map((tag) => (
                        <Badge key={tag} tone="primary">
                          {tag}
                        </Badge>
                      ))}
                    </span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </section>
      {current ? (
        <Conversation key={current} id={current} onChange={list.reload} />
      ) : (
        <div className="grid flex-1 place-items-center bg-muted/30">
          <div className="text-center">
            <span className="mx-auto mb-3 grid size-12 place-items-center rounded-full bg-primary-soft text-primary-text">
              <MessageSquare size={22} />
            </span>
            <p className="font-semibold">No conversation selected</p>
            <p className="mt-1 text-sm text-muted-foreground">Pick one from the list to read and reply.</p>
          </div>
        </div>
      )}
    </div>
  );
}

function dayLabel(iso: string) {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
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

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [count]);

  if (!data) return <div className="flex-1 bg-muted/30" />;

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
  const handler = data.human_requested ? "Your team is handling it" : workspace.ai_enabled ? "AI agent answering" : "Waiting for your team";

  return (
    <>
      <section className="flex min-w-0 flex-1 flex-col bg-muted/30">
        <header className="flex items-center gap-3 border-b bg-surface px-6 py-3">
          <Avatar name={v.name} online={v.online} size={36} />
          <div className="min-w-0 flex-1">
            <h2 className="truncate font-bold tracking-tight">{v.name}</h2>
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {data.human_requested ? <UserRound size={12} /> : workspace.ai_enabled ? <Sparkles size={12} className="text-primary-text" /> : <Clock size={12} />}
              {handler} · opened {ago(data.messages[0]?.created_at ?? data.last_message_at)} ago
            </p>
          </div>
          {data.human_requested && workspace.ai_enabled && (
            <Button variant="secondary" onClick={() => patch({ human_requested: false })} title="Let the AI agent answer the next visitor message">
              <Bot size={16} /> Hand back to AI
            </Button>
          )}
          {data.status === "open" ? (
            <Button variant="success" onClick={() => patch({ status: "resolved" })}>
              <Check size={16} /> Resolve
            </Button>
          ) : (
            <Button variant="secondary" onClick={() => patch({ status: "open" })}>
              <RotateCcw size={16} /> Reopen
            </Button>
          )}
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto px-6 py-5">
          {data.messages.map((m, i) => {
            const day = dayLabel(m.created_at);
            const showDay = i === 0 || day !== dayLabel(data.messages[i - 1].created_at);
            return (
              <Fragment key={m.id}>
                {showDay && (
                  <div className="flex justify-center py-2">
                    <span className="rounded-full border bg-surface px-3 py-0.5 text-[11px] font-semibold text-muted-foreground shadow-sm">{day}</span>
                  </div>
                )}
                <MessageBubble message={m} visitorName={v.name} />
              </Fragment>
            );
          })}
          <div ref={end} />
        </div>

        <div
          className={clsx(
            "mx-4 mb-4 rounded-xl border bg-surface shadow-sm transition-colors focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/20",
            mode === "note" && "border-warning/40 bg-warning-soft focus-within:border-warning focus-within:ring-warning/20",
          )}
        >
          <div className="flex gap-1 px-2 pt-2">
            {(["reply", "note"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={clsx(
                  "flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-colors",
                  mode === m
                    ? m === "note"
                      ? "bg-warning/15 text-warning"
                      : "bg-primary-soft text-primary-text"
                    : "text-muted-foreground hover:bg-muted",
                )}
              >
                {m === "reply" ? <MessageSquare size={13} /> : <StickyNote size={13} />}
                {m === "reply" ? "Reply" : "Internal note"}
              </button>
            ))}
          </div>
          <textarea
            aria-label={mode === "reply" ? "Reply" : "Internal note"}
            className="block w-full resize-none bg-transparent px-4 py-3 text-sm outline-none placeholder:text-muted-foreground"
            rows={3}
            placeholder={mode === "reply" ? `Reply to ${v.name}. The AI agent pauses once you answer.` : "Only your team sees notes"}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <div className="flex items-center justify-between px-3 pb-3 text-xs text-muted-foreground">
            <span className="pl-1">
              <Kbd>Enter</Kbd> to send · <Kbd>Shift</Kbd> + <Kbd>Enter</Kbd> for a new line
            </span>
            <Button onClick={send} disabled={busy || !draft.trim()} size="sm" className={mode === "note" ? "bg-warning hover:bg-warning/90" : undefined}>
              {mode === "reply" ? "Send" : "Add note"} <SendHorizontal size={14} />
            </Button>
          </div>
        </div>
      </section>

      <aside className="w-80 shrink-0 overflow-y-auto border-l bg-surface">
        <div className="flex flex-col items-center border-b px-5 pt-6 pb-5 text-center">
          <Avatar name={v.name} online={v.online} size={64} />
          <p className="mt-3 truncate text-lg font-bold tracking-tight">{v.name}</p>
          <p className="text-sm text-muted-foreground">{v.email || "No email yet"}</p>
          <Badge tone={v.online ? "success" : "neutral"} className="mt-2">
            {v.online ? "Online now" : `Last seen ${ago(v.last_seen)} ago`}
          </Badge>
        </div>
        <Section title="Visitor">
          <Detail icon={Mail} label="Email">{v.email || <span className="text-muted-foreground">Not shared yet</span>}</Detail>
          <Detail icon={Globe} label="Current page">
            {v.current_url ? (
              <a className="break-all text-primary-text hover:underline" href={v.current_url} target="_blank" rel="noreferrer">
                {v.page_title || v.current_url}
              </a>
            ) : (
              "—"
            )}
          </Detail>
          <Detail icon={Monitor} label="Browser">{browserName(v.user_agent)}</Detail>
          <Detail icon={UserRound} label="First seen">{new Date(v.first_seen).toLocaleString()}</Detail>
        </Section>
        <Section title="Conversation">
          <Detail icon={CircleCheck} label="Status">
            <Badge tone={data.status === "open" ? "primary" : "success"} className="capitalize">
              {data.status}
            </Badge>
          </Detail>
          <Detail icon={Bot} label="AI agent">
            {data.human_requested ? "Paused, a person is handling it" : workspace.ai_enabled ? "Answering" : "Off"}
          </Detail>
          <Detail icon={Tag} label="Tags">
            {data.tags.length ? (
              <span className="mt-0.5 flex flex-wrap gap-1">
                {data.tags.map((t) => (
                  <Badge key={t} tone="primary">
                    {t}
                  </Badge>
                ))}
              </span>
            ) : (
              <span className="text-muted-foreground">None</span>
            )}
          </Detail>
          <Detail icon={Hash} label="ID">#{data.id}</Detail>
        </Section>
      </aside>
    </>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border bg-background px-1 font-sans text-[10px]">{children}</kbd>;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="border-b">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between px-5 py-3 text-sm font-semibold hover:bg-muted/50" aria-expanded={open}>
        {title}
        <ChevronDown size={16} className={clsx("text-muted-foreground transition-transform", !open && "-rotate-90")} />
      </button>
      {open && <dl className="space-y-3 px-5 pb-5 text-sm">{children}</dl>}
    </div>
  );
}

function Detail({ icon: Icon, label, children }: { icon: typeof Mail; label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <Icon size={16} className="mt-0.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0">
        <dt className="text-xs text-muted-foreground">{label}</dt>
        <dd>{children}</dd>
      </div>
    </div>
  );
}

function MessageBubble({ message: m, visitorName }: { message: Message; visitorName: string }) {
  if (m.sender === "system") {
    return (
      <div className="flex justify-center">
        <span className="max-w-[80%] rounded-full bg-muted px-3 py-1 text-center text-xs whitespace-pre-wrap text-muted-foreground">
          {m.body}
          <span className="ml-2 opacity-70">{clock(m.created_at)}</span>
        </span>
      </div>
    );
  }
  const mine = m.sender !== "visitor";
  const who = m.sender === "visitor" ? visitorName : m.sender === "bot" ? "AI agent" : m.author_name;
  return (
    <div className={clsx("flex gap-2.5", mine ? "flex-row-reverse" : "flex-row")}>
      {m.sender === "bot" ? (
        <span className="grid size-8 shrink-0 place-items-center self-end rounded-full bg-primary-soft text-primary-text">
          <Sparkles size={15} />
        </span>
      ) : (
        <span className="self-end">
          <Avatar name={who} size={32} />
        </span>
      )}
      <div className={clsx("flex max-w-[72%] flex-col", mine ? "items-end" : "items-start")}>
        <p className="mb-1 flex items-center gap-2 px-1 text-xs">
          <span className="font-semibold">{who}</span>
          <span className="text-muted-foreground">{clock(m.created_at)}</span>
          {m.sender === "bot" && (
            <Badge tone="success">
              <Sparkles size={10} /> AI reply
            </Badge>
          )}
          {m.is_note && (
            <Badge tone="warning">
              <StickyNote size={10} /> Note
            </Badge>
          )}
          {m.intent && (
            <Badge tone="primary" className="font-mono" title="Sent from a button on your site">
              {m.intent}
            </Badge>
          )}
        </p>
        <div
          className={clsx(
            "rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap shadow-sm",
            m.is_note
              ? "bg-warning-soft ring-1 ring-warning/30"
              : mine
                ? "rounded-br-md bg-primary text-primary-foreground"
                : "rounded-bl-md border bg-surface",
          )}
        >
          {m.body}
          {m.a2ui && <A2uiPreview messages={m.a2ui} />}
        </div>
      </div>
    </div>
  );
}
