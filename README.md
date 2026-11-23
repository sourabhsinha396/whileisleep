# whileisleep

Open-source customer chat, like Crisp, with an AI agent that answers from your own data.

- **Workspaces**: one per website, each with its own inbox, team, help center, AI tools and widget.
- **Inbox**: conversations from the widget; reply, add internal notes, resolve, hand back to the AI.
- **Visitors**: who's on your site now, and what page they're on; message them first.
- **Knowledge base**: articles in the widget's Help tab, which the AI agent also searches.
- **Organizations**: own workspaces and the LLM settings. The owner sets an **OpenRouter API key and
  model** on the Organization & LLM page; every workspace's agent uses them (key is write-only).
- **AI agent and tools**: the LLM answers visitors. Each workspace adds **tools** (HTTP endpoints on its own
  systems: product search, stock, order status…) so the agent looks facts up instead of guessing.
  Built in: `search_knowledge_base`, `handoff_to_human`, and `reply_to_visitor` (how the model finishes).
- **Rules & playbooks** (no flow builder):
  - *Rules* run in code on each visitor message, before the AI, first match wins. Conditions: intent,
    keywords, page URL, first message. Actions: an exact reply (the AI stays quiet), a one-off
    instruction for the AI, a tag, a hand-off. Optionally also after a person took over.
  - *Intents*: a button on the host site opens the chat with `window.whileisleep.open(text, { intent:
    "exam_request", data: { exam_name } })`; rules match the intent and fill `{data.exam_name}` in replies.
  - *Playbooks*: plain-language procedures. The AI sees only each title and "when to use" line and
    loads the full text with the `read_playbook` tool when a conversation matches.
- **A2UI**: bot replies carry [A2UI](https://a2ui.org) v1.0 surfaces (article buttons, "Talk to a person", an
  email form). The server builds them from templates; the widget renders them with a small safe renderer
  (`frontend/src/lib/a2ui`), and button events come back to `POST /api/v1/widget/{key}/actions`.

## Limits and context (`backend/whileisleep/settings/base.py`)

- Visitor messages: 500 characters (`VISITOR_MESSAGE_MAX_CHARS`), enforced in the widget and the API.
- `RATE_LIMITS`: messages per visitor and per IP per minute, new visitors per IP per hour, and daily
  AI replies per visitor and per workspace. Past an AI cap the conversation goes to a person. Counters
  live in Django's cache: use Redis once there's more than one worker.
- What the AI sees: recent messages up to `HISTORY_BUDGET_CHARS` (always the last few), plus an
  "About this conversation" block built from stored data: name, whether we have their email, current
  page, what button they came from, any unanswered form, tags.
- A visitor writing after `CONVERSATION_IDLE_HOURS` (24) of quiet starts a new conversation.

## Layout

- `backend/`: Django + django-ninja, Postgres, uv. `whileisleep/env.py` validates `.env` with pydantic at
  startup: unknown keys and missing required keys stop the server. Apps in `backend/apps/`:
  `accounts` (token auth), `workspaces` (organizations, workspaces, members), `conversations` (visitors, conversations, messages, widget API),
  `knowledge` (articles, search), `agent` (the OpenRouter tool loop, HTTP tools, A2UI builders, widget actions).
  Tests in `backend/tests/`, with factories in `tests/factories.py`.
- `frontend/`: Next.js App Router dashboard, plus the widget (`src/widget`, built by esbuild into
  `public/widget.js`). Tests in `frontend/tests/`.

## Run

```sh
cd backend && cp .env.example .env    # set DEMO_EMAIL, DEMO_PASSWORD (OPENROUTER_API_KEY optional, for seed_demo)
docker compose up -d                  # API on WEB_PORT (8004), Postgres on 5448
docker compose exec -T web python manage.py seed_demo   # optional demo owner + 2 workspaces

cd ../frontend && cp .env.example .env   # WEB_PORT (3004), API_URL
pnpm install && pnpm dev
```

Then set the OpenRouter key and model on **Organization & LLM** in the dashboard. Until both are set, or
if OpenRouter fails (bad key, no credits), the bot falls back to a keyword search of the knowledge base
and leaves the reason as an internal note in the conversation.

Add the widget to any site (Settings & widget shows the snippet):

```html
<script src="http://localhost:3004/widget.js" data-workspace="ws_..." async></script>
```

The script sets `window.whileisleep` and fires `whileisleep:ready` on `window`:
`open(message?)` (opens with the message typed in), `close()`, `hide()` / `show()` (for pages where the
bubble is in the way), `identify({ name, email })` for signed-in users, and `reset()` on sign-out.

## Test

```sh
cd backend && uv run pytest && uv run ruff check .
cd frontend && pnpm test && pnpm lint && pnpm typecheck
```

## Next

- MCP servers as a second tool source (a workspace adds an MCP URL; the agent lists its tools).
- Real-time updates over SSE instead of polling; email notifications; identity verification for
  `{visitor.email}` tools; Celery for bot replies instead of a thread; encrypt stored secrets
  (OpenRouter keys, tool headers) at rest.
