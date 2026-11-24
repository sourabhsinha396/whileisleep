# How whileisleep works

The technical reference: integration, security and internals. For what the product is, see the [README](../README.md).

## What it does

- **Workspaces**: one per website, each with its own inbox, team, help center, AI tools and widget.
- **Inbox**: conversations from the widget; reply, add internal notes, resolve, hand back to the AI. Replies can have
  bold, italic, links and lists, stored as Markdown (`frontend/src/lib/chat-text.ts`). What a visitor types is shown as typed.
- **Files in chats**: pictures (checked and saved again), PDF, text, CSV, Word and Excel, up to 10 MB and five to a
  message, from both sides. Only with your own storage connected. A file's address is random but public, so anyone who
  has the link can open it. Documents open as downloads. One that is never sent is deleted after a day. The AI is told
  a file's name and that it can't open it.
- **Widget appearance**: color, logo, background pattern, and light, dark or the visitor's own mode. The header shows
  the logo and up to three teammates who have a photo, owners first.
- **Visitors**: who's on your site now, and what page they're on; message them first.
- **Knowledge base**: articles in the widget's Help tab. They are split into passages and indexed with
  Postgres full-text search, so the AI reads the section that answers a question, not whole articles.
  Written in a small visual editor and stored as Markdown; the AI reads a picture's description.
- **Images**: the workspace's logo and teammates' photos, in the server's S3-compatible bucket, and article pictures,
  in the customer's own. Every upload is checked and saved again as an image, in folders:
  `workspaces/<id>/logo`, `workspaces/<id>/articles/<article id>` and `users/<id>/photo`.
- **Your own storage** (optional): an organization connects its S3-compatible bucket in Settings › Storage, and its
  articles' images and its chats' files go there, under `whileisleep/`. Without one, both are text. Connecting tries the bucket first
  (write, open the public address, delete). Disconnecting leaves the files where they are.
- **Get started**: a row in the sidebar with the next setup step. Each step is done when the thing itself is there.
- **Organizations**: own workspaces and the LLM settings. In Settings › AI model the owner adds a key for
  **OpenAI, Anthropic, Google Gemini or OpenRouter** (write-only, and encrypted in the database) and picks
  the **model** that answers, and optionally one **fallback** model. When a call to the model fails, for any
  reason, the fallback takes over that reply from the same point; tools that ran aren't run again, and the
  team gets an internal note. The next reply starts with the main model. If both fail in a way that may
  pass, they are tried again after a few seconds, and then the help center answers.
- **AI agent and tools**: the LLM answers visitors. Each workspace adds **tools** (HTTP endpoints on its
  own systems: product search, stock, order status…) so the agent looks facts up instead of guessing.
  Built in: `search_knowledge_base`, `handoff_to_human`, and `reply_to_visitor` (how the model finishes).
- **MCP servers**: connect a Model Context Protocol server and its tools are imported next to your own.
  They arrive switched off; you turn on the ones the agent may use, and a tool whose description the
  server later changes is paused until you approve it again.
- **Rules** run in code on each visitor message, before the AI; the first match wins.
  - *Conditions* are a tree of tests joined by all / any / not, over the message, the page, attributes,
    tags and the workspace's local time: `contact.plan is pro`, `time.hour is at least 18`.
  - *Actions*: an exact reply (the AI stays quiet), a one-off instruction for the AI, a tag, a hand-off,
    or an attribute to remember, which later rules can test.
  - *Try before saving*: the editor shows how many recent messages a rule would have matched.
- **Attributes** are what you know about a visitor (email, plan) or one conversation (order number),
  each with its *source*: `verified`, `agent`, `rule`, `host`, `visitor` or `ai`. A less trusted
  source never overwrites a more trusted one. Rules, reply templates, tools and the AI all read them.
- **Playbooks**: plain-language procedures. The AI sees each title and "when to use" line and loads the
  full text with the `read_playbook` tool when a conversation matches.
- **Turns**: every visitor message leaves a record of the stage that answered it (rule, limit, AI or
  fallback), the model, tokens, cost, duration and each tool call. `GET /turns/summary` shows how much
  of your traffic never needed the model.
- **A2UI**: bot replies carry [A2UI](https://a2ui.org) v1.0 surfaces (article buttons, "Talk to a person",
  forms). The server builds them from templates; the widget renders them with a small safe renderer
  (`frontend/src/lib/a2ui`), and button events come back to `POST /api/v1/widget/{key}/actions`.

## The reply pipeline (`backend/apps/agent/pipeline.py`)

1. **Rules.** A rule with a fixed reply answers on its own: no model call.
2. **Nobody replies** if the AI is off or a person has the conversation.
3. **Limits.** Past the daily AI cap the conversation goes to a person.
4. **The AI.** A burst of quick messages is answered once, by the newest. The help center is searched with the visitor's message first, and the best passages go
   into the prompt, so a question the help center answers takes one model call. If the model is
   unavailable, a help center search answers instead.

Stages 1 to 3 run inside the visitor's request. The AI stage is a **Celery job** on Redis
(`backend/apps/agent/tasks.py`), so the request returns at once and a worker writes the reply:

- a reply survives a restart (jobs are acknowledged when they finish);
- one reply at a time per conversation (a lock), and a burst of messages gets one answer;
- a provider hiccup (timeout, rate limit, 5xx) is retried after 3 and 10 seconds before the
  help center fallback answers, unless a tool has already run;
- once a minute a sweep re-runs the pipeline for any message whose job was lost.

