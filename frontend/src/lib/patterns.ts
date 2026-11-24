/**
 * The patterns a widget's header can have, drawn for whileisleep. Each is one tile of an SVG
 * that repeats, in the header's text colour at two strengths, so it suits every widget colour.
 *
 * Inline SVG rather than CSS images: a customer's site may forbid data: images.
 */

interface Tile {
  width: number;
  height: number;
  art: string;
}

// Strong and weak.
const A = 'opacity=".17"';
const B = 'opacity=".09"';

const round = (n: number) => Math.round(n * 100) / 100;
const at = (x: number, y: number, art: string, turn = 0, scale = 1) =>
  `<g transform="translate(${x} ${y})${turn ? ` rotate(${turn})` : ""}${scale === 1 ? "" : ` scale(${scale})`}">${art}</g>`;
const dot = (x: number, y: number, r: number, look: string) => `<circle cx="${x}" cy="${y}" r="${r}" ${look}/>`;
const ring = (x: number, y: number, r: number, width: number, look: string) =>
  `<circle cx="${x}" cy="${y}" r="${r}" fill="none" stroke="currentColor" stroke-width="${width}" ${look}/>`;
const path = (d: string, look: string) => `<path d="${d}" ${look}/>`;
const line = (d: string, width: number, look: string) =>
  `<path d="${d}" fill="none" stroke="currentColor" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round" ${look}/>`;

const star = (look: string) => path("M0-10Q1.6-1.6 10 0 1.6 1.6 0 10-1.6 1.6-10 0-1.6-1.6 0-10Z", look);
const leaf = (look: string) => path("M0-13C9-6 9 6 0 13-9 6-9-6 0-13Z", look) + line("M0-7V17", 1.5, look);
const heart = (look: string) => path("M0 8C-11 1-9-8-3.5-8-1.5-8 0-6.5 0-5 0-6.5 1.5-8 3.5-8 9-8 11 1 0 8Z", look);

/** A hexagon standing on a point. */
function hexagon(x: number, y: number, r: number, look: string): string {
  const points = [0, 1, 2, 3, 4, 5].map((i) => {
    const angle = (Math.PI / 3) * i - Math.PI / 2;
    return `${round(x + r * Math.cos(angle))} ${round(y + r * Math.sin(angle))}`;
  });
  return path(`M${points.join("L")}Z`, look);
}

const HEX = { width: 34.64, height: 60 };
const SIDE = 34;
const ROW = round(SIDE * 0.866);

/** One row of triangles, pointing up and down in turn, each with its own strength. Those that
 * cross the tile's right edge are drawn again at its left, so the tile repeats without a seam. */
function mosaic(row: number, shift: number, strengths: number[]): string[] {
  const top = round(row * ROW);
  const bottom = round(top + ROW);
  const width = SIDE * 3;
  return strengths.flatMap((strength, i) => {
    const x = shift + (i * SIDE) / 2;
    const [from, to] = i % 2 ? [top, bottom] : [bottom, top];
    const draw = (left: number) => path(`M${left} ${from}H${left + SIDE}L${left + SIDE / 2} ${to}Z`, `opacity="${strength}"`);
    return x + SIDE > width ? [draw(x), draw(x - width)] : [draw(x)];
  });
}

