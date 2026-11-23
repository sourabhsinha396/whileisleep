import clsx from "clsx";
import { initials } from "@/lib/format";

export function Button({
  variant = "primary",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger" }) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:opacity-50",
        variant === "primary" && "bg-brand text-white hover:bg-brand/90",
        variant === "secondary" && "border border-gray-300 bg-white hover:bg-gray-50",
        variant === "ghost" && "hover:bg-gray-100",
        variant === "danger" && "border border-red-200 bg-white text-red-700 hover:bg-red-50",
        className,
      )}
      {...props}
    />
  );
}

export const inputClass =
  "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/15";

export function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-gray-800">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-gray-500">{hint}</span>}
    </label>
  );
}

export function Avatar({ name, online, size = 40 }: { name: string; online?: boolean; size?: number }) {
  return (
    <span className="relative inline-grid shrink-0 place-items-center rounded-full bg-indigo-100 font-semibold text-indigo-700" style={{ width: size, height: size, fontSize: size * 0.36 }}>
      {initials(name)}
      {online !== undefined && (
        <span
          className={clsx("absolute right-0 bottom-0 h-3 w-3 rounded-full border-2 border-white", online ? "bg-green-500" : "bg-gray-300")}
          aria-label={online ? "Online" : "Offline"}
        />
      )}
    </span>
  );
}

export function PageHeader({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-gray-200 bg-white px-8 py-5">
      <h1 className="text-xl font-semibold">{title}</h1>
      <div className="flex gap-2">{children}</div>
    </div>
  );
}

export function ErrorText({ children }: { children?: React.ReactNode }) {
  if (!children) return null;
  return <p className="text-sm text-red-700">{children}</p>;
}
