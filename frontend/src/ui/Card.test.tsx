// frontend/src/ui/Card.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Card } from "./Card.tsx";

describe("Card", () => {
  it("renders a neutral section with the card elevation by default", () => {
    const { container } = render(
      <Card aria-label="Neutral card">
        <p>Body</p>
      </Card>,
    );
    const card = screen.getByRole("region", { name: "Neutral card" });
    expect(card.tagName).toBe("SECTION");
    expect(card).toHaveClass("bg-surface-card", "border-line", "shadow-card", "rounded-card");
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("tints with a threat level and takes the element, elevation, and padding asked for", () => {
    render(
      <Card as="article" level={5} elevation="raised" padding="sm" aria-label="Level five">
        Body
      </Card>,
    );
    const card = screen.getByRole("article", { name: "Level five" });
    expect(card).toHaveClass(
      "bg-threat-5-surface",
      "border-threat-5-border",
      "text-threat-5-fg",
      "shadow-raised",
      "p-3",
    );
    expect(card).not.toHaveClass("bg-surface-card");
  });

  it("clamps an out-of-range level and keeps flat cards shadowless", () => {
    render(
      <Card as="div" level={9} elevation="flat" padding="none" data-testid="card">
        Body
      </Card>,
    );
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("bg-threat-5-surface");
    expect(card.className).not.toMatch(/shadow-/);
  });
});
