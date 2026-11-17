// frontend/src/map/MapView.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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
import {
  type AnnotatedLeafletLayer,
  DEFAULT_ATLANTIC_CENTER,
  DEFAULT_ATLANTIC_ZOOM,
  DEFAULT_ON_LAYER_KEYS,
  LAYER_GROUPS,
  LAYER_TOGGLE_ITEMS,
  MAP_LEGEND_SECTIONS,
  type MapAdvisoriesResponse,
  type MapDepthResponse,
  type MapLayerKey,
  type MapResponse,
  NOWCOAST_RADAR_WMS_URL,
  NOWCOAST_SATELLITE_WMS_URL,
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

function stubMatchMedia(isDesktop: boolean): void {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string): MediaQueryList => ({
      matches: query.includes("min-width: 1024px") ? isDesktop : false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }),
  });
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
    stubMatchMedia(true);
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

    // Visually hidden h1 "Map" is present for route accessibility
    expect(screen.getByRole("heading", { name: "Map", level: 1 })).toHaveClass(
      "sr-only",
    );

    // Visible OpenStreetMap attribution link
    const osmLink = screen.getByRole("link", {
      name: /OpenStreetMap contributors/i,
    });
    expect(osmLink).toHaveAttribute(
      "href",
      "https://www.openstreetmap.org/copyright",
    );

    const defaultOnSet = new Set<MapLayerKey>(DEFAULT_ON_LAYER_KEYS);

    // All 6 default-on categories are present on the map instance; the 6 depth/overlay categories are off
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

  it("opens Layers and Legend panels by default on wide matchMedia and collapses them on narrow matchMedia, groups layer toggles into four headed groups, filters the legend to visible layers only, and links to /replay only when corpus is true", async () => {
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

    // 1. Wide matchMedia (>= 1024px): panels mount open with aria-expanded="true"
    stubMatchMedia(true);
    const { unmount } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <MapView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const layersRegion = screen.getByRole("region", {
      name: "Map layer toggles",
    });
    const legendRegion = screen.getByRole("region", {
      name: "Map legend",
    });

    const layersButton = within(layersRegion).getByRole("button", {
      name: /^Layers$/i,
    });
    const legendButton = within(legendRegion).getByRole("button", {
      name: /^Legend$/i,
    });
    expect(layersButton).toHaveAttribute("aria-expanded", "true");
    expect(legendButton).toHaveAttribute("aria-expanded", "true");

    // Four headed groups inside Layers panel
    for (const group of LAYER_GROUPS) {
      expect(
        within(layersRegion).getByRole("heading", {
          name: group.title,
          level: 3,
        }),
      ).toBeInTheDocument();
    }

    // Legend displays only the 6 default-on visible layers and hides the 6 off-by-default depth layers
    const defaultOnSet = new Set<MapLayerKey>(DEFAULT_ON_LAYER_KEYS);
    for (const section of MAP_LEGEND_SECTIONS) {
      if (defaultOnSet.has(section.category)) {
        expect(
          within(legendRegion).getByRole("heading", { name: section.title }),
        ).toBeInTheDocument();
      } else {
        expect(
          within(legendRegion).queryByRole("heading", { name: section.title }),
        ).toBeNull();
      }
    }

    // Unchecking "Storm cones" removes its legend section immediately
    await user.click(
      within(layersRegion).getByRole("checkbox", { name: "Storm cones" }),
    );
    expect(
      within(legendRegion).queryByRole("heading", { name: "Storm cones" }),
    ).toBeNull();

    // Collapsing Layers and Legend via their buttons sets aria-expanded="false"
    await user.click(layersButton);
    expect(layersButton).toHaveAttribute("aria-expanded", "false");
    expect(
      within(layersRegion).queryByRole("checkbox", { name: "Forecast tracks" }),
    ).toBeNull();

    await user.click(legendButton);
    expect(legendButton).toHaveAttribute("aria-expanded", "false");
    expect(
      within(legendRegion).queryByRole("heading", { name: "Forecast tracks" }),
    ).toBeNull();

    // No replay link when corpus is false
    expect(
      screen.queryByRole("link", { name: "Replay a past storm" }),
    ).toBeNull();

    unmount();

    // 2. Narrow matchMedia (< 1024px) with corpus: true: panels mount collapsed and status chip links to /replay
    stubMatchMedia(false);
    queryClient.setQueryData(queryKeys.health(), {
      ...TYPED_HEALTH,
      corpus: true,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <MapView />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const narrowLayersBtn = screen.getByRole("button", { name: /^Layers$/i });
    const narrowLegendBtn = screen.getByRole("button", { name: /^Legend$/i });
    expect(narrowLayersBtn).toHaveAttribute("aria-expanded", "false");
    expect(narrowLegendBtn).toHaveAttribute("aria-expanded", "false");

    const replayLink = screen.getByRole("link", {
      name: "Replay a past storm",
    });
    expect(replayLink).toHaveAttribute("href", "/replay");

    // Opening Layers on narrow viewport reveals the checkboxes
    await user.click(narrowLayersBtn);
    expect(narrowLayersBtn).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("checkbox", { name: "Storm cones" }),
    ).toBeInTheDocument();
  });

  it("fetches /api/map/depth and /api/map/wind-probabilities only when toggled, shows radar and satellite unavailable banners in the Legend panel on tileerror, and steps stored advisories without moving on background updates", async () => {
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
          snapshot_id:
            TYPED_MAP.snapshot_id ?? "00000000-0000-4000-8000-000000000001",
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
    const legendRegion = screen.getByRole("region", { name: "Map legend" });
    expect(getSpy).not.toHaveBeenCalled();

    // Toggle Wind Radii on -> fetches /api/map/depth and adds its section to Map legend
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
    expect(
      within(legendRegion).getByRole("heading", {
        name: "Forecast & advisory wind radii",
      }),
    ).toBeInTheDocument();

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
    expect(
      await screen.findByText(/Extract coverage window outlined/i),
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

    // Toggle Radar and Satellite on -> adds WMS layers; firing tileerror displays both unavailable banners in Legend
    const radarCheckbox = screen.getByRole("checkbox", {
      name: /Radar \(nowCOAST\)/i,
    });
    const satelliteCheckbox = screen.getByRole("checkbox", {
      name: /Satellite IR \(nowCOAST\)/i,
    });
    await user.click(radarCheckbox);
    await user.click(satelliteCheckbox);
    expect(
      within(legendRegion).getByTestId("nowcoast-age-note"),
    ).toBeInTheDocument();

    act(() => {
      map.eachLayer((layer) => {
        if (layer instanceof L.TileLayer.WMS) {
          const wmsUrl = (layer as L.TileLayer.WMS & { _url?: string })._url;
          if (
            wmsUrl === NOWCOAST_RADAR_WMS_URL ||
            wmsUrl === NOWCOAST_SATELLITE_WMS_URL
          ) {
            layer.fire("tileerror");
          }
        }
      });
    });
    expect(
      within(legendRegion).getByTestId("radar-unavailable-banner"),
    ).toHaveTextContent("Radar unavailable");
    expect(
      within(legendRegion).getByTestId("satellite-unavailable-banner"),
    ).toHaveTextContent("Satellite unavailable");

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
            snapshot_id:
              TYPED_MAP.snapshot_id ?? "00000000-0000-4000-8000-000000000001",
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
