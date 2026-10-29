// frontend/playwright.config.ts
import { defineConfig } from "@playwright/test";

const port = Number(process.env.E2E_PORT ?? "8799");
const baseURL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${String(port)}`;
const isIdleRun = process.argv.some((arg) => arg.includes("@idle"));

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  grepInvert: isIdleRun ? undefined : /@idle/,
  reporter: [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    browserName: "chromium",
    headless: true,
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: `uv run python ../scripts/serve_demo.py --port ${String(port)} --roster-interval-minutes 1 --switch-file test-results/smoke-switch.flag`,
        url: `${baseURL}/api/health`,
        reuseExistingServer: false,
        timeout: 120_000,
      },
});
