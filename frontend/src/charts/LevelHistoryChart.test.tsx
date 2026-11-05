// frontend/src/charts/LevelHistoryChart.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LevelHistoryChart } from "./LevelHistoryChart.tsx";
import type { ChartLevelPoint } from "./LevelSparkline.tsx";

const HISTORY_POINTS: readonly ChartLevelPoint[] = [
  {
    id: 3,
    as_of: "2026-10-13T06:00:00Z",
    as_of_local: "2026-10-13T02:00:00-04:00",
    level: 1,
    label: "All Clear",
    rule: "all_clear",
    complete: true,
  },
  {
    id: 2,
    as_of: "2026-10-13T03:00:00Z",
    as_of_local: "2026-10-12T23:00:00-04:00",
    level: 4,
    label: "Warning / Watch / Evacuation",
    rule: "evacuation_order",
    complete: true,
  },
  {
    id: 1,
    as_of: "2026-10-13T00:00:00Z",
    as_of_local: "2026-10-12T20:00:00-04:00",
    level: 2,
    label: "Awareness",
    rule: "basin_activity",
    complete: true,
  },
];

describe("LevelHistoryChart", () => {
  it("renders labelled axes, stepped path, change markers, sr-only table, and no style attribute", () => {
    const { container } = render(
      <LevelHistoryChart
        location="Miami-Dade County Hall"
        timeZone="America/New_York"
        points={HISTORY_POINTS}
      />,
    );

    const svg = screen.getByRole("img", {
      name: /Threat level history for Miami-Dade County Hall: 3 assessments/i,
    });
    expect(svg).toBeInTheDocument();
    expect(screen.getByTestId("level-history-path")).toBeInTheDocument();
    expect(screen.getByTestId("level-change-marker-1")).toBeInTheDocument();
    expect(screen.getByTestId("level-change-marker-2")).toBeInTheDocument();
    expect(screen.getByTestId("level-change-marker-3")).toBeInTheDocument();

    const rows = container.querySelectorAll("table.sr-only tbody tr");
    expect(rows.length).toBe(3);
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("renders a single assessment point cleanly and explains empty state when none exist", () => {
    const single = HISTORY_POINTS.slice(0, 1);
    const { container, rerender } = render(
      <LevelHistoryChart location="Miami-Dade County Hall" points={single} />,
    );
    expect(screen.getByTestId("level-change-marker-3")).toBeInTheDocument();
    expect(container.querySelector("[style]")).toBeNull();

    rerender(
      <LevelHistoryChart location="Miami-Dade County Hall" points={[]} />,
    );
    expect(screen.getByTestId("level-history-empty")).toBeInTheDocument();
    expect(
      screen.getByText(/No assessments are stored for Miami-Dade County Hall/i),
    ).toBeInTheDocument();
    expect(container.querySelector("[style]")).toBeNull();
  });
});
