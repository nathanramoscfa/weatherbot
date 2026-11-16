// frontend/src/dashboard/FeaturedLocation.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import { TYPED_AI, TYPED_BRIEFINGS } from "../test/ai.ts";
import assessmentsFixture from "../test/fixtures/assessments.json";
import {
  compassWordsForDegrees,
  FeaturedLocation,
} from "./FeaturedLocation.tsx";

const TYPED_ASSESSMENTS = asSchema<
  components["schemas"]["AssessmentsResponse"]
>(
  assessmentsFixture satisfies JsonFixture<
    components["schemas"]["AssessmentsResponse"]
  >,
);

describe("FeaturedLocation", () => {
  it("renders stat tiles with tabular-nums, compass words, product captions, and dashes when inputs are absent", () => {
    expect(compassWordsForDegrees(0)).toEqual({ cardinal: "N", words: "North" });
    expect(compassWordsForDegrees(72)).toEqual({ cardinal: "E", words: "East" });
    expect(compassWordsForDegrees(225)).toEqual({
      cardinal: "SW",
      words: "Southwest",
    });

    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.ai(), TYPED_AI);
    queryClient.setQueryData(queryKeys.briefings(), TYPED_BRIEFINGS);

    const baseItem = TYPED_ASSESSMENTS.locations[0]!;
    const quietItem: components["schemas"]["LocationAssessmentResponse"] = {
      ...baseItem,
      assessment: {
        ...baseItem.assessment!,
        threats: [],
        wind_probabilities: [],
      },
    };

    const { container, rerender } = render(
      <QueryClientProvider client={queryClient}>
        <FeaturedLocation
          item={baseItem}
          ageSeconds={240}
          evacPending={false}
          onToggleEvacuation={() => undefined}
          provenanceChildren={<div>Provenance children</div>}
        />
      </QueryClientProvider>,
    );

    const tiles = screen.getByTestId("featured-stat-tiles");
    expect(
      within(tiles).getByRole("group", { name: "Closest approach" }),
    ).toHaveTextContent("2667.0");
    expect(
      within(tiles).getByRole("group", { name: "Storm bearing" }),
    ).toHaveTextContent("East");
    expect(
      within(tiles).getByRole("group", { name: "34-kt wind chance (120 h)" }),
    ).toHaveTextContent("<5%");
    expect(
      within(tiles).getByRole("group", { name: "Storms tracked" }),
    ).toHaveTextContent("1");
    expect(container.querySelectorAll(".tabular-nums").length).toBeGreaterThan(
      0,
    );
    expect(container.querySelector("[style]")).toBeNull();

    // Rerender with no active storm or wind probabilities -> dashes
    rerender(
      <QueryClientProvider client={queryClient}>
        <FeaturedLocation
          item={quietItem}
          ageSeconds={240}
          evacPending={false}
          onToggleEvacuation={() => undefined}
          provenanceChildren={<div>Provenance children</div>}
        />
      </QueryClientProvider>,
    );

    const emptyTiles = screen.getByTestId("featured-stat-tiles");
    expect(
      within(emptyTiles).getByRole("group", { name: "Closest approach" }),
    ).toHaveTextContent("—");
    expect(
      within(emptyTiles).getByRole("group", { name: "Storm bearing" }),
    ).toHaveTextContent("—");
    expect(
      within(emptyTiles).getByRole("group", { name: "34-kt wind chance (120 h)" }),
    ).toHaveTextContent("—");
    expect(
      within(emptyTiles).getByRole("group", { name: "64-kt wind chance (120 h)" }),
    ).toHaveTextContent("—");
  });
});
