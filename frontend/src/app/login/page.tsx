"use client";

import { Bot, BookOpen, Inbox, Zap } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Captcha } from "@/components/captcha";
import { ForgotLink } from "@/components/forgot-link";
import { GoogleButton } from "@/components/google-button";
import { Button, ErrorText, Field, inputClass, Logo, LogoMark, ThemeToggle } from "@/components/ui";
import { api, setToken, type User } from "@/lib/api";
import { loginError } from "@/lib/google";

const POINTS = [
  { icon: Bot, title: "An AI agent that answers from your data", text: "Help articles, your own APIs and playbooks, with a person one click away." },
  { icon: Inbox, title: "One shared inbox", text: "Live visitors, conversations and internal notes for the whole team." },
  { icon: BookOpen, title: "A help center in the widget", text: "Visitors find answers themselves before they ever ask." },
  { icon: Zap, title: "Rules that route the rest", text: "Tag, hand off and reply automatically by intent, keywords or page." },
];

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [captcha, setCaptcha] = useState("");
  const [tries, setTries] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const problem = loginError(window.location.search);
    if (!problem) return;
    // Read here, not while rendering: the server doesn't have the address's query.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setError(problem);
    window.history.replaceState(null, "", window.location.pathname);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = mode === "login" ? { email: form.email, password: form.password, captcha } : { ...form, captcha };
      const session = await api<{ token: string; user: User }>(`/auth/${mode}`, { method: "POST", body });
      setToken(session.token);
      router.replace("/app");
    } catch (err) {
      setError((err as Error).message);
      // A ticked box is good for one try.
      setCaptcha("");
      setTries((n) => n + 1);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-primary p-12 text-primary-foreground lg:flex">
        <div className="pointer-events-none absolute -top-32 -right-32 size-96 rounded-full bg-white/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-40 -left-20 size-96 rounded-full bg-white/10 blur-3xl" />
        <span className="relative flex items-center gap-2 text-lg font-bold tracking-tight">
          <LogoMark className="size-9 rounded-full ring-2 ring-white/30" />
          whileisleep
        </span>
        <div className="relative max-w-md">
          <h2 className="text-3xl leading-tight font-bold tracking-tight">Customer chat that keeps answering while you sleep.</h2>
          <ul className="mt-10 space-y-6">
            {POINTS.map(({ icon: Icon, title, text }) => (
              <li key={title} className="flex gap-4">
                <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-white/15">
                  <Icon size={19} />
                </span>
                <span>
                  <span className="block font-semibold">{title}</span>
                  <span className="mt-0.5 block text-sm text-white/75">{text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-white/60">Open source. Self-host it, bring your own LLM.</p>
      </section>

      <section className="flex flex-col bg-background px-6 py-8">
        <div className="flex items-center justify-between">
          <Logo className="lg:invisible" />
          <ThemeToggle />
        </div>
        <div className="flex flex-1 items-center justify-center py-10">
          <form onSubmit={submit} className="w-full max-w-sm space-y-5">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                {mode === "login" ? "Log in to your inbox." : "Set up your first workspace in a minute."}
              </p>
            </div>
            <GoogleButton />
            {mode === "signup" && (
              <Field label="Name">
                <input className={inputClass} required autoComplete="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </Field>
            )}
            <Field label="Email">
              <input className={inputClass} type="email" required autoComplete="email" placeholder="you@company.com" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
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
            {mode === "login" && <ForgotLink />}
            <Captcha key={tries} onChange={setCaptcha} />
            <ErrorText>{error}</ErrorText>
            <Button className="w-full py-3" disabled={busy}>
              {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              {mode === "login" ? "New here? " : "Have an account? "}
              <button type="button" className="font-semibold text-primary-text hover:underline" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
                {mode === "login" ? "Create an account" : "Log in"}
              </button>
            </p>
          </form>
        </div>
      </section>
    </main>
  );
}
