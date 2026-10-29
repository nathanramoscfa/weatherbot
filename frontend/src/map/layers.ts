// frontend/src/map/layers.ts
import * as L from "leaflet";
import type { components } from "../api/schema.ts";
import { formatBothTimes, formatUtc } from "../pages/format.ts";

export type MapResponse = components["schemas"]["MapResponse"];
export type StormMapLayersResponse =
  components["schemas"]["StormMapLayersResponse"];
export type GeoJsonFeatureResponse =
  components["schemas"]["GeoJsonFeatureResponse"];
export type GeoJsonFeatureCollectionResponse =
  components["schemas"]["GeoJsonFeatureCollectionResponse"];
export type GeoJsonCrsResponse = components["schemas"]["GeoJsonCrsResponse"];

export const OSM_TILE_URL =
  "https://tile.openstreetmap.org/{z}/{x}/{y}.png" as const;
export const OSM_REFERRER_POLICY = "strict-origin-when-cross-origin" as const;
export const OSM_COPYRIGHT_URL =
  "https://www.openstreetmap.org/copyright" as const;
export const OSM_ATTRIBUTION_TEXT = "© OpenStreetMap contributors" as const;
export const OSM_ATTRIBUTION_HTML =
  '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>' as const;
export const OSM_MAX_ZOOM = 19;

export interface OsmTileLayerOptions extends L.TileLayerOptions {
  readonly referrerPolicy: typeof OSM_REFERRER_POLICY;
}

export const OSM_TILE_OPTIONS: OsmTileLayerOptions = {
  maxZoom: OSM_MAX_ZOOM,
  referrerPolicy: OSM_REFERRER_POLICY,
  attribution: OSM_ATTRIBUTION_HTML,
};

// Whole-number Atlantic basin fallback centre and zoom (never 3+ decimals).
export const DEFAULT_ATLANTIC_CENTER: L.LatLngTuple = [25, -65];
export const DEFAULT_ATLANTIC_ZOOM = 4;

export type MapLayerKey =
  | "cone"
  | "track"
  | "points"
  | "watches_warnings"
  | "outlook"
  | "locations";

export type LayerVisibility = Readonly<Record<MapLayerKey, boolean>>;

export interface LayerToggleItem {
  readonly key: MapLayerKey;
  readonly label: string;
}

export const LAYER_TOGGLE_ITEMS: readonly LayerToggleItem[] = [
  { key: "cone", label: "Storm cones" },
  { key: "track", label: "Forecast tracks" },
  { key: "points", label: "Forecast points" },
  { key: "watches_warnings", label: "Watches & warnings" },
  { key: "outlook", label: "Outlook areas" },
  { key: "locations", label: "Locations" },
] as const;

export const DEFAULT_LAYER_VISIBILITY: LayerVisibility = {
  cone: true,
  track: true,
  points: true,
  watches_warnings: true,
  outlook: true,
  locations: true,
};

export function isLayerVisible(
  visibility: LayerVisibility,
  key: MapLayerKey,
): boolean {
  switch (key) {
    case "cone":
      return visibility.cone;
    case "track":
      return visibility.track;
    case "points":
      return visibility.points;
    case "watches_warnings":
      return visibility.watches_warnings;
    case "outlook":
      return visibility.outlook;
    case "locations":
      return visibility.locations;
  }
}

export interface LegendSwatch {
  readonly label: string;
  readonly color: string;
  readonly fillColor?: string;
  readonly shape: "polygon" | "line" | "circle";
  readonly swatchClass: string;
}

export interface LegendSection {
  readonly category: MapLayerKey;
  readonly title: string;
  readonly items: readonly LegendSwatch[];
}

export const NHC_WATCH_WARNING_COLORS = {
  HWR: "#dc2626", // Hurricane Warning — red
  HWA: "#ec4899", // Hurricane Watch — pink
  TWR: "#2563eb", // Tropical Storm Warning — blue
  TWA: "#eab308", // Tropical Storm Watch — yellow
} as const;

export const OUTLOOK_RISK_COLORS = {
  Low: { color: "#ca8a04", fillColor: "#facc15" }, // yellow (<40%)
  Medium: { color: "#ea580c", fillColor: "#fb923c" }, // orange (40-60%)
  High: { color: "#dc2626", fillColor: "#f87171" }, // red (>60%)
} as const;

