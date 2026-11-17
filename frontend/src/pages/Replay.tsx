// frontend/src/pages/Replay.tsx
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Layers, Maximize2, Pause, Play } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { ThreatLevelBadge } from "../app/ThreatLevelBadge.tsx";
import { EvidenceList } from "../assessment/EvidenceList.tsx";
import { LevelSummary } from "../assessment/LevelSummary.tsx";
import { LocationHero } from "../assessment/LocationHero.tsx";
import { OfficialProductList } from "../assessment/OfficialProductList.tsx";
import { ThreatTable } from "../assessment/ThreatTable.tsx";
import { WhyThisLevel } from "../assessment/WhyThisLevel.tsx";
import { LevelHistoryChart } from "../charts/LevelHistoryChart.tsx";
import type { ChartLevelPoint } from "../charts/LevelSparkline.tsx";
import {
  AdvisorySlider,
  type AdvisorySliderStep,
} from "../map/AdvisorySlider.tsx";
import {
  DEFAULT_LAYER_VISIBILITY,
  DEFAULT_ON_LAYER_KEYS,
  isLayerVisible,
  LAYER_TOGGLE_ITEMS,
  type LayerVisibility,
  type MapLayerKey,
  type MapResponse,
} from "../map/layers.ts";
import { useLeafletMap } from "../map/useLeafletMap.ts";
import { Button, LinkButton } from "../ui/Button.tsx";
import { Callout } from "../ui/Callout.tsx";
import { Card } from "../ui/Card.tsx";
import { Chip } from "../ui/Chip.tsx";
import { PageHeader } from "../ui/PageHeader.tsx";
import { cx } from "../ui/threat.ts";
import { formatRouteError, formatUtc } from "./format.ts";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type LocationsResponse = components["schemas"]["LocationsResponse"];
export type ReplayStormsResponse =
  components["schemas"]["ReplayStormsResponse"];
export type ReplayTimelineResponse =
  components["schemas"]["ReplayTimelineResponse"];
export type ReplayAssessmentResponse =
  components["schemas"]["ReplayAssessmentResponse"];

const PLAY_INTERVAL_MS = 1500;
export const WORKBENCH_MEDIA_QUERY = "(min-width: 1280px)";

export function isDefaultWideWorkbench(): boolean {
  if (typeof window === "undefined") {
    return true;
  }
  if (typeof window.matchMedia === "function") {
    return window.matchMedia(WORKBENCH_MEDIA_QUERY).matches;
  }
  return window.innerWidth >= 1280;
}

async function fetchHealth(): Promise<HealthResponse> {
  const { data, response } = await apiClient.GET("/api/health");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/health", response.status);
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

async function fetchReplayStorms(): Promise<ReplayStormsResponse> {
  const { data, response } = await apiClient.GET("/api/replay");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/replay", response.status);
  }
  return data;
}

async function fetchReplayTimeline(
  atcfId: string,
  location: string,
): Promise<ReplayTimelineResponse> {
  const { data, response } = await apiClient.GET(
    "/api/replay/{atcf_id}/timeline",
    {
      params: {
        path: { atcf_id: atcfId },
        query: { location },
      },
    },
  );
  if (!response.ok || !data) {
    throw new ApiRequestError(
      `/api/replay/${atcfId}/timeline`,
      response.status,
    );
  }
  return data;
}

async function fetchReplayAdvisoryMap(
  atcfId: string,
  advisory: string,
): Promise<MapResponse> {
  const { data, response } = await apiClient.GET(
    "/api/replay/{atcf_id}/{advisory}",
    {
      params: {
        path: { atcf_id: atcfId, advisory },
      },
    },
  );
  if (!response.ok || !data) {
    throw new ApiRequestError(
      `/api/replay/${atcfId}/${advisory}`,
      response.status,
    );
  }
  return data;
}

async function fetchReplayAssessment(
  atcfId: string,
  advisory: string,
  location: string,
): Promise<ReplayAssessmentResponse> {
  const { data, response } = await apiClient.GET(
    "/api/replay/{atcf_id}/{advisory}/assessment",
    {
      params: {
        path: { atcf_id: atcfId, advisory },
        query: { location },
      },
    },
  );
  if (!response.ok || !data) {
    throw new ApiRequestError(
      `/api/replay/${atcfId}/${advisory}/assessment`,
      response.status,
    );
  }
  return data;
}

