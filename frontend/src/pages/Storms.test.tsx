// frontend/src/pages/Storms.test.tsx
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import {
  controlledStream,
  mockGet,
  narrationEvent,
  sseFrame,
  streamAnswer,
  TYPED_AI,
  TYPED_NARRATIONS,
  TYPED_OUTLOOK,
} from "../test/ai.ts";
import stormsFixture from "../test/fixtures/storms.json";
import { asSchema, type JsonFixture } from "./format.ts";
import { Storms } from "./Storms.tsx";

const TYPED_STORMS = asSchema<components["schemas"]["StormsResponse"]>(
  stormsFixture satisfies JsonFixture<components["schemas"]["StormsResponse"]>,
);

function seeded(narrationEnabled: boolean): QueryClient {
  const queryClient = createAppQueryClient();
  queryClient.setQueryData(queryKeys.storms(), TYPED_STORMS);
  queryClient.setQueryData(queryKeys.outlook(), TYPED_OUTLOOK);
  queryClient.setQueryData(queryKeys.aiNarrations(TYPED_OUTLOOK.snapshot_id), {
    ...TYPED_NARRATIONS,
    enabled: narrationEnabled,
    narrations: narrationEnabled ? TYPED_NARRATIONS.narrations : [],
  });
  queryClient.setQueryData(queryKeys.ai(), {
    ...TYPED_AI,
    features: { ...TYPED_AI.features, outlook_narration: narrationEnabled },
  });
  return queryClient;
}

describe("Storms", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders active storms, outlook areas, and wind-speed probabilities from storms.json", () => {
    const queryClient = seeded(false);

    render(
      <QueryClientProvider client={queryClient}>
        <Storms />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Storms" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("article", { name: "Simon (EP202026)" }),
    ).toBeInTheDocument();
    expect(screen.getByText("85 kt")).toBeInTheDocument();
    expect(screen.getByText("969 mb")).toBeInTheDocument();
    expect(screen.getByText("300 deg at 3 mph")).toBeInTheDocument();
    expect(
      screen.getByText(/earliest reasonable arrival times/i),
    ).toBeInTheDocument();

    // Outlook areas
    expect(screen.getAllByText("Atlantic").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pacific").length).toBeGreaterThan(0);

    // Wind probabilities
    expect(screen.getByText("34 kt threshold")).toBeInTheDocument();
    expect(screen.getByText("50 kt threshold")).toBeInTheDocument();
    expect(screen.getByText("64 kt threshold")).toBeInTheDocument();
  });

  it("renders the quiet-tropics empty state when no active storms are present", () => {
    const queryClient = seeded(false);
    queryClient.setQueryData(queryKeys.storms(), {
      ...TYPED_STORMS,
      storms: [],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Storms />
      </QueryClientProvider>,
    );

    expect(
      screen.getByText(/No active storm in the latest NHC roster/i),
    ).toBeInTheDocument();
  });

  it("shows the six official outlook graphics, credited to the National Hurricane Center, and no AI with narration off", () => {
    render(
      <QueryClientProvider client={seeded(false)}>
        <Storms />
      </QueryClientProvider>,
    );

    const outlook = screen.getByRole("region", {
      name: "Graphical Tropical Weather Outlook",
    });
    const images = within(outlook).getAllByRole("img");
    expect(images.map((image) => image.getAttribute("src"))).toEqual([
      "/api/outlook/atl/2d0",
      "/api/outlook/atl/7d0",
      "/api/outlook/pac/2d0",
      "/api/outlook/pac/7d0",
      "/api/outlook/cpac/2d0",
      "/api/outlook/cpac/7d0",
    ]);
    expect(
      within(outlook).getByAltText(
        "National Hurricane Center official seven-day graphical tropical weather outlook for the Atlantic",
      ),
    ).toHaveAttribute("width", "900");
    expect(
      within(outlook).getByAltText(
        "National Hurricane Center official two-day graphical tropical weather outlook for the Central Pacific",
      ),
    ).toBeInTheDocument();
    expect(
      within(outlook).getAllByText(/Official graphic: National Hurricane Center/),
    ).toHaveLength(6);
    expect(within(outlook).queryByRole("button", { name: /Interpret \(AI\)/ })).toBeNull();
    expect(within(outlook).queryByTestId("ai-label")).toBeNull();
  });

  it("shows each stored narration labeled beneath its graphic and streams a new one with narration on", async () => {
    const user = userEvent.setup();
    const sse = controlledStream();
    const postSpy = vi
      .spyOn(apiClient, "POST")
      .mockResolvedValue(streamAnswer(sse.stream));
    mockGet(
      new Map<string, unknown>([
        ["/api/ai/narrations", TYPED_NARRATIONS],
        ["/api/ai", TYPED_AI],
      ]),
    );
    render(
      <QueryClientProvider client={seeded(true)}>
        <Storms />
      </QueryClientProvider>,
    );

    const stored = screen.getByRole("region", {
      name: "AI interpretation of the official graphic: Atlantic seven-day",
    });
    expect(within(stored).getByTestId("ai-label")).toHaveTextContent(
      "AI interpretation of the official graphic · Claude Sonnet 5.5",
    );
    expect(
      within(stored).getByText(/^The seven-day outlook for the Atlantic/),
    ).toBeInTheDocument();
    expect(within(stored).getByText(/chance: 20%/)).toBeInTheDocument();
    expect(
      within(stored).getByRole("link", { name: /official page/ }),
    ).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getAllByRole("button", { name: /^Interpret \(AI\)/ })).toHaveLength(5);

    const twoDay = screen.getByRole("region", {
      name: "AI interpretation of the official graphic: Atlantic two-day",
    });
    await user.click(within(twoDay).getByRole("button", { name: /Interpret \(AI\)/ }));
    expect(postSpy).toHaveBeenCalledWith(
      "/api/ai/narrations",
      expect.objectContaining({ body: { basin: "atl", horizon: "2d0" } }),
    );
    for (const button of screen.getAllByRole("button", { name: /^Interpret \(AI\)/ })) {
      expect(button).toBeDisabled();
    }

    act(() => {
      sse.push(
        sseFrame(
          narrationEvent({
            kind: "started",
            model: "claude-sonnet-5-5",
            model_name: "Claude Sonnet 5.5",
            basin: "atl",
            horizon: "2d0",
          }),
        ),
      );
    });
    expect(
      await within(twoDay).findByText("Interpreting the graphic…"),
    ).toBeInTheDocument();

    act(() => {
      sse.push(
        sseFrame(
          narrationEvent({
            kind: "done",
            output_id: 11,
            created_at: "2026-10-13T01:45:00Z",
            reused: false,
            summary: "The two-day outlook marks no area.",
            areas: [],
            caveat: "The official graphic governs.",
          }),
        ),
      );
      sse.close();
    });
    expect(
      await within(twoDay).findByText("The two-day outlook marks no area."),
    ).toBeInTheDocument();
    expect(within(twoDay).getByTestId("ai-label")).toHaveTextContent(
      "AI interpretation of the official graphic · Claude Sonnet 5.5 · written 2026-10-13 01:45 UTC",
    );
    expect(within(twoDay).queryByText("Interpreting the graphic…")).toBeNull();
  });
});
