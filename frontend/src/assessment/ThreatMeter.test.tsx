// frontend/src/assessment/ThreatMeter.test.tsx
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThreatMeter } from "./ThreatMeter.tsx";
import { FALLBACK_LEVELS } from "./vocabulary.ts";

describe("ThreatMeter", () => {
  it("renders all five steps in an ordered list with aria-current='step' and a visually hidden 'Level N of 5'", () => {
    const { container } = render(<ThreatMeter level={4} complete />);

    const list = screen.getByRole("list", { name: "Threat level meter" });
    expect(list.tagName.toLowerCase()).toBe("ol");

    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(5);

    for (const lvl of FALLBACK_LEVELS) {
      const stepEl = screen.getByTestId(`threat-meter-step-${String(lvl.number)}`);
      expect(stepEl).toHaveTextContent(`${String(lvl.number)}. ${lvl.label}`);
      if (lvl.number === 4) {
        expect(stepEl).toHaveAttribute("aria-current", "step");
        expect(within(stepEl).getByText(/Level 4 of 5/)).toHaveClass("sr-only");
      } else {
        expect(stepEl).not.toHaveAttribute("aria-current");
      }
    }

    expect(screen.queryByTestId("threat-meter-at-least")).toBeNull();
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("marks 'At least' when the assessment is incomplete", () => {
    const { container } = render(<ThreatMeter level={3} complete={false} />);

    const step3 = screen.getByTestId("threat-meter-step-3");
    expect(step3).toHaveAttribute("aria-current", "step");
    expect(
      within(step3).getByText(/At least Level 3 of 5/),
    ).toHaveClass("sr-only");
    expect(screen.getByTestId("threat-meter-at-least")).toHaveTextContent(
      "At least",
    );
    expect(container.querySelector("[style]")).toBeNull();
  });
});
