// frontend/src/map/layers.test.ts
import { describe, expect, it } from "vitest";
import type { components } from "../api/schema.ts";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import mapFixture from "../test/fixtures/map.json";
import replayAdvisoryFixture from "../test/fixtures/replay-advisory.json";
import {
  buildMapLayers,
  collectFeatureLatLngs,
  computeMapBounds,
  createPopupElement,
  createTooltipElement,
  DEFAULT_ATLANTIC_CENTER,
  DEFAULT_ATLANTIC_ZOOM,
  forecastPointStyle,
  formatCrs,
  MAP_LEGEND_SECTIONS,
  type MapDepthResponse,
  type MapResponse,
  NEUTRAL_SURGE_COLOR,
  NHC_WATCH_WARNING_COLORS,
  OSM_ATTRIBUTION_HTML,
  OSM_REFERRER_POLICY,
  OSM_TILE_OPTIONS,
  OSM_TILE_URL,
  OUTLOOK_RISK_COLORS,
  outlookStyle,
  parsePeakSurgeRange,
  pastTrackLineStyle,
  PEAK_SURGE_RANGE_COLORS,
  peakSurgeStyle,
  watchWarningColor,
  watchWarningStyle,
  windProbabilityBandStyle,
  windRadiiStyle,
} from "./layers.ts";

const TYPED_MAP = asSchema<MapResponse>(
  mapFixture satisfies JsonFixture<MapResponse>,
);
const TYPED_REPLAY_ADVISORY = asSchema<MapResponse>(
  replayAdvisoryFixture satisfies JsonFixture<MapResponse>,
);

