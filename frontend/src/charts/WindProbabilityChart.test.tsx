// frontend/src/charts/WindProbabilityChart.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  WIND_PROBABILITY_CAPTION,
  WindProbabilityChart,
  type WindReading,
} from "./WindProbabilityChart.tsx";

const MIXED_READINGS: readonly WindReading[] = [
  {
    threshold_kt: 34,
    synoptic_at: "2026-10-12T12:00:00Z",
    reading: "band",
    label: "20-30%",
    lower_pct: 20,
    upper_pct: 30,
  },
  {
    threshold_kt: 50,
    synoptic_at: "2026-10-12T12:00:00Z",
    reading: "below_every_band",
    label: null,
    lower_pct: null,
    upper_pct: null,
  },
  {
    threshold_kt: 64,
    synoptic_at: "2026-10-12T12:00:00Z",
    reading: "outside_coverage",
    label: null,
    lower_pct: null,
    upper_pct: null,
  },
];

describe("WindProbabilityChart", () => {
  it("renders 34/50/64 kt rows, band from lower_pct to upper_pct, <5% below the first gridline, outside_coverage blank with note, and required caption", () => {
    const { container } = render(
      <WindProbabilityChart
        location="Miami-Dade County Hall"
        readings={MIXED_READINGS}
      />,
    );

    expect(screen.getByTestId("wind-probability-caption")).toHaveTextContent(
      WIND_PROBABILITY_CAPTION,
    );
    expect(screen.getByTestId("wind-row-34")).toBeInTheDocument();
    expect(screen.getByTestId("wind-row-50")).toBeInTheDocument();
    expect(screen.getByTestId("wind-row-64")).toBeInTheDocument();

    // 34 kt band from 20% to 30%
    const band34 = screen.getByTestId("wind-band-34");
    expect(band34).toHaveTextContent("20-30%");

    // 50 kt <5% drawn below the 5% gridline
    const gridline50 = screen.getByTestId("wind-gridline-5pct-50");
    const gridY = Number(gridline50.getAttribute("y1"));
    const below50 = screen.getByTestId("wind-below-band-50");
    const belowRect = below50.querySelector("rect");
    expect(belowRect).not.toBeNull();
    expect(Number(belowRect?.getAttribute("y"))).toBeGreaterThanOrEqual(gridY);

    // 64 kt outside_coverage leaves axis blank and renders note
    expect(screen.queryByTestId("wind-band-64")).toBeNull();
    expect(screen.queryByTestId("wind-below-band-64")).toBeNull();
    expect(
      screen.getByTestId("wind-outside-coverage-note"),
    ).toHaveTextContent(/outside NHC wind-probability coverage/i);

    const rows = container.querySelectorAll("table.sr-only tbody tr");
    expect(rows.length).toBe(3);
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("renders an empty state when no wind readings are stored", () => {
    const { container } = render(
      <WindProbabilityChart location="Miami-Dade County Hall" readings={[]} />,
    );
    expect(screen.getByTestId("wind-probability-empty")).toBeInTheDocument();
    expect(container.querySelector("[style]")).toBeNull();
  });
});
