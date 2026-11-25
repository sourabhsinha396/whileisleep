import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LlmSettings } from "@/components/llm-settings";
import type { LlmProvider, Organization, ProviderId } from "@/lib/api";
import { KEY_EXAMPLES, keyRemovalWarning, llmStatus, MODEL_EXAMPLES } from "@/lib/llm";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const api = vi.hoisted(() => vi.fn());
vi.mock("@/lib/api", () => ({ api }));
vi.mock("@/components/workspace-context", () => ({ useWorkspace: () => ({ reload: async () => {} }) }));

const MODELS = [
  { id: "gpt-x", name: "GPT X", recommended: true, tier: "low" },
  { id: "gpt-y", name: "GPT Y", recommended: true, tier: "low" },
  { id: "gpt-z", name: "Big Z", recommended: true, tier: "high" },
  { id: "gpt-old", name: "GPT Old", recommended: false, tier: "" },
];

const NAMES: Record<ProviderId, string> = { openai: "OpenAI", anthropic: "Anthropic", google: "Google Gemini", openrouter: "OpenRouter" };

function organization(keys: ProviderId[], rest: Partial<Organization> = {}): Organization {
  const providers = (Object.keys(NAMES) as ProviderId[]).map(
    (id): LlmProvider => ({ id, name: NAMES[id], keys_url: `https://${id}.example`, has_key: keys.includes(id), key_hint: keys.includes(id) ? "…1234" : "" }),
  );
  return {
    id: 1,
    name: "Acme",
    providers,
    llm_provider: "openai",
    llm_model: "gpt-x",
    fallback_provider: "",
    fallback_model: "",
    ai_replies_per_day: null,
    alert_sound: "chime",
    alert_volume: 60,
    alert_on: "person",
    alert_repeat: 0,
    llm_ready: true,
    workspace_count: 1,
    ...rest,
  };
}

describe("llmStatus", () => {
  const fallback = { fallback_provider: "anthropic", fallback_model: "claude-y" } as const;

  it("names the model and who takes over", () => {
    expect(llmStatus(organization(["openai", "anthropic"], fallback))).toEqual({
      ok: true,
      text: "Ready: OpenAI gpt-x. If it fails, Anthropic claude-y takes over.",
    });
  });

  it("is fine without a fallback", () => {
    expect(llmStatus(organization(["openai"]))).toEqual({ ok: true, text: "Ready: OpenAI gpt-x. There is no fallback." });
  });

  it("warns about a fallback that can't take over", () => {
    expect(llmStatus(organization(["openai"], fallback)).text).toContain("still needs your Anthropic key");
    expect(llmStatus(organization(["openai", "anthropic"], { ...fallback, fallback_model: "" })).text).toContain("still needs a model");
    expect(llmStatus(organization(["openai"], fallback)).ok).toBe(false);
  });

  it("says when the fallback is doing all the work", () => {
    const status = llmStatus(organization(["anthropic"], fallback));
    expect(status.ok).toBe(false);
    expect(status.text).toBe("Your model needs your OpenAI key, so the fallback, Anthropic claude-y, writes every reply.");
  });

  it("says what is missing when nothing works", () => {
    expect(llmStatus(organization([])).text).toContain("Add a key and pick a model");
    expect(llmStatus(organization(["anthropic"])).text).toContain("needs your OpenAI key");
    expect(llmStatus(organization(["openai"], { llm_model: "" })).text).toContain("isn't picked yet");
  });
});

it("says what a removed key was used by", () => {
  const org = organization(["openai", "anthropic"], { fallback_provider: "openai", fallback_model: "gpt-y" });
  expect(keyRemovalWarning(org, org.providers[0])).toBe("Remove the OpenAI key? It is used by your model and your fallback.");
  expect(keyRemovalWarning(org, org.providers[1])).toBe("Remove the Anthropic key?");
});

it("has an example for every provider", () => {
  expect(Object.keys(MODEL_EXAMPLES).sort()).toEqual(Object.keys(NAMES).sort());
  expect(Object.keys(KEY_EXAMPLES).sort()).toEqual(Object.keys(NAMES).sort());
});

