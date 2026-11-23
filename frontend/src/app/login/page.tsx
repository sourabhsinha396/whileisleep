"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, ErrorText, Field, inputClass } from "@/components/ui";
import { api, setToken, type User } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = mode === "login" ? { email: form.email, password: form.password } : form;
      const session = await api<{ token: string; user: User }>(`/auth/${mode}`, { method: "POST", body });
      setToken(session.token);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
        <div>
          <p className="text-lg font-bold">
            <span className="text-brand">while</span>isleep
          </p>
          <h1 className="mt-4 text-xl font-semibold">{mode === "login" ? "Log in" : "Create your account"}</h1>
        </div>
        {mode === "signup" && (
          <Field label="Name">
            <input className={inputClass} required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
        )}
        <Field label="Email">
          <input className={inputClass} type="email" required autoComplete="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <Field label="Password" hint={mode === "signup" ? "At least 8 characters." : undefined}>
          <input
            className={inputClass}
            type="password"
            required
            minLength={mode === "signup" ? 8 : undefined}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </Field>
        <ErrorText>{error}</ErrorText>
        <Button className="w-full" disabled={busy}>
          {busy ? "…" : mode === "login" ? "Log in" : "Sign up"}
        </Button>
        <p className="text-center text-sm text-gray-600">
          {mode === "login" ? "New here? " : "Have an account? "}
          <button type="button" className="font-medium text-brand" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
            {mode === "login" ? "Create an account" : "Log in"}
          </button>
        </p>
      </form>
    </main>
  );
}
