---
title: Self-hosting
description: Deploy whileisleep on a VM, before your Noodles is ready 🍜
seo_title: Self-host an AI support chat
seo_description: Deploy whileisleep on your own VM with Docker Compose and pm2, with HTTPS, Postgres, Redis, backups, updates and troubleshooting, step by step.
---

One small virtual machine, from any provider, runs everything. Docker Compose runs the backend: the Django API, the stream process that sends live updates to the widget and the inbox, a Celery worker that writes the AI's replies, another that talks to Slack and webhooks, Postgres and Redis. pm2 runs the Next.js dashboard. A Cloudflare Tunnel gives it HTTPS, so no web port is open on the server.

## What you need

- A VM with 2 vCPU, 4 GB RAM and **Ubuntu 24.04** is enough to start; the AI calls happen at your LLM provider, not on this machine.
- A domain on Cloudflare, for example `chat.example.com`. Any reverse proxy with HTTPS works too (see step 4).
- An API key from OpenAI, Anthropic, Google Gemini or OpenRouter (you enter it in the dashboard after the first login, not here).

## 1. Install Docker, Node.js and pm2

Allow only SSH in your provider's firewall, then on the VM:

```sh
curl -fsSL https://get.docker.com | sh
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g pnpm@10 pm2
```

## 2. Get the code and configure it

```sh
git clone https://github.com/YOUR_ACCOUNT/whileisleep.git /opt/whileisleep
cd /opt/whileisleep
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

`frontend/.env` is for the website. The ports in both files are on the VM, open to the VM itself only: change them if something else uses them. If you change `WEB_PORT` or `STREAM_PORT` in `backend/.env`, put the same ports in `API_URL` and `STREAM_URL` in `frontend/.env`.

The contact, privacy, terms and refund pages appear when `frontend/.env` has `COMPANY_NAME` and `COMPANY_EMAIL`. Their text describes our hosted service, so leave these empty unless it is true for yours too.

For session replays of your own dashboard, put your PostHog project's `NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN` and `NEXT_PUBLIC_POSTHOG_HOST` there too, before you build. Without them nothing is recorded.

The app's other settings, and every setting named below, are in `backend/.env`:

| Setting | What to put |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `whileisleep.settings.production` |
| `COMPOSE_PROFILES` | `production` |
| `SITE_URL` | `https://` and your domain |
| `DJANGO_SECRET_KEY` | `openssl rand -base64 48` |
| `ENCRYPTION_KEYS` | `openssl rand -base64 32 \| tr '+/' '-_'` |
| `POSTGRES_PASSWORD` | `openssl rand -hex 24`, before the first start |

The `S3_*` and `STORAGE_*` settings are where uploaded files go: an S3-compatible bucket, such as Cloudflare R2 or Hetzner Object Storage. Leave them empty if you have none. Everything in that bucket is readable by anyone with the link, so use a different, private one for backups.

`ENCRYPTION_KEYS` encrypts the API keys you store in the dashboard (your AI provider keys, tool headers). **Keep a copy of it outside the server**: a database backup is unreadable without it.

To ask for Google's "I'm not a robot" box at log-in and sign-up, make a reCAPTCHA v2 checkbox key for your domain and set `RECAPTCHA_SITE_KEY` and `RECAPTCHA_SECRET_KEY`.

For "Continue with Google", make an OAuth client (web application) in Google Cloud with the redirect URI `https://YOUR_DOMAIN/api/v1/auth/google/callback`, and set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

For emails (a forgotten password), set `BREVO_API_KEY` and `MAIL_FROM`, an address that Brevo has verified as a sender.

## 3. Start it

The backend. Run this, and every `docker compose` command below, in `/opt/whileisleep/backend`:

```sh
cd /opt/whileisleep/backend
docker compose up -d --build
docker compose ps
```

`web` runs the database migrations, and the others start once it is healthy.

The frontend:

```sh
cd /opt/whileisleep/frontend
pnpm install --frozen-lockfile
pnpm build
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup
```

`pm2 startup` prints a command: run it once, so the frontend comes back after a reboot. pm2 restarts it when it crashes or uses more than 512 MB.

## 4. Connect the domain

In Cloudflare, create a tunnel and run its connector on the VM. Add three routes to it for your domain, in this order, because the first match wins:

| Path | Service |
|---|---|
| `^/api/v1/(widget/[^/]+\|workspaces/[0-9]+)/stream$` | `http://localhost:8104` |
| `^/(api\|admin\|static)/` | `http://localhost:8004` |
| *(empty)* | `http://localhost:3004` |

Turn on **Always Use HTTPS**. Keep `/widget.js` out of Cloudflare's cache with a cache rule, so a new version reaches your visitors quickly, and put no challenge on it or on `/api/`: that would break the chat on your site.

With another reverse proxy, send the same paths to the same ports, without buffering on the first, and have it set `Host`, `X-Forwarded-For` and `X-Forwarded-Proto`.

Open `https://YOUR_DOMAIN`, sign up (the first account owns its organization), then:

1. Add your AI provider's key and pick a model under **Settings › AI model**.
2. Copy the widget snippet from **Settings › Install** into your site.
3. Set `SIGNUP_ENABLED=false` in `backend/.env` and run `docker compose up -d` so nobody else can create accounts on your server.

## Slack (optional)

