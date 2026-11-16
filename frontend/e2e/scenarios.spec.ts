// frontend/e2e/scenarios.spec.ts
import type { Page } from "@playwright/test";
import { expect, test } from "./guard.ts";

// The demonstration scenarios' own servers (scripts/demo_scenarios.py), which
// playwright.config.ts starts beside the default three: `quiet` (no storm, both
// landmarks at level 1) and `landfall` (Hurricane Demo, a synthetic storm, with
// the Miami-Dade landmark at level 5 and the Nassau one at level 4).
const quietPort = Number(process.env.E2E_QUIET_PORT ?? "8802");
const landfallPort = Number(process.env.E2E_LANDFALL_PORT ?? "8806");

const MIAMI = "simulated Miami-Dade";
const NASSAU = "Parliament Square";

// The guard fails foreign requests, page errors, CSP events, and leaked
// coordinates or AI text, but not console errors: this spec counts its own.
function consoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });
  return errors;
}

function locationCard(page: Page, name: string) {
  return page.locator("article", {
    has: page.getByRole("heading", { name }),
  });
}

test.describe("quiet scenario", () => {
  test.use({ baseURL: `http://127.0.0.1:${String(quietPort)}` });

  test("both landmarks read level 1 with no console error", async ({
    page,
  }) => {
    const errors = consoleErrors(page);
    await page.goto("/");

    await expect(page.getByRole("heading", { name: MIAMI })).toBeVisible();
    await expect(page.getByRole("heading", { name: NASSAU })).toBeVisible();
    await expect(locationCard(page, MIAMI)).toContainText("Level 1");
    await expect(locationCard(page, NASSAU)).toContainText("Level 1");
    await expect(page.locator("footer")).toContainText(
      "Informational only; never a substitute for official guidance.",
    );

    expect(errors).toEqual([]);
  });
});

test.describe("landfall scenario", () => {
  test.use({ baseURL: `http://127.0.0.1:${String(landfallPort)}` });

  test("Miami-Dade reads level 5 and Nassau level 4, and /map draws the storm's cone", async ({
    page,
  }) => {
    const errors = consoleErrors(page);
    await page.goto("/");

    await expect(page.getByRole("heading", { name: MIAMI })).toBeVisible();
    await expect(page.getByRole("heading", { name: NASSAU })).toBeVisible();
    const miami = locationCard(page, MIAMI);
    const nassau = locationCard(page, NASSAU);
    await expect(miami).toContainText("Level 5");
    await expect(miami).toContainText("Hurricane Warning");
    await expect(nassau).toContainText("Level 4");

    await page.goto("/map");
    const overlay = page.locator(".leaflet-overlay-pane svg");
    await expect(overlay).toBeVisible();
    const cone = overlay.locator('path[stroke="#1d4ed8"][fill="#93c5fd"]');
    await expect(cone.first()).toBeVisible();
    const markers = overlay.locator('path[d*="a8,8"]');
    await expect(markers).toHaveCount(2);

    expect(errors).toEqual([]);
  });
});
