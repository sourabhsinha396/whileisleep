# Deploy whileisleep on a VM (before your Maggi is ready 🍜)

One small virtual machine, from any provider, runs everything with Docker Compose: Caddy (HTTPS), the Django API, the
stream process that sends live updates to the widget and the inbox, a Celery worker that
writes the AI's replies, the Next.js dashboard, Postgres and Redis.

## What you need

- A VM with 2 vCPU, 4 GB RAM and **Ubuntu 24.04** is enough to start; the AI calls happen at your LLM provider, not on this machine.
- A domain or subdomain, for example `chat.example.com`.
- An API key from OpenAI, Anthropic, Google Gemini or OpenRouter (you enter it in the dashboard after the first login, not here).

## 1. Create the VM

In your provider's console:

1. Create the VM with your SSH key.
2. Add a **firewall** that allows inbound TCP 22 (SSH), TCP 80 and 443 (web) and UDP 443
   (HTTP/3), and nothing else. Postgres and Redis are never exposed.
3. Add a DNS **A record** for your domain pointing at the server's IPv4 address (and an
   AAAA record for its IPv6 address, if you use it). Caddy can only get a certificate once
   the name resolves to this server.

## 2. Install Docker

```sh
ssh root@YOUR_SERVER_IP
curl -fsSL https://get.docker.com | sh
```

## 3. Get the code and configure it

```sh
git clone https://github.com/YOUR_ACCOUNT/whileisleep.git /opt/whileisleep
cd /opt/whileisleep/deploy
cp .env.example .env
```

Edit `.env`:

| Setting | What to put |
|---|---|
| `SITE_DOMAIN` | Your domain, without `https://` |
| `DJANGO_SECRET_KEY` | `openssl rand -base64 48` |
| `POSTGRES_PASSWORD` | `openssl rand -hex 24` |
| `ENCRYPTION_KEYS` | `openssl rand -base64 32 \| tr '+/' '-_'` |

The `S3_*` and `STORAGE_*` settings are where uploaded files go: an S3-compatible bucket, such
as Cloudflare R2 or Hetzner Object Storage. Leave them empty if you have none. Everything in
that bucket is readable by anyone with the link, so use a different, private one for backups.

`ENCRYPTION_KEYS` encrypts the API keys you store in the dashboard (your AI provider keys,
tool headers). **Keep a copy of it outside the server**: a database backup is unreadable
without it.

## 4. Start it

```sh
docker compose up -d --build
docker compose ps
```

The `release` service runs the database migrations and exits; `web`, `stream`, `worker` and
`beat` start after it. The first HTTPS request takes a few seconds while Caddy obtains the
certificate.

Open `https://YOUR_DOMAIN`, sign up (the first account owns its organization), then:

1. Add your AI provider's key and pick a model under **Settings › AI model**.
2. Copy the widget snippet from **Settings › Install** into your site.
3. Set `SIGNUP_ENABLED=false` in `.env` and run `docker compose up -d` so nobody else can
   create accounts on your server.

## Selling plans (optional)

Skip this on your own server: without it nothing is limited. With it, the AI pauses 14 days after
someone starts unless they subscribe, and **Settings › Billing** appears for the organization's owner.

1. Make an API key in Dodo Payments that can read and write products, checkouts, customers,
   subscriptions and webhooks.
2. Make the two plans and the webhook, and print the settings (`PAYMENT_PROVIDER` stays empty until
   the end: the server refuses to start half-configured). Set `DODO_BASE_URL`
   (`https://live.dodopayments.com`) and `DODO_API_KEY` in `.env`, then:

```sh
docker compose up -d
docker compose exec web python manage.py billing_setup            # shows what is missing
docker compose exec web python manage.py billing_setup --create   # makes it
```

3. Put the three printed lines in `.env`, set `PAYMENT_PROVIDER=dodo`, and run `docker compose up -d`.

