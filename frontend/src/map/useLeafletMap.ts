// frontend/src/map/useLeafletMap.ts
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import { type RefObject, useCallback, useEffect, useMemo, useRef } from "react";
import {
  type AnnotatedLeafletLayer,
  buildMapLayers,
  type BuiltMapLayers,
  DEFAULT_ATLANTIC_CENTER,
  DEFAULT_ATLANTIC_ZOOM,
  fitMapToPayload,
  isLayerVisible,
  type LayerVisibility,
  MAP_LEGEND_SECTIONS,
  type MapLayerKey,
  type MapResponse,
  OSM_ATTRIBUTION_HTML,
  OSM_MAX_ZOOM,
  OSM_REFERRER_POLICY,
  OSM_TILE_OPTIONS,
  OSM_TILE_URL,
} from "./layers.ts";

export {
  OSM_ATTRIBUTION_HTML,
  OSM_MAX_ZOOM,
  OSM_REFERRER_POLICY,
  OSM_TILE_OPTIONS,
  OSM_TILE_URL,
};

const activeMaps = new Set<L.Map>();
const containerMapRegistry = new WeakMap<HTMLElement, L.Map>();

export function getActiveLeafletMaps(): ReadonlySet<L.Map> {
  return activeMaps;
}

export function getLatestLeafletMap(): L.Map | null {
  let latest: L.Map | null = null;
  for (const map of activeMaps) {
    latest = map;
  }
  return latest;
}

export function getLeafletMapForContainer(
  container: HTMLElement | null | undefined,
): L.Map | null {
  if (!container) {
    return null;
  }
  return containerMapRegistry.get(container) ?? null;
}

export interface UseLeafletMapOptions {
  readonly mapData: MapResponse | null | undefined;
  readonly visibility: LayerVisibility;
  readonly timeZone?: string | null;
  readonly viewModeKey?: string;
}

export interface UseLeafletMapResult {
  readonly containerRef: RefObject<HTMLDivElement | null>;
  readonly builtLayers: BuiltMapLayers | null;
  readonly fitToData: () => void;
}

const ALL_LAYER_KEYS: readonly MapLayerKey[] = MAP_LEGEND_SECTIONS.map(
  (section) => section.category,
);

function getCategoryItems(
  byCategory: BuiltMapLayers["byCategory"],
  key: MapLayerKey,
) {
  switch (key) {
    case "cone":
      return byCategory.cone;
    case "track":
      return byCategory.track;
    case "points":
      return byCategory.points;
    case "watches_warnings":
      return byCategory.watches_warnings;
    case "outlook":
      return byCategory.outlook;
    case "locations":
      return byCategory.locations;
  }
}

function syncLayersOnMap(
  map: L.Map,
  currentLayersRef: { current: AnnotatedLeafletLayer[] },
  builtLayers: BuiltMapLayers | null,
  visibility: LayerVisibility,
): void {
  for (const existing of currentLayersRef.current) {
    if (map.hasLayer(existing)) {
      map.removeLayer(existing);
    }
  }
  currentLayersRef.current = [];

  if (!builtLayers) {
    return;
  }

  for (const key of ALL_LAYER_KEYS) {
    if (!isLayerVisible(visibility, key)) {
      continue;
    }
    const items = getCategoryItems(builtLayers.byCategory, key);
    for (const item of items) {
      item.layer.addTo(map);
      currentLayersRef.current.push(item.layer);
    }
  }
}