export const MAP_LEGEND_SECTIONS: readonly LegendSection[] = [
  {
    category: "cone",
    title: "Storm cones",
    items: [
      {
        label: "NHC forecast cone (outline & fill)",
        color: "#1d4ed8",
        fillColor: "#93c5fd",
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border-2 border-blue-700 bg-blue-300/60",
      },
    ],
  },
  {
    category: "track",
    title: "Forecast tracks",
    items: [
      {
        label: "Forecast center track line",
        color: "#0f172a",
        shape: "line",
        swatchClass: "h-1 w-4 rounded-xs bg-slate-900 dark:bg-slate-200",
      },
    ],
  },
  {
    category: "points",
    title: "Forecast points",
    items: [
      {
        label: "Major Hurricane (Category 3–5)",
        color: "#7f1d1d",
        fillColor: "#dc2626",
        shape: "circle",
        swatchClass: "h-3 w-3 rounded-full border-2 border-red-900 bg-red-600",
      },
      {
        label: "Hurricane (Category 1–2)",
        color: "#b91c1c",
        fillColor: "#ef4444",
        shape: "circle",
        swatchClass: "h-3 w-3 rounded-full border-2 border-red-700 bg-red-500",
      },
      {
        label: "Tropical / Subtropical Storm",
        color: "#c2410c",
        fillColor: "#f97316",
        shape: "circle",
        swatchClass:
          "h-3 w-3 rounded-full border-2 border-orange-700 bg-orange-500",
      },
      {
        label: "Depression / Disturbance / Low",
        color: "#0369a1",
        fillColor: "#38bdf8",
        shape: "circle",
        swatchClass: "h-3 w-3 rounded-full border-2 border-sky-700 bg-sky-400",
      },
    ],
  },
  {
    category: "watches_warnings",
    title: "Watches & warnings (NHC)",
    items: [
      {
        label: "Hurricane Warning (HWR)",
        color: NHC_WATCH_WARNING_COLORS.HWR,
        shape: "line",
        swatchClass: "h-1 w-4 rounded-xs bg-red-600",
      },
      {
        label: "Hurricane Watch (HWA)",
        color: NHC_WATCH_WARNING_COLORS.HWA,
        shape: "line",
        swatchClass: "h-1 w-4 rounded-xs bg-pink-500",
      },
      {
        label: "Tropical Storm Warning (TWR)",
        color: NHC_WATCH_WARNING_COLORS.TWR,
        shape: "line",
        swatchClass: "h-1 w-4 rounded-xs bg-blue-600",
      },
      {
        label: "Tropical Storm Watch (TWA)",
        color: NHC_WATCH_WARNING_COLORS.TWA,
        shape: "line",
        swatchClass: "h-1 w-4 rounded-xs bg-yellow-500",
      },
    ],
  },
  {
    category: "outlook",
    title: "Tropical Weather Outlook",
    items: [
      {
        label: "High formation chance (>60%)",
        color: OUTLOOK_RISK_COLORS.High.color,
        fillColor: OUTLOOK_RISK_COLORS.High.fillColor,
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border-2 border-red-600 bg-red-400/50",
      },
      {
        label: "Medium formation chance (40–60%)",
        color: OUTLOOK_RISK_COLORS.Medium.color,
        fillColor: OUTLOOK_RISK_COLORS.Medium.fillColor,
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border-2 border-orange-600 bg-orange-400/50",
      },
      {
        label: "Low formation chance (<40%)",
        color: OUTLOOK_RISK_COLORS.Low.color,
        fillColor: OUTLOOK_RISK_COLORS.Low.fillColor,
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border-2 border-yellow-600 bg-yellow-400/50",
      },
    ],
  },
  {
    category: "locations",
    title: "Watched locations",
    items: [
      {
        label: "Watched location point",
        color: "#065f46",
        fillColor: "#10b981",
        shape: "circle",
        swatchClass:
          "h-3 w-3 rounded-full border-2 border-emerald-800 bg-emerald-500",
      },
      {
        label: "Stored NWS zone polygon",
        color: "#065f46",
        fillColor: "#10b981",
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border-2 border-dashed border-emerald-800 bg-emerald-500/30",
      },
    ],
  },
] as const;

export function formatCrs(crs: GeoJsonCrsResponse): string {
  if (crs.datum && crs.datum.trim() !== "") {
    return `${crs.name} (${crs.datum})`;
  }
  return crs.name;
}

export function coneStyle(): L.PathOptions {
  return {
    color: "#1d4ed8",
    weight: 2,
    opacity: 0.85,
    fillColor: "#93c5fd",
    fillOpacity: 0.25,
  };
}

export function trackStyle(): L.PathOptions {
  return {
    color: "#0f172a",
    weight: 2.5,
    opacity: 0.9,
    dashArray: "6 4",
  };
}

