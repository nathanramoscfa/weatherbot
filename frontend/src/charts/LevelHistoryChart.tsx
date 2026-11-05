// frontend/src/charts/LevelHistoryChart.tsx
import { levelSvgClasses } from "../app/ThreatLevelBadge.tsx";
import {
  type ChartLevelPoint,
  sortLevelPointsChronological,
} from "./LevelSparkline.tsx";
import {
  linearScale,
  roundSvg,
  stepPath,
  ticksFor,
  timeScale,
  toEpochMs,
} from "./scale.ts";

export interface LevelHistoryChartProps {
  readonly location: string;
  readonly timeZone?: string | null;
  readonly points: readonly ChartLevelPoint[];
}

const VIEW_WIDTH = 560;
const VIEW_HEIGHT = 180;
const PLOT_LEFT = 92;
const PLOT_RIGHT = 536;
const PLOT_TOP = 20;
const PLOT_BOTTOM = 140;

const LEVEL_AXIS_LABELS: Readonly<Record<number, string>> = {
  1: "L1 Clear",
  2: "L2 Aware",
  3: "L3 Watch",
  4: "L4 Warn",
  5: "L5 Cat.",
};

function levelAxisLabel(lvl: number): string {
  switch (lvl) {
    case 5:
      return LEVEL_AXIS_LABELS[5]!;
    case 4:
      return LEVEL_AXIS_LABELS[4]!;
    case 3:
      return LEVEL_AXIS_LABELS[3]!;
    case 2:
      return LEVEL_AXIS_LABELS[2]!;
    default:
      return LEVEL_AXIS_LABELS[1]!;
  }
}

function formatShortUtc(epochMs: number): string {
  const d = new Date(epochMs);
  if (Number.isNaN(d.getTime())) {
    return "—";
  }
  const iso = d.toISOString();
  return `${iso.slice(5, 10)} ${iso.slice(11, 16)}Z`;
}

