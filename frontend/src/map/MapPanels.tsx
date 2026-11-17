// frontend/src/map/MapPanels.tsx
// Floating HUD panels positioned as siblings over the min-h-[70vh] map canvas.
import {
  ChevronDown,
  Compass,
  History,
  Layers,
  Maximize2,
} from "lucide-react";
import {
  formatAgeSeconds,
  formatUtc,
} from "../pages/format.ts";
import { Button, LinkButton } from "../ui/Button.tsx";
import { cx } from "../ui/threat.ts";
import {
  getLayerToggleItem,
  isLayerVisible,
  LAYER_GROUPS,
  type LayerVisibility,
  MAP_LEGEND_SECTIONS,
  type MapLayerKey,
  type MapResponse,
  NOWCOAST_AGE_NOTE,
} from "./layers.ts";

export type ProbabilityThresholdKt = 34 | 50 | 64;
export const PROBABILITY_THRESHOLDS: readonly ProbabilityThresholdKt[] = [
  34, 50, 64,
] as const;

export const DESKTOP_PANEL_MEDIA_QUERY = "(min-width: 1024px)";

export function isDefaultDesktopViewport(): boolean {
  if (typeof window === "undefined") {
    return true;
  }
  if (typeof window.matchMedia === "function") {
    return window.matchMedia(DESKTOP_PANEL_MEDIA_QUERY).matches;
  }
  return window.innerWidth >= 1024;
}

export interface MapStatusChipProps {
  readonly mapData: MapResponse | null | undefined;
  readonly corpusEnabled: boolean;
  readonly onFit: () => void;
  readonly className?: string;
}

