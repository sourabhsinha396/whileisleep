"use client";

import clsx from "clsx";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useState } from "react";
import { initials } from "@/lib/format";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "success";

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: "sm" | "md" }) {
  return (
    <button
      className={clsx(
        "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-full font-semibold whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-50",
        size === "md" ? "px-4 py-2 text-sm" : "px-3 py-1.5 text-xs",
        variant === "primary" && "bg-primary text-primary-foreground hover:bg-primary-hover",
        variant === "success" && "bg-success text-white hover:bg-success/90",
        variant === "secondary" && "border bg-surface hover:bg-muted",
        variant === "ghost" && "text-muted-foreground hover:bg-muted hover:text-foreground",
        variant === "danger" && "border border-danger/30 bg-surface text-danger hover:bg-danger-soft",
        className,
      )}
      {...props}
    />
  );
}

export const inputClass =
  "block w-full rounded-md border bg-background px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/30 disabled:opacity-60";

export function Field({ label, hint, children }: { label: string; hint?: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

/** A bordered panel: the building block of every settings page. */
export function Card({
  title,
  description,
  actions,
  className,
  children,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <section className={clsx("rounded-lg border bg-surface p-6 shadow-sm", className)}>
      {(title || actions) && (
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            {title && <h2 className="flex items-center gap-2 text-base font-bold tracking-tight">{title}</h2>}
            {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className="space-y-4">{children}</div>
    </section>
  );
}

type Tone = "neutral" | "primary" | "success" | "warning" | "danger";

export function Badge({ tone = "neutral", className, ...props }: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold whitespace-nowrap",
        tone === "neutral" && "bg-muted text-muted-foreground",
        tone === "primary" && "bg-primary-soft text-primary-text",
        tone === "success" && "bg-success-soft text-success",
        tone === "warning" && "bg-warning-soft text-warning",
        tone === "danger" && "bg-danger-soft text-danger",
        className,
      )}
      {...props}
    />
  );
}

export function Notice({ tone = "warning", children }: { tone?: "warning" | "danger" | "success" | "primary"; children: React.ReactNode }) {
  return (
    <p
      role={tone === "danger" ? "alert" : "status"}
      className={clsx(
        "rounded-md px-3 py-2.5 text-sm",
        tone === "warning" && "bg-warning-soft text-warning",
        tone === "danger" && "bg-danger-soft text-danger",
        tone === "success" && "bg-success-soft text-success",
        tone === "primary" && "bg-primary-soft text-primary-text",
      )}
    >
      {children}
    </p>
  );
}

/** An image over whatever is under it, which shows again if the image can't load. */
export function CoverImage({ src, className }: { src: string; className?: string }) {
  const [failed, setFailed] = useState("");
  if (!src || failed === src) return null;
  // Already small, and served by the CDN: next/image would only add a hop.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt="" onError={() => setFailed(src)} className={clsx("absolute inset-0 size-full bg-white object-cover", className)} />;
}

/** A person's photo, or a soft-coloured disc whose hue is stable for a given name. */
export function Avatar({ name, src = "", online, size = 40 }: { name: string; src?: string; online?: boolean; size?: number }) {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  const hue = Math.abs(hash) % 360;
  return (
    <span
      className="relative inline-grid shrink-0 place-items-center rounded-full font-bold"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.36,
        background: `oklch(0.9 0.06 ${hue})`,
        color: `oklch(0.38 0.1 ${hue})`,
      }}
    >
      {initials(name)}
      <CoverImage src={src} className="rounded-full" />
      {online !== undefined && (
        <span
          className={clsx(
            "absolute -right-0.5 -bottom-0.5 rounded-full border-2 border-surface",
            online ? "bg-success" : "bg-muted-foreground/40",
          )}
          style={{ width: Math.max(10, size * 0.3), height: Math.max(10, size * 0.3) }}
          aria-label={online ? "Online" : "Offline"}
        />
      )}
    </span>
  );
}

export function PageHeader({ title, description, children }: { title: string; description?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b bg-background/90 px-8 py-5 backdrop-blur">
      <div>
        <h1 className="text-xl font-bold tracking-tight">{title}</h1>
        {description && <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

/** Pill tabs, e.g. Online now / Last 7 days. */
export function Segmented<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: React.ReactNode }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-full border bg-muted p-0.5 text-sm">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={clsx(
            "rounded-full px-3.5 py-1.5 font-medium transition-colors",
            value === o.value ? "bg-surface text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function EmptyState({ icon: Icon, title, children }: { icon?: React.ComponentType<{ className?: string }>; title: string; children?: React.ReactNode }) {
  return (
    <div className="grid place-items-center rounded-lg border border-dashed p-10 text-center">
      {Icon && (
        <span className="mb-3 grid size-11 place-items-center rounded-full bg-primary-soft text-primary-text">
          <Icon className="size-5" />
        </span>
      )}
      <p className="font-semibold">{title}</p>
      {children && <div className="mt-1 max-w-sm text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function ErrorText({ children }: { children?: React.ReactNode }) {
  if (!children) return null;
  return (
    <p role="alert" className="text-sm text-danger">
      {children}
    </p>
  );
}

/**
 * The whileisleep mark: a little bot face in a chat bubble.
 * Built for a circle: the bubble sits inside a filled primary disc. The eyes are cut out
 * (even-odd), so they show the disc color through. Keep in sync with app/icon.svg.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <circle cx="16" cy="16" r="16" fill="var(--primary)" />
      <path
        transform="translate(0 -2)"
        fill="#fff"
        fillRule="evenodd"
        d="M12 11h8a4 4 0 0 1 4 4v4a4 4 0 0 1-4 4h-5.5l-3.7 3c-.5.4-1.3.05-1.3-.6v-2.6A4 4 0 0 1 8 19v-4a4 4 0 0 1 4-4zM12.4 15.4a1.1 1.1 0 0 1 2.2 0v1.2a1.1 1.1 0 0 1-2.2 0zM17.4 15.4a1.1 1.1 0 0 1 2.2 0v1.2a1.1 1.1 0 0 1-2.2 0z"
      />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={clsx("flex items-center gap-2", className)}>
      <LogoMark className="size-8" />
      <span className="text-[17px] leading-none font-bold tracking-tight">whileisleep</span>
    </span>
  );
}

/** Light or dark. Both icons render and CSS picks one, so there is no hydration flash. */
export function ThemeToggle({ className }: { className?: string }) {
  const { resolvedTheme, setTheme } = useTheme();
  return (
    <button
      type="button"
      aria-label="Toggle dark mode"
      title="Toggle dark mode"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
      className={clsx(
        "grid size-9 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        className,
      )}
    >
      <Moon className="size-[18px] dark:hidden" />
      <Sun className="hidden size-[18px] dark:block" />
    </button>
  );
}

/** An on/off switch. Put it inside a <label> so the text toggles it too. */
export function Switch({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={clsx(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        checked ? "bg-primary" : "bg-border",
      )}
    >
      <span
        className={clsx(
          "inline-block size-4 rounded-full bg-white shadow-sm transition-transform",
          checked ? "translate-x-[18px]" : "translate-x-0.5",
        )}
      />
    </button>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="grid h-full min-h-40 place-items-center">
      <span className="flex items-center gap-3 text-sm text-muted-foreground">
        <span className="size-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        {label}
      </span>
    </div>
  );
}
