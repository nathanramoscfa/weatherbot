// frontend/src/ui/PageHeader.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PageHeader } from "./PageHeader.tsx";

describe("PageHeader", () => {
  it("renders the route's h1, a one-line summary, and its actions", () => {
    render(
      <PageHeader
        title="Storms"
        summary="Active storms from the National Hurricane Center."
        actions={<button type="button">Refresh</button>}
      />,
    );
    const heading = screen.getByRole("heading", { level: 1, name: "Storms" });
    expect(heading).toHaveClass("text-2xl");
    expect(
      screen.getByText("Active storms from the National Hurricane Center."),
    ).toHaveClass("text-sm");
    expect(screen.getByRole("button", { name: "Refresh" })).toBeInTheDocument();
  });

  it("keeps a hidden title for assistive technology", () => {
    const { container } = render(<PageHeader title="Map" hideTitle />);
    const heading = screen.getByRole("heading", { level: 1, name: "Map" });
    expect(heading).toHaveClass("sr-only");
    expect(container.querySelector("p")).toBeNull();
    expect(container.querySelector("[style]")).toBeNull();
  });
});
