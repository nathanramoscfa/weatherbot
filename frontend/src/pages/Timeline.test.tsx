// frontend/src/pages/Timeline.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
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
});
