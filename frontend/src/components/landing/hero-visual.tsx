"use client";

import clsx from "clsx";
import { BookOpen, Bot, FileText, Hand, Wrench } from "lucide-react";
import { useEffect, useState } from "react";

/**
 * The hero: a live-looking whileisleep inbox where the AI answers one chat after another.
 * `handoff` (set by the demo below when a visitor asks for a person) adds a chat flagged for you.
 */

type Chat = { name: string; q: string; step: { icon: typeof Wrench; text: string }; a: string };

const CHATS: Chat[] = [
  { name: "Maya Chen", q: "Where's my order #4821?", step: { icon: Wrench, text: "order_status → shipped, ETA Thu" }, a: "It shipped yesterday and arrives Thursday. 📦" },
  { name: "Leo Martin", q: "Do you ship to Canada?", step: { icon: BookOpen, text: "Help center → International shipping" }, a: "We do! 4 to 7 business days, duties included." },
  { name: "Priya Shah", q: "Can I switch to the yearly plan?", step: { icon: FileText, text: "Playbook → Plan changes" }, a: "Sure! Yearly saves you 20%. Want me to switch it now?" },
  { name: "Sam Okafor", q: "Is the blue one in stock?", step: { icon: Wrench, text: "check_stock → 12 left" }, a: "Yes, 12 left in blue. Here's the link." },
];

const HANDOFF = { name: "Jo Rivera", q: "This is broken. Get me a human!" };
const TICK_MS = 1400;

export function HeroVisual({ handoff = false }: { handoff?: boolean }) {
  // One tick at a time: each chat shows its question, then the lookup, then the answer.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), TICK_MS);
    return () => clearInterval(id);
  }, []);
  const round = Math.floor(tick / 3);
  const current = round % CHATS.length;
  const phase = tick % 3;
  const chat = CHATS[current];
  const StepIcon = chat.step.icon;

  return (
    <div className="overflow-hidden rounded-2xl border bg-surface shadow-2xl shadow-primary/15">
      <div className="flex items-center gap-3 border-b bg-muted/60 px-4 py-2.5">
        <span className="flex gap-1.5">
          <span className="size-2.5 rounded-full bg-[#ff5f57]" />
          <span className="size-2.5 rounded-full bg-[#febc2e]" />
          <span className="size-2.5 rounded-full bg-[#28c840]" />
        </span>
        <span className="text-xs font-semibold text-muted-foreground">Inbox · Acme</span>
        <span
          className={clsx(
            "ml-auto flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold",
            handoff ? "bg-warning-soft text-warning" : "bg-success-soft text-success",
          )}
        >
          <span className={clsx("size-1.5 rounded-full", handoff ? "bg-warning" : "bg-success")} />
          {handoff ? "1 needs you" : "AI on duty"}
        </span>
      </div>

      <div className="grid h-[360px] sm:grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)]">
        {/* Conversation list */}
        <ul className="hidden space-y-1 overflow-hidden border-r p-2 sm:block">
          {handoff && <ListItem name={HANDOFF.name} preview={HANDOFF.q} status="handoff" active />}
          {CHATS.map((c, n) => (
            <ListItem
              key={c.name}
              name={c.name}
              preview={n === current && phase < 2 ? "AI is replying…" : c.a}
              status={n === current && phase < 2 ? "live" : "done"}
              active={!handoff && n === current}
            />
          ))}
        </ul>

        {/* Thread */}
        {handoff ? (
          <div className="flex flex-col gap-3 p-4 text-sm">
            <Bubble from="visitor" className="land-in">{HANDOFF.q}</Bubble>
            <p className="land-in flex w-fit items-center gap-1.5 rounded-full border border-warning/40 bg-warning-soft px-2.5 py-1 text-xs font-medium text-warning">
              <Hand size={13} /> Rule “Wants a person” → handed to you
            </p>
            <Bubble from="bot" className="land-in">Sorry about that! I&apos;ve passed this to the team. They&apos;ll reply right here.</Bubble>
          </div>
        ) : (
          <div key={current} className="flex flex-col gap-3 p-4 text-sm">
            <Bubble from="visitor" className="land-in">{chat.q}</Bubble>
            {phase === 0 && <Typing />}
            {phase >= 1 && (
              <p className="land-in flex w-fit max-w-full items-center gap-1.5 rounded-full border bg-background px-2.5 py-1 font-mono text-[11px] text-primary-text">
                <StepIcon size={12} className="shrink-0" />
                <span className="truncate">{chat.step.text}</span>
              </p>
            )}
            {phase === 1 && <Typing />}
            {phase >= 2 && <Bubble from="bot" className="land-in">{chat.a}</Bubble>}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between border-t px-4 py-2.5 text-xs text-muted-foreground">
        <span>Answered by AI tonight</span>
        <span className="font-semibold text-foreground tabular-nums">{37 + round}</span>
      </div>
    </div>
  );
}

function ListItem({ name, preview, status, active }: { name: string; preview: string; status: "live" | "done" | "handoff"; active?: boolean }) {
  return (
    <li className={clsx("flex items-center gap-2.5 rounded-xl px-2.5 py-2", active && "bg-primary-soft", status === "handoff" && "land-in")}>
      <span className="grid size-8 shrink-0 place-items-center rounded-full bg-muted text-[11px] font-bold text-muted-foreground">
        {name.split(" ").map((p) => p[0]).join("")}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center justify-between gap-2">
          <span className="truncate text-[13px] font-semibold">{name}</span>
          <span
            className={clsx(
              "size-2 shrink-0 rounded-full",
              status === "live" && "bg-primary",
              status === "done" && "bg-success",
              status === "handoff" && "bg-warning",
            )}
          />
        </span>
        <span className="block truncate text-xs text-muted-foreground">{preview}</span>
      </span>
    </li>
  );
}

function Bubble({ from, className, children }: { from: "visitor" | "bot"; className?: string; children: React.ReactNode }) {
  return (
    <div className={clsx("flex max-w-[88%] gap-2", from === "bot" && "flex-row-reverse self-end", className)}>
      {from === "bot" && (
        <span className="grid size-7 shrink-0 place-items-center self-end rounded-full bg-primary text-primary-foreground">
          <Bot size={14} />
        </span>
      )}
      <p className={clsx("rounded-2xl px-3.5 py-2 leading-snug", from === "visitor" ? "rounded-bl-md bg-muted" : "rounded-br-md bg-primary text-primary-foreground")}>
        {children}
      </p>
    </div>
  );
}

function Typing() {
  return (
    <p className="land-typing flex w-fit gap-1 self-end rounded-2xl rounded-br-md bg-primary-soft px-3.5 py-3" aria-label="Typing">
      <span className="size-1.5 rounded-full bg-primary" />
      <span className="size-1.5 rounded-full bg-primary" />
      <span className="size-1.5 rounded-full bg-primary" />
    </p>
  );
}
