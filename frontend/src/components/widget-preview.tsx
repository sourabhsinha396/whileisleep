"use client";

import { useEffect, useRef } from "react";
import type { Workspace } from "@/lib/api";
import { previewWidget } from "@/widget/preview";

type Look = Pick<Workspace, "name" | "color" | "background" | "color_mode" | "logo_url" | "greeting"> & { team: { name: string; photo_url: string }[] };

/** The real widget with these settings, to look at: it can't be used, and sends nothing. */
export function WidgetPreview({ look }: { look: Look }) {
  const box = useRef<HTMLDivElement>(null);
  const json = JSON.stringify(look);
  useEffect(() => previewWidget(box.current!, JSON.parse(json)), [json]);
  return <div ref={box} role="img" aria-label="Preview of the chat widget" inert className="h-[500px] w-full max-w-[360px]" />;
}
