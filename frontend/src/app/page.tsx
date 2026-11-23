"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Spinner } from "@/components/ui";
import { api, getToken, type Workspace } from "@/lib/api";

/** Sends you to your first workspace, to create one, or to log in. */
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api<Workspace[]>("/workspaces")
      .then((rows) => router.replace(rows.length ? `/w/${rows[0].id}/inbox` : "/new"))
      .catch(() => router.replace("/login"));
  }, [router]);
  return <div className="h-screen"><Spinner /></div>;
}