describe("map/layers", () => {
  it("exports compliant OpenStreetMap tile options and whole-number Atlantic defaults", () => {
    expect(OSM_TILE_URL).toBe(
      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    );
    expect(OSM_REFERRER_POLICY).toBe("strict-origin-when-cross-origin");
    expect(OSM_ATTRIBUTION_HTML).toContain("OpenStreetMap contributors");
    expect(OSM_ATTRIBUTION_HTML).toContain(
      "https://www.openstreetmap.org/copyright",
    );
    expect(OSM_TILE_OPTIONS.maxZoom).toBe(19);
    expect(OSM_TILE_OPTIONS.referrerPolicy).toBe(
      "strict-origin-when-cross-origin",
    );
    expect(OSM_TILE_OPTIONS.crossOrigin).toBeUndefined();
    expect(OSM_TILE_OPTIONS.keepBuffer).toBeUndefined();

    expect(Number.isInteger(DEFAULT_ATLANTIC_CENTER[0])).toBe(true);
    expect(Number.isInteger(DEFAULT_ATLANTIC_CENTER[1])).toBe(true);
    expect(Number.isInteger(DEFAULT_ATLANTIC_ZOOM)).toBe(true);
  });

  it("builds storm, outlook, and location layers from map.json and replay-advisory.json with NHC colours, legends, and CRS popups", () => {
    const liveBuilt = buildMapLayers(TYPED_MAP, {
      timeZone: "America/New_York",
    });

    expect(liveBuilt.byCategory.cone.length).toBe(1);
    expect(liveBuilt.byCategory.track.length).toBe(1);
    expect(liveBuilt.byCategory.points.length).toBe(
      TYPED_MAP.storms[0]!.forecast_points.features.length,
    );
    expect(liveBuilt.byCategory.outlook.length).toBe(
      TYPED_MAP.outlook_areas.features.length,
    );
    // 2 location points + 1 stored polygon (Miami-Dade County Hall)
    expect(liveBuilt.byCategory.locations.length).toBe(3);

    for (const item of liveBuilt.items) {
      expect(item.crsText).toBe("EPSG:4326");
      expect(item.popupLines.some((line) => line.includes("CRS: EPSG:4326"))).toBe(
        true,
      );
    }

    // Forecast point tooltips include UTC, local time zone, and intensity
    const firstPoint = liveBuilt.byCategory.points[0]!;
    expect(firstPoint.tooltipText).toContain("UTC");
    expect(firstPoint.tooltipText).toContain("EDT");
    expect(firstPoint.tooltipText).toContain("85 kt");

    // Replay advisory (Irma AL112017 advisory 036)
    const replayBuilt = buildMapLayers(TYPED_REPLAY_ADVISORY, {
      timeZone: "America/New_York",
    });
    expect(replayBuilt.byCategory.cone.length).toBe(1);
    expect(replayBuilt.byCategory.track.length).toBe(1);
    expect(replayBuilt.byCategory.points.length).toBe(
      TYPED_REPLAY_ADVISORY.storms[0]!.forecast_points.features.length,
    );
    expect(replayBuilt.byCategory.watches_warnings.length).toBe(
      TYPED_REPLAY_ADVISORY.storms[0]!.watch_warnings.features.length,
    );

    // Irma replay storm geometries declare native (D_Sphere) CRS
    expect(replayBuilt.byCategory.cone[0]!.crsText).toBe("native (D_Sphere)");
    expect(
      replayBuilt.byCategory.cone[0]!.popupLines.some((l) =>
        l.includes("CRS: native (D_Sphere)"),
      ),
    ).toBe(true);
    expect(replayBuilt.byCategory.track[0]!.crsText).toBe("native (D_Sphere)");
    expect(replayBuilt.byCategory.points[0]!.crsText).toBe("native (D_Sphere)");

    // Replay watch-warning segments carry HWR, HWA, TWR, TWA colours and breakpoint names
    const codesSeen = new Set<string>();
    for (const seg of replayBuilt.byCategory.watches_warnings) {
      expect(seg.crsText).toBe("native (D_Sphere)");
      expect(
        seg.popupLines.some((l) => l.startsWith("Breakpoints:")),
      ).toBe(true);
      if (seg.id.includes("-HWR-")) {
        codesSeen.add("HWR");
        expect(seg.style.color).toBe(NHC_WATCH_WARNING_COLORS.HWR);
      } else if (seg.id.includes("-HWA-")) {
        codesSeen.add("HWA");
        expect(seg.style.color).toBe(NHC_WATCH_WARNING_COLORS.HWA);
      } else if (seg.id.includes("-TWR-")) {
        codesSeen.add("TWR");
        expect(seg.style.color).toBe(NHC_WATCH_WARNING_COLORS.TWR);
      } else if (seg.id.includes("-TWA-")) {
        codesSeen.add("TWA");
        expect(seg.style.color).toBe(NHC_WATCH_WARNING_COLORS.TWA);
      }
    }
    expect(codesSeen).toEqual(new Set(["HWR", "HWA", "TWR"]));

    // Legend covers all twelve layer categories with new depth/overlay sections before locations
    expect(MAP_LEGEND_SECTIONS.map((s) => s.category)).toEqual([
      "cone",
      "track",
      "points",
      "watches_warnings",
      "outlook",
      "wind_radii",
      "past_track",
      "peak_surge",
      "wind_probabilities",
      "radar",
      "satellite",
      "locations",
    ]);
  });

  it("styles wind radii, past track, peak surge (known range, unknown range neutral, and markup in name), and probability bands with crsText on every built item", () => {
    expect(windRadiiStyle(64).color).toBe("#dc2626");
    expect(windRadiiStyle(50).color).toBe("#d97706");
    expect(windRadiiStyle(34).color).toBe("#0284c7");

    expect(pastTrackLineStyle({ ss: 4, stormtype: "MH" }).color).toBe("#7f1d1d");
    expect(pastTrackLineStyle({ ss: 1, stormtype: "HU" }).color).toBe("#b91c1c");
    expect(pastTrackLineStyle({ ss: 0, stormtype: "TS" }).color).toBe("#c2410c");
    expect(pastTrackLineStyle({ ss: 0, stormtype: "TD" }).color).toBe("#334155");

    expect(parsePeakSurgeRange("Tampa Bay...8-12 ft")).toBe("8-12 ft");
    expect(parsePeakSurgeRange("No Ellipsis Name")).toBeNull();

    const knownSurge = peakSurgeStyle("Tampa Bay...8-12 ft");
    expect(knownSurge.recognized).toBe(true);
    expect(knownSurge.color).toBe(PEAK_SURGE_RANGE_COLORS["8-12 ft"]!.color);
    expect(knownSurge.fillColor).toBe(
      PEAK_SURGE_RANGE_COLORS["8-12 ft"]!.fillColor,
    );

    const unknownSurge = peakSurgeStyle("Outer Bank...99-105 ft");
    expect(unknownSurge.recognized).toBe(false);
    expect(unknownSurge.parsedRange).toBe("99-105 ft");
    expect(unknownSurge.color).toBe(NEUTRAL_SURGE_COLOR.color);
    expect(unknownSurge.fillColor).toBe(NEUTRAL_SURGE_COLOR.fillColor);

    expect(windProbabilityBandStyle(5).fillColor).toBe("#86efac");
    expect(windProbabilityBandStyle(50).fillColor).toBe("#f97316");
    expect(windProbabilityBandStyle(90).fillColor).toBe("#7e22ce");

    const syntheticDepth: MapDepthResponse = {
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
                  threshold_kt: 64,
                  tau_h: 0,
                  valid_at: "2026-10-12T18:00:00Z",
                  ne_extent_nmi: 30,
                  se_extent_nmi: 25,
                  sw_extent_nmi: 20,
                  nw_extent_nmi: 25,
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
            properties: {
              name: "Tampa Bay <b><script>x</script></b>...8-12 ft",
              layer: "Polygons",
            },
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
          {
            type: "Feature",
            crs: { name: "EPSG:4326", datum: null },
            properties: {
              name: "Unknown Stretch...99-105 ft",
              layer: "Lines",
            },
            geometry: {
              type: "LineString",
              crs: { name: "EPSG:4326", datum: null },
              coordinates: [
                [-82.85, 28.18],
                [-82.74, 27.6],
              ],
            },
          },
        ],
      },
      notice: TYPED_MAP.notice,
    };

    const built = buildMapLayers(TYPED_MAP, {
      timeZone: "America/New_York",
      depthData: syntheticDepth,
    });

    expect(built.byCategory.wind_radii.length).toBe(1);
    expect(built.byCategory.past_track.length).toBe(2);
    expect(built.byCategory.peak_surge.length).toBe(2);

    for (const item of built.items) {
      expect(item.crsText).toBe("EPSG:4326");
    }

    const markupSurgeItem = built.byCategory.peak_surge[0]!;
    const popupContent = markupSurgeItem.layer.getPopup()?.getContent() as HTMLElement;
    expect(popupContent).toBeInstanceOf(HTMLElement);
    expect(popupContent.querySelector("b")).toBeNull();
    expect(popupContent.querySelector("script")).toBeNull();
    expect(popupContent.textContent).toContain(
      "Tampa Bay <b><script>x</script></b>...8-12 ft",
    );

    const unknownRangeItem = built.byCategory.peak_surge[1]!;
    expect(unknownRangeItem.style.color).toBe(NEUTRAL_SURGE_COLOR.color);
    expect(unknownRangeItem.popupLines.join(" ")).toContain("unrecognized");
  });

  it("maps NHC watch-warning codes, forecast point classifications, and outlook chances to their canonical colours", () => {
    expect(watchWarningColor("HWR")).toBe("#dc2626");
    expect(watchWarningColor("HWA")).toBe("#ec4899");
    expect(watchWarningColor("TWR")).toBe("#2563eb");
    expect(watchWarningColor("TWA")).toBe("#eab308");
    expect(watchWarningStyle("HWR").color).toBe("#dc2626");

    expect(
      forecastPointStyle({
        development: "Major Hurricane",
        saffir_simpson: 5,
      }).fillColor,
    ).toBe("#dc2626");
    expect(
      forecastPointStyle({
        development: "Hurricane",
        saffir_simpson: 2,
      }).fillColor,
    ).toBe("#ef4444");
    expect(
      forecastPointStyle({
        development: "Tropical Storm",
        saffir_simpson: null,
      }).fillColor,
    ).toBe("#f97316");
    expect(
      forecastPointStyle({
        development: "Tropical Depression",
        saffir_simpson: null,
      }).fillColor,
    ).toBe("#38bdf8");

    expect(
      outlookStyle({ risk_7day: "Low", chance_7day_pct: 20 }).color,
    ).toBe(OUTLOOK_RISK_COLORS.Low.color);
    expect(
      outlookStyle({ risk_7day: "Medium", chance_7day_pct: 50 }).color,
    ).toBe(OUTLOOK_RISK_COLORS.Medium.color);
    expect(
      outlookStyle({ risk_7day: "High", chance_7day_pct: 80 }).color,
    ).toBe(OUTLOOK_RISK_COLORS.High.color);

    expect(formatCrs({ name: "EPSG:4326", datum: null })).toBe("EPSG:4326");
    expect(formatCrs({ name: "native", datum: "D_Sphere" })).toBe(
      "native (D_Sphere)",
    );
  });

  it("preserves continuous unwrapped longitudes across the antimeridian for Central Pacific geometries", () => {
    const centralPacificFeature: components["schemas"]["GeoJsonFeatureResponse"] =
      {
        type: "Feature",
        crs: { name: "EPSG:4326", datum: null },
        properties: {
          atcf_id: "CP012026",
          storm_name: "Akoni",
        },
        geometry: {
          type: "LineString",
          crs: { name: "EPSG:4326", datum: null },
          // Two-decimal coordinates crossing 180° -> -180° unwrapped as <= -180°
          coordinates: [
            [-179.25, 18.5],
            [-179.85, 18.75],
            [-180.45, 19.0],
            [-181.15, 19.25],
          ],
        },
      };

    const latLngs = collectFeatureLatLngs(centralPacificFeature);
    expect(latLngs).toEqual([
      [18.5, -179.25],
      [18.75, -179.85],
      [19.0, -180.45],
      [19.25, -181.15],
    ]);

    // Consecutive longitudes never jump by ~360 degrees
    for (let i = 1; i < latLngs.length; i += 1) {
      const prevLon = latLngs.at(i - 1)![1];
      const currLon = latLngs.at(i)![1];
      expect(Math.abs(currLon - prevLon)).toBeLessThan(5);
    }
  });

  it("computes bounds that cover all storms and watched locations", () => {
    const bounds = computeMapBounds(TYPED_REPLAY_ADVISORY);
    expect(bounds).not.toBeNull();
    expect(bounds!.isValid()).toBe(true);

    // Covers both watched locations (Miami-Dade County Hall and Parliament Square)
    for (const locFeature of TYPED_REPLAY_ADVISORY.locations.features) {
      for (const pt of collectFeatureLatLngs(locFeature)) {
        expect(bounds!.contains(pt)).toBe(true);
      }
    }

    // Covers Irma's cone and track vertices
    const irma = TYPED_REPLAY_ADVISORY.storms[0]!;
    for (const pt of collectFeatureLatLngs(irma.cone!)) {
      expect(bounds!.contains(pt)).toBe(true);
    }
    for (const pt of collectFeatureLatLngs(irma.track!)) {
      expect(bounds!.contains(pt)).toBe(true);
    }
  });

  it("renders HTML tags in popup and tooltip strings literally as text nodes", () => {
    const popupEl = createPopupElement("Storm <b>Alpha</b>", [
      "Breakpoint: <script>alert(1)</script>",
      "CRS: EPSG:4326",
    ]);
    expect(popupEl.querySelector("b")).toBeNull();
    expect(popupEl.querySelector("script")).toBeNull();
    expect(popupEl.textContent).toContain("Storm <b>Alpha</b>");
    expect(popupEl.textContent).toContain(
      "Breakpoint: <script>alert(1)</script>",
    );

    const tooltipEl = createTooltipElement("<b>Untrusted</b> tooltip");
    expect(tooltipEl.querySelector("b")).toBeNull();
    expect(tooltipEl.textContent).toBe("<b>Untrusted</b> tooltip");
  });
});
