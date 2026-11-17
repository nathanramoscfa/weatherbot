// frontend/e2e/dogfood.spec.ts
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import type { Page } from "@playwright/test";
import { expect, recordAiText, test } from "./guard.ts";
import { auditReadability, formatFindings, type ReadabilityFinding } from "./readability.ts";

const SERVERS = [
  { name: "quiet", port: Number(process.env.E2E_QUIET_PORT ?? "8802") },
  { name: "outlook", port: Number(process.env.E2E_OUTLOOK_PORT ?? "8803") },
  { name: "cone", port: Number(process.env.E2E_CONE_PORT ?? "8804") },
  { name: "watch", port: Number(process.env.E2E_WATCH_PORT ?? "8805") },
  { name: "landfall", port: Number(process.env.E2E_LANDFALL_PORT ?? "8806") },
] as const;
const VIEWPORTS = [{ width: 1440, height: 900 }, { width: 390, height: 844 }] as const;
const THEMES = ["light", "dark"] as const;
const AUDIT_PATH = "test-results/dogfood/audit.json";

async function heading(page: Page, name: string): Promise<void> {
  await expect(page.getByRole("heading", { name, exact: true }).first()).toBeVisible();
}

const VIEWS = [
  { key: "dashboard", path: "/", ready: async (page: Page) => {
    await heading(page, "simulated Miami-Dade");
    await expect(page.getByTestId("location-hero-headline")).toBeVisible();
    await expect(page.getByTestId("dashboard-mini-map")).toBeVisible();
  } },
  { key: "map", path: "/map", ready: async (page: Page) => {
    await expect(page.getByTestId("map-status-chip")).toContainText("live");
    await expect(page.locator('.leaflet-overlay-pane svg path:not([d="M0 0"])').first()).toBeVisible();
  } },
  { key: "replay", path: "/replay", ready: async (page: Page) => {
    await page.getByLabel("Replay storm").selectOption("AL052019");
    await page.getByLabel("Replay location").selectOption("Parliament Square");
    await expect(page.getByTestId("replay-banner")).toContainText("Dorian", { timeout: 30_000 });
    await expect(page.getByTestId("location-hero-headline")).toBeVisible();
    await expect(page.getByTestId("replay-map-loading")).toHaveCount(0);
    await expect(page.locator(".leaflet-overlay-pane svg path").first()).toBeVisible();
  } },
  { key: "storms", path: "/storms", ready: (page: Page) => heading(page, "Storms") },
  { key: "alerts", path: "/alerts", ready: (page: Page) => heading(page, "Alerts") },
  { key: "timeline", path: "/timeline", ready: (page: Page) => heading(page, "Timeline") },
  { key: "ask", path: "/ask", ready: async (page: Page) => {
    await heading(page, "Ask");
    await expect(page.getByLabel("Your question")).toBeVisible();
  } },
  { key: "settings-locations", path: "/settings#locations", ready: async (page: Page) => {
    await heading(page, "Watched Locations");
    await expect(page.getByRole("button", { name: "Add location", exact: true })).toBeVisible();
  } },
  { key: "settings-notifications", path: "/settings#notifications", ready: (page: Page) => heading(page, "Quiet Hours & Cooldown") },
  { key: "settings-ai", path: "/settings#ai", ready: (page: Page) => heading(page, "AI") },
  { key: "settings-retention", path: "/settings#retention", ready: (page: Page) => heading(page, "Database & Retention") },
  { key: "settings-about", path: "/settings#about", ready: (page: Page) => heading(page, "Full Disclaimer") },
] as const;

interface RenderAudit {
  readonly key: string;
  readonly path: string;
  readonly screenshot: string;
  readonly findings: readonly ReadabilityFinding[];
}
interface RoundAudit {
  readonly commit: string;
  readonly started_at: string;
  readonly expected_renders: number;
  renders: RenderAudit[];
}

for (const server of SERVERS) {
  test.describe(`dogfood ${server.name}`, () => {
    test.use({ baseURL: `http://127.0.0.1:${String(server.port)}` });
    for (const viewport of VIEWPORTS) {
      for (const theme of THEMES) {
        const folder = `${server.name}-${String(viewport.width)}x${String(viewport.height)}-${theme}`;
        test(`@dogfood ${folder}: twelve views`, async ({ page }) => {
          test.setTimeout(360_000);
          await page.setViewportSize(viewport);
          await page.addInitScript((choice) => {
            window.localStorage.setItem("weatherbot.theme", choice);
          }, theme);
          const findings: (ReadabilityFinding & { render: string })[] = [];
          // Only the constant scenario/viewport/theme tuples above form this path.
          // eslint-disable-next-line security/detect-non-literal-fs-filename
          mkdirSync(`test-results/dogfood/${folder}`, { recursive: true });
          for (const view of VIEWS) {
            await page.goto(view.path);
            await view.ready(page);
            await expect(page.getByText(/^Loading\b/)).toHaveCount(0);
            await expect(page.locator("html")).toHaveClass(theme === "dark" ? /\bdark\b/ : /^(?!.*\bdark\b)/);
            await expect(page.locator("footer")).toContainText("Informational only");
            // Wait for async layout expansion before measuring the full page.
            await page.evaluate(async () => {
              await document.fonts.ready;
              await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
            });
            for (const text of await page.locator('[aria-label^="AI briefing"] p').allTextContents()) {
              recordAiText(page, text);
            }
            const key = `${folder}/${view.key}`;
            const screenshot = `test-results/dogfood/${key}.png`;
            await page.screenshot({ path: screenshot, fullPage: true, animations: "disabled" });
            expect(await page.evaluate(() => window.__wbCspViolations ?? []), key).toEqual([]);
            const audit = await auditReadability(page);
            findings.push(...audit.map((finding) => ({ ...finding, render: key })));
            // workers: 1; each synchronous read/append/write completes before
            // another view starts. Empty findings still get a manifest entry.
            const round = JSON.parse(readFileSync(AUDIT_PATH, "utf8")) as RoundAudit;
            round.renders.push({ key, path: view.path, screenshot, findings: audit });
            writeFileSync(AUDIT_PATH, JSON.stringify(round, null, 2) + "\n");
          }
          expect(findings, formatFindings(findings)).toEqual([]);
        });
      }
    }
  });
}
