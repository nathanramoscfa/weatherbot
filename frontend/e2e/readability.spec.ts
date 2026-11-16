// frontend/e2e/readability.spec.ts
import type { Page } from "@playwright/test";
import { expect, test } from "./guard.ts";
import {
  auditReadability,
  formatFindings,
  type ReadabilityFinding,
} from "./readability.ts";

// The readability gate (Phase 8 Decision 6, docs/DESIGN.md): every route on the
// sparsest page (`quiet`) and the densest (`landfall`), at three widths in the
// light theme and at 1440x900 in the dark theme for contrast, with no finding.
// The scenario servers hold only the public landmarks and the synthetic storm,
// so the printed text samples carry nothing private.
const quietPort = Number(process.env.E2E_QUIET_PORT ?? "8802");
const landfallPort = Number(process.env.E2E_LANDFALL_PORT ?? "8806");

const SERVERS = [
  { name: "quiet", port: quietPort },
  { name: "landfall", port: landfallPort },
] as const;

type Theme = "light" | "dark";

interface Viewport {
  readonly width: number;
  readonly height: number;
}

const LIGHT_VIEWPORTS: readonly Viewport[] = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 360, height: 740 },
];
const DARK_VIEWPORT: Viewport = { width: 1440, height: 900 };

interface Render {
  readonly path: string;
  readonly ready: (page: Page) => Promise<void>;
}

async function heading(page: Page, name: string): Promise<void> {
  await expect(
    page.getByRole("heading", { name, exact: true }).first(),
  ).toBeVisible();
}

const RENDERS: readonly Render[] = [
  {
    path: "/",
    ready: async (page) => {
      await heading(page, "simulated Miami-Dade");
      await heading(page, "Parliament Square");
    },
  },
  {
    path: "/map",
    ready: async (page) => {
      await expect(page.getByTestId("leaflet-map-container")).toBeVisible();
      await expect(
        page.locator(".leaflet-overlay-pane svg path").first(),
      ).toBeVisible();
    },
  },
  {
    path: "/replay",
    ready: async (page) => {
      await expect(page.getByTestId("replay-banner")).toBeVisible({
        timeout: 30_000,
      });
      await expect(page.getByTestId("replay-leaflet-map")).toBeVisible();
    },
  },
  { path: "/storms", ready: (page) => heading(page, "Storms") },
  { path: "/alerts", ready: (page) => heading(page, "Alerts") },
  { path: "/timeline", ready: (page) => heading(page, "Timeline") },
  { path: "/ask", ready: (page) => heading(page, "Ask") },
  {
    path: "/settings",
    ready: async (page) => {
      await heading(page, "Watched Locations");
      await heading(page, "Database & Retention");
    },
  },
];

async function auditRoutes(
  page: Page,
  server: string,
  viewport: Viewport,
  theme: Theme,
): Promise<(ReadabilityFinding & { readonly render: string })[]> {
  await page.setViewportSize(viewport);
  await page.addInitScript((choice: Theme) => {
    try {
      window.localStorage.setItem("weatherbot.theme", choice);
    } catch {
      // Storage refused: theme-init.js then follows the system preference.
    }
  }, theme);

  const findings: (ReadabilityFinding & { readonly render: string })[] = [];
  for (const render of RENDERS) {
    await page.goto(render.path);
    await expect(page.locator("html")).toHaveClass(
      theme === "dark" ? /\bdark\b/ : /^(?!.*\bdark\b)/,
    );
    await render.ready(page);
    await expect(page.getByText(/^Loading\b/)).toHaveCount(0);
    const label = `${server} ${render.path} ${String(viewport.width)}x${String(viewport.height)} ${theme}`;
    for (const finding of await auditReadability(page)) {
      findings.push({ ...finding, render: label });
    }
  }
  return findings;
}

for (const server of SERVERS) {
  test.describe(`readability on the ${server.name} scenario`, () => {
    test.use({ baseURL: `http://127.0.0.1:${String(server.port)}` });

    const runs: readonly { readonly viewport: Viewport; readonly theme: Theme }[] = [
      ...LIGHT_VIEWPORTS.map((viewport) => ({ viewport, theme: "light" as const })),
      { viewport: DARK_VIEWPORT, theme: "dark" },
    ];

    for (const run of runs) {
      const size = `${String(run.viewport.width)}x${String(run.viewport.height)}`;
      test(`every route at ${size} in ${run.theme} has no readability finding`, async ({
        page,
      }) => {
        const findings = await auditRoutes(page, server.name, run.viewport, run.theme);
        if (findings.length > 0) {
          console.log(formatFindings(findings));
        }
        expect(findings, formatFindings(findings)).toEqual([]);
      });
    }
  });
}
