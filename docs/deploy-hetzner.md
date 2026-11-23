# Deploying whileisleep on a Hetzner server

One small server runs everything with Docker Compose: Caddy (HTTPS), the Django API, the
Next.js dashboard, Postgres and Redis. The same steps work on any Linux host with Docker.

## What you need

- A Hetzner Cloud server. A **CX22** (2 vCPU, 4 GB RAM) with **Ubuntu 24.04** is enough to
  start; the AI calls happen at your LLM provider, not on this machine.
- A domain or subdomain, for example `chat.example.com`.
- An OpenRouter API key (you enter it in the dashboard after the first login, not here).

## 1. Create the server

In the Hetzner Cloud console:

1. Create the server with your SSH key.
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

`ENCRYPTION_KEYS` encrypts the API keys you store in the dashboard (your OpenRouter key,
tool headers). **Keep a copy of it outside the server**: a database backup is unreadable
without it.

## 4. Start it

```sh
docker compose up -d --build
docker compose ps
```

The `release` service runs the database migrations and exits; `web` starts after it. The
first HTTPS request takes a few seconds while Caddy obtains the certificate.

Open `https://YOUR_DOMAIN`, sign up (the first account owns its organization), then:

1. Set the OpenRouter key and model under **Organization & LLM**.
2. Copy the widget snippet from **Settings & widget** into your site.
3. Set `SIGNUP_ENABLED=false` in `.env` and run `docker compose up -d` so nobody else can
   create accounts on your server.

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

Copy the dumps off the server too (a Hetzner Storage Box works), and turn on Hetzner's
server backups for a second line of defence. To restore:

```sh
gunzip -c 2026-01-31.sql.gz | docker compose exec -T db psql -U whileisleep whileisleep
```

## Checking on it

```sh
docker compose logs -f web        # the API
docker compose logs -f caddy      # HTTPS and certificates
curl https://YOUR_DOMAIN/api/v1/ready
```

`/api/v1/ready` answers `{"ok": true}` when the API can reach the database and Redis.

## Settings reference

| Variable | Default | Meaning |
|---|---|---|
| `SIGNUP_ENABLED` | `true` | `false` closes account creation |
| `OUTBOUND_ALLOW_PRIVATE_NETWORKS` | `false` | Let AI tools call private addresses. Leave off unless your tools run on this server's own network |
| `TRUSTED_PROXY_COUNT` | `1` | Reverse proxies in front of Django. Raise it if you put a load balancer or CDN in front of Caddy, or rate limits will see the proxy's address instead of the visitor's |
| `LOG_LEVEL` | `INFO` | `DEBUG` for more detail |

To rotate `ENCRYPTION_KEYS`, put the new key first and keep the old one after a comma
(`new,old`); new writes use the new key and old values stay readable.
