// frontend/src/charts/scale.test.ts
import { describe, expect, it } from "vitest";
import {
  bandPath,
  linearScale,
  stepPath,
  ticksFor,
  timeScale,
} from "./scale.ts";

describe("charts/scale", () => {
  it("maps timeScale across a normal span and centers degenerate single or equal instants", () => {
    const t0 = "2026-10-12T12:00:00Z";
    const t1 = "2026-10-12T18:00:00Z";
    const scale = timeScale([t0, t1], [10, 110]);
    expect(scale(t0)).toBe(10);
    expect(scale("2026-10-12T15:00:00Z")).toBe(60);
    expect(scale(t1)).toBe(110);

    // Degenerate domain: one point or two equal instants maps to the range midpoint.
    const equalScale = timeScale([t0, t0], [10, 90]);
    expect(equalScale(t0)).toBe(50);
    expect(equalScale(new Date(t1))).toBe(50);
  });

  it("maps linearScale across numeric domains and centers a zero-span domain", () => {
    const yScale = linearScale([1, 5], [80, 0]);
    expect(yScale(1)).toBe(80);
    expect(yScale(3)).toBe(40);
    expect(yScale(5)).toBe(0);

    const flat = linearScale([3, 3], [20, 60]);
    expect(flat(3)).toBe(40);
  });

  it("builds stepPath for empty, one point, two equal instants, normal steps, and a gap", () => {
    expect(stepPath([])).toBe("");
    expect(stepPath([{ x: 40, y: 10 }])).toBe("M 40 10 L 40 10");

    // Two equal instants step vertically at the shared x without an extra horizontal segment.
    expect(
      stepPath([
        { x: 25, y: 16 },
        { x: 25, y: 4 },
      ]),
    ).toBe("M 25 16 L 25 4");

    // Normal step-after with a gap before the third point.
    expect(
      stepPath([
        { x: 10, y: 16 },
        { x: 40, y: 8 },
        { x: 70, y: 4, gapBefore: true },
        { x: 90, y: 12 },
      ]),
    ).toBe("M 10 16 L 40 16 L 40 8 M 70 4 L 90 4 L 90 12");
  });

  it("builds bandPath for one point, two equal instants, and a gap between runs", () => {
    expect(bandPath([])).toBe("");

    // Single point widens by halfWidth around x.
    expect(bandPath([{ x: 50, yTop: 10, yBottom: 30 }], 5)).toBe(
      "M 45 10 L 55 10 L 55 30 L 45 30 Z",
    );

    // Two equal instants collapse to a widened column around the shared x.
    expect(
      bandPath(
        [
          { x: 50, yTop: 15, yBottom: 25 },
          { x: 50, yTop: 10, yBottom: 30 },
        ],
        4,
      ),
    ).toBe("M 46 10 L 54 10 L 54 30 L 46 30 Z");

    // Multi-point run split by a gapBefore.
    expect(
      bandPath(
        [
          { x: 10, yTop: 20, yBottom: 40 },
          { x: 30, yTop: 15, yBottom: 35 },
          { x: 60, yTop: 10, yBottom: 25, gapBefore: true },
        ],
        5,
      ),
    ).toBe(
      "M 10 20 L 30 15 L 30 35 L 10 40 Z M 55 10 L 65 10 L 65 25 L 55 25 Z",
    );
  });

  it("computes ticksFor normal, single-value, and empty tick counts", () => {
    expect(ticksFor([0, 100], 5)).toEqual([0, 25, 50, 75, 100]);
    expect(ticksFor([42, 42], 4)).toEqual([42]);
    expect(ticksFor([0, 100], 1)).toEqual([0]);
    expect(ticksFor([0, 100], 0)).toEqual([]);
  });
});
