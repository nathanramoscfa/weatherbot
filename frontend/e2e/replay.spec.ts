// frontend/e2e/replay.spec.ts
import { expect, test } from "./guard.ts";

const quietPort = Number(process.env.E2E_QUIET_PORT ?? "8802");

interface TimelineStep {
  readonly advisory_id: string;
  readonly advisory: string;
}

interface TimelineDoc {
  readonly steps: readonly TimelineStep[];
}

test.describe("Replay scrubber page", () => {
  // Run against the quiet demonstration server (no 1-minute switch-file roster
  // poll), so a background live cycle on 8799 never inserts a notification row
  // between beforeNotifIds and afterNotifIds while Dorian scrubs.
  test.use({ baseURL: `http://127.0.0.1:${String(quietPort)}` });
  test("shows map, scrubber, and hero headline in the first 1440×900 (1440x900) viewport, scrubs Dorian at Parliament Square to advisories 24 and 26 without AI or notification events, and stacks in order at 390×844 (390x844)", async ({
    page,
  }) => {
    const requestedUrls: string[] = [];
    page.on("request", (req) => {
      requestedUrls.push(req.url());
    });

    const beforeNotifsRes = await page.request.get("/api/notifications");
    expect(beforeNotifsRes.ok()).toBe(true);
    const beforeNotifsJson = (await beforeNotifsRes.json()) as {
      readonly notifications: readonly { readonly id: number }[];
    };
    const beforeNotifIds = beforeNotifsJson.notifications.map((n) => n.id);

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/replay");

    await expect(
      page.getByRole("heading", { name: "Replay", exact: true }),
    ).toBeVisible();

    const stormPicker = page.getByLabel("Replay storm");
    const locationPicker = page.getByLabel("Replay location");
    await expect(stormPicker).toBeVisible();
    await expect(locationPicker).toBeVisible();

    await stormPicker.selectOption("AL052019");
    await locationPicker.selectOption("Parliament Square");

    const banner = page.getByTestId("replay-banner");
    await expect(banner).toBeVisible({ timeout: 30_000 });
    await expect(banner).toContainText("Replay: Dorian advisory 1, issued");
    await expect(banner).toContainText("— not live");

    const replayMap = page.getByTestId("replay-leaflet-map");
    const scrubber = page.getByTestId("replay-scrubber");
    const slider = page.getByRole("slider", { name: /Advisory history/i });
    const assessmentCard = page.getByTestId("replay-assessment-card");
    const heroHeadline = page.getByTestId("location-hero-headline");
    const disclosure = assessmentCard.getByTestId("why-this-level");

    await expect(replayMap).toBeVisible();
    await expect(scrubber).toBeVisible();
    await expect(slider).toBeVisible();
    await expect(assessmentCard).toBeVisible();
    await expect(heroHeadline).toBeVisible();

    // At 1440×900, the map (>= 60% viewport height), the slider/scrubber, and the hero's headline
    // all lie within the first 900 pixels without scrolling, in two side-by-side columns.
    const mapBoxWide = await replayMap.boundingBox();
    const scrubberBoxWide = await scrubber.boundingBox();
    const sliderBoxWide = await slider.boundingBox();
    const headlineBoxWide = await heroHeadline.boundingBox();

    expect(mapBoxWide).not.toBeNull();
    expect(scrubberBoxWide).not.toBeNull();
    expect(sliderBoxWide).not.toBeNull();
    expect(headlineBoxWide).not.toBeNull();

    expect(mapBoxWide!.height).toBeGreaterThanOrEqual(900 * 0.6 - 1);
    expect(mapBoxWide!.y).toBeGreaterThanOrEqual(0);
    expect(mapBoxWide!.y + mapBoxWide!.height).toBeLessThanOrEqual(900);

    expect(sliderBoxWide!.y).toBeGreaterThanOrEqual(0);
    expect(sliderBoxWide!.y + sliderBoxWide!.height).toBeLessThanOrEqual(900);
    expect(scrubberBoxWide!.y).toBeGreaterThanOrEqual(
      mapBoxWide!.y + mapBoxWide!.height - 2,
    );

    expect(headlineBoxWide!.y).toBeGreaterThanOrEqual(0);
    expect(headlineBoxWide!.y + headlineBoxWide!.height).toBeLessThanOrEqual(
      900,
    );
    expect(headlineBoxWide!.x).toBeGreaterThan(
      mapBoxWide!.x + mapBoxWide!.width,
    );

    const timelineRes = await page.request.get(
      "/api/replay/AL052019/timeline?location=Parliament%20Square",
    );
    expect(timelineRes.ok()).toBe(true);
    const timelineDoc = (await timelineRes.json()) as TimelineDoc;
    const idx024 = timelineDoc.steps.findIndex((s) => s.advisory_id === "024");
    const idx026 = timelineDoc.steps.findIndex((s) => s.advisory_id === "026");
    expect(idx024).toBeGreaterThan(0);
    expect(idx026).toBeGreaterThan(idx024);

    // Slide to advisory 024 (Level 4)
    await slider.fill(String(idx024));
    await slider.dispatchEvent("mouseup");

    await expect(banner).toContainText("Replay: Dorian advisory 24, issued");
    await expect(banner).toContainText("— not live");
    await expect(heroHeadline).toContainText("Level 4");
    await expect(assessmentCard).toContainText("Level 4");
    await expect(disclosure).toContainText("hurricane_watch");

    // Slide to advisory 026 (Level 5 with HWR)
    await slider.fill(String(idx026));
    await slider.dispatchEvent("mouseup");

    await expect(banner).toContainText("Replay: Dorian advisory 26, issued");
    await expect(banner).toContainText("— not live");
    await expect(heroHeadline).toContainText("Level 5");
    await expect(assessmentCard).toContainText("Level 5");
    await expect(disclosure).toContainText("hurricane_warning");
    await expect(disclosure).toContainText("HWR");

    // Advisory map fills its container with multiple tiles and non-zero SVG overlay viewport
    await expect
      .poll(async () => replayMap.locator(".leaflet-tile").count())
      .toBeGreaterThan(1);
    const overlaySvg = replayMap.locator(".leaflet-overlay-pane svg").first();
    await expect(overlaySvg).toBeVisible();
    const svgWidth = Number(await overlaySvg.getAttribute("width"));
    const svgHeight = Number(await overlaySvg.getAttribute("height"));
    expect(svgWidth).toBeGreaterThan(100);
    expect(svgHeight).toBeGreaterThan(100);
    const nonDegeneratePaths = await replayMap
      .locator('.leaflet-overlay-pane svg path:not([d="M0 0"])')
      .count();
    expect(nonDegeneratePaths).toBeGreaterThan(0);

    // At 390×844, the workbench stacks in order: pickers, banner, map, scrubber, hero, chart, disclosure
    await page.setViewportSize({ width: 390, height: 844 });
    const pickers = page.getByTestId("replay-pickers");
    const hero = assessmentCard.getByTestId("location-hero");
    const chart = page.getByTestId("level-history-chart");

    await expect(pickers).toBeVisible();
    await expect(chart).toBeVisible();

    const pickersBox = await pickers.boundingBox();
    const bannerBox = await banner.boundingBox();
    const mapBoxNarrow = await replayMap.boundingBox();
    const scrubberBoxNarrow = await scrubber.boundingBox();
    const heroBox = await hero.boundingBox();
    const chartBox = await chart.boundingBox();
    const disclosureBox = await disclosure.boundingBox();

    expect(pickersBox).not.toBeNull();
    expect(bannerBox).not.toBeNull();
    expect(mapBoxNarrow).not.toBeNull();
    expect(scrubberBoxNarrow).not.toBeNull();
    expect(heroBox).not.toBeNull();
    expect(chartBox).not.toBeNull();
    expect(disclosureBox).not.toBeNull();

    expect(pickersBox!.y).toBeLessThan(bannerBox!.y);
    expect(bannerBox!.y).toBeLessThan(mapBoxNarrow!.y);
    expect(mapBoxNarrow!.y).toBeLessThan(scrubberBoxNarrow!.y);
    expect(scrubberBoxNarrow!.y).toBeLessThan(heroBox!.y);
    expect(heroBox!.y).toBeLessThan(chartBox!.y);
    expect(chartBox!.y).toBeLessThan(disclosureBox!.y);

    // Map tiles and overlay remain non-zero in the narrow layout
    await expect
      .poll(async () => replayMap.locator(".leaflet-tile").count())
      .toBeGreaterThan(1);
    expect(Number(await overlaySvg.getAttribute("width"))).toBeGreaterThan(100);
    expect(Number(await overlaySvg.getAttribute("height"))).toBeGreaterThan(
      100,
    );

    // No AI panel or evacuation switch on the Replay page
    await expect(page.getByTestId("ai-label")).toHaveCount(0);
    await expect(page.getByRole("switch")).toHaveCount(0);

    // No request to Anthropic or /api/ai/ occurred while scrubbing
    const aiRequests = requestedUrls.filter(
      (url) => url.includes("anthropic") || url.includes("/api/ai"),
    );
    expect(aiRequests).toEqual([]);

    // No notification row or event was created by scrubbing
    const afterNotifsRes = await page.request.get("/api/notifications");
    expect(afterNotifsRes.ok()).toBe(true);
    const afterNotifsJson = (await afterNotifsRes.json()) as {
      readonly notifications: readonly { readonly id: number }[];
    };
    const afterNotifIds = afterNotifsJson.notifications.map((n) => n.id);
    expect(afterNotifIds).toEqual(beforeNotifIds);
  });
});
