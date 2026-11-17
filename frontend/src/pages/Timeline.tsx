// frontend/src/pages/Timeline.tsx
import { useQuery } from "@tanstack/react-query";
import { Bell, Clock, Filter } from "lucide-react";
import { useMemo, useState } from "react";
import { ChangeSummary } from "../ai/ChangeSummary.tsx";
import { fetchSummaries, type StoredSummaryResponse } from "../ai/queries.ts";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { ThreatLevelBadge } from "../app/ThreatLevelBadge.tsx";
import {
  type LadderResponse,
  levelLabel,
  ruleSentence,
  useLadder,
} from "../assessment/vocabulary.ts";
import { LevelHistoryChart } from "../charts/LevelHistoryChart.tsx";
import { WindProbabilityChart } from "../charts/WindProbabilityChart.tsx";
import { Card } from "../ui/Card.tsx";
import { Disclosure } from "../ui/Disclosure.tsx";
import { PageHeader } from "../ui/PageHeader.tsx";
import {
  formatAgeSeconds,
  formatBothTimes,
  formatFriendlyLocal,
  formatRouteError,
  formatUtc,
} from "./format.ts";

export type TimelineResponse = components["schemas"]["TimelineResponse"];
export type TimelineEntryResponse =
  components["schemas"]["TimelineEntryResponse"];
export type NotificationsResponse =
  components["schemas"]["NotificationsResponse"];
export type NotificationItemResponse =
  components["schemas"]["NotificationItemResponse"];
export type ChartsResponse = components["schemas"]["ChartsResponse"];

async function fetchTimeline(params?: {
  readonly location?: string;
  readonly before?: string;
}): Promise<TimelineResponse> {
  const query: { location?: string; before?: string } = {};
  if (params?.location !== undefined && params.location !== "") {
    query.location = params.location;
  }
  if (params?.before !== undefined && params.before !== "") {
    query.before = params.before;
  }
  const hasQuery = Object.keys(query).length > 0;
  const { data, response } = hasQuery
    ? await apiClient.GET("/api/timeline", { params: { query } })
    : await apiClient.GET("/api/timeline");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/timeline", response.status);
  }
  return data;
}

