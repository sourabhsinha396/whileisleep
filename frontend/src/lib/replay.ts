import type { PostHog, PostHogConfig } from "posthog-js";

/**
 * Session replays with PostHog, only where its key is set. The recordings are of our own site and dashboard; the
 * widget on other sites never loads this. What customers and their visitors write stays out of them: in the dashboard
 * every text but the menus is masked, and the inbox and the visitors are left out (class "ph-no-capture").
 */

/** Pages with customers' data on them. */
const PRIVATE = /^\/(w|app|new|integrations|demo)(\/|$)/;
/** Pages never loaded with it: a code is in the address, or another site is being tried out. */
const OFF = /^\/(integrations|demo|reset-password)(\/|$)/;

/** Attributes that a person, a file or an address can be read from. */
const TELLING = ["title", "alt", "aria-label", "aria-description", "href", "src", "srcset", "value", "content"];

const onPrivatePage = () => PRIVATE.test(window.location.pathname);

export function maskText(text: string, element?: Element | null): string {
  // Menus are the same for everyone.
  if (!onPrivatePage() || element?.closest("nav")) return text;
  return text.replace(/\S/g, "*");
}

export function maskAttribute(name: string, value: string, element?: Element): string {
  if (!onPrivatePage() || !TELLING.includes(name)) return value;
  // Without its styles a page can't be shown.
  if (element?.closest("head, nav")) return value;
  return "*";
}

/** An address without what follows the path, where ids and codes are. */
function plainUrl(value: unknown): unknown {
  return typeof value === "string" && /^https?:/.test(value) ? value.replace(/[?#].*$/, "") : value;
}

type Event = { properties?: Record<string, unknown>; $set?: Record<string, unknown>; $set_once?: Record<string, unknown> };

export function withoutQueries<T extends Event>(event: T | null): T | null {
  for (const values of [event?.properties, event?.$set, event?.$set_once]) {
    for (const key of Object.keys(values ?? {})) if (/(url|referrer)$/.test(key)) values![key] = plainUrl(values![key]);
  }
  return event;
}

export function replayConfig(host: string): Partial<PostHogConfig> {
  return {
    api_host: host,
    defaults: "2026-05-30",
    persistence: "localStorage",
    person_profiles: "identified_only",
    respect_dnt: true,
    // Pages and replays, nothing else.
    capture_pageview: "history_change",
    autocapture: false,
    rageclick: false,
    capture_dead_clicks: false,
    capture_heatmaps: false,
    capture_exceptions: false,
    capture_performance: false,
    disable_surveys: true,
    enable_recording_console_log: false,
    before_send: (event) => withoutQueries(event),
    session_recording: {
      maskAllInputs: true,
      maskTextSelector: "*",
      maskTextFn: maskText,
      maskAttributeFn: maskAttribute,
      blockClass: "ph-no-capture",
      recordHeaders: false,
      recordBody: false,
    },
  };
}

let loading: Promise<PostHog | null> | null = null;

/** Starts recording. Without a key, or when it can't load, nothing happens. */
export function startReplay(token = process.env.NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN, host = process.env.NEXT_PUBLIC_POSTHOG_HOST): void {
  if (!token || !host || loading || OFF.test(window.location.pathname)) return;
  loading = import("posthog-js").then(
    ({ default: posthog }) => posthog.init(token, replayConfig(host)) ?? null,
    () => null,
  );
}

/**
 * Whose replay this is, so it can be found for someone who asks for help. Only their number, after our name: a PostHog
 * project can hold several products, each with a user 7.
 */
export function identifyUser(id: number): void {
  void loading?.then((posthog) => posthog?.identify(`whileisleep-${id}`));
}

/** They logged out: what comes next may be someone else. */
export function forgetUser(): void {
  void loading?.then((posthog) => posthog?.reset());
}
