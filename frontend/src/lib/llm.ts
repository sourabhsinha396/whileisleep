import type { LlmModel, LlmProvider, Organization, ProviderId } from "@/lib/api";

/** What a model id looks like at each provider, shown until one is typed. */
export const MODEL_EXAMPLES: Record<ProviderId, string> = {
  openai: "gpt-6-luna",
  anthropic: "claude-haiku-5-5",
  google: "gemini-3.8-flash",
  openrouter: "provider/model",
};

/** What a key looks like at each provider. */
export const KEY_EXAMPLES: Record<ProviderId, string> = {
  openai: "sk-proj-…",
  anthropic: "sk-ant-…",
  google: "AIza…",
  openrouter: "sk-or-v1-…",
};

/** The headings of the model picker. */
export const TIERS: Record<Exclude<LlmModel["tier"], "">, string> = { low: "Low cost", mid: "Mid range", high: "High end" };

/** The models whose name or id has every word typed. */
export function matchingModels(models: LlmModel[], typed: string): LlmModel[] {
  const words = typed.toLowerCase().split(/\s+/).filter(Boolean);
  return models.filter((m) => words.every((word) => `${m.name} ${m.id}`.toLowerCase().includes(word)));
}

type LlmSettings = Pick<Organization, "providers" | "llm_provider" | "llm_model" | "fallback_provider" | "fallback_model">;

export function providerOf(org: Pick<Organization, "providers">, id: ProviderId | ""): LlmProvider | undefined {
  return org.providers.find((p) => p.id === id);
}

/** Whether the agent can answer, and who does when something goes wrong. */
export function llmStatus(org: LlmSettings): { ok: boolean; text: string } {
  const main = providerOf(org, org.llm_provider);
  const fallback = providerOf(org, org.fallback_provider);
  const mainReady = Boolean(main?.has_key && org.llm_model);
  const fallbackReady = Boolean(fallback?.has_key && org.fallback_model);
  const mainName = `${main?.name} ${org.llm_model}`;
  const fallbackName = `${fallback?.name} ${org.fallback_model}`;

  if (mainReady && fallbackReady) return { ok: true, text: `Ready: ${mainName}. If it fails, ${fallbackName} takes over.` };
  if (mainReady && fallback) {
    const missing = fallback.has_key ? "a model" : `your ${fallback.name} key`;
    return { ok: false, text: `Ready: ${mainName}. The fallback still needs ${missing}.` };
  }
  if (mainReady) return { ok: true, text: `Ready: ${mainName}. There is no fallback.` };

  const missing = org.llm_model ? `needs your ${main?.name} key` : "isn't picked yet";
  if (fallbackReady) return { ok: false, text: `Your model ${missing}, so the fallback, ${fallbackName}, writes every reply.` };
  if (!org.providers.some((p) => p.has_key)) {
    return { ok: false, text: "Add a key and pick a model. Until then the agent only matches help articles by keyword." };
  }
  return { ok: false, text: `Your model ${missing}. Until then the agent only matches help articles by keyword.` };
}

/** What stops working when a provider's key is removed. */
export function keyRemovalWarning(org: LlmSettings, provider: LlmProvider): string {
  const uses = [
    org.llm_provider === provider.id && org.llm_model && "your model",
    org.fallback_provider === provider.id && org.fallback_model && "your fallback",
  ].filter(Boolean);
  return `Remove the ${provider.name} key?${uses.length ? ` It is used by ${uses.join(" and ")}.` : ""}`;
}
