// frontend/src/ui/Chip.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Chip } from "./Chip.tsx";

describe("Chip", () => {
  it("is a caption-sized span in its tone", () => {
    const { container } = render(<Chip tone="ai">Lookup: storm</Chip>);
    const chip = container.firstElementChild;
    expect(chip?.tagName).toBe("SPAN");
    expect(chip).toHaveClass("text-caption", "rounded-pill", "bg-violet-50");
    expect(screen.getByText("Lookup: storm")).toBeInTheDocument();
    expect(container.querySelector("[style]")).toBeNull();
    expect(container.querySelector("p")).toBeNull();
  });

  it("tints with a threat level in place of a tone", () => {
    const { container } = render(
      <Chip level={3} icon={<svg aria-hidden="true" />}>
        Level 3
      </Chip>,
    );
    expect(container.firstElementChild).toHaveClass(
      "bg-threat-3-surface",
      "text-threat-3-fg",
    );
    expect(container.querySelector("svg")).not.toBeNull();
  });
});
