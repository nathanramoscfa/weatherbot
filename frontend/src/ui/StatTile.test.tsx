// frontend/src/ui/StatTile.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatTile } from "./StatTile.tsx";

describe("StatTile", () => {
  it("labels a tabular value with its unit, caption, and trend in words", () => {
    const { container } = render(
      <StatTile
        label="Distance to centre"
        value="71"
        unit="km"
        caption="From the latest advisory"
        trend="down"
        trendLabel="closing since 09:00 UTC"
      />,
    );
    const tile = screen.getByRole("group", { name: "Distance to centre" });
    expect(tile).toHaveTextContent("71");
    expect(screen.getByText("71")).toHaveClass("tabular-nums");
    expect(screen.getByText("km")).toBeInTheDocument();
    expect(screen.getByText("From the latest advisory")).toHaveClass("text-caption");
    expect(screen.getByText("closing since 09:00 UTC")).toBeInTheDocument();
    expect(container.querySelector("[style]")).toBeNull();
    expect(container.querySelector("p")).toBeNull();
  });

  it("names a trend when no label is given and omits what is absent", () => {
    render(<StatTile label="Wind" value={85} trend="up" />);
    expect(screen.getByText("rising")).toBeInTheDocument();
    render(<StatTile label="Pressure" value={990} />);
    expect(screen.getByRole("group", { name: "Pressure" })).not.toHaveTextContent(
      /rising|falling|steady/,
    );
  });
});
