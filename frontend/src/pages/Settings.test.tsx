// frontend/src/pages/Settings.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { BROWSER_NOTIFICATIONS_STORAGE_KEY } from "../notifications/notify.ts";
import { aiStatus, TYPED_AI, TYPED_AI_CALLS } from "../test/ai.ts";
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
    queryClient.setQueryData(queryKeys.ai(), TYPED_AI);
    queryClient.setQueryData(queryKeys.aiCalls(), TYPED_AI_CALLS);

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

    // Watched locations section rendered by LocationManager
    expect(
      screen.getByRole("heading", { name: "Watched Locations" }),
    ).toBeInTheDocument();

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

  it("submits POST /api/notifications/test and flips the browser notification switch in localStorage", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.settings(), TYPED_SETTINGS);
    queryClient.setQueryData(queryKeys.disclaimer(), TYPED_DISCLAIMER);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.licenses(), SAMPLE_LICENSES);
    queryClient.setQueryData(queryKeys.ai(), TYPED_AI);
    queryClient.setQueryData(queryKeys.aiCalls(), TYPED_AI_CALLS);

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

  it("shows the AI's state, credential source, models, today's meter, and recent requests, and pauses, resumes, and allows more behind a confirmation", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.settings(), TYPED_SETTINGS);
    queryClient.setQueryData(queryKeys.disclaimer(), TYPED_DISCLAIMER);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.licenses(), SAMPLE_LICENSES);
    queryClient.setQueryData(queryKeys.ai(), TYPED_AI);
    queryClient.setQueryData(queryKeys.aiCalls(), TYPED_AI_CALLS);
    vi.spyOn(apiClient, "GET").mockResolvedValue({
      data: TYPED_AI_CALLS,
      response: new Response(null, { status: 200 }),
    });
    const paused = aiStatus({ state: "paused", reason: "paused", paused: true });
    const putSpy = vi
      .spyOn(apiClient, "PUT")
      .mockResolvedValueOnce({
        data: paused,
        response: new Response(null, { status: 200 }),
      })
      .mockResolvedValueOnce({
        data: TYPED_AI,
        response: new Response(null, { status: 200 }),
      });
    const allowed = aiStatus({
      today: {
        ...TYPED_AI.today,
        allowance_micro_usd: 1_000_000,
        allowances_left: 2,
      },
    });
    const postSpy = vi
      .spyOn(apiClient, "POST")
      .mockResolvedValueOnce({
        data: allowed,
        response: new Response(null, { status: 200 }),
      })
      .mockResolvedValueOnce({
        error: undefined,
        response: new Response(null, { status: 409 }),
      });

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <Settings initialLicenses={SAMPLE_LICENSES} />
      </QueryClientProvider>,
    );

    const section = screen.getByRole("region", { name: "AI" });
    expect(section).toHaveAttribute("id", "ai");
    expect(within(section).getByText("Ready")).toBeInTheDocument();
    expect(
      within(section).getByText("the ANTHROPIC_API_KEY environment variable"),
    ).toBeInTheDocument();
    expect(within(section).getAllByText(/Claude Sonnet 5\.5/).length).toBeGreaterThan(0);

    const meter = within(section).getByRole("meter", {
      name: "Today's AI spend against today's limit",
    });
    expect(meter).toHaveAttribute("value", "44056");
    expect(meter).toHaveAttribute("max", "1000000");
    expect(
      within(section).getByText(/Spent \$0\.0441 · reserved \$0\.0000 · limit \$1\.00/),
    ).toHaveTextContent("(cap $1.00 + allowance $0.00) · 3 requests");
    expect(container.querySelector("[style]")).toBeNull();

    const rows = within(section).getAllByRole("row");
    expect(rows).toHaveLength(4);
    expect(rows[1]).toHaveTextContent("narration");
    expect(rows[1]).toHaveTextContent("1,283 in · 1,360 cache · 288 out");
    expect(rows[1]).toHaveTextContent("$0.0088");
    expect(rows[1]).toHaveTextContent("ok");
    expect(rows[1]).toHaveTextContent("2026-10-13 01:33 UTC");
    expect(rows[3]).toHaveTextContent("briefing · Miami-Dade County Hall");

    await user.click(within(section).getByRole("button", { name: "Pause AI" }));
    expect(putSpy).toHaveBeenLastCalledWith("/api/ai/pause", {
      body: { paused: true },
    });
    expect(await within(section).findByText("AI paused.")).toBeInTheDocument();
    expect(within(section).getByTestId("ai-state-banner")).toHaveTextContent(
      "AI paused by you — resume it in Settings.",
    );
    await user.click(within(section).getByRole("button", { name: "Resume AI" }));
    expect(putSpy).toHaveBeenLastCalledWith("/api/ai/pause", {
      body: { paused: false },
    });
    expect(await within(section).findByText("AI resumed.")).toBeInTheDocument();

    await user.click(
      within(section).getByRole("button", { name: "Allow $1.00 more today" }),
    );
    const dialog = await screen.findByRole("alertdialog", {
      name: "Allow $1.00 more today?",
    });
    expect(dialog).toHaveTextContent("Today's AI limit rises to $2.00 until midnight.");
    expect(dialog).toHaveTextContent("3 of 3 allowances are left today.");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(postSpy).not.toHaveBeenCalled();

    await user.click(
      within(section).getByRole("button", { name: "Allow $1.00 more today" }),
    );
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", {
        name: "Allow $1.00 more",
      }),
    );
    expect(postSpy).toHaveBeenLastCalledWith("/api/ai/allowance", {
      body: { usd: 1 },
    });
    expect(
      await within(section).findByText("Allowed $1.00 more today."),
    ).toBeInTheDocument();
    expect(within(section).getByText("2 of 3 allowances left today")).toBeInTheDocument();
    expect(within(section).getByText(/limit \$2\.00/)).toBeInTheDocument();

    await user.click(
      within(section).getByRole("button", { name: "Allow $1.00 more today" }),
    );
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", {
        name: "Allow $1.00 more",
      }),
    );
    expect(
      await within(section).findByText(
        "Today's three allowances are used (/api/ai/allowance returned HTTP 409).",
      ),
    ).toBeInTheDocument();
  });

  it("disables the AI controls when [ai] enabled is false", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.settings(), TYPED_SETTINGS);
    queryClient.setQueryData(queryKeys.disclaimer(), TYPED_DISCLAIMER);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.licenses(), SAMPLE_LICENSES);
    queryClient.setQueryData(
      queryKeys.ai(),
      aiStatus({ state: "off", reason: "disabled", credential_source: null }),
    );
    queryClient.setQueryData(queryKeys.aiCalls(), { ...TYPED_AI_CALLS, calls: [] });

    render(
      <QueryClientProvider client={queryClient}>
        <Settings initialLicenses={SAMPLE_LICENSES} />
      </QueryClientProvider>,
    );

    const section = screen.getByRole("region", { name: "AI" });
    expect(within(section).getByTestId("ai-state-banner")).toHaveTextContent(
      "AI is off: [ai] enabled is false in weatherbot.toml.",
    );
    expect(within(section).getByRole("button", { name: "Pause AI" })).toBeDisabled();
    expect(
      within(section).getByRole("button", { name: "Allow $1.00 more today" }),
    ).toBeDisabled();
    expect(within(section).getByText("No AI request is recorded yet.")).toBeInTheDocument();
  });
});
