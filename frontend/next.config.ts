import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8004";

const nextConfig: NextConfig = {
  // The dashboard and the widget call Django through this proxy, so one origin serves
  // both the widget script and its API.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  async headers() {
    // widget.js is loaded by other sites.
    return [{ source: "/widget.js", headers: [{ key: "Access-Control-Allow-Origin", value: "*" }] }];
  },
};

export default nextConfig;
