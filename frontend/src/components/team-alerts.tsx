"use client";

import { Bell, BellOff, Volume2, VolumeX } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLive, useLiveEvents } from "@/components/live-context";
import { playAlert } from "@/lib/alert-sound";
import { AlertTracker, alertOn, claimAlert, isLookingAt, setAlert, waitsForTeam } from "@/lib/alerts";
import { api, type ConversationRow, type Workspace } from "@/lib/api";
import { plainText } from "@/lib/chat-text";
import { unlockAudio } from "@/widget/sound";

// Without the live stream. Also in a hidden tab, which is when alerts matter most.
const POLL_MS = 15000;
// Hidden tabs let the tab someone is looking at go first.
const HIDDEN_WAIT_MS = 300;
// Nobody is there: stop ringing.
const MAX_REPEATS = 20;

/** Rings, shows a desktop notification and counts in the tab title when a chat needs the team. */
export function TeamAlerts({ workspace }: { workspace: Workspace }) {
  const { id, slug, alert_sound: sound, alert_volume: volume, alert_on: on, alert_repeat: repeat } = workspace;
  const aiEnabled = workspace.ai_enabled;
  // Alerting about every message is the same as having no AI to answer some of them.
  const aiAnswers = aiEnabled && on === "person";
  const router = useRouter();
  const live = useLive();
  const [tracker] = useState(() => new AlertTracker());
  const waiting = useRef(new Set<number>());
  // Chats this tab rang for that the team must still read, and how often it rang again.
  const ringing = useRef(new Map<number, number>());

  const alert = useCallback(
    (row: ConversationRow) => {
      const ring = () => {
        // Looking at it claims it too, so this browser's other tabs stay quiet.
        if (!claimAlert(id, row) || isLookingAt(row.id)) return;
        if (alertOn("sound")) playAlert(sound, volume);
        if (waitsForTeam(row, aiEnabled)) ringing.current.set(row.id, 0);
        if (document.hasFocus()) return;
        if (document.hidden) {
          waiting.current.add(row.id);
          document.title = `(${waiting.current.size}) ${document.title.replace(/^\(\d+\) /, "")}`;
        }
        if (!alertOn("popup")) return;
        try {
          const popup = new Notification(waitsForTeam(row, aiEnabled) ? `${row.visitor.name} needs a person` : `New message from ${row.visitor.name}`, {
            body: plainText(row.preview),
            tag: `whileisleep-${row.id}`,
            silent: true, // our chime is the sound, or none was wanted
          });
          popup.onclick = () => {
            window.focus();
            router.push(`/w/${slug}/inbox?c=${row.id}`);
            popup.close();
          };
        } catch {
          /* phones only allow these from a service worker */
        }
      };
      if (document.hasFocus()) ring();
      else setTimeout(ring, HIDDEN_WAIT_MS);
    },
    [id, slug, router, sound, volume, aiEnabled],
  );

  const load = useCallback(async () => {
    const rows = await api<ConversationRow[]>(`/workspaces/${id}/conversations?status=open`).catch(() => null);
    if (!rows) return;
    for (const chat of ringing.current.keys()) {
      if (!rows.some((row) => row.id === chat && waitsForTeam(row, aiEnabled))) ringing.current.delete(chat);
    }
    tracker.load(rows, aiAnswers).forEach(alert);
  }, [id, aiEnabled, aiAnswers, tracker, alert]);

  useEffect(() => {
    load();
    if (live) return;
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [live, load]);

  useLiveEvents((e) => {
    if (e.event === "open") load();
    else if (e.event === "message") tracker.message(e.data.conversation_id, e.data.message);
    else if (e.event === "conversation") {
      if (!waitsForTeam(e.data, aiEnabled)) ringing.current.delete(e.data.id);
      if (tracker.changed(e.data, aiAnswers)) alert(e.data);
    }
  });

  useEffect(() => {
    if (!repeat) return;
    const timer = setInterval(() => {
      for (const [chat, times] of ringing.current) {
        if (times >= MAX_REPEATS) ringing.current.delete(chat);
        else ringing.current.set(chat, times + 1);
      }
      if (ringing.current.size && alertOn("sound")) playAlert(sound, volume);
    }, repeat * 1000);
    return () => clearInterval(timer);
  }, [repeat, sound, volume]);

  useEffect(() => {
    const seen = () => {
      if (document.hidden) return;
      waiting.current.clear();
      document.title = document.title.replace(/^\(\d+\) /, "");
    };
    document.addEventListener("visibilitychange", seen);
    // Browsers allow sound only after a click or key press.
    window.addEventListener("pointerdown", unlockAudio);
    window.addEventListener("keydown", unlockAudio);
    return () => {
      document.removeEventListener("visibilitychange", seen);
      window.removeEventListener("pointerdown", unlockAudio);
      window.removeEventListener("keydown", unlockAudio);
    };
  }, []);

  return null;
}

/** The two switches in the account menu, remembered by this browser. Rendered only once the menu is opened. */
export function AlertSwitches({ workspace }: { workspace: Workspace }) {
  const [sound, setSound] = useState(() => alertOn("sound"));
  const [popup, setPopup] = useState(() => alertOn("popup"));
  const [blocked, setBlocked] = useState(false);

  function toggleSound() {
    setAlert("sound", !sound);
    setSound(!sound);
    if (!sound) playAlert(workspace.alert_sound, workspace.alert_volume);
  }

  async function togglePopup() {
    if (!popup) {
      const permission = "Notification" in window ? await Notification.requestPermission() : "denied";
      setBlocked(permission === "denied");
      if (permission !== "granted") return;
    }
    setAlert("popup", !popup);
    setPopup(!popup);
  }

  const look = "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-muted";
  const state = (on: boolean) => <span className="ml-auto text-xs text-muted-foreground">{on ? "On" : "Off"}</span>;
  return (
    <>
      <button role="menuitemcheckbox" aria-checked={sound} onClick={toggleSound} className={look}>
        {sound ? <Volume2 size={15} /> : <VolumeX size={15} />} Sound alerts {state(sound)}
      </button>
      <button role="menuitemcheckbox" aria-checked={popup} onClick={togglePopup} className={look}>
        {popup ? <Bell size={15} /> : <BellOff size={15} />} Desktop alerts {state(popup)}
      </button>
      {blocked && <p className="px-3 pb-2 text-xs text-warning">Your browser blocks notifications. Allow them in this site&apos;s settings.</p>}
    </>
  );
}
