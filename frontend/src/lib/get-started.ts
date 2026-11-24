import type { SetupStep, Workspace } from "@/lib/api";

/** One line of the "Get started" guide in the sidebar. */
export interface GuideStep {
  key: string;
  label: string;
  /** Why it is worth doing, shown on the step to do next. */
  why: string;
  href: string;
  /** Opens beside the dashboard instead of replacing it. */
  newTab?: boolean;
  /** Worth doing, but most people are fine without it. */
  optional?: boolean;
  done: boolean;
}

const ORGANIZATION_STEPS = ["ai", "storage"];
const OPTIONAL_STEPS = ["storage"];

type Viewer = Pick<Workspace, "slug" | "public_key" | "role" | "is_organization_owner">;

/** What this person can do to finish setting up, in order. The server says which are done. */
export function guide(workspace: Viewer, setup: SetupStep[]): GuideStep[] {
  if (workspace.role !== "owner") return [];
  const page = (href: string) => `/w/${workspace.slug}/${href}`;
  const known: Record<string, Omit<GuideStep, "key" | "done">> = {
    install: {
      label: "Install the chat",
      why: "Paste one script tag and visitors can write to you.",
      href: page("settings/install"),
    },
    article: {
      label: "Publish an article",
      why: "Visitors read it, and the AI answers from it.",
      href: page("knowledge"),
    },
    chat: {
      label: "Send a test chat",
      why: "See what a visitor sees, then answer from your inbox.",
      href: `/demo?key=${workspace.public_key}`,
      newTab: true,
    },
  };
  // These belong to the organization; nobody else can open their pages.
  if (workspace.is_organization_owner) {
    known.ai = {
      label: "Connect your AI",
      why: "Add your OpenRouter key so the agent can write answers.",
      href: page("settings/ai-model"),
    };
    known.storage = {
      label: "Connect storage",
      why: "Add images to articles, kept in your own R2 or S3 bucket.",
      href: page("settings/storage"),
    };
  }
  // A step this version of the dashboard doesn't know is left out.
  return setup.flatMap(({ key, done }) => (known[key] ? [{ key, done, optional: OPTIONAL_STEPS.includes(key), ...known[key] }] : []));
}

/** Whether nothing is left to ask the server about: all done, or only an optional step someone hid. */
export function settled(setup: SetupStep[], isOrganizationOwner: boolean, hidden: boolean): boolean {
  const left = setup.filter((step) => !step.done && (isOrganizationOwner || !ORGANIZATION_STEPS.includes(step.key)));
  return left.every((step) => hidden && OPTIONAL_STEPS.includes(step.key));
}

/** How far along a guide is. */
export function progress(steps: GuideStep[]) {
  const done = steps.filter((step) => step.done).length;
  const left = steps.filter((step) => !step.done);
  return {
    done,
    total: steps.length,
    next: left.at(0),
    finished: left.length === 0,
    /** Only optional steps are left, so the guide may be put away. */
    dismissible: left.length > 0 && left.every((step) => step.optional),
  };
}