describe("the settings page", () => {
  let root: Root;
  let box: HTMLElement;
  let onSaved: ReturnType<typeof vi.fn<(org: Organization) => void>>;

  beforeEach(() => {
    box = document.body.appendChild(document.createElement("div"));
    root = createRoot(box);
    onSaved = vi.fn();
    api.mockReset();
    api.mockImplementation(async (path: string) => (path.includes("/models/") ? MODELS : organization([])));
  });

  afterEach(() => {
    act(() => root.unmount());
    box.remove();
  });

  const show = (org: Organization) => act(async () => root.render(<LlmSettings org={org} onSaved={onSaved} />));
  const button = (text: string, within: Element = box) => [...within.querySelectorAll("button")].find((b) => b.textContent?.trim() === text)!;
  const labelled = <T extends Element>(label: string) => box.querySelector<T>(`[aria-label="${label}"]`)!;

  async function fill(field: HTMLInputElement, value: string) {
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(field, value);
      field.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  const provider = (label: string) => box.querySelector<HTMLElement>(`button[aria-label^="Provider of the ${label}"]`)!;

  async function choose(label: string, name: string) {
    await act(async () => provider(label).click());
    const option = [...provider(label).parentElement!.querySelectorAll<HTMLElement>("li")].find((li) => li.textContent!.startsWith(name))!;
    await act(async () => option.click());
  }

  const submit = (field: Element) => act(async () => void field.closest("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  const offered = () => [...box.querySelectorAll('[role="option"] span span:first-child')].map((o) => o.textContent);
  const sent = (method: string) => api.mock.calls.filter(([, options]) => options?.method === method);

  it("lists every provider and whether it has a key", async () => {
    await show(organization(["anthropic"]));
    const rows = [...box.querySelectorAll("ul.divide-y > li")].map((li) => li.textContent);
    expect(rows).toHaveLength(4);
    expect(rows[0]).toContain("OpenAINo key");
    expect(rows[1]).toContain("AnthropicKey …1234");
  });

  it("saves a key for its own provider", async () => {
    await show(organization([]));
    await act(async () => button("Add key", box.querySelectorAll("li")[1]).click());
    const input = labelled<HTMLInputElement>("Anthropic API key");
    await fill(input, " sk-ant-new ");
    await submit(input);
    expect(sent("PUT")).toEqual([["/organization/keys/anthropic", { method: "PUT", body: { api_key: "sk-ant-new" } }]]);
    expect(onSaved).toHaveBeenCalled();
    expect(labelled("Anthropic API key")).toBeNull();
  });

  it("picks a fallback, and drops a model id that belongs to another provider", async () => {
    await show(organization(["openai", "anthropic"]));
    expect(labelled("The fallback's id")).toBeNull();
    await choose("fallback", "OpenAI");
    await fill(labelled<HTMLInputElement>("The fallback's id"), "gpt-z");
    await choose("fallback", "Anthropic");
    const id = labelled<HTMLInputElement>("The fallback's id");
    expect(id.value).toBe("");
    await fill(id, "claude-y");
    await submit(id);
    expect(sent("PATCH")).toEqual([
      ["/organization", { method: "PATCH", body: { fallback_provider: "anthropic", fallback_model: "claude-y" } }],
    ]);
  });

  it("removes the fallback", async () => {
    await show(organization(["openai", "anthropic"], { fallback_provider: "anthropic", fallback_model: "claude-y" }));
    await choose("fallback", "None");
    await submit(provider("fallback"));
    expect(sent("PATCH")[0][1].body).toEqual({ fallback_provider: "", fallback_model: "" });
  });

  it("shows what the server refuses", async () => {
    await show(organization(["openai"]));
    api.mockRejectedValueOnce(new Error("Pick a different model."));
    const id = labelled<HTMLInputElement>("The model's id");
    await fill(id, "gpt-new");
    await submit(id);
    expect(box.querySelector('[role="alert"]')?.textContent).toBe("Pick a different model.");
  });

  it("offers only the recommended models, and knows the others when typed", async () => {
    await show(organization(["openai"]));
    const id = labelled<HTMLInputElement>("The model's id");
    await act(async () => id.click());
    expect(offered()).toEqual(["GPT X", "GPT Y", "Big Z"]);
    await fill(id, "gpt-old");
    expect(box.textContent).not.toContain("Not in OpenAI's list");
    await fill(id, "gpt-typo");
    expect(box.textContent).toContain("Not in OpenAI's list");
  });

  it("groups the models by tier and picks one with a click", async () => {
    await show(organization(["openai"]));
    const id = labelled<HTMLInputElement>("The model's id");
    await act(async () => id.click());
    expect([...box.querySelectorAll('[role="presentation"]')].map((p) => p.textContent)).toEqual(["Low cost", "High end"]);
    await act(async () => box.querySelectorAll<HTMLElement>('[role="option"]')[2].click());
    expect(id.value).toBe("gpt-z");
    expect(offered()).toEqual([]);
    expect(sent("PATCH")).toEqual([]);
  });

  it("narrows as you type, and arrows and Enter pick", async () => {
    await show(organization(["openai"]));
    const id = labelled<HTMLInputElement>("The model's id");
    const press = (key: string) => act(async () => void id.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })));
    await fill(id, "gpt y");
    expect(offered()).toEqual(["GPT Y"]);
    await press("ArrowDown");
    await press("Enter");
    expect(id.value).toBe("gpt-y");
    // Opened again, it offers everything, not only what matches the pick.
    await press("ArrowDown");
    expect(offered()).toHaveLength(3);
    await press("Escape");
    expect(offered()).toEqual([]);
    expect(id.value).toBe("gpt-y");
  });

  it("shows no list when nothing matches, so any id can be typed and saved", async () => {
    await show(organization(["openai"]));
    const id = labelled<HTMLInputElement>("The model's id");
    await fill(id, "something-else");
    expect(offered()).toEqual([]);
    await submit(id);
    expect(sent("PATCH")[0][1].body).toEqual({ llm_provider: "openai", llm_model: "something-else" });
  });

  it("asks for a model list only where there is a key to read it with", async () => {
    await show(organization(["openai"], { fallback_provider: "anthropic", fallback_model: "claude-y" }));
    expect(api.mock.calls.map(([path]) => path)).toEqual(["/organization/models/openai"]);
    expect(box.textContent).toContain("Add your Anthropic key above");
  });
});
