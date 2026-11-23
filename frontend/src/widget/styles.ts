// Lives inside the widget's shadow root, so the host page's CSS can't reach it and vice versa.
// Colours follow the dashboard's design tokens; --od-color is the workspace's widget colour.
export const styles = `
:host { all: initial; }
* { box-sizing: border-box; }
.od {
  --od-color: #2563eb;
  --od-soft: color-mix(in srgb, var(--od-color) 10%, #fff);
  --od-fg: #1b2333; --od-muted: #687387; --od-border: #e4e8ef; --od-bg: #f6f8fb; --od-surface: #fff;
  --od-success: #16a34a;
  font: 14px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
  color: var(--od-fg); -webkit-font-smoothing: antialiased;
}
button { font: inherit; }

/* Launcher */
.launcher { position: fixed; right: 20px; bottom: 20px; width: 54px; height: 54px; border-radius: 50%; border: 0;
  background: var(--od-color); color: #fff; cursor: pointer; z-index: 2147483646; display: grid; place-items: center;
  box-shadow: 0 4px 14px -2px color-mix(in srgb, var(--od-color) 40%, transparent), 0 2px 6px rgba(15,23,42,.10);
  transition: transform .2s cubic-bezier(.2,.8,.2,1), box-shadow .2s; }
.launcher:hover { transform: translateY(-2px) scale(1.04); }
.launcher:active { transform: scale(.96); }
.launcher:focus-visible, .od button:focus-visible, .od textarea:focus-visible, .od input:focus-visible {
  outline: 2px solid var(--od-color); outline-offset: 2px; }
.launcher svg { width: 32px; height: 32px; animation: od-pop .25s cubic-bezier(.2,.8,.2,1); }
.badge { position: absolute; top: -3px; right: -3px; min-width: 22px; height: 22px; border-radius: 11px; background: #ef4444;
  color: #fff; font-size: 11px; font-weight: 700; display: grid; place-items: center; padding: 0 6px; border: 2px solid #fff; }

/* Panel */
.panel { position: fixed; right: 20px; bottom: 86px; width: 360px; height: min(610px, calc(100vh - 110px));
  background: var(--od-bg); border-radius: 16px; z-index: 2147483647; display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 24px 64px -12px rgba(15,23,42,.28), 0 0 0 1px rgba(15,23,42,.06);
  transform-origin: bottom right; animation: od-open .24s cubic-bezier(.2,.8,.2,1); }
.panel[hidden] { display: none; }
@media (max-width: 480px) { .panel { right: 0; bottom: 0; width: 100vw; height: 100dvh; border-radius: 0; } }
@keyframes od-open { from { opacity: 0; transform: translateY(12px) scale(.97); } to { opacity: 1; transform: none; } }
@keyframes od-pop { from { opacity: 0; transform: rotate(-30deg) scale(.6); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .panel, .launcher svg, .msg { animation: none !important; } .launcher { transition: none; } }

/* Header */
.head { position: relative; color: #fff; padding: 18px 16px 16px 18px;
  background: linear-gradient(135deg, var(--od-color), color-mix(in srgb, var(--od-color) 70%, #0b1020)); }
.head::after { content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(120% 80% at 100% 0%, rgba(255,255,255,.18), transparent 60%); }
.head-row { position: relative; z-index: 1; display: flex; align-items: center; gap: 12px; }
.team { position: relative; flex: none; width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center;
  background: rgba(255,255,255,.2); font-weight: 700; font-size: 16px; box-shadow: inset 0 0 0 1px rgba(255,255,255,.25); }
.team .dot { position: absolute; right: -1px; bottom: -1px; width: 12px; height: 12px; border-radius: 50%;
  background: #22c55e; border: 2px solid color-mix(in srgb, var(--od-color) 80%, #000); }
.head h2 { margin: 0; font-size: 16px; line-height: 1.25; font-weight: 700; flex: 1; min-width: 0; letter-spacing: -.01em; }
.head .sub { display: block; font-size: 12.5px; opacity: .85; font-weight: 450; margin-top: 2px; }
.icon-btn { background: transparent; border: 0; color: inherit; cursor: pointer; width: 34px; height: 34px; border-radius: 10px;
  display: grid; place-items: center; flex: none; transition: background .15s; }
.icon-btn:hover { background: rgba(255,255,255,.16); }
.icon-btn svg { width: 19px; height: 19px; }
.icon-btn[hidden] { display: none; }

/* Tabs */
.tabs { position: relative; z-index: 1; display: flex; gap: 4px; margin-top: 14px; padding: 4px; border-radius: 999px; background: rgba(0,0,0,.16); }
.tabs button { flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 7px 10px; border: 0;
  border-radius: 999px; background: none; cursor: pointer; color: rgba(255,255,255,.85); font-size: 13px; font-weight: 600; transition: background .15s, color .15s; }
.tabs button svg { width: 15px; height: 15px; }
.tabs button:hover { color: #fff; }
.tabs button[aria-selected="true"] { background: #fff; color: var(--od-fg); box-shadow: 0 1px 3px rgba(0,0,0,.12); }

/* Messages */
.body { flex: 1; overflow-y: auto; padding: 18px 16px 8px; scrollbar-width: thin; }
.msg { display: flex; gap: 8px; align-items: flex-end; margin-bottom: 14px; animation: od-in .2s ease-out; }
@keyframes od-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
.msg.me { justify-content: flex-end; }
.msg-main { display: flex; flex-direction: column; max-width: 80%; min-width: 0; }
.me .msg-main { align-items: flex-end; }
.av { flex: none; width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; font-size: 11px; font-weight: 700;
  background: var(--od-soft); color: var(--od-color); }
.av svg { width: 15px; height: 15px; }
.who { font-size: 11.5px; color: var(--od-muted); margin: 0 4px 4px; display: flex; gap: 6px; align-items: center; font-weight: 500; }
.ai-tag { background: var(--od-soft); color: var(--od-color); font-weight: 700; font-size: 10px; padding: 1px 7px; border-radius: 999px; letter-spacing: .03em; }
.bubble { background: var(--od-surface); padding: 10px 14px; border-radius: 18px; border-bottom-left-radius: 6px; word-wrap: break-word;
  box-shadow: 0 1px 2px rgba(15,23,42,.06), 0 0 0 1px var(--od-border); }
.me .bubble { background: var(--od-color); color: #fff; box-shadow: none; border-radius: 18px; border-bottom-right-radius: 6px; }
.bubble p { margin: 0 0 6px; } .bubble p:last-child { margin: 0; }
.bubble a { color: inherit; text-decoration: underline; text-underline-offset: 2px; }
.msg:not(.me) .bubble a { color: var(--od-color); font-weight: 500; }
.system { text-align: center; margin: 4px 0 14px; }
.system span { display: inline-block; max-width: 85%; font-size: 12px; color: var(--od-muted); background: rgba(15,23,42,.05);
  padding: 4px 12px; border-radius: 999px; }
.typing { display: inline-flex; gap: 4px; padding: 14px 16px; }
.typing span { width: 7px; height: 7px; border-radius: 50%; background: var(--od-muted); animation: od-blink 1.2s infinite; }
.typing span:nth-child(2) { animation-delay: .2s; } .typing span:nth-child(3) { animation-delay: .4s; }
@keyframes od-blink { 0%, 80%, 100% { opacity: .25; transform: none; } 40% { opacity: 1; transform: translateY(-2px); } }

/* Composer */
.compose { display: flex; align-items: flex-end; gap: 6px; margin: 4px 12px 8px; padding: 6px 6px 6px 14px; background: var(--od-surface);
  border-radius: 20px; box-shadow: 0 0 0 1px var(--od-border), 0 2px 8px rgba(15,23,42,.05); transition: box-shadow .15s; }
.compose:focus-within { box-shadow: 0 0 0 2px var(--od-color), 0 2px 8px rgba(15,23,42,.05); }
.compose[hidden] { display: none; }
.compose textarea { flex: 1; resize: none; border: 0; padding: 7px 0; font: inherit; max-height: 120px; outline: none !important;
  background: transparent; color: inherit; }
.compose textarea::placeholder { color: var(--od-muted); }
.send { flex: none; width: 36px; height: 36px; border-radius: 50%; background: var(--od-color); color: #fff; border: 0; cursor: pointer;
  display: grid; place-items: center; transition: transform .15s, opacity .15s; }
.send svg { width: 17px; height: 17px; }
.send:hover:not(:disabled) { transform: scale(1.06); }
.send:disabled { opacity: .45; cursor: default; }
.counter { font-size: 11px; color: var(--od-muted); text-align: right; padding: 0 18px; }
.counter:empty { display: none; }
.counter.full { color: #b91c1c; }
.error { color: #b91c1c; font-size: 12px; padding: 0 18px 4px; }
.error:empty { display: none; }
.powered { text-align: center; font-size: 11px; color: var(--od-muted); padding: 2px 0 10px; opacity: .8; }

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
.article-row > svg { flex: none; width: 16px; height: 16px; color: var(--od-color); }
.article { background: var(--od-surface); border-radius: 16px; box-shadow: 0 0 0 1px var(--od-border); padding: 18px; }
.article h3 { margin: 0 0 12px; font-size: 18px; line-height: 1.3; letter-spacing: -.01em; }
.article p { margin: 0 0 10px; }
.article a { color: var(--od-color); }
.back { display: inline-flex; align-items: center; gap: 4px; background: none; border: 0; color: var(--od-color); cursor: pointer; padding: 4px 0;
  margin-bottom: 10px; font-weight: 600; font-size: 13px; }
.empty { color: var(--od-muted); text-align: center; padding: 28px 12px; }

/* A2UI basic catalog */
.a2ui-surface { margin-top: 8px; }
.a2ui-column { display: flex; flex-direction: column; gap: 6px; }
.a2ui-row { display: flex; gap: 6px; flex-wrap: wrap; }
.a2ui-card { border-radius: 14px; padding: 12px; background: var(--od-surface); box-shadow: 0 0 0 1px var(--od-border); }
.a2ui-text { margin: 0; }
.a2ui-divider { border: 0; border-top: 1px solid var(--od-border); margin: 4px 0; }
.a2ui-image { max-width: 100%; border-radius: 10px; }
.a2ui-button { cursor: pointer; border-radius: 999px; padding: 8px 14px; text-align: left; border: 1px solid var(--od-border);
  background: var(--od-surface); color: var(--od-fg); font-weight: 500; transition: border-color .15s, background .15s; }
.a2ui-button .a2ui-text { margin: 0; }
.a2ui-button:hover:not(:disabled) { border-color: var(--od-color); background: var(--od-soft); }
.a2ui-button-primary { background: var(--od-color); color: #fff; border-color: var(--od-color); text-align: center; font-weight: 600; }
.a2ui-button-primary:hover:not(:disabled) { background: var(--od-color); filter: brightness(1.08); }
.a2ui-button-borderless { border-color: transparent; background: var(--od-soft); color: var(--od-color); }
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
