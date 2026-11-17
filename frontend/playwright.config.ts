// frontend/playwright.config.ts
import { defineConfig } from "@playwright/test";

const port = Number(process.env.E2E_PORT ?? "8799");
const baseURL = process.env.E2E_BASE_URL ?? `http://127.0.0.1:${String(port)}`;
const isIdleRun = process.argv.some((arg) => arg.includes("@idle"));
const isDogfoodRun = process.argv.some((arg) => arg.includes("@dogfood"));

// The AI smoke's other two demonstration servers (frontend/e2e/ai.spec.ts):
// one whose tiny cap reads "capped", one whose every AI answer is a 401.
// Each serve_demo.py process keeps its own temporary directory.
const capPort = Number(process.env.E2E_AI_CAP_PORT ?? "8800");
const authPort = Number(process.env.E2E_AI_AUTH_PORT ?? "8801");

// The demonstration scenarios' servers (scripts/demo_scenarios.py,
// frontend/e2e/scenarios.spec.ts): the sparsest page and the densest. Ports
// 8803 to 8805 belong to the outlook, cone, and watch scenarios, which the
// dogfood harness starts; the default run does not.
const quietPort = Number(process.env.E2E_QUIET_PORT ?? "8802");
const landfallPort = Number(process.env.E2E_LANDFALL_PORT ?? "8806");

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
  grepInvert: isIdleRun || isDogfoodRun ? undefined : /@idle|@dogfood/,
  globalSetup: isDogfoodRun ? "./e2e/dogfood-setup.ts" : undefined,
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
        demoServer(quietPort, "--scenario quiet"),
        demoServer(landfallPort, "--scenario landfall"),
        ...(isDogfoodRun
          ? [
              demoServer(Number(process.env.E2E_OUTLOOK_PORT ?? "8803"), "--scenario outlook"),
              demoServer(Number(process.env.E2E_CONE_PORT ?? "8804"), "--scenario cone"),
              demoServer(Number(process.env.E2E_WATCH_PORT ?? "8805"), "--scenario watch"),
            ]
          : []),
      ],
});