export function MapStatusChip({
  mapData,
  corpusEnabled,
  onFit,
  className,
}: MapStatusChipProps) {
  return (
    <section
      aria-label="Map status"
      data-testid="map-status-chip"
      className={cx(
        "rounded-card border border-line bg-surface-card px-3 py-2 text-ink shadow-raised",
        className,
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-ink-muted tabular-nums">
          {mapData?.as_of ? (
            <>
              Origin:{" "}
              <strong className="font-semibold text-ink">
                {mapData.origin ?? "live"}
              </strong>{" "}
              · status{" "}
              <strong className="font-semibold text-ink">
                {mapData.status ?? "complete"}
              </strong>{" "}
              · as of {formatUtc(mapData.as_of)} ·{" "}
              {String(mapData.storms.length)} active{" "}
              {mapData.storms.length === 1 ? "storm" : "storms"}
            </>
          ) : (
            "No stored snapshot geometry yet. Showing default Atlantic basin view."
          )}
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" onClick={onFit}>
            <Maximize2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>Fit</span>
          </Button>
          {corpusEnabled && (
            <LinkButton
              to="/replay"
              variant="secondary"
              size="sm"
              data-testid="map-replay-link"
            >
              <History className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              <span>Replay a past storm</span>
            </LinkButton>
          )}
        </div>
      </div>
    </section>
  );
}

export interface MapLayersPanelProps {
  readonly open: boolean;
  readonly onToggleOpen: (nextOpen: boolean) => void;
  readonly visibility: LayerVisibility;
  readonly effectiveVisibility: LayerVisibility;
  readonly isLayerAvailable: (key: MapLayerKey) => boolean;
  readonly isViewingPastAdvisory: boolean;
  readonly onToggleLayer: (key: MapLayerKey, checked: boolean) => void;
  readonly probThresholdKt: ProbabilityThresholdKt;
  readonly onChangeProbThresholdKt: (next: ProbabilityThresholdKt) => void;
  readonly hasWindProbCoverage: boolean;
  readonly className?: string;
}

export function MapLayersPanel({
  open,
  onToggleOpen,
  visibility,
  effectiveVisibility,
  isLayerAvailable,
  isViewingPastAdvisory,
  onToggleLayer,
  probThresholdKt,
  onChangeProbThresholdKt,
  hasWindProbCoverage,
  className,
}: MapLayersPanelProps) {
  return (
    <section
      aria-label="Map layer toggles"
      data-testid="map-layers-panel"
      className={cx(
        "rounded-card border border-line bg-surface-card text-ink shadow-raised",
        className,
      )}
    >
      <h2 className="text-sm font-semibold text-ink">
        <button
          type="button"
          aria-expanded={open}
          aria-controls="map-layers-panel-body"
          onClick={() => onToggleOpen(!open)}
          className="flex min-h-6 w-full items-center justify-between gap-2 rounded-card px-3 py-2 text-left text-sm font-semibold text-ink hover:bg-surface-inset focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          <span className="flex items-center gap-2">
            <Layers className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
            <span>Layers</span>
          </span>
          <ChevronDown
            className={cx(
              "h-4 w-4 shrink-0 text-ink-subtle transition-transform",
              open ? "rotate-180" : "",
            )}
            aria-hidden="true"
          />
        </button>
      </h2>

      {open && (
        <div
          id="map-layers-panel-body"
          className="max-h-[36vh] space-y-1.5 overflow-y-auto border-t border-line px-3 py-2 lg:max-h-[calc(100dvh-18.5rem)]"
        >
          {LAYER_GROUPS.map((group) => (
            <div
              key={group.id}
              data-testid={`layer-group-${group.id}`}
              className="space-y-0.5"
            >
              <h3 className="text-sm font-semibold text-ink">{group.title}</h3>
              <div className="space-y-0.5">
                {group.keys.map((key) => {
                  const item = getLayerToggleItem(key);
                  if (!item) {
                    return null;
                  }
                  const available = isLayerAvailable(item.key);
                  const checked =
                    available && isLayerVisible(visibility, item.key);
                  const unavailableReason = !available
                    ? isViewingPastAdvisory
                      ? "live only"
                      : "unavailable"
                    : null;
                  return (
                    <label
                      key={item.key}
                      className={cx(
                        "flex min-h-6 items-center justify-between gap-2 rounded-control px-2 py-0.5 text-sm font-medium text-ink",
                        available
                          ? "cursor-pointer hover:bg-surface-inset"
                          : "cursor-not-allowed opacity-60",
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!available}
                          onChange={(e) =>
                            onToggleLayer(item.key, e.target.checked)
                          }
                          className="h-4 w-4 shrink-0 rounded border-line-strong text-brand focus:ring-brand disabled:cursor-not-allowed"
                        />
                        <span>{item.label}</span>
                      </span>
                      {unavailableReason && (
                        <span className="text-caption font-normal text-ink-subtle">
                          ({unavailableReason})
                        </span>
                      )}
                    </label>
                  );
                })}
              </div>
            </div>
          ))}

          {effectiveVisibility.wind_probabilities && (
            <div
              data-testid="wind-probability-controls"
              className="rounded-control border border-line bg-surface-inset p-2.5 text-sm text-ink"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label
                  htmlFor="wind-probability-threshold"
                  className="font-semibold text-ink"
                >
                  Wind speed threshold
                </label>
                <select
                  id="wind-probability-threshold"
                  aria-label="Wind speed threshold"
                  value={probThresholdKt}
                  onChange={(e) => {
                    const parsed = Number.parseInt(e.target.value, 10);
                    if (parsed === 34 || parsed === 50 || parsed === 64) {
                      onChangeProbThresholdKt(parsed);
                    }
                  }}
                  className="rounded-control border border-line-strong bg-surface-card px-2 py-1 text-sm text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                >
                  {PROBABILITY_THRESHOLDS.map((kt) => (
                    <option key={kt} value={kt}>
                      {String(kt)} kt
                    </option>
                  ))}
                </select>
              </div>
              <p className="mt-1.5 text-sm text-ink-muted">
                Chance of winds at this speed within 120 hours
              </p>
              {hasWindProbCoverage && (
                <p className="mt-1 text-sm text-ink-subtle">
                  Extract coverage window outlined (dashed border).
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export interface MapLegendPanelProps {
  readonly open: boolean;
  readonly onToggleOpen: (nextOpen: boolean) => void;
  readonly effectiveVisibility: LayerVisibility;
  readonly serverNow?: string | null;
  readonly overlayErrors: {
    readonly radar: boolean;
    readonly satellite: boolean;
  };
  readonly className?: string;
}

export function MapLegendPanel({
  open,
  onToggleOpen,
  effectiveVisibility,
  serverNow,
  overlayErrors,
  className,
}: MapLegendPanelProps) {
  const visibleSections = MAP_LEGEND_SECTIONS.filter((section) =>
    isLayerVisible(effectiveVisibility, section.category),
  );

  return (
    <section
      aria-label="Map legend"
      data-testid="map-legend-panel"
      className={cx(
        "rounded-card border border-line bg-surface-card text-ink shadow-raised",
        className,
      )}
    >
      <h2 className="text-sm font-semibold text-ink">
        <button
          type="button"
          aria-expanded={open}
          aria-controls="map-legend-panel-body"
          onClick={() => onToggleOpen(!open)}
          className="flex min-h-6 w-full items-center justify-between gap-2 rounded-card px-3 py-2 text-left text-sm font-semibold text-ink hover:bg-surface-inset focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          <span className="flex items-center gap-2">
            <Compass className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
            <span>Legend</span>
          </span>
          <ChevronDown
            className={cx(
              "h-4 w-4 shrink-0 text-ink-subtle transition-transform",
              open ? "rotate-180" : "",
            )}
            aria-hidden="true"
          />
        </button>
      </h2>

      {open && (
        <div
          id="map-legend-panel-body"
          className="max-h-[36vh] space-y-1.5 overflow-y-auto border-t border-line px-3 py-2 lg:max-h-[calc(100dvh-15rem)]"
        >
          {serverNow && (
            <span className="block text-caption text-ink-subtle tabular-nums">
              Server clock: {formatUtc(serverNow)} ({formatAgeSeconds(0)})
            </span>
          )}

          {(effectiveVisibility.radar || effectiveVisibility.satellite) && (
            <p
              data-testid="nowcoast-age-note"
              className="text-sm text-ink-muted"
            >
              {NOWCOAST_AGE_NOTE}
            </p>
          )}

          {overlayErrors.radar && effectiveVisibility.radar && (
            <div
              role="status"
              data-testid="radar-unavailable-banner"
              className="rounded-control border border-amber-400 bg-amber-50 px-3 py-1.5 text-sm font-semibold text-amber-950 dark:border-amber-600 dark:bg-amber-950 dark:text-amber-100"
            >
              Radar unavailable
            </div>
          )}

          {overlayErrors.satellite && effectiveVisibility.satellite && (
            <div
              role="status"
              data-testid="satellite-unavailable-banner"
              className="rounded-control border border-amber-400 bg-amber-50 px-3 py-1.5 text-sm font-semibold text-amber-950 dark:border-amber-600 dark:bg-amber-950 dark:text-amber-100"
            >
              Satellite unavailable
            </div>
          )}

          {visibleSections.length === 0 ? (
            <p className="text-sm text-ink-subtle">
              No map layers are currently visible.
            </p>
          ) : (
            <div className="space-y-1.5">
              {visibleSections.map((section) => (
                <div
                  key={section.category}
                  className="rounded-control border border-line bg-surface-inset p-2 text-sm text-ink"
                >
                  <h3 className="text-sm font-semibold text-ink">
                    {section.title}
                  </h3>
                  <ul className="mt-1 space-y-0.5 text-sm text-ink-muted">
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
          )}
        </div>
      )}
    </section>
  );
}
