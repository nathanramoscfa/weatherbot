// frontend/e2e/locations.spec.ts
import { expect, test } from "./guard.ts";

test("searches for a place on submit only, chooses a candidate, adds Nassau with a typed label, and removes it behind a confirmation dialog", async ({
  page,
}) => {
  const searchRequests: string[] = [];
  page.on("request", (req) => {
    if (req.url().endsWith("/api/locations/search")) {
      searchRequests.push(req.method());
    }
  });

  await page.goto("/settings");

  const placeInput = page.getByLabel("Place search");
  await placeInput.pressSequentially("Nassau, Bahamas");
  expect(searchRequests).toEqual([]);

  const searchButton = page.getByRole("button", { name: "Search" });
  await searchButton.click();

  await expect(
    page.getByText(
      "Search by OpenStreetMap Nominatim, © OpenStreetMap contributors",
    ),
  ).toBeVisible();
  expect(searchRequests).toEqual(["POST"]);

  const candidateRadio = page
    .getByRole("radio", { name: /Nassau/i })
    .first();
  await expect(candidateRadio).toBeVisible();
  await candidateRadio.check();

  const nameInput = page.getByLabel("Location name");
  await expect(nameInput).toHaveValue("");

  await nameInput.fill("Nassau");
  await page.getByRole("button", { name: "Add location" }).click();

  await expect(page.getByRole("status")).toContainText(
    'Added location "Nassau".',
  );

  const nassauCard = page.getByRole("article", { name: "Nassau" });
  await expect(nassauCard).toBeVisible();
  await expect(nassauCard).toContainText(
    "Outside NWS coverage: NHC breakpoints",
  );

  await nassauCard.getByRole("button", { name: "Remove" }).click();
  const dialog = page.getByRole("alertdialog", { name: "Remove Nassau?" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("history goes with it");

  await dialog.getByRole("button", { name: "Remove location" }).click();
  await expect(page.getByRole("status")).toContainText(
    'Removed location "Nassau".',
  );
  await expect(nassauCard).toHaveCount(0);
});
