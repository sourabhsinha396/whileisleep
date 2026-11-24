"use client";

import { ArrowRight, BookOpen, Bot, Inbox, Zap } from "lucide-react";
import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { HeroVisual } from "@/components/landing/hero-visual";
import { Demo } from "@/components/landing/demo";
import { PricingPlans } from "@/components/landing/pricing-plans";
import { Ripple } from "@/components/landing/ripple";
import { Logo, ThemeToggle } from "@/components/ui";
import { getToken } from "@/lib/api";

const FEATURES = [
  { icon: Bot, title: "Answers from your data", text: "Help articles, your own APIs and plain-language playbooks. It looks things up instead of guessing." },
  { icon: Zap, title: "Rules that run first", text: "Exact replies, tags and hand-offs by intent, keywords or page, before the AI says a word." },
  { icon: Inbox, title: "One inbox for the rest", text: "Live visitors, conversations and internal notes. Take over any chat, hand it back when you're done." },
  { icon: BookOpen, title: "A help center in the widget", text: "Visitors find answers themselves, and the agent searches the same articles." },
];

const noSubscribe = () => () => {};

const cta = "inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold transition-colors";

export default function Home() {
  // The token lives in localStorage: the server renders signed out, the client reads it after hydration.
  const signedIn = useSyncExternalStore(noSubscribe, () => Boolean(getToken()), () => false);
  const [handoff, setHandoff] = useState(false);

  return (
    <div className="min-h-screen overflow-x-hidden">
      <header className="mx-auto flex max-w-7xl items-center justify-between px-4 py-5 sm:px-6">
        <Logo />
        <nav className="flex items-center gap-1 sm:gap-2">
          <a href="#demo" className="hidden rounded-full px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground sm:block">
            Try the demo
          </a>
          <Link href="/pricing" className="rounded-full px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground">
            Pricing
          </Link>
          <ThemeToggle />
          <Link href={signedIn ? "/app" : "/login"} className={`${cta} bg-primary px-4 py-2 text-primary-foreground hover:bg-primary-hover`}>
            {signedIn ? "Open inbox" : "Log in"}
          </Link>
        </nav>
      </header>

      <main>
        {/* Hero */}
        <section className="relative isolate mx-auto grid max-w-7xl items-center gap-12 px-4 pt-8 pb-16 sm:px-6 lg:grid-cols-[0.9fr_1.1fr] lg:pt-14">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border bg-surface px-3 py-1 text-xs font-semibold text-muted-foreground">
              <span className="size-1.5 rounded-full bg-success" /> Open source · Bring your own LLM
            </p>
            <h1 className="mt-5 text-4xl leading-[1.08] font-extrabold tracking-tight text-balance sm:text-5xl lg:text-6xl">
              AI answers.
              <span className="block text-primary-text">While you sleep.</span>
            </h1>
            <p className="mt-5 max-w-lg text-lg text-muted-foreground">
              We answer from your APIs, MCP, and other data sources, only waking you for chats that need a human.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link href={signedIn ? "/app" : "/login"} className={`${cta} bg-primary text-primary-foreground hover:bg-primary-hover`}>
                {signedIn ? "Open your inbox" : "Start for free"} <ArrowRight size={16} />
              </Link>
              <a href="#demo" className={`${cta} border bg-surface hover:bg-muted`}>
                Try it yourself
              </a>
            </div>
          </div>
          <div className="relative">
            <div className="pointer-events-none absolute -inset-8 -z-10 rounded-[48px] bg-primary/10 blur-3xl" />
            <Ripple />
            <HeroVisual handoff={handoff} />
          </div>
        </section>

        {/* Interactive demo */}
        <section id="demo" className="scroll-mt-6 border-y bg-muted/40">
          <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
            <div className="mb-8 max-w-2xl">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">Now you be the customer</h2>
              <p className="mt-3 text-muted-foreground">
                Pick a question or type your own, and see what the agent does with it: rules, playbooks, your APIs, your
                articles. Ask for a human and see what lands in your inbox.
              </p>
            </div>
            <Demo onHandoff={setHandoff} />
          </div>
        </section>

        {/* Features */}
        <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
          <h2 className="max-w-xl text-3xl font-bold tracking-tight">Everything a support inbox needs, minus the night shift</h2>
          <ul className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title} className="rounded-2xl border bg-surface p-5">
                <span className="grid size-10 place-items-center rounded-xl bg-primary-soft text-primary-text">
                  <Icon size={19} />
                </span>
                <h3 className="mt-4 font-semibold">{title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{text}</p>
              </li>
            ))}
          </ul>
        </section>

        {/* Pricing */}
        <section id="pricing" aria-labelledby="pricing-title" className="scroll-mt-6 border-y bg-muted/40">
          <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6">
            <div className="mx-auto mb-10 max-w-2xl text-center">
              <h2 id="pricing-title" className="text-3xl font-bold tracking-tight text-balance sm:text-4xl">
                Pay for the inbox, not for every answer
              </h2>
              <p className="mt-3 text-balance text-muted-foreground">
                Your AI runs on your own key, at your provider&apos;s price. Host it yourself for free, or let us run it.
              </p>
            </div>
            <PricingPlans heading="h3" />
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-sm text-muted-foreground sm:px-6">
          <Logo />
          <span>Open source. Self-host it, bring your own LLM. Get some sleep.</span>
        </div>
      </footer>
    </div>
  );
}
