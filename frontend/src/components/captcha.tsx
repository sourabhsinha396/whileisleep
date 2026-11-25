"use client";

import { useTheme } from "next-themes";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { api } from "@/lib/api";

/** Google's script, as much of it as is used here. */
interface Recaptcha {
  ready(done: () => void): void;
  render(box: HTMLElement, options: Record<string, unknown>): number;
}

declare global {
  interface Window {
    grecaptcha?: Recaptcha;
  }
}

const SCRIPT = "https://www.google.com/recaptcha/api.js?render=explicit";
let loading: Promise<Recaptcha> | null = null;

/** Loaded once, and only by a page that shows the box. */
function loadRecaptcha(): Promise<Recaptcha> {
  loading ??= new Promise<Recaptcha>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SCRIPT;
    script.async = true;
    script.onload = () => {
      const recaptcha = window.grecaptcha;
      if (recaptcha) recaptcha.ready(() => resolve(recaptcha));
      else reject(new Error("no grecaptcha"));
    };
    script.onerror = () => reject(new Error("blocked"));
    document.head.appendChild(script);
  }).catch((error) => {
    // So that coming back to the form tries again.
    loading = null;
    throw error;
  });
  return loading;
}

/**
 * "I'm not a robot", where the server has it switched on, and nothing where it hasn't. Give it a new `key` after each
 * try: what a ticked box stands for is only good once.
 */
export function Captcha({ onChange }: { onChange: (token: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [siteKey, setSiteKey] = useState("");
  const [failed, setFailed] = useState(false);
  const { resolvedTheme } = useTheme();
  const change = useEffectEvent(onChange);

  useEffect(() => {
    let gone = false;
    // If this fails, so does the form, which then says why.
    api<{ site_key: string }>("/auth/captcha").then(({ site_key }) => !gone && setSiteKey(site_key), () => {});
    return () => {
      gone = true;
    };
  }, []);

  useEffect(() => {
    const holder = box.current;
    if (!siteKey || !holder) return;
    let gone = false;
    // Google draws into a fresh element each time: it can't draw twice into one, nor change a box's theme.
    const target = holder.appendChild(document.createElement("div"));
    loadRecaptcha().then(
      (recaptcha) => {
        if (gone) return;
        setFailed(false);
        recaptcha.render(target, {
          sitekey: siteKey,
          theme: resolvedTheme === "dark" ? "dark" : "light",
          callback: (token: string) => !gone && change(token),
          "expired-callback": () => !gone && change(""),
          "error-callback": () => !gone && setFailed(true),
        });
      },
      () => !gone && setFailed(true),
    );
    return () => {
      gone = true;
      target.remove();
      change("");
    };
  }, [siteKey, resolvedTheme]);

  if (!siteKey) return null;
  return (
    <div>
      <div ref={box} className="min-h-[78px]" />
      {failed && (
        <p role="alert" className="text-sm text-danger">
          The robot check from Google couldn&apos;t load. Check your connection or ad blocker, then reload the page.
        </p>
      )}
    </div>
  );
}
