// frontend/src/dashboard/ExportPopover.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { ExportPopover } from "./ExportPopover.tsx";

function Harness() {
  const [includeBriefing, setIncludeBriefing] = useState(false);
  return (
    <ExportPopover
      locationNames={["Miami-Dade County Hall", "Parliament Square"]}
      includeBriefing={includeBriefing}
      onIncludeBriefingChange={setIncludeBriefing}
    />
  );
}

describe("ExportPopover", () => {
  it("opens a portalled popover, updates report links when Include the AI briefing is ticked, and closes on Escape returning focus", async () => {
    const user = userEvent.setup();
    const { container } = render(<Harness />);

    expect(container.querySelector("[style]")).toBeNull();
    const trigger = screen.getByRole("button", { name: "Export report" });
    await user.click(trigger);

    expect(
      screen.getByText(
        /opens offline anywhere and prints to PDF from the browser/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /its words quote NWS alerts and can name a county or a forecast office/i,
      ),
    ).toBeInTheDocument();

    const exportAll = screen.getByTestId("export-report-all");
    const exportMiami = screen.getByTestId(
      "export-report-Miami-Dade County Hall",
    );
    expect(exportAll).toHaveAttribute("href", "/api/report");
    expect(exportMiami).toHaveAttribute(
      "href",
      "/api/report?location=Miami-Dade+County+Hall",
    );

    const checkbox = screen.getByRole("checkbox", {
      name: /Include the AI briefing/i,
    });
    await user.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(exportAll).toHaveAttribute("href", "/api/report?briefing=true");
    expect(exportMiami).toHaveAttribute(
      "href",
      "/api/report?location=Miami-Dade+County+Hall&briefing=true",
    );

    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("export-report-all")).toBeNull();
    expect(trigger).toHaveFocus();
  });
});
