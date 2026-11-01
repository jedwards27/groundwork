import type { NextConfig } from "next";

// The repo's single .env is read by the server routes (lib/server.ts); nothing from it reaches the
// browser. Telemetry stays off.
process.env.NEXT_TELEMETRY_DISABLED = "1";

const config: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  poweredByHeader: false,
};

export default config;