export function LevelHistoryChart({
  location,
  timeZone,
  points,
}: LevelHistoryChartProps) {
  const ordered = sortLevelPointsChronological(points);
  if (ordered.length === 0) {
    return (
      <section
        aria-label={`Threat level history for ${location}`}
        className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
        data-testid="level-history-empty"
      >
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Threat level history · {location}
        </h3>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
          No assessments are stored for {location} yet. A stepped threat-level
          history chart will appear here after the first monitor cycle stores an
          assessment.
        </p>
      </section>
    );
  }

  const first = ordered[0];
  const last = ordered.at(-1);
  const lineColors = levelSvgClasses(last?.level ?? 1);
  const hasIncomplete = ordered.some((pt) => !pt.complete);

  const yScale = linearScale([1, 5], [PLOT_BOTTOM, PLOT_TOP]);
  const firstMs = first !== undefined ? toEpochMs(first.as_of) : 0;
  const lastMs = last !== undefined ? toEpochMs(last.as_of) : 0;
  const xScale = timeScale([firstMs, lastMs], [PLOT_LEFT, PLOT_RIGHT]);

  const stepPoints =
    ordered.length === 1 && first !== undefined
      ? [
          { x: PLOT_LEFT, y: yScale(first.level) },
          { x: PLOT_RIGHT, y: yScale(first.level) },
        ]
      : ordered.map((pt) => ({
          x: xScale(pt.as_of),
          y: yScale(pt.level),
        }));
  const dPath = stepPath(stepPoints);

  const changeMarkers = ordered.filter((pt, idx) => {
    if (idx === 0 || idx === ordered.length - 1) {
      return true;
    }
    const prev = ordered[idx - 1];
    return prev === undefined || prev.level !== pt.level || prev.rule !== pt.rule;
  });

  const xTicks = ticksFor([firstMs, lastMs], ordered.length === 1 ? 1 : 3);
  const titleText = `Threat level history for ${location}: ${String(ordered.length)} assessment${ordered.length === 1 ? "" : "s"}, latest Level ${String(last?.level ?? 1)} (${last?.label ?? "All Clear"})`;

  return (
    <section
      aria-label={`Threat level history for ${location}`}
      className="relative overflow-hidden rounded-xl border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
      data-testid="level-history-chart"
    >
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Threat level history · {location}
        </h3>
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {timeZone !== null && timeZone !== undefined
            ? `UTC axis · local zone ${timeZone}`
            : "UTC axis"}
        </span>
      </div>
      <svg
        role="img"
        aria-label={titleText}
        viewBox={`0 0 ${String(VIEW_WIDTH)} ${String(VIEW_HEIGHT)}`}
        className="h-auto w-full max-w-full"
      >
        <title>{titleText}</title>
        {[1, 2, 3, 4, 5].map((lvl) => {
          const y = roundSvg(yScale(lvl));
          return (
            <g key={lvl}>
              <line
                x1={PLOT_LEFT}
                y1={y}
                x2={PLOT_RIGHT}
                y2={y}
                strokeWidth={1}
                className="stroke-slate-200 dark:stroke-slate-800"
              />
              <text
                x={PLOT_LEFT - 8}
                y={y + 4}
                textAnchor="end"
                className="fill-slate-600 text-[11px] font-medium dark:fill-slate-400"
              >
                {levelAxisLabel(lvl)}
              </text>
            </g>
          );
        })}

        {xTicks.map((tickMs, idx) => {
          const x =
            ordered.length === 1 ? roundSvg((PLOT_LEFT + PLOT_RIGHT) / 2) : roundSvg(xScale(tickMs));
          return (
            <g key={`${String(tickMs)}-${String(idx)}`}>
              <line
                x1={x}
                y1={PLOT_BOTTOM}
                x2={x}
                y2={PLOT_BOTTOM + 5}
                strokeWidth={1}
                className="stroke-slate-300 dark:stroke-slate-700"
              />
              <text
                x={x}
                y={PLOT_BOTTOM + 18}
                textAnchor="middle"
                className="fill-slate-600 font-mono text-[10px] dark:fill-slate-400"
              >
                {formatShortUtc(tickMs)}
              </text>
            </g>
          );
        })}

        {dPath !== "" ? (
          <path
            d={dPath}
            fill="none"
            strokeWidth={2.25}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray={hasIncomplete ? "4 3" : undefined}
            className={lineColors.stroke}
            data-testid="level-history-path"
          />
        ) : null}

        {changeMarkers.map((pt) => {
          const cx =
            ordered.length === 1
              ? roundSvg((PLOT_LEFT + PLOT_RIGHT) / 2)
              : roundSvg(xScale(pt.as_of));
          const cy = roundSvg(yScale(pt.level));
          const markerStyle = levelSvgClasses(pt.level);
          return (
            <g
              key={pt.id}
              data-testid={`level-change-marker-${String(pt.id)}`}
            >
              <circle
                cx={cx}
                cy={cy}
                r={4.5}
                strokeWidth={1.5}
                className={`${markerStyle.fill} stroke-white dark:stroke-slate-900`}
              />
              <text
                x={cx}
                y={cy - 8}
                textAnchor="middle"
                className="fill-slate-800 text-[10px] font-semibold dark:fill-slate-200"
              >
                {`L${String(pt.level)}`}
              </text>
            </g>
          );
        })}
      </svg>

      <table className="sr-only">
        <caption>{titleText}</caption>
        <thead>
          <tr>
            <th scope="col">As of (UTC)</th>
            <th scope="col">Local time</th>
            <th scope="col">Level</th>
            <th scope="col">Deciding rule</th>
            <th scope="col">Completeness</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((pt) => (
            <tr key={pt.id}>
              <td>{pt.as_of}</td>
              <td>{pt.as_of_local ?? "—"}</td>
              <td>{`Level ${String(pt.level)} (${pt.label})`}</td>
              <td>{pt.rule}</td>
              <td>{pt.complete ? "Complete" : "Incomplete (floor)"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
