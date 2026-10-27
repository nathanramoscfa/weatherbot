// frontend/src/pages/Settings.tsx
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bell,
  BookOpen,
  FileText,
  MapPin,
  Sliders,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { ThreatLevelBadge } from "../app/ThreatLevelBadge.tsx";
import {
  type BrowserNotificationPermission,
  getBrowserNotificationPermission,
  readBrowserNotificationsEnabled,
  requestBrowserNotificationPermission,
  writeBrowserNotificationsEnabled,
} from "../notifications/notify.ts";
import {
  formatBothTimes,
  formatBreakpointSpan,
  formatRouteError,
} from "./format.ts";

export type SettingsResponse = components["schemas"]["SettingsResponse"];
export type DisclaimerResponse = components["schemas"]["DisclaimerResponse"];
export type LocationsResponse = components["schemas"]["LocationsResponse"];
export type PolygonKind = "county" | "forecast";

export interface BundledLicenseEntry {
  readonly name: string;
  readonly version?: string;
  readonly license?: string;
}

const LADDER_RULES: ReadonlyArray<{
  readonly order: number;
  readonly id: string;
  readonly level: number;
  readonly trigger: string;
}> = [
  {
    order: 1,
    id: "hurricane_warning",
    level: 5,
    trigger:
      "A covering NWS Hurricane Warning or Extreme Wind Warning, or a covering NHC Hurricane Warning segment (HWR).",
  },
  {
    order: 2,
    id: "evacuation_order",
    level: 4,
    trigger: "The operator's evacuation-order toggle is on.",
  },
  {
    order: 3,
    id: "hurricane_watch",
    level: 4,
    trigger:
      "A covering NWS Hurricane Watch, or a covering NHC Hurricane Watch segment (HWA).",
  },
  {
    order: 4,
    id: "tropical_storm_warning",
    level: 4,
    trigger:
      "A covering NWS Tropical Storm Warning or Storm Surge Warning, or a covering NHC Tropical Storm Warning segment (TRW).",
  },
  {
    order: 5,
    id: "tropical_storm_watch",
    level: 3,
    trigger:
      "A covering NWS Tropical Storm Watch or Storm Surge Watch, or a covering NHC Tropical Storm Watch segment (TRA).",
  },
  {
    order: 6,
    id: "hurricane_cone",
    level: 3,
    trigger:
      "Inside an active storm's forecast cone within the cone horizon while the forecast track reaches hurricane intensity by closest approach.",
  },
  {
    order: 7,
    id: "hurricane_wind_probability",
    level: 3,
    trigger:
      "64-kt (hurricane) 5 km wind-speed probability band meets or exceeds hurricane_wind_floor_pct.",
  },
  {
    order: 8,
    id: "tropical_storm_cone",
    level: 2,
    trigger:
      "Inside an active storm's forecast cone within the cone horizon (below hurricane intensity by closest approach).",
  },
  {
    order: 9,
    id: "tropical_storm_wind_probability",
    level: 2,
    trigger:
      "34-kt or 50-kt 5 km wind-speed probability band meets or exceeds tropical_storm_wind_floor_pct.",
  },
  {
    order: 10,
    id: "development_region",
    level: 2,
    trigger:
      "Inside a 7-day graphical Tropical Weather Outlook development region meeting development_chance_floor_pct.",
  },
  {
    order: 11,
    id: "all_clear",
    level: 1,
    trigger: "No other rule matches.",
  },
];

async function fetchSettings(): Promise<SettingsResponse> {
  const { data, response } = await apiClient.GET("/api/settings");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/settings", response.status);
  }
  return data;
}

async function fetchDisclaimer(): Promise<DisclaimerResponse> {
  const { data, response } = await apiClient.GET("/api/disclaimer");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/disclaimer", response.status);
  }
  return data;
}

async function fetchLocations(): Promise<LocationsResponse> {
  const { data, response } = await apiClient.GET("/api/locations");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/locations", response.status);
  }
  return data;
}

async function fetchLicenses(): Promise<BundledLicenseEntry[]> {
  try {
    const response = await fetch("/licenses.json", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return [];
    }
    const raw: unknown = await response.json();
    if (!Array.isArray(raw)) {
      return [];
    }
    return raw.filter(
      (item): item is BundledLicenseEntry =>
        typeof item === "object" &&
        item !== null &&
        typeof (item as Record<string, unknown>).name === "string",
    );
  } catch {
    return [];
  }
}

export interface SettingsProps {
  readonly initialLicenses?: BundledLicenseEntry[];
}