export interface ForecastPointStyleResult extends L.CircleMarkerOptions {
  readonly classificationLabel: string;
}

export function forecastPointStyle(
  props: Readonly<Record<string, unknown>>,
): ForecastPointStyleResult {
  const category =
    typeof props.saffir_simpson === "number" ? props.saffir_simpson : null;
  const development =
    typeof props.development === "string" ? props.development : null;
  const stormType =
    typeof props.storm_type === "string" ? props.storm_type : null;
  const label = typeof props.label === "string" ? props.label : null;

  const classificationLabel =
    label ??
    (development && category !== null
      ? `${development} (Category ${String(category)})`
      : development ?? stormType ?? "Cyclone");

  if (
    (category !== null && category >= 3) ||
    development === "Major Hurricane" ||
    stormType === "MH"
  ) {
    return {
      color: "#7f1d1d",
      fillColor: "#dc2626",
      fillOpacity: 0.9,
      weight: 2,
      radius: 7,
      classificationLabel,
    };
  }
  if (
    (category !== null && category >= 1) ||
    development === "Hurricane" ||
    stormType === "HU"
  ) {
    return {
      color: "#b91c1c",
      fillColor: "#ef4444",
      fillOpacity: 0.9,
      weight: 2,
      radius: 6,
      classificationLabel,
    };
  }
  if (
    development === "Tropical Storm" ||
    development === "Subtropical Storm" ||
    stormType === "TS" ||
    stormType === "SS"
  ) {
    return {
      color: "#c2410c",
      fillColor: "#f97316",
      fillOpacity: 0.9,
      weight: 2,
      radius: 5,
      classificationLabel,
    };
  }
  return {
    color: "#0369a1",
    fillColor: "#38bdf8",
    fillOpacity: 0.9,
    weight: 2,
    radius: 5,
    classificationLabel,
  };
}

export function watchWarningColor(code: string): string {
  switch (code) {
    case "HWR":
      return NHC_WATCH_WARNING_COLORS.HWR;
    case "HWA":
      return NHC_WATCH_WARNING_COLORS.HWA;
    case "TWR":
    case "TRW":
      return NHC_WATCH_WARNING_COLORS.TWR;
    case "TWA":
    case "TRA":
      return NHC_WATCH_WARNING_COLORS.TWA;
    default:
      return NHC_WATCH_WARNING_COLORS.TWR;
  }
}

export function watchWarningLabel(code: string): string {
  switch (code) {
    case "HWR":
      return "Hurricane Warning (HWR)";
    case "HWA":
      return "Hurricane Watch (HWA)";
    case "TWR":
    case "TRW":
      return "Tropical Storm Warning (TWR)";
    case "TWA":
    case "TRA":
      return "Tropical Storm Watch (TWA)";
    default:
      return code;
  }
}

export function watchWarningStyle(code: string): L.PathOptions {
  const color = watchWarningColor(code);
  return {
    color,
    fillColor: color,
    weight: 5,
    opacity: 0.95,
    fillOpacity: 0.9,
  };
}

export type OutlookRiskCategory = "Low" | "Medium" | "High";

export function classifyOutlookRisk(
  risk7day: string | null,
  risk2day: string | null,
  chance7dayPct: number | null,
  chance2dayPct: number | null,
): OutlookRiskCategory {
  const risk = risk7day ?? risk2day;
  if (risk === "High") {
    return "High";
  }
  if (risk === "Medium") {
    return "Medium";
  }
  if (risk === "Low") {
    return "Low";
  }
  const pct = chance7dayPct ?? chance2dayPct ?? 0;
  if (pct > 60) {
    return "High";
  }
  if (pct >= 40) {
    return "Medium";
  }
  return "Low";
}

export function outlookStyle(
  props: Readonly<Record<string, unknown>>,
): L.PathOptions & { readonly riskCategory: OutlookRiskCategory } {
  const risk7day =
    typeof props.risk_7day === "string" ? props.risk_7day : null;
  const risk2day =
    typeof props.risk_2day === "string" ? props.risk_2day : null;
  const chance7day =
    typeof props.chance_7day_pct === "number" ? props.chance_7day_pct : null;
  const chance2day =
    typeof props.chance_2day_pct === "number" ? props.chance_2day_pct : null;

  const riskCategory = classifyOutlookRisk(
    risk7day,
    risk2day,
    chance7day,
    chance2day,
  );
  const palette =
    riskCategory === "High"
      ? OUTLOOK_RISK_COLORS.High
      : riskCategory === "Medium"
        ? OUTLOOK_RISK_COLORS.Medium
        : OUTLOOK_RISK_COLORS.Low;

  return {
    color: palette.color,
    fillColor: palette.fillColor,
    weight: 2,
    opacity: 0.9,
    fillOpacity: 0.25,
    riskCategory,
  };
}

