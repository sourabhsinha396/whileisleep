import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8004";
// The live streams run on Django's ASGI process (the `stream` service in backend/docker-compose.yaml).
const STREAM_URL = process.env.STREAM_URL ?? "http://localhost:8009";

const nextConfig: NextConfig = {
  // A self-contained server in .next/standalone, for the Docker image.
  output: "standalone",
  // The dashboard and the widget call Django through this proxy, so one origin serves
  // both the widget script and its API.
  async rewrites() {
    // In production Caddy routes /api itself (deploy/Caddyfile); these serve development.
    return [
      { source: "/api/v1/widget/:key/stream", destination: `${STREAM_URL}/api/v1/widget/:key/stream` },
      { source: "/api/v1/workspaces/:id/stream", destination: `${STREAM_URL}/api/v1/workspaces/:id/stream` },
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
    ];
  },
  async headers() {
    // widget.js is loaded by other sites.
    return [{ source: "/widget.js", headers: [{ key: "Access-Control-Allow-Origin", value: "*" }] }];
  },
};

export default nextConfig;
