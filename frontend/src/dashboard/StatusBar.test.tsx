// frontend/src/dashboard/StatusBar.test.tsx
import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StatusBar } from "./StatusBar.tsx";

const SNAPSHOT = {
  snapshot_id: "00000000-0000-4000-8000-000000000001",
  status: "complete" as const,
  started_at: "2026-10-13T01:30:00Z",
  completed_at: "2026-10-13T01:31:00Z",
  age_seconds: 240,
  source_outcomes: [],
  drift_warnings: [],
};

describe("StatusBar", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => false,
    });
  });

  it("renders snapshot status and age, updates the minute countdown at minute boundaries, and pauses while document.hidden is true", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-13T02:18:20Z"));

    const { container } = render(
      <StatusBar
        snapshot={SNAPSHOT}
        nextProductAt="2026-10-13T03:00:00Z"
        serverNow="2026-10-13T02:18:20Z"
        timeZone="America/New_York"
        hasAnyAssessment
        locationNames={["Miami-Dade County Hall"]}
        includeBriefing={false}
        onIncludeBriefingChange={() => undefined}
        cycleRunning={false}
        onCheckNow={() => undefined}
        cycleMessage={null}
        evacError={null}
      />,
    );

    expect(screen.getByTestId("status-bar-snapshot")).toHaveTextContent(
      "Snapshot: complete · 4 min old",
    );
    const countdown = screen.getByTestId("next-product-countdown");
    expect(countdown).toHaveTextContent("Next NHC product in 42 min");
    expect(countdown).toHaveAttribute("title", "2026-10-13 03:00 UTC");

    // Advance 40s to reach 02:19:00Z minute boundary -> 41 min
    act(() => {
      vi.advanceTimersByTime(40_000);
    });
    expect(screen.getByTestId("next-product-countdown")).toHaveTextContent(
      "Next NHC product in 41 min",
    );

    // Pause while document.hidden is true
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => true,
    });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
      vi.advanceTimersByTime(5 * 60_000);
    });
    expect(screen.getByTestId("next-product-countdown")).toHaveTextContent(
      "Next NHC product in 41 min",
    );

    // Resume when visible again (now 02:24:00Z -> 36 min)
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => false,
    });
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(screen.getByTestId("next-product-countdown")).toHaveTextContent(
      "Next NHC product in 36 min",
    );
    expect(container.querySelector("[style]")).toBeNull();
  });
});
