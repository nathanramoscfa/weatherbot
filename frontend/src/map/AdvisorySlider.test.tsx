// frontend/src/map/AdvisorySlider.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  AdvisorySlider,
  type AdvisorySliderStep,
} from "./AdvisorySlider.tsx";

const SAMPLE_STEPS: readonly AdvisorySliderStep[] = [
  {
    snapshot_id: "00000000-0000-4000-8000-000000000003",
    as_of: "2026-10-13T00:01:00Z",
    atcf_id: "AL142026",
    storm_name: "Milton",
    classification: "HU",
    advisory: "17",
    issued_at: "2026-10-13T00:00:00Z",
  },
  {
    snapshot_id: "00000000-0000-4000-8000-000000000002",
    as_of: "2026-10-12T21:01:00Z",
    atcf_id: "AL142026",
    storm_name: "Milton",
    classification: "HU",
    advisory: "16",
    issued_at: "2026-10-12T21:00:00Z",
  },
  {
    snapshot_id: "00000000-0000-4000-8000-000000000001",
    as_of: "2026-10-12T18:00:00Z",
    atcf_id: "AL142026",
    storm_name: "Milton",
    classification: "HU",
    advisory: "15",
    issued_at: "2026-10-12T18:00:00Z",
  },
];

describe("AdvisorySlider", () => {
  it("renders null when fewer than two steps exist", () => {
    const { container } = render(
      <AdvisorySlider
        steps={[SAMPLE_STEPS[0]!]}
        selectedSnapshotId={null}
        onSelectSnapshotId={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("updates the label while dragging without firing onSelectSnapshotId until release", () => {
    const onSelect = vi.fn();
    render(
      <AdvisorySlider
        steps={SAMPLE_STEPS}
        selectedSnapshotId={null}
        onSelectSnapshotId={onSelect}
      />,
    );

    const slider = screen.getByRole("slider");
    expect(slider).toHaveValue("2");
    expect(screen.getByTestId("advisory-slider-label")).toHaveTextContent(
      "Milton advisory 17, 2026-10-13 00:00 UTC",
    );

    // Move thumb through intermediate stops without releasing
    fireEvent.change(slider, { target: { value: "1" } });
    expect(screen.getByTestId("advisory-slider-label")).toHaveTextContent(
      "Milton advisory 16, 2026-10-12 21:00 UTC",
    );
    expect(onSelect).not.toHaveBeenCalled();

    fireEvent.change(slider, { target: { value: "0" } });
    expect(screen.getByTestId("advisory-slider-label")).toHaveTextContent(
      "Milton advisory 15, 2026-10-12 18:00 UTC",
    );
    expect(onSelect).not.toHaveBeenCalled();

    // Release commits once
    fireEvent.mouseUp(slider);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(
      "00000000-0000-4000-8000-000000000001",
    );
  });

  it("supports keyboard stepping, renders the stored-advisory banner and newer-advisory notice, and returns to latest", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const { rerender } = render(
      <AdvisorySlider
        steps={SAMPLE_STEPS}
        selectedSnapshotId={null}
        onSelectSnapshotId={onSelect}
      />,
    );

    const slider = screen.getByRole("slider");
    fireEvent.keyDown(slider, { key: "ArrowLeft" });
    expect(onSelect).toHaveBeenCalledWith(
      "00000000-0000-4000-8000-000000000002",
    );

    rerender(
      <AdvisorySlider
        steps={SAMPLE_STEPS}
        selectedSnapshotId="00000000-0000-4000-8000-000000000002"
        onSelectSnapshotId={onSelect}
        newerAdvisoryArrived={true}
      />,
    );

    const banner = screen.getByTestId("stored-advisory-banner");
    expect(banner).toHaveTextContent(
      "Stored advisory: Milton 16, 2026-10-12 21:00 UTC — not the latest",
    );
    expect(banner).toHaveTextContent("Newer advisory arrived");

    await user.click(screen.getByRole("button", { name: "Back to latest" }));
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });
});
