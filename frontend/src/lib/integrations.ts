import { api, type Connection, type Integration, type PluginField } from "@/lib/api";

export type Values = Record<string, string>;

/** The plugin's SVG as an image, so nothing in it can run. */
export function iconUrl(svg: string): string {
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

/** What a form starts with: what was saved, else each field's default. */
export function initialValues(fields: PluginField[], saved: Values = {}): Values {
  return Object.fromEntries(fields.map((field) => [field.name, saved[field.name] || field.default]));
}

/** Whether everything that is needed is filled in. A saved secret needn't be typed again. */
export function complete(fields: PluginField[], values: Values, secrets: string[] = []): boolean {
  return fields.every((field) => !field.required || values[field.name]?.trim() || (field.kind === "secret" && secrets.includes(field.name)));
}

/** "choices" are kept as their values with commas between, in the order they are offered. */
export function toggled(field: PluginField, value: string, option: string): string {
  const chosen = new Set(value.split(",").filter(Boolean));
  if (!chosen.delete(option)) chosen.add(option);
  return field.options
    .map((o) => o.value)
    .filter((v) => chosen.has(v))
    .join(",");
}

export interface Status {
  tone: "success" | "warning" | "danger" | "neutral";
  label: string;
}

export function statusOf(available: boolean, connection: Pick<Connection, "ready" | "last_error">): Status {
  if (!available) return { tone: "neutral", label: "Off on this server" };
  if (connection.last_error) return { tone: "danger", label: "Not working" };
  return connection.ready ? { tone: "success", label: "Working" } : { tone: "warning", label: "Finish setting up" };
}

/** One word for the whole integration in the list: what most needs looking at. */
export function summaryOf(integration: Pick<Integration, "available" | "connections">): Status | null {
  const { available, connections } = integration;
  if (!connections.length) return available ? null : { tone: "neutral", label: "Not set up on this server" };
  const all = connections.map((connection) => statusOf(available, connection));
  return all.find((s) => s.tone === "danger") ?? all.find((s) => s.tone === "warning") ?? all[0];
}

/** What the service's page sent the owner back with. */
export function readCallback(search: string): { code: string; state: string } | { error: string } {
  const params = new URLSearchParams(search);
  const [code, state] = [params.get("code"), params.get("state")];
  if (code && state) return { code, state };
  return { error: params.get("error") === "access_denied" ? "You cancelled, so nothing was connected." : "Nothing was connected. Try again." };
}

interface JobResult<T> {
  done: boolean;
  error: string;
  result: T;
}

const EVERY_MS = 700;
const PATIENCE_MS = 60000;

/** Waits for a job the server does in the background, and returns its result. Services may be slow,
 * so no request waits for one. */
export async function finish<T>(job: string, wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))): Promise<T> {
  for (let waited = 0; waited <= PATIENCE_MS; waited += EVERY_MS) {
    const state = await api<JobResult<T>>(`/integrations/jobs/${job}`);
    if (state.error) throw new Error(state.error);
    if (state.done) return state.result;
    await wait(EVERY_MS);
  }
  throw new Error("This is taking too long. Try again in a moment.");
}

/** Starts a job and waits for it. */
export async function run<T>(path: string, init: { method: string; body?: unknown }): Promise<T> {
  const { job } = await api<{ job: string }>(path, init);
  return finish<T>(job);
}
