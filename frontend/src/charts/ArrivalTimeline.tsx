// frontend/src/charts/ArrivalTimeline.tsx
import type { components } from "../api/schema.ts";
import { formatArrivalReading } from "../pages/format.ts";
import { roundSvg, timeScale, toEpochMs } from "./scale.ts";

export type ArrivalReading = components["schemas"]["ArrivalReadingResponse"];

export interface ArrivalTimelineProps {
  readonly asOf: string;
  readonly stormName: string;
  readonly earliest: ArrivalReading;
  readonly mostLikely: ArrivalReading;
}

const VIEW_WIDTH = 420;
const VIEW_HEIGHT = 72;
const PLOT_LEFT = 124;
const PLOT_RIGHT = 404;

function hasWindow(
  reading: ArrivalReading,
): reading is ArrivalReading & { readonly start: string; readonly end: string } {
  return (
    reading.reading === "between" &&
    reading.start !== null &&
    reading.end !== null
  );
}

function formatCompactUtc(iso: string): string {
  const ms = toEpochMs(iso);
  if (!Number.isFinite(ms)) {
    return iso;
  }
  const d = new Date(ms);
  const s = d.toISOString();
  return `${s.slice(5, 10)} ${s.slice(11, 16)}Z`;
}

export function ArrivalTimeline({
  asOf,
  stormName,
  earliest,
  mostLikely,
}: ArrivalTimelineProps) {
  const asOfMs = toEpochMs(asOf);
  const earliestWin = hasWindow(earliest);
  const mostLikelyWin = hasWindow(mostLikely);

  const windowEnds: number[] = [];
  if (earliestWin) {
    windowEnds.push(toEpochMs(earliest.start), toEpochMs(earliest.end));
  }
  if (mostLikelyWin) {
    windowEnds.push(toEpochMs(mostLikely.start), toEpochMs(mostLikely.end));
  }
  const maxMs =
    windowEnds.length > 0
      ? Math.max(asOfMs, ...windowEnds)
      : asOfMs;
  const minMs =
    windowEnds.length > 0
      ? Math.min(asOfMs, ...windowEnds)
      : asOfMs;

  const xScale = timeScale([minMs, maxMs], [PLOT_LEFT, PLOT_RIGHT]);
  const asOfX =
    windowEnds.length > 0 ? roundSvg(xScale(asOfMs)) : PLOT_LEFT;

  const earliestWords = formatArrivalReading(earliest);
  const mostLikelyWords = formatArrivalReading(mostLikely);
  const titleText = `34-kt wind arrival timeline for ${stormName} as of ${formatCompactUtc(asOf)}: earliest reasonable ${earliestWords}; most likely ${mostLikelyWords}`;

  const rows = [
    {
      key: "earliest",
      label: "Earliest 34 kt",
      reading: earliest,
      hasBar: earliestWin,
      words: earliestWords,
      y: 22,
      leadClass: "stroke-sky-400/70 dark:stroke-sky-500/70",
      barClass:
        "fill-sky-500/40 stroke-sky-600 dark:fill-sky-400/40 dark:stroke-sky-400",
    },
    {
      key: "most-likely",
      label: "Most likely 34 kt",
      reading: mostLikely,
      hasBar: mostLikelyWin,
      words: mostLikelyWords,
      y: 48,
      leadClass: "stroke-amber-400/70 dark:stroke-amber-500/70",
      barClass:
        "fill-amber-500/45 stroke-amber-600 dark:fill-amber-400/45 dark:stroke-amber-400",
    },
  ] as const;

  return (
    <div
      className="relative mt-2 overflow-hidden rounded-md border border-slate-200 bg-white px-2.5 py-2 dark:border-slate-800 dark:bg-slate-900"
      data-testid="arrival-timeline"
    >
      <svg
        role="img"
        aria-label={titleText}
        viewBox={`0 0 ${String(VIEW_WIDTH)} ${String(VIEW_HEIGHT)}`}
        className="h-auto w-full max-w-full"
      >
        <title>{titleText}</title>

        <line
          x1={asOfX}
          y1={8}
          x2={asOfX}
          y2={60}
          strokeWidth={1.25}
          strokeDasharray="2 2"
          className="stroke-slate-400 dark:stroke-slate-500"
          data-testid="arrival-as-of-line"
        />
        <text
          x={asOfX}
          y={69}
          textAnchor="start"
          className="fill-slate-500 font-mono text-[9px] dark:fill-slate-400"
        >
          {`As of ${formatCompactUtc(asOf)}`}
        </text>

        {rows.map((row) => {
          const startIso = row.reading.start;
          const endIso = row.reading.end;
          const canDrawBar =
            row.hasBar && startIso !== null && endIso !== null;
          const xStart = canDrawBar ? roundSvg(xScale(startIso)) : asOfX;
          const xEnd = canDrawBar ? roundSvg(xScale(endIso)) : asOfX;
          const barLeft = Math.min(xStart, xEnd);
          const barWidth = Math.max(4, roundSvg(Math.abs(xEnd - xStart)));

          return (
            <g key={row.key} data-testid={`arrival-row-${row.key}`}>
              <text
                x={PLOT_LEFT - 8}
                y={row.y + 4}
                textAnchor="end"
                className="fill-slate-700 text-[10px] font-medium dark:fill-slate-300"
              >
                {row.label}
              </text>

              {canDrawBar ? (
                <g data-testid={`arrival-bar-${row.key}`}>
                  <line
                    x1={asOfX}
                    y1={row.y}
                    x2={barLeft}
                    y2={row.y}
                    strokeWidth={2}
                    className={row.leadClass}
                    data-testid={`arrival-lead-${row.key}`}
                  />
                  <rect
                    x={barLeft}
                    y={row.y - 6}
                    width={barWidth}
                    height={12}
                    rx={2}
                    strokeWidth={1.25}
                    className={row.barClass}
                  />
                </g>
              ) : (
                <text
                  x={PLOT_LEFT + 6}
                  y={row.y + 4}
                  className="fill-slate-600 text-[10px] dark:fill-slate-400"
                  data-testid={`arrival-words-${row.key}`}
                >
                  {`${row.reading.reading}: ${row.words}`}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <table className="sr-only">
        <caption>{titleText}</caption>
        <thead>
          <tr>
            <th scope="col">Variant</th>
            <th scope="col">As of (UTC)</th>
            <th scope="col">Reading</th>
            <th scope="col">Start (UTC)</th>
            <th scope="col">End (UTC)</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Earliest reasonable 34 kt</td>
            <td>{asOf}</td>
            <td>{earliestWords}</td>
            <td>{earliest.start ?? "—"}</td>
            <td>{earliest.end ?? "—"}</td>
          </tr>
          <tr>
            <td>Most likely 34 kt</td>
            <td>{asOf}</td>
            <td>{mostLikelyWords}</td>
            <td>{mostLikely.start ?? "—"}</td>
            <td>{mostLikely.end ?? "—"}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
