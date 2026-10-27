// frontend/src/pages/Dashboard.tsx
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, RefreshCw, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { ThreatLevelBadge } from "../app/ThreatLevelBadge.tsx";
import {
  STREAM_EVENT_DOM_NAME,
  type StreamEvent,
} from "../events/useEventStream.ts";
import {
  formatAgeSeconds,
  formatArrivalReading,
  formatBearing,
  formatBothTimes,
  formatBreakpointSpan,
  formatKm,
  formatLeadHours,
  formatRouteError,
  formatUtc,
  formatWindProbability,
} from "./format.ts";

export type AssessmentsResponse =
  components["schemas"]["AssessmentsResponse"];
export type LocationsResponse = components["schemas"]["LocationsResponse"];
export type HealthResponse = components["schemas"]["HealthResponse"];
export type DisclaimerResponse = components["schemas"]["DisclaimerResponse"];
export type LocationAssessmentResponse =
  components["schemas"]["LocationAssessmentResponse"];

const FALLBACK_ESSENTIALS =
  "Weatherbot is informational only. It is never a substitute for official guidance from the National Hurricane Center (NHC), your local National Weather Service (NWS) Weather Forecast Office, or your local emergency management agency.";

async function fetchAssessments(): Promise<AssessmentsResponse> {
  const { data, response } = await apiClient.GET("/api/assessments");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/assessments", response.status);
  }
  return data;
}

async function fetchLocations(): Promise<LocationsResponse> {
  const { data, response } = await apiClient.GET("/api/locations");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/locations", response.status);
  }
  return data;
}

async function fetchHealth(): Promise<HealthResponse> {
  const { data, response } = await apiClient.GET("/api/health");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/health", response.status);
  }
  return data;
}

async function fetchDisclaimer(): Promise<DisclaimerResponse> {
  const { data, response } = await apiClient.GET("/api/disclaimer");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/disclaimer", response.status);
  }
  return data;
}

