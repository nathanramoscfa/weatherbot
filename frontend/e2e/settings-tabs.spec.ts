// frontend/e2e/settings-tabs.spec.ts
import { expect, test } from "./guard.ts";

test("opens each Settings hash, follows the footer's disclaimer link while open, preserves the selected tab across a reload, and navigates tabs with ArrowRight/ArrowLeft/Home/End", async ({
  page,
}) => {
  // 1. Default tab when opening /settings with no hash is Locations
  await page.goto("/settings");
  const locationsTab = page.getByRole("tab", { name: "Locations" });
  const notificationsTab = page.getByRole("tab", {
    name: "Notifications & Quiet Hours",
  });
  const aiTab = page.getByRole("tab", { name: "AI & Budget" });
  const retentionTab = page.getByRole("tab", {
    name: "History & Retention",
  });
  const aboutTab = page.getByRole("tab", {
    name: "Threat Ladder & About",
  });

  await expect(locationsTab).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("heading", { name: "Watched Locations" }),
  ).toBeVisible();

  // 2. Open each hash directly
  await page.goto("/settings#notifications");
  await expect(notificationsTab).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("heading", { name: "Notification Channels" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Quiet Hours & Cooldown" }),
  ).toBeVisible();

  await page.goto("/settings#ai");
  await expect(aiTab).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("heading", { name: "AI", exact: true }),
  ).toBeVisible();

  await page.goto("/settings#retention");
  await expect(retentionTab).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("heading", { name: "Database & Retention" }),
  ).toBeVisible();

  await page.goto("/settings#about");
  await expect(aboutTab).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("heading", {
      name: "Alert Ladder (11 Rules in Fixed Evaluation Order)",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Effective Settings" }),
  ).toBeVisible();

  // 3. Return to #locations, then follow the footer's router link to /settings#disclaimer
  await locationsTab.click();
  await expect(page).toHaveURL(/#locations$/);
  await expect(locationsTab).toHaveAttribute("aria-selected", "true");

  await page.getByRole("link", { name: "Read full disclaimer" }).click();
  await expect(page).toHaveURL(/#disclaimer$/);
  await expect(aboutTab).toHaveAttribute("aria-selected", "true");
  const disclaimerHeading = page.getByRole("heading", {
    name: "Full Disclaimer",
  });
  await expect(disclaimerHeading).toBeVisible();
  await expect(disclaimerHeading).toBeInViewport();

  // 4. Select History & Retention tab and reload: tab stays selected
  await retentionTab.click();
  await expect(page).toHaveURL(/#retention$/);
  await expect(retentionTab).toHaveAttribute("aria-selected", "true");
  await page.reload();
  await expect(retentionTab).toHaveAttribute("aria-selected", "true");
  await expect(
    page.getByRole("heading", { name: "Database & Retention" }),
  ).toBeVisible();

  // 5. Keyboard navigation: Home, ArrowRight, ArrowLeft, End
  await retentionTab.focus();
  await page.keyboard.press("Home");
  await expect(locationsTab).toBeFocused();
  await expect(locationsTab).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/#locations$/);

  await page.keyboard.press("ArrowRight");
  await expect(notificationsTab).toBeFocused();
  await expect(notificationsTab).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/#notifications$/);

  await page.keyboard.press("ArrowLeft");
  await expect(locationsTab).toBeFocused();
  await expect(locationsTab).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/#locations$/);

  await page.keyboard.press("End");
  await expect(aboutTab).toBeFocused();
  await expect(aboutTab).toHaveAttribute("aria-selected", "true");
  await expect(page).toHaveURL(/#about$/);
});
