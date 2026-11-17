// frontend/src/pages/Settings.test.tsx
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Link, MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { BROWSER_NOTIFICATIONS_STORAGE_KEY } from "../notifications/notify.ts";
import { aiStatus, TYPED_AI, TYPED_AI_CALLS } from "../test/ai.ts";
import disclaimerFixture from "../test/fixtures/disclaimer.json";
import ladderFixture from "../test/fixtures/ladder.json";
import locationsFixture from "../test/fixtures/locations.json";
import notificationChannelsFixture from "../test/fixtures/notification-channels.json";
import notificationsFixture from "../test/fixtures/notifications.json";
import retentionFixture from "../test/fixtures/retention.json";
import settingsFixture from "../test/fixtures/settings.json";
import { asSchema, type JsonFixture } from "./format.ts";
import { type BundledLicenseEntry, Settings } from "./Settings.tsx";

const TYPED_SETTINGS = asSchema<components["schemas"]["SettingsResponse"]>(
  settingsFixture satisfies JsonFixture<
    components["schemas"]["SettingsResponse"]
  >,
);
const TYPED_RETENTION = asSchema<components["schemas"]["RetentionResponse"]>(
  retentionFixture satisfies JsonFixture<
    components["schemas"]["RetentionResponse"]
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
const TYPED_CHANNELS = asSchema<
  components["schemas"]["NotificationChannelsResponse"]
>(
  notificationChannelsFixture satisfies JsonFixture<
    components["schemas"]["NotificationChannelsResponse"]
  >,
);
const TYPED_LADDER = asSchema<components["schemas"]["LadderResponse"]>(
  ladderFixture satisfies JsonFixture<components["schemas"]["LadderResponse"]>,
);

const SAMPLE_LICENSES: BundledLicenseEntry[] = [
  { name: "react", version: "19.3.1", license: "MIT" },
  { name: "radix-ui", version: "1.8.1", license: "MIT" },
];

function seedAll(queryClient: QueryClient) {
  queryClient.setQueryData(queryKeys.settings(), TYPED_SETTINGS);
  queryClient.setQueryData(queryKeys.ladder(), TYPED_LADDER);
  queryClient.setQueryData(queryKeys.retention(), TYPED_RETENTION);
  queryClient.setQueryData(queryKeys.disclaimer(), TYPED_DISCLAIMER);
  queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
  queryClient.setQueryData(queryKeys.notificationChannels(), TYPED_CHANNELS);
  queryClient.setQueryData(queryKeys.licenses(), SAMPLE_LICENSES);
  queryClient.setQueryData(queryKeys.ai(), TYPED_AI);
  queryClient.setQueryData(queryKeys.aiCalls(), TYPED_AI_CALLS);
}

function LocationProbe() {
  const loc = useLocation();
  return (
    <span data-testid="router-location">
      {loc.pathname}
      {loc.hash}
    </span>
  );
}

function renderSettings(
  initialEntry = "/settings",
  queryClient: QueryClient = createAppQueryClient(),
) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Settings initialLicenses={SAMPLE_LICENSES} />
        <Link to="/settings#disclaimer">Footer disclaimer link</Link>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Settings", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("defaults to the Locations tab when the hash is empty or unknown, shows banners above the tabs, and navigates between tabs by keyboard and pointer without inline styles", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    seedAll(queryClient);
    queryClient.setQueryData(queryKeys.settings(), {
      ...TYPED_SETTINGS,
      file_modified_since_start: true,
      restart_keys: ["[ai] daily_cap_usd"],
      settings_file_problem:
        "weatherbot.toml has invalid TOML at line 4, column 1",
    });

    const { container } = renderSettings("/settings#unknown-tab", queryClient);

    expect(
      screen.getByRole("heading", { name: "Settings" }),
    ).toBeInTheDocument();

    // Both banners render above the tabs
    expect(
      screen.getByText(/Configuration file modified since monitor start/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText("weatherbot.toml has invalid TOML at line 4, column 1"),
    ).toBeInTheDocument();

    // Default tab is Locations
    const locationsTab = screen.getByRole("tab", { name: "Locations" });
    expect(locationsTab).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("heading", { name: "Watched Locations" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Notification Channels" }),
    ).toBeNull();

    // Keyboard navigation across the five tabs
    locationsTab.focus();
    await user.keyboard("{ArrowRight}");
    const notifTab = screen.getByRole("tab", {
      name: "Notifications & Quiet Hours",
    });
    expect(notifTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("router-location")).toHaveTextContent(
      "/settings#notifications",
    );
    expect(
      screen.getByRole("heading", { name: "Notification Channels" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Quiet Hours & Cooldown" }),
    ).toBeInTheDocument();

    await user.keyboard("{End}");
    const aboutTab = screen.getByRole("tab", {
      name: "Threat Ladder & About",
    });
    expect(aboutTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("router-location")).toHaveTextContent(
      "/settings#about",
    );
    expect(
      screen.getByRole("heading", { name: "Full Disclaimer" }),
    ).toBeInTheDocument();

    await user.keyboard("{Home}");
    expect(locationsTab).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("router-location")).toHaveTextContent(
      "/settings#locations",
    );
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("opens each hash directly (#notifications, #ai, #retention, #about, #disclaimer) and switches to About when a router link navigates to #disclaimer while open", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    seedAll(queryClient);

    const scrollSpy = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollSpy,
    });

    const { unmount } = renderSettings("/settings#retention", queryClient);
    expect(
      screen.getByRole("tab", { name: "History & Retention" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("heading", { name: "Database & Retention" }),
    ).toBeInTheDocument();
    unmount();

    const { container } = renderSettings("/settings#locations", queryClient);
    expect(
      screen.getByRole("tab", { name: "Locations" }),
    ).toHaveAttribute("aria-selected", "true");

    // Router navigation to /settings#disclaimer while already on /settings
    await user.click(
      screen.getByRole("link", { name: "Footer disclaimer link" }),
    );
    expect(
      screen.getByRole("tab", { name: "Threat Ladder & About" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("heading", { name: "Full Disclaimer" }),
    ).toBeInTheDocument();
    expect(scrollSpy).toHaveBeenCalled();
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("submits POST /api/notifications/test and flips the browser notification switch on the #notifications tab", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    seedAll(queryClient);

    const postSpy = vi.spyOn(apiClient, "POST").mockResolvedValue({
      data: TYPED_NOTIFICATIONS.notifications[0]!,
      response: new Response(null, { status: 200 }),
    });

    const { container } = renderSettings("/settings#notifications", queryClient);

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
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("shows the AI's state, credential source, models, today's meter, and four request rows on the #ai tab, and pauses, resumes, and allows more behind a confirmation", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    seedAll(queryClient);
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

    const { container } = renderSettings("/settings#ai", queryClient);

    const section = screen.getByRole("region", { name: "AI" });
    expect(section).toHaveAttribute("id", "ai");
    expect(within(section).getByText("Ready")).toBeInTheDocument();
    expect(
      within(section).getByText("the ANTHROPIC_API_KEY environment variable"),
    ).toBeInTheDocument();
    expect(
      within(section).getAllByText(/Claude Sonnet 5\.5/).length,
    ).toBeGreaterThan(0);

    const meter = within(section).getByRole("meter", {
      name: "Today's AI spend against today's limit",
    });
    expect(meter).toHaveAttribute("value", "44056");
    expect(meter).toHaveAttribute("max", "1000000");
    expect(
      within(section).getByText(
        /Spent \$0\.0441 · reserved \$0\.0000 · limit \$1\.00/,
      ),
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
    expect(dialog).toHaveTextContent(
      "Today's AI limit rises to $2.00 until midnight.",
    );
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
    expect(
      within(section).getByText("2 of 3 allowances left today"),
    ).toBeInTheDocument();
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

  it("disables the AI controls on the #ai tab when [ai] enabled is false", () => {
    const queryClient = createAppQueryClient();
    seedAll(queryClient);
    queryClient.setQueryData(
      queryKeys.ai(),
      aiStatus({ state: "off", reason: "disabled", credential_source: null }),
    );
    queryClient.setQueryData(queryKeys.aiCalls(), {
      ...TYPED_AI_CALLS,
      calls: [],
    });

    const { container } = renderSettings("/settings#ai", queryClient);

    const section = screen.getByRole("region", { name: "AI" });
    expect(within(section).getByTestId("ai-state-banner")).toHaveTextContent(
      "AI is off: [ai] enabled is false in weatherbot.toml.",
    );
    expect(
      within(section).getByRole("button", { name: "Pause AI" }),
    ).toBeDisabled();
    expect(
      within(section).getByRole("button", { name: "Allow $1.00 more today" }),
    ).toBeDisabled();
    expect(
      within(section).getByText("No AI request is recorded yet."),
    ).toBeInTheDocument();
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("renders the eleven ladder rules from ladder.json, effective settings with origins, the full disclaimer, and bundled dependency licences on the #about tab", () => {
    const queryClient = createAppQueryClient();
    seedAll(queryClient);

    const { container } = renderSettings("/settings#about", queryClient);

    const ladderSection = screen.getByRole("region", {
      name: /Alert Ladder/i,
    });
    for (const rule of TYPED_LADDER.rules) {
      const row = within(ladderSection).getByTestId(`ladder-rule-${rule.id}`);
      expect(row).toHaveTextContent(`${String(rule.order)}. ${rule.sentence}`);
      expect(row).toHaveTextContent(rule.id);
    }

    for (const ev of TYPED_LADDER.events) {
      expect(
        within(ladderSection).getAllByText(ev.event).length,
      ).toBeGreaterThan(0);
    }
    for (const item of TYPED_LADDER.codes) {
      expect(within(ladderSection).getByText(item.code)).toBeInTheDocument();
    }

    // Effective settings and origins
    expect(screen.getByText("[engine] coastal_reach_km")).toBeInTheDocument();
    expect(
      screen.getByText("WEATHERBOT_ENGINE_COASTAL_REACH_KM"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("default").length).toBeGreaterThan(0);

    // Full disclaimer and bundled licences
    expect(
      screen.getByRole("heading", { name: "Full Disclaimer" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/WEATHERBOT LEGAL DISCLAIMER/i),
    ).toBeInTheDocument();
    expect(screen.getByText("react")).toBeInTheDocument();
    expect(screen.getByText("radix-ui")).toBeInTheDocument();

    // Wrong rule name and non-ladder products never appear
    const retiredNames = [
      ["tropical_storm", "_cone"].join(""),
      ["Extreme ", "Wind Warning"].join(""),
      ["Storm Surge ", "Warning"].join(""),
      ["Storm Surge ", "Watch"].join(""),
    ];
    for (const retired of retiredNames) {
      expect(ladderSection.textContent ?? "").not.toContain(retired);
    }
    expect(container.querySelector("[style]")).toBeNull();
  });
});
