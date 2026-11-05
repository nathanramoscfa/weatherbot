// frontend/src/charts/WindProbabilityChart.tsx
import type { components } from "../api/schema.ts";
import {
  type BandPoint,
  bandPath,
  linearScale,
  roundSvg,
  ticksFor,
  timeScale,
  toEpochMs,
} from "./scale.ts";

export type WindReading = components["schemas"]["WindReadingResponse"];

export const WIND_PROBABILITY_CAPTION =
  "The official chance of these winds within 120 hours, as each advisory cycle put it";

export interface WindProbabilityChartProps {
  readonly location: string;
  readonly readings: readonly WindReading[];
}

const THRESHOLDS = [34, 50, 64] as const;
type ThresholdKt = (typeof THRESHOLDS)[number];

const THRESHOLD_META: Readonly<
  Record<
    ThresholdKt,
    {
      readonly label: string;
      readonly fillClass: string;
      readonly strokeClass: string;
    }
  >
> = {
  34: {
    label: "34 kt (TS)",
    fillClass: "fill-sky-500/35 dark:fill-sky-400/35",
    strokeClass: "stroke-sky-600 dark:stroke-sky-400",
  },
  50: {
    label: "50 kt",
    fillClass: "fill-amber-500/35 dark:fill-amber-400/35",
    strokeClass: "stroke-amber-600 dark:stroke-amber-400",
  },
  64: {
    label: "64 kt (Hurr.)",
    fillClass: "fill-red-500/35 dark:fill-red-400/35",
    strokeClass: "stroke-red-600 dark:stroke-red-400",
  },
};

function thresholdMeta(threshold: ThresholdKt) {
  switch (threshold) {
    case 64:
      return THRESHOLD_META[64];
    case 50:
      return THRESHOLD_META[50];
    default:
      return THRESHOLD_META[34];
  }
}

const VIEW_WIDTH = 560;
const VIEW_HEIGHT = 240;
const PLOT_LEFT = 92;
const PLOT_RIGHT = 536;
const ROW_HEIGHT = 56;
const ROW_GAP = 14;
const TOP_OFFSET = 16;

function formatSynopticUtc(epochMs: number): string {
  const d = new Date(epochMs);
  if (Number.isNaN(d.getTime())) {
    return "—";
  }
  const iso = d.toISOString();
  return `${iso.slice(5, 10)} ${iso.slice(11, 16)}Z`;
}

function describeReading(reading: WindReading): string {
  if (reading.reading === "band") {
    if (reading.label !== null && reading.label !== "") {
      return reading.label;
    }
    if (reading.lower_pct !== null && reading.upper_pct !== null) {
      return `${String(reading.lower_pct)}–${String(reading.upper_pct)}%`;
    }
    return "In band";
  }
  if (reading.reading === "below_every_band") {
    return "<5% (below every band)";
  }
  return "Outside coverage";
}

