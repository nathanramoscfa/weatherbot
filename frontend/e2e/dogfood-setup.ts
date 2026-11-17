// frontend/e2e/dogfood-setup.ts
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";

// Global setup runs once, even if a failed test restarts the worker. Evidence
// is written only below Playwright's ignored results directory, never to Git.
export default function setup(): void {
  mkdirSync("test-results/dogfood", { recursive: true });
  const commit = execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim();
  writeFileSync("test-results/dogfood/audit.json", JSON.stringify({
    commit, started_at: new Date().toISOString(), expected_renders: 240, renders: [],
  }, null, 2) + "\n");
}
