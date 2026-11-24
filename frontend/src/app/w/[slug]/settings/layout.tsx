"use client";

import { WithSubNav } from "@/components/sub-nav";
import { useWorkspace } from "@/components/workspace-context";
import { settingsNav } from "@/lib/nav";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const { workspace } = useWorkspace();
  return (
    <WithSubNav title="Settings" slug={workspace.slug} groups={settingsNav(workspace)}>
      {children}
    </WithSubNav>
  );
}
