// frontend/src/map/useLeafletMap.ts
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import { type RefObject, useCallback, useEffect, useMemo, useRef } from "react";
import {
  type AnnotatedLeafletLayer,
  buildMapLayers,
  type BuiltMapLayers,
  createPopupElement,
  createTooltipElement,
  DEFAULT_ATLANTIC_CENTER,
  DEFAULT_ATLANTIC_ZOOM,
  extractMultiLineLatLngs,
  extractMultiPolygonLatLngs,
  fitMapToPayload,
  formatCrs,
  type GeoJsonFeatureResponse,
  isLayerVisible,
  type LayerVisibility,
  MAP_LEGEND_SECTIONS,
  type MapDepthResponse,
  type MapLayerKey,
  type MapResponse,
  NOWCOAST_ATTRIBUTION_TEXT,
  NOWCOAST_RADAR_LAYER,
  NOWCOAST_RADAR_WMS_URL,
  NOWCOAST_SATELLITE_LAYER,
  NOWCOAST_SATELLITE_WMS_URL,
  NOWCOAST_WMS_OPACITY,
  OSM_ATTRIBUTION_HTML,
  OSM_MAX_ZOOM,
  OSM_REFERRER_POLICY,
  OSM_TILE_OPTIONS,
  OSM_TILE_URL,
  windProbabilityBandStyle,
  windProbabilityCoverageStyle,
  type WindProbabilityResponse,
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

export interface UseLeafletMapOverlays {
  readonly windProbabilities?: WindProbabilityResponse | null;
  readonly showWindProbabilities?: boolean;
  readonly radar?: boolean;
  readonly satellite?: boolean;
  readonly onOverlayError?: (layer: "radar" | "satellite") => void;
}

export interface UseLeafletMapOptions {
  readonly mapData: MapResponse | null | undefined;
  readonly depthData?: MapDepthResponse | null;
  readonly visibility: LayerVisibility;
  readonly overlays?: UseLeafletMapOverlays;
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
    case "wind_radii":
      return byCategory.wind_radii;
    case "past_track":
      return byCategory.past_track;
    case "peak_surge":
      return byCategory.peak_surge;
    case "wind_probabilities":
      return byCategory.wind_probabilities;
    case "radar":
      return byCategory.radar;
    case "satellite":
      return byCategory.satellite;
    case "locations":
      return byCategory.locations;
  }
}

