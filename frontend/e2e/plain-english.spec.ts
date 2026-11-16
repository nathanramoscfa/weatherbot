// frontend/e2e/plain-english.spec.ts
import type { Page } from "@playwright/test";
import { expect, test } from "./guard.ts";

const landfallPort = Number(process.env.E2E_LANDFALL_PORT ?? "8806");

const MIAMI = "simulated Miami-Dade";
const NASSAU = "Parliament Square";

const SNAKE_CASE_ID_PATTERN = /\b[a-z]+_[a-z_]+\b/;
const FORBIDDEN_CODE_PATTERN =
  /\b(HWR|TWR|HWA|TWA|TRW|TRA|FLZ\d+|FLC\d+|nhc-[a-z-]+|nws-[a-z-]+)\b/;

function consoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(message.text());
    }
  });
  return errors;
}

function locationCard(page: Page, name: string) {
  return page.locator("article", {
    has: page.getByRole("heading", { name }),
  });
}

test.describe("plain-English hierarchy and provenance disclosure", () => {
  test.use({ baseURL: `http://127.0.0.1:${String(landfallPort)}` });

  test("each hero headline and sentence hold no snake-case rule id or product code, and opening the disclosure reveals hurricane_warning, HWR, and the evacuation-order switch", async ({
    page,
  }) => {
    const errors = consoleErrors(page);
    await page.goto("/");

    const miamiCard = locationCard(page, MIAMI);
    const nassauCard = locationCard(page, NASSAU);
    await expect(miamiCard).toBeVisible();
    await expect(nassauCard).toBeVisible();

    const featured = page.getByTestId("featured-location");
    const headline = featured.getByTestId("location-hero-headline");
    const sentence = featured.getByTestId("location-hero-sentence");
    await expect(headline).toHaveText("Level 5 — Hurricane Warning");
    await expect(sentence).toBeVisible();

    const miamiHeadlineText = (await headline.textContent()) ?? "";
    const miamiSentenceText = (await sentence.textContent()) ?? "";
    expect(miamiHeadlineText).not.toMatch(SNAKE_CASE_ID_PATTERN);
    expect(miamiHeadlineText).not.toMatch(FORBIDDEN_CODE_PATTERN);
    expect(miamiSentenceText).not.toMatch(SNAKE_CASE_ID_PATTERN);
    expect(miamiSentenceText).not.toMatch(FORBIDDEN_CODE_PATTERN);

    const miamiDisclosure = featured.getByTestId("why-this-level");
    await expect(miamiDisclosure).not.toHaveAttribute("open");
    await expect(
      featured.getByRole("switch", {
        name: `Evacuation order for ${MIAMI}`,
      }),
    ).not.toBeVisible();

    await miamiDisclosure
      .locator("summary", {
        hasText: "Why this level / Official provenance & controls",
      })
      .click();
    await expect(miamiDisclosure).toHaveAttribute("open", "");

    await expect(
      miamiDisclosure.getByText("hurricane_warning", { exact: true }),
    ).toBeVisible();
    await expect(miamiDisclosure.getByText(/HWR/).first()).toBeVisible();
    await expect(
      miamiDisclosure.getByRole("switch", {
        name: `Evacuation order for ${MIAMI}`,
      }),
    ).toBeVisible();

    // Feature Parliament Square and verify its hero headline and sentence too
    await page.getByRole("link", { name: NASSAU }).click();
    await expect(headline).toHaveText("Level 4 — Warning / Watch / Evacuation");
    const nassauHeadlineText = (await headline.textContent()) ?? "";
    const nassauSentenceText = (await sentence.textContent()) ?? "";
    expect(nassauHeadlineText).not.toMatch(SNAKE_CASE_ID_PATTERN);
    expect(nassauHeadlineText).not.toMatch(FORBIDDEN_CODE_PATTERN);
    expect(nassauSentenceText).not.toMatch(SNAKE_CASE_ID_PATTERN);
    expect(nassauSentenceText).not.toMatch(FORBIDDEN_CODE_PATTERN);

    expect(errors).toEqual([]);
  });
});