export function Settings({ initialLicenses }: SettingsProps = {}) {
  const queryClient = useQueryClient();

  const [browserNotifEnabled, setBrowserNotifEnabled] = useState<boolean>(() =>
    readBrowserNotificationsEnabled(),
  );
  const [browserPermission, setBrowserPermission] =
    useState<BrowserNotificationPermission>(() =>
      getBrowserNotificationPermission(),
    );

  const [locName, setLocName] = useState("");
  const [locLat, setLocLat] = useState("");
  const [locLon, setLocLon] = useState("");
  const [locPolygon, setLocPolygon] = useState<"" | PolygonKind>("");
  const [locSubmitting, setLocSubmitting] = useState(false);
  const [locFeedback, setLocFeedback] = useState<{
    kind: "success" | "error";
    text: string;
  } | null>(null);

  const [testNotifSubmitting, setTestNotifSubmitting] = useState(false);
  const [testNotifFeedback, setTestNotifFeedback] = useState<{
    kind: "success" | "error";
    text: string;
  } | null>(null);

  const settingsQuery = useQuery({
    queryKey: queryKeys.settings(),
    queryFn: fetchSettings,
  });

  const disclaimerQuery = useQuery({
    queryKey: queryKeys.disclaimer(),
    queryFn: fetchDisclaimer,
  });

  const locationsQuery = useQuery({
    queryKey: queryKeys.locations(),
    queryFn: fetchLocations,
  });

  const licensesQuery = useQuery({
    queryKey: queryKeys.licenses(),
    queryFn: fetchLicenses,
    ...(initialLicenses !== undefined ? { initialData: initialLicenses } : {}),
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

  const handleAddLocation = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLocFeedback(null);

    const trimmedName = locName.trim();
    const latNum = Number(locLat);
    const lonNum = Number(locLon);

    if (
      !trimmedName ||
      locLat.trim() === "" ||
      locLon.trim() === "" ||
      !Number.isFinite(latNum) ||
      !Number.isFinite(lonNum)
    ) {
      setLocFeedback({
        kind: "error",
        text: "Enter a location name and valid decimal latitude and longitude.",
      });
      return;
    }

    setLocSubmitting(true);
    try {
      const { data, response } = await apiClient.POST("/api/locations", {
        body: {
          name: trimmedName,
          latitude: latNum,
          longitude: lonNum,
          polygon: locPolygon === "" ? null : locPolygon,
        },
      });

      if (response.status === 201 && data) {
        setLocName("");
        setLocLat("");
        setLocLon("");
        setLocPolygon("");
        setLocFeedback({
          kind: "success",
          text: `Added location "${data.name}".`,
        });
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: queryKeys.locations() }),
          queryClient.invalidateQueries({ queryKey: queryKeys.assessments() }),
        ]);
        return;
      }

      if (response.status === 409) {
        setLocFeedback({
          kind: "error",
          text: "A location with that name already exists (/api/locations returned HTTP 409).",
        });
      } else if (response.status === 422) {
        setLocFeedback({
          kind: "error",
          text: "Invalid location parameters or zone polygon requested outside NWS coverage (/api/locations returned HTTP 422).",
        });
      } else {
        setLocFeedback({
          kind: "error",
          text: formatRouteError("/api/locations", response.status),
        });
      }
    } catch {
      setLocFeedback({
        kind: "error",
        text: formatRouteError("/api/locations"),
      });
    } finally {
      setLocSubmitting(false);
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

  if (settingsQuery.isError) {
    const status =
      settingsQuery.error instanceof ApiRequestError
        ? settingsQuery.error.status
        : undefined;
    return (
      <div
        role="alert"
        className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
      >
        {formatRouteError("/api/settings", status)}
      </div>
    );
  }

  const settingsData = settingsQuery.data;
  const locations = locationsQuery.data?.locations ?? [];
  const disclaimer = disclaimerQuery.data;
  const licenses = licensesQuery.data ?? [];

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          Settings
        </h1>
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          Manage watched locations, browser notifications, effective
          configuration, the alert ladder, and the full disclaimer.
        </p>
      </section>

      {settingsData?.file_modified_since_start && (
        <div
          role="alert"
          className="rounded-lg border border-amber-400 bg-amber-50 p-4 text-xs text-amber-950 dark:border-amber-600 dark:bg-amber-950/70 dark:text-amber-100"
        >
          <div className="flex items-start gap-2.5">
            <AlertTriangle
              className="mt-0.5 h-4 w-4 shrink-0 text-amber-700 dark:text-amber-400"
              aria-hidden="true"
            />
            <div>
              <p className="font-semibold">
                Configuration file modified since monitor start
              </p>
              <p className="mt-0.5">
                <code>weatherbot.toml</code> has changed on disk since{" "}
                <code>weatherbot serve</code> started. Restart{" "}
                <code>weatherbot serve</code> (or the{" "}
                <code>\Weatherbot\serve</code> scheduled task) to apply the new
                settings.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Watched Locations & Add Location Form */}
      <section
        aria-labelledby="locations-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center gap-2">
          <MapPin
            className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <h2
            id="locations-heading"
            className="text-base font-bold text-slate-900 dark:text-slate-100"
          >
            Watched Locations
          </h2>
        </div>

        {locations.length > 0 && (
          <div className="mt-3 space-y-2">
            {locations.map((loc) => (
              <div
                key={loc.name}
                className="rounded-md border border-slate-200 bg-slate-50/70 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/40"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-bold text-slate-900 dark:text-slate-100">
                    {loc.name}
                  </span>
                  <span className="font-mono text-slate-600 dark:text-slate-300">
                    {String(loc.latitude)}, {String(loc.longitude)}
                  </span>
                </div>
                <div className="mt-1 text-slate-600 dark:text-slate-400">
                  {loc.display_name ? `${loc.display_name} · ` : ""}
                  {loc.nws
                    ? `NWS ${loc.nws.cwa} (${loc.nws.forecast_zone}, ${loc.nws.county_zone}) · ${loc.nws.time_zone}`
                    : "Outside NWS coverage"}
                  {loc.has_polygon ? " · Zone polygon stored" : ""}
                </div>
                <div className="mt-1 text-slate-600 dark:text-slate-400">
                  Breakpoint span: {formatBreakpointSpan(loc.breakpoint_span)} ·
                  Evacuation order:{" "}
                  <strong>
                    {loc.evacuation_order_in_effect ? "On" : "Off"}
                  </strong>
                  {loc.evacuation_order_set_at
                    ? ` (since ${formatBothTimes(loc.evacuation_order_set_at, loc.nws?.time_zone)})`
                    : ""}
                </div>
              </div>
            ))}
          </div>
        )}

        <form
          onSubmit={(e) => void handleAddLocation(e)}
          className="mt-4 space-y-3 border-t border-slate-200 pt-4 text-xs dark:border-slate-800"
        >
          <h3 className="font-semibold text-slate-900 dark:text-slate-100">
            Add a watched location
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <div>
              <label
                htmlFor="location-name-input"
                className="block font-medium text-slate-700 dark:text-slate-300"
              >
                Location name
              </label>
              <input
                id="location-name-input"
                aria-label="Location name"
                type="text"
                value={locName}
                onChange={(e) => setLocName(e.target.value)}
                placeholder="e.g. Miami-Dade County Hall"
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label
                htmlFor="location-lat-input"
                className="block font-medium text-slate-700 dark:text-slate-300"
              >
                Latitude
              </label>
              <input
                id="location-lat-input"
                aria-label="Latitude"
                type="text"
                inputMode="decimal"
                value={locLat}
                onChange={(e) => setLocLat(e.target.value)}
                placeholder="-90 to 90"
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label
                htmlFor="location-lon-input"
                className="block font-medium text-slate-700 dark:text-slate-300"
              >
                Longitude
              </label>
              <input
                id="location-lon-input"
                aria-label="Longitude"
                type="text"
                inputMode="decimal"
                value={locLon}
                onChange={(e) => setLocLon(e.target.value)}
                placeholder="-180 to 180"
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>
            <div>
              <label
                htmlFor="location-polygon-select"
                className="block font-medium text-slate-700 dark:text-slate-300"
              >
                Zone polygon
              </label>
              <select
                id="location-polygon-select"
                aria-label="Zone polygon"
                value={locPolygon}
                onChange={(e) =>
                  setLocPolygon(e.target.value as "" | PolygonKind)
                }
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="">None (point only)</option>
                <option value="forecast">Forecast zone</option>
                <option value="county">County zone</option>
              </select>
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled={locSubmitting}
              className="inline-flex items-center rounded-md bg-sky-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:opacity-60 dark:bg-sky-500 dark:text-slate-950"
            >
              Add location
            </button>
          </div>

          {locFeedback && (
            <div
              role={locFeedback.kind === "error" ? "alert" : "status"}
              className={`rounded-md border px-3 py-2 text-xs ${
                locFeedback.kind === "error"
                  ? "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
                  : "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200"
              }`}
            >
              {locFeedback.text}
            </div>
          )}
        </form>
      </section>

      {/* Browser Notifications & Test Notification */}
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
            Browser &amp; Desktop Notifications
          </h2>
        </div>

        <div className="mt-3 flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div className="space-y-1 text-xs">
            <p className="font-semibold text-slate-900 dark:text-slate-100">
              Background Web Notifications:{" "}
              <span>{browserNotifEnabled ? "On" : "Off"}</span> (Permission:{" "}
              <code>{browserPermission}</code>)
            </p>
            <p className="text-slate-600 dark:text-slate-300">
              In-page notification toasts always appear when a notification
              event arrives while this dashboard is open. Turning this switch on
              also fires a system Web Notification when the tab is hidden.
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

      {/* Effective Settings */}
      <section
        aria-labelledby="effective-settings-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center gap-2">
          <Sliders
            className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <h2
            id="effective-settings-heading"
            className="text-base font-bold text-slate-900 dark:text-slate-100"
          >
            Effective Settings
          </h2>
        </div>

        {settingsData && (
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">
            Configuration file: <code>{settingsData.settings_file}</code> (
            {settingsData.settings_file_exists ? "present" : "not created"})
          </p>
        )}

        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 text-slate-600 dark:border-slate-800 dark:text-slate-400">
                <th className="py-2 pr-3 font-semibold">Setting</th>
                <th className="py-2 pr-3 font-semibold">Value</th>
                <th className="py-2 pr-3 font-semibold">Origin</th>
                <th className="py-2 font-semibold">Environment variable</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {(settingsData?.settings ?? []).map((item) => (
                <tr key={`${item.table}.${item.key}`}>
                  <td className="py-1.5 pr-3 font-mono text-slate-900 dark:text-slate-100">
                    [{item.table}] {item.key}
                  </td>
                  <td className="py-1.5 pr-3 font-mono text-slate-800 dark:text-slate-200">
                    {String(item.value)}
                  </td>
                  <td className="py-1.5 pr-3">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                      {item.origin}
                    </span>
                  </td>
                  <td className="py-1.5 font-mono text-slate-500 dark:text-slate-400">
                    {item.variable}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Alert Ladder Reference */}
      <section
        aria-labelledby="ladder-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center gap-2">
          <BookOpen
            className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <h2
            id="ladder-heading"
            className="text-base font-bold text-slate-900 dark:text-slate-100"
          >
            Alert Ladder (11 Rules in Fixed Evaluation Order)
          </h2>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <ThreatLevelBadge level={1} />
          <ThreatLevelBadge level={2} />
          <ThreatLevelBadge level={3} />
          <ThreatLevelBadge level={4} />
          <ThreatLevelBadge level={5} />
        </div>

        <div className="mt-4 space-y-2 text-xs">
          {LADDER_RULES.map((rule) => (
            <div
              key={rule.id}
              className="flex flex-col justify-between gap-2 rounded-md border border-slate-200 bg-slate-50/60 p-2.5 sm:flex-row sm:items-center dark:border-slate-800 dark:bg-slate-800/30"
            >
              <div>
                <span className="font-bold text-slate-900 dark:text-slate-100">
                  {String(rule.order)}. <code>{rule.id}</code>
                </span>
                <p className="mt-0.5 text-slate-600 dark:text-slate-300">
                  {rule.trigger}
                </p>
              </div>
              <div className="shrink-0">
                <ThreatLevelBadge level={rule.level} size="sm" />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Full Disclaimer */}
      <section
        id="disclaimer"
        aria-labelledby="disclaimer-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center gap-2">
          <FileText
            className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
            aria-hidden="true"
          />
          <h2
            id="disclaimer-heading"
            className="text-base font-bold text-slate-900 dark:text-slate-100"
          >
            Full Disclaimer
          </h2>
        </div>

        {disclaimer ? (
          <div className="mt-3 space-y-3 text-xs leading-relaxed text-slate-700 dark:text-slate-300">
            <div className="rounded-md border border-amber-300 bg-amber-50/70 p-3 text-amber-950 dark:border-amber-700/80 dark:bg-amber-950/50 dark:text-amber-100">
              <p className="font-semibold">Essentials</p>
              <p className="mt-1 whitespace-pre-line">
                {disclaimer.essentials.join("\n")}
              </p>
            </div>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 p-3 font-sans text-xs text-slate-800 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200">
              {disclaimer.full_text}
            </pre>
          </div>
        ) : (
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
            Weatherbot is informational only and never a substitute for official
            NHC, NWS, or local emergency-management guidance.
          </p>
        )}
      </section>

      {/* Bundled Dependency Licences */}
      <section
        aria-labelledby="licenses-heading"
        className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
      >
        <h2
          id="licenses-heading"
          className="text-base font-bold text-slate-900 dark:text-slate-100"
        >
          Bundled Frontend Dependency Licences
        </h2>
        {licenses.length === 0 ? (
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">
            Build the frontend bundle (<code>npm run build</code>) to populate{" "}
            <code>/licenses.json</code>.
          </p>
        ) : (
          <ul className="mt-3 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
            {licenses.map((pkg) => (
              <li
                key={`${pkg.name}-${pkg.version ?? ""}`}
                className="rounded border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/40"
              >
                <span className="font-semibold text-slate-900 dark:text-slate-100">
                  {pkg.name}
                </span>
                {pkg.version ? ` v${pkg.version}` : ""}
                {pkg.license ? (
                  <span className="ml-1.5 rounded bg-slate-200 px-1.5 py-0.5 text-[11px] font-medium text-slate-800 dark:bg-slate-700 dark:text-slate-200">
                    {pkg.license}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
