// frontend/src/pages/Dashboard.tsx
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { EvidenceList } from "../assessment/EvidenceList.tsx";
import { LevelSummary } from "../assessment/LevelSummary.tsx";
import { OfficialProductList } from "../assessment/OfficialProductList.tsx";
import { ThreatTable } from "../assessment/ThreatTable.tsx";
import { useLadder } from "../assessment/vocabulary.ts";
import { buildReportHref } from "../dashboard/ExportPopover.tsx";
import { FeaturedLocation } from "../dashboard/FeaturedLocation.tsx";
import {
  LocationSwitcher,
  locationCardId,
  selectFeaturedLocation,
} from "../dashboard/LocationSwitcher.tsx";
import { MiniMap } from "../dashboard/MiniMap.tsx";
import {
  type CycleStatusMessage,
  StatusBar,
} from "../dashboard/StatusBar.tsx";
import {
  STREAM_EVENT_DOM_NAME,
  type StreamEvent,
} from "../events/useEventStream.ts";
import { Card } from "../ui/Card.tsx";
import { formatRouteError } from "./format.ts";

export { buildReportHref, locationCardId };

export type AssessmentsResponse =
  components["schemas"]["AssessmentsResponse"];
export type LocationsResponse = components["schemas"]["LocationsResponse"];
export type HealthResponse = components["schemas"]["HealthResponse"];
export type DisclaimerResponse = components["schemas"]["DisclaimerResponse"];
export type LocationAssessmentResponse =
  components["schemas"]["LocationAssessmentResponse"];
export type ChartsResponse = components["schemas"]["ChartsResponse"];

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

function formatAiStateSummary(
  ai: HealthResponse["ai"] | null | undefined,
  featuredName: string,
): string {
  if (!ai) {
    return `AI briefing card for ${featuredName} is below the stat tiles.`;
  }
  switch (ai.state) {
    case "ready":
      return `AI ready for ${featuredName} · press Brief me in the briefing card to stream an explanation.`;
    case "paused":
      return "AI is paused by you — resume it in Settings.";
    case "capped":
      return "AI is paused because today's daily spend cap is reached.";
    case "unavailable":
      return "AI is temporarily unavailable — check Settings for details.";
    default:
      return "AI is off — configure an Anthropic credential to enable briefings.";
  }
}

