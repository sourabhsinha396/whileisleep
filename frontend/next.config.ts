import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8004";
// The live streams run on Django's ASGI process (the `stream` service in docker-compose.yaml).
const STREAM_URL = process.env.STREAM_URL ?? "http://localhost:8009";

const nextConfig: NextConfig = {
  // A self-contained server in .next/standalone, for the Docker image.
  output: "standalone",
  // The docs read their pages while the server runs.
  outputFileTracingIncludes: { "/docs": ["./content/docs/*.md"], "/docs/**": ["./content/docs/*.md"], "/llms*": ["./content/docs/*.md"] },
  // The dashboard and the widget call Django through this proxy, so one origin serves
  // both the widget script and its API.
  async rewrites() {
    // In production the proxy routes /api itself; these serve development.
    return [
      { source: "/api/v1/widget/:key/stream", destination: `${STREAM_URL}/api/v1/widget/:key/stream` },
      { source: "/api/v1/workspaces/:id/stream", destination: `${STREAM_URL}/api/v1/workspaces/:id/stream` },
      // A page of the docs as Markdown, for language models.
      { source: "/docs/:page([a-z0-9-]+).md", destination: "/docs/:page/markdown" },
      { source: "/api/:path*", destination: `${API_URL}/api/:path*` },
    ];
  },
  // Areas open on their first page, and links from before the settings were grouped still work.
  async redirects() {
    return [
      { source: "/w/:slug/ai", destination: "/w/:slug/ai/behavior", permanent: false },
      { source: "/w/:slug/settings", destination: "/w/:slug/settings/general", permanent: false },
      { source: "/w/:slug/automation", destination: "/w/:slug/ai/rules", permanent: false },
      { source: "/w/:slug/organization", destination: "/w/:slug/settings/ai-model", permanent: false },
      { source: "/w/:slug/settings/billing", destination: "/w/:slug/billing", permanent: false },
    ];
  },
  async headers() {
    // widget.js is loaded by other sites. Cached briefly, so a new release reaches them in minutes.
    const widget = {
      source: "/widget.js",
      headers: [
        { key: "Access-Control-Allow-Origin", value: "*" },
        { key: "Cache-Control", value: "public, max-age=300" },
      ],
    };
    // The dashboard and the test page are nothing to find in a search engine.
    const noindex = [{ key: "X-Robots-Tag", value: "noindex, nofollow" }];
    return [widget, ...["/w/:path*", "/app", "/new", "/demo", "/integrations/:path*"].map((source) => ({ source, headers: noindex }))];
  },
};

export default nextConfig;
