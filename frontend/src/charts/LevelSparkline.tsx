// frontend/src/charts/LevelSparkline.tsx
import type { components } from "../api/schema.ts";
import { levelSvgClasses } from "../app/ThreatLevelBadge.tsx";
import { linearScale, roundSvg, stepPath, timeScale, toEpochMs } from "./scale.ts";

export type ChartLevelPoint =
  components["schemas"]["ChartLevelPointResponse"];

export interface LevelSparklineProps {
  readonly location: string;
  readonly points: readonly ChartLevelPoint[];
}

const WIDTH = 80;
const HEIGHT = 20;
const PAD_LEFT = 6;
const PAD_RIGHT = 74;
const PAD_BOTTOM = 16;
const PAD_TOP = 4;

export function sortLevelPointsChronological(
  points: readonly ChartLevelPoint[],
): readonly ChartLevelPoint[] {
  return [...points].sort((a, b) => {
    const dt = toEpochMs(a.as_of) - toEpochMs(b.as_of);
    return dt !== 0 ? dt : a.id - b.id;
  });
}

export function LevelSparkline({ location, points }: LevelSparklineProps) {
  const ordered = sortLevelPointsChronological(points);
  const current = ordered.at(-1);
  const colors = levelSvgClasses(current?.level ?? 1);
  const hasIncomplete = ordered.some((pt) => !pt.complete);

  const titleText =
    current !== undefined
      ? `${location} threat level sparkline: current Level ${String(current.level)} (${current.label})${hasIncomplete ? ", includes incomplete assessment" : ""}`
      : `${location} threat level sparkline: no stored assessments`;

  const yScale = linearScale([1, 5], [PAD_BOTTOM, PAD_TOP]);
  const first = ordered[0];
  const last = ordered[ordered.length - 1];
  const xScale =
    first !== undefined && last !== undefined
      ? timeScale([first.as_of, last.as_of], [PAD_LEFT, PAD_RIGHT])
      : () => PAD_RIGHT;

  const stepPoints =
    ordered.length === 1 && first !== undefined
      ? [
          { x: PAD_LEFT, y: yScale(first.level) },
          { x: PAD_RIGHT, y: yScale(first.level) },
        ]
      : ordered.map((pt) => ({
          x: xScale(pt.as_of),
          y: yScale(pt.level),
        }));

  const fullPath = stepPath(stepPoints);
  const dotX =
    ordered.length === 1
      ? PAD_RIGHT
      : last !== undefined
        ? roundSvg(xScale(last.as_of))
        : PAD_RIGHT;
  const dotY =
    last !== undefined ? roundSvg(yScale(last.level)) : roundSvg(yScale(1));

  return (
    <span
      className="relative inline-flex items-center overflow-hidden"
      data-testid="level-sparkline"
    >
      <svg
        role="img"
        aria-label={titleText}
        width={WIDTH}
        height={HEIGHT}
        viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
        className="overflow-visible"
      >
        <title>{titleText}</title>
        <line
          x1={PAD_LEFT}
          y1={PAD_BOTTOM}
          x2={PAD_RIGHT}
          y2={PAD_BOTTOM}
          strokeWidth={0.75}
          className="stroke-slate-200 dark:stroke-slate-700"
        />
        {fullPath !== "" ? (
          <path
            d={fullPath}
            fill="none"
            strokeWidth={1.75}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray={hasIncomplete ? "2 2" : undefined}
            className={colors.stroke}
            data-testid="sparkline-path"
          />
        ) : null}
        {current !== undefined ? (
          <circle
            cx={dotX}
            cy={dotY}
            r={2.5}
            className={colors.fill}
            data-testid="sparkline-current-dot"
          />
        ) : null}
      </svg>
      <table className="sr-only">
        <caption>{titleText}</caption>
        <thead>
          <tr>
            <th scope="col">As of (UTC)</th>
            <th scope="col">Level</th>
            <th scope="col">Rule</th>
            <th scope="col">Completeness</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((pt) => (
            <tr key={pt.id}>
              <td>{pt.as_of}</td>
              <td>{`Level ${String(pt.level)} (${pt.label})`}</td>
              <td>{pt.rule}</td>
              <td>{pt.complete ? "Complete" : "Incomplete (floor)"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </span>
  );
}
