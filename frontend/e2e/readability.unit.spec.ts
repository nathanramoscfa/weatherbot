// frontend/e2e/readability.unit.spec.ts
import { expect, test } from "@playwright/test";
import { readabilityKit } from "./readability.ts";

// The audit's pure functions, run by Playwright without a page or a server:
// three known WCAG ratios, the compositing that finds a text's backdrop, and
// the large-text threshold.
const kit = readabilityKit();

const WHITE = { r: 255, g: 255, b: 255, a: 1 };
const BLACK = { r: 0, g: 0, b: 0, a: 1 };

test("relative luminance spans 0 (black) to 1 (white)", () => {
  expect(kit.relativeLuminance(BLACK)).toBe(0);
  expect(kit.relativeLuminance(WHITE)).toBeCloseTo(1, 10);
});

test("pins three known contrast ratios", () => {
  // Black on white is the scale's maximum.
  expect(kit.contrastRatio(BLACK, WHITE)).toBeCloseTo(21, 6);
  // #777777 on white is the classic just-below-AA grey.
  expect(
    kit.contrastRatio({ r: 0x77, g: 0x77, b: 0x77, a: 1 }, WHITE),
  ).toBeCloseTo(4.478, 3);
  // The brand token (sky-700, #0069a8) under white text, as docs/DESIGN.md records.
  expect(
    kit.contrastRatio(WHITE, { r: 0x00, g: 0x69, b: 0xa8, a: 1 }),
  ).toBeCloseTo(5.86, 2);
  // Order does not matter.
  expect(kit.contrastRatio(WHITE, BLACK)).toBeCloseTo(
    kit.contrastRatio(BLACK, WHITE),
    10,
  );
});

test("composites a translucent layer onto its backdrop", () => {
  const half = kit.composite({ r: 0, g: 0, b: 0, a: 0.5 }, WHITE);
  expect(half.a).toBe(1);
  expect(half.r).toBeCloseTo(127.5, 6);
  expect(kit.composite({ r: 10, g: 20, b: 30, a: 1 }, WHITE)).toEqual({
    r: 10,
    g: 20,
    b: 30,
    a: 1,
  });
  expect(kit.composite({ r: 9, g: 9, b: 9, a: 0 }, WHITE)).toEqual(WHITE);
});

test("large text is 24 px, or 18.66 px at weight 700, and needs 3:1", () => {
  expect(kit.isLargeText(24, 400)).toBe(true);
  expect(kit.isLargeText(18.66, 700)).toBe(true);
  expect(kit.isLargeText(18.66, 600)).toBe(false);
  expect(kit.isLargeText(17, 700)).toBe(false);
  expect(kit.minimumRatio(30, 400)).toBe(3);
  expect(kit.minimumRatio(15, 700)).toBe(4.5);
  expect(kit.MIN_PROSE_PX).toBe(14);
  expect(kit.MIN_TEXT_PX).toBe(13);
  expect(kit.MAX_MEASURE_EM).toBe(42);
  expect(kit.MEASURE_MIN_CHARS).toBe(160);
});
