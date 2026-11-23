"use client";

import clsx from "clsx";
import { BellRing, BookOpen, Bot, FileText, Hand, Moon, Send, Wrench, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/**
 * A scripted stand-in for the real thing: a visitor chats in the widget on the left, and the
 * right side shows what whileisleep does behind the scenes (rules, playbooks, tools, hand-off).
 * Nothing here calls the backend.
 */

type StepKind = "rule" | "playbook" | "tool" | "kb" | "handoff" | "reply";
type Step = { kind: StepKind; title: string; detail: string };
type Card = { kind: "article"; title: string } | { kind: "form"; label: string } | { kind: "person" };
type Scenario = {
  id: string;
  prompt: string;
  steps: Step[];
  reply: string;
  card?: Card;
  wakesYou?: boolean;
};

const SCENARIOS: Scenario[] = [
  {
    id: "order",
    prompt: "Where's my order #4821?",
    steps: [
      { kind: "rule", title: "Rules checked", detail: "No rule matches, so the AI takes it" },
      { kind: "tool", title: "Called your API: order_status", detail: '{ "order": "4821" } → { "status": "shipped", "eta": "Thu" }' },
      { kind: "reply", title: "Replied to the visitor", detail: "Answered with real data, no guessing" },
    ],
    reply: "Good news: order #4821 shipped yesterday and should arrive on Thursday. 📦",
  },
  {
    id: "ship",
    prompt: "Do you ship to Canada?",
    steps: [
      { kind: "rule", title: "Rules checked", detail: "No rule matches, so the AI takes it" },
      { kind: "kb", title: "Searched your help center", detail: '"ship canada" → International shipping (1 article)' },
      { kind: "reply", title: "Replied with the article", detail: "Visitors can open the full article in the widget" },
    ],
    reply: "We do! Canada takes 4 to 7 business days, and duties are included at checkout.",
    card: { kind: "article", title: "International shipping" },
  },
  {
    id: "refund",
    prompt: "I'd like a refund",
    steps: [
      { kind: "rule", title: "Rules checked", detail: "No rule matches, so the AI takes it" },
      { kind: "playbook", title: "Opened a playbook: Refunds", detail: "“Ask for the order email first, then confirm the item”" },
      { kind: "reply", title: "Asked with a form", detail: "An email form, built by the AI from your playbook" },
    ],
    reply: "Happy to help with that. What email did you order with? I'll find the order.",
    card: { kind: "form", label: "Your order email" },
  },
  {
    id: "human",
    prompt: "This is broken. Get me a human!",
    steps: [
      { kind: "rule", title: "Rule matched: Wants a person", detail: "Keywords “human”, “broken” → tag urgent + hand off" },
      { kind: "handoff", title: "Handed off to your team", detail: "Pinged the inbox. The AI stays quiet now" },
      { kind: "reply", title: "Sent the exact reply from the rule", detail: "No AI involved for this one" },
    ],
    reply: "Sorry about that! I've passed this to the team. They'll reply right here, and by email too.",
    card: { kind: "person" },
    wakesYou: true,
  },
];

const FALLBACK: Scenario = {
  id: "unknown",
  prompt: "",
  steps: [
    { kind: "rule", title: "Rules checked", detail: "No rule matches, so the AI takes it" },
    { kind: "kb", title: "Searched your help center", detail: "No good match, and no tool fits" },
    { kind: "reply", title: "Offered a person instead of guessing", detail: "Better an honest answer than a made-up one" },
  ],
  reply: "I don't have a good answer for that one, and I'd rather not guess. Want me to get a person?",
  card: { kind: "person" },
};

function match(text: string): Scenario {
  const t = text.toLowerCase();
  if (/human|person|agent|broken|angry|manager|real people/.test(t)) return SCENARIOS[3];
  if (/refund|money back|return/.test(t)) return SCENARIOS[2];
  if (/ship|deliver|canada|international|abroad/.test(t)) return SCENARIOS[1];
  if (/order|track|package|parcel|where/.test(t)) return SCENARIOS[0];
  return FALLBACK;
}

const STEP_ICON: Record<StepKind, React.ComponentType<{ size?: number }>> = {
  rule: Zap,
  playbook: FileText,
  tool: Wrench,
  kb: BookOpen,
  handoff: Hand,
  reply: Bot,
};

type Msg = { id: number; from: "visitor" | "bot"; text: string; card?: Card };

const STEP_MS = 900;
const MAX_CHARS = 500;

export function Demo({ onHandoff }: { onHandoff?: (handedOff: boolean) => void }) {
  const [messages, setMessages] = useState<Msg[]>([
    { id: 0, from: "bot", text: "Hi! 👋 Ask me anything. Try a suggestion below, or type your own." },
  ]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [typing, setTyping] = useState(false);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState("");
  const [stats, setStats] = useState({ ai: 0, you: 0 });
  const [awake, setAwake] = useState(false);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const chatRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);
  useEffect(() => onHandoff?.(awake), [awake, onHandoff]);
  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, typing]);

  function later(ms: number, fn: () => void) {
    timers.current.push(setTimeout(fn, ms));
  }

  function ask(text: string, scenario = match(text)) {
    if (busy || !text.trim()) return;
    setBusy(true);
    setDraft("");
    setSteps([]);
    setAwake(false);
    setMessages((m) => [...m, { id: nextId.current++, from: "visitor", text: text.trim() }]);
    setTyping(true);
    scenario.steps.forEach((step, i) => later(500 + i * STEP_MS, () => setSteps((s) => [...s, step])));
    later(500 + scenario.steps.length * STEP_MS, () => {
      setTyping(false);
      setMessages((m) => [...m, { id: nextId.current++, from: "bot", text: scenario.reply, card: scenario.card }]);
      setStats((s) => (scenario.wakesYou ? { ...s, you: s.you + 1 } : { ...s, ai: s.ai + 1 }));
      if (scenario.wakesYou) {
        setAwake(true);
        later(9000, () => setAwake(false)); // and back to sleep
      }
      setBusy(false);
    });
  }

  return (
    <div className="grid overflow-hidden rounded-3xl border bg-surface shadow-xl shadow-primary/5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
      {/* Left: the widget, as a visitor sees it */}
      <div className="flex min-h-[520px] flex-col border-b bg-muted/40 p-4 sm:p-6 lg:border-r lg:border-b-0">
        <p className="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">On your website</p>
        <div className="flex flex-1 flex-col overflow-hidden rounded-2xl border bg-surface shadow-sm">
          <div className="flex items-center gap-3 bg-primary px-4 py-3 text-primary-foreground">
            <span className="grid size-8 place-items-center rounded-full bg-white/20">
              <Bot size={17} />
            </span>
            <span className="leading-tight">
              <span className="block text-sm font-semibold">Acme Support</span>
              <span className="block text-xs text-white/75">Replies instantly, even at 3am</span>
            </span>
          </div>
          <div ref={chatRef} className="flex h-72 flex-1 flex-col gap-2.5 overflow-y-auto p-4 lg:h-auto">
            {messages.map((m) => (
              <div key={m.id} className={clsx("land-in flex max-w-[85%] flex-col gap-2", m.from === "visitor" ? "self-end items-end" : "self-start")}>
                <p className={clsx("rounded-2xl px-3.5 py-2 text-sm", m.from === "visitor" ? "rounded-br-sm bg-primary text-primary-foreground" : "rounded-bl-sm bg-muted")}>
                  {m.text}
                </p>
                {m.card && <CardView card={m.card} />}
              </div>
            ))}
            {typing && (
              <p className="land-typing flex w-fit gap-1 rounded-2xl rounded-bl-sm bg-muted px-3.5 py-3" aria-label="Typing">
                <span className="size-1.5 rounded-full bg-muted-foreground" />
                <span className="size-1.5 rounded-full bg-muted-foreground" />
                <span className="size-1.5 rounded-full bg-muted-foreground" />
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5 border-t px-3 pt-3">
            {SCENARIOS.map((s) => (
              <button
                key={s.id}
                type="button"
                disabled={busy}
                onClick={() => ask(s.prompt, s)}
                className="rounded-full border border-primary/30 bg-primary-soft px-3 py-1 text-xs font-medium text-primary-text transition-colors hover:border-primary disabled:opacity-50"
              >
                {s.prompt}
              </button>
            ))}
          </div>
          <form
            className="flex items-center gap-2 p-3"
            onSubmit={(e) => {
              e.preventDefault();
              ask(draft);
            }}
          >
            <input
              value={draft}
              maxLength={MAX_CHARS}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Type a message…"
              aria-label="Message"
              className="min-w-0 flex-1 rounded-full border bg-background px-4 py-2 text-sm outline-none focus:border-ring"
            />
            <button type="submit" disabled={busy || !draft.trim()} aria-label="Send" className="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground disabled:opacity-40">
              <Send size={15} />
            </button>
          </form>
        </div>
      </div>

      {/* Right: what happens behind the scenes */}
      <div className="flex flex-col p-4 sm:p-6">
        <p className="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Behind the scenes</p>
        <ol className="flex-1 space-y-2.5">
          {steps.length === 0 && (
            <li className="grid h-full min-h-48 place-items-center rounded-2xl border border-dashed p-6 text-center text-sm text-muted-foreground">
              Send a message and watch the agent work: rules first, then your playbooks, APIs and help articles.
            </li>
          )}
          {steps.map((step, i) => {
            const Icon = STEP_ICON[step.kind];
            return (
              <li key={i} className="land-in flex gap-3 rounded-2xl border bg-background p-3">
                <span
                  className={clsx(
                    "grid size-9 shrink-0 place-items-center rounded-xl",
                    step.kind === "handoff" ? "bg-warning-soft text-warning" : step.kind === "reply" ? "bg-success-soft text-success" : "bg-primary-soft text-primary-text",
                  )}
                >
                  <Icon size={17} />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold">{step.title}</span>
                  <span className={clsx("mt-0.5 block text-xs break-words text-muted-foreground", step.kind === "tool" && "font-mono")}>{step.detail}</span>
                </span>
              </li>
            );
          })}
        </ol>

        <div className="mt-5 grid grid-cols-[1fr_auto_auto] items-center gap-3 rounded-2xl bg-muted p-3">
          <span className="flex items-center gap-2.5 text-sm">
            <span className={clsx("grid size-9 place-items-center rounded-full", awake ? "bg-warning-soft text-warning" : "bg-primary-soft text-primary-text")}>
              {awake ? <BellRing size={17} /> : <Moon size={17} />}
            </span>
            <span className="leading-tight">
              <span className="block font-semibold">{awake ? "You got pinged" : "You: still asleep"}</span>
              <span className="block text-xs text-muted-foreground">{awake ? "Only for the one that needs you" : "The AI has this"}</span>
            </span>
          </span>
          <Stat value={stats.ai} label="by AI" />
          <Stat value={stats.you} label="for you" />
        </div>
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <span className="text-center leading-tight">
      <span className="block text-lg font-bold tabular-nums">{value}</span>
      <span className="block text-[11px] text-muted-foreground">{label}</span>
    </span>
  );
}

function CardView({ card }: { card: Card }) {
  if (card.kind === "article")
    return (
      <span className="flex w-fit items-center gap-2 rounded-xl border bg-surface px-3 py-2 text-xs font-medium">
        <BookOpen size={14} className="text-primary-text" /> {card.title}
      </span>
    );
  if (card.kind === "form")
    return (
      <span className="flex w-56 flex-col gap-2 rounded-xl border bg-surface p-3 text-xs">
        <span className="font-medium">{card.label}</span>
        <span className="rounded-md border bg-background px-2 py-1.5 text-muted-foreground">you@example.com</span>
        <span className="self-start rounded-full bg-primary px-3 py-1 font-semibold text-primary-foreground">Send</span>
      </span>
    );
  return (
    <span className="flex w-fit items-center gap-2 rounded-full border bg-surface px-3 py-1.5 text-xs font-medium">
      <Hand size={14} className="text-warning" /> Talk to a person
    </span>
  );
}