export function locationLevelColors(level: number | null): {
  readonly color: string;
  readonly fillColor: string;
} {
  switch (level) {
    case 5:
      return { color: "#7f1d1d", fillColor: "#dc2626" };
    case 4:
      return { color: "#9a3412", fillColor: "#ea580c" };
    case 3:
      return { color: "#854d0e", fillColor: "#eab308" };
    case 2:
      return { color: "#075985", fillColor: "#0ea5e9" };
    case 1:
      return { color: "#065f46", fillColor: "#10b981" };
    default:
      return { color: "#334155", fillColor: "#64748b" };
  }
}

// Coordinate conversion: GeoJSON [lon, lat] -> Leaflet [lat, lon] with no
// transformation, wrapping, or rounding.
export function toLatLngTuple(position: unknown): L.LatLngTuple | null {
  if (!Array.isArray(position) || position.length < 2) {
    return null;
  }
  const lon: unknown = position[0];
  const lat: unknown = position[1];
  if (
    typeof lon !== "number" ||
    typeof lat !== "number" ||
    !Number.isFinite(lon) ||
    !Number.isFinite(lat)
  ) {
    return null;
  }
  return [lat, lon];
}

export function extractLineLatLngs(coords: unknown): L.LatLngTuple[] {
  if (!Array.isArray(coords)) {
    return [];
  }
  const out: L.LatLngTuple[] = [];
  for (const pos of coords) {
    const tuple = toLatLngTuple(pos);
    if (tuple !== null) {
      out.push(tuple);
    }
  }
  return out;
}

export function extractMultiLineLatLngs(coords: unknown): L.LatLngTuple[][] {
  if (!Array.isArray(coords)) {
    return [];
  }
  const out: L.LatLngTuple[][] = [];
  for (const line of coords) {
    const ring = extractLineLatLngs(line);
    if (ring.length > 0) {
      out.push(ring);
    }
  }
  return out;
}

export function extractMultiPolygonLatLngs(
  coords: unknown,
): L.LatLngTuple[][][] {
  if (!Array.isArray(coords)) {
    return [];
  }
  const out: L.LatLngTuple[][][] = [];
  for (const poly of coords) {
    const rings = extractMultiLineLatLngs(poly);
    if (rings.length > 0) {
      out.push(rings);
    }
  }
  return out;
}

export function collectFeatureLatLngs(
  feature: GeoJsonFeatureResponse,
): L.LatLngTuple[] {
  const { type, coordinates } = feature.geometry;
  switch (type) {
    case "Point": {
      const pt = toLatLngTuple(coordinates);
      return pt !== null ? [pt] : [];
    }
    case "MultiPoint":
    case "LineString":
      return extractLineLatLngs(coordinates);
    case "MultiLineString":
    case "Polygon":
      return extractMultiLineLatLngs(coordinates).flat();
    case "MultiPolygon":
      return extractMultiPolygonLatLngs(coordinates).flat(2);
  }
}

export function createPopupElement(
  title: string,
  lines: readonly string[],
): HTMLElement {
  const container = document.createElement("div");
  container.className = "space-y-1 text-xs";

  const heading = document.createElement("p");
  heading.className = "font-bold";
  heading.textContent = title;
  container.appendChild(heading);

  for (const line of lines) {
    const row = document.createElement("p");
    row.textContent = line;
    container.appendChild(row);
  }
  return container;
}

export function createTooltipElement(text: string): HTMLElement {
  const span = document.createElement("span");
  span.textContent = text;
  return span;
}

export interface WeatherbotLayerMetadata {
  readonly id: string;
  readonly category: MapLayerKey;
  readonly crsText: string;
  readonly popupTitle: string;
  readonly popupLines: readonly string[];
  readonly tooltipText: string | null;
}

export type AnnotatedLeafletLayer = L.Layer & {
  weatherbotMeta?: WeatherbotLayerMetadata;
};

export interface MapLayerItem extends WeatherbotLayerMetadata {
  readonly layer: AnnotatedLeafletLayer;
  readonly latLngs: readonly L.LatLngTuple[];
  readonly style: L.PathOptions;
}

export interface BuiltMapLayers {
  readonly items: readonly MapLayerItem[];
  readonly byCategory: Readonly<Record<MapLayerKey, readonly MapLayerItem[]>>;
  readonly bounds: L.LatLngBounds | null;
}

export interface BuildMapLayersOptions {
  readonly timeZone?: string | null;
}

