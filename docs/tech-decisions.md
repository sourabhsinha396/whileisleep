# Tech decisions

Technical decisions made by the project owner, newest first. Each says what was decided and, when
given, why. A reversed decision stays here, marked as replaced, with a link to the new one.
Product decisions are in [product-decisions.md](product-decisions.md).

## 2026-11-24: Payments work without webhooks

**Decision.** Payments work without a webhook key, locally and in production. When someone comes back from checkout, we ask
Dodo. Webhooks are only for odd cases, such as a lost connection after paying.

**Why.** Depending completely on webhooks is not good.

## 2026-11-24: Country flags load from flagcdn.com

**Decision.** The flag images come from flagcdn.com, instead of copies on our own server.

## 2026-11-24: Slow services never block our threads

**Decision.** If many requests to Slack, or any outside service, are slow, they must not block our threads. No blocking
call runs inside async code.

## 2026-11-24: Integrations are plugins

**Decision.** The code is kept so that other people can build plugins, and we can add integrations easily when needed.

## 2026-11-24: Payments go through Dodo Payments

**Decision.** The hosted plans are sold with Dodo Payments.

## 2026-11-24: Decisions are in two files

**Decision.** Tech decisions are in this file, and product decisions in [product-decisions.md](product-decisions.md).

## 2026-11-24: Uploaded images are kept in folders

**Decision.** A workspace's images are arranged in folders and subfolders in Cloudflare R2, not all in one place.

## 2026-11-24: The deploy guide is for any VM

**Decision.** The guide is "Deploy on a VM (before your Noodles is ready)" (`docs/deploy-vm.md`), not tied to Hetzner.

## 2026-11-24: Technical decisions are kept in this file

**Decision.** Technical decisions the owner gives are recorded in `docs/decision.md`.

Replaced by [Decisions are in two files](#2026-11-24-decisions-are-in-two-files).

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
