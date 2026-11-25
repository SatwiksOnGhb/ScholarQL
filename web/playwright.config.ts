import { defineConfig, devices } from "@playwright/test";

// End-to-end smoke tests: real browser, real web app, real API (no mocks).
// Start the stack first (`docker compose up`), then: pnpm test:e2e
// Point at another deployment with E2E_BASE_URL, e.g. the Vercel URL.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      // E2E_CHROME_CHANNEL=chrome uses an installed Google Chrome instead of Playwright's
      use: { ...devices["Desktop Chrome"], channel: process.env.E2E_CHROME_CHANNEL },
    },
  ],
});
