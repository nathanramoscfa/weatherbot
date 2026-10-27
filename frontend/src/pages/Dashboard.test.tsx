// frontend/src/pages/Dashboard.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import {
  STREAM_EVENT_DOM_NAME,
  type StreamEvent,
} from "../events/useEventStream.ts";
import { createAppQueryClient } from "../main.tsx";
import assessmentsFixture from "../test/fixtures/assessments.json";
import disclaimerFixture from "../test/fixtures/disclaimer.json";
import healthFixture from "../test/fixtures/health.json";
import locationsFixture from "../test/fixtures/locations.json";
import { Dashboard } from "./Dashboard.tsx";
import { asSchema, type JsonFixture } from "./format.ts";

const TYPED_ASSESSMENTS = asSchema<components["schemas"]["AssessmentsResponse"]>(
  assessmentsFixture satisfies JsonFixture<
    components["schemas"]["AssessmentsResponse"]
  >,
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

describe("Dashboard", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the level cards, county-zone context alerts, storm threats, and evacuation toggle from fixtures, and calls PUT /api/locations/evacuation", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.assessments(), TYPED_ASSESSMENTS);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.health(), TYPED_HEALTH);
    queryClient.setQueryData(queryKeys.disclaimer(), TYPED_DISCLAIMER);

    const putSpy = vi
      .spyOn(apiClient, "PUT")
      .mockResolvedValue({
        data: TYPED_LOCATIONS.locations[0]!,
        response: new Response(null, { status: 200 }),
      } as never);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("article", { name: "Miami-Dade County Hall" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("article", { name: "Parliament Square" }),
    ).toBeInTheDocument();

    // Covering alert and county-zone context alert
    expect(
      screen.getAllByText(/Rip Current Statement/).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(
        /County-zone alerts outside this location's zones \(context only; never sets the level\)/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/Coastal Flood Statement/).length,
    ).toBeGreaterThan(0);

    // Storm threat with 0.1 km distance and integer degree bearing
    expect(screen.getAllByText(/2798\.0 km at 72 deg/i).length).toBeGreaterThan(
      0,
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
  });

  it("shows 'At least' with missing inputs when complete is false and escapes HTML in product and storm strings", () => {
    const queryClient = createAppQueryClient();
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
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.health(), TYPED_HEALTH);

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getAllByText(/At least Level 1/i).length).toBeGreaterThan(0);
    expect(
      screen.getByTestId("level-live-region"),
    ).toHaveTextContent(
      "Miami <script>alert(1)</script>: At least Level 1, All Clear. Decided by all_clear.",
    );
    expect(
      screen.getByText(
        /At least: the level is a floor because these inputs were unavailable:/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/nws-alerts-zone/)).toBeInTheDocument();
    expect(
      screen.getByText("Miami <script>alert(1)</script>"),
    ).toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
  });

  it("disables 'Check now' while a cycle it started is running until a cycle event arrives, and shows plain messages on 409 and 429", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.assessments(), TYPED_ASSESSMENTS);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.health(), TYPED_HEALTH);

    const postSpy = vi.spyOn(apiClient, "POST");

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Dashboard />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const checkBtn = screen.getByRole("button", { name: /check now/i });

    // 1. 202 Accepted disables button until cycle StreamEvent arrives
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

    // 2. 409 Conflict shows plain message and re-enables button
    postSpy.mockResolvedValueOnce({
      data: undefined,
      response: new Response(null, { status: 409 }),
    });
    await user.click(checkBtn);
    expect(checkBtn).not.toBeDisabled();
    expect(
      screen.getByRole("alert"),
    ).toHaveTextContent(
      "Another monitor cycle is already running (/api/cycles returned HTTP 409).",
    );

    // 3. 429 Too Many Requests shows plain message
    postSpy.mockResolvedValueOnce({
      data: undefined,
      response: new Response(null, { status: 429 }),
    });
    await user.click(checkBtn);
    expect(
      screen.getByRole("alert"),
    ).toHaveTextContent(
      "Please wait before starting another manual check (/api/cycles returned HTTP 429).",
    );
  });

  it("renders the empty state with disclaimer essentials and a link to /settings when no locations are watched", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.assessments(), {
      ...TYPED_ASSESSMENTS,
      locations: [],
    });
    queryClient.setQueryData(queryKeys.locations(), {
      ...TYPED_LOCATIONS,
      locations: [],
    });
    queryClient.setQueryData(queryKeys.disclaimer(), TYPED_DISCLAIMER);

    render(
      <QueryClientProvider client={queryClient}>
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
    const settingsLink = screen.getByRole("link", {
      name: /Add your first location in Settings/i,
    });
    expect(settingsLink).toHaveAttribute("href", "/settings");
  });
});
