"use client";

import { useState } from "react";
import { AuthCard } from "@/components/auth-card";
import { Captcha } from "@/components/captcha";
import { Button, ErrorText, Field, inputClass } from "@/components/ui";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [captcha, setCaptcha] = useState("");
  const [tries, setTries] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/password/forgot", { method: "POST", body: { email, captcha } });
      setSent(true);
    } catch (err) {
      setError((err as Error).message);
      // A ticked box is good for one try.
      setCaptcha("");
      setTries((n) => n + 1);
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return <AuthCard title="Check your email" text={`If ${email} has an account, a link to choose a new password is on its way. It works for one hour.`} />;
  }
  return (
    <AuthCard title="Forgot your password?" text="We'll email you a link to choose a new one.">
      <form onSubmit={submit} className="space-y-5">
        <Field label="Email">
          <input className={inputClass} type="email" required autoComplete="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Captcha key={tries} onChange={setCaptcha} />
        <ErrorText>{error}</ErrorText>
        <Button className="w-full py-3" disabled={busy}>
          {busy ? "Please wait…" : "Email me a link"}
        </Button>
      </form>
    </AuthCard>
  );
}
