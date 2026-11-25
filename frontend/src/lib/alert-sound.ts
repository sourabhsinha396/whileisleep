import { type Note, playNotes } from "@/widget/sound";

/** The dashboard's alert sounds, synthesised so there are no audio files (apps/workspaces AlertSound). */
export const SOUNDS = {
  chime: { label: "Chime", notes: [{ freq: 880, at: 0, length: 0.6 }, { freq: 1318.5, at: 0.12, length: 0.6 }] },
  bell: { label: "Bell", notes: [{ freq: 1046.5, at: 0, length: 1.6 }, { freq: 2637, at: 0, length: 0.8 }] },
  knock: { label: "Knock", notes: [0, 0.16, 0.32].map((at) => ({ freq: 190, at, length: 0.12, type: "triangle" as const })) },
  pop: { label: "Pop", notes: [{ freq: 520, at: 0, length: 0.12 }, { freq: 780, at: 0.07, length: 0.14 }] },
  alarm: { label: "Alarm", notes: [0, 0.2, 0.4, 0.6].map((at, i) => ({ freq: i % 2 ? 740 : 988, at, length: 0.2, type: "square" as const })) },
} satisfies Record<string, { label: string; notes: Note[] }>;

export type SoundName = keyof typeof SOUNDS;

// At 100 percent. A square or triangle wave is louder than a sine at the same level.
const LOUDEST = 0.5;

export function playAlert(sound: SoundName, volume: number) {
  if (volume > 0) playNotes((SOUNDS[sound] ?? SOUNDS.chime).notes, (LOUDEST * volume) / 100);
}
