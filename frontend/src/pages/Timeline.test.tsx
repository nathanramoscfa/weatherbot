// frontend/src/pages/Timeline.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { TYPED_SUMMARIES } from "../test/ai.ts";
import notificationsFixture from "../test/fixtures/notifications.json";
import timelineFixture from "../test/fixtures/timeline.json";
import { asSchema, type JsonFixture } from "./format.ts";
import { Timeline } from "./Timeline.tsx";

const TYPED_TIMELINE = asSchema<components["schemas"]["TimelineResponse"]>(
  timelineFixture satisfies JsonFixture<
    components["schemas"]["TimelineResponse"]
  >,
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
      screen.queryByText(
        "Miami-Dade County Hall: level 4, Warning / Watch / Evacuation",
      ),
    ).not.toBeInTheDocument();
  });

  it("shows each change entry's stored summary, labeled, and a withheld summary's reason", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.timeline(), TYPED_TIMELINE);
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
});
