// frontend/src/dashboard/FeaturedLocation.tsx
import type { ReactNode } from "react";
import { BriefingPanel } from "../ai/BriefingPanel.tsx";
import type { components } from "../api/schema.ts";
import { LocationHero } from "../assessment/LocationHero.tsx";
import {
  type LadderResponse,
  levelLabel,
} from "../assessment/vocabulary.ts";
import { WhyThisLevel } from "../assessment/WhyThisLevel.tsx";
import { ArrivalTimeline } from "../charts/ArrivalTimeline.tsx";
import {
  formatArrivalReading,
  formatBothTimes,
  formatFriendlyLocal,
  formatKm,
  formatUtc,
} from "../pages/format.ts";
import { Card } from "../ui/Card.tsx";
import { Chip } from "../ui/Chip.tsx";
import { StatTile } from "../ui/StatTile.tsx";

export type LocationAssessmentResponse =
  components["schemas"]["LocationAssessmentResponse"];
type ArrivalReadingResponse = components["schemas"]["ArrivalReadingResponse"];
type WindReadingResponse = components["schemas"]["WindReadingResponse"];

export function compassWordsForDegrees(deg: number): {
  readonly cardinal: string;
  readonly words: string;
} {
  const norm = ((deg % 360) + 360) % 360;
  const sector = Math.round(norm / 45) % 8;
  switch (sector) {
    case 0:
      return { cardinal: "N", words: "North" };
    case 1:
      return { cardinal: "NE", words: "Northeast" };
    case 2:
      return { cardinal: "E", words: "East" };
    case 3:
      return { cardinal: "SE", words: "Southeast" };
    case 4:
      return { cardinal: "S", words: "South" };
    case 5:
      return { cardinal: "SW", words: "Southwest" };
    case 6:
      return { cardinal: "W", words: "West" };
    default:
      return { cardinal: "NW", words: "Northwest" };
  }
}

function arrivalProductCaption(reading: ArrivalReadingResponse): string {
  const adv = reading.advisory ?? "?";
  if (reading.origin === "kmz") {
    return `NHC arrival-time KMZ (adv ${adv})`;
  }
  if (reading.origin === "map_layer") {
    return `NHC arrival-time layer (adv ${adv})`;
  }
  return `NHC forecast track fallback (adv ${adv})`;
}

export function summarizeArrivalStat(
  reading: ArrivalReadingResponse | null | undefined,
  timeZone?: string | null,
): { readonly value: string; readonly caption: string } {
  if (!reading) {
    return {
      value: "—",
      caption: "NHC 34-kt wind arrival product — no active storm",
    };
  }
  const product = arrivalProductCaption(reading);
  switch (reading.reading) {
    case "between": {
      const startLocal =
        formatFriendlyLocal(reading.start, timeZone) ??
        formatUtc(reading.start);
      const endLocal =
        formatFriendlyLocal(reading.end, timeZone) ?? formatUtc(reading.end);
      return {
        value: startLocal,
        caption: `Through ${endLocal} · ${product}`,
      };
    }
    case "before": {
      const endLocal =
        formatFriendlyLocal(reading.end, timeZone) ?? formatUtc(reading.end);
      return {
        value: `By ${endLocal}`,
        caption: `Before ${formatUtc(reading.end)} · ${product}`,
      };
    }
    case "after": {
      const startLocal =
        formatFriendlyLocal(reading.start, timeZone) ??
        formatUtc(reading.start);
      return {
        value: `After ${startLocal}`,
        caption: `After ${formatUtc(reading.start)} · ${product}`,
      };
    }
    case "track": {
      const approachLocal =
        formatFriendlyLocal(reading.approach_at, timeZone) ??
        formatUtc(reading.approach_at);
      return {
        value: approachLocal,
        caption: `Track closest approach (not a wind arrival) · ${product}`,
      };
    }
    case "outside":
      return {
        value: "Outside 5%",
        caption: `Outside the 5% contour · ${product}`,
      };
    case "unresolved":
      return {
        value: "—",
        caption: `Unresolved · ${product}`,
      };
  }
}

export function summarizeWindStat(
  reading: WindReadingResponse | undefined,
  thresholdKt: 34 | 64,
): { readonly value: string; readonly caption: string } {
  if (!reading) {
    return {
      value: "—",
      caption: `NHC 5 km ${String(thresholdKt)}-kt wind probabilities — unavailable`,
    };
  }
  const synoptic = formatUtc(reading.synoptic_at);
  if (reading.reading === "band") {
    return {
      value: reading.label ?? `${String(reading.lower_pct ?? 0)}%`,
      caption: `At least ${String(reading.lower_pct ?? 0)}% within 120 h · NHC 5 km wind probabilities (${synoptic})`,
    };
  }
  if (reading.reading === "below_every_band") {
    return {
      value: "<5%",
      caption: `Below every band within 120 h · NHC 5 km wind probabilities (${synoptic})`,
    };
  }
  return {
    value: "—",
    caption: `Outside coverage · NHC 5 km wind probabilities (${synoptic})`,
  };
}

