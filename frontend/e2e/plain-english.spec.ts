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

    for (const card of [miamiCard, nassauCard]) {
      const headline = card.getByTestId("location-hero-headline");
      const sentence = card.getByTestId("location-hero-sentence");
      await expect(headline).toBeVisible();
      await expect(sentence).toBeVisible();

      const headlineText = (await headline.textContent()) ?? "";
      const sentenceText = (await sentence.textContent()) ?? "";
      expect(headlineText).not.toMatch(SNAKE_CASE_ID_PATTERN);
      expect(headlineText).not.toMatch(FORBIDDEN_CODE_PATTERN);
      expect(sentenceText).not.toMatch(SNAKE_CASE_ID_PATTERN);
      expect(sentenceText).not.toMatch(FORBIDDEN_CODE_PATTERN);
    }

    await expect(
      miamiCard.getByTestId("location-hero-headline"),
    ).toHaveText("Level 5 — Hurricane Warning");
    await expect(
      nassauCard.getByTestId("location-hero-headline"),
    ).toHaveText("Level 4 — Warning / Watch / Evacuation");

    const miamiDisclosure = miamiCard.getByTestId("why-this-level");
    await expect(miamiDisclosure).not.toHaveAttribute("open");
    await expect(
      miamiCard.getByRole("switch", {
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

    expect(errors).toEqual([]);
  });
});
