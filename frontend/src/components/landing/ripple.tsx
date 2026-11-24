/**
 * Rings that breathe around whatever sits on top of them (after Magic UI's Ripple).
 * Decoration only. The parent needs `relative isolate`; the rings fade out before their own edge,
 * so nothing has to clip them.
 */

const RINGS = 7;
const SMALLEST = 400;
const STEP = 90;

export function Ripple() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute top-1/2 left-1/2 -z-10 h-[680px] w-[1040px] -translate-x-1/2 -translate-y-1/2 [mask-image:radial-gradient(closest-side,black_45%,transparent)] select-none"
    >
      {Array.from({ length: RINGS }, (_, i) => {
        const size = SMALLEST + i * STEP;
        return (
          <div
            key={i}
            className="land-ripple absolute top-1/2 left-1/2 rounded-full border border-primary bg-primary/10"
            style={{ width: size, height: size, opacity: 0.5 - i * 0.05, animationDelay: `${i * 0.12}s` }}
          />
        );
      })}
    </div>
  );
}
