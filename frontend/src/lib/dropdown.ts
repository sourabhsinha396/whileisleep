/** The most a dropdown's list takes, in pixels. */
const LIST_HEIGHT = 320;

/** Whether a dropdown's list should open above its field: there is no room below, and more above. */
export function opensAbove(field: Pick<DOMRect, "top" | "bottom"> | undefined, viewport: number): boolean {
  if (!field) return false;
  const below = viewport - field.bottom;
  return below < LIST_HEIGHT && field.top > below;
}

/** The option a typed letter jumps to: the next one after `from` that starts with it, going round. */
export function nextStartingWith(labels: string[], letter: string, from: number): number {
  const at = labels.map((_, i) => (from + 1 + i) % labels.length);
  return at.find((i) => labels[i].toLowerCase().startsWith(letter.toLowerCase())) ?? from;
}
