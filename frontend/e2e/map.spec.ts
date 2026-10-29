// frontend/e2e/map.spec.ts
import { expect, test } from "./guard.ts";

test("map replay loads Irma AL112017 mid-storm advisory with cone, track, points, and both location markers under not-live banner", async ({
  page,
}) => {
  await page.goto("/map");

  const stormSelect = page.locator("#replay-storm-select");
  await expect(stormSelect).toBeVisible();
  await stormSelect.selectOption("AL112017");

  const advisorySelect = page.locator("#replay-advisory-select");
  await expect(advisorySelect).toBeEnabled();
  await advisorySelect.selectOption("031");

  const banner = page.getByTestId("replay-not-live-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("not live");
  await expect(banner).toContainText("Irma");
  await expect(banner).toContainText("advisory 031");

  const overlaySvg = page.locator(".leaflet-overlay-pane svg");
  await expect(overlaySvg).toBeVisible();

  const conePaths = overlaySvg.locator('path[stroke="#1d4ed8"][fill="#93c5fd"]');
  await expect(conePaths.first()).toBeVisible();

  const trackPaths = overlaySvg.locator('path[stroke="#0f172a"][stroke-dasharray="6 4"]');
  await expect(trackPaths.first()).toBeVisible();

  const pointPaths = overlaySvg.locator('path[d*="a7,7"], path[d*="a6,6"], path[d*="a5,5"]');
  expect(await pointPaths.count()).toBeGreaterThanOrEqual(5);

  const locationMarkerPaths = overlaySvg.locator('path[d*="a8,8"]');
  await expect(locationMarkerPaths).toHaveCount(2);
});
