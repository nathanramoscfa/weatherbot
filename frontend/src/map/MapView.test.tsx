// frontend/src/map/MapView.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as L from "leaflet";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
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
  LAYER_TOGGLE_ITEMS,
  type MapLayerKey,
  type MapResponse,
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
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mounts inside React.StrictMode leaving one map, draws cone, track, point, segment, outlook, and location layers, and toggles each layer on and off via map.eachLayer", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();

    queryClient.setQueryData(queryKeys.map(), TYPED_MAP);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.health(), {
      ...TYPED_HEALTH,
      corpus: false,
    });

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

    // All 6 categories are present on the map instance
    const initialCounts = collectOverlayCategories(map!);
    for (const item of LAYER_TOGGLE_ITEMS) {
      expect(initialCounts.get(item.key) ?? 0).toBeGreaterThan(0);
    }

    // Toggling each checkbox removes and re-adds its category's layers
    for (const item of LAYER_TOGGLE_ITEMS) {
      const checkbox = screen.getByRole("checkbox", { name: item.label });
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

  it("shows the replay panel when corpus is true, loads Irma advisory 036 with the 'not live' banner, fits the view, and returns to live on 'Back to live'", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();

    queryClient.setQueryData(queryKeys.map(), TYPED_MAP);
    queryClient.setQueryData(queryKeys.locations(), TYPED_LOCATIONS);
    queryClient.setQueryData(queryKeys.health(), {
      ...TYPED_HEALTH,
      corpus: true,
    });
    queryClient.setQueryData(queryKeys.replay(), TYPED_REPLAY);

    const getSpy = vi.spyOn(apiClient, "GET").mockImplementation((path) => {
      if (path === "/api/replay/{atcf_id}/{advisory}") {
        return Promise.resolve({
          data: TYPED_REPLAY_ADVISORY,
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
