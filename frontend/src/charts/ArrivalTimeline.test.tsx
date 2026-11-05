// frontend/src/charts/ArrivalTimeline.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ArrivalTimeline, type ArrivalReading } from "./ArrivalTimeline.tsx";

const WINDOW_EARLIEST: ArrivalReading = {
  kind: "earliest_reasonable",
  origin: "kmz",
  reading: "between",
  advisory: "36",
  start: "2017-09-09T12:00:00Z",
  end: "2017-09-10T00:00:00Z",
  approach_at: null,
  label: "Sat 8 AM - Sat 8 PM EDT",
  reason: null,
};

const WINDOW_MOST_LIKELY: ArrivalReading = {
  kind: "most_likely",
  origin: "kmz",
  reading: "between",
  advisory: "36",
  start: "2017-09-10T00:00:00Z",
  end: "2017-09-10T12:00:00Z",
  approach_at: null,
  label: "Sat 8 PM - Sun 8 AM EDT",
  reason: null,
};

const OUTSIDE_READING: ArrivalReading = {
  kind: "most_likely",
  origin: "kmz",
  reading: "outside",
  advisory: "36",
  start: null,
  end: null,
  approach_at: null,
  label: null,
  reason: null,
};

describe("ArrivalTimeline", () => {
  it("draws bars from the assessment asOf prop to start..end when present and sets no style attribute", () => {
    const { container } = render(
      <ArrivalTimeline
        asOf="2017-09-08T03:00:00Z"
        stormName="Irma"
        earliest={WINDOW_EARLIEST}
        mostLikely={WINDOW_MOST_LIKELY}
      />,
    );

    const svg = screen.getByRole("img", {
      name: /34-kt wind arrival timeline for Irma as of 09-08 03:00Z/i,
    });
    expect(svg).toBeInTheDocument();
    expect(screen.getByTestId("arrival-bar-earliest")).toBeInTheDocument();
    expect(screen.getByTestId("arrival-bar-most-likely")).toBeInTheDocument();
    expect(screen.queryByTestId("arrival-words-earliest")).toBeNull();
    expect(screen.queryByTestId("arrival-words-most-likely")).toBeNull();

    const rows = container.querySelectorAll("table.sr-only tbody tr");
    expect(rows.length).toBe(2);
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("prints reading words without inventing a bar when start or end is absent", () => {
    const beforeReading: ArrivalReading = {
      kind: "earliest_reasonable",
      origin: "kmz",
      reading: "before",
      advisory: "36",
      start: null,
      end: "2017-09-09T12:00:00Z",
      approach_at: null,
      label: "Sat 8 AM EDT",
      reason: null,
    };

    const { container } = render(
      <ArrivalTimeline
        asOf="2017-09-08T03:00:00Z"
        stormName="Irma"
        earliest={beforeReading}
        mostLikely={OUTSIDE_READING}
      />,
    );

    expect(screen.queryByTestId("arrival-bar-earliest")).toBeNull();
    expect(screen.queryByTestId("arrival-bar-most-likely")).toBeNull();
    expect(screen.getByTestId("arrival-words-earliest")).toHaveTextContent(
      /before: by 2017-09-09/i,
    );
    expect(screen.getByTestId("arrival-words-most-likely")).toHaveTextContent(
      /outside: outside the 5% contour/i,
    );
    expect(container.querySelector("[style]")).toBeNull();
  });
});
