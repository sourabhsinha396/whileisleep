"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { Spinner } from "@/components/ui";
import { api, setToken, type User } from "@/lib/api";
import { identifyUser } from "@/lib/replay";

/** Where a login with Google ends: a cookie only the server can read is swapped for the dashboard's token. */
export default function GoogleLoginPage() {
  const router = useRouter();
  // The cookie works once, and React runs effects twice in development.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api<{ token: string; user: User }>("/auth/google/session", { method: "POST" }).then(
      ({ token, user }) => {
        setToken(token);
        identifyUser(user);
        router.replace("/app");
      },
      () => router.replace("/login?error=google_expired"),
    );
  }, [router]);

  return (
    <div className="h-screen">
      <Spinner label="Logging in…" />
    </div>
  );
}