function attachPopupAndTooltip(
  layer: AnnotatedLeafletLayer,
  meta: WeatherbotLayerMetadata,
): AnnotatedLeafletLayer {
  layer.weatherbotMeta = meta;
  layer.bindPopup(createPopupElement(meta.popupTitle, meta.popupLines));
  if (meta.tooltipText !== null) {
    layer.bindTooltip(createTooltipElement(meta.tooltipText));
  }
  return layer;
}

function createGeometryLayer(
  feature: GeoJsonFeatureResponse,
  style: L.PathOptions,
  circleRadius = 6,
): AnnotatedLeafletLayer | null {
  const { type, coordinates } = feature.geometry;
  switch (type) {
    case "Point": {
      const pt = toLatLngTuple(coordinates);
      if (pt === null) {
        return null;
      }
      return L.circleMarker(pt, {
        ...style,
        radius: circleRadius,
      });
    }
    case "MultiPoint": {
      const pts = extractLineLatLngs(coordinates);
      if (pts.length === 0) {
        return null;
      }
      if (pts.length === 1 && pts[0]) {
        return L.circleMarker(pts[0], {
          ...style,
          radius: circleRadius,
        });
      }
      return L.featureGroup(
        pts.map((pt) =>
          L.circleMarker(pt, {
            ...style,
            radius: circleRadius,
          }),
        ),
      );
    }
    case "LineString": {
      const pts = extractLineLatLngs(coordinates);
      if (pts.length === 0) {
        return null;
      }
      return L.polyline(pts, style);
    }
    case "MultiLineString": {
      const lines = extractMultiLineLatLngs(coordinates);
      if (lines.length === 0) {
        return null;
      }
      return L.polyline(lines, style);
    }
    case "Polygon": {
      const rings = extractMultiLineLatLngs(coordinates);
      if (rings.length === 0) {
        return null;
      }
      return L.polygon(rings, style);
    }
    case "MultiPolygon": {
      const polys = extractMultiPolygonLatLngs(coordinates);
      if (polys.length === 0) {
        return null;
      }
      return L.polygon(polys, style);
    }
  }
}

function stringProp(
  props: Readonly<Record<string, unknown>>,
  key: string,
): string | null {
  for (const [k, v] of Object.entries(props)) {
    if (k === key && typeof v === "string") {
      return v;
    }
  }
  return null;
}

function numberProp(
  props: Readonly<Record<string, unknown>>,
  key: string,
): number | null {
  for (const [k, v] of Object.entries(props)) {
    if (k === key && typeof v === "number" && Number.isFinite(v)) {
      return v;
    }
  }
  return null;
}

function booleanProp(
  props: Readonly<Record<string, unknown>>,
  key: string,
): boolean | null {
  for (const [k, v] of Object.entries(props)) {
    if (k === key && typeof v === "boolean") {
      return v;
    }
  }
  return null;
}

function stringArrayProp(
  props: Readonly<Record<string, unknown>>,
  key: string,
): string[] {
  for (const [k, v] of Object.entries(props)) {
    if (k === key && Array.isArray(v)) {
      return v.filter((item): item is string => typeof item === "string");
    }
  }
  return [];
}

export function computeMapBounds(mapData: MapResponse): L.LatLngBounds | null {
  const coords: L.LatLngTuple[] = [];
  for (const storm of mapData.storms) {
    if (storm.cone) {
      coords.push(...collectFeatureLatLngs(storm.cone));
    }
    if (storm.track) {
      coords.push(...collectFeatureLatLngs(storm.track));
    }
    for (const pt of storm.forecast_points.features) {
      coords.push(...collectFeatureLatLngs(pt));
    }
    for (const seg of storm.watch_warnings.features) {
      coords.push(...collectFeatureLatLngs(seg));
    }
  }
  for (const loc of mapData.locations.features) {
    coords.push(...collectFeatureLatLngs(loc));
  }
  for (const poly of mapData.location_polygons.features) {
    coords.push(...collectFeatureLatLngs(poly));
  }
  if (coords.length === 0) {
    return null;
  }
  return L.latLngBounds(coords);
}

export function fitMapToPayload(map: L.Map, mapData: MapResponse): void {
  const bounds = computeMapBounds(mapData);
  if (bounds && bounds.isValid()) {
    map.fitBounds(bounds, {
      animate: false,
      padding: [24, 24],
      maxZoom: 8,
    });
    return;
  }
  map.setView(DEFAULT_ATLANTIC_CENTER, DEFAULT_ATLANTIC_ZOOM, {
    animate: false,
  });
}

