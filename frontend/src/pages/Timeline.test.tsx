// frontend/src/pages/Timeline.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { TYPED_SUMMARIES } from "../test/ai.ts";
import chartsFixture from "../test/fixtures/charts.json";
import notificationsFixture from "../test/fixtures/notifications.json";
import timelineFixture from "../test/fixtures/timeline.json";
import { asSchema, type JsonFixture } from "./format.ts";
import { Timeline } from "./Timeline.tsx";

const TYPED_TIMELINE = asSchema<components["schemas"]["TimelineResponse"]>(
  timelineFixture satisfies JsonFixture<
    components["schemas"]["TimelineResponse"]
  >,
);
const TYPED_CHARTS = asSchema<components["schemas"]["ChartsResponse"]>(
  chartsFixture satisfies JsonFixture<components["schemas"]["ChartsResponse"]>,
);
const TYPED_NOTIFICATIONS = asSchema<
  components["schemas"]["NotificationsResponse"]
>(
  notificationsFixture satisfies JsonFixture<
    components["schemas"]["NotificationsResponse"]
  >,
);

describe("Timeline", () => {
  it("renders assessments and notifications from timeline.json and notifications.json, and filters by location", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.timeline(), TYPED_TIMELINE);
    queryClient.setQueryData(
      queryKeys.charts("Miami-Dade County Hall"),
      TYPED_CHARTS,
    );
    queryClient.setQueryData(queryKeys.charts("Parliament Square"), {
      ...TYPED_CHARTS,
      location: "Parliament Square",
      levels: [TYPED_CHARTS.levels[0]!],
    });
    queryClient.setQueryData(queryKeys.notifications(), TYPED_NOTIFICATIONS);
    queryClient.setQueryData(queryKeys.aiSummaries(), {
      ...TYPED_SUMMARIES,
      summaries: [],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Timeline />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Timeline" }),
    ).toBeInTheDocument();

    // Shows both landmarks and the test notification initially
    expect(
      screen.getAllByText("Miami-Dade County Hall").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("Parliament Square").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Weatherbot test notification").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByText(
        "Miami-Dade County Hall: level 4, Warning / Watch / Evacuation",
      ).length,
    ).toBeGreaterThan(0);

    // Filter by Parliament Square
    const filterSelect = screen.getByLabelText("Filter by location");
    await user.selectOptions(filterSelect, "Parliament Square");

    expect(screen.getAllByText("Parliament Square").length).toBeGreaterThan(0);
    expect(
      screen.getByTestId("timeline-location-charts"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("level-history-chart")).toBeInTheDocument();
    expect(screen.getByTestId("wind-probability-chart")).toBeInTheDocument();
    expect(
      screen.queryByText(
        "Miami-Dade County Hall: level 4, Warning / Watch / Evacuation",
      ),
    ).not.toBeInTheDocument();
  });

  it("pages older entries through next_before when Show older is clicked", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    const firstEntry = TYPED_TIMELINE.entries[0]!;
    const secondEntry = TYPED_TIMELINE.entries[1]!;

    queryClient.setQueryData(queryKeys.timeline(), {
      ...TYPED_TIMELINE,
      entries: [firstEntry],
      next_before: "2026-10-13T01:31:00Z|assessment|3",
    });
    queryClient.setQueryData(queryKeys.notifications(), TYPED_NOTIFICATIONS);
    queryClient.setQueryData(queryKeys.aiSummaries(), {
      ...TYPED_SUMMARIES,
      summaries: [],
    });

    const getSpy = vi.spyOn(apiClient, "GET").mockResolvedValue({
      data: {
        ...TYPED_TIMELINE,
        entries: [secondEntry],
        next_before: null,
      },
      response: new Response(null, { status: 200 }),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Timeline />
      </QueryClientProvider>,
    );

    const showOlderBtn = screen.getByTestId("timeline-show-older");
    expect(showOlderBtn).toBeInTheDocument();
    await user.click(showOlderBtn);

    expect(getSpy).toHaveBeenCalledWith("/api/timeline", {
      params: {
        query: { before: "2026-10-13T01:31:00Z|assessment|3" },
      },
    });
    expect(screen.queryByTestId("timeline-show-older")).toBeNull();
    getSpy.mockRestore();
  });

  it("shows each change entry's stored summary, labeled, and a withheld summary's reason", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.timeline(), TYPED_TIMELINE);
    queryClient.setQueryData(
      queryKeys.charts("Miami-Dade County Hall"),
      TYPED_CHARTS,
    );
    queryClient.setQueryData(queryKeys.charts("Parliament Square"), {
      ...TYPED_CHARTS,
      location: "Parliament Square",
      levels: [TYPED_CHARTS.levels[0]!],
    });
    queryClient.setQueryData(queryKeys.notifications(), TYPED_NOTIFICATIONS);
    const summary = TYPED_SUMMARIES.summaries[0]!;
    queryClient.setQueryData(queryKeys.aiSummaries(), {
      ...TYPED_SUMMARIES,
      summaries: [
        summary,
        {
          ...summary,
          id: 7,
          assessment_id: 2,
          location: "Parliament Square",
          status: "withheld",
          withheld_reason: "url",
          summary: null,
        },
      ],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Timeline />
      </QueryClientProvider>,
    );

    const changed = screen.getByRole("article", {
      name: "Assessment 3 for Miami-Dade County Hall",
    });
    const block = within(changed).getByRole("region", {
      name: "AI summary of assessment 3",
    });
    expect(within(block).getByTestId("ai-label")).toHaveTextContent(
      "AI summary of what changed · Claude Sonnet 5.5 · written 2026-10-13 01:33 UTC",
    );
    expect(
      within(block).getByText(
        "The evacuation order for Miami-Dade County Hall was lifted, so the official level is no longer driven by it.",
      ),
    ).toBeInTheDocument();
    expect(
      within(changed).getByText(/The level fell from 4/),
    ).toBeInTheDocument();

    const withheld = screen.getByRole("article", {
      name: "Assessment 2 for Parliament Square",
    });
    expect(within(withheld).getByText("Withheld: it carried a URL")).toBeInTheDocument();

    expect(
      within(
        screen.getByRole("article", { name: "Assessment 1 for Miami-Dade County Hall" }),
      ).queryByTestId("ai-label"),
    ).toBeNull();
  });

  it("renders a muted delivery chip with its detail on the notification log", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.timeline(), TYPED_TIMELINE);
    const baseNotif = TYPED_NOTIFICATIONS.notifications[0]!;
    queryClient.setQueryData(queryKeys.notifications(), {
      ...TYPED_NOTIFICATIONS,
      notifications: [
        {
          ...baseNotif,
          deliveries: [
            ...baseNotif.deliveries,
            {
              id: 99,
              channel: "ntfy",
              attempted_at: "2026-10-13T01:30:05Z",
              result: "muted",
              detail: "below this location's phone level",
            },
          ],
        },
      ],
    });
    queryClient.setQueryData(queryKeys.aiSummaries(), {
      ...TYPED_SUMMARIES,
      summaries: [],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Timeline />
      </QueryClientProvider>,
    );

    const mutedChip = screen.getByText(/below this location's phone level/);
    expect(mutedChip).toHaveAttribute("data-delivery-result", "muted");
  });
});
