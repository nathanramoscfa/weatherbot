// frontend/e2e/idle.spec.ts
import { mkdirSync, writeFileSync } from "node:fs";
import { expect, test } from "./guard.ts";

const SETTLE_MS = 30_000;
const WINDOW_MS = 600_000;
const WINDOW_SECONDS = WINDOW_MS / 1000;

test("measures idle tab TaskDuration over 600 seconds after 30 second settle @idle", async ({
  page,
  context,
}) => {
  test.setTimeout(720_000);

  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "simulated Miami-Dade" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Parliament Square" }),
  ).toBeVisible();

  await page.waitForTimeout(SETTLE_MS);

  const cdp = await context.newCDPSession(page);
  await cdp.send("Performance.enable");
  const startMetrics = await cdp.send("Performance.getMetrics");
  const taskDurationStart =
    startMetrics.metrics.find((metric) => metric.name === "TaskDuration")
      ?.value ?? 0;

  mkdirSync("test-results", { recursive: true });
  writeFileSync("test-results/idle-window-started.flag", "started\n", "utf8");

  await page.waitForTimeout(WINDOW_MS);

  const endMetrics = await cdp.send("Performance.getMetrics");
  const taskDurationEnd =
    endMetrics.metrics.find((metric) => metric.name === "TaskDuration")
      ?.value ?? 0;
  const taskDurationDelta = Math.max(0, taskDurationEnd - taskDurationStart);
  const tabCpuPercent = (taskDurationDelta / WINDOW_SECONDS) * 100;

  writeFileSync(
    "test-results/idle-metrics.json",
    `${JSON.stringify(
      {
        window_seconds: WINDOW_SECONDS,
        task_duration_start_seconds: taskDurationStart,
        task_duration_end_seconds: taskDurationEnd,
        task_duration_delta_seconds: taskDurationDelta,
        tab_cpu_percent: tabCpuPercent,
      },
      null,
      2,
    )}\n`,
    "utf8",
  );

  expect(tabCpuPercent).toBeLessThan(0.5);
});
