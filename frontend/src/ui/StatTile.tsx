// frontend/src/ui/StatTile.tsx
import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { type ReactNode, useId } from "react";
import { cx } from "./threat.ts";

export type StatTrend = "up" | "down" | "steady";

export interface StatTileProps {
  readonly label: string;
  readonly value: ReactNode;
  readonly unit?: string;
  readonly caption?: ReactNode;
  readonly trend?: StatTrend;
  // Words for the trend, read in place of the arrow ("rising since 09:00 UTC").
  readonly trendLabel?: string;
  readonly className?: string;
}

function trendWords(trend: StatTrend): string {
  switch (trend) {
    case "up":
      return "rising";
    case "down":
      return "falling";
    default:
      return "steady";
  }
}

// One number with its label and unit, set in tabular figures so it never
// jitters as it changes. docs/DESIGN.md, "StatTile".
export function StatTile({
  label,
  value,
  unit,
  caption,
  trend,
  trendLabel,
  className,
}: StatTileProps) {
  const labelId = useId();
  const TrendIcon =
    trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : ArrowRight;
  return (
    <div
      role="group"
      aria-labelledby={labelId}
      className={cx(
        "rounded-card border border-line bg-surface-inset px-3.5 py-3",
        className,
      )}
    >
      <span id={labelId} className="block text-caption font-medium text-ink-subtle">
        {label}
      </span>
      <span className="mt-1 flex flex-wrap items-baseline gap-1.5">
        <span className="text-2xl font-semibold tabular-nums text-ink">{value}</span>
        {unit !== undefined && (
          <span className="text-sm font-medium text-ink-subtle">{unit}</span>
        )}
        {trend !== undefined && (
          <span className="inline-flex items-center gap-0.5 self-center text-caption font-medium text-ink-muted">
            <TrendIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{trendLabel ?? trendWords(trend)}</span>
          </span>
        )}
      </span>
      {caption !== undefined && caption !== null && (
        <span className="mt-1 block text-caption text-ink-subtle">{caption}</span>
      )}
    </div>
  );
}
