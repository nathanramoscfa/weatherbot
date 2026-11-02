// frontend/src/pages/OutlookGraphics.tsx
import { useQuery } from "@tanstack/react-query";
import { basinName, horizonName } from "../ai/format.ts";
import { NarrationPanel } from "../ai/NarrationPanel.tsx";
import {
  fetchNarrations,
  fetchOutlook,
  type OutlookGraphicResponse,
} from "../ai/queries.ts";
import { useAiStatus } from "../ai/useAiStatus.ts";
import { ApiRequestError } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import { formatRouteError, formatUtc } from "./format.ts";

export function outlookAlt(graphic: OutlookGraphicResponse): string {
  return `National Hurricane Center official ${horizonName(graphic.horizon)} graphical tropical weather outlook for the ${basinName(graphic.basin)}`;
}

export function OutlookGraphics() {
  const outlookQuery = useQuery({
    queryKey: queryKeys.outlook(),
    queryFn: fetchOutlook,
  });
  const snapshotId = outlookQuery.data?.snapshot_id ?? null;
  const narrationsQuery = useQuery({
    queryKey: queryKeys.aiNarrations(snapshotId),
    queryFn: fetchNarrations,
    enabled: outlookQuery.isSuccess,
  });
  const status = useAiStatus();

  if (outlookQuery.isError) {
    return (
      <p role="alert" className="mt-3 text-xs text-red-800 dark:text-red-300">
        {formatRouteError(
          "/api/outlook",
          outlookQuery.error instanceof ApiRequestError
            ? outlookQuery.error.status
            : undefined,
        )}
      </p>
    );
  }

  const graphics = outlookQuery.data?.graphics ?? [];
  if (graphics.length === 0) {
    return outlookQuery.isLoading ? null : (
      <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
        No official outlook graphic is stored with the latest snapshot.
      </p>
    );
  }

  const narrations = narrationsQuery.data;
  const narrationOn = narrations?.enabled === true;

  return (
    <div className="mt-4 space-y-2">
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
        Official outlook graphics
      </h3>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {graphics.map((graphic) => {
          const stored =
            narrations?.narrations.find(
              (item) => item.graphic_sha256 === graphic.sha256,
            ) ?? null;
          return (
            <figure
              key={`${graphic.basin}-${graphic.horizon}`}
              className="space-y-2 rounded-md border border-slate-200 bg-slate-50/70 p-2.5 text-xs dark:border-slate-800 dark:bg-slate-800/40"
            >
              <img
                key={graphic.sha256}
                src={`/api/outlook/${graphic.basin}/${graphic.horizon}`}
                alt={outlookAlt(graphic)}
                width={graphic.width_px}
                height={graphic.height_px}
                loading="lazy"
                className="h-auto w-full rounded border border-slate-200 bg-white dark:border-slate-700"
              />
              <figcaption className="text-slate-600 dark:text-slate-300">
                <span className="font-semibold text-slate-900 dark:text-slate-100">
                  {basinName(graphic.basin)} · {horizonName(graphic.horizon)}{" "}
                  outlook
                </span>{" "}
                · Official graphic: National Hurricane Center · fetched{" "}
                {formatUtc(graphic.fetched_at)}
                {graphic.issued_at
                  ? ` · issued ${formatUtc(graphic.issued_at)}`
                  : ""}
              </figcaption>
              {narrationOn ? (
                <NarrationPanel
                  basin={graphic.basin}
                  horizon={graphic.horizon}
                  label={narrations.label}
                  stored={stored}
                  ai={status.data}
                />
              ) : null}
            </figure>
          );
        })}
      </div>
    </div>
  );
}