export interface FeaturedLocationProps {
  readonly item: LocationAssessmentResponse;
  readonly ageSeconds: number;
  readonly evacPending: boolean;
  readonly onToggleEvacuation: (nextOn: boolean) => void;
  readonly provenanceChildren: ReactNode;
  readonly miniMap?: ReactNode;
  readonly ladder?: LadderResponse;
}

export function FeaturedLocation({
  item,
  ageSeconds,
  evacPending,
  onToggleEvacuation,
  provenanceChildren,
  miniMap,
  ladder,
}: FeaturedLocationProps) {
  const { assessment, time_zone: timeZone } = item;

  if (!assessment) {
    return (
      <div
        data-testid="featured-location"
        className="grid grid-cols-1 gap-5 xl:grid-cols-3 xl:items-start"
      >
        <div className="order-1 xl:col-span-2">
          <Card as="section" aria-label={`Featured assessment for ${item.name}`}>
            <p className="text-sm text-ink-muted">
              No assessment stored yet for {item.name}. Press Check now to fetch
              NHC and NWS products.
            </p>
          </Card>
        </div>
        {miniMap !== undefined && miniMap !== null && (
          <div className="order-2 xl:col-span-1">{miniMap}</div>
        )}
      </div>
    );
  }

  const leadThreat = assessment.threats[0] ?? null;
  const closestApproachValue =
    leadThreat !== null && leadThreat.closest_approach_km !== null
      ? leadThreat.closest_approach_km.toFixed(1)
      : "—";
  const closestApproachUnit =
    leadThreat !== null && leadThreat.closest_approach_km !== null
      ? "km"
      : undefined;
  const closestApproachCaption =
    leadThreat !== null && leadThreat.closest_approach_km !== null
      ? `${leadThreat.storm_name} · ${formatFriendlyLocal(leadThreat.closest_approach_at, timeZone) ?? formatUtc(leadThreat.closest_approach_at)} · NHC forecast track (adv ${leadThreat.advisory})`
      : "NHC forecast track — no active storm";

  const compass =
    leadThreat !== null && leadThreat.bearing_deg !== null
      ? compassWordsForDegrees(leadThreat.bearing_deg)
      : null;
  const bearingValue = compass ? compass.words : "—";
  const bearingUnit =
    compass && leadThreat && leadThreat.bearing_deg !== null
      ? `${compass.cardinal} (${String(Math.round(leadThreat.bearing_deg))}°)`
      : undefined;
  const bearingCaption =
    leadThreat !== null && leadThreat.bearing_deg !== null
      ? `Current center ${leadThreat.distance_km !== null ? formatKm(leadThreat.distance_km) : "—"} away · NHC forecast points (adv ${leadThreat.advisory})`
      : "NHC forecast points — no active storm";

  const earliestStat = summarizeArrivalStat(
    leadThreat?.earliest_arrival,
    timeZone,
  );
  const mostLikelyStat = summarizeArrivalStat(
    leadThreat?.most_likely_arrival,
    timeZone,
  );

  const wp34 = assessment.wind_probabilities.find(
    (wp) => wp.threshold_kt === 34,
  );
  const wp64 = assessment.wind_probabilities.find(
    (wp) => wp.threshold_kt === 64,
  );
  const wind34Stat = summarizeWindStat(wp34, 34);
  const wind64Stat = summarizeWindStat(wp64, 64);

  const stormsCountValue = String(assessment.threats.length);
  const stormsCountUnit =
    assessment.threats.length === 1 ? "storm" : "storms";
  const stormsCountCaption =
    assessment.threats.length > 0
      ? `${assessment.threats.map((t) => `${t.storm_name} (adv ${t.advisory})`).join(", ")} · NHC current storms roster`
      : "No active tropical cyclones · NHC current storms roster";

  const level4Name = levelLabel(4, ladder);

  return (
    <div
      data-testid="featured-location"
      className="grid grid-cols-1 gap-5 xl:grid-cols-3 xl:items-start"
    >
      <div className="order-1 space-y-4 xl:col-span-2">
        <Card
          as="section"
          aria-label={`Featured assessment for ${item.name}`}
          className="space-y-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
            <div className="flex flex-wrap items-center gap-2">
              <span
                data-testid="featured-location-name"
                className="text-base font-bold text-ink sm:text-lg"
              >
                {item.name}
              </span>
              <Chip tone="neutral">
                {item.inside_nws_coverage
                  ? "Inside NWS coverage"
                  : "Outside NWS coverage"}
              </Chip>
            </div>
            <span className="text-caption tabular-nums text-ink-subtle">
              Time zone: {timeZone ?? "UTC"}
            </span>
          </div>

          <LocationHero
            assessment={assessment}
            timeZone={timeZone}
            ageSeconds={ageSeconds}
            evacuationOrderOn={item.evacuation_order.on}
            origin="live"
            {...(ladder !== undefined ? { ladder } : {})}
          />

          <div
            data-testid="featured-stat-tiles"
            className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
          >
            <StatTile
              label="Closest approach"
              value={closestApproachValue}
              {...(closestApproachUnit !== undefined
                ? { unit: closestApproachUnit }
                : {})}
              caption={closestApproachCaption}
            />
            <StatTile
              label="Storm bearing"
              value={bearingValue}
              {...(bearingUnit !== undefined ? { unit: bearingUnit } : {})}
              caption={bearingCaption}
            />
            <StatTile
              label="Earliest & most likely 34-kt arrival"
              value={earliestStat.value}
              caption={`Most likely: ${mostLikelyStat.value} · ${earliestStat.caption}`}
            />
            <StatTile
              label="34-kt wind chance (120 h)"
              value={wind34Stat.value}
              caption={wind34Stat.caption}
            />
            <StatTile
              label="64-kt wind chance (120 h)"
              value={wind64Stat.value}
              caption={wind64Stat.caption}
            />
            <StatTile
              label="Storms tracked"
              value={stormsCountValue}
              unit={stormsCountUnit}
              caption={stormsCountCaption}
            />
          </div>

          {leadThreat && (
            <div className="grid grid-cols-1 items-center gap-4 rounded-card border border-line bg-surface-inset p-3.5 md:grid-cols-2">
              <ArrivalTimeline
                asOf={assessment.as_of}
                stormName={leadThreat.storm_name}
                earliest={leadThreat.earliest_arrival}
                mostLikely={leadThreat.most_likely_arrival}
              />
              <div className="space-y-1.5 text-sm text-ink-muted tabular-nums">
                <p className="font-semibold text-ink">
                  {leadThreat.storm_name} ({leadThreat.development}
                  {leadThreat.category !== null &&
                  leadThreat.category !== undefined
                    ? `, Category ${String(leadThreat.category)}`
                    : ""}
                  ) · Advisory {leadThreat.advisory}
                </p>
                <p>
                  Earliest reasonable 34-kt winds:{" "}
                  <span className="font-medium text-ink">
                    {formatArrivalReading(leadThreat.earliest_arrival, timeZone)}
                  </span>
                </p>
                <p>
                  Most likely 34-kt winds:{" "}
                  <span className="font-medium text-ink">
                    {formatArrivalReading(
                      leadThreat.most_likely_arrival,
                      timeZone,
                    )}
                  </span>
                </p>
              </div>
            </div>
          )}

          <BriefingPanel
            location={item.name}
            assessmentId={assessment.id}
            assessedAt={assessment.as_of}
          />
        </Card>
      </div>

      {miniMap !== undefined && miniMap !== null && (
        <div className="order-2 lg:order-3 xl:order-2 xl:col-span-1 xl:row-span-2">
          {miniMap}
        </div>
      )}

      <div className="order-3 space-y-4 lg:order-2 xl:order-3 xl:col-span-2">
        <Card
          as="section"
          aria-label={`Provenance and controls for ${item.name}`}
          className="space-y-4"
        >
          {assessment.changes.length > 0 && (
            <div className="space-y-1 text-sm">
              <h3 className="font-semibold text-ink">
                Changes since previous assessment
              </h3>
              <ul className="list-disc space-y-0.5 pl-4 text-ink-muted">
                {assessment.changes.map((chg, idx) => (
                  <li
                    key={`${chg.kind}-${String(idx)}`}
                    className="max-w-measure"
                  >
                    {chg.detail}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <WhyThisLevel
            assessment={assessment}
            insideNwsCoverage={item.inside_nws_coverage}
            timeZone={timeZone}
            breakpointSpan={assessment.breakpoint_span ?? item.breakpoint_span}
            controls={
              <div className="rounded-md border border-line bg-surface-inset p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="font-semibold text-ink">
                      Evacuation-order toggle
                    </p>
                    <p className="mt-0.5 text-ink-muted">
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
                    className={`rounded-md px-2.5 py-1 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-60 ${
                      item.evacuation_order.on
                        ? "bg-orange-600 text-white hover:bg-orange-700"
                        : "border border-slate-300 bg-white text-slate-800 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                    }`}
                  >
                    {item.evacuation_order.on ? "Turn off" : "Turn on"}
                  </button>
                </div>
                <p className="mt-2 text-ink-subtle">
                  When on, holds {item.name} at Level 4 ({level4Name}) or above
                  on the next fetched snapshot.
                </p>
              </div>
            }
          >
            {provenanceChildren}
          </WhyThisLevel>
        </Card>
      </div>
    </div>
  );
}
