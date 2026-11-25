import type { ChatMessage } from "./api";

/** The id of the newest reply worth a chime, or 0 for none.
 * A reply is a message from the team or the AI; the visitor's own messages and system notes don't count.
 * Only while the tab is hidden (the visitor is looking elsewhere), and never twice for the same message
 * (`chimedId` is shared across this visitor's tabs, so two open tabs don't both ring). */
export function chimeFor(incoming: Pick<ChatMessage, "id" | "sender">[], hidden: boolean, chimedId: number): number {
  if (!hidden) return 0;
  const replies = incoming.filter((m) => m.sender !== "visitor" && m.sender !== "system" && m.id > chimedId);
  return replies.length ? Math.max(...replies.map((m) => m.id)) : 0;
}

let ctx: AudioContext | undefined;

/** Browsers only allow audio after the visitor has interacted with the page, so the context is
 * created (or resumed) on their first click or key press and reused for every chime after that. */
export function unlockAudio() {
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return;
  try {
    ctx ??= new Ctor();
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
  } catch {
    /* audio unavailable */
  }
}

/** A tone that starts `at` seconds in and fades over `length` seconds. */
export interface Note {
  freq: number;
  at: number;
  length: number;
  type?: OscillatorType;
}

/** A soft two-note chime, synthesised so there's no audio file to load. */
export function playChime() {
  playNotes([{ freq: 880, at: 0, length: 0.6 }, { freq: 1318.5, at: 0.12, length: 0.6 }], 0.08);
}

/** Plays the notes, each peaking at `peak` (0 to 1). Silent if audio isn't unlocked. */
export function playNotes(notes: Note[], peak: number) {
  if (!ctx || ctx.state !== "running") return;
  const start = ctx.currentTime;
  for (const { freq, at, length, type } of notes) {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type ?? "sine";
    osc.frequency.value = freq;
    const t = start + at;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(peak, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + length);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t);
    osc.stop(t + length + 0.05);
  }
}
