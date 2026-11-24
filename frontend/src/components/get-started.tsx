"use client";

import clsx from "clsx";
import { ArrowRight, Check, ChevronRight, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, type SetupStep, type Workspace } from "@/lib/api";
import { guide, type GuideStep, progress, settled } from "@/lib/get-started";
import { useDismiss } from "@/lib/use-dismiss";
import { usePoll } from "@/lib/use-poll";

const hiddenKey = (workspaceId: number) => `whileisleep:guide-hidden:${workspaceId}`;

/** The steps of this person's guide; empty while loading and once everything is done. */
export function useGuide(workspace: Workspace | undefined): GuideStep[] {
  const id = workspace?.role === "owner" ? workspace.id : undefined;
  const isOrganizationOwner = workspace?.is_organization_owner ?? false;
  // Once nothing is left to ask about.
  const finished = useRef<number>(undefined);
  const { data } = usePoll(
    useCallback(async () => {
      if (id === undefined) return null;
      if (finished.current === id) return { id, setup: [] };
      const setup = await api<SetupStep[]>(`/workspaces/${id}/setup`);
      if (settled(setup, isOrganizationOwner, isHidden(id))) finished.current = id;
      return { id, setup };
    }, [id, isOrganizationOwner]),
    15000,
  );
  // Right after switching workspaces, `data` is still the previous one's.
  if (!workspace || !data || data.id !== id) return [];
  const steps = guide(workspace, data.setup);
  const { finished: nothingLeft, dismissible } = progress(steps);
  return nothingLeft || (dismissible && isHidden(workspace.id)) ? [] : steps;
}

/** One slim row in the sidebar: the next step and how far setup is. It opens the whole guide
 *  in a panel beside the sidebar, so the page stays in view. */
export function GetStarted({ steps, workspaceId }: { steps: GuideStep[]; workspaceId: number }) {
  const [open, setOpen] = useState(false);
  const [hidden, setHidden] = useState(false);
  const panelId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  const ref = useDismiss(open, close);
  const { done, total, next, dismissible } = progress(steps);

  useEffect(() => {
    if (open) panelRef.current?.focus();
  }, [open]);

  // Back to where the keyboard was, not the top of the page.
  function closeAndReturn() {
    close();
    buttonRef.current?.focus();
  }

  if (hidden) return null;
  return (
    <div className="relative" ref={ref}>
      <button
        ref={buttonRef}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? panelId : undefined}
        aria-label={`Get started, ${done} of ${total} done. Next: ${next?.label ?? "nothing"}`}
        className={clsx("block w-full rounded-md px-3 py-2 text-left text-xs transition-colors hover:bg-muted", open && "bg-muted")}
      >
        <span className="flex items-center gap-2">
          <span className="min-w-0 flex-1 truncate">
            <span className="text-muted-foreground">Next:</span> <span className="font-medium">{next?.label}</span>
          </span>
          <span className="text-muted-foreground tabular-nums">
            {done}/{total}
          </span>
          <ChevronRight size={14} className="shrink-0 text-muted-foreground" />
        </span>
        <Bar done={done} total={total} className="mt-2 h-1" />
      </button>

      {open && (
        <div
          ref={panelRef}
          id={panelId}
          role="dialog"
          aria-label="Get started"
          tabIndex={-1}
          onKeyDown={(e) => e.key === "Escape" && closeAndReturn()}
          className="absolute bottom-0 left-full z-40 ml-3 max-h-[80vh] w-88 max-w-[calc(100vw-2rem)] overflow-y-auto rounded-xl border bg-surface p-4 shadow-xl outline-none"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Get started</h2>
            <button onClick={closeAndReturn} aria-label="Close" className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground">
              <X size={15} />
            </button>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {done} of {total} done. Nothing here is required.
          </p>
          <div role="progressbar" aria-label="Setup progress" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
            <Bar done={done} total={total} className="mt-3 h-1.5" />
          </div>
          <ol className="mt-3 space-y-1">
            {steps.map((step, i) => (
              <li key={step.key}>
                <Step step={step} number={i + 1} isNext={step === next} onGo={close} />
              </li>
            ))}
          </ol>
          {dismissible && (
            <button
              onClick={() => {
                hide(workspaceId);
                setHidden(true);
              }}
              className="mt-2 w-full rounded-lg px-2.5 py-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              Hide this guide
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Bar({ done, total, className }: { done: number; total: number; className: string }) {
  return (
    <span className={clsx("block overflow-hidden rounded-full bg-primary/15", className)}>
      <span className="block h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${Math.max(done / total, 0.04) * 100}%` }} />
    </span>
  );
}

function Step({ step, number, isNext, onGo }: { step: GuideStep; number: number; isNext: boolean; onGo: () => void }) {
  return (
    <Link
      href={step.href}
      target={step.newTab ? "_blank" : undefined}
      onClick={onGo}
      aria-current={isNext ? "step" : undefined}
      className={clsx("flex items-start gap-3 rounded-lg p-2.5 transition-colors", isNext ? "bg-primary-soft" : "hover:bg-muted")}
    >
      <span
        className={clsx(
          "grid size-5 shrink-0 place-items-center rounded-full text-[11px] font-bold",
          step.done ? "bg-success-soft text-success" : isNext ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground",
        )}
      >
        {step.done ? <Check size={12} strokeWidth={3} /> : number}
      </span>
      <span className="min-w-0 flex-1">
        <span className={clsx("block text-sm", step.done ? "text-muted-foreground" : "font-medium")}>
          {step.label}
          {step.done && <span className="sr-only"> (done)</span>}
          {step.optional && !step.done && <span className="ml-1.5 font-normal text-muted-foreground">Optional</span>}
        </span>
        {!step.done && <span className="mt-0.5 block text-xs text-muted-foreground">{step.why}</span>}
      </span>
      {isNext && <ArrowRight size={15} className="mt-0.5 shrink-0 text-primary-text" />}
    </Link>
  );
}

// Remembered in this browser. Storage can be blocked; hiding then lasts until the page reloads.
function isHidden(workspaceId: number): boolean {
  try {
    return localStorage.getItem(hiddenKey(workspaceId)) === "1";
  } catch {
    return false;
  }
}

function hide(workspaceId: number) {
  try {
    localStorage.setItem(hiddenKey(workspaceId), "1");
  } catch {
    /* ignore */
  }
}
