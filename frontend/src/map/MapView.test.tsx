// frontend/src/map/MapView.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as L from "leaflet";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import healthFixture from "../test/fixtures/health.json";
import locationsFixture from "../test/fixtures/locations.json";
import mapFixture from "../test/fixtures/map.json";
import replayFixture from "../test/fixtures/replay.json";
import replayAdvisoryFixture from "../test/fixtures/replay-advisory.json";
import {
  type AnnotatedLeafletLayer,
  DEFAULT_ATLANTIC_CENTER,
  DEFAULT_ATLANTIC_ZOOM,
  DEFAULT_ON_LAYER_KEYS,
  LAYER_TOGGLE_ITEMS,
  type MapAdvisoriesResponse,
  type MapDepthResponse,
  type MapLayerKey,
  type MapResponse,
  type WindProbabilityResponse,
} from "./layers.ts";
import { MapView } from "./MapView.tsx";
import {
  getActiveLeafletMaps,
  getLatestLeafletMap,
} from "./useLeafletMap.ts";

const TYPED_MAP = asSchema<MapResponse>(
  mapFixture satisfies JsonFixture<MapResponse>,
);
const TYPED_LOCATIONS = asSchema<components["schemas"]["LocationsResponse"]>(
  locationsFixture satisfies JsonFixture<
    components["schemas"]["LocationsResponse"]
  >,
);
const TYPED_HEALTH = asSchema<components["schemas"]["HealthResponse"]>(
  healthFixture satisfies JsonFixture<components["schemas"]["HealthResponse"]>,
);
const TYPED_REPLAY = asSchema<components["schemas"]["ReplayStormsResponse"]>(
  replayFixture satisfies JsonFixture<
    components["schemas"]["ReplayStormsResponse"]
  >,
);
const TYPED_REPLAY_ADVISORY = asSchema<MapResponse>(
  replayAdvisoryFixture satisfies JsonFixture<MapResponse>,
);

const SYNTHETIC_DEPTH: MapDepthResponse = {
  snapshot_id: TYPED_MAP.snapshot_id,
  as_of: TYPED_MAP.as_of,
  storms: [
    {
      atcf_id: TYPED_MAP.storms[0]!.atcf_id,
      wind_radii: {
        type: "FeatureCollection",
        crs: { name: "EPSG:4326", datum: null },
        features: [
          {
            type: "Feature",
            crs: { name: "EPSG:4326", datum: null },
            properties: {
              threshold_kt: 34,
              tau_h: 0,
              valid_at: "2026-10-12T18:00:00Z",
              ne_extent_nmi: 90,
              se_extent_nmi: 80,
              sw_extent_nmi: 60,
              nw_extent_nmi: 75,
              advisory: "15",
            },
            geometry: {
              type: "Polygon",
              crs: { name: "EPSG:4326", datum: null },
              coordinates: [
                [
                  [-80.2, 25.5],
                  [-79.8, 25.5],
                  [-79.8, 25.9],
                  [-80.2, 25.5],
                ],
              ],
            },
          },
        ],
      },
      past_track: {
        type: "FeatureCollection",
        crs: { name: "EPSG:4326", datum: null },
        features: [
          {
            type: "Feature",
            crs: { name: "EPSG:4326", datum: null },
            properties: { stormtype: "HU", ss: 2 },
            geometry: {
              type: "LineString",
              crs: { name: "EPSG:4326", datum: null },
              coordinates: [
                [-81.5, 24.5],
                [-80.5, 25.2],
              ],
            },
          },
        ],
      },
      past_points: {
        type: "FeatureCollection",
        crs: { name: "EPSG:4326", datum: null },
        features: [
          {
            type: "Feature",
            crs: { name: "EPSG:4326", datum: null },
            properties: {
              stormtype: "HU",
              ss: 2,
              intensity: 85,
              mslp: 972,
              dtg: "2026-10-12 18:00 UTC",
            },
            geometry: {
              type: "Point",
              crs: { name: "EPSG:4326", datum: null },
              coordinates: [-80.5, 25.2],
            },
          },
        ],
      },
    },
  ],
  peak_surge: {
    type: "FeatureCollection",
    crs: { name: "EPSG:4326", datum: null },
    features: [
      {
        type: "Feature",
        crs: { name: "EPSG:4326", datum: null },
        properties: { name: "Tampa Bay...8-12 ft", layer: "Polygons" },
        geometry: {
          type: "Polygon",
          crs: { name: "EPSG:4326", datum: null },
          coordinates: [
            [
              [-82.75, 27.55],
              [-82.42, 27.55],
              [-82.42, 27.95],
              [-82.75, 27.55],
            ],
          ],
        },
      },
    ],
  },
  notice: TYPED_MAP.notice,
};

