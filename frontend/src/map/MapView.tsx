// frontend/src/map/MapView.tsx
import { useQuery } from "@tanstack/react-query";
import { Compass, History, Layers, Maximize2, RotateCcw } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import {
  formatAgeSeconds,
  formatRouteError,
  formatUtc,
} from "../pages/format.ts";
import { AdvisorySlider } from "./AdvisorySlider.tsx";
import {
  DEFAULT_LAYER_VISIBILITY,
  isLayerVisible,
  LAYER_TOGGLE_ITEMS,
  type LayerVisibility,
  MAP_LEGEND_SECTIONS,
  type MapAdvisoriesResponse,
  type MapDepthResponse,
  type MapLayerKey,
  type MapResponse,
  NOWCOAST_AGE_NOTE,
  type WindProbabilityResponse,
} from "./layers.ts";
import { useLeafletMap } from "./useLeafletMap.ts";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type LocationsResponse = components["schemas"]["LocationsResponse"];
export type ReplayStormsResponse =
  components["schemas"]["ReplayStormsResponse"];

export type ProbabilityThresholdKt = 34 | 50 | 64;
export const PROBABILITY_THRESHOLDS: readonly ProbabilityThresholdKt[] = [
  34, 50, 64,
] as const;

async function fetchMap(snapshotId?: string): Promise<MapResponse> {
  const { data, response } = await apiClient.GET("/api/map", {
    params: snapshotId
      ? {
          query: {
            snapshot_id: snapshotId,
          },
        }
      : undefined,
  });
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/map", response.status);
  }
  return data;
}

async function fetchMapAdvisories(): Promise<MapAdvisoriesResponse> {
  const { data, response } = await apiClient.GET("/api/map/advisories");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/map/advisories", response.status);
  }
  return data;
}

async function fetchMapDepth(
  snapshotId: string | null,
): Promise<MapDepthResponse> {
  const { data, response } = await apiClient.GET("/api/map/depth", {
    params: snapshotId
      ? {
          query: {
            snapshot_id: snapshotId,
          },
        }
      : undefined,
  });
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/map/depth", response.status);
  }
  return data;
}

async function fetchMapWindProbabilities(
  thresholdKt: ProbabilityThresholdKt,
  snapshotId: string | null,
): Promise<WindProbabilityResponse> {
  const { data, response } = await apiClient.GET(
    "/api/map/wind-probabilities",
    {
      params: {
        query: {
          threshold_kt: thresholdKt,
          ...(snapshotId ? { snapshot_id: snapshotId } : {}),
        },
      },
    },
  );
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/map/wind-probabilities", response.status);
  }
  return data;
}

