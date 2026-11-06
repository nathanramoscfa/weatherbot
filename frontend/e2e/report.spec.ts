// frontend/e2e/report.spec.ts
import { mkdirSync, readFileSync } from "node:fs";
import { expect, recordAiText, test } from "./guard.ts";

const LANDMARK = "Parliament Square";

test("ticks Include the AI briefing, downloads the report, opens it offline with zero external requests, and renders to PDF", async ({
  page,
  browser,
}) => {
  await page.goto("/");

  const panel = page.getByRole("region", {
    name: `AI briefing for ${LANDMARK}`,
  });
  await expect(panel).toBeVisible();

  const briefButton = panel.getByRole("button", { name: "Brief me" });
  await expect(briefButton).toBeEnabled();
  await briefButton.click();
  await expect(panel.getByText("Writing the briefing…")).toBeVisible();
  await expect(panel.getByText("Writing the briefing…")).toBeHidden({
    timeout: 30_000,
  });
  await expect(
    panel.getByRole("heading", { name: "Situation" }),
  ).toBeVisible();
  await expect(panel.getByTestId("ai-label")).toContainText(
    "Claude Sonnet 5.5",
  );
  recordAiText(page, await panel.innerText());

  const briefingCheckbox = page.getByRole("checkbox", {
    name: /Include the AI briefing/i,
  });
  await expect(briefingCheckbox).not.toBeChecked();
  await briefingCheckbox.check();
  await expect(briefingCheckbox).toBeChecked();

  const exportLink = page.getByTestId("export-report-all");
  await expect(exportLink).toHaveAttribute("href", "/api/report?briefing=true");

  const downloadPromise = page.waitForEvent("download");
  await exportLink.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(
    /^weatherbot-report-\d{8}T\d{4}Z\.html$/,
  );

  mkdirSync("test-results", { recursive: true });
  const savedPath = "test-results/exported-report.html";
  await download.saveAs(savedPath);
  const fileUrl = new URL("../test-results/exported-report.html", import.meta.url)
    .href;
  const savedHtml = readFileSync(savedPath, "utf8");
  expect(savedHtml).toContain("<!doctype html>");

  const offlineContext = await browser.newContext({ offline: true });
  try {
    const externalRequests: string[] = [];

    offlineContext.on("request", (req) => {
      const url = req.url();
      if (!url.startsWith("file://")) {
        externalRequests.push(url);
      }
    });

    const offlinePage = await offlineContext.newPage();
    await offlinePage.goto(fileUrl);

    expect(externalRequests).toEqual([]);

    await expect(offlinePage.getByTestId("report-notice")).toContainText(
      "Informational only; never a substitute for official guidance. See DISCLAIMER.md.",
    );
    await expect(offlinePage.getByTestId("report-footer")).toContainText(
      "Weatherbot is informational only.",
    );
    await expect(offlinePage.getByTestId("ai-label")).toContainText(
      "AI briefing · Claude Sonnet 5.5",
    );
    await expect(offlinePage.getByTestId("ai-label")).toContainText(
      "AI-generated · may be wrong · the level above comes from official products",
    );

    const pdfBytes = (await offlinePage.pdf()) as unknown as Uint8Array;
    expect(pdfBytes.byteLength).toBeGreaterThan(100);
    const pdfHeader = new TextDecoder().decode(pdfBytes.subarray(0, 4));
    expect(pdfHeader).toBe("%PDF");
  } finally {
    await offlineContext.close();
  }
});
