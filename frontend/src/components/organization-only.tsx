"use client";

import { useCallback } from "react";
import { Notice, Spinner } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api, type Organization } from "@/lib/api";
import { usePoll } from "@/lib/use-poll";

type Content = (org: Organization, setOrg: (org: Organization) => void) => React.ReactNode;

/**
 * A settings page about the organization. The API returns the organization you own, so in someone
 * else's workspace that would be the wrong one: there it says who can change this instead.
 */
export function OrganizationOnly({ children }: { children: Content }) {
  const { workspace } = useWorkspace();
  return (
    <div className="mx-auto max-w-3xl p-8">
      {workspace.is_organization_owner ? <Load>{children}</Load> : <Notice>Only the organization&apos;s owner can change this.</Notice>}
    </div>
  );
}

function Load({ children }: { children: Content }) {
  const { data: org, setData } = usePoll(useCallback(() => api<Organization>("/organization"), []), 60000);
  return org ? children(org, setData) : <Spinner />;
}
