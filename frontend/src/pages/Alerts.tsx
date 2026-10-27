// frontend/src/pages/Alerts.tsx
import { useQuery } from "@tanstack/react-query";
import { BellRing, ShieldAlert } from "lucide-react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import {
  formatAgeSeconds,
  formatBothTimes,
  formatKm,
  formatRouteError,
  formatUtc,
} from "./format.ts";

export type AlertsResponse = components["schemas"]["AlertsResponse"];
export type LocationAlertsGroupResponse =
  components["schemas"]["LocationAlertsGroupResponse"];
export type LocationAlertResponse =
  components["schemas"]["LocationAlertResponse"];
export type WatchWarningSegmentResponse =
  components["schemas"]["WatchWarningSegmentResponse"];

async function fetchAlerts(): Promise<AlertsResponse> {
  const { data, response } = await apiClient.GET("/api/alerts");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/alerts", response.status);
  }
  return data;
}

function formatTcww(code: string): string {
  switch (code) {
    case "HWR":
      return "Hurricane Warning (HWR)";
    case "HWA":
      return "Hurricane Watch (HWA)";
    case "TWR":
      return "Tropical Storm Warning (TWR)";
    case "TWA":
      return "Tropical Storm Watch (TWA)";
    case "TRW":
      return "Tropical Storm Warning (TRW)";
    case "TRA":
      return "Tropical Storm Watch (TRA)";
    default:
      return code;
  }
}

function formatFoundBy(
  foundBy: LocationAlertResponse["found_by"],
): string {
  return foundBy
    .map((q) => (q.kind === "point" ? "the point" : q.zone_id ?? "zone"))
    .join(", ");
}