function createCanvasPolygon(
  feature: GeoJsonFeatureResponse,
  style: L.PathOptions,
  renderer: L.Canvas,
): L.Polygon | null {
  const { type, coordinates } = feature.geometry;
  if (type === "Polygon") {
    const rings = extractMultiLineLatLngs(coordinates);
    if (rings.length === 0) {
      return null;
    }
    return L.polygon(rings, { ...style, renderer });
  }
  if (type === "MultiPolygon") {
    const polys = extractMultiPolygonLatLngs(coordinates);
    if (polys.length === 0) {
      return null;
    }
    return L.polygon(polys, { ...style, renderer });
  }
  return null;
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
  depthData = null,
  visibility,
  overlays,
  timeZone,
  viewModeKey = "live",
}: UseLeafletMapOptions): UseLeafletMapResult {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);
  const overlayLayersRef = useRef<AnnotatedLeafletLayer[]>([]);
  const canvasRendererRef = useRef<L.Canvas | null>(null);
  const probLayersRef = useRef<L.Layer[]>([]);
  const radarLayerRef = useRef<L.TileLayer.WMS | null>(null);
  const satelliteLayerRef = useRef<L.TileLayer.WMS | null>(null);
  const onOverlayErrorRef = useRef(overlays?.onOverlayError);
  const programmaticMoveRef = useRef(false);
  const userMovedRef = useRef(false);
  const lastFittedModeKeyRef = useRef<string | null>(null);
  const latestMapDataRef = useRef<MapResponse | null | undefined>(mapData);

  useEffect(() => {
    onOverlayErrorRef.current = overlays?.onOverlayError;
  }, [overlays?.onOverlayError]);

  const builtLayers = useMemo(() => {
    if (!mapData) {
      return null;
    }
    return buildMapLayers(mapData, { timeZone, depthData });
  }, [mapData, depthData, timeZone]);

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
        map.invalidateSize({ animate: false });
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

    let hadNonZeroSize =
      container.clientWidth > 0 && container.clientHeight > 0;
    const resizeObserver =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => {
            const hasNonZeroSize =
              container.clientWidth > 0 && container.clientHeight > 0;
            if (!hasNonZeroSize) {
              hadNonZeroSize = false;
              return;
            }
            const becameVisible = !hadNonZeroSize;
            hadNonZeroSize = true;
            programmaticMoveRef.current = true;
            try {
              map.invalidateSize({ animate: false });
              if (becameVisible) {
                if (!userMovedRef.current) {
                  if (latestMapDataRef.current) {
                    fitMapToPayload(map, latestMapDataRef.current);
                  } else {
                    map.setView(DEFAULT_ATLANTIC_CENTER, DEFAULT_ATLANTIC_ZOOM, {
                      animate: false,
                    });
                  }
                }
                syncLayersOnMap(
                  map,
                  overlayLayersRef,
                  latestBuiltRef.current,
                  latestVisibilityRef.current,
                );
              }
            } finally {
              programmaticMoveRef.current = false;
            }
          })
        : null;
    resizeObserver?.observe(container);

    return () => {
      resizeObserver?.disconnect();
      for (const layer of overlayLayersRef.current) {
        if (map.hasLayer(layer)) {
          map.removeLayer(layer);
        }
      }
      overlayLayersRef.current = [];
      for (const layer of probLayersRef.current) {
        if (map.hasLayer(layer)) {
          map.removeLayer(layer);
        }
      }
      probLayersRef.current = [];
      if (canvasRendererRef.current && map.hasLayer(canvasRendererRef.current)) {
        map.removeLayer(canvasRendererRef.current);
      }
      canvasRendererRef.current = null;
      if (radarLayerRef.current) {
        radarLayerRef.current.off();
        if (map.hasLayer(radarLayerRef.current)) {
          map.removeLayer(radarLayerRef.current);
        }
        radarLayerRef.current = null;
      }
      if (satelliteLayerRef.current) {
        satelliteLayerRef.current.off();
        if (map.hasLayer(satelliteLayerRef.current)) {
          map.removeLayer(satelliteLayerRef.current);
        }
        satelliteLayerRef.current = null;
      }
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
    map.invalidateSize({ animate: false });
    syncLayersOnMap(map, overlayLayersRef, builtLayers, visibility);
  }, [builtLayers, visibility]);

  // Sync canvas wind probability bands and WMS raster overlays independently.
  const windProbabilities = overlays?.windProbabilities ?? null;
  const showWindProbabilities = overlays?.showWindProbabilities === true;
  const showRadar = overlays?.radar === true;
  const showSatellite = overlays?.satellite === true;

  useEffect(() => {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    for (const existing of probLayersRef.current) {
      if (map.hasLayer(existing)) {
        map.removeLayer(existing);
      }
    }
    probLayersRef.current = [];

    if (showWindProbabilities && windProbabilities) {
      canvasRendererRef.current ??= L.canvas({ padding: 0.5 });
      const renderer = canvasRendererRef.current;
      const crsText = formatCrs(windProbabilities.bands.crs);
      const thresholdKt = windProbabilities.threshold_kt;
      const sortedBands = [...windProbabilities.bands.features].sort((a, b) => {
        const aLower =
          typeof a.properties.lower_pct === "number"
            ? a.properties.lower_pct
            : 0;
        const bLower =
          typeof b.properties.lower_pct === "number"
            ? b.properties.lower_pct
            : 0;
        return aLower - bLower;
      });

      for (const feature of sortedBands) {
        const lowerPct =
          typeof feature.properties.lower_pct === "number"
            ? feature.properties.lower_pct
            : 0;
        const label =
          typeof feature.properties.label === "string" &&
          feature.properties.label.length > 0
            ? feature.properties.label
            : `${String(lowerPct)}%`;
        const style = windProbabilityBandStyle(lowerPct);
        const poly = createCanvasPolygon(feature, style, renderer);
        if (!poly) {
          continue;
        }
        const popupLines: string[] = [
          "Chance of winds at this speed within 120 hours",
          `Band: ${label}`,
          `Threshold: ${String(thresholdKt)} kt`,
        ];
        if (
          typeof feature.properties.geometry_note === "string" &&
          feature.properties.geometry_note.length > 0
        ) {
          popupLines.push(`Geometry: ${feature.properties.geometry_note}`);
        }
        popupLines.push(`CRS: ${crsText}`);
        poly.bindPopup(() =>
          createPopupElement(
            `Wind Speed Probability (${String(thresholdKt)} kt): ${label}`,
            popupLines,
          ),
        );
        poly.addTo(map);
        probLayersRef.current.push(poly);
      }

      if (windProbabilities.coverage) {
        const covFeature = windProbabilities.coverage;
        const covPoly = createCanvasPolygon(
          covFeature,
          windProbabilityCoverageStyle(),
          renderer,
        );
        if (covPoly) {
          const covNote =
            typeof covFeature.properties.note === "string" &&
            covFeature.properties.note.length > 0
              ? covFeature.properties.note
              : "Extract coverage window";
          covPoly.bindPopup(() =>
            createPopupElement("Wind Probability Extract Coverage", [
              covNote,
              `Threshold: ${String(thresholdKt)} kt`,
              `CRS: ${crsText}`,
            ]),
          );
          covPoly.bindTooltip(createTooltipElement(covNote), {
            sticky: true,
            direction: "top",
          });
          covPoly.addTo(map);
          probLayersRef.current.push(covPoly);
        }
      }
    } else if (
      canvasRendererRef.current &&
      map.hasLayer(canvasRendererRef.current)
    ) {
      map.removeLayer(canvasRendererRef.current);
    }

    if (showRadar) {
      if (!radarLayerRef.current) {
        const wms = L.tileLayer.wms(NOWCOAST_RADAR_WMS_URL, {
          layers: NOWCOAST_RADAR_LAYER,
          version: "1.3.0",
          format: "image/png",
          transparent: true,
          opacity: NOWCOAST_WMS_OPACITY,
          attribution: NOWCOAST_ATTRIBUTION_TEXT,
        });
        wms.on("tileerror", () => {
          onOverlayErrorRef.current?.("radar");
        });
        wms.addTo(map);
        radarLayerRef.current = wms;
      }
    } else if (radarLayerRef.current) {
      radarLayerRef.current.off();
      if (map.hasLayer(radarLayerRef.current)) {
        map.removeLayer(radarLayerRef.current);
      }
      radarLayerRef.current = null;
    }

    if (showSatellite) {
      if (!satelliteLayerRef.current) {
        const wms = L.tileLayer.wms(NOWCOAST_SATELLITE_WMS_URL, {
          layers: NOWCOAST_SATELLITE_LAYER,
          version: "1.3.0",
          format: "image/png",
          transparent: true,
          opacity: NOWCOAST_WMS_OPACITY,
          attribution: NOWCOAST_ATTRIBUTION_TEXT,
        });
        wms.on("tileerror", () => {
          onOverlayErrorRef.current?.("satellite");
        });
        wms.addTo(map);
        satelliteLayerRef.current = wms;
      }
    } else if (satelliteLayerRef.current) {
      satelliteLayerRef.current.off();
      if (map.hasLayer(satelliteLayerRef.current)) {
        map.removeLayer(satelliteLayerRef.current);
      }
      satelliteLayerRef.current = null;
    }
  }, [showWindProbabilities, windProbabilities, showRadar, showSatellite]);

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
