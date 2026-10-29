// frontend/e2e/screens.spec.ts
import { mkdirSync } from "node:fs";
import { expect, test } from "./guard.ts";

const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 360, height: 740 },
] as const;

const THEMES = ["light", "dark"] as const;

test("captures dashboard and map screenshots at 1280x800 and 360x740 in light and dark themes", async ({
  page,
}) => {
  mkdirSync("test-results/screenshots", { recursive: true });

  for (const theme of THEMES) {
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize(viewport);
      await page.goto("/");
      await page.evaluate((choice) => {
        window.localStorage.setItem("weatherbot.theme", choice);
        document.documentElement.classList.toggle("dark", choice === "dark");
      }, theme);

      await expect(
        page.getByRole("heading", { name: "simulated Miami-Dade" }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "Parliament Square" }),
      ).toBeVisible();

      const sizeTag = `${String(viewport.width)}x${String(viewport.height)}`;
      await page.screenshot({
        path: `test-results/screenshots/dashboard-${sizeTag}-${theme}.png`,
        fullPage: true,
      });

      await page.goto("/map");
      await page.evaluate((choice) => {
        window.localStorage.setItem("weatherbot.theme", choice);
        document.documentElement.classList.toggle("dark", choice === "dark");
      }, theme);

      await expect(page.getByTestId("leaflet-map-container")).toBeVisible();
      await expect(
        page.locator(".leaflet-overlay-pane svg path").first(),
      ).toBeVisible();

      await page.screenshot({
        path: `test-results/screenshots/map-${sizeTag}-${theme}.png`,
        fullPage: true,
      });
    }
  }
});
