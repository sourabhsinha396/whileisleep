import { inputClass } from "@/components/ui";

/** How many AI replies a day. */
export function LimitInput({
  value,
  onChange,
  ...rest
}: { value: string; onChange: (value: string) => void } & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  return <input className={inputClass} type="number" min={1} max={1000000} step={1} value={value} onChange={(e) => onChange(e.target.value)} {...rest} />;
}
