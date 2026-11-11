// frontend/e2e/phase7.spec.ts
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { expect, test } from "./guard.ts";

const SWITCH_FILE_PATH = "test-results/smoke-switch.flag";
const ADDED_LOCATION_NAME = "Nassau Harbour";

interface TimelineStep {
  readonly advisory_id: string;
  readonly advisory: string;
}

interface TimelineDoc {
  readonly steps: readonly TimelineStep[];
}

function removeSwitchFile(): void {
  rmSync(SWITCH_FILE_PATH, { force: true });
}

test.describe("Phase 7 end-to-end smoke", () => {
  test.afterEach(async ({ page }, testInfo) => {
    if (testInfo.status !== testInfo.expectedStatus) {
      mkdirSync("test-results", { recursive: true });
      await page.screenshot({
        path: `test-results/phase7-failure-${String(Date.now())}.png`,
        fullPage: true,
      });
    }
  });

  test("searches and adds Nassau, configures channels/quiet-hours/retention, toggles map layers and radar failure, steps advisory slider, reads sparkline and wind chart, scrubs Dorian replay to Level 5, and exports report", async ({
    page,
  }) => {
    try {
      // 1. Search for "Nassau, Bahamas" on /settings, add it, and see its card read as outside NWS coverage
      await page.goto("/settings");
      await expect(
        page.getByRole("heading", { name: "Watched Locations" }),
      ).toBeVisible();

      await page.getByLabel("Place search").pressSequentially("Nassau, Bahamas");
      const searchButton = page.getByRole("button", { name: "Search" });
      const candidateRadio = page
        .getByRole("radio", { name: /Nassau/i })
        .first();
      await expect
        .poll(
          async () => {
            if (await candidateRadio.isVisible()) {
              return true;
            }
            await searchButton.click();
            return await candidateRadio.isVisible();
          },
          { timeout: 20_000, intervals: [500, 1500, 2000] },
        )
        .toBe(true);
      await candidateRadio.check();

      await page.getByLabel("Location name").fill(ADDED_LOCATION_NAME);
      await page.getByRole("button", { name: "Add location" }).click();

      const addedSettingsCard = page.getByRole("article", {
        name: ADDED_LOCATION_NAME,
      });
      await expect(addedSettingsCard).toBeVisible();
      await expect(addedSettingsCard).toContainText(
        "Outside NWS coverage: NHC breakpoints",
      );

      // 2. Open/inspect the channel view on /settings
      await expect(
        page.getByRole("heading", { name: "Notification Channels" }),
      ).toBeVisible();
      await expect(page.getByTestId("channel-card-log")).toBeVisible();
      await expect(page.getByTestId("channel-card-toast")).toBeVisible();
      await expect(page.getByTestId("channel-card-browser")).toBeVisible();
      await expect(page.getByTestId("channel-card-ntfy")).toBeVisible();

      // 3. Save quiet hours and read the retention plan on /settings
      await page.getByLabel("Quiet hours start (HH:MM)").fill("22:00");
      await page.getByLabel("Quiet hours end (HH:MM)").fill("07:00");
      await page
        .getByLabel("Quiet hours time zone (IANA)")
        .fill("America/New_York");
      await page.getByRole("button", { name: "Save quiet hours" }).click();
      await expect(
        page.getByText(/Saved .* to weatherbot\.toml/i),
      ).toBeVisible();

      await expect(
        page.getByRole("heading", { name: "Database & Retention" }),
      ).toBeVisible();
      await expect(page.getByText(/Plan for/)).toBeVisible();
      await expect(page.getByText(/Protected by keep-list:/)).toBeVisible();

      // 4. Visit Dashboard (/): see the added Nassau Harbour card read as outside NWS coverage,
      //    ensure at least 2 stored advisories exist, and read the sparkline
      await page.goto("/");
      const nassauDashboardCard = page.getByRole("article", {
        name: ADDED_LOCATION_NAME,
      });
      await expect(nassauDashboardCard).toBeVisible();
      await expect(nassauDashboardCard).toContainText("Outside NWS coverage");

      const advRes = await page.request.get("/api/map/advisories");
      const advData = (await advRes.json()) as {
        steps: Array<{ advisory: string }>;
      };
      if (advData.steps.length < 2) {
        mkdirSync("test-results", { recursive: true });
        writeFileSync(SWITCH_FILE_PATH, "switched\n", "utf8");
        await page.getByRole("button", { name: "Check now" }).click();
        const miamiCard = page.locator("article", {
          has: page.getByRole("heading", { name: "simulated Miami-Dade" }),
        });
        await expect(miamiCard).toContainText("Level 5", {
          timeout: 90_000,
        });
      }

      const sparklines = page.getByTestId("level-sparkline");
      await expect(sparklines.first()).toBeVisible();

      // Remove the temporary Nassau Harbour location so later specs see the default two landmarks
      await page.goto("/settings");
      const cardToRemove = page.getByRole("article", {
        name: ADDED_LOCATION_NAME,
      });
      await cardToRemove.getByRole("button", { name: "Remove" }).click();
      const dialog = page.getByRole("alertdialog", {
        name: `Remove ${ADDED_LOCATION_NAME}?`,
      });
      await expect(dialog).toBeVisible();
      await dialog.getByRole("button", { name: "Remove location" }).click();
      await expect(cardToRemove).toHaveCount(0);

      // 5. Turn on every map layer in turn with nowcoast.noaa.gov fulfilled by the blank tile,
      //    see "Radar unavailable" with that route aborted, and step the advisory slider
      await page.goto("/map");
      await expect(page.getByTestId("leaflet-map-container")).toBeVisible();

      const togglesSection = page.getByRole("region", {
        name: "Map layer toggles",
      });
      const layerPatterns = [
        /^Wind radii/,
        /^Past track/,
        /^Peak surge/,
        /^Wind probabilities/,
        /^Radar \(nowCOAST\)/,
        /^Satellite IR \(nowCOAST\)/,
      ];
      for (const pattern of layerPatterns) {
        const checkbox = togglesSection.getByLabel(pattern);
        await checkbox.check();
        await expect(checkbox).toBeChecked();
      }
      await expect(
        page.getByTestId("wind-probability-controls"),
      ).toBeVisible();
      await expect(page.getByTestId("radar-unavailable-banner")).toHaveCount(0);

      const sliderPanel = page.getByTestId("advisory-slider-panel");
      await expect(sliderPanel).toBeVisible();
      const slider = sliderPanel.locator("#advisory-history-slider");
      await expect(slider).toBeEnabled();
      await slider.focus();
      await slider.press("ArrowLeft");

      const storedBanner = page.getByTestId("stored-advisory-banner");
      await expect(storedBanner).toBeVisible();
      await sliderPanel
        .getByRole("button", { name: "Back to latest" })
        .click();
      await expect(storedBanner).toHaveCount(0);

      await page.route("https://nowcoast.noaa.gov/**", async (route) => {
        await route.abort();
      });
      await page.goto("/map");
      await expect(page.getByTestId("leaflet-map-container")).toBeVisible();
      await page
        .getByRole("region", { name: "Map layer toggles" })
        .getByLabel(/^Radar \(nowCOAST\)/)
        .check();
      const radarBanner = page.getByTestId("radar-unavailable-banner");
      await expect(radarBanner).toBeVisible();
      await expect(radarBanner).toContainText("Radar unavailable");
      await page.unroute("https://nowcoast.noaa.gov/**");

      // 6. Read the wind chart on /timeline
      await page.goto("/timeline");
      await page
        .getByLabel("Filter by location")
        .selectOption("simulated Miami-Dade");
      const windChart = page.getByTestId("wind-probability-chart");
      await expect(windChart).toBeVisible();

      // 7. Scrub Dorian at Parliament Square on /replay to advisory 26 and see Level 5 (hurricane_warning, HWR)
      await page.goto("/replay");
      await expect(
        page.getByRole("heading", { name: "Replay", exact: true }),
      ).toBeVisible();
      await page.getByLabel("Replay storm").selectOption("AL052019");
      await page
        .getByLabel("Replay location")
        .selectOption("Parliament Square");

      const replayBanner = page.getByTestId("replay-banner");
      await expect(replayBanner).toBeVisible({ timeout: 30_000 });

      const timelineRes = await page.request.get(
        "/api/replay/AL052019/timeline?location=Parliament%20Square",
      );
      expect(timelineRes.ok()).toBe(true);
      const timelineDoc = (await timelineRes.json()) as TimelineDoc;
      const idx026 = timelineDoc.steps.findIndex(
        (s) => s.advisory_id === "026",
      );
      expect(idx026).toBeGreaterThan(0);

      const replaySlider = page.getByRole("slider", {
        name: /Advisory history/i,
      });
      await replaySlider.fill(String(idx026));
      await replaySlider.dispatchEvent("mouseup");

      await expect(replayBanner).toContainText(
        "Replay: Dorian advisory 26, issued",
      );
      const assessmentCard = page.getByTestId("replay-assessment-card");
      await expect(assessmentCard).toContainText("Level 5");
      await expect(assessmentCard).toContainText("hurricane_warning");
      await expect(assessmentCard).toContainText("HWR");

      const replayMap = page.getByTestId("replay-leaflet-map");
      await expect(replayMap).toBeVisible();
      await expect
        .poll(async () => replayMap.locator(".leaflet-tile").count())
        .toBeGreaterThan(1);
      const overlaySvg = replayMap.locator(".leaflet-overlay-pane svg").first();
      await expect(overlaySvg).toBeVisible();
      expect(Number(await overlaySvg.getAttribute("width"))).toBeGreaterThan(
        100,
      );
      expect(Number(await overlaySvg.getAttribute("height"))).toBeGreaterThan(
        100,
      );

      // 8. Export the report on /
      await page.goto("/");
      const exportAll = page.getByTestId("export-report-all");
      await expect(exportAll).toBeVisible();
      mkdirSync("test-results", { recursive: true });
      const downloadPromise = page.waitForEvent("download");
      await exportAll.click();
      const download = await downloadPromise;
      const savedPath = "test-results/phase7-smoke-report.html";
      await download.saveAs(savedPath);
      const reportHtml = readFileSync(savedPath, "utf8");
      expect(reportHtml.startsWith("<!doctype html>")).toBe(true);
      expect(reportHtml).toContain("Weatherbot is informational only.");
    } finally {
      removeSwitchFile();
      await page.unroute("https://nowcoast.noaa.gov/**").catch(() => undefined);
      await page.request
        .post("/api/locations/remove", {
          data: { location: ADDED_LOCATION_NAME },
        })
        .catch(() => undefined);
      const settingsRes = await page.request
        .get("/api/settings")
        .catch(() => null);
      if (settingsRes?.ok()) {
        const settingsData = (await settingsRes.json()) as {
          settings_file_sha256: string;
        };
        await page.request
          .put("/api/settings", {
            data: {
              expected_sha256: settingsData.settings_file_sha256,
              changes: [
                { table: "notifications", key: "quiet_hours_start", value: "" },
                { table: "notifications", key: "quiet_hours_end", value: "" },
              ],
            },
          })
          .catch(() => undefined);
      }
    }
  });
});