const SYNTHETIC_PROBABILITIES: WindProbabilityResponse = {
  snapshot_id: TYPED_MAP.snapshot_id,
  synoptic_at: "2026-10-12T18:00:00Z",
  threshold_kt: 34,
  bands: {
    type: "FeatureCollection",
    crs: { name: "EPSG:4326", datum: null },
    features: [
      {
        type: "Feature",
        crs: { name: "EPSG:4326", datum: null },
        properties: {
          lower_pct: 5,
          upper_pct: 10,
          label: "5-10%",
          geometry_note: "Simplified for display (tolerance 0.03 deg)",
        },
        geometry: {
          type: "Polygon",
          crs: { name: "EPSG:4326", datum: null },
          coordinates: [
            [
              [-81.2, 25.1],
              [-80.1, 25.1],
              [-80.1, 26.2],
              [-81.2, 25.1],
            ],
          ],
        },
      },
    ],
  },
  coverage: {
    type: "Feature",
    crs: { name: "EPSG:4326", datum: null },
    properties: { note: "Extract coverage window" },
    geometry: {
      type: "Polygon",
      crs: { name: "EPSG:4326", datum: null },
      coordinates: [
        [
          [-82.0, 24.5],
          [-79.5, 24.5],
          [-79.5, 27.0],
          [-82.0, 24.5],
        ],
      ],
    },
  },
  notice: TYPED_MAP.notice,
};

function stubCanvasGetContext(): void {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
    () =>
      ({
        save: vi.fn(),
        restore: vi.fn(),
        clearRect: vi.fn(),
        beginPath: vi.fn(),
        moveTo: vi.fn(),
        lineTo: vi.fn(),
        closePath: vi.fn(),
        fill: vi.fn(),
        stroke: vi.fn(),
        arc: vi.fn(),
        rect: vi.fn(),
        clip: vi.fn(),
        setLineDash: vi.fn(),
        setTransform: vi.fn(),
        fillRect: vi.fn(),
        translate: vi.fn(),
        scale: vi.fn(),
      }) as unknown as CanvasRenderingContext2D,
  );
}

function collectOverlayCategories(map: L.Map): Map<MapLayerKey, number> {
  const counts = new Map<MapLayerKey, number>();
  map.eachLayer((layer) => {
    const meta = (layer as AnnotatedLeafletLayer).weatherbotMeta;
    if (meta) {
      counts.set(meta.category, (counts.get(meta.category) ?? 0) + 1);
    }
  });
  return counts;
}