const REPLAY_LAYER_KEYS: ReadonlySet<MapLayerKey> = new Set<MapLayerKey>([
  ...DEFAULT_ON_LAYER_KEYS,
]);

function toggleLayerVisibility(
  current: LayerVisibility,
  key: MapLayerKey,
): LayerVisibility {
  const checked = !isLayerVisible(current, key);
  switch (key) {
    case "cone":
      return { ...current, cone: checked };
    case "track":
      return { ...current, track: checked };
    case "points":
      return { ...current, points: checked };
    case "watches_warnings":
      return { ...current, watches_warnings: checked };
    case "outlook":
      return { ...current, outlook: checked };
    case "locations":
      return { ...current, locations: checked };
    case "wind_radii":
      return { ...current, wind_radii: checked };
    case "past_track":
      return { ...current, past_track: checked };
    case "peak_surge":
      return { ...current, peak_surge: checked };
    case "wind_probabilities":
      return { ...current, wind_probabilities: checked };
    case "radar":
      return { ...current, radar: checked };
    case "satellite":
      return { ...current, satellite: checked };
  }
}

export function Replay() {
  const playButtonRef = useRef<HTMLButtonElement | null>(null);

  const [selectedStormId, setSelectedStormId] = useState<string | null>(null);
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null);
  const [selectedAdvisoryId, setSelectedAdvisoryId] = useState<string | null>(
    null,
  );
  const [playing, setPlaying] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [visibility, setVisibility] = useState<LayerVisibility>(
    DEFAULT_LAYER_VISIBILITY,
  );
  const [isWideWorkbench, setIsWideWorkbench] = useState<boolean>(() =>
    isDefaultWideWorkbench(),
  );

  useEffect(() => {
    if (
      typeof window === "undefined" ||
      typeof window.matchMedia !== "function"
    ) {
      return undefined;
    }
    const mql = window.matchMedia(WORKBENCH_MEDIA_QUERY);
    const syncLayout = () => {
      setIsWideWorkbench(mql.matches);
    };
    syncLayout();
    mql.addEventListener("change", syncLayout);
    window.addEventListener("resize", syncLayout);
    return () => {
      mql.removeEventListener("change", syncLayout);
      window.removeEventListener("resize", syncLayout);
    };
  }, []);

  const healthQuery = useQuery({
    queryKey: queryKeys.health(),
    queryFn: fetchHealth,
  });

  const locationsQuery = useQuery({
    queryKey: queryKeys.locations(),
    queryFn: fetchLocations,
  });

  const corpusEnabled = healthQuery.data?.corpus ?? false;
  const corpusExplicitlyDisabled = healthQuery.data?.corpus === false;

  const replayStormsQuery = useQuery({
    queryKey: queryKeys.replay(),
    queryFn: fetchReplayStorms,
    enabled: corpusEnabled,
  });

  const storms = useMemo(
    () => replayStormsQuery.data?.storms ?? [],
    [replayStormsQuery.data?.storms],
  );
  const locations = useMemo(
    () => locationsQuery.data?.locations ?? [],
    [locationsQuery.data?.locations],
  );

  const activeStorm = useMemo(() => {
    if (storms.length === 0) {
      return null;
    }
    if (selectedStormId !== null) {
      const found = storms.find((s) => s.atcf_id === selectedStormId);
      if (found) {
        return found;
      }
    }
    return storms[0] ?? null;
  }, [storms, selectedStormId]);

  const activeLocationName = useMemo(() => {
    if (locations.length === 0) {
      return null;
    }
    if (selectedLocation !== null) {
      const found = locations.find((loc) => loc.name === selectedLocation);
      if (found) {
        return found.name;
      }
    }
    const nassau = locations.find((loc) => loc.name === "Parliament Square");
    if (nassau) {
      return nassau.name;
    }
    return locations[0]?.name ?? null;
  }, [locations, selectedLocation]);

  const timelineQuery = useQuery({
    queryKey: queryKeys.replayTimeline(
      activeStorm?.atcf_id ?? "",
      activeLocationName ?? "",
    ),
    queryFn: () =>
      fetchReplayTimeline(activeStorm!.atcf_id, activeLocationName!),
    enabled:
      corpusEnabled && activeStorm !== null && activeLocationName !== null,
  });

  const timeline = timelineQuery.data ?? null;
  const steps = useMemo(() => timeline?.steps ?? [], [timeline?.steps]);

  const activeStep = useMemo(() => {
    if (steps.length === 0) {
      return null;
    }
    if (selectedAdvisoryId !== null) {
      const found = steps.find(
        (step) => step.advisory_id === selectedAdvisoryId,
      );
      if (found) {
        return found;
      }
    }
    return steps[0] ?? null;
  }, [steps, selectedAdvisoryId]);

  const activeStepIndex = useMemo(() => {
    if (!activeStep || steps.length === 0) {
      return -1;
    }
    return steps.findIndex((s) => s.advisory_id === activeStep.advisory_id);
  }, [steps, activeStep]);

  const replayMapQuery = useQuery({
    queryKey: queryKeys.replayAdvisory(
      activeStorm?.atcf_id ?? "",
      activeStep?.advisory_id ?? "",
    ),
    queryFn: () =>
      fetchReplayAdvisoryMap(activeStorm!.atcf_id, activeStep!.advisory_id),
    enabled: corpusEnabled && activeStorm !== null && activeStep !== null,
  });

  const replayAssessmentQuery = useQuery({
    queryKey: queryKeys.replayAssessment(
      activeStorm?.atcf_id ?? "",
      activeStep?.advisory_id ?? "",
      activeLocationName ?? "",
    ),
    queryFn: () =>
      fetchReplayAssessment(
        activeStorm!.atcf_id,
        activeStep!.advisory_id,
        activeLocationName!,
      ),
    enabled:
      corpusEnabled &&
      activeStorm !== null &&
      activeStep !== null &&
      activeLocationName !== null,
  });

  const { containerRef: mapContainerRef, fitToData } = useLeafletMap({
    mapData: replayMapQuery.data,
    visibility,
    timeZone: timeline?.time_zone ?? null,
    viewModeKey:
      activeStorm && activeStep
        ? `replay:${activeStorm.atcf_id}:${activeStep.advisory_id}`
        : "replay:none",
  });

  const isPlaying =
    playing &&
    steps.length > 1 &&
    activeStepIndex >= 0 &&
    activeStepIndex < steps.length - 1;

  useEffect(() => {
    if (!isPlaying) {
      return;
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        setPlaying(false);
      }
    };

    const handleUserInput = (event: Event) => {
      const target = event.target;
      if (
        target instanceof Node &&
        playButtonRef.current !== null &&
        playButtonRef.current.contains(target)
      ) {
        return;
      }
      setPlaying(false);
    };

    const timerId = window.setInterval(() => {
      const nextIdx = activeStepIndex + 1;
      const nextStep = steps.at(nextIdx);
      if (!nextStep) {
        setPlaying(false);
        return;
      }
      setSelectedAdvisoryId(nextStep.advisory_id);
      if (nextIdx >= steps.length - 1) {
        setPlaying(false);
      }
    }, PLAY_INTERVAL_MS);

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("keydown", handleUserInput, { capture: true });
    window.addEventListener("pointerdown", handleUserInput, { capture: true });
    window.addEventListener("mousedown", handleUserInput, { capture: true });
    window.addEventListener("wheel", handleUserInput, { capture: true });
    window.addEventListener("touchstart", handleUserInput, { capture: true });

    return () => {
      window.clearInterval(timerId);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("keydown", handleUserInput, { capture: true });
      window.removeEventListener("pointerdown", handleUserInput, {
        capture: true,
      });
      window.removeEventListener("mousedown", handleUserInput, {
        capture: true,
      });
      window.removeEventListener("wheel", handleUserInput, { capture: true });
      window.removeEventListener("touchstart", handleUserInput, {
        capture: true,
      });
    };
  }, [isPlaying, steps, activeStepIndex]);

  const sliderSteps: readonly AdvisorySliderStep[] = useMemo(
    () =>
      steps.map((step) => ({
        snapshot_id: step.advisory_id,
        as_of: step.issued_at,
        atcf_id: timeline?.atcf_id ?? "",
        storm_name: timeline?.name ?? "",
        advisory: step.advisory,
        issued_at: step.issued_at,
      })),
    [steps, timeline?.atcf_id, timeline?.name],
  );

  const chartPoints: readonly ChartLevelPoint[] = useMemo(
    () =>
      steps.map((step, idx) => ({
        id: idx + 1,
        as_of: step.issued_at,
        as_of_local: null,
        level: step.level.number,
        label: step.level.label,
        rule: step.rule,
        complete: step.complete,
      })),
    [steps],
  );

  const handleToggleLayer = (key: MapLayerKey) => {
    setPlaying(false);
    setVisibility((prev) => toggleLayerVisibility(prev, key));
  };

  const handleTogglePlay = () => {
    if (isPlaying) {
      setPlaying(false);
      return;
    }
    if (steps.length <= 1) {
      return;
    }
    if (activeStepIndex >= steps.length - 1) {
      const first = steps.at(0);
      if (first) {
        setSelectedAdvisoryId(first.advisory_id);
      }
    }
    setPlaying(true);
  };

  const assessment = replayAssessmentQuery.data ?? null;
  const replayLayerItems = LAYER_TOGGLE_ITEMS.filter((item) =>
    REPLAY_LAYER_KEYS.has(item.key),
  );
  const noLocationsStored =
    corpusEnabled && locations.length === 0 && !locationsQuery.isLoading;

  if (corpusExplicitlyDisabled) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Replay"
          summary="Scrub archived NHC storm advisories against your watched locations without storing history or triggering notifications."
        />
        <Callout
          tone="warning"
          role="note"
          aria-label="Replay corpus configuration"
          data-testid="replay-corpus-disabled"
          title="No historical replay corpus is configured"
        >
          <p className="text-sm leading-relaxed">
            To scrub historical storms in the UI, set{" "}
            <code className="rounded bg-amber-200/70 px-1 py-0.5 font-mono dark:bg-amber-900/60">
              [web] corpus
            </code>{" "}
            in{" "}
            <code className="rounded bg-amber-200/70 px-1 py-0.5 font-mono dark:bg-amber-900/60">
              weatherbot.toml
            </code>{" "}
            (or pass{" "}
            <code className="rounded bg-amber-200/70 px-1 py-0.5 font-mono dark:bg-amber-900/60">
              weatherbot serve --corpus DIR
            </code>
            ) naming a checkout&apos;s{" "}
            <code className="rounded bg-amber-200/70 px-1 py-0.5 font-mono dark:bg-amber-900/60">
              tests/fixtures/replay
            </code>{" "}
            directory, or a{" "}
            <code className="rounded bg-amber-200/70 px-1 py-0.5 font-mono dark:bg-amber-900/60">
              convert --full
            </code>{" "}
            output directory built with{" "}
            <code className="rounded bg-amber-200/70 px-1 py-0.5 font-mono dark:bg-amber-900/60">
              uv run python scripts/fetch_replay_corpus.py convert --full --out
              DIR
            </code>
            .
          </p>
        </Callout>
      </div>
    );
  }

  if (noLocationsStored) {
    return (
      <div className="space-y-4">
        <PageHeader
          title="Replay"
          summary="Scrub archived NHC storm advisories against your watched locations without storing history or triggering notifications."
        />
        <Callout
          tone="note"
          role="note"
          aria-label="No stored locations for replay"
          data-testid="replay-no-locations"
          title="No watched locations stored"
        >
          <p className="text-sm">
            Add a watched location in Settings to scrub historical storm
            timelines against it.
          </p>
          <div className=" pt-1.5">
            <LinkButton to="/settings" variant="primary" size="sm">
              Add a location in Settings
            </LinkButton>
          </div>
        </Callout>
      </div>
    );
  }

  const mapIsLoading =
    !timeline || !activeStep || replayMapQuery.isLoading;

  return (
    <div className="space-y-4">
      {timelineQuery.isError && (
        <Callout tone="error" role="alert">
          <p>
            {formatRouteError(
              `/api/replay/${activeStorm?.atcf_id ?? ""}/timeline`,
              timelineQuery.error instanceof ApiRequestError
                ? timelineQuery.error.status
                : undefined,
            )}
          </p>
        </Callout>
      )}

      <div
        data-testid="replay-workbench"
        className="grid grid-cols-1 gap-3.5 xl:grid-cols-2 xl:items-start"
      >
        <div className="max-xl:contents xl:col-start-1 xl:row-start-1 xl:space-y-3">
          <Card
            as="section"
            padding="sm"
            aria-label="Replay advisory map"
            data-testid="replay-map-section"
            className="order-3 space-y-2"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold text-ink">Advisory map</h2>

              <div className="flex flex-wrap items-center gap-2">
                <Button variant="secondary" size="sm" onClick={fitToData}>
                  <Maximize2
                    className="h-3.5 w-3.5 shrink-0"
                    aria-hidden="true"
                  />
                  <span>Fit</span>
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  aria-expanded={layersOpen}
                  aria-controls="replay-map-layers"
                  onClick={() => setLayersOpen((prev) => !prev)}
                >
                  <Layers
                    className="h-3.5 w-3.5 shrink-0 text-brand"
                    aria-hidden="true"
                  />
                  <span>Layers</span>
                  <ChevronDown
                    className={cx(
                      "h-3.5 w-3.5 shrink-0 text-ink-subtle transition-transform",
                      layersOpen ? "rotate-180" : "",
                    )}
                    aria-hidden="true"
                  />
                </Button>
              </div>
            </div>

            {layersOpen && (
              <div
                id="replay-map-layers"
                className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-control border border-line bg-surface-inset px-3 py-2 text-sm text-ink"
              >
                {replayLayerItems.map((layer) => (
                  <label
                    key={layer.key}
                    className="inline-flex min-h-6 cursor-pointer items-center gap-1.5 text-sm text-ink"
                  >
                    <input
                      type="checkbox"
                      checked={isLayerVisible(visibility, layer.key)}
                      onChange={() => handleToggleLayer(layer.key)}
                      className="h-4 w-4 rounded border-line-strong text-brand focus:ring-brand"
                    />
                    <span>{layer.label}</span>
                  </label>
                ))}
              </div>
            )}

            <div className="relative isolate">
              <div
                ref={mapContainerRef}
                data-testid="replay-leaflet-map"
                className="relative z-0 h-[60vh] min-h-[60vh] w-full rounded-control border border-line"
              />
              {mapIsLoading && (
                <div
                  role="status"
                  data-testid="replay-map-loading"
                  className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-control bg-surface-page/40 p-4"
                >
                  <span className="rounded-pill border border-line bg-surface-card px-3.5 py-1.5 text-sm font-medium text-ink shadow-card">
                    Loading replay advisory map…
                  </span>
                </div>
              )}
            </div>
          </Card>

          {timeline && activeStep && (
            <Card
              as="section"
              padding="sm"
              aria-label="Replay advisory scrubber"
              data-testid="replay-scrubber"
              className="order-4 space-y-2"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    ref={playButtonRef}
                    type="button"
                    aria-label={isPlaying ? "Pause" : "Play"}
                    onClick={handleTogglePlay}
                    disabled={steps.length <= 1}
                    className="inline-flex min-h-6 items-center gap-1.5 rounded-control bg-brand px-3 py-1 text-sm font-semibold text-on-brand hover:bg-brand-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isPlaying ? (
                      <>
                        <Pause className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>Pause</span>
                      </>
                    ) : (
                      <>
                        <Play className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>Play</span>
                      </>
                    )}
                  </button>
                  <span className="text-caption text-ink-subtle tabular-nums">
                    Step {String(activeStepIndex + 1)} of{" "}
                    {String(steps.length)} · Advisory {activeStep.advisory} (
                    {activeStep.advisory_id}) ·{" "}
                    {formatUtc(activeStep.issued_at)}
                  </span>
                </div>
              </div>

              <AdvisorySlider
                steps={sliderSteps}
                selectedSnapshotId={activeStep.advisory_id}
                onSelectSnapshotId={(id) => {
                  setPlaying(false);
                  setSelectedAdvisoryId(id);
                }}
                order="oldest-first"
                showStoredBanner={false}
              />
            </Card>
          )}

          {isWideWorkbench && timeline && activeStep && (
            <LevelHistoryChart
              location={timeline.location}
              timeZone={timeline.time_zone}
              points={chartPoints}
              activeAsOf={activeStep.issued_at}
            />
          )}
        </div>

        <div className="max-xl:contents xl:col-start-2 xl:row-start-1 xl:sticky xl:top-4 xl:space-y-3">
          <Card
            as="section"
            padding="sm"
            aria-label="Replay controls"
            data-testid="replay-pickers"
            className="order-1 space-y-2.5"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h1 className="text-lg font-bold text-ink sm:text-xl">Replay</h1>
              <span className="text-caption text-ink-subtle">
                Historical archive · not live
              </span>
            </div>
            <p className="text-sm text-ink-muted">
              Scrub archived NHC storm advisories against your watched locations
              without storing history or triggering notifications.
            </p>

            {corpusEnabled && storms.length > 0 && locations.length > 0 && (
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                <div className="flex flex-col gap-1 text-sm">
                  <label
                    htmlFor="replay-storm-picker"
                    className="font-semibold text-ink"
                  >
                    Storm
                  </label>
                  <select
                    id="replay-storm-picker"
                    aria-label="Replay storm"
                    value={activeStorm?.atcf_id ?? ""}
                    onChange={(e) => {
                      setPlaying(false);
                      setSelectedStormId(e.target.value);
                      setSelectedAdvisoryId(null);
                    }}
                    className="min-h-6 rounded-control border border-line-strong bg-surface-card px-2.5 py-1.5 text-sm text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                  >
                    {storms.map((storm) => (
                      <option key={storm.atcf_id} value={storm.atcf_id}>
                        {storm.name} ({storm.atcf_id}) · {storm.advisory_count}{" "}
                        advisories
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-1 text-sm">
                  <label
                    htmlFor="replay-location-picker"
                    className="font-semibold text-ink"
                  >
                    Location
                  </label>
                  <select
                    id="replay-location-picker"
                    aria-label="Replay location"
                    value={activeLocationName ?? ""}
                    onChange={(e) => {
                      setPlaying(false);
                      setSelectedLocation(e.target.value);
                    }}
                    className="min-h-6 rounded-control border border-line-strong bg-surface-card px-2.5 py-1.5 text-sm text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                  >
                    {locations.map((loc) => (
                      <option key={loc.name} value={loc.name}>
                        {loc.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </Card>

          {timeline && activeStep && (
            <Callout
              tone="warning"
              role="status"
              data-testid="replay-banner"
              className="order-2 font-semibold"
            >
              <p>
                Replay: {timeline.name} advisory {activeStep.advisory}, issued{" "}
                {formatUtc(activeStep.issued_at)} — not live
              </p>
            </Callout>
          )}

          {assessment ? (
            <Card
              as="article"
              padding="sm"
              aria-label={`Replayed assessment for ${assessment.location}`}
              data-testid="replay-assessment-card"
              className="order-5 space-y-3.5"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-bold text-ink sm:text-lg">
                    {assessment.location}
                  </h2>
                  <Chip tone="neutral">
                    {assessment.inside_nws_coverage
                      ? "Inside NWS coverage"
                      : "Outside NWS coverage"}
                  </Chip>
                </div>

                <ThreatLevelBadge
                  level={assessment.level.number}
                  label={assessment.level.label}
                  atLeast={!assessment.complete}
                />
              </div>

              <LocationHero
                assessment={assessment}
                timeZone={assessment.time_zone}
                origin="replay"
              />

              {assessment.changes.length > 0 && (
                <div className="space-y-1 text-sm">
                  <h3 className="font-semibold text-ink">
                    Changes at this advisory
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

              {!isWideWorkbench && timeline && activeStep && (
                <LevelHistoryChart
                  location={timeline.location}
                  timeZone={timeline.time_zone}
                  points={chartPoints}
                  activeAsOf={activeStep.issued_at}
                />
              )}

              <WhyThisLevel
                assessment={assessment}
                insideNwsCoverage={assessment.inside_nws_coverage}
                timeZone={assessment.time_zone}
                breakpointSpan={assessment.breakpoint_span}
              >
                {timeline && timeline.notes.length > 0 && (
                  <Callout
                    tone="warning"
                    role="note"
                    aria-label="Replay notes"
                    data-testid="replay-notes"
                    title="Replay notes"
                  >
                    <ul className="list-disc space-y-1 pl-4">
                      {timeline.notes.map((note, idx) => (
                        <li
                          key={`note-${String(idx)}`}
                          className="max-w-measure"
                        >
                          {note}
                        </li>
                      ))}
                    </ul>
                  </Callout>
                )}

                <LevelSummary assessment={assessment}>
                  <EvidenceList
                    evidence={assessment.evidence}
                    timeZone={assessment.time_zone}
                  />
                </LevelSummary>

                <OfficialProductList
                  official={assessment.official}
                  timeZone={assessment.time_zone}
                />

                <ThreatTable
                  threats={assessment.threats}
                  windProbabilities={assessment.wind_probabilities}
                  asOf={assessment.as_of}
                  timeZone={assessment.time_zone}
                />
              </WhyThisLevel>
            </Card>
          ) : (
            timeline &&
            activeStep &&
            replayAssessmentQuery.isLoading && (
              <Card
                as="section"
                padding="sm"
                className="order-5 text-sm text-ink-muted"
              >
                <p>Loading replay assessment…</p>
              </Card>
            )
          )}
        </div>
      </div>
    </div>
  );
}
