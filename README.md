# whileisleep

Open-source customer chat, like Crisp, with an AI agent that answers from your own data.

The idea that shapes it: **code decides whatever code can decide, and the model only writes
language.** A visitor message goes through a pipeline that tries the cheapest way to answer
first, and records which stage answered and what it cost.

## What it does

- **Workspaces**: one per website, each with its own inbox, team, help center, AI tools and widget.
- **Inbox**: conversations from the widget; reply, add internal notes, resolve, hand back to the AI.
- **Visitors**: who's on your site now, and what page they're on; message them first.
- **Knowledge base**: articles in the widget's Help tab. They are split into passages and indexed with
  Postgres full-text search, so the AI reads the section that answers a question, not whole articles.
- **Organizations**: own workspaces and the LLM settings. The owner sets an **OpenRouter API key and
  model** on the Organization & LLM page (the key is write-only and encrypted in the database).
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

## Identifying visitors

```js
// What the page says. Useful for display; not proof.
window.whileisleep.identify({ name, email, attributes: { plan: "pro" } });
```

Anything from the page can be typed into a browser console, so a tool that returns someone's data
(`/orders?email={visitor.email}`) only accepts **verified** values. Your server signs a short-lived
token with the workspace's identity secret (Settings & widget) and the page passes it on:

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

## Layout

- `backend/`: Django + django-ninja, Postgres, uv. Apps in `backend/apps/`:
  `accounts` (token auth), `workspaces` (organizations, workspaces, members),
  `conversations` (visitors, conversations, messages, attributes, identity, widget API),
  `knowledge` (articles, passages, search),
  `agent` (pipeline, rules and conditions, the OpenRouter tool loop, the Celery tasks, HTTP and MCP
  tools, turns, A2UI).
  Tests in `backend/tests/`, with factories in `tests/factories.py`.
- `frontend/`: Next.js App Router dashboard, plus the widget (`src/widget`, built by esbuild into
  `public/widget.js`). Tests in `frontend/tests/`.
- `deploy/`: the production Docker Compose stack. `docs/deploy-hetzner.md` walks through it.

## Run locally

```sh
cd backend && cp .env.example .env    # set DEMO_EMAIL, DEMO_PASSWORD (OPENROUTER_API_KEY optional, for seed_demo)
docker compose up -d --build          # API on WEB_PORT (8004), Postgres on 5448, Redis, and the worker
docker compose exec -T web python manage.py seed_demo   # optional demo owner + 2 workspaces

cd ../frontend && cp .env.example .env   # WEB_PORT (3004), API_URL
pnpm install && pnpm dev
```

The `worker` container writes the AI's replies and restarts itself when the code changes
(`docker compose logs -f worker` shows each one). Running Django outside Docker with no
`REDIS_URL` needs no worker: replies are then written inside the request.

Then set the OpenRouter key and model on **Organization & LLM** in the dashboard. Until both are set, or
if OpenRouter fails (bad key, no credits), the bot falls back to a help center search and leaves the
reason as an internal note in the conversation.

Add the widget to any site (Settings & widget shows the snippet):

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

## Deploy

One server with Docker Compose: Caddy for HTTPS, the API, the worker and its scheduler, the
dashboard, Postgres and Redis.
See [docs/deploy-hetzner.md](docs/deploy-hetzner.md).

## Next

- Real-time updates over SSE instead of polling; email notifications.
- Exact answers: human-approved snippets sent verbatim when a question matches.
- The inbox showing each reply's Turn (rule, passages, tools, tokens, cost) and the attributes panel.
- Dashboard sessions in httpOnly cookies, and login tokens hashed in the database.
- Tool result shaping (keep only named fields) and per-tool approval before actions that change data.
- Optional vector search next to full-text search.
