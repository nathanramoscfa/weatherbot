// frontend/src/map/layers.ts
import * as L from "leaflet";
import type { components } from "../api/schema.ts";
import { formatBothTimes, formatUtc } from "../pages/format.ts";

export type MapResponse = components["schemas"]["MapResponse"];
export type MapDepthResponse = components["schemas"]["MapDepthResponse"];
export type WindProbabilityResponse =
  components["schemas"]["WindProbabilityResponse"];
export type MapAdvisoriesResponse =
  components["schemas"]["MapAdvisoriesResponse"];
export type AdvisoryStepResponse =
  components["schemas"]["AdvisoryStepResponse"];
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

export const NOWCOAST_RADAR_WMS_URL =
  "https://nowcoast.noaa.gov/geoserver/weather_radar/ows" as const;
export const NOWCOAST_RADAR_LAYER =
  "conus_base_reflectivity_mosaic" as const;
export const NOWCOAST_SATELLITE_WMS_URL =
  "https://nowcoast.noaa.gov/geoserver/satellite/ows" as const;
export const NOWCOAST_SATELLITE_LAYER = "goes_longwave_imagery" as const;
export const NOWCOAST_ATTRIBUTION_TEXT = "NOAA nowCOAST" as const;
export const NOWCOAST_WMS_OPACITY = 0.6;
export const NOWCOAST_AGE_NOTE =
  "NOAA nowCOAST imagery may be several minutes old." as const;
export const WIND_PROBABILITY_NOTE =
  "Chance of winds at this speed within 120 hours" as const;

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
  | "locations"
  | "wind_radii"
  | "past_track"
  | "peak_surge"
  | "wind_probabilities"
  | "radar"
  | "satellite";

export type LayerVisibility = Readonly<Record<MapLayerKey, boolean>>;

export interface LayerToggleItem {
  readonly key: MapLayerKey;
  readonly label: string;
}

export const DEFAULT_ON_LAYER_KEYS: readonly MapLayerKey[] = [
  "cone",
  "track",
  "points",
  "watches_warnings",
  "outlook",
  "locations",
] as const;

export const LAYER_TOGGLE_ITEMS: readonly LayerToggleItem[] = [
  { key: "cone", label: "Storm cones" },
  { key: "track", label: "Forecast tracks" },
  { key: "points", label: "Forecast points" },
  { key: "watches_warnings", label: "Watches & warnings" },
  { key: "outlook", label: "Outlook areas" },
  { key: "locations", label: "Locations" },
  { key: "wind_radii", label: "Wind radii" },
  { key: "past_track", label: "Past track" },
  { key: "peak_surge", label: "Peak surge" },
  { key: "wind_probabilities", label: "Wind probabilities" },
  { key: "radar", label: "Radar (nowCOAST)" },
  { key: "satellite", label: "Satellite IR (nowCOAST)" },
] as const;

