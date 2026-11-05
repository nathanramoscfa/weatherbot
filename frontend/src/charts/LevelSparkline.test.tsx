// frontend/src/charts/LevelSparkline.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LevelSparkline, type ChartLevelPoint } from "./LevelSparkline.tsx";

const SAMPLE_POINTS: readonly ChartLevelPoint[] = [
  {
    id: 2,
    as_of: "2026-10-13T01:31:00Z",
    as_of_local: "2026-10-12T21:31:00-04:00",
    level: 4,
    label: "Warning / Watch / Evacuation",
    rule: "evacuation_order",
    complete: true,
  },
  {
    id: 1,
    as_of: "2026-10-13T01:00:00Z",
    as_of_local: "2026-10-12T21:00:00-04:00",
    level: 1,
    label: "All Clear",
    rule: "all_clear",
    complete: true,
  },
];

describe("LevelSparkline", () => {
  it("renders an 80x20 SVG stepped line, current level dot, title, sr-only table, and no style attribute", () => {
    const { container } = render(
      <LevelSparkline
        location="Miami-Dade County Hall"
        points={SAMPLE_POINTS}
      />,
    );

    const svg = screen.getByRole("img", {
      name: /Miami-Dade County Hall threat level sparkline: current Level 4/i,
    });
    expect(svg.getAttribute("width")).toBe("80");
    expect(svg.getAttribute("height")).toBe("20");

    const path = screen.getByTestId("sparkline-path");
    expect(path.getAttribute("d")).toContain("M 6 16 L 74 16 L 74 7");
    expect(path.getAttribute("stroke-dasharray")).toBeNull();
    expect(path.getAttribute("class")).toContain("stroke-orange-600");

    const dot = screen.getByTestId("sparkline-current-dot");
    expect(dot.getAttribute("cx")).toBe("74");
    expect(dot.getAttribute("cy")).toBe("7");
    expect(dot.getAttribute("class")).toContain("fill-orange-600");

    const rows = container.querySelectorAll("table.sr-only tbody tr");
    expect(rows.length).toBe(2);
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("draws a dashed line when an assessment is incomplete and supports a single point", () => {
    const incompletePoint: ChartLevelPoint = {
      id: 10,
      as_of: "2026-10-13T02:00:00Z",
      as_of_local: null,
      level: 2,
      label: "Awareness",
      rule: "basin_activity",
      complete: false,
    };
    const { container } = render(
      <LevelSparkline
        location="Parliament Square, Nassau"
        points={[incompletePoint]}
      />,
    );

    const path = screen.getByTestId("sparkline-path");
    expect(path.getAttribute("stroke-dasharray")).toBe("2 2");
    expect(path.getAttribute("d")).toBe("M 6 13 L 74 13");
    expect(screen.getByText("Incomplete (floor)")).toBeInTheDocument();
    expect(container.querySelector("[style]")).toBeNull();
  });
});
