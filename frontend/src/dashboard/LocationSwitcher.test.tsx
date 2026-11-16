// frontend/src/dashboard/LocationSwitcher.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import assessmentsFixture from "../test/fixtures/assessments.json";
import chartsFixture from "../test/fixtures/charts.json";
import {
  LocationSwitcher,
  selectFeaturedLocation,
} from "./LocationSwitcher.tsx";

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

describe("LocationSwitcher", () => {
  it("selects the hash match first, then highest threat level, then list order, and renders one heading and sparkline per location", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(
      queryKeys.charts("Miami-Dade County Hall"),
      TYPED_CHARTS,
    );
    queryClient.setQueryData(queryKeys.charts("Parliament Square"), {
      ...TYPED_CHARTS,
      location: "Parliament Square",
      levels: [TYPED_CHARTS.levels[0]!],
    });

    const loc0 = TYPED_ASSESSMENTS.locations[0]!;
    const loc1 = TYPED_ASSESSMENTS.locations[1]!;
    const elevatedSecond = {
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
      },
    };
    const list = [loc0, elevatedSecond];

    expect(selectFeaturedLocation(list, "")?.name).toBe("Parliament Square");
    expect(
      selectFeaturedLocation(list, "#location-miami-dade-county-hall")?.name,
    ).toBe("Miami-Dade County Hall");

    const onSelect = vi.fn();
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <LocationSwitcher
          locations={list}
          featuredName="Parliament Square"
          ageSeconds={240}
          onSelectLocation={onSelect}
        />
      </QueryClientProvider>,
    );

    expect(
      screen.getAllByRole("heading", { name: "Miami-Dade County Hall" }),
    ).toHaveLength(1);
    expect(
      screen.getAllByRole("heading", { name: "Parliament Square" }),
    ).toHaveLength(1);

    const nassauArticle = screen.getByRole("article", {
      name: "Parliament Square",
    });
    expect(nassauArticle).toHaveTextContent("Outside NWS coverage");
    expect(
      within(nassauArticle).getByRole("link", { name: "Parliament Square" }),
    ).toHaveAttribute("aria-current", "true");

    const miamiLink = screen.getByRole("link", {
      name: "Miami-Dade County Hall",
    });
    expect(miamiLink).toHaveAttribute(
      "href",
      "#location-miami-dade-county-hall",
    );
    await user.click(miamiLink);
    expect(onSelect).toHaveBeenCalledWith("location-miami-dade-county-hall");
    expect(screen.getAllByTestId("level-sparkline")).toHaveLength(2);
    expect(container.querySelector("[style]")).toBeNull();
  });
});
