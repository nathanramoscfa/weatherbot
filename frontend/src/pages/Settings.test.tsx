// frontend/src/pages/Settings.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { BROWSER_NOTIFICATIONS_STORAGE_KEY } from "../notifications/notify.ts";
import disclaimerFixture from "../test/fixtures/disclaimer.json";
import locationsFixture from "../test/fixtures/locations.json";
import notificationsFixture from "../test/fixtures/notifications.json";
import settingsFixture from "../test/fixtures/settings.json";
import { asSchema, type JsonFixture } from "./format.ts";
import { type BundledLicenseEntry, Settings } from "./Settings.tsx";

const TYPED_SETTINGS = asSchema<components["schemas"]["SettingsResponse"]>(
  settingsFixture satisfies JsonFixture<
    components["schemas"]["SettingsResponse"]
  >,
);
const TYPED_DISCLAIMER = asSchema<components["schemas"]["DisclaimerResponse"]>(
  disclaimerFixture satisfies JsonFixture<
    components["schemas"]["DisclaimerResponse"]
  >,
);
const TYPED_LOCATIONS = asSchema<components["schemas"]["LocationsResponse"]>(
  locationsFixture satisfies JsonFixture<
    components["schemas"]["LocationsResponse"]
  >,
);
const TYPED_NOTIFICATIONS = asSchema<
  components["schemas"]["NotificationsResponse"]
>(
  notificationsFixture satisfies JsonFixture<
    components["schemas"]["NotificationsResponse"]
  >,
);

const SAMPLE_LICENSES: BundledLicenseEntry[] = [
  { name: "react", version: "19.3.1", license: "MIT" },
  { name: "radix-ui", version: "1.8.1", license: "MIT" },
];

describe("Settings", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("renders effective settings with origins, the reload banner when file_modified_since_start is true, the disclaimer, and bundled dependency licences", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.settings(), {
      ...TYPED_SETTINGS,
      file_modified_since_start: true,
    });
    queryClient.setQueryData(queryKeys.disclaimer(), TYPED_DISCLAIMER);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.licenses(), SAMPLE_LICENSES);

    render(
      <QueryClientProvider client={queryClient}>
        <Settings initialLicenses={SAMPLE_LICENSES} />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Settings" }),
    ).toBeInTheDocument();

    // Reload banner when file_modified_since_start is true
    expect(
      screen.getByText(/Configuration file modified since monitor start/i),
    ).toBeInTheDocument();

    // Effective settings and origins
    expect(screen.getByText("[engine] coastal_reach_km")).toBeInTheDocument();
    expect(
      screen.getByText("WEATHERBOT_ENGINE_COASTAL_REACH_KM"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("default").length).toBeGreaterThan(0);

    // Disclaimer and bundled licences
    expect(
      screen.getByRole("heading", { name: "Full Disclaimer" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/WEATHERBOT LEGAL DISCLAIMER/i),
    ).toBeInTheDocument();
    expect(screen.getByText("react")).toBeInTheDocument();
    expect(screen.getByText("radix-ui")).toBeInTheDocument();
  });

  it("submits POST /api/locations and shows plain messages on 409 and 422", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.settings(), TYPED_SETTINGS);
    queryClient.setQueryData(queryKeys.disclaimer(), TYPED_DISCLAIMER);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.licenses(), SAMPLE_LICENSES);

    const postSpy = vi.spyOn(apiClient, "POST");

    render(
      <QueryClientProvider client={queryClient}>
        <Settings initialLicenses={SAMPLE_LICENSES} />
      </QueryClientProvider>,
    );

    const nameInput = screen.getByLabelText("Location name");
    const latInput = screen.getByLabelText("Latitude");
    const lonInput = screen.getByLabelText("Longitude");
    const addBtn = screen.getByRole("button", { name: "Add location" });

    // 1. 409 Conflict
    postSpy.mockResolvedValueOnce({
      data: undefined,
      response: new Response(null, { status: 409 }),
    });

    await user.type(nameInput, "Miami-Dade County Hall");
    await user.type(latInput, "25.78");
    await user.type(lonInput, "-80.20");
    await user.click(addBtn);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "A location with that name already exists (/api/locations returned HTTP 409).",
    );

    // 2. 422 Unprocessable Entity
    postSpy.mockResolvedValueOnce({
      data: undefined,
      response: new Response(null, { status: 422 }),
    });
    await user.click(addBtn);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Invalid location parameters or zone polygon requested outside NWS coverage (/api/locations returned HTTP 422).",
    );

    // 3. 201 Created
    postSpy.mockResolvedValueOnce({
      data: TYPED_LOCATIONS.locations[0]!,
      response: new Response(null, { status: 201 }),
    });
    await user.click(addBtn);

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        'Added location "Miami-Dade County Hall".',
      );
    });
  });

  it("submits POST /api/notifications/test and flips the browser notification switch in localStorage", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.settings(), TYPED_SETTINGS);
    queryClient.setQueryData(queryKeys.disclaimer(), TYPED_DISCLAIMER);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.licenses(), SAMPLE_LICENSES);

    const postSpy = vi.spyOn(apiClient, "POST").mockResolvedValue({
      data: TYPED_NOTIFICATIONS.notifications[0]!,
      response: new Response(null, { status: 200 }),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Settings initialLicenses={SAMPLE_LICENSES} />
      </QueryClientProvider>,
    );

    const notifSwitch = screen.getByRole("switch", {
      name: "Browser notifications",
    });
    expect(notifSwitch).toHaveAttribute("aria-checked", "false");
    expect(
      window.localStorage.getItem(BROWSER_NOTIFICATIONS_STORAGE_KEY),
    ).toBeNull();

    await user.click(notifSwitch);
    expect(notifSwitch).toHaveAttribute("aria-checked", "true");
    expect(
      window.localStorage.getItem(BROWSER_NOTIFICATIONS_STORAGE_KEY),
    ).toBe("on");

    const testBtn = screen.getByRole("button", {
      name: "Send test notification",
    });
    await user.click(testBtn);
    expect(postSpy).toHaveBeenCalledWith("/api/notifications/test", {
      body: {},
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Test notification sent/i,
    );
  });
});
