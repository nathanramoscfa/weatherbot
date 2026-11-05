// frontend/e2e/charts.spec.ts
import { expect, test } from "./guard.ts";

test.describe("Dashboard and Timeline SVG charts", () => {
  test("renders comparison strip, level sparklines, arrival timelines, and timeline charts across themes and phone width without CSP errors", async ({
    page,
  }) => {
    await page.goto("/");

    const comparisonStrip = page.getByTestId("location-comparison-strip");
    await expect(comparisonStrip).toBeVisible();
    await expect(
      comparisonStrip.getByRole("link", { name: "simulated Miami-Dade" }),
    ).toHaveAttribute("href", "#location-simulated-miami-dade");

    await expect(page.getByTestId("level-sparkline").first()).toBeVisible();
    await expect(page.getByTestId("arrival-timeline").first()).toBeVisible();

    // Navigate to Timeline and select simulated Miami-Dade
    await page.getByRole("link", { name: /^Timeline$/i }).click();
    await expect(
      page.getByRole("heading", { name: "Timeline" }),
    ).toBeVisible();

    const filterSelect = page.getByLabel("Filter by location");
    await filterSelect.selectOption("simulated Miami-Dade");

    const historyChart = page.getByTestId("level-history-chart");
    const windChart = page.getByTestId("wind-probability-chart");
    await expect(historyChart).toBeVisible();
    await expect(windChart).toBeVisible();
    await expect(page.getByTestId("wind-probability-caption")).toHaveText(
      "The official chance of these winds within 120 hours, as each advisory cycle put it",
    );

    // Toggle theme and verify charts remain visible
    const themeToggle = page.getByRole("button", { name: /theme/i });
    if ((await themeToggle.count()) > 0) {
      await themeToggle.first().click();
      await expect(historyChart).toBeVisible();
      await expect(windChart).toBeVisible();
    }

    // Verify phone width (360px) fits without horizontal overflow
    await page.setViewportSize({ width: 360, height: 740 });
    await expect(historyChart).toBeVisible();
    await expect(windChart).toBeVisible();
    const hasHorizontalOverflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth,
    );
    expect(hasHorizontalOverflow).toBe(false);
  });
});
