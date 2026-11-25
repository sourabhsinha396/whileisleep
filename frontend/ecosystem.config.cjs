/* eslint-disable @typescript-eslint/no-require-imports -- pm2 loads this file as CommonJS */
// Production: `pm2 start ecosystem.config.cjs`, after `pnpm build`.
const { existsSync, readFileSync } = require("node:fs");
const path = require("node:path");
const { parseEnv } = require("node:util");

// Only the port is taken from here: Next reads .env itself, at every start.
const file = path.join(__dirname, ".env");
const env = existsSync(file) ? parseEnv(readFileSync(file, "utf8")) : {};

module.exports = {
  apps: [
    {
      name: "whileisleep-frontend",
      cwd: __dirname,
      // Not through pnpm, so that pm2 stops and measures the server itself.
      script: "node_modules/next/dist/bin/next",
      // Localhost only; the tunnel or reverse proxy reaches it.
      args: ["start", "-H", "127.0.0.1", "-p", env.WEB_PORT || "3004"],
      env: { NODE_ENV: "production", NEXT_TELEMETRY_DISABLED: "1" },
      max_memory_restart: "512M",
      // Waits longer after each crash in a row.
      exp_backoff_restart_delay: 200,
    },
  ],
};