export function WindProbabilityChart({
  location,
  readings,
}: WindProbabilityChartProps) {
  const ordered = [...readings].sort((a, b) => {
    const dt = toEpochMs(a.synoptic_at) - toEpochMs(b.synoptic_at);
    return dt !== 0 ? dt : a.threshold_kt - b.threshold_kt;
  });

  if (ordered.length === 0) {
    return (
      <section
        aria-label={`Wind-speed probabilities for ${location}`}
        className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
        data-testid="wind-probability-empty"
      >
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Wind-speed probabilities · {location}
        </h3>
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
          {WIND_PROBABILITY_CAPTION}
        </p>
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
          No wind-speed probability readings are stored for {location} yet.
          Bands for 34, 50, and 64 kt winds will appear here once an assessment
          with NHC wind-probability products is stored.
        </p>
      </section>
    );
  }

  const synopticTimes = Array.from(
    new Set(ordered.map((r) => toEpochMs(r.synoptic_at))),
  ).sort((a, b) => a - b);
  const firstMs = synopticTimes[0] ?? 0;
  const lastMs = synopticTimes[synopticTimes.length - 1] ?? firstMs;
  const xScale = timeScale([firstMs, lastMs], [PLOT_LEFT + 16, PLOT_RIGHT - 16]);
  const xTicks = ticksFor(
    [firstMs, lastMs],
    synopticTimes.length <= 1 ? 1 : Math.min(3, synopticTimes.length),
  );

  const outsideCount = ordered.filter(
    (r) => r.reading === "outside_coverage",
  ).length;
  const titleText = `Wind-speed probability bands (34, 50, 64 kt) for ${location} across ${String(synopticTimes.length)} synoptic cycle${synopticTimes.length === 1 ? "" : "s"}`;

  return (
    <section
      aria-label={`Wind-speed probabilities for ${location}`}
      className="relative overflow-hidden rounded-xl border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
      data-testid="wind-probability-chart"
    >
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
          Wind-speed probabilities · {location}
        </h3>
        <p
          className="text-xs text-slate-600 dark:text-slate-400"
          data-testid="wind-probability-caption"
        >
          {WIND_PROBABILITY_CAPTION}
        </p>
      </div>

      <svg
        role="img"
        aria-label={titleText}
        viewBox={`0 0 ${String(VIEW_WIDTH)} ${String(VIEW_HEIGHT)}`}
        className="h-auto w-full max-w-full"
      >
        <title>{titleText}</title>

        {THRESHOLDS.map((threshold, rowIdx) => {
          const meta = thresholdMeta(threshold);
          const rowTop = TOP_OFFSET + rowIdx * (ROW_HEIGHT + ROW_GAP);
          const rowBottom = rowTop + ROW_HEIGHT;
          const yScale = linearScale([0, 100], [rowBottom, rowTop]);
          const yGrid5 = roundSvg(yScale(5));
          const yGrid50 = roundSvg(yScale(50));
          const yGrid100 = roundSvg(yScale(100));

          const rowReadings = ordered.filter(
            (r) => r.threshold_kt === threshold,
          );
          const bandPoints: BandPoint[] = [];
          let gapNext = false;
          for (const item of rowReadings) {
            if (item.reading === "outside_coverage") {
              gapNext = true;
              continue;
            }
            const x =
              synopticTimes.length === 1
                ? roundSvg((PLOT_LEFT + PLOT_RIGHT) / 2)
                : roundSvg(xScale(item.synoptic_at));
            if (
              item.reading === "band" &&
              item.lower_pct !== null &&
              item.upper_pct !== null
            ) {
              bandPoints.push({
                x,
                yTop: roundSvg(yScale(item.upper_pct)),
                yBottom: roundSvg(yScale(item.lower_pct)),
                gapBefore: gapNext,
              });
              gapNext = false;
            }
          }
          const connectedBandD = bandPath(bandPoints, 8);

          return (
            <g
              key={threshold}
              data-testid={`wind-row-${String(threshold)}`}
            >
              <line
                x1={PLOT_LEFT}
                y1={rowBottom}
                x2={PLOT_RIGHT}
                y2={rowBottom}
                strokeWidth={1}
                className="stroke-slate-300 dark:stroke-slate-700"
              />
              <line
                x1={PLOT_LEFT}
                y1={yGrid5}
                x2={PLOT_RIGHT}
                y2={yGrid5}
                strokeWidth={0.75}
                strokeDasharray="2 2"
                className="stroke-slate-300 dark:stroke-slate-700"
                data-testid={`wind-gridline-5pct-${String(threshold)}`}
              />
              <line
                x1={PLOT_LEFT}
                y1={yGrid50}
                x2={PLOT_RIGHT}
                y2={yGrid50}
                strokeWidth={0.5}
                className="stroke-slate-200 dark:stroke-slate-800"
              />
              <line
                x1={PLOT_LEFT}
                y1={yGrid100}
                x2={PLOT_RIGHT}
                y2={yGrid100}
                strokeWidth={0.5}
                className="stroke-slate-200 dark:stroke-slate-800"
              />

              <text
                x={PLOT_LEFT - 8}
                y={roundSvg((rowTop + rowBottom) / 2) + 4}
                textAnchor="end"
                className="fill-slate-700 text-[11px] font-semibold dark:fill-slate-300"
              >
                {meta.label}
              </text>
              <text
                x={PLOT_RIGHT + 4}
                y={yGrid5 + 3}
                className="fill-slate-500 font-mono text-[9px] dark:fill-slate-400"
              >
                5%
              </text>

              {connectedBandD !== "" ? (
                <path
                  d={connectedBandD}
                  strokeWidth={1.25}
                  className={`${meta.fillClass} ${meta.strokeClass}`}
                  data-testid={`wind-band-path-${String(threshold)}`}
                />
              ) : null}

              {rowReadings.map((item) => {
                const x =
                  synopticTimes.length === 1
                    ? roundSvg((PLOT_LEFT + PLOT_RIGHT) / 2)
                    : roundSvg(xScale(item.synoptic_at));
                if (item.reading === "outside_coverage") {
                  return null;
                }
                if (item.reading === "below_every_band") {
                  const yBelowTop = yGrid5;
                  const yBelowBottom = roundSvg(rowBottom);
                  const height = Math.max(2, roundSvg(yBelowBottom - yBelowTop));
                  return (
                    <g
                      key={`${String(threshold)}-${item.synoptic_at}`}
                      data-testid={`wind-below-band-${String(threshold)}`}
                    >
                      <rect
                        x={roundSvg(x - 6)}
                        y={yBelowTop}
                        width={12}
                        height={height}
                        rx={1}
                        className="fill-slate-400/50 stroke-slate-500 dark:fill-slate-500/50 dark:stroke-slate-400"
                      />
                      <text
                        x={x}
                        y={yBelowTop - 3}
                        textAnchor="middle"
                        className="fill-slate-600 font-mono text-[9px] dark:fill-slate-400"
                      >
                        {"<5%"}
                      </text>
                    </g>
                  );
                }

                const lower = item.lower_pct ?? 0;
                const upper = item.upper_pct ?? lower;
                const yTop = roundSvg(yScale(upper));
                const yBottom = roundSvg(yScale(lower));
                const barH = Math.max(2, roundSvg(yBottom - yTop));
                return (
                  <g
                    key={`${String(threshold)}-${item.synoptic_at}`}
                    data-testid={`wind-band-${String(threshold)}`}
                  >
                    <rect
                      x={roundSvg(x - 5)}
                      y={yTop}
                      width={10}
                      height={barH}
                      rx={1.5}
                      strokeWidth={1}
                      className={`${meta.fillClass} ${meta.strokeClass}`}
                    />
                    <text
                      x={x}
                      y={Math.max(rowTop + 8, yTop - 3)}
                      textAnchor="middle"
                      className="fill-slate-800 font-mono text-[9px] font-semibold dark:fill-slate-200"
                    >
                      {item.label ?? `${String(lower)}-${String(upper)}%`}
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })}

        {xTicks.map((tickMs, idx) => {
          const x =
            synopticTimes.length === 1
              ? roundSvg((PLOT_LEFT + PLOT_RIGHT) / 2)
              : roundSvg(xScale(tickMs));
          const axisY = TOP_OFFSET + 3 * ROW_HEIGHT + 2 * ROW_GAP;
          return (
            <g key={`${String(tickMs)}-${String(idx)}`}>
              <line
                x1={x}
                y1={axisY}
                x2={x}
                y2={axisY + 5}
                strokeWidth={1}
                className="stroke-slate-300 dark:stroke-slate-700"
              />
              <text
                x={x}
                y={axisY + 18}
                textAnchor="middle"
                className="fill-slate-600 font-mono text-[10px] dark:fill-slate-400"
              >
                {formatSynopticUtc(tickMs)}
              </text>
            </g>
          );
        })}
      </svg>

      {outsideCount > 0 ? (
        <p
          className="mt-2 text-xs text-slate-600 dark:text-slate-400"
          data-testid="wind-outside-coverage-note"
        >
          Note: {String(outsideCount)} reading{outsideCount === 1 ? " is" : "s are"}{" "}
          outside NHC wind-probability coverage and left blank on the axis.
        </p>
      ) : null}

      <table className="sr-only">
        <caption>{`${titleText} — ${WIND_PROBABILITY_CAPTION}`}</caption>
        <thead>
          <tr>
            <th scope="col">Threshold (kt)</th>
            <th scope="col">Synoptic time (UTC)</th>
            <th scope="col">Reading</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((item, idx) => (
            <tr
              key={`${String(item.threshold_kt)}-${item.synoptic_at}-${String(idx)}`}
            >
              <td>{`${String(item.threshold_kt)} kt`}</td>
              <td>{item.synoptic_at}</td>
              <td>{describeReading(item)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