export function buildMapLayers(
  mapData: MapResponse,
  options?: BuildMapLayersOptions,
): BuiltMapLayers {
  const effectiveTimeZone = options?.timeZone ?? "America/New_York";
  const coneItems: MapLayerItem[] = [];
  const trackItems: MapLayerItem[] = [];
  const pointItems: MapLayerItem[] = [];
  const wwItems: MapLayerItem[] = [];
  const outlookItems: MapLayerItem[] = [];
  const locationItems: MapLayerItem[] = [];

  for (const storm of mapData.storms) {
    const stormLabel = `${storm.name} (${storm.atcf_id})`;

    if (storm.cone) {
      const style = coneStyle();
      const layer = createGeometryLayer(storm.cone, style);
      if (layer) {
        const crsText = formatCrs(storm.cone.crs);
        const periodH = numberProp(storm.cone.properties, "forecast_period_h");
        const issuedAt =
          stringProp(storm.cone.properties, "issued_at") ?? storm.issued_at;
        const popupTitle = `${stormLabel} — Forecast cone`;
        const popupLines = [
          `Advisory: ${storm.advisory ?? "—"}`,
          ...(periodH !== null ? [`Forecast period: ${String(periodH)} h`] : []),
          ...(issuedAt
            ? [`Issued: ${formatBothTimes(issuedAt, effectiveTimeZone)}`]
            : []),
          `CRS: ${crsText}`,
        ];
        const meta: WeatherbotLayerMetadata = {
          id: `cone-${storm.atcf_id}`,
          category: "cone",
          crsText,
          popupTitle,
          popupLines,
          tooltipText: null,
        };
        attachPopupAndTooltip(layer, meta);
        coneItems.push({
          ...meta,
          layer,
          latLngs: collectFeatureLatLngs(storm.cone),
          style,
        });
      }
    }

    if (storm.track) {
      const style = trackStyle();
      const layer = createGeometryLayer(storm.track, style);
      if (layer) {
        const crsText = formatCrs(storm.track.crs);
        const issuedAt =
          stringProp(storm.track.properties, "issued_at") ?? storm.issued_at;
        const popupTitle = `${stormLabel} — Forecast track`;
        const popupLines = [
          `Advisory: ${storm.advisory ?? "—"}`,
          ...(issuedAt
            ? [`Issued: ${formatBothTimes(issuedAt, effectiveTimeZone)}`]
            : []),
          `CRS: ${crsText}`,
        ];
        const meta: WeatherbotLayerMetadata = {
          id: `track-${storm.atcf_id}`,
          category: "track",
          crsText,
          popupTitle,
          popupLines,
          tooltipText: null,
        };
        attachPopupAndTooltip(layer, meta);
        trackItems.push({
          ...meta,
          layer,
          latLngs: collectFeatureLatLngs(storm.track),
          style,
        });
      }
    }

    storm.forecast_points.features.forEach((ptFeature, idx) => {
      const ptStyle = forecastPointStyle(ptFeature.properties);
      const radius = ptStyle.radius ?? 5;
      const layer = createGeometryLayer(ptFeature, ptStyle, radius);
      if (!layer) {
        return;
      }
      const crsText = formatCrs(ptFeature.crs);
      const validAt = stringProp(ptFeature.properties, "valid_at");
      const validLocalText = stringProp(
        ptFeature.properties,
        "valid_local_text",
      );
      const maxWindKt = numberProp(ptFeature.properties, "max_wind_kt");
      const gustKt = numberProp(ptFeature.properties, "gust_kt");
      const mslpMb = numberProp(ptFeature.properties, "mslp_mb");
      const tauH = numberProp(ptFeature.properties, "tau_h");
      const advisory =
        stringProp(ptFeature.properties, "advisory") ?? storm.advisory;

      const timeDisplay = validAt
        ? formatBothTimes(validAt, effectiveTimeZone)
        : validLocalText ?? "—";
      const intensityDisplay =
        maxWindKt !== null
          ? `${ptStyle.classificationLabel}, ${String(maxWindKt)} kt`
          : ptStyle.classificationLabel;

      const tooltipText = `${stormLabel} · ${timeDisplay}${
        validLocalText ? ` (${validLocalText})` : ""
      } · ${intensityDisplay}`;

      const popupTitle = `${stormLabel} — Forecast point`;
      const popupLines = [
        `Valid: ${timeDisplay}${
          validLocalText ? ` · NHC local: ${validLocalText}` : ""
        }`,
        `Intensity: ${intensityDisplay}${
          gustKt !== null ? ` (gusts ${String(gustKt)} kt)` : ""
        }${mslpMb !== null ? ` · ${String(mslpMb)} mb` : ""}`,
        `Advisory: ${advisory ?? "—"}${
          tauH !== null ? ` (+${String(tauH)} h)` : ""
        }`,
        `CRS: ${crsText}`,
      ];
      const meta: WeatherbotLayerMetadata = {
        id: `point-${storm.atcf_id}-${String(idx)}`,
        category: "points",
        crsText,
        popupTitle,
        popupLines,
        tooltipText,
      };
      attachPopupAndTooltip(layer, meta);
      pointItems.push({
        ...meta,
        layer,
        latLngs: collectFeatureLatLngs(ptFeature),
        style: ptStyle,
      });
    });

    storm.watch_warnings.features.forEach((segFeature, idx) => {
      const code =
        stringProp(segFeature.properties, "code") ??
        stringProp(segFeature.properties, "tcww") ??
        "TWR";
      const style = watchWarningStyle(code);
      const layer = createGeometryLayer(segFeature, style, 6);
      if (!layer) {
        return;
      }
      const crsText = formatCrs(segFeature.crs);
      const breakpoints = stringArrayProp(segFeature.properties, "breakpoints");
      const geometryNote = stringProp(segFeature.properties, "geometry_note");
      const issuedAt =
        stringProp(segFeature.properties, "issued_at") ?? storm.issued_at;
      const advisory =
        stringProp(segFeature.properties, "advisory") ?? storm.advisory;

      const popupTitle = `${stormLabel} — ${watchWarningLabel(code)}`;
      const popupLines = [
        `Breakpoints: ${
          breakpoints.length > 0 ? breakpoints.join(" to ") : "none"
        }`,
        `Advisory: ${advisory ?? "—"}`,
        ...(geometryNote ? [`Note: ${geometryNote}`] : []),
        ...(issuedAt
          ? [`Issued: ${formatBothTimes(issuedAt, effectiveTimeZone)}`]
          : []),
        `CRS: ${crsText}`,
      ];
      const meta: WeatherbotLayerMetadata = {
        id: `ww-${storm.atcf_id}-${code}-${String(idx)}`,
        category: "watches_warnings",
        crsText,
        popupTitle,
        popupLines,
        tooltipText: `${watchWarningLabel(code)}: ${
          breakpoints.length > 0 ? breakpoints.join(" to ") : stormLabel
        }`,
      };
      attachPopupAndTooltip(layer, meta);
      wwItems.push({
        ...meta,
        layer,
        latLngs: collectFeatureLatLngs(segFeature),
        style,
      });
    });
  }

  mapData.outlook_areas.features.forEach((outFeature, idx) => {
    const style = outlookStyle(outFeature.properties);
    const layer = createGeometryLayer(outFeature, style, 6);
    if (!layer) {
      return;
    }
    const crsText = formatCrs(outFeature.crs);
    const basin = stringProp(outFeature.properties, "basin") ?? "Atlantic";
    const kind =
      stringProp(outFeature.properties, "kind") ?? "development_region";
    const chance2d = numberProp(outFeature.properties, "chance_2day_pct");
    const chance7d = numberProp(outFeature.properties, "chance_7day_pct");
    const risk2d = stringProp(outFeature.properties, "risk_2day");
    const risk7d = stringProp(outFeature.properties, "risk_7day");
    const issuedAt = stringProp(outFeature.properties, "issued_at");

    const chance2dText =
      chance2d !== null
        ? `${String(chance2d)}% (${risk2d ?? style.riskCategory})`
        : "—";
    const chance7dText =
      chance7d !== null
        ? `${String(chance7d)}% (${risk7d ?? style.riskCategory})`
        : "—";

    const popupTitle = `${basin} Outlook (${kind})`;
    const popupLines = [
      `2-day formation chance: ${chance2dText}`,
      `7-day formation chance: ${chance7dText}`,
      ...(issuedAt ? [`Issued: ${formatUtc(issuedAt)}`] : []),
      `CRS: ${crsText}`,
    ];
    const meta: WeatherbotLayerMetadata = {
      id: `outlook-${basin}-${String(idx)}`,
      category: "outlook",
      crsText,
      popupTitle,
      popupLines,
      tooltipText: `${basin} outlook: 2-day ${chance2dText}, 7-day ${chance7dText}`,
    };
    attachPopupAndTooltip(layer, meta);
    outlookItems.push({
      ...meta,
      layer,
      latLngs: collectFeatureLatLngs(outFeature),
      style,
    });
  });

  // Track which location polygons we have added so we don't duplicate between
  // mapData.locations (feature_kind="polygon") and mapData.location_polygons.
  const addedPolygonNames = new Set<string>();

  const addLocationPolygon = (
    polyFeature: GeoJsonFeatureResponse,
    idx: number,
  ) => {
    const locName =
      stringProp(polyFeature.properties, "name") ?? `Location ${String(idx)}`;
    if (addedPolygonNames.has(locName)) {
      return;
    }
    addedPolygonNames.add(locName);

    const level = numberProp(polyFeature.properties, "level");
    const label = stringProp(polyFeature.properties, "label");
    const zoneId = stringProp(polyFeature.properties, "zone_id");
    const colors = locationLevelColors(level);
    const style: L.PathOptions = {
      color: colors.color,
      fillColor: colors.fillColor,
      weight: 2,
      opacity: 0.85,
      fillOpacity: 0.14,
      dashArray: "4 4",
    };
    const layer = createGeometryLayer(polyFeature, style);
    if (!layer) {
      return;
    }
    const crsText = formatCrs(polyFeature.crs);
    const levelText =
      level !== null
        ? `Level ${String(level)}${label ? ` (${label})` : ""}`
        : "No stored assessment";
    const popupTitle = `${locName} — Zone polygon`;
    const popupLines = [
      `Threat level: ${levelText}`,
      ...(zoneId ? [`Zone: ${zoneId}`] : []),
      `CRS: ${crsText}`,
    ];
    const meta: WeatherbotLayerMetadata = {
      id: `location-polygon-${locName}`,
      category: "locations",
      crsText,
      popupTitle,
      popupLines,
      tooltipText: `${locName} zone (${levelText})`,
    };
    attachPopupAndTooltip(layer, meta);
    locationItems.push({
      ...meta,
      layer,
      latLngs: collectFeatureLatLngs(polyFeature),
      style,
    });
  };

  mapData.location_polygons.features.forEach((polyFeature, idx) => {
    addLocationPolygon(polyFeature, idx);
  });

  mapData.locations.features.forEach((locFeature, idx) => {
    const featureKind = stringProp(locFeature.properties, "feature_kind");
    if (featureKind === "polygon" || locFeature.geometry.type !== "Point") {
      addLocationPolygon(locFeature, idx);
      return;
    }

    const locName =
      stringProp(locFeature.properties, "name") ?? `Location ${String(idx)}`;
    const level = numberProp(locFeature.properties, "level");
    const label = stringProp(locFeature.properties, "label");
    const inCone = booleanProp(locFeature.properties, "in_cone");
    const insideNws = booleanProp(locFeature.properties, "inside_nws_coverage");
    const evac = booleanProp(
      locFeature.properties,
      "evacuation_order_in_effect",
    );

    const colors = locationLevelColors(level);
    const style: L.CircleMarkerOptions = {
      color: colors.color,
      fillColor: colors.fillColor,
      fillOpacity: 0.9,
      weight: 2.5,
      radius: 8,
    };
    const layer = createGeometryLayer(locFeature, style, 8);
    if (!layer) {
      return;
    }
    const crsText = formatCrs(locFeature.crs);
    const levelText =
      level !== null
        ? `Level ${String(level)}${label ? ` (${label})` : ""}`
        : "No stored assessment";
    const popupTitle = locName;
    const popupLines = [
      `Threat level: ${levelText}`,
      ...(inCone !== null
        ? [`In NHC cone: ${inCone ? "yes" : "no"}`]
        : []),
      ...(insideNws !== null
        ? [
            `Coverage: ${
              insideNws ? "Inside NWS coverage" : "Outside NWS coverage"
            }`,
          ]
        : []),
      ...(evac ? ["Evacuation order: in effect"] : []),
      `CRS: ${crsText}`,
    ];
    const meta: WeatherbotLayerMetadata = {
      id: `location-point-${locName}`,
      category: "locations",
      crsText,
      popupTitle,
      popupLines,
      tooltipText: `${locName}: ${levelText}`,
    };
    attachPopupAndTooltip(layer, meta);
    locationItems.push({
      ...meta,
      layer,
      latLngs: collectFeatureLatLngs(locFeature),
      style,
    });
  });

  const items: MapLayerItem[] = [
    ...coneItems,
    ...trackItems,
    ...pointItems,
    ...wwItems,
    ...outlookItems,
    ...locationItems,
  ];

  return {
    items,
    byCategory: {
      cone: coneItems,
      track: trackItems,
      points: pointItems,
      watches_warnings: wwItems,
      outlook: outlookItems,
      locations: locationItems,
    },
    bounds: computeMapBounds(mapData),
  };
}
