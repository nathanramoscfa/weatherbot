// frontend/src/assessment/ThreatTable.tsx
import type { components } from "../api/schema.ts";
import { ArrivalTimeline } from "../charts/ArrivalTimeline.tsx";
import {
  formatArrivalReading,
  formatBearing,
  formatBothTimes,
  formatKm,
  formatLeadHours,
  formatUtc,
  formatWindProbability,
} from "../pages/format.ts";

type StormThreatResponse = components["schemas"]["StormThreatResponse"];
type WindReadingResponse = components["schemas"]["WindReadingResponse"];

export interface ThreatTableProps {
  readonly threats: readonly StormThreatResponse[];
  readonly windProbabilities: readonly WindReadingResponse[];
  readonly asOf: string;
  readonly timeZone: string | null | undefined;
}

export function ThreatTable({
  threats,
  windProbabilities,
  asOf,
  timeZone,
}: ThreatTableProps) {
  if (threats.length === 0 && windProbabilities.length === 0) {
    return null;
  }

  return (
    <>
      {threats.length > 0 && (
        <div className="space-y-2 text-xs">
          <h3 className="font-semibold text-slate-900 dark:text-slate-100">
            Storm threats
          </h3>
          <div className="space-y-2">
            {threats.map((threat) => (
              <div
                key={threat.atcf_id}
                className="rounded-md border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-800/40"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold text-slate-900 dark:text-slate-100">
                    {threat.storm_name} ({threat.atcf_id}) · Advisory{" "}
                    {threat.advisory}
                  </span>
                  <span className="rounded bg-slate-200/80 px-2 py-0.5 font-medium text-slate-800 dark:bg-slate-700 dark:text-slate-200">
                    {threat.development}
                    {threat.category !== null && threat.category !== undefined
                      ? ` (Category ${String(threat.category)})`
                      : ""}
                  </span>
                </div>
                <div className="mt-1.5 grid grid-cols-1 gap-1 text-slate-700 sm:grid-cols-2 dark:text-slate-300">
                  <div>
                    Cone:{" "}
                    <strong>
                      {threat.in_cone === true
                        ? "inside its cone"
                        : threat.in_cone === false
                          ? "outside its cone"
                          : "no usable cone"}
                    </strong>
                  </div>
                  <div>
                    Current center:{" "}
                    {threat.distance_km !== null
                      ? formatKm(threat.distance_km)
                      : "—"}{" "}
                    at{" "}
                    {threat.bearing_deg !== null
                      ? formatBearing(threat.bearing_deg)
                      : "—"}
                  </div>
                  <div className="sm:col-span-2">
                    Closest approach:{" "}
                    {threat.closest_approach_km !== null
                      ? formatKm(threat.closest_approach_km)
                      : "—"}{" "}
                    at {formatBothTimes(threat.closest_approach_at, timeZone)}{" "}
                    (lead{" "}
                    {threat.lead_h !== null
                      ? formatLeadHours(threat.lead_h)
                      : "—"}
                    {threat.hurricane_by_approach
                      ? ", hurricane by approach"
                      : ""}
                    )
                  </div>
                  <div className="sm:col-span-2">
                    Earliest reasonable 34-kt arrival:{" "}
                    {formatArrivalReading(threat.earliest_arrival, timeZone)}
                  </div>
                  <div className="sm:col-span-2">
                    Most likely 34-kt arrival:{" "}
                    {formatArrivalReading(threat.most_likely_arrival, timeZone)}
                  </div>
                </div>
                <ArrivalTimeline
                  asOf={asOf}
                  stormName={threat.storm_name}
                  earliest={threat.earliest_arrival}
                  mostLikely={threat.most_likely_arrival}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {windProbabilities.length > 0 && (
        <div className="space-y-1.5 text-xs">
          <h3 className="font-semibold text-slate-900 dark:text-slate-100">
            5 km wind-speed probabilities (synoptic{" "}
            {formatUtc(windProbabilities[0]?.synoptic_at)})
          </h3>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {windProbabilities.map((wp) => (
              <div
                key={wp.threshold_kt}
                className="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 dark:border-slate-800 dark:bg-slate-800/40"
              >
                <span className="font-semibold text-slate-900 dark:text-slate-100">
                  {String(wp.threshold_kt)} kt:{" "}
                </span>
                <span className="text-slate-700 dark:text-slate-300">
                  {formatWindProbability(wp)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
