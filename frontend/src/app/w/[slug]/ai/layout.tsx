"use client";

import { WithSubNav } from "@/components/sub-nav";
import { useWorkspace } from "@/components/workspace-context";
import { AI_NAV } from "@/lib/nav";

export default function AiLayout({ children }: { children: React.ReactNode }) {
  const { workspace } = useWorkspace();
  return (
    <WithSubNav title="AI agent" slug={workspace.slug} groups={AI_NAV}>
      {children}
    </WithSubNav>
  );
}