export const DEFAULT_LAYER_VISIBILITY: LayerVisibility = {
  cone: true,
  track: true,
  points: true,
  watches_warnings: true,
  outlook: true,
  locations: true,
  wind_radii: false,
  past_track: false,
  peak_surge: false,
  wind_probabilities: false,
  radar: false,
  satellite: false,
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
    case "wind_radii":
      return visibility.wind_radii;
    case "past_track":
      return visibility.past_track;
    case "peak_surge":
      return visibility.peak_surge;
    case "wind_probabilities":
      return visibility.wind_probabilities;
    case "radar":
      return visibility.radar;
    case "satellite":
      return visibility.satellite;
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
    category: "wind_radii",
    title: "Forecast & advisory wind radii",
    items: [
      {
        label: "64 kt hurricane-force wind radii",
        color: "#dc2626",
        fillColor: "#f87171",
        shape: "polygon",
        swatchClass: "h-3 w-3.5 rounded-xs border-2 border-red-600 bg-red-400/40",
      },
      {
        label: "50 kt storm-force wind radii",
        color: "#d97706",
        fillColor: "#fbbf24",
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border-2 border-amber-600 bg-amber-400/35",
      },
      {
        label: "34 kt tropical-storm-force wind radii",
        color: "#0284c7",
        fillColor: "#38bdf8",
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border-2 border-dashed border-sky-600 bg-sky-400/25",
      },
    ],
  },
  {
    category: "past_track",
    title: "Past track & positions",
    items: [
      {
        label: "Past center track (solid line)",
        color: "#334155",
        shape: "line",
        swatchClass: "h-1 w-4 rounded-xs bg-slate-700 dark:bg-slate-300",
      },
      {
        label: "Past position (styled by Saffir-Simpson category)",
        color: "#b91c1c",
        fillColor: "#ef4444",
        shape: "circle",
        swatchClass:
          "h-2.5 w-2.5 rounded-full border-2 border-red-700 bg-red-500",
      },
    ],
  },
  {
    category: "peak_surge",
    title: "Peak storm surge (NHC)",
    items: [
      {
        label: "High surge (8–12 ft / >9 ft)",
        color: "#991b1b",
        fillColor: "#ef4444",
        shape: "polygon",
        swatchClass: "h-3 w-3.5 rounded-xs border-2 border-red-800 bg-red-500/60",
      },
      {
        label: "Moderate surge (5–10 ft / 6–9 ft)",
        color: "#9a3412",
        fillColor: "#f97316",
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border-2 border-orange-800 bg-orange-500/60",
      },
      {
        label: "Lower surge (1–4 ft / 3–5 ft)",
        color: "#854d0e",
        fillColor: "#facc15",
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border-2 border-yellow-800 bg-yellow-400/60",
      },
      {
        label: "Unrecognized surge range (neutral)",
        color: "#475569",
        fillColor: "#94a3b8",
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border-2 border-slate-600 bg-slate-400/50",
      },
    ],
  },
  {
    category: "wind_probabilities",
    title: "120-h wind speed probabilities",
    items: [
      {
        label: "High probability (≥60%)",
        color: "#7e22ce",
        fillColor: "#a855f7",
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border border-purple-700 bg-purple-500/70",
      },
      {
        label: "Moderate probability (30–60%)",
        color: "#c2410c",
        fillColor: "#fb923c",
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border border-orange-700 bg-orange-400/70",
      },
      {
        label: "Low probability (5–30%)",
        color: "#15803d",
        fillColor: "#4ade80",
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border border-green-700 bg-green-400/70",
      },
      {
        label: "Archive extract coverage boundary",
        color: "#475569",
        shape: "line",
        swatchClass:
          "h-3 w-3.5 rounded-xs border-2 border-dashed border-slate-600 bg-transparent",
      },
    ],
  },
  {
    category: "radar",
    title: "Weather radar (NOAA nowCOAST)",
    items: [
      {
        label: "CONUS base reflectivity mosaic (WMS)",
        color: "#0284c7",
        fillColor: "#38bdf8",
        shape: "polygon",
        swatchClass: "h-3 w-3.5 rounded-xs border border-sky-700 bg-sky-500/60",
      },
    ],
  },
  {
    category: "satellite",
    title: "GOES longwave IR (NOAA nowCOAST)",
    items: [
      {
        label: "GOES longwave infrared imagery (WMS)",
        color: "#475569",
        fillColor: "#94a3b8",
        shape: "polygon",
        swatchClass:
          "h-3 w-3.5 rounded-xs border border-slate-600 bg-slate-400/60",
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

export function windRadiiStyle(thresholdKt: number | null): L.PathOptions {
  switch (thresholdKt) {
    case 64:
      return {
        color: "#dc2626",
        fillColor: "#f87171",
        weight: 2,
        opacity: 0.9,
        fillOpacity: 0.16,
      };
    case 50:
      return {
        color: "#d97706",
        fillColor: "#fbbf24",
        weight: 1.8,
        opacity: 0.85,
        fillOpacity: 0.12,
      };
    default:
      return {
        color: "#0284c7",
        fillColor: "#38bdf8",
        weight: 1.5,
        opacity: 0.8,
        fillOpacity: 0.08,
        dashArray: "4 2",
      };
  }
}

export function pastTrackLineStyle(
  props: Readonly<Record<string, unknown>>,
): L.PathOptions {
  const ss = typeof props.ss === "number" ? props.ss : null;
  const stormType =
    typeof props.stormtype === "string" ? props.stormtype : null;
  if ((ss !== null && ss >= 3) || stormType === "MH") {
    return {
      color: "#7f1d1d",
      weight: 2.5,
      opacity: 0.85,
    };
  }
  if ((ss !== null && ss >= 1) || stormType === "HU") {
    return {
      color: "#b91c1c",
      weight: 2.5,
      opacity: 0.85,
    };
  }
  if (stormType === "TS" || stormType === "SS") {
    return {
      color: "#c2410c",
      weight: 2.2,
      opacity: 0.85,
    };
  }
  return {
    color: "#334155",
    weight: 2,
    opacity: 0.8,
  };
}

export function pastPointStyle(
  props: Readonly<Record<string, unknown>>,
): L.CircleMarkerOptions & { readonly classificationLabel: string } {
  const ss = typeof props.ss === "number" ? props.ss : null;
  const stormType =
    typeof props.stormtype === "string" ? props.stormtype : null;
  return forecastPointStyle({
    saffir_simpson: ss,
    storm_type: stormType,
  });
}

export const NEUTRAL_SURGE_COLOR = {
  color: "#475569",
  fillColor: "#94a3b8",
} as const;

export const PEAK_SURGE_RANGE_COLORS: Readonly<
  Record<string, { readonly color: string; readonly fillColor: string }>
> = {
  "1-3 ft": { color: "#0369a1", fillColor: "#38bdf8" },
  "2-4 ft": { color: "#0369a1", fillColor: "#38bdf8" },
  "3-5 ft": { color: "#854d0e", fillColor: "#facc15" },
  "4-6 ft": { color: "#854d0e", fillColor: "#facc15" },
  "4-7 ft": { color: "#854d0e", fillColor: "#facc15" },
  "5-8 ft": { color: "#9a3412", fillColor: "#f97316" },
  "5-10 ft": { color: "#9a3412", fillColor: "#f97316" },
  "6-9 ft": { color: "#9a3412", fillColor: "#f97316" },
  "6-10 ft": { color: "#9a3412", fillColor: "#f97316" },
  "8-12 ft": { color: "#991b1b", fillColor: "#ef4444" },
  "9-13 ft": { color: "#991b1b", fillColor: "#ef4444" },
  "10-15 ft": { color: "#581c87", fillColor: "#a855f7" },
  ">10 ft": { color: "#581c87", fillColor: "#a855f7" },
  ">15 ft": { color: "#581c87", fillColor: "#a855f7" },
} as const;

export function parsePeakSurgeRange(name: string): string | null {
  const idx = name.lastIndexOf("...");
  if (idx === -1) {
    return null;
  }
  const raw = name.slice(idx + 3).trim().toLowerCase();
  return raw.length > 0 ? raw : null;
}

export function peakSurgeStyle(name: string): L.PathOptions & {
  readonly parsedRange: string | null;
  readonly recognized: boolean;
} {
  const parsedRange = parsePeakSurgeRange(name);
  let palette: { readonly color: string; readonly fillColor: string } | null =
    null;
  if (parsedRange !== null) {
    for (const [k, v] of Object.entries(PEAK_SURGE_RANGE_COLORS)) {
      if (k === parsedRange) {
        palette = v;
        break;
      }
    }
  }
  const effective = palette ?? NEUTRAL_SURGE_COLOR;
  return {
    color: effective.color,
    fillColor: effective.fillColor,
    weight: 2.5,
    opacity: 0.9,
    fillOpacity: 0.4,
    parsedRange,
    recognized: palette !== null,
  };
}

// NHC 120-hour cumulative wind speed probability ramp as Tailwind-free hex constants.
export const WIND_PROBABILITY_RAMP: readonly {
  readonly lowerPct: number;
  readonly label: string;
  readonly color: string;
  readonly fillColor: string;
}[] = [
  { lowerPct: 0, label: "<5%", color: "#86efac", fillColor: "#dcfce7" },
  { lowerPct: 5, label: "5-10%", color: "#4ade80", fillColor: "#86efac" },
  { lowerPct: 10, label: "10-20%", color: "#22c55e", fillColor: "#4ade80" },
  { lowerPct: 20, label: "20-30%", color: "#eab308", fillColor: "#fde047" },
  { lowerPct: 30, label: "30-40%", color: "#ca8a04", fillColor: "#facc15" },
  { lowerPct: 40, label: "40-50%", color: "#ea580c", fillColor: "#fb923c" },
  { lowerPct: 50, label: "50-60%", color: "#c2410c", fillColor: "#f97316" },
  { lowerPct: 60, label: "60-70%", color: "#b91c1c", fillColor: "#ef4444" },
  { lowerPct: 70, label: "70-80%", color: "#991b1b", fillColor: "#dc2626" },
  { lowerPct: 80, label: "80-90%", color: "#7e22ce", fillColor: "#a855f7" },
  { lowerPct: 90, label: ">90%", color: "#581c87", fillColor: "#7e22ce" },
] as const;

export function windProbabilityBandStyle(lowerPct: number): L.PathOptions {
  let matched = WIND_PROBABILITY_RAMP[0];
  for (const entry of WIND_PROBABILITY_RAMP) {
    if (lowerPct >= entry.lowerPct) {
      matched = entry;
    }
  }
  const color = matched ? matched.color : "#475569";
  const fillColor = matched ? matched.fillColor : "#94a3b8";
  return {
    color,
    fillColor,
    weight: 1,
    opacity: 0.85,
    fillOpacity: 0.45,
  };
}

export function windProbabilityCoverageStyle(): L.PathOptions {
  return {
    color: "#475569",
    fillColor: "#94a3b8",
    weight: 1.5,
    opacity: 0.85,
    fillOpacity: 0.04,
    dashArray: "6 4",
  };
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
  readonly depthData?: MapDepthResponse | null;
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
  const depthData = options?.depthData ?? null;
  const coneItems: MapLayerItem[] = [];
  const trackItems: MapLayerItem[] = [];
  const pointItems: MapLayerItem[] = [];
  const wwItems: MapLayerItem[] = [];
  const outlookItems: MapLayerItem[] = [];
  const windRadiiItems: MapLayerItem[] = [];
  const pastTrackItems: MapLayerItem[] = [];
  const peakSurgeItems: MapLayerItem[] = [];
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

  if (depthData) {
    for (const stormDepth of depthData.storms) {
      stormDepth.wind_radii.features.forEach((radiiFeature, idx) => {
        const thresholdKt = numberProp(radiiFeature.properties, "threshold_kt");
        const tauH = numberProp(radiiFeature.properties, "tau_h");
        const advisory = stringProp(radiiFeature.properties, "advisory");
        const stormName =
          stringProp(radiiFeature.properties, "storm_name") ??
          stormDepth.atcf_id;
        const isAdvField = booleanProp(
          radiiFeature.properties,
          "is_advisory_field",
        );
        const ne = numberProp(radiiFeature.properties, "ne_extent_nmi");
        const se = numberProp(radiiFeature.properties, "se_extent_nmi");
        const sw = numberProp(radiiFeature.properties, "sw_extent_nmi");
        const nw = numberProp(radiiFeature.properties, "nw_extent_nmi");
        const validAt = stringProp(radiiFeature.properties, "valid_at");

        const style = windRadiiStyle(thresholdKt);
        const layer = createGeometryLayer(radiiFeature, style);
        if (!layer) {
          return;
        }
        const crsText = formatCrs(radiiFeature.crs);
        const thresholdLabel =
          thresholdKt !== null ? `${String(thresholdKt)} kt` : "Wind";
        const kindLabel = isAdvField ? "Advisory wind field" : "Forecast radii";
        const popupTitle = `${stormName} (${stormDepth.atcf_id}) — ${thresholdLabel} ${kindLabel}`;
        const extentParts = [
          ne !== null ? `NE ${String(ne)}` : null,
          se !== null ? `SE ${String(se)}` : null,
          sw !== null ? `SW ${String(sw)}` : null,
          nw !== null ? `NW ${String(nw)}` : null,
        ].filter((part): part is string => part !== null);
        const popupLines = [
          `Advisory: ${advisory ?? "—"}${
            tauH !== null ? ` (+${String(tauH)} h)` : ""
          }`,
          ...(extentParts.length > 0
            ? [`Extents: ${extentParts.join(" · ")} nmi`]
            : []),
          ...(validAt
            ? [`Valid: ${formatBothTimes(validAt, effectiveTimeZone)}`]
            : []),
          `CRS: ${crsText}`,
        ];
        const meta: WeatherbotLayerMetadata = {
          id: `radii-${stormDepth.atcf_id}-${String(idx)}`,
          category: "wind_radii",
          crsText,
          popupTitle,
          popupLines,
          tooltipText: `${stormDepth.atcf_id} · ${thresholdLabel} (${
            tauH !== null ? `+${String(tauH)} h` : kindLabel
          })`,
        };
        attachPopupAndTooltip(layer, meta);
        windRadiiItems.push({
          ...meta,
          layer,
          latLngs: collectFeatureLatLngs(radiiFeature),
          style,
        });
      });

      stormDepth.past_track.features.forEach((trackFeature, idx) => {
        const style = pastTrackLineStyle(trackFeature.properties);
        const layer = createGeometryLayer(trackFeature, style);
        if (!layer) {
          return;
        }
        const crsText = formatCrs(trackFeature.crs);
        const stormType =
          stringProp(trackFeature.properties, "stormtype") ?? "Cyclone";
        const ss = numberProp(trackFeature.properties, "ss");
        const popupTitle = `${stormDepth.atcf_id} — Past track`;
        const popupLines = [
          `Stage: ${stormType}${
            ss !== null && ss > 0 ? ` (Category ${String(ss)})` : ""
          }`,
          `CRS: ${crsText}`,
        ];
        const meta: WeatherbotLayerMetadata = {
          id: `past-track-${stormDepth.atcf_id}-${String(idx)}`,
          category: "past_track",
          crsText,
          popupTitle,
          popupLines,
          tooltipText: `${stormDepth.atcf_id} past track (${stormType})`,
        };
        attachPopupAndTooltip(layer, meta);
        pastTrackItems.push({
          ...meta,
          layer,
          latLngs: collectFeatureLatLngs(trackFeature),
          style,
        });
      });

      stormDepth.past_points.features.forEach((ptFeature, idx) => {
        const ptStyle = pastPointStyle(ptFeature.properties);
        const layer = createGeometryLayer(ptFeature, ptStyle, 4.5);
        if (!layer) {
          return;
        }
        const crsText = formatCrs(ptFeature.crs);
        const stormType =
          stringProp(ptFeature.properties, "stormtype") ??
          ptStyle.classificationLabel;
        const ss = numberProp(ptFeature.properties, "ss");
        const intensity = numberProp(ptFeature.properties, "intensity");
        const mslp = numberProp(ptFeature.properties, "mslp");
        const dtg =
          numberProp(ptFeature.properties, "dtg") ??
          stringProp(ptFeature.properties, "dtg");
        const popupTitle = `${stormDepth.atcf_id} — Past position`;
        const popupLines = [
          `Stage: ${stormType}${
            ss !== null && ss > 0 ? ` (Category ${String(ss)})` : ""
          }`,
          ...(intensity !== null ? [`Intensity: ${String(intensity)} kt`] : []),
          ...(mslp !== null && mslp > 0
            ? [`Pressure: ${String(mslp)} mb`]
            : []),
          ...(dtg !== null ? [`Synoptic time: ${String(dtg)}`] : []),
          `CRS: ${crsText}`,
        ];
        const meta: WeatherbotLayerMetadata = {
          id: `past-point-${stormDepth.atcf_id}-${String(idx)}`,
          category: "past_track",
          crsText,
          popupTitle,
          popupLines,
          tooltipText: `${stormDepth.atcf_id} past position${
            intensity !== null ? ` (${String(intensity)} kt)` : ""
          }`,
        };
        attachPopupAndTooltip(layer, meta);
        pastTrackItems.push({
          ...meta,
          layer,
          latLngs: collectFeatureLatLngs(ptFeature),
          style: ptStyle,
        });
      });
    }

    depthData.peak_surge.features.forEach((surgeFeature, idx) => {
      const surgeName =
        stringProp(surgeFeature.properties, "name") ??
        `Peak surge ${String(idx + 1)}`;
      const sourceLayer =
        stringProp(surgeFeature.properties, "layer") ?? "Polygons";
      const surgeStyle = peakSurgeStyle(surgeName);
      const layer = createGeometryLayer(surgeFeature, surgeStyle);
      if (!layer) {
        return;
      }
      const crsText = formatCrs(surgeFeature.crs);
      const rangeText = surgeStyle.recognized
        ? (surgeStyle.parsedRange ?? "—")
        : `${surgeStyle.parsedRange ?? "unknown"} (unrecognized range — neutral style)`;
      const popupTitle = surgeName;
      const popupLines = [
        `Peak surge range: ${rangeText}`,
        `Source layer: ${sourceLayer}`,
        `CRS: ${crsText}`,
      ];
      const meta: WeatherbotLayerMetadata = {
        id: `surge-${String(idx)}`,
        category: "peak_surge",
        crsText,
        popupTitle,
        popupLines,
        tooltipText: surgeName,
      };
      attachPopupAndTooltip(layer, meta);
      peakSurgeItems.push({
        ...meta,
        layer,
        latLngs: collectFeatureLatLngs(surgeFeature),
        style: surgeStyle,
      });
    });
  }

  const items: MapLayerItem[] = [
    ...coneItems,
    ...trackItems,
    ...pointItems,
    ...wwItems,
    ...outlookItems,
    ...windRadiiItems,
    ...pastTrackItems,
    ...peakSurgeItems,
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
      wind_radii: windRadiiItems,
      past_track: pastTrackItems,
      peak_surge: peakSurgeItems,
      wind_probabilities: [],
      radar: [],
      satellite: [],
      locations: locationItems,
    },
    bounds: computeMapBounds(mapData),
  };
}
