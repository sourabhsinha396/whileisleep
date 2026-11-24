# Decisions

Technical decisions made by the project owner, newest first. Each says what was decided and, when
given, why. A reversed decision stays here, marked as replaced, with a link to the new one.

## 2026-11-24: Several AI providers, and one fallback model

**Decision.** Customers can use OpenAI, Anthropic, OpenRouter and one more provider (Google Gemini was chosen), not
only OpenRouter. They can also pick a fallback model, from any provider. There is never more than one fallback.

**Why.** When the chosen model is down, say OpenAI's, another one such as Anthropic's Haiku should answer.

## 2026-11-24: Help articles are written in a small visual editor

**Decision.** A minimal what-you-see-is-what-you-get editor, from a popular toolkit, with only 5 or 6 controls.
It is Tiptap, with bold, heading, bullet list, numbered list, link and image.

## 2026-11-24: Uploaded images are kept in folders

**Decision.** A workspace's images are arranged in folders and subfolders in Cloudflare R2, not all in one place.

## 2026-11-24: The README has one GIF and two images

**Decision.** At most one GIF (or interactive demo) and two images, with the inbox captured on a large screen.

**Why.** On a small screen the chat looked narrow.

## 2026-11-24: One Settings entry with groups inside it

**Decision.** The sidebar holds the daily work (inbox, visitors, knowledge base, AI agent), and everything set up
once sits behind one Settings entry, in groups with sub-settings the way Crisp does it. Related settings are merged.

**Why.** The sidebar was not arranged well: organization and LLM settings sat beside the daily pages.

## 2026-11-24: The deploy guide is for any VM

**Decision.** The guide is "Deploy on a VM (before your Maggi is ready)" (`docs/deploy-vm.md`), not tied to Hetzner.

## 2026-11-24: The README is for visitors, not a code reference

**Decision.** The README shows what whileisleep does and how the UI looks, and lets the reader explore.
It has no references to code, and at most 10 important commands (ideally 5).

**Why.** Nobody reads code today, so code references in the README don't help the people who land on
the GitHub page.

## 2026-11-24: Technical decisions are kept in this file

**Decision.** Technical decisions the owner gives are recorded in `docs/decision.md`.

## 2026-11-24: `main` is the only long-lived branch

**Decision.** `master` became `main`, the v1 revamp was brought into it, and the old branches were deleted.

## 2026-11-23: Celery and Redis run the background jobs

**Decision.** The job queue is Celery on Redis, chosen over a Postgres queue (Procrastinate).

**Why.** The owner already runs Celery in other projects.

## 2026-11-23: Deploy to one Hetzner server

**Decision.** Production is Docker Compose on a single Hetzner server, not Kubernetes.

## 2026-11-23: The backend is Django with Django Ninja

**Decision.** The backend stays Django, and APIs use Django Ninja.

## 2026-11-23: Small commits, and tests with every change

**Decision.** One understandable change per commit, each with its tests.

**Why.** The project is open source, so people will review the history.
