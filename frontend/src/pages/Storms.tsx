// frontend/src/pages/Storms.tsx
import { useQuery } from "@tanstack/react-query";
import { CloudRainWind, Compass, Wind } from "lucide-react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { compassWordsForDegrees } from "../dashboard/FeaturedLocation.tsx";
import { Card } from "../ui/Card.tsx";
import { Disclosure } from "../ui/Disclosure.tsx";
import { PageHeader } from "../ui/PageHeader.tsx";
import {
  formatAgeSeconds,
  formatBearing,
  formatFriendlyLocal,
  formatRouteError,
  formatUtc,
} from "./format.ts";
import { OutlookGraphics } from "./OutlookGraphics.tsx";

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

export function formatStormClassification(raw: string): string {
  switch (raw.trim().toUpperCase()) {
    case "HU":
      return "Hurricane";
    case "MH":
      return "Major Hurricane";
    case "TS":
      return "Tropical Storm";
    case "TD":
      return "Tropical Depression";
    case "SS":
      return "Subtropical Storm";
    case "SD":
      return "Subtropical Depression";
    case "PTC":
    case "PT":
      return "Post-Tropical Cyclone";
    case "PC":
      return "Potential Tropical Cyclone";
    default:
      return raw;
  }
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

function formatRelativeAge(
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
  const diffSeconds = Math.max(0, Math.round((refMs - targetMs) / 1000));
  return formatAgeSeconds(diffSeconds);
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

  const {
    snapshot,
    storms,
    outlook,
    wind_probabilities: windProbs,
  } = stormsQuery.data;

  return (
    <div className="space-y-5">
      <Card as="section">
        <PageHeader
          title="Storms"
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

      <Card as="section" aria-labelledby="active-storms-heading">
        <div className="flex items-center gap-2">
          <CloudRainWind
            className="h-5 w-5 shrink-0 text-brand"
            aria-hidden="true"
          />
          <h2
            id="active-storms-heading"
            className="text-base font-bold text-ink"
          >
            Active Storms
          </h2>
        </div>

        {storms.length === 0 ? (
          <p className="mt-3 text-sm text-ink-muted">
            No active storm in the latest NHC roster. The tropics are quiet for
            named cyclones; when the National Hurricane Center initiates
            advisories on a depression, storm, or hurricane, its intensity,
            movement, and forecast products will appear here on the next monitor
            cycle.
          </p>
        ) : (
          <div className="mt-4 space-y-4">
            {storms.map((storm) => (
              <StormCard
                key={storm.atcf_id}
                storm={storm}
                snapshotCompletedAt={snapshot?.completed_at}
              />
            ))}
          </div>
        )}
      </Card>

      <Card as="section" aria-labelledby="outlook-heading">
        <div className="flex items-center gap-2">
          <Compass
            className="h-5 w-5 shrink-0 text-brand"
            aria-hidden="true"
          />
          <h2 id="outlook-heading" className="text-base font-bold text-ink">
            Graphical Tropical Weather Outlook
          </h2>
        </div>

        {outlook.length === 0 ? (
          <p className="mt-3 text-sm text-ink-muted">
            No graphical outlook areas in the latest snapshot. When the National
            Hurricane Center highlights a two-day or seven-day disturbance in
            its Tropical Weather Outlook, its formation chances and basin will
            appear here on the next monitor cycle.
          </p>
        ) : (
          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {outlook.map((area, idx) => (
              <div
                key={`${area.basin}-${area.kind}-${String(idx)}`}
                className="rounded-card border border-line bg-surface-inset p-3 text-sm"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-ink">{area.basin}</span>
                  <span className="rounded-pill border border-line bg-surface-card px-2 py-0.5 text-caption font-medium text-ink">
                    {formatOutlookKind(area.kind)}
                  </span>
                </div>
                <div className="mt-2 space-y-1 text-ink-muted">
                  <div>
                    48-hour formation chance:{" "}
                    <strong className="text-ink">
                      {area.chance_2day_pct !== null
                        ? `${String(area.chance_2day_pct)}% (${area.risk_2day?.raw ?? "—"})`
                        : "—"}
                    </strong>
                  </div>
                  <div>
                    7-day formation chance:{" "}
                    <strong className="text-ink">
                      {area.chance_7day_pct !== null
                        ? `${String(area.chance_7day_pct)}% (${area.risk_7day?.raw ?? "—"})`
                        : "—"}
                    </strong>
                  </div>
                  <div className="text-ink-subtle">
                    Issued:{" "}
                    {formatFriendlyLocal(area.issued_at) ??
                      formatUtc(area.issued_at)}{" "}
                    <span className="text-caption text-ink-subtle">
                      ({formatUtc(area.issued_at)})
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <OutlookGraphics />
      </Card>

      <Card as="section" aria-labelledby="wind-prob-heading">
        <div className="flex items-center gap-2">
          <Wind className="h-5 w-5 shrink-0 text-brand" aria-hidden="true" />
          <h2 id="wind-prob-heading" className="text-base font-bold text-ink">
            5 km Wind-Speed Probabilities
          </h2>
        </div>

        {windProbs.length === 0 ? (
          <p className="mt-3 text-sm text-ink-muted">
            No wind-speed probability products in the latest snapshot. When NHC
            publishes 34-, 50-, and 64-knot wind-speed probability bands for an
            active cyclone, band counts and synoptic times will appear here on
            the next monitor cycle.
          </p>
        ) : (
          <div className="mt-3 space-y-2 text-sm">
            <p className="text-ink-muted">
              Synoptic time:{" "}
              {formatFriendlyLocal(windProbs[0]?.synoptic_at) ??
                formatUtc(windProbs[0]?.synoptic_at)}{" "}
              <span className="text-caption text-ink-subtle">
                ({formatUtc(windProbs[0]?.synoptic_at)})
              </span>
            </p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {windProbs.map((wp) => (
                <div
                  key={wp.threshold_kt}
                  className="rounded-card border border-line bg-surface-inset p-3"
                >
                  <div className="font-bold text-ink">
                    {String(wp.threshold_kt)} kt threshold
                  </div>
                  <div className="mt-1 text-ink-muted">
                    {String(wp.bands)} probability bands
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

function StormCard({
  storm,
  snapshotCompletedAt,
}: {
  readonly storm: StormSummaryResponse;
  readonly snapshotCompletedAt: string | undefined;
}) {
  const classificationWords = formatStormClassification(
    storm.classification.raw,
  );
  const directionWords =
    storm.movement_dir_deg !== null && storm.movement_dir_deg !== undefined
      ? compassWordsForDegrees(storm.movement_dir_deg).words
      : null;
  const issuedAge = formatRelativeAge(
    storm.advisory_issued_at,
    snapshotCompletedAt,
  );
  const issuedLocal = formatFriendlyLocal(storm.advisory_issued_at);

  return (
    <article
      aria-label={`${storm.name} (${storm.atcf_id})`}
      className="space-y-3 rounded-card border border-line bg-surface-inset p-4 text-sm"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h3 className="text-base font-bold text-ink">
            {storm.name} — {classificationWords}
          </h3>
          <p className="mt-0.5 text-ink-muted">
            {storm.intensity_kt !== null && storm.intensity_kt !== undefined
              ? `Maximum sustained winds ${String(storm.intensity_kt)} kt`
              : "Intensity unavailable"}
            {storm.movement_dir_deg !== null &&
            storm.movement_dir_deg !== undefined &&
            storm.movement_speed_mph !== null &&
            storm.movement_speed_mph !== undefined
              ? ` · Moving ${directionWords ?? ""} (${formatBearing(storm.movement_dir_deg)}) at ${String(storm.movement_speed_mph)} mph`
              : ""}
          </p>
        </div>
        {storm.advisory_issued_at && (
          <span className="text-caption tabular-nums text-ink-subtle">
            {issuedAge ? `Issued ${issuedAge}` : "Advisory issued"}
            {issuedLocal ? ` · ${issuedLocal}` : ""}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="rounded-control border border-line bg-surface-card p-2.5">
          <span className="text-ink-subtle">Maximum winds: </span>
          <strong className="tabular-nums text-ink">
            {storm.intensity_kt !== null && storm.intensity_kt !== undefined
              ? `${String(storm.intensity_kt)} kt`
              : "—"}
          </strong>
        </div>
        <div className="rounded-control border border-line bg-surface-card p-2.5">
          <span className="text-ink-subtle">Min pressure: </span>
          <strong className="tabular-nums text-ink">
            {storm.pressure_mb !== null && storm.pressure_mb !== undefined
              ? `${String(storm.pressure_mb)} mb`
              : "—"}
          </strong>
        </div>
        <div className="rounded-control border border-line bg-surface-card p-2.5">
          <span className="text-ink-subtle">Movement: </span>
          <strong className="tabular-nums text-ink">
            {storm.movement_dir_deg !== null &&
            storm.movement_dir_deg !== undefined &&
            storm.movement_speed_mph !== null &&
            storm.movement_speed_mph !== undefined
              ? `${formatBearing(storm.movement_dir_deg)} at ${String(storm.movement_speed_mph)} mph`
              : "—"}
          </strong>
        </div>
      </div>

      <Disclosure
        summary="Storm identifiers, advisory & snapshot products"
        caption={`${storm.atcf_id}${storm.advisory ? ` · Advisory ${storm.advisory}` : ""}`}
      >
        <div className="space-y-2 text-ink-muted">
          <p>
            Identifier: <code className="font-mono text-ink">{storm.atcf_id}</code>{" "}
            · Classification:{" "}
            <strong className="text-ink">{storm.classification.raw}</strong> (
            {classificationWords})
            {storm.slot ? ` · Slot ${storm.slot}` : ""}
            {storm.advisory ? ` · Advisory ${storm.advisory}` : ""}
          </p>
          <p className="text-ink-subtle">
            {storm.advisory_issued_at
              ? `Advisory issued: ${formatUtc(storm.advisory_issued_at)}`
              : ""}
            {storm.advisory_issued_at && storm.last_update ? " · " : ""}
            {storm.last_update
              ? `Last update: ${formatUtc(storm.last_update)}`
              : ""}
          </p>
          <p className="font-semibold text-ink">Products in snapshot</p>
          <p>
            Forecast cone:{" "}
            <strong className="text-ink">
              {storm.products.cone ? "yes" : "no"}
            </strong>{" "}
            · Forecast track:{" "}
            <strong className="text-ink">
              {storm.products.track ? "yes" : "no"}
            </strong>{" "}
            · Forecast points:{" "}
            <strong className="text-ink">
              {String(storm.products.track_points)}
            </strong>{" "}
            · Watch/warning segments:{" "}
            <strong className="text-ink">
              {String(storm.products.watch_warning_segments)}
            </strong>{" "}
            · Wind radii:{" "}
            <strong className="text-ink">
              {String(storm.products.wind_radii)}
            </strong>
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
      </Disclosure>
    </article>
  );
}
