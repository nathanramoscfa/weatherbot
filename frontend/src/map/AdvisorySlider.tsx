// frontend/src/map/AdvisorySlider.tsx
import { Clock, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";
import { formatUtc } from "../pages/format.ts";

export interface AdvisorySliderStep {
  readonly snapshot_id: string;
  readonly as_of?: string | null;
  readonly atcf_id: string;
  readonly storm_name: string;
  readonly classification?: string | null;
  readonly advisory: string;
  readonly issued_at?: string | null;
}

export interface AdvisorySliderProps {
  readonly steps: readonly AdvisorySliderStep[];
  readonly selectedSnapshotId: string | null;
  readonly onSelectSnapshotId: (snapshotId: string | null) => void;
  readonly newerAdvisoryArrived?: boolean;
  readonly order?: "newest-first" | "oldest-first";
}

export function formatStepLabel(step: AdvisorySliderStep): string {
  const advisoryText =
    step.advisory.trim().length > 0 ? step.advisory : "—";
  const timeText = formatUtc(step.issued_at ?? step.as_of ?? null);
  return `${step.storm_name} advisory ${advisoryText}, ${timeText}`;
}

export function AdvisorySlider({
  steps,
  selectedSnapshotId,
  onSelectSnapshotId,
  newerAdvisoryArrived = false,
  order = "newest-first",
}: AdvisorySliderProps) {
  const chronologicalSteps = useMemo(() => {
    if (order === "oldest-first") {
      return [...steps];
    }
    return [...steps].reverse();
  }, [steps, order]);

  const latestIndex = Math.max(0, chronologicalSteps.length - 1);

  const committedIndex = useMemo(() => {
    if (selectedSnapshotId === null) {
      return latestIndex;
    }
    const found = chronologicalSteps.findIndex(
      (step) => step.snapshot_id === selectedSnapshotId,
    );
    return found === -1 ? latestIndex : found;
  }, [chronologicalSteps, latestIndex, selectedSnapshotId]);

  const [draftState, setDraftState] = useState<{
    readonly forCommitted: number;
    readonly index: number;
  }>({
    forCommitted: committedIndex,
    index: committedIndex,
  });

  const activeDraftIndex =
    draftState.forCommitted === committedIndex
      ? draftState.index
      : committedIndex;

  if (chronologicalSteps.length <= 1) {
    return null;
  }

  const clampedDraftIndex = Math.min(
    Math.max(0, activeDraftIndex),
    chronologicalSteps.length - 1,
  );
  const draftStep =
    chronologicalSteps.at(clampedDraftIndex) ??
    chronologicalSteps.at(latestIndex);
  const committedStep =
    chronologicalSteps.at(committedIndex) ?? chronologicalSteps.at(latestIndex);

  if (!draftStep || !committedStep) {
    return null;
  }

  const isViewingPast = selectedSnapshotId !== null;

  const commitIndex = (indexToCommit: number) => {
    const clamped = Math.min(
      Math.max(0, indexToCommit),
      chronologicalSteps.length - 1,
    );
    const targetStep = chronologicalSteps.at(clamped);
    if (!targetStep) {
      return;
    }
    if (clamped === latestIndex) {
      if (selectedSnapshotId !== null) {
        onSelectSnapshotId(null);
      }
      return;
    }
    if (targetStep.snapshot_id !== selectedSnapshotId) {
      onSelectSnapshotId(targetStep.snapshot_id);
    }
  };

  const handleRangeChange = (nextValue: string) => {
    const parsed = Number.parseInt(nextValue, 10);
    if (Number.isNaN(parsed)) {
      return;
    }
    const clamped = Math.min(
      Math.max(0, parsed),
      chronologicalSteps.length - 1,
    );
    setDraftState({ forCommitted: committedIndex, index: clamped });
  };

  const handleRelease = () => {
    commitIndex(clampedDraftIndex);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    let nextIndex: number | null = null;
    if (event.key === "ArrowLeft" || event.key === "ArrowDown") {
      nextIndex = Math.max(0, clampedDraftIndex - 1);
    } else if (event.key === "ArrowRight" || event.key === "ArrowUp") {
      nextIndex = Math.min(latestIndex, clampedDraftIndex + 1);
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = latestIndex;
    }
    if (nextIndex !== null) {
      event.preventDefault();
      setDraftState({ forCommitted: committedIndex, index: nextIndex });
      commitIndex(nextIndex);
    }
  };

  const handleBackToLatest = () => {
    setDraftState({ forCommitted: committedIndex, index: latestIndex });
    onSelectSnapshotId(null);
  };

  const draftLabel = formatStepLabel(draftStep);
  const committedAdvisoryText =
    committedStep.advisory.trim().length > 0 ? committedStep.advisory : "—";
  const committedTimeText = formatUtc(
    committedStep.issued_at ?? committedStep.as_of ?? null,
  );

  return (
    <section
      aria-label="Advisory history"
      data-testid="advisory-slider-panel"
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <label
          htmlFor="advisory-history-slider"
          className="flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-800 dark:text-slate-200"
        >
          <Clock
            className="h-3.5 w-3.5 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <span>Advisory history:</span>
          <span
            data-testid="advisory-slider-label"
            className="font-normal text-slate-700 dark:text-slate-300"
          >
            {draftLabel}
          </span>
        </label>

        {isViewingPast && (
          <button
            type="button"
            onClick={handleBackToLatest}
            className="inline-flex items-center justify-center gap-1.5 rounded-md bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:bg-sky-500 dark:text-slate-950"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            <span>Back to latest</span>
          </button>
        )}
      </div>

      <div className="mt-2">
        <input
          id="advisory-history-slider"
          type="range"
          min={0}
          max={latestIndex}
          step={1}
          value={clampedDraftIndex}
          aria-valuetext={draftLabel}
          onChange={(e) => handleRangeChange(e.target.value)}
          onMouseUp={handleRelease}
          onPointerUp={handleRelease}
          onTouchEnd={handleRelease}
          onKeyDown={handleKeyDown}
          className="w-full cursor-pointer accent-sky-600 dark:accent-sky-400"
        />
      </div>

      {isViewingPast && (
        <div
          role="status"
          data-testid="stored-advisory-banner"
          className="mt-3 rounded-md border border-amber-400 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-950 dark:border-amber-600 dark:bg-amber-950/70 dark:text-amber-100"
        >
          Stored advisory: {committedStep.storm_name} {committedAdvisoryText},{" "}
          {committedTimeText} — not the latest
          {newerAdvisoryArrived ? " · Newer advisory arrived" : ""}
        </div>
      )}
    </section>
  );
}
