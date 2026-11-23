"use client";

import { useEffect, useRef } from "react";
import { renderSurface } from "@/lib/a2ui/render";
import { applyMessages, type A2uiMessage } from "@/lib/a2ui/surface";

/** Shows the A2UI a bot message carried, read-only, as the visitor saw it. */
export function A2uiPreview({ messages }: { messages: A2uiMessage[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    node.replaceChildren(...Array.from(applyMessages(messages).values()).map((s) => renderSurface(s, { disabled: true })));
  }, [messages]);
  return <div ref={ref} title="Interactive UI sent with this message (A2UI)" />;
}
