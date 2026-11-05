// frontend/src/pages/Replay.tsx
import { useQuery } from "@tanstack/react-query";
import { Pause, Play, ShieldAlert } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { ThreatLevelBadge } from "../app/ThreatLevelBadge.tsx";
import { EvidenceList } from "../assessment/EvidenceList.tsx";
import {
  LevelSummary,
  UnavailableBanner,
} from "../assessment/LevelSummary.tsx";
import { OfficialProductList } from "../assessment/OfficialProductList.tsx";
import { ThreatTable } from "../assessment/ThreatTable.tsx";
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
import {
  formatBothTimes,
  formatBreakpointSpan,
  formatRouteError,
  formatUtc,
} from "./format.ts";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type LocationsResponse = components["schemas"]["LocationsResponse"];
export type ReplayStormsResponse =
  components["schemas"]["ReplayStormsResponse"];
export type ReplayTimelineResponse =
  components["schemas"]["ReplayTimelineResponse"];
export type ReplayAssessmentResponse =
  components["schemas"]["ReplayAssessmentResponse"];

const PLAY_INTERVAL_MS = 1500;

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
  const [visibility, setVisibility] = useState<LayerVisibility>(
    DEFAULT_LAYER_VISIBILITY,
  );

  const healthQuery = useQuery({
    queryKey: queryKeys.health(),
    queryFn: fetchHealth,
  });

  const locationsQuery = useQuery({
    queryKey: queryKeys.locations(),
    queryFn: fetchLocations,
  });

  const corpusEnabled = healthQuery.data?.corpus ?? false;

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

  const { containerRef: mapContainerRef } = useLeafletMap({
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

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              Replay
            </h1>
            <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-300">
              Scrub archived NHC storm advisories against your watched locations
              without storing history or triggering notifications.
            </p>
          </div>

          {corpusEnabled && storms.length > 0 && locations.length > 0 && (
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-1.5 text-xs">
                <label
                  htmlFor="replay-storm-picker"
                  className="font-semibold text-slate-700 dark:text-slate-300"
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
                  className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs text-slate-900 focus:border-sky-500 focus:outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
                >
                  {storms.map((storm) => (
                    <option key={storm.atcf_id} value={storm.atcf_id}>
                      {storm.name} ({storm.atcf_id}) · {storm.advisory_count}{" "}
                      advisories
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-1.5 text-xs">
                <label
                  htmlFor="replay-location-picker"
                  className="font-semibold text-slate-700 dark:text-slate-300"
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
                  className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs text-slate-900 focus:border-sky-500 focus:outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
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
        </div>
      </section>

      {!corpusEnabled && (
        <section
          aria-label="Replay corpus configuration"
          data-testid="replay-corpus-disabled"
          className="rounded-lg border border-amber-300 bg-amber-50/90 p-5 text-sm text-amber-950 dark:border-amber-700/80 dark:bg-amber-950/50 dark:text-amber-100"
        >
          <div className="flex items-start gap-3">
            <ShieldAlert
              className="mt-0.5 h-5 w-5 shrink-0 text-amber-700 dark:text-amber-400"
              aria-hidden="true"
            />
            <div className="space-y-2">
              <h2 className="font-semibold">
                No historical replay corpus is configured
              </h2>
              <p className="text-xs leading-relaxed">
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
                  uv run python scripts/fetch_replay_corpus.py convert --full
                  --out DIR
                </code>
                .
              </p>
            </div>
          </div>
        </section>
      )}

      {corpusEnabled && locations.length === 0 && !locationsQuery.isLoading && (
        <section
          aria-label="No stored locations for replay"
          data-testid="replay-no-locations"
          className="rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300"
        >
          <p className="font-semibold text-slate-900 dark:text-slate-100">
            No watched locations stored
          </p>
          <p className="mt-1 text-xs">
            Add a watched location in Settings to scrub historical storm
            timelines against it.
          </p>
          <div className="mt-3">
            <Link
              to="/settings"
              className="inline-flex items-center rounded-md bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 dark:bg-sky-500 dark:text-slate-950"
            >
              Add a location in Settings
            </Link>
          </div>
        </section>
      )}

      {timelineQuery.isError && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
        >
          {formatRouteError(
            `/api/replay/${activeStorm?.atcf_id ?? ""}/timeline`,
            timelineQuery.error instanceof ApiRequestError
              ? timelineQuery.error.status
              : undefined,
          )}
        </div>
      )}

      {corpusEnabled && timeline && activeStep && (
        <>
          <div
            role="status"
            data-testid="replay-banner"
            className="rounded-lg border border-amber-400 bg-amber-50 px-4 py-2.5 text-xs font-semibold text-amber-950 dark:border-amber-600/80 dark:bg-amber-950/70 dark:text-amber-100"
          >
            Replay: {timeline.name} advisory {activeStep.advisory}, issued{" "}
            {formatUtc(activeStep.issued_at)} — not live
          </div>

          <section
            aria-label="Replay advisory scrubber"
            className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <button
                  ref={playButtonRef}
                  type="button"
                  aria-label={isPlaying ? "Pause" : "Play"}
                  onClick={handleTogglePlay}
                  disabled={steps.length <= 1}
                  className="inline-flex items-center gap-1.5 rounded-md bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-sky-500 dark:text-slate-950"
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
                <span className="text-xs text-slate-600 dark:text-slate-400">
                  Step {String(activeStepIndex + 1)} of {String(steps.length)} ·
                  Advisory {activeStep.advisory} ({activeStep.advisory_id})
                </span>
              </div>

              <div className="flex items-center gap-2">
                <ThreatLevelBadge
                  level={activeStep.level.number}
                  atLeast={!activeStep.complete}
                  size="sm"
                />
                <span className="text-xs text-slate-600 dark:text-slate-400">
                  Rule:{" "}
                  <code className="rounded bg-slate-100 px-1 py-0.5 font-mono dark:bg-slate-800">
                    {activeStep.rule}
                  </code>
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

            <LevelHistoryChart
              location={timeline.location}
              timeZone={timeline.time_zone}
              points={chartPoints}
              activeAsOf={activeStep.issued_at}
            />
          </section>

          {timeline.notes.length > 0 && (
            <section
              aria-label="Replay notes"
              data-testid="replay-notes"
              className="rounded-lg border border-amber-300 bg-amber-50/70 p-3.5 text-xs text-amber-950 dark:border-amber-700/70 dark:bg-amber-950/40 dark:text-amber-100"
            >
              <h2 className="font-semibold">Replay notes</h2>
              <ul className="mt-1 list-disc space-y-1 pl-4">
                {timeline.notes.map((note, idx) => (
                  <li key={`note-${String(idx)}`}>{note}</li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <div
        className={
          corpusEnabled && timeline && activeStep
            ? "grid grid-cols-1 gap-5 lg:grid-cols-2"
            : "hidden"
        }
      >
        <section
          aria-label="Replay advisory map"
          className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
              Advisory map
            </h2>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              {replayLayerItems.map((layer) => (
                <label
                  key={layer.key}
                  className="inline-flex cursor-pointer items-center gap-1 text-slate-700 dark:text-slate-300"
                >
                  <input
                    type="checkbox"
                    checked={isLayerVisible(visibility, layer.key)}
                    onChange={() => handleToggleLayer(layer.key)}
                    className="rounded border-slate-300 text-sky-600 focus:ring-sky-500 dark:border-slate-700"
                  />
                  <span>{layer.label}</span>
                </label>
              ))}
            </div>
          </div>

          <div
            ref={mapContainerRef}
            data-testid="replay-leaflet-map"
            className="h-96 w-full rounded-md border border-slate-200 dark:border-slate-800"
          />
        </section>

        {assessment && (
          <article
            aria-label={`Replayed assessment for ${assessment.location}`}
            data-testid="replay-assessment-card"
            className="space-y-4 rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="flex flex-col justify-between gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-start dark:border-slate-800">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-bold text-slate-900 sm:text-lg dark:text-slate-100">
                    {assessment.location}
                  </h2>
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                    {assessment.inside_nws_coverage
                      ? "Inside NWS coverage"
                      : "Outside NWS coverage"}
                  </span>
                </div>
                <p className="text-xs text-slate-600 dark:text-slate-400">
                  Time zone: {assessment.time_zone ?? "UTC"} · Breakpoint span:{" "}
                  {formatBreakpointSpan(assessment.breakpoint_span)}
                </p>
              </div>

              <div className="flex flex-col items-start gap-1 sm:items-end">
                <ThreatLevelBadge
                  level={assessment.level.number}
                  atLeast={!assessment.complete}
                />
                <span className="text-xs text-slate-600 dark:text-slate-400">
                  Issued:{" "}
                  {formatBothTimes(assessment.as_of, assessment.time_zone)}
                </span>
              </div>
            </div>

            <UnavailableBanner
              complete={assessment.complete}
              unavailable={assessment.unavailable}
            />

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

            {assessment.changes.length > 0 && (
              <div className="space-y-1 text-xs">
                <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                  Changes at this advisory
                </h3>
                <ul className="list-disc space-y-0.5 pl-4 text-slate-700 dark:text-slate-300">
                  {assessment.changes.map((chg, idx) => (
                    <li key={`${chg.kind}-${String(idx)}`}>{chg.detail}</li>
                  ))}
                </ul>
              </div>
            )}
          </article>
        )}
      </div>
    </div>
  );
}