Organizations that already exist get a full 14 days from that moment. Try it first with a test key and
`https://test.dodopayments.com`.

## Updating

```sh
cd /opt/whileisleep && git pull
cd deploy && docker compose up -d --build
```

Migrations run automatically before the new version starts.

## Backups

Everything worth keeping is in Postgres. A nightly dump, kept for two weeks:

```sh
mkdir -p /var/backups/whileisleep
cat > /etc/cron.daily/whileisleep-backup <<'EOF'
#!/bin/sh
cd /opt/whileisleep/deploy
docker compose exec -T db pg_dump -U whileisleep whileisleep | gzip > /var/backups/whileisleep/$(date +%F).sql.gz
find /var/backups/whileisleep -name '*.sql.gz' -mtime +14 -delete
EOF
chmod +x /etc/cron.daily/whileisleep-backup
```

Copy the dumps off the server too (to object storage, for example), and turn on your
provider's VM backups for a second line of defence. To restore:

```sh
gunzip -c 2026-01-31.sql.gz | docker compose exec -T db psql -U whileisleep whileisleep
```

## Checking on it

```sh
docker compose logs -f web        # the API
docker compose logs -f worker     # AI replies: one "Task ... answer ... succeeded" per reply
docker compose logs -f caddy      # HTTPS and certificates
curl https://YOUR_DOMAIN/api/v1/ready
```

Check the file storage settings (writes a small file, opens its public address, deletes it):

```sh
docker compose exec web python manage.py check_storage
```

`/api/v1/ready` answers `{"ok": true}` when the API can reach the database and Redis.

### If chats only update every few seconds

The widget and the inbox get new messages, typing and the AI's status over a live stream
(server-sent events) from the `stream` service. When it is down they fall back to polling,
which still works, only more slowly. To check the stream itself (the visitor token comes
from your browser's local storage, key `whileisleep:ws_...`):

```sh
docker compose ps stream
curl -N https://YOUR_DOMAIN/api/v1/widget/ws_YOUR_KEY/stream -H "X-Visitor-Token: vt_..."
```

`curl` should print `: connected` at once and `: ping` every 15 seconds. If the lines only
show up in bursts, something between the browser and Caddy buffers responses: turn off
buffering for paths ending in `/stream` there. Caddy itself passes them on unbuffered and
uncompressed (see `Caddyfile`).

Restarting `stream` drops open connections; browsers reconnect within seconds and catch up
on anything they missed.

### If the AI stops answering

Replies are written by the `worker` service, not by the API, so the widget keeps accepting
messages even when it is down. Check, in this order:

```sh
docker compose ps worker beat redis                      # all three should be "running"
docker compose logs --tail 50 worker                     # errors while writing a reply
docker compose exec redis redis-cli -n 1 llen celery     # replies waiting; should stay near 0
```

A number that keeps growing means replies arrive faster than they are written: raise
`--concurrency` on the worker in `docker-compose.yml`, or run a second one with
`docker compose up -d --scale worker=2`. Messages that were missed while the worker was down
are picked up by themselves within a few minutes of it coming back (only those less than 30
minutes old: a late answer to an old question helps nobody).

## Settings reference

| Variable | Default | Meaning |
|---|---|---|
| `SIGNUP_ENABLED` | `true` | `false` closes account creation |
| `OUTBOUND_ALLOW_PRIVATE_NETWORKS` | `false` | Let AI tools call private addresses. Leave off unless your tools run on this server's own network |
| `TRUSTED_PROXY_COUNT` | `1` | Reverse proxies in front of Django. Raise it if you put a load balancer or CDN in front of Caddy, or rate limits will see the proxy's address instead of the visitor's |
| `LOG_LEVEL` | `INFO` | `DEBUG` for more detail |

To rotate `ENCRYPTION_KEYS`, put the new key first and keep the old one after a comma
(`new,old`); new writes use the new key and old values stay readable.
