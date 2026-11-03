import { defineConfig } from "@playwright/test";

// The walkthrough drives the real stack: the API on :8000 (dev database, Lake Mariner fixture) and
// the web app on :3000, which forwards /api to it. It resets the demo before each test. Without
// E2E_BASE_URL, Playwright starts both servers if they are not already running (`make e2e`). With
// E2E_BASE_URL (the compose stack, the hosted rehearsal, or the plugin's own server), it tests
// whatever is there and starts nothing.
//
// Browser: the installed Google Chrome by default, so nothing is downloaded. Set PW_CHANNEL= (empty)
// to use Playwright's own Chromium after `npx playwright install chromium`.
const external = process.env.E2E_BASE_URL;
const channel = process.env.PW_CHANNEL ?? "chrome";

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: external ?? "http://localhost:3000",
    channel: channel || undefined,
    trace: "retain-on-failure",
  },
  webServer: external
    ? undefined
    : [
        {
          command: "uv run --directory ../backend groundwork serve --port 8000",
          url: "http://localhost:8000/health",
          reuseExistingServer: true,
          timeout: 60_000,
        },
        {
          command: "npm run dev",
          url: "http://localhost:3000",
          reuseExistingServer: true,
          timeout: 120_000,
        },
      ],
});