The prompt is ordered from what never changes (the business's instructions) to what changes every
message (passages, a rule's instruction), so providers can cache its beginning.

## Live updates (`backend/apps/realtime`)

The widget and the inbox get new messages, what the AI is doing ("Searching the help center", from
the steps its Turn records), "is typing" and who is online as they happen, over **server-sent
events**. No WebSockets: sending stays plain REST.

- Whatever changes something (the API, the Celery worker) publishes it on **Redis pub/sub**: one
  channel per visitor (never notes or system messages) and one per workspace.
- **Async Django views on an ASGI process** (uvicorn, the `stream` service) hold the open
  connections: `GET /api/v1/widget/{key}/stream` and `GET /api/v1/workspaces/{id}/stream`.
- Browsers read them with `fetch`, not `EventSource`, so the visitor and dashboard tokens go in
  headers, never the URL. A reconnect sends `Last-Event-ID` (the newest message id the page has)
  and gets what it missed first.
- Typing is a POST (`/widget/{key}/typing`, `.../conversations/{id}/typing`) sent at most every
  3 seconds; only who is typing goes out, never the draft.
- **Presence** is a Redis key per visitor with a 45-second TTL, refreshed by the open stream.
- While a stream is down the page polls the REST endpoints, as often as it used to.

## Identifying visitors

```js
// What the page says. Useful for display; not proof.
window.whileisleep.identify({ name, email, attributes: { plan: "pro" } });
```

Anything from the page can be typed into a browser console, so a tool that returns someone's data
(`/orders?email={visitor.email}`) only accepts **verified** values. Your server signs a short-lived
token with the workspace's identity secret (Settings › Verified identity) and the page passes it on:

```python
import jwt, time
token = jwt.encode(
    {"sub": str(user.id), "email": user.email, "plan": "pro", "exp": int(time.time()) + 3600},
    WHILEISLEEP_IDENTITY_SECRET, algorithm="HS256",
)
```

```js
window.whileisleep.identify({ token });
```

`sub` ties the visitor to your user, so they keep their conversations across devices; the other
claims become verified attributes.

## Limits and context (`backend/whileisleep/settings/base.py`)

- Visitor messages: 500 characters (`VISITOR_MESSAGE_MAX_CHARS`), enforced in the widget and the API.
- `RATE_LIMITS`: messages per visitor and per IP per minute, new visitors per IP per hour, and daily
  AI replies per visitor and per workspace. Counters live in Django's cache, which is Redis whenever
  `REDIS_URL` is set (Docker Compose sets it, in development and production).
- What the AI sees: recent messages up to `HISTORY_BUDGET_CHARS`, an "About this conversation" block
  built from stored data (name, attributes, current page, tags), and up to `KNOWLEDGE_BUDGET_CHARS` of
  help center text per search.
- A visitor writing after `CONVERSATION_IDLE_HOURS` (24) of quiet starts a new conversation.

## Security

- Tools can't call private network addresses (`whileisleep/outbound.py`); set
  `OUTBOUND_ALLOW_PRIVATE_NETWORKS` only if yours live there.
- LLM keys and tool headers are encrypted at rest with `ENCRYPTION_KEYS`.
- Rate limits read the client address only from proxies you declare (`TRUSTED_PROXY_COUNT`).
- `SIGNUP_ENABLED=false` closes account creation on a private installation.
- Plans (only where they are sold) are paid on Dodo Payments' own pages; no card detail reaches this server. A
  signed webhook only says which subscription changed, and its state is then read from Dodo.

## Layout

- `backend/`: Django + django-ninja, Postgres, uv. Apps in `backend/apps/`:
  `accounts` (token auth), `workspaces` (organizations, workspaces, members),
  `conversations` (visitors, conversations, messages, attributes, identity, widget API),
  `knowledge` (articles, passages, search),
  `agent` (pipeline, rules and conditions, the OpenRouter tool loop, the Celery tasks, HTTP and MCP
  tools, turns, A2UI), `realtime` (Redis pub/sub, presence, the live streams).
  Tests in `backend/tests/`, with factories in `tests/factories.py`.
- `frontend/`: Next.js App Router dashboard, plus the widget (`src/widget`, built by esbuild into
  `public/widget.js`). Tests in `frontend/tests/`.
- `deploy/`: the production Docker Compose stack. [deploy-vm.md](deploy-vm.md) walks through it.

## The widget

Add the widget to any site (Settings › Install shows the snippet):

```html
<script src="http://localhost:3004/widget.js" data-workspace="ws_..." async></script>
```

The script sets `window.whileisleep` and fires `whileisleep:ready` on `window`:
`open(message?, { intent, data })` (opens with the message typed in; rules can match the intent),
`close()`, `hide()` / `show()`, `identify(...)` (above), `restart()` to clear the chat and start a new
conversation (also a button in the chat header), and `reset()` on sign-out.

## Test

Backend tests run on Postgres (the `db` service from `docker compose up -d db`); they need no
`.env` and make no network calls.

```sh
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && pnpm test && pnpm lint && pnpm typecheck
```

CI (`.github/workflows/ci.yml`) runs the same, checks that every model change has a migration, and
builds the production images.

## Next

- Email notifications.
- Exact answers: human-approved snippets sent verbatim when a question matches.
- The inbox showing each reply's Turn (rule, passages, tools, tokens, cost) and the attributes panel.
- Dashboard sessions in httpOnly cookies, and login tokens hashed in the database.
- Tool result shaping (keep only named fields) and per-tool approval before actions that change data.
- Optional vector search next to full-text search.
