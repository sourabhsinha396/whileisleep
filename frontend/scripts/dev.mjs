// Starts `next dev` on WEB_PORT from .env and rebuilds public/widget.js on change.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import * as esbuild from "esbuild";

if (existsSync(".env")) process.loadEnvFile(".env");
const port = process.env.WEB_PORT ?? "3004";

const widget = await esbuild.context({
  entryPoints: ["src/widget/index.ts"],
  bundle: true,
  format: "iife",
  target: "es2019",
  outfile: "public/widget.js",
  logLevel: "info",
});
await widget.watch();

const next = spawn("next", ["dev", "-p", port, ...process.argv.slice(2)], { stdio: "inherit", shell: true });
next.on("exit", async (code) => {
  await widget.dispose();
  process.exit(code ?? 0);
});