export function Alerts() {
  const alertsQuery = useQuery({
    queryKey: queryKeys.alerts(),
    queryFn: fetchAlerts,
  });

  if (alertsQuery.isError) {
    const status =
      alertsQuery.error instanceof ApiRequestError
        ? alertsQuery.error.status
        : undefined;
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
      >
        {formatRouteError("/api/alerts", status)}
      </div>
    );
  }

  if (alertsQuery.isLoading || !alertsQuery.data) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
        Loading official NWS alerts and NHC watch-warning segments…
      </div>
    );
  }

  const { snapshot, locations } = alertsQuery.data;

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          Alerts
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

      {locations.length === 0 ? (
        <section className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-xs dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
          No watched locations configured.
        </section>
      ) : (
        <div className="space-y-5">
          {locations.map((locItem) => (
            <LocationAlertsCard
              key={locItem.location.name}
              item={locItem}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function LocationAlertsCard({
  item,
}: {
  readonly item: LocationAlertsGroupResponse;
}) {
  const { location, alerts, watch_warnings: segments, note } = item;
  const timeZone = location.time_zone;
  const coveringAlerts = alerts?.filter((a) => a.covers) ?? [];
  const contextAlerts =
    alerts?.filter((a) => !a.covers || a.is_county_context) ?? [];

  return (
    <article
      aria-label={location.name}
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-3 dark:border-slate-800">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <BellRing
              className="h-4 w-4 shrink-0 text-sky-600 dark:text-sky-400"
              aria-hidden="true"
            />
            <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">
              {location.name}
            </h2>
            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
              {location.inside_nws_coverage
                ? "Inside NWS coverage"
                : "Outside NWS coverage"}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
            Time zone: {timeZone ?? "UTC"}
            {location.forecast_zone
              ? ` · Forecast zone: ${location.forecast_zone}`
              : ""}
            {location.county_zone
              ? ` · County zone: ${location.county_zone}`
              : ""}
          </p>
        </div>
      </div>

      {note && (
        <p className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700 dark:border-slate-800 dark:bg-slate-800/50 dark:text-slate-300">
          {note}
        </p>
      )}

      {alerts !== null && (
        <div className="mt-4 space-y-4">
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-300">
              Covering NWS Alerts
            </h3>
            {coveringAlerts.length === 0 ? (
              <p className="text-xs text-slate-600 dark:text-slate-400">
                No active NWS alert covers {location.name}.
              </p>
            ) : (
              <div className="space-y-2.5">
                {coveringAlerts.map((alert) => (
                  <NwsAlertBlock
                    key={alert.id}
                    alert={alert}
                    timeZone={timeZone}
                  />
                ))}
              </div>
            )}
          </div>

          {contextAlerts.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-300">
                County-zone alerts outside this location&apos;s zones (context
                only — never sets the threat level)
              </h3>
              <div className="space-y-2.5">
                {contextAlerts.map((alert) => (
                  <NwsAlertBlock
                    key={alert.id}
                    alert={alert}
                    timeZone={timeZone}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="mt-4 space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-700 dark:text-slate-300">
          NHC Watch-Warning Segments
        </h3>
        {segments.length === 0 ? (
          <p className="text-xs text-slate-600 dark:text-slate-400">
            No NHC watch-warning segment covers this location.
          </p>
        ) : (
          <div className="space-y-2">
            {segments.map((seg, idx) => (
              <SegmentBlock
                key={`${seg.atcf_id}-${seg.tcww.raw}-${String(idx)}`}
                segment={seg}
                timeZone={timeZone}
              />
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function NwsAlertBlock({
  alert,
  timeZone,
}: {
  readonly alert: LocationAlertResponse;
  readonly timeZone: string | null;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/40">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 font-bold text-slate-900 dark:text-slate-100">
          <ShieldAlert
            className="h-4 w-4 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <span>{alert.event}</span>
          {alert.sender_name ? (
            <span className="font-normal text-slate-600 dark:text-slate-400">
              · {alert.sender_name}
            </span>
          ) : null}
        </div>
        <span
          className={`rounded px-2 py-0.5 font-medium ${
            alert.covers
              ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-950/70 dark:text-emerald-200"
              : "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-200"
          }`}
        >
          {alert.covers
            ? "Covers this location"
            : "Does not cover this location (context)"}
        </span>
      </div>

      {alert.headline && (
        <p className="mt-1.5 font-medium text-slate-800 dark:text-slate-200">
          {alert.headline}
        </p>
      )}

      <p className="mt-1 text-slate-700 dark:text-slate-300">
        {alert.covers ? "Covers this location: " : "Does not cover this location: "}
        {alert.coverage}
      </p>

      <div className="mt-2 grid grid-cols-1 gap-1 text-slate-600 sm:grid-cols-2 dark:text-slate-400">
        <div>
          Effective: {formatBothTimes(alert.effective, timeZone)}
        </div>
        <div>
          Expires: {formatBothTimes(alert.expires, timeZone)}
        </div>
        <div>
          Severity: <strong>{alert.severity.raw}</strong> · Urgency:{" "}
          <strong>{alert.urgency.raw}</strong> · Certainty:{" "}
          <strong>{alert.certainty.raw}</strong>
        </div>
        <div>Found by: {formatFoundBy(alert.found_by)}</div>
        {alert.affected_zone_ids.length > 0 && (
          <div className="sm:col-span-2">
            Affected zones: {alert.affected_zone_ids.join(", ")}
          </div>
        )}
        {alert.vtec.length > 0 && (
          <div className="sm:col-span-2 font-mono text-[11px]">
            VTEC: {alert.vtec.join(", ")}
          </div>
        )}
      </div>
    </div>
  );
}

function SegmentBlock({
  segment,
  timeZone,
}: {
  readonly segment: WatchWarningSegmentResponse;
  readonly timeZone: string | null;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/40">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-bold text-slate-900 dark:text-slate-100">
          {segment.storm_name} ({segment.atcf_id}) ·{" "}
          {formatTcww(segment.tcww.raw)} · Advisory {segment.advisory ?? "?"}
        </span>
        <span className="rounded bg-slate-200 px-2 py-0.5 font-medium text-slate-800 dark:bg-slate-700 dark:text-slate-200">
          {segment.covers ? "covers location" : "does not cover it"}
        </span>
      </div>
      <div className="mt-1 space-y-0.5 text-slate-700 dark:text-slate-300">
        {segment.coverage && <div>Coverage: {segment.coverage}</div>}
        {segment.distance_km !== null && segment.distance_km !== undefined && (
          <div>
            Distance: {formatKm(segment.distance_km)}
            {segment.at_end ? " (at its end)" : ""}
          </div>
        )}
        {segment.breakpoints.length > 0 && (
          <div>Breakpoints: {segment.breakpoints.join(" to ")}</div>
        )}
        {segment.issued_at && (
          <div className="text-slate-500 dark:text-slate-400">
            Issued: {formatBothTimes(segment.issued_at, timeZone)}
          </div>
        )}
      </div>
    </div>
  );
}
