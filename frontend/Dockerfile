# The dashboard and the widget script, as a small Next.js standalone server.

FROM node:22-slim AS build
ENV PNPM_HOME=/pnpm PATH="/pnpm:$PATH" NEXT_TELEMETRY_DISABLED=1
RUN corepack enable
WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
# Read while building: they become part of the pages. Empty: no session replays.
ARG NEXT_PUBLIC_POSTHOG_PROJECT_TOKEN=
ARG NEXT_PUBLIC_POSTHOG_HOST=
# Builds public/widget.js, then the app. In production the reverse proxy sends /api to
# Django itself, so the dev-only API_URL rewrite needs no real address here.
RUN pnpm build


FROM node:22-slim
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app

# The standalone output carries only the files and packages the server needs.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

USER node
EXPOSE 3000
CMD ["node", "server.js"]
