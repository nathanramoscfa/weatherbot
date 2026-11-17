// frontend/e2e/map.spec.ts
import { expect, test } from "./guard.ts";

const landfallPort = Number(process.env.E2E_LANDFALL_PORT ?? "8806");

test.describe("immersive map on landfall scenario", () => {
  test.use({ baseURL: `http://127.0.0.1:${String(landfallPort)}` });

  test("fills at least 70% of the viewport, draws the live cone, track, forecast points, and both location markers, hides the cone when toggled off in the Layers panel, and shows no replay panel", async ({
    page,
  }) => {
    await page.goto("/map");

    const mapContainer = page.getByTestId("leaflet-map-container");
    await expect(mapContainer).toBeVisible();

    const viewport = page.viewportSize();
    const mapBox = await mapContainer.boundingBox();
    expect(viewport).not.toBeNull();
    expect(mapBox).not.toBeNull();
    if (viewport && mapBox) {
      expect(mapBox.height).toBeGreaterThanOrEqual(viewport.height * 0.7 - 1);
    }

    await expect(page.getByTestId("replay-panel")).toHaveCount(0);
    await expect(
      page.getByRole("link", { name: "Replay a past storm" }),
    ).toHaveAttribute("href", "/replay");

    const overlaySvg = page.locator(".leaflet-overlay-pane svg");
    await expect(overlaySvg).toBeVisible();

    const conePaths = overlaySvg.locator(
      'path[stroke="#1d4ed8"][fill="#93c5fd"]',
    );
    await expect(conePaths.first()).toBeVisible();

    const trackPaths = overlaySvg.locator(
      'path[stroke="#0f172a"][stroke-dasharray="6 4"]',
    );
    await expect(trackPaths.first()).toBeVisible();

    const pointPaths = overlaySvg.locator(
      'path[d*="a7,7"], path[d*="a6,6"], path[d*="a5,5"]',
    );
    expect(await pointPaths.count()).toBeGreaterThanOrEqual(5);

    const locationMarkerPaths = overlaySvg.locator('path[d*="a8,8"]');
    await expect(locationMarkerPaths).toHaveCount(2);

    // DF-07: each plotted point must remain in the exposed canvas, including
    // the current storm position near the right edge of the landfall track.
    const pointsClearOfHud = () => page.evaluate(() => {
      const points = document.querySelectorAll('.leaflet-overlay-pane path[d*="a7,7"], .leaflet-overlay-pane path[d*="a6,6"], .leaflet-overlay-pane path[d*="a5,5"], .leaflet-overlay-pane path[d*="a8,8"]');
      return points.length >= 7 && [...points].every((point) => {
        const box = point.getBoundingClientRect();
        const target = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
        return target?.closest(".leaflet-container") !== null && target !== null;
      });
    });
    await expect.poll(pointsClearOfHud).toBe(true);
    await page.getByRole("button", { name: "Fit", exact: true }).click();
    await expect.poll(pointsClearOfHud).toBe(true);

    const togglesRegion = page.getByRole("region", {
      name: "Map layer toggles",
    });
    const coneCheckbox = togglesRegion.getByRole("checkbox", {
      name: "Storm cones",
    });
    await expect(coneCheckbox).toBeChecked();
    await coneCheckbox.uncheck();
    await expect(conePaths).toHaveCount(0);

    await coneCheckbox.check();
    await expect(conePaths.first()).toBeVisible();
  });
});
