import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// In development Vite serves the app on :3000 and forwards the API (and the plugin's /p/<token>
// hand-off) to it, so the browser sees one origin, as it does when the API serves the built app.
// The Host header passes through unchanged: the API checks that a state change's Origin matches it.
const api = process.env.GROUNDWORK_API_URL ?? "http://localhost:8000";
const forward = { target: api, changeOrigin: false };

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  server: { proxy: { "/api": forward, "/p/": forward, "/health": forward } },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1500 },
});
