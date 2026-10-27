// frontend/src/pages/Timeline.tsx
import { useQuery } from "@tanstack/react-query";
import { Bell, Clock, Filter } from "lucide-react";
import { useMemo, useState } from "react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { ThreatLevelBadge } from "../app/ThreatLevelBadge.tsx";
import { formatBothTimes, formatRouteError, formatUtc } from "./format.ts";

export type TimelineResponse = components["schemas"]["TimelineResponse"];
export type TimelineEntryResponse =
  components["schemas"]["TimelineEntryResponse"];
export type NotificationsResponse =
  components["schemas"]["NotificationsResponse"];
export type NotificationItemResponse =
  components["schemas"]["NotificationItemResponse"];

async function fetchTimeline(): Promise<TimelineResponse> {
  const { data, response } = await apiClient.GET("/api/timeline");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/timeline", response.status);
  }
  return data;
}

async function fetchNotifications(): Promise<NotificationsResponse> {
  const { data, response } = await apiClient.GET("/api/notifications");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/notifications", response.status);
  }
  return data;
}

export function Timeline() {
  const [selectedLocation, setSelectedLocation] = useState<string>("");

  const timelineQuery = useQuery({
    queryKey: queryKeys.timeline(),
    queryFn: fetchTimeline,
  });

  const notificationsQuery = useQuery({
    queryKey: queryKeys.notifications(),
    queryFn: fetchNotifications,
  });

  const entries = useMemo(
    () => timelineQuery.data?.entries ?? [],
    [timelineQuery.data],
  );
  const notifications = useMemo(
    () => notificationsQuery.data?.notifications ?? [],
    [notificationsQuery.data],
  );

  const locationOptions = useMemo(() => {
    const names = new Set<string>();
    for (const entry of entries) {
      if (entry.location) {
        names.add(entry.location);
      }
    }
    for (const notif of notifications) {
      if (notif.location) {
        names.add(notif.location);
      }
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [entries, notifications]);

  if (timelineQuery.isError) {
    const status =
      timelineQuery.error instanceof ApiRequestError
        ? timelineQuery.error.status
        : undefined;
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
      >
        {formatRouteError("/api/timeline", status)}
      </div>
    );
  }

  if (notificationsQuery.isError) {
    const status =
      notificationsQuery.error instanceof ApiRequestError
        ? notificationsQuery.error.status
        : undefined;
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
      >
        {formatRouteError("/api/notifications", status)}
      </div>
    );
  }

  if (timelineQuery.isLoading || notificationsQuery.isLoading) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
        Loading assessment history and notifications…
      </div>
    );
  }

  const filteredEntries = selectedLocation
    ? entries.filter((e) => e.location === selectedLocation)
    : entries;

  const filteredNotifications = selectedLocation
    ? notifications.filter((n) => n.location === selectedLocation)
    : notifications;

  return (
    <div className="space-y-5">
      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div>
            <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              Timeline
            </h1>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
              Reverse-chronological history of stored assessments, change
              events, policy decisions, and channel deliveries.
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs">
            <Filter
              className="h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400"
              aria-hidden="true"
            />
            <label
              htmlFor="timeline-location-filter"
              className="font-medium text-slate-700 dark:text-slate-300"
            >
              Filter by location
            </label>
            <select
              id="timeline-location-filter"
              aria-label="Filter by location"
              value={selectedLocation}
              onChange={(e) => setSelectedLocation(e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="">All locations</option>
              {locationOptions.map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <section
        aria-labelledby="timeline-entries-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center gap-2">
          <Clock
            className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <h2
            id="timeline-entries-heading"
            className="text-base font-bold text-slate-900 dark:text-slate-100"
          >
            History ({String(filteredEntries.length)})
          </h2>
        </div>

        {filteredEntries.length === 0 ? (
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
            No timeline entries match the current filter.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {filteredEntries.map((entry) => (
              <TimelineEntryCard
                key={`${entry.kind}-${String(entry.id)}`}
                entry={entry}
              />
            ))}
          </div>
        )}
      </section>

      <section
        aria-labelledby="notifications-log-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center gap-2">
          <Bell
            className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <h2
            id="notifications-log-heading"
            className="text-base font-bold text-slate-900 dark:text-slate-100"
          >
            Notification Log ({String(filteredNotifications.length)})
          </h2>
        </div>

        {filteredNotifications.length === 0 ? (
          <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
            No stored notifications match the current filter.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {filteredNotifications.map((notif) => (
              <NotificationLogCard key={notif.id} item={notif} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function TimelineEntryCard({
  entry,
}: {
  readonly entry: TimelineEntryResponse;
}) {
  if (entry.kind === "assessment") {
    return (
      <article
        aria-label={`Assessment ${String(entry.id)} for ${entry.location ?? "unknown"}`}
        className="rounded-md border border-slate-200 bg-slate-50/70 p-3.5 text-xs dark:border-slate-800 dark:bg-slate-800/40"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded bg-sky-100 px-2 py-0.5 font-semibold text-sky-900 dark:bg-sky-950/70 dark:text-sky-200">
              Assessment
            </span>
            <span className="font-bold text-slate-900 dark:text-slate-100">
              {entry.location ?? "Unknown location"}
            </span>
            {entry.level && (
              <ThreatLevelBadge
                level={entry.level.number}
                atLeast={entry.complete === false}
                size="sm"
              />
            )}
          </div>
          <span className="text-slate-600 dark:text-slate-400">
            {formatBothTimes(entry.occurred_at, entry.time_zone)}
          </span>
        </div>

        <div className="mt-2 space-y-1 text-slate-700 dark:text-slate-300">
          {entry.rule && (
            <p>
              Decided by{" "}
              <code className="rounded bg-slate-200/80 px-1 py-0.5 font-mono dark:bg-slate-700">
                {entry.rule}
              </code>
              {entry.rule_trigger ? `: ${entry.rule_trigger}` : ""}
            </p>
          )}
          {entry.changes.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-4">
              {entry.changes.map((chg, idx) => (
                <li key={`${chg.kind}-${String(idx)}`}>{chg.detail}</li>
              ))}
            </ul>
          )}
        </div>
      </article>
    );
  }

  return (
    <article
      aria-label={`Notification ${String(entry.id)}`}
      className="rounded-md border border-amber-200 bg-amber-50/50 p-3.5 text-xs dark:border-amber-900/60 dark:bg-amber-950/20"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded bg-amber-200/80 px-2 py-0.5 font-semibold text-amber-950 dark:bg-amber-900/70 dark:text-amber-100">
            Notification ({entry.notification_kind ?? "event"})
          </span>
          {entry.location && (
            <span className="font-bold text-slate-900 dark:text-slate-100">
              {entry.location}
            </span>
          )}
          {entry.level && (
            <ThreatLevelBadge level={entry.level.number} size="sm" />
          )}
        </div>
        <span className="text-slate-600 dark:text-slate-400">
          {formatBothTimes(entry.occurred_at, entry.time_zone)}
        </span>
      </div>

      {entry.title && (
        <p className="mt-2 font-semibold text-slate-900 dark:text-slate-100">
          {entry.title}
        </p>
      )}
      {entry.body.length > 0 && (
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-slate-700 dark:text-slate-300">
          {entry.body.map((line, idx) => (
            <li key={idx}>{line}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

function NotificationLogCard({
  item,
}: {
  readonly item: NotificationItemResponse;
}) {
  return (
    <article
      aria-label={`Notification log ${String(item.id)}: ${item.title}`}
      className="rounded-md border border-slate-200 bg-slate-50/70 p-3.5 text-xs dark:border-slate-800 dark:bg-slate-800/40"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-bold text-slate-900 dark:text-slate-100">
            {item.title}
          </span>
          <span className="rounded bg-slate-200 px-2 py-0.5 font-medium text-slate-800 dark:bg-slate-700 dark:text-slate-200">
            {item.kind}
          </span>
          {item.level !== null && item.level !== undefined && (
            <ThreatLevelBadge level={item.level} size="sm" />
          )}
        </div>
        <span className="text-slate-600 dark:text-slate-400">
          {formatBothTimes(item.created_at, item.time_zone)}
        </span>
      </div>

      {item.body.length > 0 && (
        <ul className="mt-2 list-disc space-y-0.5 pl-4 text-slate-700 dark:text-slate-300">
          {item.body.map((line, idx) => (
            <li key={idx}>{line}</li>
          ))}
        </ul>
      )}

      {item.decisions.length > 0 && (
        <div className="mt-2.5 border-t border-slate-200 pt-2 dark:border-slate-700">
          <p className="font-semibold text-slate-800 dark:text-slate-200">
            Policy decisions
          </p>
          <ul className="mt-1 space-y-0.5 text-slate-600 dark:text-slate-300">
            {item.decisions.map((dec) => (
              <li key={dec.id}>
                Trigger <code>{dec.trigger}</code> →{" "}
                <strong>{dec.decision}</strong>
                {dec.level_after !== null && dec.level_after !== undefined
                  ? ` (level ${String(dec.level_after)})`
                  : ""}
                {dec.event_key ? ` [${dec.event_key}]` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      {item.deliveries.length > 0 && (
        <div className="mt-2.5 border-t border-slate-200 pt-2 dark:border-slate-700">
          <p className="font-semibold text-slate-800 dark:text-slate-200">
            Channel deliveries
          </p>
          <div className="mt-1 flex flex-wrap gap-2">
            {item.deliveries.map((deliv) => (
              <span
                key={deliv.id}
                className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2 py-0.5 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
              >
                <strong>{deliv.channel}:</strong> {deliv.result}
                {deliv.detail ? ` (${deliv.detail})` : ""} ·{" "}
                {formatUtc(deliv.attempted_at)}
              </span>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}
