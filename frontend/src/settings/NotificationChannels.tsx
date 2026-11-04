// frontend/src/settings/NotificationChannels.tsx
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { useState } from "react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import {
  type BrowserNotificationPermission,
  getBrowserNotificationPermission,
  readBrowserNotificationsEnabled,
  requestBrowserNotificationPermission,
  writeBrowserNotificationsEnabled,
} from "../notifications/notify.ts";
import { formatBothTimes, formatRouteError } from "../pages/format.ts";

export type NotificationChannelsResponse =
  components["schemas"]["NotificationChannelsResponse"];
export type NotificationChannelStatusResponse =
  components["schemas"]["NotificationChannelStatusResponse"];

async function fetchNotificationChannels(): Promise<NotificationChannelsResponse> {
  const { data, response } = await apiClient.GET("/api/notifications/channels");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/notifications/channels", response.status);
  }
  return data;
}

function stateBadgeClass(
  state: NotificationChannelStatusResponse["state"],
): string {
  switch (state) {
    case "on":
      return "bg-emerald-100 text-emerald-900 dark:bg-emerald-950/70 dark:text-emerald-200";
    case "unconfigured":
      return "bg-amber-100 text-amber-900 dark:bg-amber-950/70 dark:text-amber-200";
    case "off":
      return "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300";
  }
}

export function NotificationChannels() {
  const queryClient = useQueryClient();

  const [browserNotifEnabled, setBrowserNotifEnabled] = useState<boolean>(() =>
    readBrowserNotificationsEnabled(),
  );
  const [browserPermission, setBrowserPermission] =
    useState<BrowserNotificationPermission>(() =>
      getBrowserNotificationPermission(),
    );

  const [testNotifSubmitting, setTestNotifSubmitting] = useState(false);
  const [testNotifFeedback, setTestNotifFeedback] = useState<{
    kind: "success" | "error";
    text: string;
  } | null>(null);

  const channelsQuery = useQuery({
    queryKey: queryKeys.notificationChannels(),
    queryFn: fetchNotificationChannels,
  });

  const handleToggleBrowserNotifications = async () => {
    const next = !browserNotifEnabled;
    writeBrowserNotificationsEnabled(next);
    setBrowserNotifEnabled(next);
    if (next) {
      const perm = await requestBrowserNotificationPermission();
      setBrowserPermission(perm);
    } else {
      setBrowserPermission(getBrowserNotificationPermission());
    }
  };

  const handleSendTestNotification = async () => {
    setTestNotifSubmitting(true);
    setTestNotifFeedback(null);
    try {
      const { data, response } = await apiClient.POST(
        "/api/notifications/test",
        { body: {} },
      );
      if (response.ok && data) {
        const summary = data.deliveries
          .map((d) => `${d.channel}: ${d.result}`)
          .join(", ");
        setTestNotifFeedback({
          kind: "success",
          text: `Test notification sent (${summary}).`,
        });
        await Promise.all([
          queryClient.invalidateQueries({
            queryKey: queryKeys.notifications(),
          }),
          queryClient.invalidateQueries({
            queryKey: queryKeys.notificationChannels(),
          }),
          queryClient.invalidateQueries({ queryKey: queryKeys.timeline() }),
        ]);
        return;
      }
      if (response.status === 429) {
        setTestNotifFeedback({
          kind: "error",
          text: "Please wait before sending another test notification (/api/notifications/test returned HTTP 429).",
        });
      } else {
        setTestNotifFeedback({
          kind: "error",
          text: formatRouteError("/api/notifications/test", response.status),
        });
      }
    } catch {
      setTestNotifFeedback({
        kind: "error",
        text: formatRouteError("/api/notifications/test"),
      });
    } finally {
      setTestNotifSubmitting(false);
    }
  };

  const channels = channelsQuery.data?.channels ?? [];

  return (
    <section
      aria-labelledby="notifications-settings-heading"
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex items-center gap-2">
        <Bell
          className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
          aria-hidden="true"
        />
        <h2
          id="notifications-settings-heading"
          className="text-base font-bold text-slate-900 dark:text-slate-100"
        >
          Notification Channels
        </h2>
      </div>

      {channels.length > 0 && (
        <div
          aria-label="Configured notification channels"
          className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2"
        >
          {channels.map((ch) => (
            <div
              key={ch.name}
              data-testid={`channel-card-${ch.name}`}
              className="rounded-md border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-800/40"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono font-bold text-slate-900 dark:text-slate-100">
                  {ch.name}
                </span>
                <span
                  className={`rounded px-2 py-0.5 text-[11px] font-semibold ${stateBadgeClass(ch.state)}`}
                >
                  {ch.state}
                </span>
              </div>
              <p className="mt-1 text-slate-600 dark:text-slate-300">
                {ch.detail}
              </p>
              <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                {ch.last_result && ch.last_attempted_at
                  ? `Last delivery: ${ch.last_result} · ${formatBothTimes(ch.last_attempted_at)}`
                  : "Last delivery: none recorded yet"}
              </p>
            </div>
          ))}
        </div>
      )}

      <div className="mt-4 flex flex-col justify-between gap-4 border-t border-slate-200 pt-3 sm:flex-row sm:items-center dark:border-slate-800">
        <div className="space-y-1 text-xs">
          <p className="font-semibold text-slate-900 dark:text-slate-100">
            Background Web Notifications:{" "}
            <span>{browserNotifEnabled ? "On" : "Off"}</span> (Permission:{" "}
            <code>{browserPermission}</code>)
          </p>
          <p className="text-slate-600 dark:text-slate-300">
            In-page notification toasts always appear when a notification event
            arrives while this dashboard is open. Turning this switch on also
            fires a system Web Notification when the tab is hidden.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            role="switch"
            aria-checked={browserNotifEnabled}
            aria-label="Browser notifications"
            onClick={() => void handleToggleBrowserNotifications()}
            className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 ${
              browserNotifEnabled
                ? "bg-sky-600 text-white hover:bg-sky-700 dark:bg-sky-500 dark:text-slate-950"
                : "border border-slate-300 bg-white text-slate-800 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            }`}
          >
            {browserNotifEnabled
              ? "Disable browser notifications"
              : "Enable browser notifications"}
          </button>

          <button
            type="button"
            disabled={testNotifSubmitting}
            onClick={() => void handleSendTestNotification()}
            className="rounded-md border border-slate-300 bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
          >
            Send test notification
          </button>
        </div>
      </div>

      {testNotifFeedback && (
        <div
          role={testNotifFeedback.kind === "error" ? "alert" : "status"}
          className={`mt-3 rounded-md border px-3 py-2 text-xs ${
            testNotifFeedback.kind === "error"
              ? "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
              : "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200"
          }`}
        >
          {testNotifFeedback.text}
        </div>
      )}
    </section>
  );
}
