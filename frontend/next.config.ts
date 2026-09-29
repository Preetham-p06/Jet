import type { NextConfig } from "next";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Proxy the FastAPI backend so the browser sees `/api/*` (and the
  // `js_session` cookie) as first-party. No CORS needed.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
  experimental: {
    // Undocumented but typed + schema-validated in next@16.3.5
    // (config-shared.d.ts, router-utils/proxy-request.js; default 30 s).
    // Extraction with Claude can run long; give rewrites 120 s.
    proxyTimeout: 120_000,
  },
};

export default nextConfig;
