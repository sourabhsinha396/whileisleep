/** Readable text for a widget color. Deep colors take white text; bright ones take dark text.
 * Shared by the dashboard and the widget. */
export const DARK_TEXT = "#1b2333";

function channels(color: string): number[] {
  const hex = color.slice(1);
  const full = hex.length < 6 ? [...hex].map((c) => c + c).join("") : hex;
  return [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16));
}

/** WCAG contrast ratio of two hex colors. */
export function contrast(a: string, b: string): number {
  const [light, dark] = [a, b]
    .map((color) => {
      const [r, g, bl] = channels(color).map((v) => (v / 255 <= 0.04045 ? v / 255 / 12.92 : ((v / 255 + 0.055) / 1.055) ** 2.4));
      return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
    })
    .sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/** Too light for white text. 3 rather than 4.5 so in-between colors from before the list stay white. */
export function isBright(color: string): boolean {
  return contrast(color, "#ffffff") < 3;
}

/** Text that sits on the color. */
export function textOn(color: string): string {
  return isBright(color) ? DARK_TEXT : "#ffffff";
}

/** The color as text on white: a bright one is darkened, a deep one is used as it is. */
export function inkOf(color: string): string {
  if (!isBright(color)) return color;
  return "#" + channels(color).map((v) => Math.round(v * 0.42).toString(16).padStart(2, "0")).join("");
}
