// frontend/e2e/replay.spec.ts
import { expect, test } from "./guard.ts";

interface TimelineStep {
  readonly advisory_id: string;
  readonly advisory: string;
}

interface TimelineDoc {
  readonly steps: readonly TimelineStep[];
}

test.describe("Replay scrubber page", () => {
  test("scrubs Dorian at Parliament Square to advisories 24 (Level 4) and 26 (Level 5 with HWR) under the not-live banner without AI calls or notification events", async ({
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

    const timelineRes = await page.request.get(
      "/api/replay/AL052019/timeline?location=Parliament%20Square",
    );
    expect(timelineRes.ok()).toBe(true);
    const timelineDoc = (await timelineRes.json()) as TimelineDoc;
    const idx024 = timelineDoc.steps.findIndex((s) => s.advisory_id === "024");
    const idx026 = timelineDoc.steps.findIndex((s) => s.advisory_id === "026");
    expect(idx024).toBeGreaterThan(0);
    expect(idx026).toBeGreaterThan(idx024);

    const slider = page.getByRole("slider", { name: /Advisory history/i });
    await expect(slider).toBeVisible();

    // Slide to advisory 024 (Level 4)
    await slider.fill(String(idx024));
    await slider.dispatchEvent("mouseup");

    await expect(banner).toContainText("Replay: Dorian advisory 24, issued");
    await expect(banner).toContainText("— not live");

    const assessmentCard = page.getByTestId("replay-assessment-card");
    await expect(assessmentCard).toBeVisible();
    await expect(assessmentCard).toContainText("Level 4");
    await expect(assessmentCard).toContainText("hurricane_watch");

    // Slide to advisory 026 (Level 5 with HWR)
    await slider.fill(String(idx026));
    await slider.dispatchEvent("mouseup");

    await expect(banner).toContainText("Replay: Dorian advisory 26, issued");
    await expect(banner).toContainText("— not live");
    await expect(assessmentCard).toContainText("Level 5");
    await expect(assessmentCard).toContainText("hurricane_warning");
    await expect(assessmentCard).toContainText("HWR");

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
