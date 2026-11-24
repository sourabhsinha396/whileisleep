/** A still night sky that frames the hero's inbox. Looks the same in both themes: it is always night here. */

// [x %, y %, radius px, opacity]. Along the top and the sides, where the inbox doesn't cover them.
const STARS = [
  [4, 5, 1, 0.7], [9, 11, 1.5, 0.9], [16, 4, 1, 0.5], [22, 9, 1, 0.8], [29, 5, 1.5, 0.6],
  [36, 12, 1, 0.5], [43, 4, 1, 0.8], [50, 9, 1.5, 0.9], [57, 5, 1, 0.5], [64, 11, 1, 0.7],
  [71, 4, 1.5, 0.6], [77, 9, 1, 0.8], [96, 4, 1, 0.6], [97, 16, 1, 0.7], [2, 22, 1, 0.6],
  [3, 36, 1.5, 0.5], [98, 30, 1.5, 0.5], [2, 52, 1, 0.4], [97.5, 48, 1, 0.4],
];

export function NightPanel({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-linear-to-b from-[#0a1230] via-[#13245a] to-[#2f5fb8] px-4 pt-20 pb-6 sm:px-8 sm:pb-8">
      <div aria-hidden className="pointer-events-none absolute inset-0">
        <svg className="absolute inset-0 size-full">
          {STARS.map(([x, y, r, opacity]) => (
            <circle key={`${x}-${y}`} cx={`${x}%`} cy={`${y}%`} r={r} fill="white" opacity={opacity} />
          ))}
        </svg>
        <svg viewBox="0 0 24 24" className="absolute top-5 right-8 size-10 drop-shadow-[0_0_14px_rgb(253_230_160/0.6)] sm:right-12">
          <path d="M20.5 14.5A9 9 0 1 1 9.5 3.5a7 7 0 0 0 11 11Z" fill="#fdeeb8" />
        </svg>
        {/* First light on the horizon. */}
        <div className="absolute inset-x-0 bottom-0 h-1/3 bg-[radial-gradient(ellipse_at_bottom,rgb(140_190_255/0.55),transparent_70%)]" />
      </div>
      <div className="relative">{children}</div>
    </div>
  );
}
