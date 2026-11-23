// Lives inside the widget's shadow root, so the host page's CSS can't reach it and vice versa.
export const styles = `
:host { all: initial; }
* { box-sizing: border-box; }
.od { --od-color: #2563eb; font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #111827; }
.launcher { position: fixed; right: 20px; bottom: 20px; width: 56px; height: 56px; border-radius: 50%; border: 0;
  background: var(--od-color); color: #fff; cursor: pointer; box-shadow: 0 8px 24px rgba(0,0,0,.18); z-index: 2147483646;
  display: grid; place-items: center; transition: transform .15s; }
.launcher:hover { transform: scale(1.05); }
.launcher svg { width: 26px; height: 26px; }
.badge { position: absolute; top: -2px; right: -2px; min-width: 20px; height: 20px; border-radius: 10px; background: #ef4444;
  color: #fff; font-size: 11px; font-weight: 700; display: grid; place-items: center; padding: 0 5px; }
.panel { position: fixed; right: 20px; bottom: 88px; width: 380px; height: min(620px, calc(100vh - 110px)); background: #fff;
  border-radius: 16px; box-shadow: 0 16px 48px rgba(0,0,0,.2); z-index: 2147483647; display: flex; flex-direction: column;
  overflow: hidden; }
.panel[hidden] { display: none; }
@media (max-width: 480px) { .panel { right: 0; bottom: 0; width: 100vw; height: 100dvh; border-radius: 0; } }
.head { background: var(--od-color); color: #fff; padding: 14px 16px; display: flex; align-items: center; gap: 10px; }
.head h2 { margin: 0; font-size: 16px; font-weight: 650; flex: 1; }
.head .sub { font-size: 12px; opacity: .85; font-weight: 400; display: block; }
.icon-btn { background: transparent; border: 0; color: inherit; cursor: pointer; padding: 4px; border-radius: 6px; display: grid; }
.icon-btn:hover { background: rgba(255,255,255,.15); }
.icon-btn svg { width: 20px; height: 20px; }
.tabs { display: flex; border-bottom: 1px solid #e5e7eb; }
.tabs button { flex: 1; padding: 10px; border: 0; background: none; cursor: pointer; font: inherit; color: #6b7280; border-bottom: 2px solid transparent; }
.tabs button[aria-selected="true"] { color: #111827; border-color: var(--od-color); font-weight: 600; }
.body { flex: 1; overflow-y: auto; padding: 16px; background: #f9fafb; }
.msg { display: flex; flex-direction: column; margin-bottom: 12px; max-width: 85%; }
.msg.me { margin-left: auto; align-items: flex-end; }
.who { font-size: 11px; color: #6b7280; margin: 0 4px 3px; display: flex; gap: 6px; align-items: center; }
.ai-tag { background: #dcfce7; color: #166534; font-weight: 700; font-size: 10px; padding: 1px 6px; border-radius: 4px; letter-spacing: .03em; }
.bubble { background: #fff; border: 1px solid #e5e7eb; padding: 9px 12px; border-radius: 14px; border-top-left-radius: 4px; word-wrap: break-word; }
.me .bubble { background: var(--od-color); border-color: var(--od-color); color: #fff; border-radius: 14px; border-top-right-radius: 4px; }
.bubble p { margin: 0 0 6px; } .bubble p:last-child { margin: 0; }
.bubble a { color: inherit; text-decoration: underline; }
.typing { display: inline-flex; gap: 4px; padding: 12px; }
.typing span { width: 6px; height: 6px; border-radius: 50%; background: #9ca3af; animation: od-blink 1.2s infinite; }
.typing span:nth-child(2) { animation-delay: .2s; } .typing span:nth-child(3) { animation-delay: .4s; }
@keyframes od-blink { 0%, 80%, 100% { opacity: .3 } 40% { opacity: 1 } }
.compose { display: flex; gap: 8px; padding: 10px; border-top: 1px solid #e5e7eb; background: #fff; }
.compose textarea { flex: 1; resize: none; border: 1px solid #d1d5db; border-radius: 10px; padding: 9px 11px; font: inherit; max-height: 120px; outline: none; }
.compose textarea:focus { border-color: var(--od-color); }
.send { background: var(--od-color); color: #fff; border: 0; border-radius: 10px; padding: 0 14px; cursor: pointer; font-weight: 600; }
.send:disabled { opacity: .5; cursor: default; }
.counter { font-size: 11px; color: #6b7280; text-align: right; padding: 0 14px; min-height: 0; }
.counter:empty { display: none; }
.counter.full { color: #b91c1c; }
.error { color: #b91c1c; font-size: 12px; padding: 4px 12px 0; }
.search { width: 100%; padding: 9px 12px; border: 1px solid #d1d5db; border-radius: 10px; font: inherit; margin-bottom: 12px; outline: none; }
.article-row { display: block; width: 100%; text-align: left; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
  padding: 10px 12px; margin-bottom: 8px; cursor: pointer; font: inherit; color: inherit; }
.article-row:hover { border-color: var(--od-color); }
.article-row strong { display: block; } .article-row span { color: #6b7280; font-size: 13px; }
.article h3 { margin: 0 0 10px; font-size: 17px; }
.article p { margin: 0 0 10px; }
.back { background: none; border: 0; color: var(--od-color); cursor: pointer; padding: 0; margin-bottom: 10px; font: inherit; }
.empty { color: #6b7280; text-align: center; margin-top: 24px; }
.powered { text-align: center; font-size: 11px; color: #9ca3af; padding: 4px 0 8px; background: #fff; }
/* A2UI basic catalog */
.a2ui-surface { margin-top: 8px; }
.a2ui-column { display: flex; flex-direction: column; gap: 6px; }
.a2ui-row { display: flex; gap: 6px; flex-wrap: wrap; }
.a2ui-card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px; background: #fff; }
.a2ui-text { margin: 0; }
.a2ui-divider { border: 0; border-top: 1px solid #e5e7eb; margin: 4px 0; }
.a2ui-image { max-width: 100%; border-radius: 8px; }
.a2ui-button { font: inherit; cursor: pointer; border-radius: 10px; padding: 8px 12px; text-align: left; border: 1px solid #d1d5db; background: #fff; color: #111827; }
.a2ui-button .a2ui-text { margin: 0; }
.a2ui-button:hover:not(:disabled) { border-color: var(--od-color); }
.a2ui-button-primary { background: var(--od-color); color: #fff; border-color: var(--od-color); text-align: center; }
.a2ui-button-borderless { border-color: #e5e7eb; color: var(--od-color); }
.a2ui-button:disabled { opacity: .55; cursor: default; }
.a2ui-field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #374151; }
.a2ui-input { font: inherit; font-size: 14px; padding: 8px 10px; border: 1px solid #d1d5db; border-radius: 8px; }
.a2ui-choices { border: 0; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.a2ui-choices legend { padding: 0; margin-bottom: 4px; font-size: 12px; color: #374151; }
.a2ui-choice { display: flex; align-items: center; gap: 8px; font-size: 14px; cursor: pointer; }
.a2ui-choice input { accent-color: var(--od-color); }
`;
