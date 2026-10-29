// frontend/src/map/MapView.tsx
import { useQuery } from "@tanstack/react-query";
import { Compass, History, Layers, Maximize2, RotateCcw } from "lucide-react";
import { useState } from "react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import {
  formatAgeSeconds,
  formatRouteError,
  formatUtc,
} from "../pages/format.ts";
import {
  DEFAULT_LAYER_VISIBILITY,
  isLayerVisible,
  LAYER_TOGGLE_ITEMS,
  type LayerVisibility,
  MAP_LEGEND_SECTIONS,
  type MapLayerKey,
  type MapResponse,
} from "./layers.ts";
import { useLeafletMap } from "./useLeafletMap.ts";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type LocationsResponse = components["schemas"]["LocationsResponse"];
export type ReplayStormsResponse =
  components["schemas"]["ReplayStormsResponse"];

async function fetchMap(): Promise<MapResponse> {
  const { data, response } = await apiClient.GET("/api/map");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/map", response.status);
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
  }
}

export function MapView() {
  const [visibility, setVisibility] = useState<LayerVisibility>(
    DEFAULT_LAYER_VISIBILITY,
  );
  const [selectedStormId, setSelectedStormId] = useState<string>("");
  const [selectedAdvisory, setSelectedAdvisory] = useState<string>("");

  const mapQuery = useQuery({
    queryKey: queryKeys.map(),
    queryFn: fetchMap,
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
    : mapQuery.data;

  const viewModeKey =
    isReplaying && replayAdvisoryQuery.data
      ? `replay:${selectedStormId}:${selectedAdvisory}`
      : "live";

  const { containerRef, fitToData } = useLeafletMap({
    mapData: activeMapData,
    visibility,
    timeZone: primaryTimeZone,
    viewModeKey,
  });

  const replayStorms = replayStormsQuery.data?.storms ?? [];
  const selectedStormSummary =
    replayStorms.find((s) => s.atcf_id === selectedStormId) ?? null;

  const handleStormChange = (nextStormId: string) => {
    if (nextStormId === "") {
      setSelectedStormId("");
      setSelectedAdvisory("");
      return;
    }
    setSelectedStormId(nextStormId);
    const matchingStorm = replayStorms.find((s) => s.atcf_id === nextStormId);
    const defaultAdv = matchingStorm?.advisories[0] ?? "";
    setSelectedAdvisory(defaultAdv);
  };

  const handleBackToLive = () => {
    setSelectedStormId("");
    setSelectedAdvisory("");
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

      {mapQuery.isError && !isReplaying && (
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
              const checked = isLayerVisible(visibility, item.key);
              return (
                <label
                  key={item.key}
                  className="flex cursor-pointer items-center gap-2.5 rounded-md border border-slate-200 bg-slate-50/70 px-3 py-2 text-xs font-medium text-slate-800 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-800/40 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) =>
                      setVisibility((prev) =>
                        updateVisibility(prev, item.key, e.target.checked),
                      )
                    }
                    className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-600 dark:border-slate-600 dark:bg-slate-900"
                  />
                  <span>{item.label}</span>
                </label>
              );
            })}
          </div>
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
