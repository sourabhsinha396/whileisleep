"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Nothing where the server can't send emails. */
export function ForgotLink() {
  const [shown, setShown] = useState(false);

  useEffect(() => {
    let gone = false;
    api<{ can_reset: boolean }>("/auth/password").then(({ can_reset }) => !gone && setShown(can_reset), () => {});
    return () => {
      gone = true;
    };
  }, []);

  if (!shown) return null;
  return (
    <Link href="/forgot-password" className="block text-right text-sm text-primary-text hover:underline">
      Forgot password?
    </Link>
  );
}
