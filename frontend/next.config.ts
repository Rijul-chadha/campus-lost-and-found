import type { NextConfig } from "next";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // Same-origin proxy: the browser only ever talks to this app, so the session cookie is
  // first-party, httpOnly and SameSite=Lax, and no CORS is needed for API calls.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(self), geolocation=()" },
        ],
      },
    ];
  },
  images: { unoptimized: true },
};

export default config;
