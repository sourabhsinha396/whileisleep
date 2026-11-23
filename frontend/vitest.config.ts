import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// All frontend tests live in tests/. DOM tests run in happy-dom.
export default defineConfig({
  esbuild: { jsx: "automatic" },
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: { include: ["tests/**/*.test.{ts,tsx}"], environment: "happy-dom" },
});
