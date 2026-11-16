// frontend/src/ui/SectionHeading.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SectionHeading } from "./SectionHeading.tsx";

describe("SectionHeading", () => {
  it("renders an h2 on the scale with its description and actions", () => {
    render(
      <SectionHeading
        id="retention-heading"
        description="How long history is kept."
        actions={<button type="button">Prune now</button>}
      >
        Database &amp; Retention
      </SectionHeading>,
    );
    const heading = screen.getByRole("heading", {
      level: 2,
      name: "Database & Retention",
    });
    expect(heading).toHaveAttribute("id", "retention-heading");
    expect(heading).toHaveClass("text-lg", "font-semibold");
    expect(screen.getByText("How long history is kept.").tagName).toBe("P");
    expect(screen.getByRole("button", { name: "Prune now" })).toBeInTheDocument();
  });

  it("renders lower levels at their own sizes", () => {
    const { container } = render(
      <>
        <SectionHeading as="h3">Evidence</SectionHeading>
        <SectionHeading as="h4">Sources</SectionHeading>
      </>,
    );
    expect(screen.getByRole("heading", { level: 3, name: "Evidence" })).toHaveClass(
      "text-base",
    );
    expect(screen.getByRole("heading", { level: 4, name: "Sources" })).toHaveClass(
      "text-sm",
    );
    expect(container.querySelector("[style]")).toBeNull();
  });
});