[Slack](slack.md#set-it-up-on-your-own-server) needs an app of your own and three settings. Webhooks need nothing.

## Selling plans (optional)

Skip this on your own server: without it nothing is limited. With it, the AI pauses 14 days after someone starts unless they subscribe, and **Billing** appears in the sidebar for the organization's owner.

1. Make an API key in Dodo Payments that can read and write products, checkouts, customers and subscriptions, and webhooks if you want them. They are optional: without them, a change made at Dodo (such as a refund) gets here within a day.
2. Make the two plans and the webhook, and print the settings (`PAYMENT_PROVIDER` stays empty until the end: the server refuses to start half-configured). Set `DODO_BASE_URL` (`https://live.dodopayments.com`) and `DODO_API_KEY` in `backend/.env`, then:

```sh
docker compose up -d
docker compose exec web python manage.py billing_setup            # shows what is missing
docker compose exec web python manage.py billing_setup --create   # makes it
```

3. Put the printed lines in `backend/.env`, set `PAYMENT_PROVIDER=dodo`, and run `docker compose up -d`.

Organizations that already exist get a full 14 days from that moment. Try it first with a test key and `https://test.dodopayments.com`.

## Editing the docs (optional)

Your server has its own copy of these docs at `/docs`. A superuser sees **Edit text** and **Add video** on every page:

```sh
docker compose exec web python manage.py make_superuser YOUR_EMAIL
```

A superuser can also open `/admin/`, so make only yourself one.

## Updating

```sh
cd /opt/whileisleep/backend && git pull
docker compose build
docker compose up -d --force-recreate web stream worker integrations beat
cd ../frontend && pnpm install --frozen-lockfile && pnpm build && pm2 reload ecosystem.config.cjs
```

Migrations run automatically before the new version starts. The backend's code is mounted into the containers, so run the commands together: a pull alone changes files under the running app. Postgres and Redis keep running. After a change to `frontend/.env`, run the last line again.

### From a version with the frontend in Docker

Move the settings of the old `.env` at the top of the repository: the ports (except `FRONTEND_PORT`) and `COMPOSE_PROFILES` to `backend/.env`, `FRONTEND_PORT` to `WEB_PORT` in `frontend/.env`, and the rest to `frontend/.env`. `POSTGRES_PORT` in `backend/.env` is now the port Docker opens. Delete the old file, pull, remove the old frontend and start as in step 3:

```sh
docker rm -f whileisleep-frontend-1
```

The database stays: the project is still called `whileisleep`. Never run `docker compose down -v`, which deletes it.

## Backups

Everything worth keeping is in Postgres. A nightly dump, kept for two weeks:

```sh
mkdir -p /var/backups/whileisleep
cat > /etc/cron.daily/whileisleep-backup <<'EOF'
#!/bin/sh
cd /opt/whileisleep/backend
docker compose exec -T db pg_dump -U whileisleep whileisleep | gzip > /var/backups/whileisleep/$(date +%F).sql.gz
find /var/backups/whileisleep -name '*.sql.gz' -mtime +14 -delete
EOF
chmod +x /etc/cron.daily/whileisleep-backup
```

Copy the dumps off the server too (to object storage, for example), and turn on your provider's VM backups for a second line of defence. To restore:

```sh
gunzip -c 2026-01-31.sql.gz | docker compose exec -T db psql -U whileisleep whileisleep
```

## Checking on it

```sh
docker compose logs -f web        # the API
docker compose logs -f worker     # AI replies: one "Task ... answer ... succeeded" per reply
pm2 logs whileisleep-frontend     # the dashboard
curl https://YOUR_DOMAIN/api/v1/ready
```

Check the file storage settings (writes a small file, opens its public address, deletes it):

```sh
docker compose exec web python manage.py check_storage
```

`/api/v1/ready` answers `{"ok": true}` when the API can reach the database and Redis.

### If chats only update every few seconds

The widget and the inbox get new messages, typing and the AI's status over a live stream (server-sent events) from the `stream` service. When it is down they fall back to polling, which still works, only more slowly. To check the stream itself (the visitor token comes from your browser's local storage, key `whileisleep:ws_...`):

```sh
docker compose ps stream
curl -N https://YOUR_DOMAIN/api/v1/widget/ws_YOUR_KEY/stream -H "X-Visitor-Token: vt_..."
```

`curl` should print `: connected` at once and `: ping` every 15 seconds. If it doesn't, check that the stream route is the first one on the tunnel. If the lines only show up in bursts, something in between buffers responses: turn off buffering for paths ending in `/stream` there.

Restarting `stream` drops open connections; browsers reconnect within seconds and catch up on anything they missed.

### If the AI stops answering

Replies are written by the `worker` service, not by the API, so the widget keeps accepting messages even when it is down. Check, in this order:

```sh
docker compose ps worker beat redis                      # all three should be "running"
docker compose logs --tail 50 worker                     # errors while writing a reply
docker compose exec redis redis-cli -n 1 llen celery     # replies waiting; should stay near 0
```

A number that keeps growing means replies arrive faster than they are written: raise `--concurrency` on the worker in `backend/docker-compose.yaml`, or run a second one with `docker compose up -d --scale worker=2`. Messages that were missed while the worker was down are picked up by themselves within a few minutes of it coming back (only those less than 30 minutes old: a late answer to an old question helps nobody).

## Settings reference

| Variable | Default | Meaning |
|---|---|---|
| `SIGNUP_ENABLED` | `true` | `false` closes account creation |
| `OUTBOUND_ALLOW_PRIVATE_NETWORKS` | `false` | Let AI tools call private addresses. Leave off unless your tools run on this server's own network |
| `TRUSTED_PROXY_COUNT` | `1` | Reverse proxies in front of Django. Raise it if there is another one behind the first, or rate limits will see the proxy's address instead of the visitor's |
| `LOG_LEVEL` | `INFO` | `DEBUG` for more detail |

To rotate `ENCRYPTION_KEYS`, put the new key first and keep the old one after a comma (`new,old`); new writes use the new key and old values stay readable.
