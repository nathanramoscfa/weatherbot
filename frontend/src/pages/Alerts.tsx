// frontend/src/pages/Alerts.tsx
import { useQuery } from "@tanstack/react-query";
import { BellRing, ShieldAlert } from "lucide-react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { Card } from "../ui/Card.tsx";
import { Disclosure } from "../ui/Disclosure.tsx";
import { PageHeader } from "../ui/PageHeader.tsx";
import {
  formatAgeSeconds,
  formatBothTimes,
  formatFriendlyLocal,
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

export function tcwwPlainName(code: string): string {
  switch (code) {
    case "HWR":
      return "Hurricane Warning";
    case "HWA":
      return "Hurricane Watch";
    case "TWR":
    case "TRW":
      return "Tropical Storm Warning";
    case "TWA":
    case "TRA":
      return "Tropical Storm Watch";
    default:
      return code;
  }
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

function formatRelativeSpan(
  iso: string | null | undefined,
  referenceIso: string | null | undefined,
): string | null {
  if (!iso || !referenceIso) {
    return null;
  }
  const targetMs = new Date(iso).getTime();
  const refMs = new Date(referenceIso).getTime();
  if (!Number.isFinite(targetMs) || !Number.isFinite(refMs)) {
    return null;
  }
  const deltaSeconds = Math.round((targetMs - refMs) / 1000);
  if (deltaSeconds <= 0) {
    return formatAgeSeconds(Math.abs(deltaSeconds));
  }
  if (deltaSeconds < 60) {
    return `in ${String(deltaSeconds)} s`;
  }
  const minutes = Math.floor(deltaSeconds / 60);
  if (minutes < 60) {
    return `in ${String(minutes)} min`;
  }
  const hours = Math.floor(minutes / 60);
  const remMinutes = minutes % 60;
  if (remMinutes === 0) {
    return `in ${String(hours)} h`;
  }
  return `in ${String(hours)} h ${String(remMinutes)} min`;
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
      <Card as="section">
        <PageHeader
          title="Alerts"
          summary={
            snapshot ? (
              <>
                Snapshot:{" "}
                <strong className="font-semibold text-ink">
                  {snapshot.status}
                </strong>{" "}
                · {formatAgeSeconds(snapshot.age_seconds)} (
                {formatFriendlyLocal(snapshot.completed_at) ??
                  formatUtc(snapshot.completed_at)}
                ) ·{" "}
                <span className="text-caption text-ink-subtle">
                  {formatUtc(snapshot.completed_at)}
                </span>
              </>
            ) : (
              "No snapshot stored yet."
            )
          }
        />
      </Card>

      {locations.length === 0 ? (
        <Card as="section" className="text-sm text-ink-muted">
          No watched locations configured. Add a watched location in Settings to
          monitor official NWS alerts and NHC coastal watch-warning segments on
          each cycle.
        </Card>
      ) : (
        <div className="space-y-5">
          {locations.map((locItem) => (
            <LocationAlertsCard
              key={locItem.location.name}
              item={locItem}
              snapshotCompletedAt={snapshot?.completed_at}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function LocationAlertsCard({
  item,
  snapshotCompletedAt,
}: {
  readonly item: LocationAlertsGroupResponse;
  readonly snapshotCompletedAt: string | undefined;
}) {
  const { location, alerts, watch_warnings: segments, note } = item;
  const timeZone = location.time_zone;
  const coveringAlerts = alerts?.filter((a) => a.covers) ?? [];
  const contextAlerts =
    alerts?.filter((a) => !a.covers || a.is_county_context) ?? [];

  return (
    <Card as="article" aria-label={location.name}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <BellRing
              className="h-4 w-4 shrink-0 text-brand"
              aria-hidden="true"
            />
            <h2 className="text-base font-bold text-ink">{location.name}</h2>
            <span className="rounded-pill border border-line bg-surface-inset px-2 py-0.5 text-caption font-medium text-ink">
              {location.inside_nws_coverage
                ? "Inside NWS coverage"
                : "Outside NWS coverage"}
            </span>
          </div>
          <p className="mt-1 text-sm text-ink-muted">
            Local time zone: {timeZone ?? "UTC"}
          </p>
        </div>
      </div>

      {note && (
        <p className="mt-3 rounded-card border border-line bg-surface-inset px-3 py-2 text-sm text-ink-muted">
          {note}
        </p>
      )}

      {alerts !== null && (
        <div className="mt-4 space-y-4">
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-ink">
              Covering NWS Alerts
            </h3>
            {coveringAlerts.length === 0 ? (
              <p className="text-sm text-ink-muted">
                No active NWS alert covers {location.name}. When the National
                Weather Service issues a watch, warning, or statement covering
                this location&apos;s point or zone, its event, headline, and
                expiry will appear here on the next monitor cycle.
              </p>
            ) : (
              <div className="space-y-2.5">
                {coveringAlerts.map((alert) => (
                  <NwsAlertBlock
                    key={alert.id}
                    alert={alert}
                    locationName={location.name}
                    timeZone={timeZone}
                    snapshotCompletedAt={snapshotCompletedAt}
                  />
                ))}
              </div>
            )}
          </div>

          {contextAlerts.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-ink">
                County-zone alerts outside this location&apos;s zones (context
                only — never sets the threat level)
              </h3>
              <div className="space-y-2.5">
                {contextAlerts.map((alert) => (
                  <NwsAlertBlock
                    key={alert.id}
                    alert={alert}
                    locationName={location.name}
                    timeZone={timeZone}
                    snapshotCompletedAt={snapshotCompletedAt}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="mt-4 space-y-2">
        <h3 className="text-sm font-semibold text-ink">
          NHC Watch-Warning Segments
        </h3>
        {segments.length === 0 ? (
          <p className="text-sm text-ink-muted">
            No NHC watch-warning segment covers this location. When the National
            Hurricane Center places a coastal hurricane or tropical storm watch
            or warning segment within reach of {location.name}, it will appear
            here on the next advisory.
          </p>
        ) : (
          <div className="space-y-2">
            {segments.map((seg, idx) => (
              <SegmentBlock
                key={`${seg.atcf_id}-${seg.tcww.raw}-${String(idx)}`}
                segment={seg}
                locationName={location.name}
                timeZone={timeZone}
                snapshotCompletedAt={snapshotCompletedAt}
              />
            ))}
          </div>
        )}
      </div>

      {(location.forecast_zone !== null || location.county_zone !== null) && (
        <div className="mt-3">
          <Disclosure summary="Location NWS zone identifiers">
            <p className="text-sm text-ink-muted">
              Time zone: <code className="font-mono text-ink">{timeZone ?? "UTC"}</code>
              {location.forecast_zone
                ? ` · Forecast zone: ${location.forecast_zone}`
                : ""}
              {location.county_zone
                ? ` · County zone: ${location.county_zone}`
                : ""}
            </p>
          </Disclosure>
        </div>
      )}
    </Card>
  );
}

function NwsAlertBlock({
  alert,
  locationName,
  timeZone,
  snapshotCompletedAt,
}: {
  readonly alert: LocationAlertResponse;
  readonly locationName: string;
  readonly timeZone: string | null;
  readonly snapshotCompletedAt: string | undefined;
}) {
  const expiresRelative = formatRelativeSpan(
    alert.expires,
    snapshotCompletedAt ?? alert.effective,
  );
  const expiresLocal =
    formatFriendlyLocal(alert.expires, timeZone) ?? formatUtc(alert.expires);

  return (
    <div className="space-y-2.5 rounded-card border border-line bg-surface-inset p-3.5 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 font-bold text-ink">
          <ShieldAlert
            className="h-4 w-4 shrink-0 text-brand"
            aria-hidden="true"
          />
          <span>{alert.event}</span>
          <span className="font-normal text-ink-muted">
            for {locationName}
          </span>
          {alert.sender_name ? (
            <span className="font-normal text-ink-subtle">
              · {alert.sender_name}
            </span>
          ) : null}
        </div>
        <span
          className={`rounded-pill px-2.5 py-0.5 text-caption font-medium ${
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
        <p className="font-medium text-ink">{alert.headline}</p>
      )}

      <p className="text-ink-muted">
        {alert.covers
          ? "Covers this location: "
          : "Does not cover this location: "}
        {alert.coverage}
      </p>

      <p className="text-ink-muted">
        <span className="font-semibold text-ink">Expires:</span>{" "}
        {expiresRelative ? `${expiresRelative} · ` : ""}
        {expiresLocal}{" "}
        <span className="text-caption text-ink-subtle">
          ({formatUtc(alert.expires)})
        </span>
      </p>

      <Disclosure summary="Alert codes, zones & provenance">
        <div className="grid grid-cols-1 gap-1.5 text-ink-muted sm:grid-cols-2">
          <div>Effective: {formatBothTimes(alert.effective, timeZone)}</div>
          <div>Expires: {formatBothTimes(alert.expires, timeZone)}</div>
          <div>
            Severity: <strong className="text-ink">{alert.severity.raw}</strong>{" "}
            · Urgency: <strong className="text-ink">{alert.urgency.raw}</strong>{" "}
            · Certainty:{" "}
            <strong className="text-ink">{alert.certainty.raw}</strong>
          </div>
          <div>Found by: {formatFoundBy(alert.found_by)}</div>
          {alert.affected_zone_ids.length > 0 && (
            <div className="sm:col-span-2">
              Affected zones: {alert.affected_zone_ids.join(", ")}
            </div>
          )}
          {alert.vtec.length > 0 && (
            <div className="break-all font-mono text-sm sm:col-span-2">
              VTEC: {alert.vtec.join(", ")}
            </div>
          )}
        </div>
      </Disclosure>
    </div>
  );
}

function SegmentBlock({
  segment,
  locationName,
  timeZone,
  snapshotCompletedAt,
}: {
  readonly segment: WatchWarningSegmentResponse;
  readonly locationName: string;
  readonly timeZone: string | null;
  readonly snapshotCompletedAt: string | undefined;
}) {
  const plainName = tcwwPlainName(segment.tcww.raw);
  const issuedRelative = formatRelativeSpan(
    segment.issued_at,
    snapshotCompletedAt,
  );
  const issuedLocal = segment.issued_at
    ? (formatFriendlyLocal(segment.issued_at, timeZone) ??
      formatUtc(segment.issued_at))
    : null;

  return (
    <div className="space-y-2 rounded-card border border-line bg-surface-inset p-3.5 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-bold text-ink">
          {plainName} — {segment.storm_name} for {locationName}
        </span>
        <span className="rounded-pill border border-line bg-surface-card px-2.5 py-0.5 text-caption font-medium text-ink">
          {segment.covers ? "covers location" : "does not cover it"}
        </span>
      </div>

      {segment.coverage && (
        <p className="text-ink-muted">Coverage: {segment.coverage}</p>
      )}

      {issuedLocal && (
        <p className="text-ink-subtle">
          Issued {issuedRelative ? `${issuedRelative} · ` : ""}
          {issuedLocal}
        </p>
      )}

      <Disclosure summary="Segment code, breakpoints & distance">
        <div className="space-y-1 text-ink-muted">
          <div className="font-medium text-ink">
            {segment.storm_name} ({segment.atcf_id}) ·{" "}
            {formatTcww(segment.tcww.raw)} · Advisory {segment.advisory ?? "?"}
          </div>
          {segment.distance_km !== null &&
            segment.distance_km !== undefined && (
              <div>
                Distance: {formatKm(segment.distance_km)}
                {segment.at_end ? " (at its end)" : ""}
              </div>
            )}
          {segment.breakpoints.length > 0 && (
            <div>Breakpoints: {segment.breakpoints.join(" to ")}</div>
          )}
          {segment.issued_at && (
            <div className="text-ink-subtle">
              Issued: {formatBothTimes(segment.issued_at, timeZone)}
            </div>
          )}
        </div>
      </Disclosure>
    </div>
  );
}
