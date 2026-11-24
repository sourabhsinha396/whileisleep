// Lives inside the widget's shadow root, so the host page's CSS can't reach it and vice versa.
// Colours follow the dashboard's design tokens; --od-color is the workspace's widget colour,
// --od-on the text on it, and --od-ink the colour as text on white (lib/contrast.ts sets all three).
export const styles = `
:host { all: initial; }
* { box-sizing: border-box; }
.od {
  --od-color: #2563eb; --od-on: #fff; --od-ink: #2563eb;
  --od-deep: color-mix(in srgb, var(--od-color) 70%, #0b1020); --od-track: rgba(0,0,0,.16);
  --od-soft: color-mix(in srgb, var(--od-color) 10%, #fff);
  --od-fg: #1b2333; --od-muted: #687387; --od-border: #e4e8ef; --od-bg: #f6f8fb; --od-surface: #fff;
  --od-success: #16a34a;
  font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  color: var(--od-fg); -webkit-font-smoothing: antialiased;
}
/* Bright colours carry dark text, so what sits behind it is lightened instead of darkened. */
.od.bright { --od-deep: color-mix(in srgb, var(--od-color) 75%, #fff); --od-track: rgba(255,255,255,.3); }
.od { --od-danger: #b91c1c; --od-idle: #e9edf3; --od-wash: rgba(15,23,42,.06); }
/* Dark: the same tokens, and the workspace's colour lightened where it is text. Important,
   because the light one is set on the element itself. */
.od.dark { --od-soft: color-mix(in srgb, var(--od-color) 24%, #1c2230); --od-ink: color-mix(in srgb, var(--od-color) 45%, #fff) !important;
  --od-fg: #e8ebf2; --od-muted: #9aa5b8; --od-border: #2c3546; --od-bg: #11151d; --od-surface: #1c2230; --od-danger: #f87171; --od-idle: #2a3344;
  --od-wash: rgba(255,255,255,.09); color-scheme: dark; }
button { font: inherit; }

/* Launcher */
.launcher { position: fixed; right: 20px; bottom: 20px; width: 54px; height: 54px; border-radius: 50%; border: 0;
  background: var(--od-color); color: var(--od-on); cursor: pointer; z-index: 2147483646; display: grid; place-items: center;
  box-shadow: 0 4px 14px -2px color-mix(in srgb, var(--od-color) 40%, transparent), 0 2px 6px rgba(15,23,42,.10);
  transition: transform .2s cubic-bezier(.2,.8,.2,1), box-shadow .2s; }
.launcher:hover { transform: translateY(-2px) scale(1.04); }
.launcher:active { transform: scale(.96); }
.launcher:focus-visible, .od button:focus-visible, .od textarea:focus-visible, .od input:focus-visible {
  outline: 2px solid var(--od-color); outline-offset: 2px; }
.head button:focus-visible { outline-color: var(--od-on); }
.launcher svg { width: 32px; height: 32px; animation: od-pop .25s cubic-bezier(.2,.8,.2,1); }
.badge { position: absolute; top: -3px; right: -3px; min-width: 22px; height: 22px; border-radius: 11px; background: #ef4444;
  color: #fff; font-size: 11px; font-weight: 700; display: grid; place-items: center; padding: 0 6px; border: 2px solid #fff; }

/* Panel */
.panel { position: fixed; right: 20px; bottom: 86px; width: 380px; height: min(640px, calc(100vh - 110px));
  background: var(--od-bg); border-radius: 16px; z-index: 2147483647; display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 24px 64px -12px rgba(15,23,42,.28), 0 0 0 1px rgba(15,23,42,.06);
  transform-origin: bottom right; animation: od-open .24s cubic-bezier(.2,.8,.2,1); }
.panel[hidden] { display: none; }
@media (max-width: 480px) { .panel { right: 0; bottom: 0; width: 100vw; height: 100dvh; border-radius: 0; } }
@keyframes od-open { from { opacity: 0; transform: translateY(12px) scale(.97); } to { opacity: 1; transform: none; } }
@keyframes od-pop { from { opacity: 0; transform: rotate(-30deg) scale(.6); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .panel, .launcher svg, .msg, .emoji, .uploading { animation: none !important; } .launcher { transition: none; } }

/* Header */
.head { position: relative; color: var(--od-on); padding: 14px 12px 12px;
  background: linear-gradient(135deg, var(--od-color), var(--od-deep)); }
.head::after { content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(120% 80% at 100% 0%, rgba(255,255,255,.18), transparent 60%); }
.head-row { position: relative; z-index: 1; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; }
/* The logo in front, teammates tucked behind it one after another. */
.faces { display: flex; align-items: center; flex: none; isolation: isolate; }
.team { position: relative; z-index: 4; flex: none; width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center;
  background: color-mix(in srgb, var(--od-color) 78%, #fff); font-weight: 700; font-size: 16px; box-shadow: 0 0 0 2px var(--od-ring); }
.bright .team { background: color-mix(in srgb, var(--od-color) 60%, #fff); }
.od { --od-ring: color-mix(in srgb, var(--od-color) 88%, #0b1020); }
.team .dot { position: absolute; right: -1px; bottom: -1px; width: 12px; height: 12px; border-radius: 50%;
  background: #22c55e; border: 2px solid var(--od-ring); }
.face { position: relative; z-index: 3; width: 40px; height: 40px; margin-left: -11px; border-radius: 50%; box-shadow: 0 0 0 2px var(--od-ring);
  background: rgba(255,255,255,.25); }
.face + .face { z-index: 2; } .face + .face + .face { z-index: 1; }
.icon-btn { background: transparent; border: 0; padding: 0; color: inherit; cursor: pointer; width: 32px; height: 32px; border-radius: 10px;
  display: grid; place-items: center; flex: none; transition: background .15s; }
.icon-btn:last-child { justify-self: end; }
.icon-btn:hover { background: rgba(255,255,255,.16); }
.icon-btn svg { width: 18px; height: 18px; }
/* Keeps its place, so the faces stay in the middle. */
.icon-btn[hidden] { visibility: hidden; }

/* Tabs */
.tabs { position: relative; z-index: 1; display: flex; gap: 3px; margin-top: 12px; padding: 3px; border-radius: 999px; background: var(--od-track); }
.tabs button { flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 5px 10px; border: 0;
  border-radius: 999px; background: none; cursor: pointer; color: color-mix(in srgb, var(--od-on) 85%, transparent); font-size: 13px; font-weight: 600; transition: background .15s, color .15s; }
.tabs button svg { width: 15px; height: 15px; }
.tabs button:hover { color: var(--od-on); }
.tabs button[aria-selected="true"] { background: #fff; color: #1b2333; box-shadow: 0 1px 3px rgba(0,0,0,.12); }

/* lib/patterns.ts. */
.pattern { position: absolute; inset: 0; pointer-events: none; }

/* Messages */
.body { flex: 1; overflow-y: auto; padding: 16px 14px 8px; scrollbar-width: thin; scrollbar-color: color-mix(in srgb, var(--od-muted) 40%, transparent) transparent; overscroll-behavior: contain; }
.msg { display: flex; gap: 8px; align-items: flex-end; margin-bottom: 3px; }
.msg.last { margin-bottom: 14px; }
.msg.new { animation: od-in .2s ease-out; }
@keyframes od-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
.msg.me { justify-content: flex-end; }
.msg-main { display: flex; flex-direction: column; max-width: 80%; min-width: 0; }
.me .msg-main { align-items: flex-end; }
.av { position: relative; flex: none; width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; font-size: 11px; font-weight: 700;
  background: var(--od-soft); color: var(--od-ink); }
.av svg { width: 15px; height: 15px; }
.av.none { background: none; }
.pic { position: absolute; inset: 0; width: 100%; height: 100%; border-radius: 50%; object-fit: cover; background: #fff; }
.who time { font-weight: 400; opacity: .8; }
.who { font-size: 11.5px; color: var(--od-muted); margin: 0 4px 4px; display: flex; gap: 6px; align-items: center; font-weight: 500; }
.bubble { background: var(--od-surface); padding: 10px 14px; border-radius: 18px; border-bottom-left-radius: 6px; overflow-wrap: anywhere;
  box-shadow: 0 1px 2px rgba(15,23,42,.06), 0 0 0 1px var(--od-border); }
.me .bubble { background: var(--od-color); color: var(--od-on); box-shadow: none; border-radius: 18px; border-bottom-right-radius: 6px; }
.bubble p, .bubble ul, .bubble ol { margin: 0 0 6px; } .bubble > :last-child { margin-bottom: 0; }
.bubble ul, .bubble ol { padding-left: 20px; list-style: revert; }
/* Inside a group, both corners on the speaker's side are tucked in. */
.msg:not(.first):not(.me) .bubble { border-top-left-radius: 6px; } .me:not(.first) .bubble { border-top-right-radius: 6px; }
.bubble a { color: inherit; text-decoration: underline; text-underline-offset: 2px; }
.msg:not(.me) .bubble a { color: var(--od-ink); font-weight: 500; }
.photo { display: block; margin-top: 4px; border-radius: 14px; overflow: hidden; box-shadow: 0 0 0 1px var(--od-border); background: var(--od-surface); }
.photo img { display: block; max-width: 100%; height: auto; object-fit: cover; }
.file-card { display: flex; align-items: center; gap: 10px; max-width: 100%; margin-top: 4px; padding: 9px 14px 9px 11px; border-radius: 14px;
  background: var(--od-surface); color: var(--od-fg); text-decoration: none; box-shadow: 0 0 0 1px var(--od-border); transition: background .15s; }
.file-card:hover { background: var(--od-soft); }
.file-card svg { flex: none; width: 20px; height: 20px; color: var(--od-ink); }
.file-card span { min-width: 0; }
.file-card strong { display: block; font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-card small { display: block; font-size: 11.5px; color: var(--od-muted); }
.system { text-align: center; margin: 4px 0 14px; }
.system span { display: inline-block; max-width: 85%; font-size: 12px; color: var(--od-muted); background: var(--od-wash);
  padding: 4px 12px; border-radius: 999px; }
.typing { display: inline-flex; gap: 4px; padding: 14px 16px; }
.typing span { width: 7px; height: 7px; border-radius: 50%; background: var(--od-muted); animation: od-blink 1.2s infinite; }
.typing span:nth-child(2) { animation-delay: .2s; } .typing span:nth-child(3) { animation-delay: .4s; }
.activity { font-size: 11.5px; color: var(--od-muted); margin: 4px 4px 0; }
@keyframes od-blink { 0%, 80%, 100% { opacity: .25; transform: none; } 40% { opacity: 1; transform: translateY(-2px); } }

/* Composer */
.compose { position: relative; margin: 4px 12px 6px; background: var(--od-surface); border-radius: 18px;
  box-shadow: 0 0 0 1px var(--od-border), 0 2px 8px rgba(15,23,42,.05); transition: box-shadow .15s; }
.compose:focus-within { box-shadow: 0 0 0 1.5px var(--od-color), 0 0 0 5px color-mix(in srgb, var(--od-color) 14%, transparent); }
.compose[hidden] { display: none; }
.compose-row { display: flex; align-items: flex-end; gap: 1px; padding: 5px 5px 5px 14px; }
.compose textarea { flex: 1; min-width: 0; resize: none; border: 0; margin: 0; padding: 6px 4px 6px 0; font: inherit; line-height: 21px; max-height: 120px;
  outline: none !important; background: transparent; color: inherit; scrollbar-width: thin; }
.compose textarea::placeholder { color: var(--od-muted); }
.tool { flex: none; width: 32px; height: 33px; padding: 0; border: 0; border-radius: 10px; background: none; color: var(--od-muted); cursor: pointer;
  display: grid; place-items: center; transition: background .15s, color .15s; }
.tool:hover, .tool[aria-expanded="true"] { background: var(--od-soft); color: var(--od-ink); }
.tool svg { width: 18px; height: 18px; }
.send { flex: none; width: 33px; height: 33px; margin-left: 4px; padding: 0; border-radius: 50%; background: var(--od-color); color: var(--od-on); border: 0; cursor: pointer;
  display: grid; place-items: center; transition: transform .15s, background .15s, color .15s; }
.send svg { width: 17px; height: 17px; }
.send:hover:not(:disabled) { transform: scale(1.06); }
.send:disabled { background: var(--od-idle); color: var(--od-muted); cursor: default; }
.emoji { position: absolute; right: 0; bottom: calc(100% + 8px); z-index: 3; display: grid; grid-template-columns: repeat(8, 34px); padding: 8px;
  background: var(--od-surface); border-radius: 16px; box-shadow: 0 12px 32px -8px rgba(15,23,42,.28), 0 0 0 1px var(--od-border); animation: od-in .15s ease-out; }
.emoji[hidden] { display: none; }
.emoji button { width: 34px; height: 34px; padding: 0; border: 0; border-radius: 9px; background: none; font-size: 19px; line-height: 1; cursor: pointer; }
.emoji button:hover { background: var(--od-soft); }
.files { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 8px 0; }
.files:empty { display: none; }
.file { display: flex; align-items: center; gap: 7px; max-width: 166px; padding: 4px 4px 4px 5px; border-radius: 10px; font-size: 12px; background: var(--od-bg); box-shadow: 0 0 0 1px var(--od-border); }
.file > svg { flex: none; width: 18px; height: 18px; margin: 0 2px; color: var(--od-ink); }
.file img { flex: none; width: 28px; height: 28px; border-radius: 7px; object-fit: cover; }
.file-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.file-remove { flex: none; width: 22px; height: 22px; padding: 0; border: 0; border-radius: 7px; background: none; color: var(--od-muted); cursor: pointer; display: grid; place-items: center; }
.file-remove:hover { background: var(--od-wash); color: var(--od-fg); }
.file-remove svg { width: 13px; height: 13px; }
.uploading img, .uploading > svg, .uploading .file-name { animation: od-wait 1.1s ease-in-out infinite; }
@keyframes od-wait { 50% { opacity: .35; } }
.drop { position: absolute; inset: 8px; z-index: 5; display: grid; place-items: center; border-radius: 12px; border: 2px dashed var(--od-color);
  background: color-mix(in srgb, var(--od-soft) 92%, transparent); color: var(--od-ink); font-weight: 600; pointer-events: none; }
.drop[hidden] { display: none; }
.counter { font-size: 11px; color: var(--od-muted); text-align: right; padding: 0 14px 6px; }
.counter:empty { display: none; }
.counter.full { color: var(--od-danger); }
.error { color: var(--od-danger); font-size: 12px; padding: 0 18px 4px; }
.error:empty { display: none; }
.powered { text-align: center; font-size: 11px; color: var(--od-muted); padding: 0 0 8px; opacity: .8; }
.powered a { color: inherit; text-decoration: underline; text-underline-offset: 2px; }
.powered a:hover { color: var(--od-fg); }

/* In the dashboard's settings: the panel where it is put, without the launcher. */
.preview { height: 100%; }
.preview .launcher { display: none; }
.preview .panel { position: relative; inset: auto; width: 100%; height: 100%; z-index: 0; animation: none; border-radius: 16px; }

/* Help center */
.search-wrap { position: relative; margin-bottom: 14px; }
.search-wrap svg { position: absolute; left: 13px; top: 50%; width: 16px; height: 16px; transform: translateY(-50%); color: var(--od-muted); pointer-events: none; }
.search { width: 100%; padding: 11px 14px 11px 38px; border: 0; border-radius: 14px; font: inherit; outline: none; background: var(--od-surface);
  color: inherit; box-shadow: 0 0 0 1px var(--od-border); }
.search:focus { box-shadow: 0 0 0 2px var(--od-color); }
.articles { background: var(--od-surface); border-radius: 16px; box-shadow: 0 0 0 1px var(--od-border); overflow: hidden; }
.articles:empty { display: none; }
.article-row { display: flex; align-items: center; gap: 10px; width: 100%; text-align: left; background: none; border: 0;
  border-top: 1px solid var(--od-border); padding: 12px 14px; cursor: pointer; color: inherit; transition: background .15s; }
.article-row:first-child { border-top: 0; }
.article-row:hover { background: var(--od-bg); }
.article-row .txt { flex: 1; min-width: 0; }
.article-row strong { display: block; font-weight: 600; }
.article-row .txt span { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; color: var(--od-muted); font-size: 13px; }
.article-row > svg { flex: none; width: 16px; height: 16px; color: var(--od-ink); }
.article { background: var(--od-surface); border-radius: 16px; box-shadow: 0 0 0 1px var(--od-border); padding: 18px; }
.article h3 { margin: 0 0 12px; font-size: 18px; line-height: 1.3; letter-spacing: -.01em; }
.article p { margin: 0 0 10px; }
.article a { color: var(--od-ink); }
.article h4, .article h5 { margin: 18px 0 8px; font-size: 16px; line-height: 1.35; font-weight: 700; }
.article h5 { font-size: 14px; }
.article ul, .article ol { margin: 0 0 10px; padding-left: 22px; list-style: revert; }
.article li { margin: 0 0 4px; }
.article li > ul, .article li > ol { margin: 4px 0 0; }
.article img { display: block; max-width: 100%; height: auto; margin: 6px 0; border-radius: 10px; box-shadow: 0 0 0 1px var(--od-border); }
.back { display: inline-flex; align-items: center; gap: 4px; background: none; border: 0; color: var(--od-ink); cursor: pointer; padding: 4px 0;
  margin-bottom: 10px; font-weight: 600; font-size: 13px; }
.empty { color: var(--od-muted); text-align: center; padding: 28px 12px; }

/* A2UI (public/a2ui/v1/catalog.json) */
.a2ui-surface { margin-top: 8px; }
.a2ui-column { display: flex; flex-direction: column; gap: 6px; }
.a2ui-row { display: flex; gap: 6px; flex-wrap: wrap; }
.a2ui-card { border-radius: 14px; padding: 12px; background: var(--od-surface); box-shadow: 0 0 0 1px var(--od-border); }
.a2ui-text { margin: 0; }
.a2ui-text-title { font-weight: 600; }
.a2ui-text-value { font-weight: 500; text-align: right; margin-left: auto; }
.a2ui-row-detail, .a2ui-row-step { flex-wrap: nowrap; gap: 12px; }
.a2ui-row-step { gap: 8px; }
.a2ui-row-detail > *, .a2ui-row-step > * { min-width: 0; overflow-wrap: anywhere; }
.a2ui-row-step > :first-child, .a2ui-row-detail > .a2ui-text-label { flex: none; max-width: 50%; }
.a2ui-text-label, .a2ui-text-todo { color: var(--od-muted); }
.a2ui-text-done { color: var(--od-success); font-weight: 700; }
.a2ui-divider { border: 0; border-top: 1px solid var(--od-border); margin: 4px 0; }
.a2ui-image { max-width: 100%; border-radius: 10px; }
.a2ui-button { cursor: pointer; border-radius: 999px; padding: 8px 14px; text-align: left; border: 1px solid var(--od-border);
  background: var(--od-surface); color: var(--od-fg); font-weight: 500; transition: border-color .15s, background .15s; }
.a2ui-button .a2ui-text { margin: 0; }
.a2ui-button:hover:not(:disabled) { border-color: var(--od-color); background: var(--od-soft); }
.a2ui-button-primary { background: var(--od-color); color: var(--od-on); border-color: var(--od-color); text-align: center; font-weight: 600; }
.a2ui-button-primary:hover:not(:disabled) { background: var(--od-color); filter: brightness(1.08); }
.a2ui-button-borderless { border-color: transparent; background: var(--od-soft); color: var(--od-ink); }
.a2ui-button:disabled { opacity: .55; cursor: default; }
.a2ui-field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--od-muted); font-weight: 500; }
.a2ui-input { font: inherit; font-size: 14px; padding: 9px 12px; border: 0; border-radius: 10px; background: var(--od-surface); color: var(--od-fg);
  box-shadow: 0 0 0 1px var(--od-border); outline: none; }
.a2ui-input:focus { box-shadow: 0 0 0 2px var(--od-color); }
.a2ui-choices { border: 0; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.a2ui-choices legend { padding: 0; margin-bottom: 4px; font-size: 12px; color: var(--od-muted); font-weight: 500; }
.a2ui-choice { display: flex; align-items: center; gap: 8px; font-size: 14px; cursor: pointer; }
.a2ui-choice input { accent-color: var(--od-color); }
`;