export function useLeafletMap({
  mapData,
  visibility,
  timeZone,
  viewModeKey = "live",
}: UseLeafletMapOptions): UseLeafletMapResult {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const overlayLayersRef = useRef<AnnotatedLeafletLayer[]>([]);
  const programmaticMoveRef = useRef(false);
  const userMovedRef = useRef(false);
  const lastFittedModeKeyRef = useRef<string | null>(null);
  const latestMapDataRef = useRef<MapResponse | null | undefined>(mapData);

  const builtLayers = useMemo(() => {
    if (!mapData) {
      return null;
    }
    return buildMapLayers(mapData, { timeZone });
  }, [mapData, timeZone]);

  const latestBuiltRef = useRef<BuiltMapLayers | null>(builtLayers);
  const latestVisibilityRef = useRef<LayerVisibility>(visibility);

  useEffect(() => {
    latestMapDataRef.current = mapData;
    latestBuiltRef.current = builtLayers;
    latestVisibilityRef.current = visibility;
  }, [mapData, builtLayers, visibility]);

  const runProgrammaticFit = useCallback(
    (map: L.Map, payload: MapResponse | null | undefined) => {
      programmaticMoveRef.current = true;
      try {
        if (payload) {
          fitMapToPayload(map, payload);
        } else {
          map.setView(DEFAULT_ATLANTIC_CENTER, DEFAULT_ATLANTIC_ZOOM, {
            animate: false,
          });
        }
      } finally {
        programmaticMoveRef.current = false;
      }
    },
    [],
  );

  // Mount and unmount the single Leaflet map instance (safe under React 19 StrictMode).
  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return undefined;
    }

    const map = L.map(container, {
      center: DEFAULT_ATLANTIC_CENTER,
      zoom: DEFAULT_ATLANTIC_ZOOM,
      zoomControl: true,
      attributionControl: true,
      preferCanvas: false,
    });
    map.attributionControl.setPrefix(false);

    // Tile URL: https://tile.openstreetmap.org/{z}/{x}/{y}.png
    // referrerPolicy: strict-origin-when-cross-origin
    // Attribution: © OpenStreetMap contributors
    const tileLayer = L.tileLayer(OSM_TILE_URL, OSM_TILE_OPTIONS);
    tileLayer.addTo(map);

    const handleInteractionStart = () => {
      if (!programmaticMoveRef.current) {
        userMovedRef.current = true;
      }
    };

    map.on("dragstart", handleInteractionStart);
    map.on("zoomstart", handleInteractionStart);

    mapRef.current = map;
    tileLayerRef.current = tileLayer;
    activeMaps.add(map);
    containerMapRegistry.set(container, map);

    syncLayersOnMap(
      map,
      overlayLayersRef,
      latestBuiltRef.current,
      latestVisibilityRef.current,
    );

    return () => {
      for (const layer of overlayLayersRef.current) {
        if (map.hasLayer(layer)) {
          map.removeLayer(layer);
        }
      }
      overlayLayersRef.current = [];
      map.off("dragstart", handleInteractionStart);
      map.off("zoomstart", handleInteractionStart);
      map.off();
      map.remove();
      activeMaps.delete(map);
      containerMapRegistry.delete(container);
      lastFittedModeKeyRef.current = null;
      if (mapRef.current === map) {
        mapRef.current = null;
      }
      if (tileLayerRef.current === tileLayer) {
        tileLayerRef.current = null;
      }
    };
  }, []);

  // Sync overlay layers whenever the payload or toggle state changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    syncLayersOnMap(map, overlayLayersRef, builtLayers, visibility);
  }, [builtLayers, visibility]);

  // Fit bounds on first load and when switching viewModeKey (replay advisory or back to live),
  // never on background refetches after the user has moved the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapData) {
      return;
    }
    if (lastFittedModeKeyRef.current === viewModeKey) {
      return;
    }
    if (lastFittedModeKeyRef.current === null && userMovedRef.current) {
      lastFittedModeKeyRef.current = viewModeKey;
      return;
    }
    userMovedRef.current = false;
    lastFittedModeKeyRef.current = viewModeKey;
    runProgrammaticFit(map, mapData);
  }, [mapData, viewModeKey, runProgrammaticFit]);

  const fitToData = useCallback(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    userMovedRef.current = false;
    runProgrammaticFit(map, latestMapDataRef.current);
  }, [runProgrammaticFit]);

  return {
    containerRef,
    builtLayers,
    fitToData,
  };
}
