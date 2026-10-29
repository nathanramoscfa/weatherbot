// frontend/e2e/dashboard.spec.ts
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { expect, test } from "./guard.ts";

test("dashboard renders landmarks, switches theme under CSP nonce, and updates to level 5 via SSE without reload", async ({
  page,
}) => {
  rmSync("test-results/smoke-switch.flag", { force: true });
  try {
    await page.goto("/");

    await expect(
      page.getByRole("heading", { name: "simulated Miami-Dade" }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Parliament Square" }),
    ).toBeVisible();
    await expect(page.locator("footer")).toContainText(
      "Informational only; never a substitute for official guidance.",
    );

    const themeButton = page.getByRole("button", { name: /^Theme:/ });
    await themeButton.click();
    await page.getByRole("menuitemradio", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);

    await themeButton.click();
    await page.getByRole("menuitemradio", { name: "System" }).click();

    await expect(page.getByText("Live", { exact: true })).toBeVisible();

    await page.evaluate(() => {
      window.__wbSmokeMark = "retained-across-sse";
    });

    mkdirSync("test-results", { recursive: true });
    writeFileSync("test-results/smoke-switch.flag", "switched\n", "utf8");

    await page.getByRole("button", { name: "Check now" }).click();

    const miamiCard = page.locator("article", {
      has: page.getByRole("heading", { name: "simulated Miami-Dade" }),
    });
    await expect(miamiCard).toContainText("Level 5", {
      timeout: 90_000,
    });
    await expect(miamiCard).toContainText("Hurricane Warning");

    await expect(
      page.getByRole("button", { name: "Dismiss notification" }),
    ).toBeVisible({ timeout: 15_000 });

    const smokeMark = await page.evaluate(() => window.__wbSmokeMark);
    expect(smokeMark).toBe("retained-across-sse");
  } finally {
    rmSync("test-results/smoke-switch.flag", { force: true });
  }
});
