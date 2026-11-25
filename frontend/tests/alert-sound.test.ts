import { beforeEach, describe, expect, it, vi } from "vitest";
import { playAlert, type SoundName, SOUNDS } from "@/lib/alert-sound";
import { playNotes } from "@/widget/sound";

vi.mock("@/widget/sound", () => ({ playNotes: vi.fn() }));

beforeEach(() => vi.mocked(playNotes).mockClear());

describe("playAlert", () => {
  it("plays every sound the server offers", () => {
    expect(Object.keys(SOUNDS)).toEqual(["chime", "bell", "knock", "pop", "alarm"]);
    for (const { notes } of Object.values(SOUNDS)) expect(notes.every((n) => n.length > 0.02)).toBe(true);
  });

  it("gets louder with the volume", () => {
    playAlert("bell", 20);
    playAlert("bell", 100);
    const [quiet, loud] = vi.mocked(playNotes).mock.calls;
    expect(quiet[0]).toBe(SOUNDS.bell.notes);
    expect(loud[1]).toBeCloseTo(quiet[1] * 5);
  });

  it("is silent at 0", () => {
    playAlert("bell", 0);
    expect(playNotes).not.toHaveBeenCalled();
  });

  it("falls back to the chime for a sound it doesn't know", () => {
    playAlert("foghorn" as SoundName, 50);
    expect(vi.mocked(playNotes).mock.calls[0][0]).toBe(SOUNDS.chime.notes);
  });
});