async function fetchLocationCharts(location: string): Promise<ChartsResponse> {
  const { data, response } = await apiClient.GET("/api/charts", {
    params: { query: { location } },
  });
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/charts", response.status);
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

function formatRelativeAge(
  iso: string | null | undefined,
  referenceIso: string | null | undefined,
): string | null {
  if (!iso || !referenceIso) {
    return null;
  }
  const targetMs = new Date(iso).getTime();
  const refMs = new Date(referenceIso).getTime();
  if (!Number.isFinite(targetMs) || !Number.isFinite(refMs)) {
    return null;
  }
  const diffSeconds = Math.max(0, Math.round((refMs - targetMs) / 1000));
  return formatAgeSeconds(diffSeconds);
}

export function Timeline() {
  const [selectedLocation, setSelectedLocation] = useState<string>("");
  const [olderPages, setOlderPages] = useState<readonly TimelineResponse[]>([]);
  const [loadingOlder, setLoadingOlder] = useState<boolean>(false);
  const [olderError, setOlderError] = useState<string | null>(null);
  const { ladder } = useLadder();

  const timelineQuery = useQuery({
    queryKey: queryKeys.timeline(),
    queryFn: () => fetchTimeline(),
  });

  const notificationsQuery = useQuery({
    queryKey: queryKeys.notifications(),
    queryFn: fetchNotifications,
  });

  const summariesQuery = useQuery({
    queryKey: queryKeys.aiSummaries(),
    queryFn: fetchSummaries,
  });

  const chartsQuery = useQuery({
    queryKey: queryKeys.charts(selectedLocation),
    queryFn: () => fetchLocationCharts(selectedLocation),
    enabled: selectedLocation !== "",
  });

  const entries = useMemo(() => {
    const base = timelineQuery.data?.entries ?? [];
    if (olderPages.length === 0) {
      return base;
    }
    const merged: TimelineEntryResponse[] = [...base];
    const seen = new Set<string>(
      base.map((item) => `${item.kind}-${String(item.id)}`),
    );
    for (const page of olderPages) {
      for (const item of page.entries) {
        const key = `${item.kind}-${String(item.id)}`;
        if (!seen.has(key)) {
          seen.add(key);
          merged.push(item);
        }
      }
    }
    return merged;
  }, [timelineQuery.data, olderPages]);

  const nextBefore = useMemo(() => {
    if (olderPages.length > 0) {
      const lastPage = olderPages[olderPages.length - 1];
      return lastPage?.next_before ?? null;
    }
    return timelineQuery.data?.next_before ?? null;
  }, [timelineQuery.data, olderPages]);

  async function handleShowOlder() {
    if (nextBefore === null || loadingOlder) {
      return;
    }
    setLoadingOlder(true);
    setOlderError(null);
    try {
      const nextPage = await fetchTimeline({
        before: nextBefore,
      });
      setOlderPages((prev) => [...prev, nextPage]);
    } catch (err) {
      const status = err instanceof ApiRequestError ? err.status : undefined;
      setOlderError(formatRouteError("/api/timeline", status));
    } finally {
      setLoadingOlder(false);
    }
  }

  const notifications = useMemo(
    () => notificationsQuery.data?.notifications ?? [],
    [notificationsQuery.data],
  );

  const summaries = useMemo(() => {
    const byAssessment = new Map<number, StoredSummaryResponse>();
    for (const summary of summariesQuery.data?.summaries ?? []) {
      if (
        summary.assessment_id !== null &&
        !byAssessment.has(summary.assessment_id)
      ) {
        byAssessment.set(summary.assessment_id, summary);
      }
    }
    return byAssessment;
  }, [summariesQuery.data]);

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

  const referenceIso = useMemo(() => {
    const firstEntryAt = entries[0]?.occurred_at ?? null;
    const firstNotifAt = notifications[0]?.created_at ?? null;
    if (firstEntryAt && firstNotifAt) {
      return firstEntryAt >= firstNotifAt ? firstEntryAt : firstNotifAt;
    }
    return firstEntryAt ?? firstNotifAt;
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
      <Card as="section">
        <PageHeader
          title="Timeline"
          summary="Reverse-chronological history of stored assessments, threat-level changes, policy decisions, and channel deliveries."
          actions={
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Filter
                className="h-4 w-4 shrink-0 text-ink-subtle"
                aria-hidden="true"
              />
              <label
                htmlFor="timeline-location-filter"
                className="font-medium text-ink"
              >
                Filter by location
              </label>
              <select
                id="timeline-location-filter"
                aria-label="Filter by location"
                value={selectedLocation}
                onChange={(e) => setSelectedLocation(e.target.value)}
                className="rounded-control border border-line-strong bg-surface-card px-2.5 py-1.5 text-sm text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                <option value="">All locations</option>
                {locationOptions.map((loc) => (
                  <option key={loc} value={loc}>
                    {loc}
                  </option>
                ))}
              </select>
            </div>
          }
        />
      </Card>

      {selectedLocation !== "" ? (
        <div
          className="grid grid-cols-1 gap-4 lg:grid-cols-2"
          data-testid="timeline-location-charts"
        >
          <LevelHistoryChart
            location={selectedLocation}
            timeZone={chartsQuery.data?.time_zone ?? null}
            points={chartsQuery.data?.levels ?? []}
          />
          <WindProbabilityChart
            location={selectedLocation}
            readings={chartsQuery.data?.wind ?? []}
          />
        </div>
      ) : (
        <section
          aria-label="Location charts prompt"
          data-testid="timeline-charts-prompt"
          className="rounded-card border border-dashed border-line-strong bg-surface-inset px-4 py-3 text-sm text-ink-muted"
        >
          Choose a watched location in{" "}
          <strong className="text-ink">Filter by location</strong> above to
          display its stepped threat-level history chart and 34/50/64 kt
          wind-speed probability bands.
        </section>
      )}

      <Card as="section" aria-labelledby="timeline-entries-heading">
        <div className="flex items-center gap-2">
          <Clock
            className="h-5 w-5 shrink-0 text-brand"
            aria-hidden="true"
          />
          <h2
            id="timeline-entries-heading"
            className="text-base font-bold text-ink"
          >
            History ({String(filteredEntries.length)})
          </h2>
        </div>

        {filteredEntries.length === 0 ? (
          <p className="mt-3 text-sm text-ink-muted">
            No timeline entries match the current filter. Stored assessments,
            level changes, and notification decisions will appear here after
            monitor cycles run.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {filteredEntries.map((entry) => (
              <TimelineEntryCard
                key={`${entry.kind}-${String(entry.id)}`}
                entry={entry}
                summary={
                  entry.kind === "assessment"
                    ? (summaries.get(entry.id) ?? null)
                    : null
                }
                referenceIso={referenceIso}
                ladder={ladder}
              />
            ))}
          </div>
        )}

        {olderError !== null && (
          <div
            role="alert"
            className="mt-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
          >
            {olderError}
          </div>
        )}

        {nextBefore !== null && (
          <div className="mt-4 flex justify-center">
            <button
              type="button"
              onClick={() => void handleShowOlder()}
              disabled={loadingOlder}
              data-testid="timeline-show-older"
              className="inline-flex min-h-6 items-center rounded-control border border-line-strong bg-surface-card px-3.5 py-1.5 text-sm font-semibold text-ink hover:bg-surface-inset focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loadingOlder ? "Loading older…" : "Show older"}
            </button>
          </div>
        )}
      </Card>

      <Card as="section" aria-labelledby="notifications-log-heading">
        <div className="flex items-center gap-2">
          <Bell
            className="h-5 w-5 shrink-0 text-brand"
            aria-hidden="true"
          />
          <h2
            id="notifications-log-heading"
            className="text-base font-bold text-ink"
          >
            Notification Log ({String(filteredNotifications.length)})
          </h2>
        </div>

        {filteredNotifications.length === 0 ? (
          <p className="mt-3 text-sm text-ink-muted">
            No stored notifications match the current filter. When a watched
            location&apos;s threat level escalates, settles after quiet hours,
            or a test notification is sent, its policy decisions and channel
            delivery outcomes will appear here.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            {filteredNotifications.map((notif) => (
              <NotificationLogCard
                key={notif.id}
                item={notif}
                referenceIso={referenceIso}
                ladder={ladder}
              />
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function TimelineEntryCard({
  entry,
  summary,
  referenceIso,
  ladder,
}: {
  readonly entry: TimelineEntryResponse;
  readonly summary: StoredSummaryResponse | null;
  readonly referenceIso: string | null;
  readonly ladder: LadderResponse;
}) {
  const ageText = formatRelativeAge(entry.occurred_at, referenceIso);
  const friendlyLocal =
    formatFriendlyLocal(entry.occurred_at, entry.time_zone) ??
    formatUtc(entry.occurred_at);

  if (entry.kind === "assessment") {
    const levelNum = entry.level?.number;
    const engineLabel =
      levelNum !== undefined
        ? levelLabel(levelNum, ladder) || entry.level?.label
        : undefined;
    const sentence =
      entry.rule_trigger ||
      (entry.rule ? ruleSentence(entry.rule, ladder) : "");

    return (
      <article
        aria-label={`Assessment ${String(entry.id)} for ${entry.location ?? "unknown"}`}
        className="space-y-2.5 rounded-card border border-line bg-surface-inset p-3.5 text-sm"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-bold text-ink">
              {entry.location ?? "Unknown location"}
            </span>
            {entry.level && (
              <ThreatLevelBadge
                level={entry.level.number}
                label={engineLabel}
                atLeast={entry.complete === false}
                size="sm"
              />
            )}
          </div>
          <span className="text-caption tabular-nums text-ink-subtle">
            {ageText ? `${ageText} · ` : ""}
            {friendlyLocal}
          </span>
        </div>

        <div className="space-y-1 text-ink-muted">
          {sentence && <p className="font-medium text-ink">{sentence}</p>}
          {entry.changes.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-4">
              {entry.changes.map((chg, idx) => (
                <li
                  key={`${chg.kind}-${String(idx)}`}
                  className="max-w-measure"
                >
                  {chg.detail}
                </li>
              ))}
            </ul>
          )}
        </div>

        {summary && <ChangeSummary summary={summary} />}

        <Disclosure summary="Rule ID & official timestamps">
          <div className="space-y-1 text-ink-muted">
            {entry.rule && (
              <p>
                Decided by{" "}
                <code className="rounded bg-surface-inset px-1 py-0.5 font-mono text-ink">
                  {entry.rule}
                </code>
                {entry.rule_trigger ? `: ${entry.rule_trigger}` : ""}
              </p>
            )}
            <p className="text-ink-subtle">
              Occurred: {formatBothTimes(entry.occurred_at, entry.time_zone)}
            </p>
          </div>
        </Disclosure>
      </article>
    );
  }

  const notifLevelNum = entry.level?.number;
  const notifLabel =
    notifLevelNum !== undefined
      ? levelLabel(notifLevelNum, ladder) || entry.level?.label
      : undefined;

  return (
    <article
      aria-label={`Notification ${String(entry.id)}`}
      className="space-y-2.5 rounded-card border border-amber-300 bg-amber-50/50 p-3.5 text-sm dark:border-amber-800/70 dark:bg-amber-950/20"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {entry.location && (
            <span className="font-bold text-ink">{entry.location}</span>
          )}
          {entry.level && (
            <ThreatLevelBadge
              level={entry.level.number}
              label={notifLabel}
              size="sm"
            />
          )}
        </div>
        <span className="text-caption tabular-nums text-ink-subtle">
          {ageText ? `${ageText} · ` : ""}
          {friendlyLocal}
        </span>
      </div>

      {entry.title && <p className="font-semibold text-ink">{entry.title}</p>}
      {entry.body.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-4 text-ink-muted">
          {entry.body.map((line, idx) => (
            <li key={idx} className="max-w-measure">
              {line}
            </li>
          ))}
        </ul>
      )}

      <Disclosure summary="Notification kind & timestamps">
        <div className="space-y-1 text-ink-muted">
          <p>
            Kind:{" "}
            <strong className="text-ink">
              Notification ({entry.notification_kind ?? "event"})
            </strong>
          </p>
          <p className="text-ink-subtle">
            Occurred: {formatBothTimes(entry.occurred_at, entry.time_zone)}
          </p>
        </div>
      </Disclosure>
    </article>
  );
}

function NotificationLogCard({
  item,
  referenceIso,
  ladder,
}: {
  readonly item: NotificationItemResponse;
  readonly referenceIso: string | null;
  readonly ladder: LadderResponse;
}) {
  const ageText = formatRelativeAge(item.created_at, referenceIso);
  const friendlyLocal =
    formatFriendlyLocal(item.created_at, item.time_zone) ??
    formatUtc(item.created_at);

  return (
    <article
      aria-label={`Notification log ${String(item.id)}: ${item.title}`}
      className="space-y-2.5 rounded-card border border-line bg-surface-inset p-3.5 text-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-bold text-ink">{item.title}</span>
          {item.level !== null && item.level !== undefined && (
            <ThreatLevelBadge
              level={item.level}
              label={levelLabel(item.level, ladder)}
              size="sm"
            />
          )}
        </div>
        <span className="text-caption tabular-nums text-ink-subtle">
          {ageText ? `${ageText} · ` : ""}
          {friendlyLocal}
        </span>
      </div>

      {item.body.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-4 text-ink-muted">
          {item.body.map((line, idx) => (
            <li key={idx} className="max-w-measure">
              {line}
            </li>
          ))}
        </ul>
      )}

      <Disclosure summary="Policy decisions, channel deliveries & timestamps">
        <div className="space-y-2.5 text-ink-muted">
          <p>
            Kind: <strong className="text-ink">{item.kind}</strong> · Created:{" "}
            {formatBothTimes(item.created_at, item.time_zone)}
          </p>

          {item.decisions.length > 0 && (
            <div>
              <p className="font-semibold text-ink">Policy decisions</p>
              <ul className="mt-1 space-y-0.5">
                {item.decisions.map((dec) => (
                  <li key={dec.id}>
                    Trigger <code className="font-mono text-ink">{dec.trigger}</code> →{" "}
                    <strong className="text-ink">{dec.decision}</strong>
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
            <div>
              <p className="font-semibold text-ink">Channel deliveries</p>
              <div className="mt-1 flex flex-wrap gap-2">
                {item.deliveries.map((deliv) => (
                  <span
                    key={deliv.id}
                    data-delivery-result={deliv.result}
                    className={
                      deliv.result === "muted"
                        ? "inline-flex items-center gap-1 rounded border border-slate-200 bg-slate-100 px-2 py-0.5 text-slate-600 dark:border-slate-700 dark:bg-slate-800/70 dark:text-slate-300"
                        : "inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2 py-0.5 text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
                    }
                  >
                    <strong>{deliv.channel}:</strong> {deliv.result}
                    {deliv.detail ? ` (${deliv.detail})` : ""} ·{" "}
                    {formatUtc(deliv.attempted_at)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </Disclosure>
    </article>
  );
}
