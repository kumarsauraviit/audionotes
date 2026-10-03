import type { NextConfig } from "next";

// The browser talks to this Vercel project and Vercel proxies /api/* to the
// backend server-side. This keeps the app working on networks that block the
// backend's own hostname (e.g. *.sslip.io) and removes CORS entirely.
//
// BACKEND_ORIGIN is a build-time env var set in the Vercel project (it is not
// exposed to the browser). Falls back to the local API for `next dev`.
const backendOrigin = (process.env.BACKEND_ORIGIN || "http://localhost:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backendOrigin}/api/:path*` },
      { source: "/health", destination: `${backendOrigin}/health` },
    ];
  },
};

export default nextConfig;
