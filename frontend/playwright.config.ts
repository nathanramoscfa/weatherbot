// frontend/playwright.config.ts
import { defineConfig } from "@playwright/test";

const port = Number(process.env.E2E_PORT ?? "8799");
const baseURL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${String(port)}`;
const isIdleRun = process.argv.some((arg) => arg.includes("@idle"));

// The AI smoke's other two demonstration servers (frontend/e2e/ai.spec.ts):
// one whose tiny cap reads "capped", one whose every AI answer is a 401.
// Each serve_demo.py process keeps its own temporary directory.
const capPort = Number(process.env.E2E_AI_CAP_PORT ?? "8800");
const authPort = Number(process.env.E2E_AI_AUTH_PORT ?? "8801");

function demoServer(serverPort: number, options: string) {
  return {
    command: `uv run python ../scripts/serve_demo.py --port ${String(serverPort)} ${options}`,
    url: `http://127.0.0.1:${String(serverPort)}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
  };
}

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
    : [
        demoServer(
          port,
          "--roster-interval-minutes 1 --switch-file test-results/smoke-switch.flag",
        ),
        demoServer(capPort, "--ai-cap-usd 0.001"),
        demoServer(authPort, "--ai-fail-auth"),
      ],
});
