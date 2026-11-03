// frontend/e2e/ai.spec.ts
import { mkdirSync } from "node:fs";
import type { Locator, Page } from "@playwright/test";
import { expect, recordAiText, test } from "./guard.ts";

declare global {
  interface Window {
    __wbSectionCounts?: number[];
  }
}

// The three demonstration servers playwright.config.ts starts: 8799 answers AI
// from recordings, 8800 has a $0.001 cap, and 8801 answers every AI request 401.
const CAP_URL = `http://127.0.0.1:${process.env.E2E_AI_CAP_PORT ?? "8800"}`;
const AUTH_URL = `http://127.0.0.1:${process.env.E2E_AI_AUTH_PORT ?? "8801"}`;
const LANDMARK = "Parliament Square";
const OTHER_LANDMARK = "simulated Miami-Dade";
const WRITING = "Writing the briefing…";
const AUTH_FAILED = "AI unavailable: authentication failed";

const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 360, height: 740 },
] as const;
const THEMES = ["light", "dark"] as const;
const BASINS = ["Atlantic", "Eastern Pacific", "Central Pacific"] as const;
const HORIZONS = ["two-day", "seven-day"] as const;

interface AiStatus {
  state: string;
  reason: string | null;
  today: { cap_micro_usd: number; spent_micro_usd: number };
}

interface AiCall {
  kind: string;
  status: string;
  error_kind: string | null;
}

function briefingPanel(page: Page, location: string): Locator {
  return page.getByRole("region", { name: `AI briefing for ${location}` });
}

async function aiStatus(page: Page): Promise<AiStatus> {
  const response = await page.request.get("/api/ai");
  expect(response.ok()).toBe(true);
  return (await response.json()) as AiStatus;
}

async function aiCalls(page: Page): Promise<AiCall[]> {
  const response = await page.request.get("/api/ai/calls?limit=10");
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { calls: AiCall[] }).calls;
}

// Records how many sections the panel shows each time it changes while the
// briefing is being written, so the test can tell they arrived one by one.
async function watchSections(page: Page, location: string): Promise<void> {
  await page.evaluate(
    ({ name, writing }) => {
      const counts: number[] = [];
      window.__wbSectionCounts = counts;
      const region = document.querySelector(
        `section[aria-label="AI briefing for ${name}"]`,
      );
      if (region === null) {
        return;
      }
      new MutationObserver(() => {
        const statuses = Array.from(region.querySelectorAll('[role="status"]'));
        if (!statuses.some((el) => el.textContent?.includes(writing))) {
          return;
        }
        const shown = region.querySelectorAll("h4").length;
        if (counts[counts.length - 1] !== shown) {
          counts.push(shown);
        }
      }).observe(region, { childList: true, subtree: true, characterData: true });
    },
    { name: location, writing: WRITING },
  );
}

async function captureThemes(
  page: Page,
  target: Locator,
  name: string,
): Promise<void> {
  mkdirSync("test-results/screenshots", { recursive: true });
  for (const theme of THEMES) {
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize(viewport);
      await page.evaluate((choice) => {
        window.localStorage.setItem("weatherbot.theme", choice);
        document.documentElement.classList.toggle("dark", choice === "dark");
      }, theme);
      await target.scrollIntoViewIfNeeded();
      const sizeTag = `${String(viewport.width)}x${String(viewport.height)}`;
      await target.screenshot({
        path: `test-results/screenshots/ai-${name}-${sizeTag}-${theme}.png`,
      });
    }
  }
  await page.setViewportSize(VIEWPORTS[0]);
}

