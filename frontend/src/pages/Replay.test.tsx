// frontend/src/pages/Replay.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import type { MapResponse } from "../map/layers.ts";
import { getLeafletMapForContainer } from "../map/useLeafletMap.ts";
import healthFixture from "../test/fixtures/health.json";
import locationsFixture from "../test/fixtures/locations.json";
import replayFixture from "../test/fixtures/replay.json";
import replayAdvisoryFixture from "../test/fixtures/replay-advisory.json";
import replayAssessmentFixture from "../test/fixtures/replay-assessment.json";
import replayTimelineFixture from "../test/fixtures/replay-timeline.json";
import { asSchema, type JsonFixture } from "./format.ts";
import { Replay } from "./Replay.tsx";

const TYPED_HEALTH = asSchema<components["schemas"]["HealthResponse"]>(
  healthFixture satisfies JsonFixture<components["schemas"]["HealthResponse"]>,
);
const TYPED_LOCATIONS = asSchema<components["schemas"]["LocationsResponse"]>(
  locationsFixture satisfies JsonFixture<
    components["schemas"]["LocationsResponse"]
  >,
);
const TYPED_REPLAY = asSchema<components["schemas"]["ReplayStormsResponse"]>(
  replayFixture satisfies JsonFixture<
    components["schemas"]["ReplayStormsResponse"]
  >,
);
const TYPED_REPLAY_ADVISORY = asSchema<MapResponse>(
  replayAdvisoryFixture satisfies JsonFixture<MapResponse>,
);
const TYPED_REPLAY_TIMELINE = asSchema<
  components["schemas"]["ReplayTimelineResponse"]
>(
  replayTimelineFixture satisfies JsonFixture<
    components["schemas"]["ReplayTimelineResponse"]
  >,
);
const TYPED_REPLAY_ASSESSMENT = asSchema<
  components["schemas"]["ReplayAssessmentResponse"]
>(
  replayAssessmentFixture satisfies JsonFixture<
    components["schemas"]["ReplayAssessmentResponse"]
  >,
);

function buildShortTimeline(): components["schemas"]["ReplayTimelineResponse"] {
  const step0 = TYPED_REPLAY_TIMELINE.steps.find(
    (s) => s.advisory_id === "001",
  )!;
  const step24 = TYPED_REPLAY_TIMELINE.steps.find(
    (s) => s.advisory_id === "024",
  )!;
  const step26 = TYPED_REPLAY_TIMELINE.steps.find(
    (s) => s.advisory_id === "026",
  )!;
  return {
    ...TYPED_REPLAY_TIMELINE,
    notes: [
      ...TYPED_REPLAY_TIMELINE.notes,
      "The stored evacuation-order toggle of 'Parliament Square' is on; the replay assesses with it off, because the toggle is a present-day input.",
    ],
    steps: [step0, step24, step26],
  };
}

function buildStepAssessment(
  step: components["schemas"]["ReplayTimelineStepResponse"],
): components["schemas"]["ReplayAssessmentResponse"] {
  return {
    ...TYPED_REPLAY_ASSESSMENT,
    advisory_id: step.advisory_id,
    advisory: step.advisory,
    as_of: step.issued_at,
    level: step.level,
    rule: step.rule,
    rule_trigger: step.rule_trigger,
    complete: step.complete,
    changes: step.changes,
  };
}

