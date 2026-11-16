// frontend/src/ui/Callout.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Callout, DEFAULT_CALLOUT_ROLE } from "./Callout.tsx";

describe("Callout", () => {
  it("maps each tone to its usual role", () => {
    expect(DEFAULT_CALLOUT_ROLE).toEqual({
      note: "note",
      info: "status",
      warning: "alert",
      error: "alert",
    });
    render(
      <>
        <Callout tone="note">A note</Callout>
        <Callout tone="info">Some news</Callout>
        <Callout tone="warning" title="Stale monitor data:">
          Two sources
        </Callout>
      </>,
    );
    expect(screen.getByRole("note")).toHaveTextContent("A note");
    expect(screen.getByRole("status")).toHaveTextContent("Some news");
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Stale monitor data:");
    expect(alert).toHaveTextContent("Two sources");
    expect(alert).toHaveClass("text-sm");
  });

  it("keeps the role an existing use already has, or none", () => {
    const { container } = render(
      <>
        <Callout tone="error" role="status">
          Saved with a problem
        </Callout>
        <Callout tone="warning" role="none" data-testid="plain">
          No landmark
        </Callout>
      </>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Saved with a problem");
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByTestId("plain")).not.toHaveAttribute("role");
    expect(container.querySelector("[style]")).toBeNull();
  });
});
