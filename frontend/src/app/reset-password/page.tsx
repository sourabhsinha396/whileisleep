"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthCard } from "@/components/auth-card";
import { Button, ErrorText, Field, inputClass } from "@/components/ui";
import { api, setToken, type User } from "@/lib/api";
import { identifyUser } from "@/lib/replay";

/** Where the link in the email leads: /reset-password#<key>. */
export default function ResetPasswordPage() {
  const router = useRouter();
  // Null until the browser has read it: the server never sees what follows the "#".
  const [key, setKey] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const read = () => setKey(window.location.hash.slice(1));
    read();
    // Another link opened in this tab changes only the "#".
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const session = await api<{ token: string; user: User }>("/auth/password/reset", { method: "POST", body: { key, password } });
      setToken(session.token);
      identifyUser(session.user);
      router.replace("/app");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  if (key === "") return <AuthCard title="This link isn't complete" text="Open it from the email again, or ask for a new one on the log-in page." />;
  return (
    <AuthCard title="Choose a new password" text="You'll be logged in here, and logged out everywhere else.">
      <form onSubmit={submit} className="space-y-5">
        <Field label="New password" hint="At least 8 characters.">
          <input
            className={inputClass}
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <ErrorText>{error}</ErrorText>
        {error && (
          <Link href="/forgot-password" className="block text-sm text-primary-text hover:underline">
            Ask for a new link
          </Link>
        )}
        <Button className="w-full py-3" disabled={busy || !key}>
          {busy ? "Please wait…" : "Save password"}
        </Button>
      </form>
    </AuthCard>
  );
}
