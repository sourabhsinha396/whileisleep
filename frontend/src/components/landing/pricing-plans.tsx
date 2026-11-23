"use client";

import clsx from "clsx";
import { ArrowRight, Check, Cloud, Server } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { CLOUD_PRICE, cloudPrice, dollars, REPO_URL, yearlySaving, type Billing } from "@/lib/pricing";

const SELF_HOSTED = [
  "Every feature, nothing held back",
  "Unlimited workspaces, teammates and conversations",
  "Your own OpenRouter key and model",
  "One server with Docker Compose",
  "Community support",
];

const CLOUD = [
  "Everything in self-hosted",
  "We run it, update it and back it up",
  "Your own OpenRouter key: AI at your provider's price",
  "Email support",
];

const cta = "inline-flex w-full items-center justify-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold transition-colors";

export function PricingPlans() {
  const [billing, setBilling] = useState<Billing>("yearly");
  const price = cloudPrice(billing);

  return (
    <div>
      <div className="flex justify-center">
        <div role="radiogroup" aria-label="Billing period" className="inline-flex rounded-full border bg-muted p-1 text-sm">
          {(["monthly", "yearly"] as const).map((option) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={billing === option}
              onClick={() => setBilling(option)}
              className={clsx(
                "flex items-center gap-2 rounded-full px-4 py-1.5 font-medium transition-colors",
                billing === option ? "bg-surface text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {option === "monthly" ? "Monthly" : "Yearly"}
              {option === "yearly" && (
                <span className="rounded-full bg-success-soft px-2 py-0.5 text-xs font-semibold text-success">Save {yearlySaving()}%</span>
              )}
            </button>
          ))}
        </div>
      </div>

      <div className="mx-auto mt-10 grid max-w-4xl gap-6 md:grid-cols-2">
        <section aria-labelledby="plan-self-hosted" className="flex flex-col rounded-2xl border bg-surface p-7">
          <span className="grid size-10 place-items-center rounded-xl bg-muted text-muted-foreground">
            <Server size={19} />
          </span>
          <h2 id="plan-self-hosted" className="mt-4 text-lg font-bold">
            Self-hosted
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">Run it on your own server.</p>
          <p className="mt-6 flex items-baseline gap-1.5">
            <span className="text-5xl font-extrabold tracking-tight">$0</span>
            <span className="text-sm text-muted-foreground">forever</span>
          </p>
          <p className="mt-1 text-sm text-muted-foreground">Open source</p>
          <Features items={SELF_HOSTED} />
          {REPO_URL && (
            <a href={REPO_URL} target="_blank" rel="noreferrer" className={`${cta} mt-8 border bg-surface hover:bg-muted`}>
              Get the code <ArrowRight size={16} />
            </a>
          )}
        </section>

        <section aria-labelledby="plan-cloud" className="relative flex flex-col rounded-2xl border-2 border-primary bg-surface p-7">
          <span className="absolute -top-3 left-7 rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground">
            Launch price
          </span>
          <span className="grid size-10 place-items-center rounded-xl bg-primary-soft text-primary-text">
            <Cloud size={19} />
          </span>
          <h2 id="plan-cloud" className="mt-4 text-lg font-bold">
            Cloud
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">We host it for you.</p>
          <p className="mt-6 flex items-baseline gap-1.5" aria-live="polite">
            <span className="text-5xl font-extrabold tracking-tight">{dollars(price.perMonth)}</span>
            <span className="text-sm text-muted-foreground">/ month</span>
            {billing === "yearly" && (
              <span className="ml-1 text-lg text-muted-foreground line-through" aria-label={`instead of ${dollars(CLOUD_PRICE.monthly)}`}>
                {dollars(CLOUD_PRICE.monthly)}
              </span>
            )}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">{price.billed}</p>
          <Features items={CLOUD} />
          <Link href="/login" className={`${cta} mt-8 bg-primary text-primary-foreground hover:bg-primary-hover`}>
            Get started <ArrowRight size={16} />
          </Link>
        </section>
      </div>
    </div>
  );
}

function Features({ items }: { items: string[] }) {
  return (
    <ul className="mt-6 flex-1 space-y-3 border-t pt-6 text-sm">
      {items.map((item) => (
        <li key={item} className="flex gap-2.5">
          <Check size={17} className="mt-0.5 shrink-0 text-success" />
          {item}
        </li>
      ))}
    </ul>
  );
}