async function fetchReplayWindProbabilities(
  atcfId: string,
  advisory: string,
  thresholdKt: ProbabilityThresholdKt,
): Promise<WindProbabilityResponse> {
  const { data, response } = await apiClient.GET(
    "/api/replay/{atcf_id}/{advisory}/wind-probabilities",
    {
      params: {
        path: {
          atcf_id: atcfId,
          advisory,
        },
        query: {
          threshold_kt: thresholdKt,
        },
      },
    },
  );
  if (!response.ok || !data) {
    throw new ApiRequestError(
      `/api/replay/${atcfId}/${advisory}/wind-probabilities`,
      response.status,
    );
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

async function fetchReplayStorms(): Promise<ReplayStormsResponse> {
  const { data, response } = await apiClient.GET("/api/replay");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/replay", response.status);
  }
  return data;
}

async function fetchReplayAdvisory(
  atcfId: string,
  advisory: string,
): Promise<MapResponse> {
  const { data, response } = await apiClient.GET(
    "/api/replay/{atcf_id}/{advisory}",
    {
      params: {
        path: {
          atcf_id: atcfId,
          advisory,
        },
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

function updateVisibility(
  current: LayerVisibility,
  key: MapLayerKey,
  checked: boolean,
): LayerVisibility {
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

export function MapView() {
  const [visibility, setVisibility] = useState<LayerVisibility>(
    DEFAULT_LAYER_VISIBILITY,
  );
  const [selectedStormId, setSelectedStormId] = useState<string>("");
  const [selectedAdvisory, setSelectedAdvisory] = useState<string>("");
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(
    null,
  );
  const [headSnapshotAtSelection, setHeadSnapshotAtSelection] = useState<
    string | null
  >(null);
  const [probThresholdKt, setProbThresholdKt] =
    useState<ProbabilityThresholdKt>(34);
  const [overlayErrors, setOverlayErrors] = useState<{
    readonly radar: boolean;
    readonly satellite: boolean;
  }>({
    radar: false,
    satellite: false,
  });

  const mapQuery = useQuery({
    queryKey: queryKeys.map(),
    queryFn: () => fetchMap(),
  });

  const locationsQuery = useQuery({
    queryKey: queryKeys.locations(),
    queryFn: fetchLocations,
  });

  const healthQuery = useQuery({
    queryKey: queryKeys.health(),
    queryFn: fetchHealth,
  });

  const corpusEnabled = healthQuery.data?.corpus === true;

  const replayStormsQuery = useQuery({
    queryKey: queryKeys.replay(),
    queryFn: fetchReplayStorms,
    enabled: corpusEnabled,
  });

  const isReplaying =
    corpusEnabled && selectedStormId !== "" && selectedAdvisory !== "";

  const advisoriesQuery = useQuery({
    queryKey: queryKeys.mapAdvisories(),
    queryFn: fetchMapAdvisories,
    enabled: !isReplaying,
  });

  const isViewingPastAdvisory = !isReplaying && selectedSnapshotId !== null;

  const pastMapQuery = useQuery({
    queryKey: queryKeys.mapSnapshot(selectedSnapshotId ?? ""),
    queryFn: () => fetchMap(selectedSnapshotId ?? undefined),
    enabled: isViewingPastAdvisory,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const replayAdvisoryQuery = useQuery({
    queryKey: queryKeys.replayAdvisory(selectedStormId, selectedAdvisory),
    queryFn: () => fetchReplayAdvisory(selectedStormId, selectedAdvisory),
    enabled: isReplaying,
  });

  const primaryTimeZone =
    locationsQuery.data?.locations.find((loc) => loc.nws?.time_zone)?.nws
      ?.time_zone ?? "America/New_York";

  const activeMapData = isReplaying
    ? (replayAdvisoryQuery.data ?? mapQuery.data)
    : isViewingPastAdvisory
      ? (pastMapQuery.data ?? mapQuery.data)
      : mapQuery.data;

  const availableLayerSet = useMemo(() => {
    const list = activeMapData?.available_layers;
    if (!list || list.length === 0) {
      return null;
    }
    return new Set<string>(list);
  }, [activeMapData?.available_layers]);

  const isLayerAvailable = useCallback(
    (key: MapLayerKey): boolean => {
      if (isViewingPastAdvisory && (key === "radar" || key === "satellite")) {
        return false;
      }
      if (!availableLayerSet) {
        if (isReplaying) {
          return (
            key !== "wind_radii" &&
            key !== "past_track" &&
            key !== "peak_surge" &&
            key !== "radar" &&
            key !== "satellite"
          );
        }
        return true;
      }
      return availableLayerSet.has(key);
    },
    [availableLayerSet, isReplaying, isViewingPastAdvisory],
  );

  const effectiveVisibility = useMemo<LayerVisibility>(
    () => ({
      cone: visibility.cone && isLayerAvailable("cone"),
      track: visibility.track && isLayerAvailable("track"),
      points: visibility.points && isLayerAvailable("points"),
      watches_warnings:
        visibility.watches_warnings && isLayerAvailable("watches_warnings"),
      outlook: visibility.outlook && isLayerAvailable("outlook"),
      locations: visibility.locations && isLayerAvailable("locations"),
      wind_radii: visibility.wind_radii && isLayerAvailable("wind_radii"),
      past_track: visibility.past_track && isLayerAvailable("past_track"),
      peak_surge: visibility.peak_surge && isLayerAvailable("peak_surge"),
      wind_probabilities:
        visibility.wind_probabilities && isLayerAvailable("wind_probabilities"),
      radar: visibility.radar && isLayerAvailable("radar"),
      satellite: visibility.satellite && isLayerAvailable("satellite"),
    }),
    [visibility, isLayerAvailable],
  );

  const needsDepth =
    !isReplaying &&
    (effectiveVisibility.wind_radii ||
      effectiveVisibility.past_track ||
      effectiveVisibility.peak_surge);

  const depthQuery = useQuery({
    queryKey: queryKeys.mapDepth(selectedSnapshotId),
    queryFn: () => fetchMapDepth(selectedSnapshotId),
    enabled: needsDepth,
  });

  const windProbScopeKey = isReplaying
    ? `replay:${selectedStormId}:${selectedAdvisory}`
    : (selectedSnapshotId ?? "latest");

  const windProbQuery = useQuery({
    queryKey: queryKeys.mapWindProbabilities(
      windProbScopeKey,
      probThresholdKt,
    ),
    queryFn: () =>
      isReplaying
        ? fetchReplayWindProbabilities(
            selectedStormId,
            selectedAdvisory,
            probThresholdKt,
          )
        : fetchMapWindProbabilities(probThresholdKt, selectedSnapshotId),
    enabled: effectiveVisibility.wind_probabilities,
  });

  const handleOverlayError = useCallback((layer: "radar" | "satellite") => {
    setOverlayErrors((prev) =>
      layer === "radar"
        ? { ...prev, radar: true }
        : { ...prev, satellite: true },
    );
  }, []);

  const viewModeKey =
    isReplaying && replayAdvisoryQuery.data
      ? `replay:${selectedStormId}:${selectedAdvisory}`
      : isViewingPastAdvisory
        ? `stored:${selectedSnapshotId}`
        : "live";

  const { containerRef, fitToData } = useLeafletMap({
    mapData: activeMapData,
    depthData: needsDepth ? (depthQuery.data ?? null) : null,
    visibility: effectiveVisibility,
    overlays: {
      windProbabilities: windProbQuery.data ?? null,
      showWindProbabilities: effectiveVisibility.wind_probabilities,
      radar: effectiveVisibility.radar,
      satellite: effectiveVisibility.satellite,
      onOverlayError: handleOverlayError,
    },
    timeZone: primaryTimeZone,
    viewModeKey,
  });

  const advisoriesSteps = advisoriesQuery.data?.steps ?? [];
  const currentHeadSnapshotId =
    advisoriesSteps[0]?.snapshot_id ?? mapQuery.data?.snapshot_id ?? null;

  const newerAdvisoryArrived =
    isViewingPastAdvisory &&
    headSnapshotAtSelection !== null &&
    currentHeadSnapshotId !== null &&
    currentHeadSnapshotId !== headSnapshotAtSelection;

  const handleSelectSnapshotId = (nextSnapshotId: string | null) => {
    if (nextSnapshotId === null) {
      setSelectedSnapshotId(null);
      setHeadSnapshotAtSelection(null);
      return;
    }
    if (selectedSnapshotId === null) {
      setHeadSnapshotAtSelection(currentHeadSnapshotId);
    }
    setSelectedSnapshotId(nextSnapshotId);
  };

  const replayStorms = replayStormsQuery.data?.storms ?? [];
  const selectedStormSummary =
    replayStorms.find((s) => s.atcf_id === selectedStormId) ?? null;

  const handleStormChange = (nextStormId: string) => {
    if (nextStormId === "") {
      setSelectedStormId("");
      setSelectedAdvisory("");
      return;
    }
    setSelectedSnapshotId(null);
    setHeadSnapshotAtSelection(null);
    setSelectedStormId(nextStormId);
    const matchingStorm = replayStorms.find((s) => s.atcf_id === nextStormId);
    const defaultAdv = matchingStorm?.advisories[0] ?? "";
    setSelectedAdvisory(defaultAdv);
  };

  const handleBackToLive = () => {
    setSelectedStormId("");
    setSelectedAdvisory("");
  };

  const handleToggleChange = (key: MapLayerKey, checked: boolean) => {
    if (checked && key === "radar") {
      setOverlayErrors((prev) => ({ ...prev, radar: false }));
    }
    if (checked && key === "satellite") {
      setOverlayErrors((prev) => ({ ...prev, satellite: false }));
    }
    setVisibility((prev) => updateVisibility(prev, key, checked));
  };

  const replayedStormLayer =
    isReplaying && replayAdvisoryQuery.data
      ? replayAdvisoryQuery.data.storms[0]
      : undefined;

  const replayStormLabel = replayedStormLayer
    ? `${replayedStormLayer.name} (${replayedStormLayer.atcf_id.toUpperCase()})`
    : selectedStormSummary
      ? `${selectedStormSummary.name} (${selectedStormSummary.atcf_id.toUpperCase()})`
      : selectedStormId.toUpperCase();

  const replayAdvisoryLabel =
    selectedAdvisory !== ""
      ? selectedAdvisory
      : (replayedStormLayer?.advisory ?? "");

  const replayIssuedLabel = formatUtc(
    replayedStormLayer?.issued_at ?? replayAdvisoryQuery.data?.as_of,
  );

  return (
    <div className="min-w-0 space-y-4">
      <section
        aria-label="Map header and controls"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div className="min-w-0 space-y-1">
            <div className="flex items-center gap-2">
              <Compass
                className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
                aria-hidden="true"
              />
              <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                Map
              </h1>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-300">
              {activeMapData?.as_of ? (
                <>
                  Origin:{" "}
                  <strong className="font-semibold text-slate-800 dark:text-slate-100">
                    {activeMapData.origin ?? "live"}
                  </strong>{" "}
                  · status{" "}
                  <strong className="font-semibold text-slate-800 dark:text-slate-100">
                    {activeMapData.status ?? "complete"}
                  </strong>{" "}
                  · as of {formatUtc(activeMapData.as_of)} ·{" "}
                  {String(activeMapData.storms.length)} active{" "}
                  {activeMapData.storms.length === 1 ? "storm" : "storms"}
                </>
              ) : (
                "No stored snapshot geometry yet. Showing default Atlantic basin view."
              )}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={fitToData}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
            >
              <Maximize2 className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Fit</span>
            </button>
          </div>
        </div>
      </section>

      {mapQuery.isError && !isReplaying && !isViewingPastAdvisory && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
        >
          {formatRouteError(
            "/api/map",
            mapQuery.error instanceof ApiRequestError
              ? mapQuery.error.status
              : undefined,
          )}
        </div>
      )}

      {pastMapQuery.isError && isViewingPastAdvisory && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
        >
          {formatRouteError(
            "/api/map",
            pastMapQuery.error instanceof ApiRequestError
              ? pastMapQuery.error.status
              : undefined,
          )}
        </div>
      )}

      {replayAdvisoryQuery.isError && isReplaying && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
        >
          {formatRouteError(
            `/api/replay/${selectedStormId}/${selectedAdvisory}`,
            replayAdvisoryQuery.error instanceof ApiRequestError
              ? replayAdvisoryQuery.error.status
              : undefined,
          )}
        </div>
      )}

      {!isReplaying && advisoriesSteps.length > 1 && (
        <AdvisorySlider
          steps={advisoriesSteps}
          selectedSnapshotId={selectedSnapshotId}
          onSelectSnapshotId={handleSelectSnapshotId}
          newerAdvisoryArrived={newerAdvisoryArrived}
        />
      )}

      {corpusEnabled && (
        <section
          aria-label="Replay corpus controls"
          data-testid="replay-panel"
          className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div className="grid min-w-0 flex-1 grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="min-w-0">
                <label
                  htmlFor="replay-storm-select"
                  className="flex items-center gap-1.5 text-xs font-semibold text-slate-800 dark:text-slate-200"
                >
                  <History
                    className="h-3.5 w-3.5 text-sky-600 dark:text-sky-400"
                    aria-hidden="true"
                  />
                  <span>Replay storm</span>
                </label>
                <select
                  id="replay-storm-select"
                  aria-label="Replay storm"
                  value={selectedStormId}
                  onChange={(e) => handleStormChange(e.target.value)}
                  className="mt-1 w-full max-w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                >
                  <option value="">Live map (select a storm to replay)</option>
                  {replayStorms.map((storm) => (
                    <option key={storm.atcf_id} value={storm.atcf_id}>
                      {storm.name} ({storm.atcf_id.toUpperCase()}) —{" "}
                      {String(storm.advisory_count)} advisories
                    </option>
                  ))}
                </select>
              </div>

              <div className="min-w-0">
                <label
                  htmlFor="replay-advisory-select"
                  className="block text-xs font-semibold text-slate-800 dark:text-slate-200"
                >
                  Replay advisory
                </label>
                <select
                  id="replay-advisory-select"
                  aria-label="Replay advisory"
                  value={selectedAdvisory}
                  disabled={!selectedStormSummary}
                  onChange={(e) => setSelectedAdvisory(e.target.value)}
                  className="mt-1 w-full max-w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                >
                  {!selectedStormSummary ? (
                    <option value="">Select a storm first</option>
                  ) : (
                    selectedStormSummary.advisories.map((adv) => (
                      <option key={adv} value={adv}>
                        Advisory {adv}
                      </option>
                    ))
                  )}
                </select>
              </div>
            </div>

            {isReplaying && (
              <button
                type="button"
                onClick={handleBackToLive}
                className="inline-flex items-center justify-center gap-1.5 rounded-md bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:bg-sky-500 dark:text-slate-950"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                <span>Back to live</span>
              </button>
            )}
          </div>

          {isReplaying && (
            <div
              role="status"
              data-testid="replay-not-live-banner"
              className="mt-3 rounded-md border border-amber-400 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-950 dark:border-amber-600 dark:bg-amber-950/70 dark:text-amber-100"
            >
              Replay: {replayStormLabel} advisory {replayAdvisoryLabel}, issued{" "}
              {replayIssuedLabel} — not live
            </div>
          )}
        </section>
      )}

      <div
        ref={containerRef}
        data-testid="leaflet-map-container"
        aria-label="Tropical cyclone threat map"
        className="relative z-0 h-[280px] w-full overflow-hidden rounded-lg border border-slate-300 bg-slate-100 shadow-xs sm:h-[520px] dark:border-slate-700 dark:bg-slate-900"
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <section
          aria-label="Map layer toggles"
          className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="flex items-center gap-2 border-b border-slate-200 pb-2.5 dark:border-slate-800">
            <Layers
              className="h-4 w-4 shrink-0 text-sky-600 dark:text-sky-400"
              aria-hidden="true"
            />
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              Layer Toggles
            </h2>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-1">
            {LAYER_TOGGLE_ITEMS.map((item) => {
              const available = isLayerAvailable(item.key);
              const checked =
                available && isLayerVisible(visibility, item.key);
              const unavailableReason = !available
                ? isReplaying
                  ? "not in this corpus"
                  : isViewingPastAdvisory
                    ? "live only"
                    : "unavailable"
                : null;
              return (
                <label
                  key={item.key}
                  className={`flex items-center justify-between gap-2.5 rounded-md border border-slate-200 bg-slate-50/70 px-3 py-2 text-xs font-medium text-slate-800 dark:border-slate-800 dark:bg-slate-800/40 dark:text-slate-200 ${
                    available
                      ? "cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800"
                      : "cursor-not-allowed opacity-60"
                  }`}
                >
                  <span className="flex items-center gap-2.5">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!available}
                      onChange={(e) =>
                        handleToggleChange(item.key, e.target.checked)
                      }
                      className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-600 disabled:cursor-not-allowed dark:border-slate-600 dark:bg-slate-900"
                    />
                    <span>{item.label}</span>
                  </span>
                  {unavailableReason && (
                    <span className="text-[11px] font-normal text-slate-500 dark:text-slate-400">
                      ({unavailableReason})
                    </span>
                  )}
                </label>
              );
            })}
          </div>

          {effectiveVisibility.wind_probabilities && (
            <div
              data-testid="wind-probability-controls"
              className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/50"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label
                  htmlFor="wind-probability-threshold"
                  className="font-semibold text-slate-800 dark:text-slate-200"
                >
                  Wind speed threshold
                </label>
                <select
                  id="wind-probability-threshold"
                  aria-label="Wind speed threshold"
                  value={probThresholdKt}
                  onChange={(e) => {
                    const parsed = Number.parseInt(e.target.value, 10);
                    if (parsed === 34 || parsed === 50 || parsed === 64) {
                      setProbThresholdKt(parsed);
                    }
                  }}
                  className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                >
                  {PROBABILITY_THRESHOLDS.map((kt) => (
                    <option key={kt} value={kt}>
                      {String(kt)} kt
                    </option>
                  ))}
                </select>
              </div>
              <p className="mt-1.5 text-[11px] text-slate-600 dark:text-slate-300">
                Chance of winds at this speed within 120 hours
              </p>
              {windProbQuery.data?.coverage && (
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                  Extract coverage window outlined (dashed border).
                </p>
              )}
            </div>
          )}
        </section>

        <section
          aria-label="Map legend"
          className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs lg:col-span-2 dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 pb-2.5 dark:border-slate-800">
            <h2 className="text-sm font-bold text-slate-900 dark:text-slate-100">
              Map Legend
            </h2>
            {healthQuery.data?.now && (
              <span className="text-[11px] text-slate-500 dark:text-slate-400">
                Server clock: {formatUtc(healthQuery.data.now)} (
                {formatAgeSeconds(0)})
              </span>
            )}
          </div>

          {(effectiveVisibility.radar || effectiveVisibility.satellite) && (
            <p
              data-testid="nowcoast-age-note"
              className="mt-2.5 text-xs text-slate-600 dark:text-slate-300"
            >
              {NOWCOAST_AGE_NOTE}
            </p>
          )}

          {overlayErrors.radar && effectiveVisibility.radar && (
            <div
              role="status"
              data-testid="radar-unavailable-banner"
              className="mt-2.5 rounded-md border border-amber-400 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-950 dark:border-amber-600 dark:bg-amber-950/70 dark:text-amber-100"
            >
              Radar unavailable
            </div>
          )}

          {overlayErrors.satellite && effectiveVisibility.satellite && (
            <div
              role="status"
              data-testid="satellite-unavailable-banner"
              className="mt-2.5 rounded-md border border-amber-400 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-950 dark:border-amber-600 dark:bg-amber-950/70 dark:text-amber-100"
            >
              Satellite unavailable
            </div>
          )}

          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {MAP_LEGEND_SECTIONS.map((section) => (
              <div
                key={section.category}
                className="rounded-md border border-slate-200 bg-slate-50/70 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/40"
              >
                <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                  {section.title}
                </h3>
                <ul className="mt-1.5 space-y-1 text-slate-700 dark:text-slate-300">
                  {section.items.map((swatch) => (
                    <li
                      key={swatch.label}
                      className="flex items-center gap-2"
                    >
                      <span
                        aria-hidden="true"
                        className={`inline-block shrink-0 ${swatch.swatchClass}`}
                      />
                      <span>{swatch.label}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
