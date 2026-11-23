"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";

export default function WorkspaceHome() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  useEffect(() => {
    router.replace(`/w/${slug}/inbox`);
  }, [slug, router]);
  return null;
}
