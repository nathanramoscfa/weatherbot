// frontend/e2e/command-center.spec.ts
import type { Page } from "@playwright/test";
import { expect, test } from "./guard.ts";

const landfallPort = Number(process.env.E2E_LANDFALL_PORT ?? "8806");

const MIAMI = "simulated Miami-Dade";
const NASSAU = "Parliament Square";

function consoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });
  return errors;
}

test.describe("command-center dashboard on landfall scenario", () => {
  test.use({ baseURL: `http://127.0.0.1:${String(landfallPort)}` });

  test("fits the status bar on one line at 1440 px with a minute countdown, opens and closes the export popover on Escape returning focus, switches featured location with Back restoring the last, and draws the cone and both markers on the mini-map with zero console errors", async ({
    page,
  }) => {
    const errors = consoleErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");

    // 1. Status bar fits one line at 1440 px and countdown reads minutes
    const barRow = page.getByTestId("status-bar-row");
    await expect(barRow).toBeVisible();
    const snapshotStatus = page.getByTestId("status-bar-snapshot");
    const countdown = page.getByTestId("next-product-countdown");
    const exportButton = page.getByRole("button", { name: "Export report" });
    const checkNowButton = page.getByRole("button", { name: "Check now" });

    await expect(snapshotStatus).toBeVisible();
    await expect(countdown).toBeVisible();
    await expect(countdown).toContainText(/Next NHC product in \d+ min/);
    await expect(countdown).toHaveAttribute("title", /UTC$/);
    await expect(exportButton).toBeVisible();
    await expect(checkNowButton).toBeVisible();

    const rowBox = await barRow.boundingBox();
    const snapBox = await snapshotStatus.boundingBox();
    const countBox = await countdown.boundingBox();
    const exportBox = await exportButton.boundingBox();
    const checkBox = await checkNowButton.boundingBox();
    expect(rowBox).not.toBeNull();
    expect(snapBox).not.toBeNull();
    expect(countBox).not.toBeNull();
    expect(exportBox).not.toBeNull();
    expect(checkBox).not.toBeNull();
    if (rowBox && snapBox && countBox && exportBox && checkBox) {
      expect(rowBox.height).toBeLessThanOrEqual(56);
      const snapMidY = snapBox.y + snapBox.height / 2;
      const countMidY = countBox.y + countBox.height / 2;
      const exportMidY = exportBox.y + exportBox.height / 2;
      const checkMidY = checkBox.y + checkBox.height / 2;
      expect(Math.abs(snapMidY - checkMidY)).toBeLessThanOrEqual(8);
      expect(Math.abs(countMidY - checkMidY)).toBeLessThanOrEqual(8);
      expect(Math.abs(exportMidY - checkMidY)).toBeLessThanOrEqual(8);
    }

    // 2. Popover opens, closes on Escape, and returns focus to its button
    await exportButton.click();
    const exportAll = page.getByTestId("export-report-all");
    await expect(exportAll).toBeVisible();
    await expect(page.getByTestId(`export-report-${MIAMI}`)).toBeVisible();
    await expect(page.getByTestId(`export-report-${NASSAU}`)).toBeVisible();
    await expect(
      page.getByRole("checkbox", { name: /Include the AI briefing/i }),
    ).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(exportAll).toHaveCount(0);
    await expect(exportButton).toBeFocused();

    // 3. Switcher link features a location and Back restores the previous one
    const featured = page.getByTestId("featured-location");
    await expect(featured.getByTestId("location-hero-headline")).toHaveText(
      "Level 5 — Hurricane Warning",
    );
    await expect(
      featured.getByRole("region", { name: `AI briefing for ${MIAMI}` }),
    ).toBeVisible();

    const switcher = page.getByTestId("location-switcher");
    await switcher.getByRole("link", { name: NASSAU }).click();
    await expect(page).toHaveURL(/#location-parliament-square$/);
    await expect(featured.getByTestId("location-hero-headline")).toHaveText(
      "Level 4 — Warning / Watch / Evacuation",
    );
    await expect(
      featured.getByRole("region", { name: `AI briefing for ${NASSAU}` }),
    ).toBeVisible();

    await page.goBack();
    await expect(featured.getByTestId("location-hero-headline")).toHaveText(
      "Level 5 — Hurricane Warning",
    );
    await expect(
      featured.getByRole("region", { name: `AI briefing for ${MIAMI}` }),
    ).toBeVisible();

    // 4. Mini-map draws the storm's cone and both location markers
    const miniMap = page.getByTestId("mini-map-container");
    await expect(miniMap).toBeVisible();
    const overlay = miniMap.locator(".leaflet-overlay-pane svg");
    await expect(overlay).toBeVisible();
    const cone = overlay.locator('path[stroke="#1d4ed8"][fill="#93c5fd"]');
    await expect(cone.first()).toBeVisible();
    const markers = overlay.locator('path[d*="a8,8"]');
    await expect(markers).toHaveCount(2);

    expect(errors).toEqual([]);
  });
});
