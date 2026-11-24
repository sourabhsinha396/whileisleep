// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import BehaviorPage from "@/app/w/[slug]/ai/behavior/page";
import { LlmSettings } from "@/components/llm-settings";
import { WorkspaceContext } from "@/components/workspace-context";
import type { Organization, User, Workspace } from "@/lib/api";

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });

let host: HTMLDivElement;
let root: Root;
let sent: unknown;

beforeEach(() => {
  host = document.body.appendChild(document.createElement("div"));
  root = createRoot(host);
  sent = undefined;
  vi.stubGlobal("fetch", async (_path: string, init: RequestInit) => {
    sent = JSON.parse(String(init.body));
    return Response.json({});
  });
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});

function show(node: React.ReactNode, role: "owner" | "agent" = "owner") {
  const workspace = { id: 1, slug: "acme", role, llm_ready: true, ai_enabled: true, ai_instructions: "", ai_replies_per_visitor: 50, ai_replies_per_day: 2000 } as Workspace;
  return act(async () =>
    root.render(
      <WorkspaceContext.Provider value={{ me: {} as User, workspace, workspaces: [workspace], reload: async () => {} }}>{node}</WorkspaceContext.Provider>,
    ),
  );
}

const inputs = () => [...host.querySelectorAll<HTMLInputElement>("input[type=number]")];

function type(input: HTMLInputElement, value: string) {
  return act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

it("workspace owners set the workspace's daily limits", async () => {
  await show(<BehaviorPage />);
  const [perVisitor, perDay] = inputs();
  expect([perVisitor.value, perDay.value]).toEqual(["50", "2000"]);
  await type(perVisitor, "10");
  await act(async () => host.querySelector("form")!.requestSubmit());
  expect(sent).toMatchObject({ ai_replies_per_visitor: 10, ai_replies_per_day: 2000 });
});

it("agents only see them", async () => {
  await show(<BehaviorPage />, "agent");
  expect(inputs().map((input) => input.disabled)).toEqual([true, true]);
  expect([...host.querySelectorAll("button")].some((button) => button.textContent === "Save")).toBe(false);
});

it("the organization's limit can be set, and left out", async () => {
  const org = { name: "Acme", providers: [], llm_provider: "openai", llm_model: "", fallback_provider: "", fallback_model: "", ai_replies_per_day: null, workspace_count: 2 };
  await show(<LlmSettings org={org as unknown as Organization} onSaved={() => {}} />);
  const [limit] = inputs();
  const save = () => act(async () => limit.form!.requestSubmit());
  expect(limit.value).toBe("");
  await type(limit, "500");
  await save();
  expect(sent).toEqual({ ai_replies_per_day: 500 });
  await type(limit, "");
  await save();
  expect(sent).toEqual({ ai_replies_per_day: null });
});
