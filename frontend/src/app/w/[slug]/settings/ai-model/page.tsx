"use client";

import { LlmSettings } from "@/components/llm-settings";
import { OrganizationOnly } from "@/components/organization-only";
import { PageHeader } from "@/components/ui";

/** The provider keys, the model every workspace's AI agent uses, and its fallback. */
export default function AiModelPage() {
  return (
    <>
      <PageHeader title="AI model" docs="connect-ai" description="The model, its fallback and the API keys every workspace in this organization shares." />
      <OrganizationOnly>{(org, setOrg) => <LlmSettings key={org.id} org={org} onSaved={setOrg} />}</OrganizationOnly>
    </>
  );
}
