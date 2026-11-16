// frontend/src/pages/Dashboard.test.tsx
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import {
  STREAM_EVENT_DOM_NAME,
  type StreamEvent,
} from "../events/useEventStream.ts";
import { createAppQueryClient } from "../main.tsx";
import { TYPED_AI, TYPED_BRIEFINGS } from "../test/ai.ts";
import assessmentsFixture from "../test/fixtures/assessments.json";
import chartsFixture from "../test/fixtures/charts.json";
import disclaimerFixture from "../test/fixtures/disclaimer.json";
import healthFixture from "../test/fixtures/health.json";
import locationsFixture from "../test/fixtures/locations.json";
import mapFixture from "../test/fixtures/map.json";
import { Dashboard } from "./Dashboard.tsx";
import { asSchema, type JsonFixture } from "./format.ts";

const TYPED_ASSESSMENTS = asSchema<
  components["schemas"]["AssessmentsResponse"]
>(
  assessmentsFixture satisfies JsonFixture<
    components["schemas"]["AssessmentsResponse"]
  >,
);
const TYPED_CHARTS = asSchema<components["schemas"]["ChartsResponse"]>(
  chartsFixture satisfies JsonFixture<components["schemas"]["ChartsResponse"]>,
);
const TYPED_LOCATIONS = asSchema<components["schemas"]["LocationsResponse"]>(
  locationsFixture satisfies JsonFixture<
    components["schemas"]["LocationsResponse"]
  >,
);
const TYPED_HEALTH = asSchema<components["schemas"]["HealthResponse"]>(
  healthFixture satisfies JsonFixture<components["schemas"]["HealthResponse"]>,
);
const TYPED_DISCLAIMER = asSchema<components["schemas"]["DisclaimerResponse"]>(
  disclaimerFixture satisfies JsonFixture<
    components["schemas"]["DisclaimerResponse"]
  >,
);
const TYPED_MAP = asSchema<components["schemas"]["MapResponse"]>(
  mapFixture satisfies JsonFixture<components["schemas"]["MapResponse"]>,
);

function seedDashboardClient(): QueryClient {
  const queryClient = createAppQueryClient();
  queryClient.setQueryData(queryKeys.assessments(), TYPED_ASSESSMENTS);
  queryClient.setQueryData(
    queryKeys.charts("Miami-Dade County Hall"),
    TYPED_CHARTS,
  );
  queryClient.setQueryData(queryKeys.charts("Parliament Square"), {
    ...TYPED_CHARTS,
    location: "Parliament Square",
    levels: [TYPED_CHARTS.levels[0]!],
  });
  queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
  queryClient.setQueryData(queryKeys.health(), TYPED_HEALTH);
  queryClient.setQueryData(queryKeys.ai(), TYPED_AI);
  queryClient.setQueryData(queryKeys.briefings(), TYPED_BRIEFINGS);
  queryClient.setQueryData(queryKeys.disclaimer(), TYPED_DISCLAIMER);
  queryClient.setQueryData(queryKeys.map(), TYPED_MAP);
  return queryClient;
}

