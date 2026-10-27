// frontend/src/pages/Storms.tsx
import { useQuery } from "@tanstack/react-query";
import { CloudRainWind, Compass, Wind } from "lucide-react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import {
  formatAgeSeconds,
  formatBearing,
  formatRouteError,
  formatUtc,
} from "./format.ts";

export type StormsResponse = components["schemas"]["StormsResponse"];
export type StormSummaryResponse =
  components["schemas"]["StormSummaryResponse"];
export type OutlookAreaSummaryResponse =
  components["schemas"]["OutlookAreaSummaryResponse"];

async function fetchStorms(): Promise<StormsResponse> {
  const { data, response } = await apiClient.GET("/api/storms");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/storms", response.status);
  }
  return data;
}

function formatOutlookKind(kind: OutlookAreaSummaryResponse["kind"]): string {
  switch (kind) {
    case "development_region":
      return "7-day development region";
    case "two_day_location":
      return "2-day location";
    case "seven_day_location":
      return "7-day location";
    case "development_motion":
      return "development motion";
  }
}

export function Storms() {
  const stormsQuery = useQuery({
    queryKey: queryKeys.storms(),
    queryFn: fetchStorms,
  });

  if (stormsQuery.isError) {
    const status =
      stormsQuery.error instanceof ApiRequestError
        ? stormsQuery.error.status
        : undefined;
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
      >
        {formatRouteError("/api/storms", status)}
      </div>
    );
  }

  if (stormsQuery.isLoading || !stormsQuery.data) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
        Loading NHC storms and outlook…
      </div>
    );
  }

  const { snapshot, storms, outlook, wind_probabilities: windProbs } =
    stormsQuery.data;

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          Storms
        </h1>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          {snapshot ? (
            <>
              Snapshot:{" "}
              <strong className="font-semibold text-slate-800 dark:text-slate-100">
                {snapshot.status}
              </strong>{" "}
              · completed {formatUtc(snapshot.completed_at)} (
              {formatAgeSeconds(snapshot.age_seconds)})
            </>
          ) : (
            "No snapshot stored yet."
          )}
        </p>
      </section>

      <section
        aria-labelledby="active-storms-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center gap-2">
          <CloudRainWind
            className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <h2
            id="active-storms-heading"
            className="text-base font-bold text-slate-900 dark:text-slate-100"
          >
            Active Storms
          </h2>
        </div>

        {storms.length === 0 ? (
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
            No active storm in the latest NHC roster. The tropics are quiet for
            named cyclones.
          </p>
        ) : (
          <div className="mt-4 space-y-4">
            {storms.map((storm) => (
              <StormCard key={storm.atcf_id} storm={storm} />
            ))}
          </div>
        )}
      </section>

      <section
        aria-labelledby="outlook-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center gap-2">
          <Compass
            className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <h2
            id="outlook-heading"
            className="text-base font-bold text-slate-900 dark:text-slate-100"
          >
            Graphical Tropical Weather Outlook
          </h2>
        </div>

        {outlook.length === 0 ? (
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
            No graphical outlook areas in the latest snapshot.
          </p>
        ) : (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {outlook.map((area, idx) => (
              <div
                key={`${area.basin}-${area.kind}-${String(idx)}`}
                className="rounded-md border border-slate-200 bg-slate-50/70 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/40"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-slate-900 dark:text-slate-100">
                    {area.basin}
                  </span>
                  <span className="rounded bg-slate-200/80 px-2 py-0.5 font-medium text-slate-800 dark:bg-slate-700 dark:text-slate-200">
                    {formatOutlookKind(area.kind)}
                  </span>
                </div>
                <div className="mt-2 space-y-1 text-slate-700 dark:text-slate-300">
                  <div>
                    48-hour formation chance:{" "}
                    <strong>
                      {area.chance_2day_pct !== null
                        ? `${String(area.chance_2day_pct)}% (${area.risk_2day?.raw ?? "—"})`
                        : "—"}
                    </strong>
                  </div>
                  <div>
                    7-day formation chance:{" "}
                    <strong>
                      {area.chance_7day_pct !== null
                        ? `${String(area.chance_7day_pct)}% (${area.risk_7day?.raw ?? "—"})`
                        : "—"}
                    </strong>
                  </div>
                  <div className="text-slate-500 dark:text-slate-400">
                    Issued: {formatUtc(area.issued_at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section
        aria-labelledby="wind-prob-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center gap-2">
          <Wind
            className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <h2
            id="wind-prob-heading"
            className="text-base font-bold text-slate-900 dark:text-slate-100"
          >
            5 km Wind-Speed Probabilities
          </h2>
        </div>

        {windProbs.length === 0 ? (
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
            No wind-speed probability products in the latest snapshot.
          </p>
        ) : (
          <div className="mt-3 space-y-2 text-xs">
            <p className="text-slate-600 dark:text-slate-300">
              Synoptic time: {formatUtc(windProbs[0]?.synoptic_at)}
            </p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {windProbs.map((wp) => (
                <div
                  key={wp.threshold_kt}
                  className="rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-800/40"
                >
                  <div className="font-bold text-slate-900 dark:text-slate-100">
                    {String(wp.threshold_kt)} kt threshold
                  </div>
                  <div className="mt-1 text-slate-600 dark:text-slate-300">
                    {String(wp.bands)} probability bands
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function StormCard({ storm }: { readonly storm: StormSummaryResponse }) {
  return (
    <article
      aria-label={`${storm.name} (${storm.atcf_id})`}
      className="rounded-md border border-slate-200 bg-slate-50/70 p-4 text-xs dark:border-slate-800 dark:bg-slate-800/40"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-3 dark:border-slate-700">
        <div>
          <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
            {storm.name} ({storm.atcf_id})
          </h3>
          <p className="mt-0.5 text-slate-600 dark:text-slate-400">
            Classification: <strong>{storm.classification.raw}</strong>
            {storm.slot ? ` · Slot ${storm.slot}` : ""}
            {storm.advisory ? ` · Advisory ${storm.advisory}` : ""}
          </p>
        </div>
        <div className="text-right text-slate-600 dark:text-slate-300">
          {storm.advisory_issued_at && (
            <div>Advisory issued: {formatUtc(storm.advisory_issued_at)}</div>
          )}
          {storm.last_update && (
            <div>Last update: {formatUtc(storm.last_update)}</div>
          )}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="rounded border border-slate-200 bg-white p-2.5 dark:border-slate-700 dark:bg-slate-900">
          <span className="text-slate-500 dark:text-slate-400">
            Maximum winds:{" "}
          </span>
          <strong className="text-slate-900 dark:text-slate-100">
            {storm.intensity_kt !== null && storm.intensity_kt !== undefined
              ? `${String(storm.intensity_kt)} kt`
              : "—"}
          </strong>
        </div>
        <div className="rounded border border-slate-200 bg-white p-2.5 dark:border-slate-700 dark:bg-slate-900">
          <span className="text-slate-500 dark:text-slate-400">
            Min pressure:{" "}
          </span>
          <strong className="text-slate-900 dark:text-slate-100">
            {storm.pressure_mb !== null && storm.pressure_mb !== undefined
              ? `${String(storm.pressure_mb)} mb`
              : "—"}
          </strong>
        </div>
        <div className="rounded border border-slate-200 bg-white p-2.5 dark:border-slate-700 dark:bg-slate-900">
          <span className="text-slate-500 dark:text-slate-400">Movement: </span>
          <strong className="text-slate-900 dark:text-slate-100">
            {storm.movement_dir_deg !== null &&
            storm.movement_dir_deg !== undefined &&
            storm.movement_speed_mph !== null &&
            storm.movement_speed_mph !== undefined
              ? `${formatBearing(storm.movement_dir_deg)} at ${String(storm.movement_speed_mph)} mph`
              : "—"}
          </strong>
        </div>
      </div>

      <div className="mt-3 space-y-1.5 text-slate-700 dark:text-slate-300">
        <p className="font-semibold text-slate-900 dark:text-slate-100">
          Products in snapshot
        </p>
        <p>
          Forecast cone: <strong>{storm.products.cone ? "yes" : "no"}</strong> ·{" "}
          Forecast track: <strong>{storm.products.track ? "yes" : "no"}</strong>{" "}
          · Forecast points:{" "}
          <strong>{String(storm.products.track_points)}</strong> · Watch/warning
          segments:{" "}
          <strong>{String(storm.products.watch_warning_segments)}</strong> ·
          Wind radii: <strong>{String(storm.products.wind_radii)}</strong>
        </p>

        {storm.products.arrival_times.length > 0 && (
          <ul className="list-disc space-y-1 pl-4">
            {storm.products.arrival_times.map((arr) => (
              <li key={`${arr.kind}-${arr.origin}`}>
                <span>
                  {arr.kind === "earliest_reasonable"
                    ? "earliest reasonable arrival times"
                    : "most likely arrival times"}{" "}
                  ({arr.origin}, adv {arr.advisory ?? "?"}, {String(arr.lines)}{" "}
                  {arr.lines === 1 ? "line" : "lines"})
                </span>
                {arr.published_at
                  ? ` · published ${formatUtc(arr.published_at)}`
                  : ""}
                {arr.withheld_reason
                  ? ` — unresolved: ${arr.withheld_reason}`
                  : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}
