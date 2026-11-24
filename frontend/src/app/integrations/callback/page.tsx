"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ErrorText, Logo, Spinner } from "@/components/ui";
import { readCallback, run } from "@/lib/integrations";

/** Where a service (Slack) sends an owner back to. The dashboard's token proves who came back. */
export default function CallbackPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  // A code works once, and React runs effects twice in development.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const back = readCallback(window.location.search);
    // The code shouldn't stay in the address or the history.
    window.history.replaceState(null, "", window.location.pathname);
    const work =
      "error" in back
        ? Promise.reject(new Error(back.error))
        : run<{ workspace: string; plugin: string }>("/integrations/callback", { method: "POST", body: back });
    work
      .then(({ workspace, plugin }) => router.replace(`/w/${workspace}/settings/integrations/${plugin}`))
      .catch((e: Error) => setError(e.message));
  }, [router]);

  return (
    <main className="grid min-h-screen place-items-center bg-muted p-6">
      <div className="w-full max-w-sm space-y-5 rounded-lg border bg-surface p-8 shadow-sm">
        <Logo />
        {error ? (
          <>
            <ErrorText>{error}</ErrorText>
            <Link href="/app" className="text-sm text-primary-text hover:underline">
              Back to the dashboard
            </Link>
          </>
        ) : (
          <Spinner label="Connecting…" />
        )}
      </div>
    </main>
  );
}
