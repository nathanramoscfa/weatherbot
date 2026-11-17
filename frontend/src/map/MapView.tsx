// frontend/src/map/MapView.tsx
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { formatRouteError } from "../pages/format.ts";
import { AdvisorySlider } from "./AdvisorySlider.tsx";
import {
  DEFAULT_LAYER_VISIBILITY,
  type LayerVisibility,
  type MapAdvisoriesResponse,
  type MapDepthResponse,
  type MapLayerKey,
  type MapResponse,
  type WindProbabilityResponse,
} from "./layers.ts";
import {
  isDefaultDesktopViewport,
  MapLayersPanel,
  MapLegendPanel,
  MapStatusChip,
  PROBABILITY_THRESHOLDS,
  type ProbabilityThresholdKt,
} from "./MapPanels.tsx";
import { useLeafletMap } from "./useLeafletMap.ts";

export { PROBABILITY_THRESHOLDS, type ProbabilityThresholdKt };

export type HealthResponse = components["schemas"]["HealthResponse"];
export type LocationsResponse = components["schemas"]["LocationsResponse"];

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
  const [layersOpen, setLayersOpen] = useState<boolean>(() =>
    isDefaultDesktopViewport(),
  );
  const [legendOpen, setLegendOpen] = useState<boolean>(() =>
    isDefaultDesktopViewport(),
  );
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

  const advisoriesQuery = useQuery({
    queryKey: queryKeys.mapAdvisories(),
    queryFn: fetchMapAdvisories,
  });

  const isViewingPastAdvisory = selectedSnapshotId !== null;

  const pastMapQuery = useQuery({
    queryKey: queryKeys.mapSnapshot(selectedSnapshotId ?? ""),
    queryFn: () => fetchMap(selectedSnapshotId ?? undefined),
    enabled: isViewingPastAdvisory,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const primaryTimeZone =
    locationsQuery.data?.locations.find((loc) => loc.nws?.time_zone)?.nws
      ?.time_zone ?? "America/New_York";

  const activeMapData = isViewingPastAdvisory
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
        return true;
      }
      return availableLayerSet.has(key);
    },
    [availableLayerSet, isViewingPastAdvisory],
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
    effectiveVisibility.wind_radii ||
    effectiveVisibility.past_track ||
    effectiveVisibility.peak_surge;

  const depthQuery = useQuery({
    queryKey: queryKeys.mapDepth(selectedSnapshotId),
    queryFn: () => fetchMapDepth(selectedSnapshotId),
    enabled: needsDepth,
  });

  const windProbScopeKey = selectedSnapshotId ?? "latest";

  const windProbQuery = useQuery({
    queryKey: queryKeys.mapWindProbabilities(
      windProbScopeKey,
      probThresholdKt,
    ),
    queryFn: () => fetchMapWindProbabilities(probThresholdKt, selectedSnapshotId),
    enabled: effectiveVisibility.wind_probabilities,
  });

  const handleOverlayError = useCallback((layer: "radar" | "satellite") => {
    setOverlayErrors((prev) =>
      layer === "radar"
        ? { ...prev, radar: true }
        : { ...prev, satellite: true },
    );
  }, []);

  const viewModeKey = isViewingPastAdvisory
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

  const handleToggleChange = (key: MapLayerKey, checked: boolean) => {
    if (checked && key === "radar") {
      setOverlayErrors((prev) => ({ ...prev, radar: false }));
    }
    if (checked && key === "satellite") {
      setOverlayErrors((prev) => ({ ...prev, satellite: false }));
    }
    setVisibility((prev) => updateVisibility(prev, key, checked));
  };

  return (
    <div className="min-w-0">
      <h1 className="sr-only">Map</h1>

      <div className="relative h-[calc(100dvh-10rem)] min-h-[70vh] w-full overflow-hidden rounded-card border border-line bg-surface-inset shadow-card">
        <div
          ref={containerRef}
          data-testid="leaflet-map-container"
          aria-label="Tropical cyclone threat map"
          className="relative z-0 isolate h-full min-h-[70vh] w-full"
        />

        {/* Floating HUD panels positioned as siblings of the Leaflet container.
            Status chip links to /replay when corpus is enabled; Layers ("Map layer toggles")
            and Legend ("Map legend") toggle via aria-expanded. */}
        <div className="pointer-events-none absolute top-2.5 right-2.5 left-12 z-10 flex flex-col gap-2.5 lg:top-3 lg:right-72 lg:left-3 xl:right-80">
          <div className="flex flex-col gap-2 lg:min-h-[4.25rem] lg:pl-11">
            <MapStatusChip
              mapData={activeMapData}
              corpusEnabled={corpusEnabled}
              onFit={fitToData}
              className="pointer-events-auto"
            />

            {mapQuery.isError && !isViewingPastAdvisory && (
              <div
                role="alert"
                className="pointer-events-auto rounded-card border border-red-300 bg-red-50 p-3 text-sm text-red-900 shadow-raised dark:border-red-800 dark:bg-red-950 dark:text-red-200"
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
                className="pointer-events-auto rounded-card border border-red-300 bg-red-50 p-3 text-sm text-red-900 shadow-raised dark:border-red-800 dark:bg-red-950 dark:text-red-200"
              >
                {formatRouteError(
                  "/api/map",
                  pastMapQuery.error instanceof ApiRequestError
                    ? pastMapQuery.error.status
                    : undefined,
                )}
              </div>
            )}
          </div>
        </div>

        <div className="pointer-events-none absolute inset-x-2.5 bottom-7 z-10 flex flex-col gap-2 lg:inset-0">
          <div className="pointer-events-auto lg:absolute lg:top-28 lg:left-3 lg:w-64 xl:w-72">
            <MapLayersPanel
              open={layersOpen}
              onToggleOpen={setLayersOpen}
              visibility={visibility}
              effectiveVisibility={effectiveVisibility}
              isLayerAvailable={isLayerAvailable}
              isViewingPastAdvisory={isViewingPastAdvisory}
              onToggleLayer={handleToggleChange}
              probThresholdKt={probThresholdKt}
              onChangeProbThresholdKt={setProbThresholdKt}
              hasWindProbCoverage={Boolean(windProbQuery.data?.coverage)}
            />
          </div>

          <div className="pointer-events-auto lg:absolute lg:top-3 lg:right-3 lg:w-64 xl:w-72">
            <MapLegendPanel
              open={legendOpen}
              onToggleOpen={setLegendOpen}
              effectiveVisibility={effectiveVisibility}
              serverNow={healthQuery.data?.now}
              overlayErrors={overlayErrors}
            />
          </div>

          {advisoriesSteps.length > 1 && (
            <div className="pointer-events-auto lg:absolute lg:right-72 lg:bottom-7 lg:left-72 xl:right-80 xl:left-80">
              <AdvisorySlider
                steps={advisoriesSteps}
                selectedSnapshotId={selectedSnapshotId}
                onSelectSnapshotId={handleSelectSnapshotId}
                newerAdvisoryArrived={newerAdvisoryArrived}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
