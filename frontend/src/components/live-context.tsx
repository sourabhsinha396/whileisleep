"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { getToken, type ConversationRow, type Message } from "@/lib/api";
import { openLiveStream } from "@/lib/live-stream";

/** What the workspace's live stream sends (apps/realtime on the server). */
export type InboxEvent =
  | { event: "message"; data: { conversation_id: number; message: Message } }
  | { event: "conversation"; data: ConversationRow }
  | { event: "status"; data: { conversation_id: number; text: string } }
  | { event: "typing"; data: { conversation_id: number; sender: "visitor" | "agent"; name: string } }
  | { event: "presence"; data: { visitor_id: number; online: boolean } }
  // Connected (again): anything may have changed meanwhile, so reload.
  | { event: "open"; data: null };

type Listener = (event: InboxEvent) => void;

interface Live {
  /** The stream is connected; pages poll slowly while it is, quickly while it isn't. */
  live: boolean;
  subscribe(listener: Listener): () => void;
}

const LiveContext = createContext<Live>({ live: false, subscribe: () => () => {} });

/** Opens the workspace's live stream for the pages inside it. */
export function LiveProvider({ workspaceId, children }: { workspaceId: number; children: React.ReactNode }) {
  const [live, setLive] = useState(false);
  const listeners = useRef(new Set<Listener>());
  const [value] = useState<Omit<Live, "live">>(() => ({
    subscribe(listener) {
      listeners.current.add(listener);
      return () => listeners.current.delete(listener);
    },
  }));

  useEffect(() => {
    // The newest message id seen, so a reconnect gets what it missed.
    let lastId: number | null = null;
    const emit = (event: InboxEvent) => listeners.current.forEach((listener) => listener(event));
    const stream = openLiveStream({
      url: `/api/v1/workspaces/${workspaceId}/stream`,
      headers: (): Record<string, string> => (getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
      lastEventId: () => lastId,
      onEvent: (raw) => {
        const event = raw as InboxEvent;
        if (event.event === "message") lastId = Math.max(lastId ?? 0, event.data.message.id);
        emit(event);
      },
      onOpen: () => emit({ event: "open", data: null }),
      onLive: setLive,
    });
    return () => stream.close();
  }, [workspaceId]);

  return <LiveContext.Provider value={{ ...value, live }}>{children}</LiveContext.Provider>;
}

export function useLive(): boolean {
  return useContext(LiveContext).live;
}

/** Calls `handler` with every live event; the latest handler, without resubscribing. */
export function useLiveEvents(handler: Listener) {
  const { subscribe } = useContext(LiveContext);
  const ref = useRef(handler);
  useEffect(() => {
    ref.current = handler;
  });
  useEffect(() => subscribe((event) => ref.current(event)), [subscribe]);
}