describe("MapView", () => {
  beforeEach(() => {
    stubCanvasGetContext();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mounts inside React.StrictMode leaving one map, draws cone, track, point, segment, outlook, and location layers, and toggles each default-on layer on and off via map.eachLayer", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();

    queryClient.setQueryData(queryKeys.map(), TYPED_MAP);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.health(), {
      ...TYPED_HEALTH,
      corpus: false,
    });
    queryClient.setQueryData(queryKeys.mapAdvisories(), {
      limit: 96,
      steps: [],
      notice: TYPED_MAP.notice,
    } satisfies MapAdvisoriesResponse);

    const { unmount } = render(
      <StrictMode>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <MapView />
          </MemoryRouter>
        </QueryClientProvider>
      </StrictMode>,
    );

    // StrictMode double-mount leaves exactly one active Leaflet map
    expect(getActiveLeafletMaps().size).toBe(1);
    const map = getLatestLeafletMap();
    expect(map).not.toBeNull();

    // Replay panel is absent when health.corpus is false
    expect(screen.queryByTestId("replay-panel")).toBeNull();

    // Visible OpenStreetMap attribution link
    const osmLink = screen.getByRole("link", {
      name: /OpenStreetMap contributors/i,
    });
    expect(osmLink).toHaveAttribute(
      "href",
      "https://www.openstreetmap.org/copyright",
    );

    const defaultOnSet = new Set<MapLayerKey>(DEFAULT_ON_LAYER_KEYS);

    // All 6 default-on categories are present on the map instance; the 6 new depth/overlay categories are off
    const initialCounts = collectOverlayCategories(map!);
    for (const item of LAYER_TOGGLE_ITEMS) {
      const checkbox = screen.getByRole("checkbox", {
        name: item.label,
      });
      if (defaultOnSet.has(item.key)) {
        expect(checkbox).toBeChecked();
        expect(initialCounts.get(item.key) ?? 0).toBeGreaterThan(0);
      } else {
        expect(checkbox).not.toBeChecked();
        expect(initialCounts.get(item.key) ?? 0).toBe(0);
      }
    }

    // Toggling each default-on checkbox removes and re-adds its category's layers
    for (const item of LAYER_TOGGLE_ITEMS.filter((i) =>
      defaultOnSet.has(i.key),
    )) {
      const checkbox = screen.getByRole("checkbox", {
        name: item.label,
      });
      expect(checkbox).toBeChecked();

      await user.click(checkbox);
      expect(checkbox).not.toBeChecked();
      const afterUncheck = collectOverlayCategories(map!);
      expect(afterUncheck.get(item.key) ?? 0).toBe(0);

      await user.click(checkbox);
      expect(checkbox).toBeChecked();
      const afterRecheck = collectOverlayCategories(map!);
      expect(afterRecheck.get(item.key)).toBe(initialCounts.get(item.key));
    }

    unmount();
    expect(getActiveLeafletMaps().size).toBe(0);
  });

  it("shows the replay panel when corpus is true, disables unavailable replay toggles with '(not in this corpus)', loads Irma advisory 036, and returns to live on 'Back to live'", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();

    queryClient.setQueryData(queryKeys.map(), TYPED_MAP);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.health(), {
      ...TYPED_HEALTH,
      corpus: true,
    });
    queryClient.setQueryData(queryKeys.replay(), TYPED_REPLAY);
    queryClient.setQueryData(queryKeys.mapAdvisories(), {
      limit: 96,
      steps: [],
      notice: TYPED_MAP.notice,
    } satisfies MapAdvisoriesResponse);

    const getSpy = vi.spyOn(apiClient, "GET").mockImplementation((path) => {
      if (path === "/api/replay/{atcf_id}/{advisory}") {
        return Promise.resolve({
          data: TYPED_REPLAY_ADVISORY,
          response: new Response(null, { status: 200 }),
        } as never);
      }
      if (path === "/api/replay/{atcf_id}/{advisory}/wind-probabilities") {
        return Promise.resolve({
          data: SYNTHETIC_PROBABILITIES,
          response: new Response(null, { status: 200 }),
        } as never);
      }
      return Promise.reject(new Error(`Unexpected GET ${String(path)}`));
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <MapView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("replay-panel")).toBeInTheDocument();
    const map = getLatestLeafletMap()!;
    const fitBoundsSpy = vi.spyOn(map, "fitBounds");

    const stormSelect = screen.getByRole("combobox", {
      name: "Replay storm",
    });
    await user.selectOptions(stormSelect, "AL112017");

    const advisorySelect = screen.getByRole("combobox", {
      name: "Replay advisory",
    });
    await user.selectOptions(advisorySelect, "036");

    await waitFor(() => {
      expect(
        screen.getByTestId("replay-not-live-banner"),
      ).toHaveTextContent(
        "Replay: Irma (AL112017) advisory 036, issued 2017-09-08 03:00 UTC — not live",
      );
    });

    expect(getSpy).toHaveBeenCalledWith(
      "/api/replay/{atcf_id}/{advisory}",
      expect.objectContaining({
        params: { path: { atcf_id: "AL112017", advisory: "036" } },
      }),
    );

    // Replay disables wind_radii, past_track, peak_surge, radar, and satellite with "(not in this corpus)"
    expect(screen.getAllByText("(not in this corpus)").length).toBe(5);
    expect(
      screen.getByRole("checkbox", { name: /Wind radii/i }),
    ).toBeDisabled();

    // Replay wind probabilities stay enabled and fetch the replay sibling route
    const probCheckbox = screen.getByRole("checkbox", {
      name: /Wind probabilities/i,
    });
    expect(probCheckbox).toBeEnabled();
    await user.click(probCheckbox);
    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith(
        "/api/replay/{atcf_id}/{advisory}/wind-probabilities",
        expect.objectContaining({
          params: {
            path: { atcf_id: "AL112017", advisory: "036" },
            query: { threshold_kt: 34 },
          },
        }),
      );
    });
    expect(
      screen.getByText(/Extract coverage window outlined/i),
    ).toBeInTheDocument();

    // Map layers now hold Irma's 26 watch-warning segments and native (D_Sphere) CRS
    const replayCounts = collectOverlayCategories(map);
    expect(replayCounts.get("watches_warnings")).toBe(
      TYPED_REPLAY_ADVISORY.storms[0]!.watch_warnings.features.length,
    );
    expect(fitBoundsSpy).toHaveBeenCalled();

    // Clicking "Back to live" restores /api/map and removes the "not live" banner
    const backBtn = screen.getByRole("button", { name: /back to live/i });
    await user.click(backBtn);

    expect(screen.queryByTestId("replay-not-live-banner")).toBeNull();
    const liveCounts = collectOverlayCategories(map);
    expect(liveCounts.get("watches_warnings")).toBe(
      TYPED_MAP.storms[0]!.watch_warnings.features.length,
    );
  });

  it("fetches /api/map/depth and /api/map/wind-probabilities only when toggled, shows 'Radar unavailable' on tileerror, and steps stored advisories without moving on background updates", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();

    queryClient.setQueryData(queryKeys.map(), TYPED_MAP);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.health(), {
      ...TYPED_HEALTH,
      corpus: false,
    });
    queryClient.setQueryData(queryKeys.mapAdvisories(), {
      limit: 96,
      steps: [
        {
          snapshot_id: TYPED_MAP.snapshot_id ?? "00000000-0000-4000-8000-000000000001",
          as_of: "2026-10-12T21:01:00Z",
          atcf_id: "AL142026",
          storm_name: "Milton",
          classification: "HU",
          advisory: "16",
          issued_at: "2026-10-12T21:00:00Z",
        },
        {
          snapshot_id: "00000000-0000-4000-8000-000000000099",
          as_of: "2026-10-12T18:00:00Z",
          atcf_id: "AL142026",
          storm_name: "Milton",
          classification: "HU",
          advisory: "15",
          issued_at: "2026-10-12T18:00:00Z",
        },
      ],
      notice: TYPED_MAP.notice,
    } satisfies MapAdvisoriesResponse);

    const pastMapPayload: MapResponse = {
      ...TYPED_MAP,
      snapshot_id: "00000000-0000-4000-8000-000000000099",
      available_layers: [
        "cone",
        "track",
        "points",
        "watches_warnings",
        "outlook",
        "locations",
        "wind_radii",
        "past_track",
        "peak_surge",
        "wind_probabilities",
      ],
    };

    const getSpy = vi.spyOn(apiClient, "GET").mockImplementation((path) => {
      if (path === "/api/map/depth") {
        return Promise.resolve({
          data: SYNTHETIC_DEPTH,
          response: new Response(null, { status: 200 }),
        } as never);
      }
      if (path === "/api/map/wind-probabilities") {
        return Promise.resolve({
          data: SYNTHETIC_PROBABILITIES,
          response: new Response(null, { status: 200 }),
        } as never);
      }
      if (path === "/api/map") {
        return Promise.resolve({
          data: pastMapPayload,
          response: new Response(null, { status: 200 }),
        } as never);
      }
      return Promise.reject(new Error(`Unexpected GET ${String(path)}`));
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <MapView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const map = getLatestLeafletMap()!;
    expect(getSpy).not.toHaveBeenCalled();

    // Toggle Wind Radii on -> fetches /api/map/depth
    const radiiCheckbox = screen.getByRole("checkbox", {
      name: /Wind radii/i,
    });
    await user.click(radiiCheckbox);
    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith(
        "/api/map/depth",
        expect.anything(),
      );
    });
    await waitFor(() => {
      expect(collectOverlayCategories(map).get("wind_radii")).toBe(1);
    });

    // Toggle Wind Speed Probabilities on -> fetches /api/map/wind-probabilities
    const probCheckbox = screen.getByRole("checkbox", {
      name: /Wind probabilities/i,
    });
    await user.click(probCheckbox);
    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith(
        "/api/map/wind-probabilities",
        expect.objectContaining({
          params: { query: { threshold_kt: 34 } },
        }),
      );
    });
    expect(
      screen.getByText("Chance of winds at this speed within 120 hours"),
    ).toBeInTheDocument();

    // Change threshold to 50 kt -> fetches threshold_kt=50
    const thresholdSelect = screen.getByRole("combobox", {
      name: "Wind speed threshold",
    });
    await user.selectOptions(thresholdSelect, "50");
    await waitFor(() => {
      expect(getSpy).toHaveBeenCalledWith(
        "/api/map/wind-probabilities",
        expect.objectContaining({
          params: { query: { threshold_kt: 50 } },
        }),
      );
    });

    // Toggle Radar on -> adds WMS layer; firing tileerror displays "Radar unavailable"
    const radarCheckbox = screen.getByRole("checkbox", {
      name: /Radar \(nowCOAST\)/i,
    });
    await user.click(radarCheckbox);
    expect(screen.getByTestId("nowcoast-age-note")).toBeInTheDocument();

    act(() => {
      map.eachLayer((layer) => {
        if (layer instanceof L.TileLayer.WMS) {
          layer.fire("tileerror");
        }
      });
    });
    expect(screen.getByTestId("radar-unavailable-banner")).toHaveTextContent(
      "Radar unavailable",
    );

    // Step the advisory slider to the past step -> fetches /api/map?snapshot_id=...
    const slider = screen.getByRole("slider");
    fireEvent.keyDown(slider, { key: "ArrowLeft" });

    await waitFor(() => {
      expect(screen.getByTestId("stored-advisory-banner")).toHaveTextContent(
        "Stored advisory: Milton 15, 2026-10-12 18:00 UTC — not the latest",
      );
    });
    expect(screen.getAllByText("(live only)").length).toBe(2);

    // Simulate a newer advisory arriving while viewing the past step
    act(() => {
      queryClient.setQueryData(queryKeys.mapAdvisories(), {
        limit: 96,
        steps: [
          {
            snapshot_id: "00000000-0000-4000-8000-000000000100",
            as_of: "2026-10-13T00:01:00Z",
            atcf_id: "AL142026",
            storm_name: "Milton",
            classification: "HU",
            advisory: "17",
            issued_at: "2026-10-13T00:00:00Z",
          },
          {
            snapshot_id: TYPED_MAP.snapshot_id ?? "00000000-0000-4000-8000-000000000001",
            as_of: "2026-10-12T21:01:00Z",
            atcf_id: "AL142026",
            storm_name: "Milton",
            classification: "HU",
            advisory: "16",
            issued_at: "2026-10-12T21:00:00Z",
          },
          {
            snapshot_id: "00000000-0000-4000-8000-000000000099",
            as_of: "2026-10-12T18:00:00Z",
            atcf_id: "AL142026",
            storm_name: "Milton",
            classification: "HU",
            advisory: "15",
            issued_at: "2026-10-12T18:00:00Z",
          },
        ],
        notice: TYPED_MAP.notice,
      } satisfies MapAdvisoriesResponse);
    });

    await waitFor(() => {
      expect(screen.getByTestId("stored-advisory-banner")).toHaveTextContent(
        "Newer advisory arrived",
      );
    });

    await user.click(screen.getByRole("button", { name: "Back to latest" }));
    expect(screen.queryByTestId("stored-advisory-banner")).toBeNull();
  });

  it("does not re-fit the map on background data updates after the user has moved the map, fits when 'Fit' is clicked, falls back to the Atlantic basin when empty, and renders <b> in names as text", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();

    const untrustedMap: MapResponse = {
      ...TYPED_MAP,
      storms: [
        {
          ...TYPED_MAP.storms[0]!,
          name: "Storm <b>Untrusted</b>",
        },
      ],
    };

    queryClient.setQueryData(queryKeys.map(), untrustedMap);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.health(), {
      ...TYPED_HEALTH,
      corpus: false,
    });
    queryClient.setQueryData(queryKeys.mapAdvisories(), {
      limit: 96,
      steps: [],
      notice: TYPED_MAP.notice,
    } satisfies MapAdvisoriesResponse);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <MapView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const map = getLatestLeafletMap()!;

    // Verify popup/tooltip content for "Storm <b>Untrusted</b>" has no <b> DOM element
    let foundConePopupTitle = "";
    map.eachLayer((layer) => {
      const annotated = layer as AnnotatedLeafletLayer;
      if (annotated.weatherbotMeta?.category === "cone") {
        foundConePopupTitle = annotated.weatherbotMeta.popupTitle;
        const popup = annotated.getPopup();
        const content = popup?.getContent();
        expect(content).toBeInstanceOf(HTMLElement);
        const el = content as HTMLElement;
        expect(el.querySelector("b")).toBeNull();
        expect(el.textContent).toContain("Storm <b>Untrusted</b>");
      }
    });
    expect(foundConePopupTitle).toContain("Storm <b>Untrusted</b>");

    // Simulate user panning the map
    map.fire("dragstart");
    const fitBoundsSpy = vi.spyOn(map, "fitBounds");

    // Background snapshot update via queryClient.setQueryData does not call fitBounds
    act(() => {
      queryClient.setQueryData(queryKeys.map(), {
        ...untrustedMap,
        snapshot_id: "11111111-1111-4111-8111-111111111111",
      });
    });
    expect(fitBoundsSpy).not.toHaveBeenCalled();

    // Clicking the "Fit" button explicitly fits the view
    const fitBtn = screen.getByRole("button", { name: /^fit$/i });
    await user.click(fitBtn);
    expect(fitBoundsSpy).toHaveBeenCalledTimes(1);

    // With nothing to fit, clicking "Fit" centers on DEFAULT_ATLANTIC_CENTER at DEFAULT_ATLANTIC_ZOOM
    const setViewSpy = vi.spyOn(map, "setView");
    act(() => {
      queryClient.setQueryData(queryKeys.map(), {
        ...TYPED_MAP,
        storms: [],
        locations: { type: "FeatureCollection", features: [] },
        location_polygons: { type: "FeatureCollection", features: [] },
      });
    });
    await user.click(fitBtn);
    expect(setViewSpy).toHaveBeenCalledWith(
      DEFAULT_ATLANTIC_CENTER,
      DEFAULT_ATLANTIC_ZOOM,
      expect.objectContaining({ animate: false }),
    );
  });
});
