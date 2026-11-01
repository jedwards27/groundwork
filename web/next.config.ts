import type { NextConfig } from "next";

// The repo's single .env is read by the server routes (lib/server.ts); nothing from it reaches the
// browser. Telemetry stays off.
process.env.NEXT_TELEMETRY_DISABLED = "1";

// Headers for every response. No framing (clickjacking on the approve button), no MIME sniffing,
// no referrer to other sites, no camera or microphone. HSTS only takes effect over HTTPS.
const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "same-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
];

const config: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default config;