const TILES = {
  bubbles: {
    width: 84,
    height: 72,
    art:
      dot(22, 20, 15, B) + dot(17, 14, 4, A) + ring(58, 16, 9, 2.5, A) + dot(62, 48, 18, B) + dot(56, 41, 5, A) +
      ring(24, 54, 11, 2.5, A) + dot(24, 54, 4, A) + dot(40, 34, 3, A) + dot(78, 22, 2.5, A) + dot(42, 66, 2.5, A) + dot(5, 40, 3, A),
  },
  confetti: {
    width: 88,
    height: 80,
    art:
      dot(14, 14, 6, A) + line("M34 12q5-7 10 0t10 0", 3, A) + path("M74 8l9 15H65Z", B) + at(20, 44, `<rect x="-8" y="-4" width="16" height="8" rx="2.5" ${B}/>`, 35) +
      ring(50, 38, 8, 3, B) + line("M78 40v12M72 46h12", 3, A) + line("M8 66q4-6 8 0t8 0", 3, B) + path("M42 60l12 5-9 9Z", A) + dot(74, 70, 5, B) + dot(34, 28, 2.5, A) + dot(62, 60, 2, A),
  },
  chat: {
    width: 92,
    height: 80,
    art:
      path("M10 8h22a6 6 0 0 1 6 6v8a6 6 0 0 1-6 6H20l-8 6v-6h-2a6 6 0 0 1-6-6v-8a6 6 0 0 1 6-6Z", B) + dot(14, 18, 2, A) + dot(21, 18, 2, A) + dot(28, 18, 2, A) +
      at(66, 16, heart(A), -12) + path("M58 40h20a6 6 0 0 1 6 6v7a6 6 0 0 1-6 6h-1v6l-8-6H58a6 6 0 0 1-6-6v-7a6 6 0 0 1 6-6Z", A) +
      line("M61 47h14M61 52h9", 2, B) + ring(24, 58, 10, 2.5, B) + line("M20.5 56a3.5 3.5 0 1 1 4.6 3.4q-1.1.5-1.1 1.8", 2.2, A) + dot(24, 64, 1.4, A) + dot(86, 28, 2.5, B) + dot(44, 72, 2.5, B),
  },
  night: {
    width: 92,
    height: 80,
    art:
      at(20, 22, path("M5-13A14 14 0 1 0 13 6 11 11 0 0 1 5-13Z", A)) + at(58, 14, star(A), 0, 0.8) + at(80, 34, star(B), 0, 0.5) + at(44, 44, star(B), 0, 0.6) +
      at(66, 60, path("M4-11A12 12 0 1 0 11 5 9.5 9.5 0 0 1 4-11Z", B), 12) + line("M14 54h9l-9 10h9", 2.6, A) + line("M30 66h6l-6 7h6", 2.2, B) + dot(40, 12, 1.8, A) + dot(84, 10, 1.8, B) + dot(86, 66, 2, A) + dot(6, 74, 1.8, B),
  },
  stars: {
    width: 76,
    height: 68,
    art:
      at(20, 20, star(A), 0, 1.6) + at(58, 12, star(A), 0, 0.7) + at(54, 46, star(A), 0, 1.3) + at(16, 56, star(A), 0, 0.8) + at(38, 36, star(B), 0, 0.6) +
      ring(20, 20, 19, 1.2, B) + dot(38, 6, 2, A) + dot(71, 30, 2, A) + dot(34, 62, 1.8, A) + dot(4, 38, 1.8, B),
  },
  leaves: {
    width: 76,
    height: 72,
    art: at(18, 18, leaf(A), 38) + at(56, 14, leaf(B), -48, 0.85) + at(56, 52, leaf(A), 128, 0.95) + at(18, 54, leaf(B), -118, 0.85) + dot(38, 34, 2.2, A) + dot(38, 4, 1.8, B) + dot(72, 34, 1.8, B),
  },
  petals: {
    width: 44,
    height: 44,
    art:
      path("M22 0A22 22 0 0 1 0 22 22 22 0 0 1 22 0Z", A) + path("M22 0A22 22 0 0 0 44 22 22 22 0 0 0 22 0Z", B) +
      path("M22 44A22 22 0 0 0 0 22 22 22 0 0 0 22 44Z", B) + path("M22 44A22 22 0 0 1 44 22 22 22 0 0 1 22 44Z", A) + dot(22, 22, 2.5, A),
  },
  waves: {
    width: 72,
    height: 36,
    art:
      path("M0 9Q18-5 36 9T72 9V18Q54 32 36 18T0 18Z", B) + line("M0 9Q18-5 36 9T72 9", 1.5, A) + line("M0 24Q18 10 36 24T72 24", 2.5, A) + line("M0 31Q18 17 36 31T72 31", 1.5, B),
  },
  hexagons: {
    ...HEX,
    art: [[0, 0], [HEX.width, 0], [0, HEX.height], [HEX.width, HEX.height]].map(([x, y]) => hexagon(x, y, 18, B) + hexagon(x, y, 8, A)).join("") + hexagon(HEX.width / 2, HEX.height / 2, 18, A),
  },
  triangles: {
    width: SIDE * 3,
    height: ROW * 2,
    art: [...mosaic(0, 0, [0.17, 0.05, 0.1, 0.13, 0.03, 0.08]), ...mosaic(1, SIDE / 2, [0.04, 0.12, 0.17, 0.02, 0.09, 0.06])].join(""),
  },
  diamonds: {
    width: 48,
    height: 48,
    art:
      path("M24 2L46 24 24 46 2 24Z", B) + path("M24 13L35 24 24 35 13 24Z", A) +
      [[0, 0], [48, 0], [0, 48], [48, 48]].map(([x, y]) => dot(x, y, 8, A)).join(""),
  },
  circuit: {
    width: 96,
    height: 88,
    art:
      line("M0 22H30L42 34V58", 2, A) + dot(42, 62, 4, A) + line("M96 22H70", 2, A) + ring(66, 22, 4, 2, A) +
      line("M72 88V58L84 46H96M0 46H12", 2, B) + dot(16, 46, 4, B) + line("M72 0V6", 2, B) + ring(72, 10, 4, 2, B) +
      line("M18 88V72M18 0V8", 2, B) + ring(18, 68, 4, 2, B) + dot(18, 11, 3.5, B) + line("M46 10H54", 2, B) + dot(43, 10, 3, A) + line("M56 88V76L62 70", 2, A) + dot(64, 68, 3, A) + line("M56 0V4", 2, A),
  },
} satisfies Record<string, Tile>;

export type PatternName = keyof typeof TILES;

export const PATTERNS = Object.keys(TILES) as PatternName[];

export function isPattern(name: string | undefined): name is PatternName {
  return !!name && Object.prototype.hasOwnProperty.call(TILES, name);
}

/** SVG markup that fills its box with the pattern. `id` must be the only one of its kind on the
 * page; `scale` makes the tile smaller, for a swatch. */
export function patternSvg(name: PatternName, id: string, scale = 1): string {
  const { width, height, art } = TILES[name];
  return (
    `<svg class="pattern" aria-hidden="true" width="100%" height="100%"><defs>` +
    `<pattern id="${id}" width="${width}" height="${round(height)}" patternUnits="userSpaceOnUse" patternTransform="scale(${scale})" fill="currentColor">${art}</pattern>` +
    `</defs><rect width="100%" height="100%" fill="url(#${id})"/></svg>`
  );
}
