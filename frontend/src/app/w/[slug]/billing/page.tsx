"use client";

import clsx from "clsx";
import { ExternalLink } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { OrganizationOnly } from "@/components/organization-only";
import { Button, ErrorText, Notice, PageHeader, Spinner } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api } from "@/lib/api";
import { type Billing, canSubscribe, checkoutResult, headline, type Interval } from "@/lib/billing";
import { dollars } from "@/lib/pricing";
import { usePoll } from "@/lib/use-poll";

export default function BillingPage() {
  return (
    <>
      <PageHeader title="Billing" description="The plan of your organization. It covers all its workspaces." />
      <OrganizationOnly>{() => <Plan />}</OrganizationOnly>
    </>
  );
}

const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const ask = (body: object) => api<Billing>("/billing/sync", { method: "POST", body });

/** Asks Dodo when the page opens. Coming back from checkout, until the payment has gone through. */
function useFreshPlan(onPlan: (billing: Billing) => void) {
  // Read once, when the page opens: the address is cleaned below.
  const [result] = useState(() => checkoutResult(window.location.search));
  const id = result && !result.failed ? result.subscriptionId : "";
  const [message, setMessage] = useState<"" | "confirming" | "slow" | "failed">(result?.failed ? "failed" : id ? "confirming" : "");
  useEffect(() => {
    // So reloading the page doesn't repeat it.
    if (result) window.history.replaceState(null, "", window.location.pathname);
    let gone = false;
    async function confirm() {
      // The first tries are quick; after them it keeps asking for half an hour.
      for (let attempt = 0; attempt < 66; attempt++) {
        if (attempt) await pause(attempt < 6 ? 3000 : 30000);
        if (gone) return;
        // A failed try isn't the end.
        const billing = await ask({ subscription_id: id }).catch(() => null);
        if (gone) return;
        if (billing) onPlan(billing);
        if (billing?.state === "active") return setMessage("");
        if (attempt === 5) setMessage("slow");
      }
    }
    if (id) confirm();
    // They may have paid without coming back here, or changed something in the portal. If it can't
    // be asked, what we know is shown.
    else ask({}).then((billing) => !gone && onPlan(billing), () => {});
    return () => {
      gone = true;
    };
  }, [result, id, onPlan]);
  return message;
}

function Plan() {
  const { workspace, reload } = useWorkspace();
  const { data: billing, setData, error: loadError, reload: reread } = usePoll(useCallback(() => api<Billing>("/billing"), []), 30000);
  const [interval, setInterval] = useState<Interval>("yearly");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const back = useFreshPlan(
    useCallback(
      (fresh: Billing) => {
        setData(fresh);
        // The sidebar shows it too.
        reload();
      },
      // `reload` is new on every render of the layout; calling an older one is fine.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [setData],
    ),
  );

  async function open(path: string, body: object) {
    setError("");
    setBusy(true);
    try {
      const { url } = await api<{ url: string }>(path, { method: "POST", body: { workspace: workspace.slug, ...body } });
      window.location.assign(url);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
      // It may have found a plan they already paid for.
      reread();
    }
  }

  if (!billing) return loadError ? <ErrorText>{loadError}</ErrorText> : <Spinner />;
  if (billing.state === "off") return <Notice tone="success">Billing is off on this installation. Everything is free.</Notice>;

  const { tone, text } = headline(billing);
  return (
    <div className="space-y-5">
      {back === "confirming" && <Notice tone="primary">Confirming your payment…</Notice>}
      {back === "slow" && <Notice>Your payment is still being processed. This page updates by itself when it is done.</Notice>}
      {back === "failed" && <Notice tone="danger">The payment didn&apos;t go through, and you weren&apos;t charged. You can try again.</Notice>}

      <section className="space-y-4 rounded-lg border bg-surface p-6 shadow-sm">
        <Notice tone={tone}>{text}</Notice>
        {billing.subscription && billing.state === "active" && (
          <p className="text-sm">
            <span className="font-semibold">Cloud, {billing.subscription.interval}</span>{" "}
            <span className="text-muted-foreground">
              {dollars(billing.prices[billing.subscription.interval] / 100)} a {billing.subscription.interval === "monthly" ? "month" : "year"}, plus tax
            </span>
          </p>
        )}
        {billing.can_manage && (
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="secondary" disabled={busy} onClick={() => open("/billing/portal", {})}>
              Manage plan <ExternalLink size={15} />
            </Button>
            <span className="text-sm text-muted-foreground">Change your card, get invoices or cancel.</span>
          </div>
        )}
      </section>

      {canSubscribe(billing) && (
        <section className="space-y-4 rounded-lg border bg-surface p-6 shadow-sm">
          <div>
            <h2 className="text-base font-bold tracking-tight">Cloud</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Keeps the AI answering after the trial. It runs on your own AI key, which you pay separately.
            </p>
          </div>
          <div role="radiogroup" aria-label="Billing period" className="grid gap-3 sm:grid-cols-2">
            {(["yearly", "monthly"] as const).map((option) => (
              <button
                key={option}
                type="button"
                role="radio"
                aria-checked={interval === option}
                onClick={() => setInterval(option)}
                className={clsx(
                  "rounded-lg border p-4 text-left transition-colors",
                  interval === option ? "border-primary ring-1 ring-primary" : "hover:bg-muted",
                )}
              >
                <span className="block text-sm font-semibold capitalize">{option}</span>
                <span className="mt-1 block text-2xl font-extrabold tracking-tight">{dollars(billing.prices[option] / 100)}</span>
                <span className="block text-sm text-muted-foreground">a {option === "monthly" ? "month" : "year"}, plus tax</span>
              </button>
            ))}
          </div>
          <Button disabled={busy || back === "confirming"} onClick={() => open("/billing/checkout", { interval })}>
            {busy ? "Opening…" : "Subscribe"}
          </Button>
        </section>
      )}
      <ErrorText>{error}</ErrorText>
    </div>
  );
}
