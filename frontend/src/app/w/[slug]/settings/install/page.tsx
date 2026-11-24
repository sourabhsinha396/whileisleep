"use client";

import { Copy, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";

export default function InstallPage() {
  const { workspace } = useWorkspace();
  const [copied, setCopied] = useState(false);
  // Workspace pages render only in the browser (the layout waits for the API first).
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const snippet = `<script src="${origin}/widget.js" data-workspace="${workspace.public_key}" async></script>`;

  return (
    <>
      <PageHeader title="Install" description="Put the chat widget on your site." />
      <div className="mx-auto max-w-3xl p-8">
        <section className="space-y-3 rounded-lg border bg-surface p-6 shadow-sm">
          <p className="text-sm text-muted-foreground">Paste this before <code>&lt;/body&gt;</code> on every page of your site.</p>
          <div className="flex gap-2">
            <code className="block flex-1 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs whitespace-nowrap text-gray-100">{snippet}</code>
            <Button variant="secondary" onClick={() => navigator.clipboard.writeText(snippet).then(() => setCopied(true))}>
              <Copy size={15} /> {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">
            Signed-in users? Call <code>window.whileisleep.identify({"{ name, email, attributes: { country } }"})</code> so conversations show who they are; a country
            (&quot;IN&quot; or &quot;India&quot;) shows as a flag. To let
            tools look up a user&apos;s own data, prove who they are with a{" "}
            {workspace.role === "owner" ? (
              <Link className="font-medium text-primary-text hover:underline" href={`/w/${workspace.slug}/settings/identity`}>
                signed token
              </Link>
            ) : (
              "signed token"
            )}
            .
          </p>
          <a className="inline-flex items-center gap-1 text-sm font-medium text-primary-text hover:underline" href={`/demo?key=${workspace.public_key}`} target="_blank">
            Open a test page with the widget <ExternalLink size={14} />
          </a>
        </section>
      </div>
    </>
  );
}