describe("Dashboard", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => false,
    });
  });

  it("renders the status bar, export popover, location switcher with one heading per name, featured location hero/tiles/briefing/disclosure, mini-map, and calls PUT /api/locations/evacuation", async () => {
    const user = userEvent.setup();
    const queryClient = seedDashboardClient();

    const putSpy = vi.spyOn(apiClient, "PUT").mockResolvedValue({
      data: TYPED_LOCATIONS.locations[0]!,
      response: new Response(null, { status: 200 }),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Dashboard" }),
    ).toBeInTheDocument();

    // One heading per location name in the switcher
    expect(
      screen.getAllByRole("heading", { name: "Miami-Dade County Hall" }),
    ).toHaveLength(1);
    expect(
      screen.getAllByRole("heading", { name: "Parliament Square" }),
    ).toHaveLength(1);

    const switcher = screen.getByTestId("location-switcher");
    expect(within(switcher).getAllByTestId("level-sparkline")).toHaveLength(2);
    expect(
      within(switcher).getByRole("link", { name: "Miami-Dade County Hall" }),
    ).toHaveAttribute("href", "#location-miami-dade-county-hall");

    // Featured location shows hero, stat tiles, arrival timeline, briefing, and disclosure
    const featured = screen.getByTestId("featured-location");
    const heroHeadline = within(featured).getByTestId("location-hero-headline");
    expect(heroHeadline).toHaveTextContent("Level 1 — All Clear");

    const tiles = within(featured).getByTestId("featured-stat-tiles");
    expect(
      within(tiles).getByRole("group", { name: "Closest approach" }),
    ).toHaveTextContent("2667.0");
    expect(
      within(tiles).getByRole("group", { name: "Storm bearing" }),
    ).toHaveTextContent("East");
    expect(tiles.querySelectorAll(".tabular-nums").length).toBeGreaterThan(0);

    expect(
      within(featured).getAllByTestId("arrival-timeline").length,
    ).toBeGreaterThan(0);

    const briefing = within(featured).getByRole("region", {
      name: "AI briefing for Miami-Dade County Hall",
    });
    expect(
      heroHeadline.compareDocumentPosition(briefing) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(within(briefing).getByTestId("ai-label")).toHaveTextContent(
      "AI briefing · Claude Sonnet 5.5",
    );

    const disclosure = within(featured).getByTestId("why-this-level");
    expect(disclosure).not.toHaveAttribute("open");
    expect(screen.getAllByText(/Rip Current Statement/).length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByText(
        /County-zone alerts outside this location's zones \(context only; never sets the level\)/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/2798\.0 km at 72 deg/i).length).toBeGreaterThan(
      0,
    );

    // Mini-map container is rendered inside the dashboard
    expect(screen.getByTestId("mini-map-container")).toBeInTheDocument();
    expect(screen.getByTestId("mini-map-caption")).toHaveTextContent(
      "1 active storm · Snapshot 4 min old",
    );

    // Evacuation toggle interaction
    const miamiSwitch = screen.getByRole("switch", {
      name: "Evacuation order for Miami-Dade County Hall",
    });
    expect(miamiSwitch).toHaveAttribute("aria-checked", "false");
    await user.click(miamiSwitch);
    expect(putSpy).toHaveBeenCalledWith("/api/locations/evacuation", {
      body: { location: "Miami-Dade County Hall", on: true },
    });

    // Switch featured location via switcher link
    await user.click(
      within(switcher).getByRole("link", { name: "Parliament Square" }),
    );
    expect(
      within(screen.getByTestId("featured-location")).getByRole("region", {
        name: "AI briefing for Parliament Square",
      }),
    ).toHaveTextContent("No briefing yet.");

    // Export popover contents and Include the AI briefing checkbox
    await user.click(screen.getByRole("button", { name: "Export report" }));
    expect(
      screen.getByText(
        /opens offline anywhere and prints to PDF from the browser/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /its words quote NWS alerts and can name a county or a forecast office/i,
      ),
    ).toBeInTheDocument();
    const briefingCheckbox = screen.getByRole("checkbox", {
      name: /Include the AI briefing/i,
    });
    expect(briefingCheckbox).not.toBeChecked();

    const exportAllLink = screen.getByTestId("export-report-all");
    const exportMiamiLink = screen.getByTestId(
      "export-report-Miami-Dade County Hall",
    );
    expect(exportAllLink).toHaveAttribute("href", "/api/report");
    expect(exportMiamiLink).toHaveAttribute(
      "href",
      "/api/report?location=Miami-Dade+County+Hall",
    );

    await user.click(briefingCheckbox);
    expect(briefingCheckbox).toBeChecked();
    expect(exportAllLink).toHaveAttribute("href", "/api/report?briefing=true");
    expect(exportMiamiLink).toHaveAttribute(
      "href",
      "/api/report?location=Miami-Dade+County+Hall&briefing=true",
    );
  });

  it("features the highest-level location by default or the hash's location when specified, and renders dashes on stat tiles when inputs are absent", () => {
    const queryClient = seedDashboardClient();
    const loc0 = TYPED_ASSESSMENTS.locations[0]!;
    const loc1 = TYPED_ASSESSMENTS.locations[1]!;
    const elevatedAssessments: components["schemas"]["AssessmentsResponse"] = {
      ...TYPED_ASSESSMENTS,
      locations: [
        {
          ...loc0,
          assessment: {
            ...loc0.assessment!,
            threats: [],
            wind_probabilities: [],
          },
        },
        {
          ...loc1,
          assessment: {
            ...loc1.assessment!,
            level: {
              number: 4,
              label: "Warning / Watch / Evacuation",
              actions: "Prepare now",
            },
            rule: "tropical_storm_warning",
            rule_trigger: "A Tropical Storm Warning covers the location.",
            threats: [],
            wind_probabilities: [],
          },
        },
      ],
    };
    queryClient.setQueryData(queryKeys.assessments(), elevatedAssessments);

    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/"]}>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Highest level (Parliament Square at Level 4) is featured by default
    expect(screen.getByTestId("featured-location-name")).toHaveTextContent(
      "Parliament Square",
    );
    expect(screen.getByTestId("location-hero-headline")).toHaveTextContent(
      "Level 4 — Warning / Watch / Evacuation",
    );

    const tiles = screen.getByTestId("featured-stat-tiles");
    expect(
      within(tiles).getByRole("group", { name: "Closest approach" }),
    ).toHaveTextContent("—");
    expect(
      within(tiles).getByRole("group", { name: "Storm bearing" }),
    ).toHaveTextContent("—");

    unmount();

    // Explicit URL hash overrides default level priority
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/#location-miami-dade-county-hall"]}>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("featured-location-name")).toHaveTextContent(
      "Miami-Dade County Hall",
    );
    expect(screen.getByTestId("location-hero-headline")).toHaveTextContent(
      "Level 1 — All Clear",
    );
  });

  it("updates the next-product countdown at minute boundaries and pauses while document.hidden is true", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-13T02:18:30Z"));

    const queryClient = seedDashboardClient();
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const countdown = screen.getByTestId("next-product-countdown");
    expect(countdown).toHaveTextContent("Next NHC product in 42 min");

    act(() => {
      vi.advanceTimersByTime(30_000);
    });
    expect(screen.getByTestId("next-product-countdown")).toHaveTextContent(
      "Next NHC product in 41 min",
    );

    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => true,
    });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
      vi.advanceTimersByTime(3 * 60_000);
    });
    expect(screen.getByTestId("next-product-countdown")).toHaveTextContent(
      "Next NHC product in 41 min",
    );

    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => false,
    });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(screen.getByTestId("next-product-countdown")).toHaveTextContent(
      "Next NHC product in 38 min",
    );
  });

  it("shows 'At least' with missing inputs when complete is false and escapes HTML in product and storm strings", () => {
    const queryClient = seedDashboardClient();
    const baseLoc = TYPED_ASSESSMENTS.locations[0]!;
    const incompleteAssessments: components["schemas"]["AssessmentsResponse"] =
      {
        ...TYPED_ASSESSMENTS,
        locations: [
          {
            ...baseLoc,
            name: "Miami <script>alert(1)</script>",
            assessment: {
              ...baseLoc.assessment!,
              complete: false,
              unavailable: [
                {
                  kind: "nws_alerts",
                  source_id: "nws-alerts-zone",
                  storm_name: "<img src=x onerror=alert(1)>",
                  threshold_kt: null,
                  reason: "source failed (unavailable)",
                },
              ],
            },
          },
        ],
      };

    queryClient.setQueryData(queryKeys.assessments(), incompleteAssessments);

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getAllByText(/At least Level 1/i).length).toBeGreaterThan(0);
    expect(screen.getByTestId("level-live-region")).toHaveTextContent(
      "Miami <script>alert(1)</script>: At least Level 1, All Clear. No other rule matches.",
    );
    expect(
      screen.getByText(
        /At least: the level is a floor because these inputs were unavailable:/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/nws-alerts-zone/)).toBeInTheDocument();
    expect(
      screen.getAllByText("Miami <script>alert(1)</script>").length,
    ).toBeGreaterThan(0);
    expect(container.querySelector("script")).toBeNull();
  });

  it("disables 'Check now' while a cycle it started is running until a cycle event arrives, and shows plain messages on 409 and 429", async () => {
    const user = userEvent.setup();
    const queryClient = seedDashboardClient();
    const postSpy = vi.spyOn(apiClient, "POST");

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const checkBtn = screen.getByRole("button", { name: /check now/i });

    postSpy.mockResolvedValueOnce({
      data: {
        status: "accepted",
        trigger: "manual",
        started_at: "2026-10-13T01:35:00Z",
        notice: TYPED_ASSESSMENTS.notice,
      },
      response: new Response(null, { status: 202 }),
    });

    await user.click(checkBtn);
    expect(checkBtn).toBeDisabled();
    expect(
      screen.getByText(/Monitor cycle started\. Waiting for cycle completion/i),
    ).toBeInTheDocument();

    act(() => {
      const cycleEvent: StreamEvent = {
        id: 99,
        kind: "cycle",
        at: "2026-10-13T01:35:00Z",
        invalidate: ["health"],
        started_at: null,
        cycle_id: 3,
        runner: "serve",
        trigger: "manual",
        status: "ok",
        snapshot_id: null,
        location: null,
        assessment_id: null,
        level: null,
        complete: null,
        notification_id: null,
        notification_kind: null,
        escalation: null,
        title: null,
        body: null,
        display: false,
        call_id: null,
        output_id: null,
        ai_kind: null,
      };
      window.dispatchEvent(
        new CustomEvent<StreamEvent>(STREAM_EVENT_DOM_NAME, {
          detail: cycleEvent,
        }),
      );
    });

    await waitFor(() => {
      expect(checkBtn).not.toBeDisabled();
    });

    postSpy.mockResolvedValueOnce({
      data: undefined,
      response: new Response(null, { status: 409 }),
    });
    await user.click(checkBtn);
    expect(checkBtn).not.toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Another monitor cycle is already running (/api/cycles returned HTTP 409).",
    );

    postSpy.mockResolvedValueOnce({
      data: undefined,
      response: new Response(null, { status: 429 }),
    });
    await user.click(checkBtn);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Please wait before starting another manual check (/api/cycles returned HTTP 429).",
    );
  });

  it("renders the empty, loading, and error states", async () => {
    const emptyClient = createAppQueryClient();
    emptyClient.setQueryData(queryKeys.assessments(), {
      ...TYPED_ASSESSMENTS,
      locations: [],
    });
    emptyClient.setQueryData(queryKeys.locations(), {
      ...TYPED_LOCATIONS,
      locations: [],
    });
    emptyClient.setQueryData(queryKeys.disclaimer(), TYPED_DISCLAIMER);

    const { unmount: unmountEmpty } = render(
      <QueryClientProvider client={emptyClient}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "No watched locations configured" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Weatherbot is informational only/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Add your first location in Settings/i }),
    ).toHaveAttribute("href", "/settings");
    unmountEmpty();

    // Loading state
    vi.spyOn(apiClient, "GET").mockImplementation(
      () => new Promise(() => undefined),
    );
    const loadingClient = createAppQueryClient();
    const { unmount: unmountLoading } = render(
      <QueryClientProvider client={loadingClient}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      screen.getByText("Loading threat assessments…"),
    ).toBeInTheDocument();
    unmountLoading();

    // Error state
    vi.spyOn(apiClient, "GET").mockRejectedValue(
      new ApiRequestError("/api/assessments", 503),
    );
    const errorClient = createAppQueryClient();
    errorClient.setDefaultOptions({
      queries: { retry: false },
    });
    render(
      <QueryClientProvider client={errorClient}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Request to /api/assessments failed (HTTP 503).",
    );
  });
});
