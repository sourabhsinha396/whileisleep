"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

/** A stand-in customer site that loads the widget: /demo?key=ws_... */
export default function DemoPage() {
  return (
    <Suspense>
      <Demo />
    </Suspense>
  );
}

function Demo() {
  const key = useSearchParams().get("key") ?? "";
  useEffect(() => {
    if (!key || document.getElementById("whileisleep-script")) return;
    const script = document.createElement("script");
    script.id = "whileisleep-script";
    script.src = "/widget.js";
    script.async = true;
    script.dataset.workspace = key;
    document.body.appendChild(script);
  }, [key]);

  return (
    <main className="min-h-screen bg-surface">
      <header className="border-b px-8 py-5 text-lg font-bold">Your website</header>
      <section className="mx-auto max-w-2xl space-y-4 p-8 text-foreground">
        <h1 className="text-3xl font-bold text-foreground">Widget test page</h1>
        <p>This page stands in for a customer&apos;s site. The chat bubble in the corner is the whileisleep widget for workspace <code>{key || "(none)"}</code>.</p>
        <p>Ask it something your tools or articles cover, then answer from the dashboard inbox.</p>
        {!key && <p className="text-danger">Add ?key=ws_… to the URL.</p>}
      </section>
    </main>
  );
}