export function Dashboard() {
  const queryClient = useQueryClient();
  const [cycleRunning, setCycleRunning] = useState(false);
  const [cycleMessage, setCycleMessage] = useState<{
    kind: "info" | "error";
    text: string;
  } | null>(null);
  const [evacPendingName, setEvacPendingName] = useState<string | null>(null);
  const [evacError, setEvacError] = useState<string | null>(null);

  const assessmentsQuery = useQuery({
    queryKey: queryKeys.assessments(),
    queryFn: fetchAssessments,
  });

  const locationsQuery = useQuery({
    queryKey: queryKeys.locations(),
    queryFn: fetchLocations,
  });

  const healthQuery = useQuery({
    queryKey: queryKeys.health(),
    queryFn: fetchHealth,
    enabled: false,
  });

  const disclaimerQuery = useQuery({
    queryKey: queryKeys.disclaimer(),
    queryFn: fetchDisclaimer,
  });

  useEffect(() => {
    const handleStreamEvent = (evt: Event) => {
      const custom = evt as CustomEvent<StreamEvent>;
      if (custom.detail.kind === "cycle") {
        setCycleRunning(false);
        setCycleMessage(null);
      }
    };
    window.addEventListener(STREAM_EVENT_DOM_NAME, handleStreamEvent);
    return () => {
      window.removeEventListener(STREAM_EVENT_DOM_NAME, handleStreamEvent);
    };
  }, []);

  const handleCheckNow = async () => {
    setCycleRunning(true);
    setCycleMessage(null);
    try {
      const { response } = await apiClient.POST("/api/cycles", {
        body: {},
      });
      if (response.status === 202) {
        setCycleMessage({
          kind: "info",
          text: "Monitor cycle started. Waiting for cycle completion…",
        });
        return;
      }
      setCycleRunning(false);
      if (response.status === 409) {
        setCycleMessage({
          kind: "error",
          text: "Another monitor cycle is already running (/api/cycles returned HTTP 409).",
        });
      } else if (response.status === 429) {
        setCycleMessage({
          kind: "error",
          text: "Please wait before starting another manual check (/api/cycles returned HTTP 429).",
        });
      } else {
        setCycleMessage({
          kind: "error",
          text: formatRouteError("/api/cycles", response.status),
        });
      }
    } catch {
      setCycleRunning(false);
      setCycleMessage({
        kind: "error",
        text: formatRouteError("/api/cycles"),
      });
    }
  };

  const handleEvacuationToggle = async (
    locationName: string,
    nextOn: boolean,
  ) => {
    setEvacPendingName(locationName);
    setEvacError(null);
    try {
      const { response } = await apiClient.PUT("/api/locations/evacuation", {
        body: { location: locationName, on: nextOn },
      });
      if (!response.ok) {
        setEvacError(
          formatRouteError("/api/locations/evacuation", response.status),
        );
        return;
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.locations() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.assessments() }),
      ]);
    } catch {
      setEvacError(formatRouteError("/api/locations/evacuation"));
    } finally {
      setEvacPendingName(null);
    }
  };

  if (assessmentsQuery.isError) {
    const status =
      assessmentsQuery.error instanceof ApiRequestError
        ? assessmentsQuery.error.status
        : undefined;
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
      >
        {formatRouteError("/api/assessments", status)}
      </div>
    );
  }

  if (locationsQuery.isError) {
    const status =
      locationsQuery.error instanceof ApiRequestError
        ? locationsQuery.error.status
        : undefined;
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
      >
        {formatRouteError("/api/locations", status)}
      </div>
    );
  }

  if (assessmentsQuery.isLoading || locationsQuery.isLoading) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
        Loading threat assessments…
      </div>
    );
  }

  const assessmentsData = assessmentsQuery.data;
  const locationsData = locationsQuery.data;
  const locationCards = assessmentsData?.locations ?? [];
  const watchedLocations = locationsData?.locations ?? [];

  if (locationCards.length === 0 && watchedLocations.length === 0) {
    const essentialsList = disclaimerQuery.data?.essentials;
    const essentials =
      essentialsList && essentialsList.length > 0
        ? essentialsList.join("\n")
        : FALLBACK_ESSENTIALS;
    return (
      <section
        aria-labelledby="empty-dashboard-heading"
        className="space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-start gap-3">
          <ShieldAlert
            className="mt-0.5 h-6 w-6 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <div className="space-y-2">
            <h1
              id="empty-dashboard-heading"
              className="text-lg font-semibold text-slate-900 dark:text-slate-100"
            >
              No watched locations configured
            </h1>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Add a location in Settings to monitor official NHC and NWS
              products and compute threat levels.
            </p>
          </div>
        </div>

        <div className="rounded-md border border-amber-300 bg-amber-50/80 p-4 text-xs leading-relaxed text-amber-950 dark:border-amber-700/80 dark:bg-amber-950/50 dark:text-amber-100">
          <p className="font-semibold uppercase tracking-wide">
            Disclaimer essentials
          </p>
          <p className="mt-1 whitespace-pre-line">{essentials}</p>
        </div>

        <div>
          <Link
            to="/settings"
            className="inline-flex items-center rounded-md bg-sky-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-sky-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:bg-sky-500 dark:text-slate-950"
          >
            Add your first location in Settings
          </Link>
        </div>
      </section>
    );
  }

  const snapshot = assessmentsData?.snapshot ?? null;
  const nextProductAt = healthQuery.data?.next_product_at ?? null;
  const liveAnnouncement = locationCards
    .map((item) => {
      if (!item.assessment) {
        return `${item.name}: no stored assessment.`;
      }
      const prefix = item.assessment.complete ? "" : "At least ";
      return `${item.name}: ${prefix}Level ${String(item.assessment.level.number)}, ${item.assessment.level.label}. Decided by ${item.assessment.rule}.`;
    })
    .join(" ");

  return (
    <div className="space-y-5">
      <div
        aria-live="polite"
        aria-atomic="true"
        data-testid="level-live-region"
        className="sr-only"
      >
        {liveAnnouncement}
      </div>

      <section
        aria-label="Monitor cycle controls"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div className="space-y-1">
            <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              Dashboard
            </h1>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-300">
              {snapshot ? (
                <span>
                  Snapshot:{" "}
                  <strong className="font-semibold text-slate-800 dark:text-slate-100">
                    {snapshot.status}
                  </strong>{" "}
                  · completed {formatUtc(snapshot.completed_at)} (
                  {formatAgeSeconds(snapshot.age_seconds)})
                </span>
              ) : (
                <span>No snapshot stored yet.</span>
              )}
              {nextProductAt && (
                <span>
                  Next NHC product:{" "}
                  <strong className="font-semibold text-slate-800 dark:text-slate-100">
                    {formatUtc(nextProductAt)}
                  </strong>
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleCheckNow()}
              disabled={cycleRunning}
              className="inline-flex items-center gap-1.5 rounded-md bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-sky-500 dark:text-slate-950"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${cycleRunning ? "animate-spin" : ""}`}
                aria-hidden="true"
              />
              <span>Check now</span>
            </button>
          </div>
        </div>

        {cycleMessage && (
          <div
            role={cycleMessage.kind === "error" ? "alert" : "status"}
            className={`mt-3 rounded-md border px-3 py-2 text-xs ${
              cycleMessage.kind === "error"
                ? "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
                : "border-sky-300 bg-sky-50 text-sky-900 dark:border-sky-800 dark:bg-sky-950/60 dark:text-sky-200"
            }`}
          >
            {cycleMessage.text}
          </div>
        )}

        {evacError && (
          <div
            role="alert"
            className="mt-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
          >
            {evacError}
          </div>
        )}
      </section>

      <div className="space-y-5">
        {locationCards.map((loc) => (
          <LocationLevelCard
            key={loc.name}
            item={loc}
            evacPending={evacPendingName === loc.name}
            onToggleEvacuation={(nextOn) =>
              void handleEvacuationToggle(loc.name, nextOn)
            }
          />
        ))}
      </div>
    </div>
  );
}

interface LocationLevelCardProps {
  readonly item: LocationAssessmentResponse;
  readonly evacPending: boolean;
  readonly onToggleEvacuation: (nextOn: boolean) => void;
}

function LocationLevelCard({
  item,
  evacPending,
  onToggleEvacuation,
}: LocationLevelCardProps) {
  const { assessment, time_zone: timeZone } = item;
  const coveringOfficial =
    assessment?.official.filter((p) => p.covers && !p.is_county_context) ?? [];
  const contextAlerts =
    assessment?.official.filter((p) => p.is_county_context || !p.covers) ?? [];

  return (
    <article
      aria-label={item.name}
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex flex-col justify-between gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-start dark:border-slate-800">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-bold text-slate-900 sm:text-lg dark:text-slate-100">
              {item.name}
            </h2>
            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
              {item.inside_nws_coverage
                ? "Inside NWS coverage"
                : "Outside NWS coverage"}
            </span>
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-400">
            Time zone: {timeZone ?? "UTC"} · Breakpoint span:{" "}
            {formatBreakpointSpan(
              assessment?.breakpoint_span ?? item.breakpoint_span,
            )}
          </p>
        </div>

        {assessment && (
          <div className="flex flex-col items-start gap-1 sm:items-end">
            <ThreatLevelBadge
              level={assessment.level.number}
              atLeast={!assessment.complete}
            />
            <span className="text-xs text-slate-600 dark:text-slate-400">
              Assessed: {formatBothTimes(assessment.as_of, timeZone)}
            </span>
          </div>
        )}
      </div>

      {!assessment ? (
        <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">
          No assessment stored yet for {item.name}. Press Check now to fetch
          NHC and NWS products.
        </p>
      ) : (
        <div className="mt-4 space-y-4">
          {!assessment.complete && (
            <div
              role="note"
              className="rounded-md border border-amber-400 bg-amber-50 p-3 text-xs text-amber-950 dark:border-amber-600 dark:bg-amber-950/60 dark:text-amber-100"
            >
              <div className="flex items-start gap-2">
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 shrink-0 text-amber-700 dark:text-amber-400"
                  aria-hidden="true"
                />
                <div className="space-y-1">
                  <p className="font-semibold">
                    At least: the level is a floor because these inputs were
                    unavailable:
                  </p>
                  <ul className="list-disc space-y-0.5 pl-4">
                    {assessment.unavailable.map((unavail, idx) => (
                      <li key={`${unavail.kind}-${String(idx)}`}>
                        <span className="font-medium">{unavail.kind}</span>
                        {unavail.source_id ? ` (${unavail.source_id})` : ""}
                        {unavail.storm_name ? ` — ${unavail.storm_name}` : ""}
                        {unavail.threshold_kt !== null &&
                        unavail.threshold_kt !== undefined
                          ? ` — ${String(unavail.threshold_kt)} kt`
                          : ""}
                        : {unavail.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {assessment.toggle_changed && assessment.toggle_note && (
            <div
              role="note"
              className="rounded-md border border-amber-400 bg-amber-50 p-3 text-xs text-amber-950 dark:border-amber-600 dark:bg-amber-950/60 dark:text-amber-100"
            >
              {assessment.toggle_note}
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/40">
              <p className="font-semibold text-slate-900 dark:text-slate-100">
                Deciding rule:{" "}
                <code className="rounded bg-slate-200/80 px-1 py-0.5 font-mono dark:bg-slate-700">
                  {assessment.rule}
                </code>
              </p>
              <p className="mt-1 text-slate-700 dark:text-slate-300">
                {assessment.rule_trigger}
              </p>
              <p className="mt-2 font-medium text-slate-900 dark:text-slate-100">
                Recommended actions: {assessment.level.actions}
              </p>
              {assessment.evidence.length > 0 && (
                <div className="mt-2 border-t border-slate-200 pt-2 dark:border-slate-700">
                  <p className="font-semibold text-slate-800 dark:text-slate-200">
                    Deciding evidence
                  </p>
                  <ul className="mt-1 space-y-1 text-slate-700 dark:text-slate-300">
                    {assessment.evidence.map((ev, idx) => (
                      <li key={`${ev.product}-${String(idx)}`}>
                        <span>{ev.detail}</span>
                        {ev.code ? ` · ${ev.code}` : ""}
                        {ev.source_id ? ` (${ev.source_id})` : ""}
                        {ev.distance_km !== null &&
                        ev.distance_km !== undefined
                          ? ` · ${formatKm(ev.distance_km)}${ev.at_end ? " (at its end)" : ""}`
                          : ""}
                        {ev.issued_at
                          ? ` · issued ${formatBothTimes(ev.issued_at, timeZone)}`
                          : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/40">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">
                    Evacuation-order toggle
                  </p>
                  <p className="mt-0.5 text-slate-600 dark:text-slate-300">
                    State:{" "}
                    <strong>
                      {item.evacuation_order.on ? "On" : "Off"}
                    </strong>
                    {item.evacuation_order.set_at
                      ? ` since ${formatBothTimes(item.evacuation_order.set_at, timeZone)}`
                      : ""}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={item.evacuation_order.on}
                  aria-label={`Evacuation order for ${item.name}`}
                  disabled={evacPending}
                  onClick={() =>
                    onToggleEvacuation(!item.evacuation_order.on)
                  }
                  className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:opacity-60 ${
                    item.evacuation_order.on
                      ? "bg-orange-600 text-white hover:bg-orange-700"
                      : "border border-slate-300 bg-white text-slate-800 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                  }`}
                >
                  {item.evacuation_order.on ? "Turn off" : "Turn on"}
                </button>
              </div>
              <p className="mt-2 text-slate-600 dark:text-slate-400">
                When on, holds {item.name} at Level 4 (Warning / Watch /
                Evacuation) or above on the next fetched snapshot.
              </p>
            </div>
          </div>

          {coveringOfficial.length > 0 && (
            <div className="space-y-1.5 text-xs">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                Covering official products
              </h3>
              <ul className="space-y-1.5">
                {coveringOfficial.map((prod, idx) => (
                  <li
                    key={`${prod.code}-${String(idx)}`}
                    className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/40"
                  >
                    <div className="font-semibold text-slate-900 dark:text-slate-100">
                      {prod.code}
                      {prod.issuer ? ` · ${prod.issuer}` : ""}
                      {prod.storm_name
                        ? ` · ${prod.storm_name} (${prod.atcf_id ?? ""}, adv ${prod.advisory ?? "?"})`
                        : ""}
                    </div>
                    <div className="mt-0.5 text-slate-700 dark:text-slate-300">
                      {prod.reason}
                      {prod.distance_km !== null &&
                      prod.distance_km !== undefined
                        ? ` · ${formatKm(prod.distance_km)}`
                        : ""}
                    </div>
                    <div className="mt-0.5 text-slate-600 dark:text-slate-400">
                      Issued: {formatBothTimes(prod.issued_at, timeZone)}
                      {prod.expires_at
                        ? ` · Expires: ${formatBothTimes(prod.expires_at, timeZone)}`
                        : ""}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {contextAlerts.length > 0 && (
            <div className="space-y-1.5 text-xs">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                County-zone alerts outside this location&apos;s zones (context
                only; never sets the level)
              </h3>
              <ul className="space-y-1.5">
                {contextAlerts.map((prod, idx) => (
                  <li
                    key={`${prod.code}-${String(idx)}`}
                    className="rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/30"
                  >
                    <div className="font-semibold text-slate-800 dark:text-slate-200">
                      {prod.code}
                      {prod.issuer ? ` · ${prod.issuer}` : ""}
                    </div>
                    <div className="mt-0.5 text-slate-600 dark:text-slate-300">
                      {prod.reason}
                      {prod.zones.length > 0
                        ? ` · Zones: ${prod.zones.join(", ")}`
                        : ""}
                    </div>
                    <div className="mt-0.5 text-slate-500 dark:text-slate-400">
                      Issued: {formatBothTimes(prod.issued_at, timeZone)}
                      {prod.expires_at
                        ? ` · Expires: ${formatBothTimes(prod.expires_at, timeZone)}`
                        : ""}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {assessment.threats.length > 0 && (
            <div className="space-y-2 text-xs">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                Storm threats
              </h3>
              <div className="space-y-2">
                {assessment.threats.map((threat) => (
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
                        {threat.category !== null &&
                        threat.category !== undefined
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
                        at{" "}
                        {formatBothTimes(threat.closest_approach_at, timeZone)}{" "}
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
                        {formatArrivalReading(
                          threat.earliest_arrival,
                          timeZone,
                        )}
                      </div>
                      <div className="sm:col-span-2">
                        Most likely 34-kt arrival:{" "}
                        {formatArrivalReading(
                          threat.most_likely_arrival,
                          timeZone,
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {assessment.wind_probabilities.length > 0 && (
            <div className="space-y-1.5 text-xs">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                5 km wind-speed probabilities (synoptic{" "}
                {formatUtc(assessment.wind_probabilities[0]?.synoptic_at)})
              </h3>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                {assessment.wind_probabilities.map((wp) => (
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

          {assessment.changes.length > 0 && (
            <div className="space-y-1 text-xs">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                Changes since previous assessment
              </h3>
              <ul className="list-disc space-y-0.5 pl-4 text-slate-700 dark:text-slate-300">
                {assessment.changes.map((chg, idx) => (
                  <li key={`${chg.kind}-${String(idx)}`}>{chg.detail}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </article>
  );
}
