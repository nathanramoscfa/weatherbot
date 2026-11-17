// frontend/e2e/phase8.spec.ts
import { expect, test } from "./guard.ts";

const landfallPort = Number(process.env.E2E_LANDFALL_PORT ?? "8806");

test.describe("Phase 8 redesigned surface", () => {
  test.use({ baseURL: `http://127.0.0.1:${String(landfallPort)}` });

  test("walks the command center, map panels, replay, settings, Ask chips, and list headlines without console errors", async ({ page }) => {
    const errors: string[] = [];
    const chatRequests: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    page.on("request", (request) => {
      if (new URL(request.url()).pathname === "/api/ai/chat") chatRequests.push(request.url());
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await expect(page.getByTestId("status-bar")).toBeVisible();
    await expect(page.getByTestId("next-product-countdown")).toBeVisible();
    await page.getByTestId("export-report-trigger").click();
    await expect(page.getByTestId("export-report-all")).toBeVisible();
    await expect(page.getByLabel("Include the AI briefing")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("location-switcher")).toBeVisible();
    await expect(page.getByTestId("location-hero-headline")).toContainText("Level 5");
    await expect(page.getByTestId("featured-stat-tiles")).toBeVisible();
    await expect(page.getByTestId("dashboard-mini-map")).toBeVisible();
    await page.getByRole("link", { name: "Parliament Square", exact: true }).click();
    await expect(page.getByTestId("location-hero-headline")).toContainText("Level 4");
    const disclosure = page.getByTestId("why-this-level");
    await disclosure.locator("summary").click();
    await expect(disclosure.getByRole("switch")).toBeVisible();

    await page.goto("/map");
    for (const id of ["map-layers-panel", "map-legend-panel"]) {
      const button = page.getByTestId(id).getByRole("button").first();
      await expect(button).toHaveAttribute("aria-expanded", "true");
      await button.click();
      await expect(button).toHaveAttribute("aria-expanded", "false");
      await button.click();
      await expect(button).toHaveAttribute("aria-expanded", "true");
    }
    await page.goto("/replay");
    await page.getByLabel("Replay storm").selectOption("AL052019");
    await page.getByLabel("Replay location").selectOption("Parliament Square");
    await expect(page.getByTestId("replay-banner")).toBeVisible({ timeout: 30_000 });
    const response = await page.request.get("/api/replay/AL052019/timeline?location=Parliament%20Square");
    expect(response.ok()).toBe(true);
    const timeline = await response.json() as { steps: { advisory_id: string }[] };
    for (const [advisory, level] of [["024", 4], ["026", 5]] as const) {
      const index = timeline.steps.findIndex((step) => step.advisory_id === advisory);
      expect(index).toBeGreaterThan(0);
      const slider = page.getByRole("slider", { name: /Advisory history/i });
      await slider.fill(String(index));
      await slider.dispatchEvent("mouseup");
      await expect(page.getByTestId("location-hero-headline")).toContainText(`Level ${String(level)}`);
    }
    for (const [hash, name] of [
      ["locations", "Watched Locations"], ["notifications", "Quiet Hours & Cooldown"],
      ["ai", "AI"], ["retention", "Database & Retention"], ["about", "Full Disclaimer"],
    ]) {
      await page.goto(`/settings#${hash}`);
      await expect(page.getByRole("heading", { name, exact: true }).first()).toBeVisible();
    }
    await page.goto("/ask");
    await page.getByTestId("ask-chip-1").click();
    await expect(page.getByLabel("Your question")).not.toHaveValue("");
    await expect(page.getByLabel("Your question")).toBeFocused();
    expect(chatRequests).toEqual([]);
    for (const path of ["/storms", "/alerts", "/timeline"]) {
      await page.goto(path);
      const headline = page.locator("main h2").first();
      await expect(headline).toBeVisible();
      await expect(headline).not.toContainText(/hurricane_warning|nhc-|HWR|FLZ/);
    }
    expect(errors).toEqual([]);
  });
});