describe("Replay page", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("shows corpus configuration guidance when health.corpus is false", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.health(), {
      ...TYPED_HEALTH,
      corpus: false,
    });
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Replay />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const disabledBox = screen.getByTestId("replay-corpus-disabled");
    expect(disabledBox).toHaveTextContent("[web] corpus");
    expect(disabledBox).toHaveTextContent("tests/fixtures/replay");
    expect(disabledBox).toHaveTextContent("convert --full");
    expect(screen.queryByTestId("replay-banner")).toBeNull();
  });

  it("explains when no watched locations are stored", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.health(), {
      ...TYPED_HEALTH,
      corpus: true,
    });
    queryClient.setQueryData(queryKeys.locations(), {
      ...TYPED_LOCATIONS,
      locations: [],
    });
    queryClient.setQueryData(queryKeys.replay(), TYPED_REPLAY);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Replay />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("replay-no-locations")).toHaveTextContent(
      /No watched locations stored/i,
    );
  });

  it("renders storm and location pickers, scrubber, banner, notes, assessment card without AI or evacuation switch", () => {
    const queryClient = createAppQueryClient();
    const shortTimeline = buildShortTimeline();
    queryClient.setQueryData(queryKeys.health(), {
      ...TYPED_HEALTH,
      corpus: true,
    });
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.replay(), TYPED_REPLAY);
    queryClient.setQueryData(
      queryKeys.replayTimeline("AL052019", "Parliament Square"),
      shortTimeline,
    );
    queryClient.setQueryData(
      queryKeys.replayTimeline("AL052019", "Miami-Dade County Hall"),
      {
        ...shortTimeline,
        location: "Miami-Dade County Hall",
      },
    );
    queryClient.setQueryData(
      queryKeys.replayTimeline("AL112017", "Parliament Square"),
      {
        ...shortTimeline,
        atcf_id: "AL112017",
        name: "Irma",
      },
    );

    for (const step of shortTimeline.steps) {
      queryClient.setQueryData(
        queryKeys.replayAdvisory("AL052019", step.advisory_id),
        TYPED_REPLAY_ADVISORY,
      );
      queryClient.setQueryData(
        queryKeys.replayAdvisory("AL112017", step.advisory_id),
        TYPED_REPLAY_ADVISORY,
      );
      queryClient.setQueryData(
        queryKeys.replayAssessment(
          "AL052019",
          step.advisory_id,
          "Parliament Square",
        ),
        step.advisory_id === "026"
          ? TYPED_REPLAY_ASSESSMENT
          : buildStepAssessment(step),
      );
      queryClient.setQueryData(
        queryKeys.replayAssessment(
          "AL052019",
          step.advisory_id,
          "Miami-Dade County Hall",
        ),
        {
          ...buildStepAssessment(step),
          location: "Miami-Dade County Hall",
        },
      );
      queryClient.setQueryData(
        queryKeys.replayAssessment(
          "AL112017",
          step.advisory_id,
          "Parliament Square",
        ),
        {
          ...buildStepAssessment(step),
          atcf_id: "AL112017",
          name: "Irma",
        },
      );
    }

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Replay />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Non-dismissible banner at initial step (advisory 1)
    const banner = screen.getByTestId("replay-banner");
    expect(banner).toHaveTextContent(
      /Replay: Dorian advisory 1, issued .* — not live/i,
    );
    expect(within(banner).queryByRole("button")).toBeNull();

    // Notes block
    const notes = screen.getByTestId("replay-notes");
    expect(notes).toHaveTextContent(/Replayed assessments lack/i);
    expect(notes).toHaveTextContent(/evacuation-order toggle/i);

    // Active marker on LevelHistoryChart
    expect(
      screen.getByTestId("level-history-active-marker"),
    ).toBeInTheDocument();

    // Scrub slider to step index 1 (024 -> Level 4) then index 2 (026 -> Level 5 with HWR)
    const slider = screen.getByRole("slider", { name: /Advisory history/i });
    fireEvent.change(slider, { target: { value: "1" } });
    fireEvent.mouseUp(slider);
    expect(screen.getByTestId("replay-banner")).toHaveTextContent(
      /Replay: Dorian advisory 24, issued .* — not live/i,
    );
    const card = screen.getByTestId("replay-assessment-card");
    expect(within(card).getAllByText(/Level 4/).length).toBeGreaterThan(0);

    fireEvent.change(slider, { target: { value: "2" } });
    fireEvent.mouseUp(slider);
    expect(screen.getByTestId("replay-banner")).toHaveTextContent(
      /Replay: Dorian advisory 26, issued .* — not live/i,
    );
    expect(within(card).getAllByText(/Level 5/).length).toBeGreaterThan(0);
    expect(
      within(card).getAllByText(/hurricane_warning/).length,
    ).toBeGreaterThan(0);
    expect(within(card).getAllByText(/HWR/).length).toBeGreaterThan(0);

    // No AI panel and no evacuation switch anywhere on the Replay page
    expect(screen.queryByTestId("ai-label")).toBeNull();
    expect(screen.queryByRole("switch")).toBeNull();

    // Location picker switches location
    const locationSelect = screen.getByLabelText("Replay location");
    fireEvent.change(locationSelect, {
      target: { value: "Miami-Dade County Hall" },
    });
    expect(
      within(screen.getByTestId("replay-assessment-card")).getByRole(
        "heading",
        { name: "Miami-Dade County Hall" },
      ),
    ).toBeInTheDocument();

    // Storm picker switches storm and resets to first advisory
    fireEvent.change(locationSelect, {
      target: { value: "Parliament Square" },
    });
    const stormSelect = screen.getByLabelText("Replay storm");
    fireEvent.change(stormSelect, { target: { value: "AL112017" } });
    expect(screen.getByTestId("replay-banner")).toHaveTextContent(
      /Replay: Irma advisory 1, issued .* — not live/i,
    );
  });

  it("advances one step every 1.5s on Play and stops at the end, on user input, and on visibilitychange to hidden", () => {
    vi.useFakeTimers();
    const setIntervalSpy = vi.spyOn(window, "setInterval");
    const clearIntervalSpy = vi.spyOn(window, "clearInterval");

    const queryClient = createAppQueryClient();
    const shortTimeline = buildShortTimeline();
    queryClient.setQueryData(queryKeys.health(), {
      ...TYPED_HEALTH,
      corpus: true,
    });
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.replay(), TYPED_REPLAY);
    queryClient.setQueryData(
      queryKeys.replayTimeline("AL052019", "Parliament Square"),
      shortTimeline,
    );
    for (const step of shortTimeline.steps) {
      queryClient.setQueryData(
        queryKeys.replayAdvisory("AL052019", step.advisory_id),
        TYPED_REPLAY_ADVISORY,
      );
      queryClient.setQueryData(
        queryKeys.replayAssessment(
          "AL052019",
          step.advisory_id,
          "Parliament Square",
        ),
        buildStepAssessment(step),
      );
    }

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <Replay />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // No timer before Play is clicked
    expect(setIntervalSpy).not.toHaveBeenCalled();

    const playButton = screen.getByRole("button", { name: "Play" });
    fireEvent.click(playButton);
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();

    // Advance 1.5s -> moves from step 0 (adv 1) to step 1 (adv 24)
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.getByTestId("replay-banner")).toHaveTextContent(
      /Replay: Dorian advisory 24/i,
    );

    // Advance another 1.5s -> moves to step 2 (adv 26, last step) and stops automatically
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.getByTestId("replay-banner")).toHaveTextContent(
      /Replay: Dorian advisory 26/i,
    );
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(clearIntervalSpy).toHaveBeenCalled();

    // Clicking Play at the end restarts from step 0, and user input stops playback
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(screen.getByTestId("replay-banner")).toHaveTextContent(
      /Replay: Dorian advisory 1/i,
    );
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();

    // Start Play again and verify visibilitychange to "hidden" stops playback
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible",
    });
  });

  it("invalidates Leaflet map size and fits bounds when the replay map container transitions from hidden (0x0) to visible", () => {
    let resizeCallback: ResizeObserverCallback | null = null;
    const OriginalResizeObserver = globalThis.ResizeObserver;
    class MockResizeObserver {
      constructor(cb: ResizeObserverCallback) {
        resizeCallback = cb;
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal("ResizeObserver", MockResizeObserver);

    try {
      const queryClient = createAppQueryClient();
      const shortTimeline = buildShortTimeline();
      queryClient.setQueryData(queryKeys.health(), {
        ...TYPED_HEALTH,
        corpus: true,
      });
      queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
      queryClient.setQueryData(queryKeys.replay(), TYPED_REPLAY);

      // Render while timeline is not yet resolved so the map wrapper is hidden (0x0)
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <Replay />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      const mapContainer = screen.getByTestId("replay-leaflet-map");
      const leafletMap = getLeafletMapForContainer(mapContainer);
      expect(leafletMap).not.toBeNull();
      const invalidateSpy = vi.spyOn(leafletMap!, "invalidateSize");

      // Populate timeline and advisory data and simulate container becoming visible
      Object.defineProperty(mapContainer, "clientWidth", {
        configurable: true,
        get: () => 580,
      });
      Object.defineProperty(mapContainer, "clientHeight", {
        configurable: true,
        get: () => 384,
      });

      act(() => {
        queryClient.setQueryData(
          queryKeys.replayTimeline("AL052019", "Parliament Square"),
          shortTimeline,
        );
        for (const step of shortTimeline.steps) {
          queryClient.setQueryData(
            queryKeys.replayAdvisory("AL052019", step.advisory_id),
            TYPED_REPLAY_ADVISORY,
          );
          queryClient.setQueryData(
            queryKeys.replayAssessment(
              "AL052019",
              step.advisory_id,
              "Parliament Square",
            ),
            buildStepAssessment(step),
          );
        }
        resizeCallback?.([], {} as ResizeObserver);
      });

      expect(invalidateSpy).toHaveBeenCalledWith({ animate: false });
    } finally {
      if (OriginalResizeObserver) {
        vi.stubGlobal("ResizeObserver", OriginalResizeObserver);
      } else {
        vi.unstubAllGlobals();
      }
    }
  });
});
