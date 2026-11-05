// frontend/e2e/layers.spec.ts
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { expect, leaksCoordinate, test } from "./guard.ts";

test("map layers stay silent until toggled, render depth and probability overlays, fetch nowCOAST tiles only on toggle, and step stored advisories", async ({
  page,
}) => {
  const nowcoastRequests: string[] = [];
  page.on("request", (req) => {
    const url = req.url();
    if (url.startsWith("https://nowcoast.noaa.gov/")) {
      nowcoastRequests.push(url);
    }
  });

  mkdirSync("test-results", { recursive: true });
  writeFileSync("test-results/smoke-switch.flag", "switched\n", "utf8");
  try {
    await page.goto("/");
    await page.getByRole("button", { name: "Check now" }).click();

    const miamiCard = page.locator("article", {
      has: page.getByRole("heading", { name: "simulated Miami-Dade" }),
    });
    await expect(miamiCard).toContainText("Level 5", {
      timeout: 90_000,
    });

    await page.goto("/map");
    await expect(page.getByTestId("leaflet-map-container")).toBeVisible();

    // Before any overlay toggle is enabled, zero requests have been made to nowCOAST.
    expect(nowcoastRequests).toEqual([]);

    const togglesSection = page.getByRole("region", {
      name: "Map layer toggles",
    });

    const windRadiiCheckbox = togglesSection.getByLabel(/^Wind radii/);
    const pastTrackCheckbox = togglesSection.getByLabel(/^Past track/);
    const peakSurgeCheckbox = togglesSection.getByLabel(/^Peak surge/);
    const windProbCheckbox = togglesSection.getByLabel(/^Wind probabilities/);
    const radarCheckbox = togglesSection.getByLabel(/^Radar \(nowCOAST\)/);
    const satelliteCheckbox = togglesSection.getByLabel(
      /^Satellite IR \(nowCOAST\)/,
    );

    await expect(windRadiiCheckbox).not.toBeChecked();
    await expect(pastTrackCheckbox).not.toBeChecked();
    await expect(peakSurgeCheckbox).not.toBeChecked();
    await expect(windProbCheckbox).not.toBeChecked();
    await expect(radarCheckbox).not.toBeChecked();
    await expect(satelliteCheckbox).not.toBeChecked();

    // Enable vector depth layers (wind radii, past track, peak surge).
    await windRadiiCheckbox.check();
    await pastTrackCheckbox.check();
    await peakSurgeCheckbox.check();

    const overlaySvg = page.locator(".leaflet-overlay-pane svg");
    await expect(overlaySvg).toBeVisible();
    // Synthetic peak surge feature "Tampa Bay...8-12 ft" renders with #ef4444 fill.
    await expect(
      overlaySvg.locator('path[fill="#ef4444"]').first(),
    ).toBeVisible();

    // Enable wind speed probabilities (canvas layer).
    await windProbCheckbox.check();
    await expect(page.getByTestId("wind-probability-controls")).toBeVisible();
    await expect(
      page.getByText("Chance of winds at this speed within 120 hours"),
    ).toBeVisible();
    await expect(
      page.locator(".leaflet-overlay-pane canvas").first(),
    ).toBeVisible();

    // Still zero requests to nowCOAST before radar/satellite are toggled on.
    expect(nowcoastRequests).toEqual([]);

    // Enable radar and satellite WMS overlays.
    await radarCheckbox.check();
    await satelliteCheckbox.check();
    await expect(page.getByTestId("nowcoast-age-note")).toBeVisible();

    await expect.poll(() => nowcoastRequests.length).toBeGreaterThanOrEqual(1);
    expect(nowcoastRequests.some((url) => leaksCoordinate(url))).toBe(false);

    // Step the advisory history slider back to the previous stored advisory.
    const sliderPanel = page.getByTestId("advisory-slider-panel");
    await expect(sliderPanel).toBeVisible();
    const slider = sliderPanel.locator("#advisory-history-slider");
    await slider.focus();
    await slider.press("ArrowLeft");

    const storedBanner = page.getByTestId("stored-advisory-banner");
    await expect(storedBanner).toBeVisible();
    await expect(storedBanner).toContainText("Stored advisory:");
    await expect(storedBanner).toContainText("not the latest");
    await expect(togglesSection).toContainText("(live only)");

    await sliderPanel.getByRole("button", { name: "Back to latest" }).click();
    await expect(storedBanner).toHaveCount(0);
  } finally {
    rmSync("test-results/smoke-switch.flag", { force: true });
  }
});