test("streams a labeled briefing section by section, answers after a tool chip, and shows the official outlook graphics", async ({
  page,
}) => {
  await page.goto("/");
  const panel = briefingPanel(page, LANDMARK);
  const brief = panel.getByRole("button", { name: "Brief me" });
  await expect(brief).toBeEnabled();

  await watchSections(page, LANDMARK);
  await brief.click();
  await expect(panel.getByText(WRITING)).toBeVisible();
  await expect(panel.getByText(WRITING)).toBeHidden({ timeout: 30_000 });

  const counts = await page.evaluate(() => window.__wbSectionCounts ?? []);
  expect(
    new Set(counts.filter((count) => count > 0)).size,
    `sections shown while writing: ${counts.join(", ")}`,
  ).toBeGreaterThanOrEqual(3);
  expect(counts).toEqual([...counts].sort((a, b) => a - b));

  const label = panel.getByTestId("ai-label");
  await expect(label).toContainText("AI briefing");
  await expect(label).toContainText("Claude Sonnet 5.5");
  await expect(label).toContainText("written");
  await expect(panel.getByRole("heading", { name: "Situation" })).toBeVisible();
  await expect(
    panel.getByRole("button", { name: "Brief me again" }),
  ).toHaveCount(0);
  recordAiText(page, await panel.innerText());
  await captureThemes(page, panel, "briefing");

  // The allowance's confirmation injects a nonced <style>; the guard fails on
  // any Content-Security-Policy violation it raises.
  await page.goto("/settings#ai");
  await page.getByRole("button", { name: /^Allow \$.+ more today$/ }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();

  await page.getByRole("link", { name: "Ask", exact: true }).click();
  await page.getByLabel("About").selectOption(LANDMARK);
  await page
    .getByLabel("Your question")
    .fill("What is the official level here, and what is it based on?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();

  const transcript = page.getByRole("list", { name: "Transcript" });
  await expect(
    transcript
      .getByRole("list", { name: "Lookups" })
      .getByText("Reading the assessment"),
  ).toBeVisible();
  const answer = transcript.getByTestId("chat-answer");
  await expect(answer).toContainText("All Clear");
  await expect(transcript.getByTestId("ai-label")).toContainText("AI answer", {
    timeout: 30_000,
  });
  recordAiText(page, await answer.innerText());
  await captureThemes(page, transcript, "answer");

  await page.goto("/storms");
  for (const horizon of HORIZONS) {
    for (const basin of BASINS) {
      const graphic = page.getByRole("img", {
        name: `National Hurricane Center official ${horizon} graphical tropical weather outlook for the ${basin}`,
      });
      await graphic.scrollIntoViewIfNeeded();
      await expect(graphic).toBeVisible();
      await expect
        .poll(() =>
          graphic.evaluate((element) => (element as HTMLImageElement).naturalWidth),
        )
        .toBeGreaterThan(0);
    }
  }

  const calls = await aiCalls(page);
  expect(calls.map((call) => [call.kind, call.status])).toContainEqual([
    "briefing",
    "ok",
  ]);
});

test.describe("with today's cap below the smallest request", () => {
  test.use({ baseURL: CAP_URL });

  test("reads capped, refuses the first request on the page and the server, and spends nothing", async ({
    page,
  }) => {
    const status = await aiStatus(page);
    expect(status.state).toBe("capped");
    expect(status.today.cap_micro_usd).toBe(1000);

    await page.goto("/");
    const panel = briefingPanel(page, LANDMARK);
    await expect(panel.getByTestId("ai-state-banner")).toContainText(
      "cap is reached",
    );
    await expect(panel.getByRole("button", { name: "Brief me" })).toBeDisabled();

    // The page will not send it; the server refuses the same request before
    // any spend, and the banner still reads the same.
    const refused = await page.request.post("/api/ai/briefings", {
      data: { location: LANDMARK, new: false },
      headers: { Origin: CAP_URL },
    });
    expect(refused.status()).toBe(429);
    const body = (await refused.json()) as { detail: { reason: string } };
    expect(body.detail.reason).toBe("capped");
    expect(await aiCalls(page)).toEqual([]);
    expect((await aiStatus(page)).today.spent_micro_usd).toBe(0);

    await page.reload();
    await expect(panel.getByTestId("ai-state-banner")).toContainText(
      "cap is reached",
    );
    await page.getByRole("link", { name: "Ask", exact: true }).click();
    const conversation = page.locator("section", {
      has: page.getByRole("heading", { name: "Conversation" }),
    });
    await expect(conversation.getByTestId("ai-state-banner")).toContainText(
      "cap is reached",
    );
    await expect(
      conversation.getByRole("button", { name: "Ask", exact: true }),
    ).toBeDisabled();
    await captureThemes(page, conversation, "capped");
  });
});

test.describe("with a credential Anthropic refuses", () => {
  test.use({ baseURL: AUTH_URL });

  test("holds AI unavailable after the third authentication failure", async ({
    page,
  }) => {
    await page.goto("/");
    const panel = briefingPanel(page, LANDMARK);
    const brief = panel.getByRole("button", { name: "Brief me" });

    for (const attempt of [1, 2, 3]) {
      await expect(brief).toBeEnabled();
      await brief.click();
      await expect(panel.getByTestId("ai-state-banner")).toContainText(
        AUTH_FAILED,
      );
      const status = await aiStatus(page);
      expect(status.state, `after attempt ${String(attempt)}`).toBe(
        attempt < 3 ? "ready" : "unavailable",
      );
    }
    expect((await aiStatus(page)).reason).toBe("auth_failed");

    // The hold is the state, not one request's answer: the other card, which
    // never asked, shows it too, and every AI button waits.
    const other = briefingPanel(page, OTHER_LANDMARK);
    await expect(other.getByTestId("ai-state-banner")).toContainText(
      AUTH_FAILED,
    );
    await expect(other.getByRole("button", { name: "Brief me" })).toBeDisabled();
    await expect(brief).toBeDisabled();

    const calls = await aiCalls(page);
    expect(calls).toHaveLength(3);
    for (const call of calls) {
      expect([call.kind, call.status, call.error_kind]).toEqual([
        "briefing",
        "failed",
        "auth_failed",
      ]);
    }
    await captureThemes(page, panel, "auth-failed");
  });
});
