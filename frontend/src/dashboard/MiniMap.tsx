// frontend/src/dashboard/MiniMap.tsx
import { useQuery } from "@tanstack/react-query";
import { Map as MapIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import { type LayerVisibility, type MapResponse } from "../map/layers.ts";
import { useLeafletMap } from "../map/useLeafletMap.ts";
import { formatAgeSeconds } from "../pages/format.ts";
import { Card } from "../ui/Card.tsx";

export const MINI_MAP_VISIBILITY: LayerVisibility = {
  cone: true,
  track: true,
  points: true,
  watches_warnings: true,
  outlook: false,
  locations: true,
  wind_radii: false,
  past_track: false,
  peak_surge: false,
  wind_probabilities: false,
  radar: false,
  satellite: false,
};

async function fetchMap(): Promise<MapResponse> {
  const { data, response } = await apiClient.GET("/api/map");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/map", response.status);
  }
  return data;
}

export interface MiniMapProps {
  readonly ageSeconds: number | null;
  readonly timeZone?: string | null;
  readonly statusNote?: ReactNode;
}

export function MiniMap({
  ageSeconds,
  timeZone = null,
  statusNote,
}: MiniMapProps) {
  const mapQuery = useQuery({
    queryKey: queryKeys.map(),
    queryFn: fetchMap,
  });

  const { containerRef } = useLeafletMap({
    mapData: mapQuery.data,
    visibility: MINI_MAP_VISIBILITY,
    timeZone,
    viewModeKey: "dashboard-mini-map",
  });

  const stormCount = mapQuery.data?.storms.length ?? 0;
  const stormWords =
    stormCount === 1
      ? "1 active storm"
      : `${String(stormCount)} active storms`;
  const ageWords =
    ageSeconds !== null
      ? `Snapshot ${formatAgeSeconds(ageSeconds)}`
      : "No snapshot stored yet";

  return (
    <div className="space-y-3" data-testid="dashboard-mini-map-column">
      <Card
        as="section"
        aria-label="Live situation mini-map"
        padding="sm"
        data-testid="dashboard-mini-map"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="inline-flex items-center gap-1.5 text-base font-bold text-ink">
            <MapIcon className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
            <span>Live situation map</span>
          </h2>
          <Link
            to="/map"
            className="rounded-control text-sm font-semibold text-brand underline underline-offset-2 hover:text-brand-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            Open the map
          </Link>
        </div>

        <span
          data-testid="mini-map-caption"
          className="mt-1 block text-caption tabular-nums text-ink-subtle"
        >
          {stormWords} · {ageWords}
        </span>

        <div
          ref={containerRef}
          data-testid="mini-map-container"
          className="relative isolate mt-2.5 h-56 w-full overflow-hidden rounded-control border border-line sm:h-72"
        />
      </Card>

      {statusNote !== undefined && statusNote !== null && (
        <div className="hidden xl:block">{statusNote}</div>
      )}
    </div>
  );
}
