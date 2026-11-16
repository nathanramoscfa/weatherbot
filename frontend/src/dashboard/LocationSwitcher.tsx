// frontend/src/dashboard/LocationSwitcher.tsx
import { useQuery } from "@tanstack/react-query";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { ThreatLevelBadge } from "../app/ThreatLevelBadge.tsx";
import {
  type LadderResponse,
  levelLabel,
  ruleSentence,
} from "../assessment/vocabulary.ts";
import {
  type ChartLevelPoint,
  LevelSparkline,
} from "../charts/LevelSparkline.tsx";
import { formatAgeSeconds } from "../pages/format.ts";
import { Card } from "../ui/Card.tsx";
import { Chip } from "../ui/Chip.tsx";
import { cx } from "../ui/threat.ts";

export type LocationAssessmentResponse =
  components["schemas"]["LocationAssessmentResponse"];
export type ChartsResponse = components["schemas"]["ChartsResponse"];

export function locationCardId(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `location-${slug}`;
}

export function selectFeaturedLocation(
  locations: readonly LocationAssessmentResponse[],
  hash: string,
): LocationAssessmentResponse | null {
  if (locations.length === 0) {
    return null;
  }
  const normalizedHash = hash.replace(/^#/, "");
  if (normalizedHash.length > 0) {
    const matched = locations.find(
      (loc) => locationCardId(loc.name) === normalizedHash,
    );
    if (matched !== undefined) {
      return matched;
    }
  }
  let best = locations[0]!;
  let bestLevel = best.assessment?.level.number ?? 0;
  for (const loc of locations) {
    const level = loc.assessment?.level.number ?? 0;
    if (level > bestLevel) {
      best = loc;
      bestLevel = level;
    }
  }
  return best;
}

async function fetchLocationCharts(location: string): Promise<ChartsResponse> {
  const { data, response } = await apiClient.GET("/api/charts", {
    params: { query: { location } },
  });
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/charts", response.status);
  }
  return data;
}

export function useLocationLevelPoints(
  item: LocationAssessmentResponse,
): readonly ChartLevelPoint[] {
  const chartsQuery = useQuery({
    queryKey: queryKeys.charts(item.name),
    queryFn: () => fetchLocationCharts(item.name),
  });
  if (chartsQuery.data !== undefined && chartsQuery.data.levels.length > 0) {
    return chartsQuery.data.levels;
  }
  if (item.assessment !== null) {
    return [
      {
        id: item.assessment.id,
        as_of: item.assessment.as_of,
        as_of_local: null,
        level: item.assessment.level.number,
        label: item.assessment.level.label,
        rule: item.assessment.rule,
        complete: item.assessment.complete,
      },
    ];
  }
  return [];
}

export interface LocationSwitcherProps {
  readonly locations: readonly LocationAssessmentResponse[];
  readonly featuredName: string;
  readonly ageSeconds: number;
  readonly onSelectLocation: (cardId: string) => void;
  readonly ladder?: LadderResponse;
}

export function LocationSwitcher({
  locations,
  featuredName,
  ageSeconds,
  onSelectLocation,
  ladder,
}: LocationSwitcherProps) {
  return (
    <section
      aria-label="Watched locations"
      data-testid="location-switcher"
      className={cx(
        "grid grid-cols-1 gap-3",
        locations.length >= 2 ? "md:grid-cols-2" : "",
      )}
    >
      {locations.map((item) => (
        <LocationSwitcherCard
          key={item.name}
          item={item}
          isFeatured={item.name === featuredName}
          ageSeconds={ageSeconds}
          onSelectLocation={onSelectLocation}
          {...(ladder !== undefined ? { ladder } : {})}
        />
      ))}
    </section>
  );
}

interface LocationSwitcherCardProps {
  readonly item: LocationAssessmentResponse;
  readonly isFeatured: boolean;
  readonly ageSeconds: number;
  readonly onSelectLocation: (cardId: string) => void;
  readonly ladder?: LadderResponse;
}

function LocationSwitcherCard({
  item,
  isFeatured,
  ageSeconds,
  onSelectLocation,
  ladder,
}: LocationSwitcherCardProps) {
  const points = useLocationLevelPoints(item);
  const { assessment } = item;
  const cardId = locationCardId(item.name);
  const cardHref = `#${cardId}`;
  const engineLabel = assessment
    ? levelLabel(assessment.level.number, ladder) || assessment.level.label
    : null;
  const plainHeadline = assessment
    ? assessment.rule_trigger || ruleSentence(assessment.rule, ladder)
    : "No assessment stored yet. Press Check now to fetch NHC and NWS products.";

  return (
    <Card
      as="article"
      id={cardId}
      aria-label={item.name}
      padding="sm"
      data-testid={`switcher-card-${item.name}`}
      className={cx(
        "flex flex-col justify-between gap-2.5 transition-shadow",
        isFeatured ? "border-brand ring-2 ring-brand/40" : "",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-bold text-ink">
              <a
                href={cardHref}
                aria-current={isFeatured ? "true" : undefined}
                onClick={(evt) => {
                  if (
                    evt.button === 0 &&
                    !evt.metaKey &&
                    !evt.ctrlKey &&
                    !evt.shiftKey &&
                    !evt.altKey
                  ) {
                    evt.preventDefault();
                    onSelectLocation(cardId);
                  }
                }}
                className="rounded-control text-ink underline decoration-brand/60 underline-offset-4 hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                {item.name}
              </a>
            </h2>
            {isFeatured && <Chip tone="brand">Featured</Chip>}
          </div>

          <span className="block text-caption font-medium text-ink-subtle">
            {item.inside_nws_coverage
              ? "Inside NWS coverage"
              : "Outside NWS coverage"}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {assessment && engineLabel ? (
            <ThreatLevelBadge
              level={assessment.level.number}
              label={engineLabel}
              atLeast={!assessment.complete}
              size="sm"
              {...(ladder !== undefined ? { ladder } : {})}
            />
          ) : (
            <span className="text-sm text-ink-subtle">
              No stored assessment
            </span>
          )}
        </div>
      </div>

      <p className="text-sm text-ink-muted">{plainHeadline}</p>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2 text-caption tabular-nums text-ink-subtle">
        <LevelSparkline location={item.name} points={points} />
        <span>
          {assessment
            ? `Assessed ${formatAgeSeconds(ageSeconds)}`
            : "Awaiting first check"}
        </span>
      </div>
    </Card>
  );
}