export function Dashboard() {
  const queryClient = useQueryClient();
  const routerLocation = useLocation();
  const navigate = useNavigate();
  const { data: ladder } = useLadder();

  const [cycleRunning, setCycleRunning] = useState(false);
  const [cycleMessage, setCycleMessage] = useState<CycleStatusMessage | null>(
    null,
  );
  const [evacPendingName, setEvacPendingName] = useState<string | null>(null);
  const [evacError, setEvacError] = useState<string | null>(null);
  const [includeBriefing, setIncludeBriefing] = useState(false);

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

  const handleSelectLocation = (cardId: string) => {
    const targetHash = `#${cardId}`;
    if (routerLocation.hash !== targetHash) {
      void navigate({
        pathname: routerLocation.pathname,
        hash: targetHash,
      });
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
      <div className="rounded-lg border border-line bg-surface-card p-6 text-sm text-ink-muted">
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
        className="space-y-4 rounded-card border border-line bg-surface-card p-6 shadow-card"
      >
        <div className="flex items-start gap-3">
          <ShieldAlert
            className="mt-0.5 h-6 w-6 shrink-0 text-brand"
            aria-hidden="true"
          />
          <div className="space-y-2">
            <h1
              id="empty-dashboard-heading"
              className="text-lg font-semibold text-ink"
            >
              No watched locations configured
            </h1>
            <p className="text-sm text-ink-muted">
              Add a location in Settings to monitor official NHC and NWS
              products and compute threat levels.
            </p>
          </div>
        </div>

        <div className="rounded-md border border-amber-300 bg-amber-50/80 p-4 text-sm leading-relaxed text-amber-950 dark:border-amber-700/80 dark:bg-amber-950/50 dark:text-amber-100">
          <p className="font-semibold uppercase tracking-wide">
            Disclaimer essentials
          </p>
          <p className="mt-1 whitespace-pre-line">{essentials}</p>
        </div>

        <div>
          <Link
            to="/settings"
            className="inline-flex items-center rounded-md bg-brand px-3.5 py-2 text-sm font-semibold text-on-brand hover:bg-brand-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            Add your first location in Settings
          </Link>
        </div>
      </section>
    );
  }

  const snapshot = assessmentsData?.snapshot ?? null;
  const nextProductAt = healthQuery.data?.next_product_at ?? null;
  const serverNow = healthQuery.data?.now ?? null;
  const hasAnyAssessment = locationCards.some(
    (item) => item.assessment !== null,
  );
  const featured = selectFeaturedLocation(locationCards, routerLocation.hash);
  const featuredTimeZone = featured?.time_zone ?? null;

  const liveAnnouncement = locationCards
    .map((item) => {
      if (!item.assessment) {
        return `${item.name}: no stored assessment.`;
      }
      const prefix = item.assessment.complete ? "" : "At least ";
      return `${item.name}: ${prefix}Level ${String(item.assessment.level.number)}, ${item.assessment.level.label}. ${item.assessment.rule_trigger}`;
    })
    .join(" ");

  return (
    <div className="space-y-5">
      <h1 className="sr-only">Dashboard</h1>

      <div
        aria-live="polite"
        aria-atomic="true"
        data-testid="level-live-region"
        className="sr-only"
      >
        {liveAnnouncement}
      </div>

      <StatusBar
        snapshot={snapshot}
        nextProductAt={nextProductAt}
        serverNow={serverNow}
        timeZone={featuredTimeZone}
        hasAnyAssessment={hasAnyAssessment}
        locationNames={locationCards.map((item) => item.name)}
        includeBriefing={includeBriefing}
        onIncludeBriefingChange={setIncludeBriefing}
        cycleRunning={cycleRunning}
        onCheckNow={() => void handleCheckNow()}
        cycleMessage={cycleMessage}
        evacError={evacError}
      />

      {locationCards.length > 0 && featured && (
        <>
          <LocationSwitcher
            locations={locationCards}
            featuredName={featured.name}
            ageSeconds={snapshot?.age_seconds ?? 0}
            onSelectLocation={handleSelectLocation}
            ladder={ladder}
          />

          <FeaturedLocation
            item={featured}
            ageSeconds={snapshot?.age_seconds ?? 0}
            evacPending={evacPendingName === featured.name}
            onToggleEvacuation={(nextOn) =>
              void handleEvacuationToggle(featured.name, nextOn)
            }
            ladder={ladder}
            miniMap={
              <MiniMap
                ageSeconds={snapshot ? snapshot.age_seconds : null}
                timeZone={featuredTimeZone}
                statusNote={
                  <Card
                    as="aside"
                    aria-label="Briefing status summary"
                    padding="sm"
                    data-testid="mini-map-briefing-status"
                  >
                    <div className="flex items-start gap-2 text-sm text-ink-muted">
                      <Sparkles
                        className="mt-0.5 h-4 w-4 shrink-0 text-violet-700 dark:text-violet-300"
                        aria-hidden="true"
                      />
                      <div className="space-y-1">
                        <p className="font-semibold text-ink">
                          AI briefing status
                        </p>
                        <p>
                          {formatAiStateSummary(
                            healthQuery.data?.ai,
                            featured.name,
                          )}
                        </p>
                      </div>
                    </div>
                  </Card>
                }
              />
            }
            provenanceChildren={
              featured.assessment ? (
                <>
                  <LevelSummary assessment={featured.assessment}>
                    <EvidenceList
                      evidence={featured.assessment.evidence}
                      timeZone={featured.time_zone}
                    />
                  </LevelSummary>
                  <OfficialProductList
                    official={featured.assessment.official}
                    timeZone={featured.time_zone}
                  />
                  <ThreatTable
                    threats={featured.assessment.threats}
                    windProbabilities={featured.assessment.wind_probabilities}
                    asOf={featured.assessment.as_of}
                    timeZone={featured.time_zone}
                  />
                </>
              ) : null
            }
          />
        </>
      )}
    </div>
  );
}
