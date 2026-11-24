"use client";

import { Copy } from "lucide-react";
import { useState } from "react";
import { Button, ErrorText, Notice, PageHeader } from "@/components/ui";
import { useWorkspace } from "@/components/workspace-context";
import { api } from "@/lib/api";

export default function IdentityPage() {
  const { workspace } = useWorkspace();
  return (
    <>
      <PageHeader title="Verified identity" docs="verified-identity" description="Prove to the agent's tools who your signed-in visitors are." />
      <div className="mx-auto max-w-3xl p-8">
        {workspace.role === "owner" ? <IdentitySecret /> : <Notice>Only the workspace&apos;s owners can see this secret.</Notice>}
      </div>
    </>
  );
}

/** The secret the site's server signs identity tokens with. Fetched only when asked for. */
function IdentitySecret() {
  const { workspace } = useWorkspace();
  const base = `/workspaces/${workspace.id}/identity-secret`;
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");

  async function load(path: string, method: "GET" | "POST") {
    setError("");
    try {
      setSecret((await api<{ secret: string }>(path, { method })).secret);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function rotate() {
    if (window.confirm("Replace the secret? Tokens signed with the current one stop working at once.")) load(`${base}/rotate`, "POST");
  }

  return (
    <section className="space-y-3 rounded-lg border bg-surface p-6 shadow-sm">
      <p className="text-sm text-muted-foreground">
        What a page says about its user can be typed into a browser console, so tools only use a visitor&apos;s details once your server
        has vouched for them. Sign a short-lived HS256 token with this secret on your server (claims: <code>sub</code> your user&apos;s id,{" "}
        <code>exp</code>, plus <code>email</code>, <code>name</code> and anything else) and call{" "}
        <code>window.whileisleep.identify({"{ token }"})</code>. Keep the secret on the server; never put it in the page.
      </p>
      {secret ? (
        <div className="flex gap-2">
          <code className="block flex-1 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs whitespace-nowrap text-gray-100">{secret}</code>
          <Button variant="secondary" onClick={() => navigator.clipboard.writeText(secret)}>
            <Copy size={15} /> Copy
          </Button>
        </div>
      ) : (
        <Button variant="secondary" onClick={() => load(base, "GET")}>
          Show the secret
        </Button>
      )}
      {secret && (
        <Button variant="danger" onClick={rotate}>
          Replace the secret
        </Button>
      )}
      <ErrorText>{error}</ErrorText>
    </section>
  );
}
