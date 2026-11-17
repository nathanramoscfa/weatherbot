// frontend/src/pages/Settings.tsx
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BookOpen,
  FileText,
  Sliders,
} from "lucide-react";
import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router";
import { AiSettingsSection } from "../ai/AiSettingsSection.tsx";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { ThreatLevelBadge } from "../app/ThreatLevelBadge.tsx";
import { levelLabel, useLadder } from "../assessment/vocabulary.ts";
import {
  LocationManager,
  type PolygonKind,
} from "../settings/LocationManager.tsx";
import { NotificationChannels } from "../settings/NotificationChannels.tsx";
import { QuietHoursForm } from "../settings/QuietHoursForm.tsx";
import { RetentionPanel } from "../settings/RetentionPanel.tsx";
import { Card } from "../ui/Card.tsx";
import { PageHeader } from "../ui/PageHeader.tsx";
import { Tab, TabList, TabPanel, Tabs } from "../ui/Tabs.tsx";
import { formatRouteError } from "./format.ts";

export type SettingsResponse = components["schemas"]["SettingsResponse"];
export type DisclaimerResponse = components["schemas"]["DisclaimerResponse"];
export type LocationsResponse = components["schemas"]["LocationsResponse"];
export type { PolygonKind };

export type SettingsTabId =
  | "locations"
  | "notifications"
  | "ai"
  | "retention"
  | "about";

export const SETTINGS_TABS: ReadonlyArray<{
  readonly id: SettingsTabId;
  readonly label: string;
  readonly hash: string;
}> = [
  { id: "locations", label: "Locations", hash: "#locations" },
  {
    id: "notifications",
    label: "Notifications & Quiet Hours",
    hash: "#notifications",
  },
  { id: "ai", label: "AI & Budget", hash: "#ai" },
  { id: "retention", label: "History & Retention", hash: "#retention" },
  { id: "about", label: "Threat Ladder & About", hash: "#about" },
];

export function resolveSettingsTab(hash: string): SettingsTabId {
  const normalized = hash.replace(/^#/, "").trim().toLowerCase();
  switch (normalized) {
    case "locations":
      return "locations";
    case "notifications":
      return "notifications";
    case "ai":
      return "ai";
    case "retention":
      return "retention";
    case "about":
    case "disclaimer":
      return "about";
    default:
      return "locations";
  }
}

export interface BundledLicenseEntry {
  readonly name: string;
  readonly version?: string;
  readonly license?: string;
}

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

function LocationsTabContent() {
  const locationsQuery = useQuery({
    queryKey: queryKeys.locations(),
    queryFn: fetchLocations,
  });
  const locations = locationsQuery.data?.locations ?? [];
  return <LocationManager locations={locations} />;
}

function AboutTabContent({
  settingsData,
  initialLicenses,
}: {
  readonly settingsData: SettingsResponse | undefined;
  readonly initialLicenses: BundledLicenseEntry[] | undefined;
}) {
  const disclaimerQuery = useQuery({
    queryKey: queryKeys.disclaimer(),
    queryFn: fetchDisclaimer,
  });
  const licensesQuery = useQuery({
    queryKey: queryKeys.licenses(),
    queryFn: fetchLicenses,
    ...(initialLicenses !== undefined ? { initialData: initialLicenses } : {}),
  });
  const { ladder } = useLadder();

  const disclaimer = disclaimerQuery.data;
  const licenses = licensesQuery.data ?? [];

  return (
    <div className="space-y-6">
      {/* Alert Ladder Reference */}
      <Card as="section" aria-labelledby="ladder-heading">
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
          {ladder.levels.map((lvl) => (
            <ThreatLevelBadge
              key={lvl.number}
              level={lvl.number}
              label={lvl.label}
            />
          ))}
        </div>

        <div className="mt-4 space-y-2 text-sm">
          {ladder.rules.map((rule) => (
            <div
              key={rule.id}
              data-testid={`ladder-rule-${rule.id}`}
              className="flex flex-col justify-between gap-2 rounded-md border border-line bg-surface-inset p-3 sm:flex-row sm:items-center"
            >
              <div className="space-y-0.5">
                <span className="font-bold text-ink">
                  {String(rule.order)}. {rule.sentence}
                </span>
                <span className="block text-caption text-ink-subtle">
                  Rule: <code className="font-mono text-ink">{rule.id}</code> ·{" "}
                  {rule.sources.length > 0
                    ? `Reads: ${rule.sources.join(", ")}`
                    : "Fallback when no earlier rule matches"}
                </span>
              </div>
              <div className="shrink-0">
                <ThreatLevelBadge
                  level={rule.level}
                  label={levelLabel(rule.level, ladder)}
                  size="sm"
                />
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <div className="rounded-md border border-line bg-surface-inset p-3">
            <h3 className="font-semibold text-ink">
              NWS alert events read by the ladder
            </h3>
            <ul className="mt-1.5 space-y-1 text-ink-muted">
              {ladder.events.map((ev) => (
                <li key={ev.event}>
                  <span className="font-medium text-ink">{ev.event}</span> →{" "}
                  <code className="font-mono text-ink">{ev.rule}</code> (Level{" "}
                  {String(ev.level)})
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-md border border-line bg-surface-inset p-3">
            <h3 className="font-semibold text-ink">
              NHC watch-warning segment codes read by the ladder
            </h3>
            <ul className="mt-1.5 space-y-1 text-ink-muted">
              {ladder.codes.map((item) => (
                <li key={item.code}>
                  <code className="font-mono font-semibold text-ink">
                    {item.code}
                  </code>{" "}
                  ({item.name}) →{" "}
                  <code className="font-mono text-ink">{item.rule}</code> (Level{" "}
                  {String(item.level)})
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Card>

      {/* Effective Settings */}
      <Card as="section" aria-labelledby="effective-settings-heading">
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
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Configuration file: <code>{settingsData.settings_file}</code> (
            {settingsData.settings_file_exists ? "present" : "not created"})
          </p>
        )}

        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
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
      </Card>

      {/* Full Disclaimer */}
      <Card as="section" id="disclaimer" aria-labelledby="disclaimer-heading">
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
          <div className="mt-3 space-y-3 text-sm leading-relaxed text-slate-700 dark:text-slate-300">
            <div className="rounded-md border border-amber-300 bg-amber-50/70 p-3 text-amber-950 dark:border-amber-700/80 dark:bg-amber-950/50 dark:text-amber-100">
              <p className="font-semibold">Essentials</p>
              <p className="mt-1 whitespace-pre-line">
                {disclaimer.essentials.join("\n")}
              </p>
            </div>
            <pre className="overflow-x-auto whitespace-pre-wrap rounded-md border border-slate-200 bg-slate-50 p-3 font-sans text-sm text-slate-800 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200">
              {disclaimer.full_text}
            </pre>
          </div>
        ) : (
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            Weatherbot is informational only and never a substitute for official
            NHC, NWS, or local emergency-management guidance.
          </p>
        )}
      </Card>

      {/* Bundled Dependency Licences */}
      <Card as="section" aria-labelledby="licenses-heading">
        <h2
          id="licenses-heading"
          className="text-base font-bold text-slate-900 dark:text-slate-100"
        >
          Bundled Frontend Dependency Licences
        </h2>
        {licenses.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            Build the frontend bundle (<code>npm run build</code>) to populate{" "}
            <code>/licenses.json</code>.
          </p>
        ) : (
          <ul className="mt-3 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
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
                  <span className="ml-1.5 rounded bg-slate-200 px-1.5 py-0.5 text-caption font-medium text-slate-800 dark:bg-slate-700 dark:text-slate-200">
                    {pkg.license}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

export interface SettingsProps {
  readonly initialLicenses?: BundledLicenseEntry[];
}

export function Settings({ initialLicenses }: SettingsProps = {}) {
  const location = useLocation();
  const navigate = useNavigate();

  const settingsQuery = useQuery({
    queryKey: queryKeys.settings(),
    queryFn: fetchSettings,
  });

  useEffect(() => {
    const syncFromWindowHash = () => {
      if (window.location.hash !== location.hash) {
        void navigate(
          { pathname: location.pathname, hash: window.location.hash },
          { replace: true },
        );
      }
    };
    window.addEventListener("hashchange", syncFromWindowHash);
    return () => {
      window.removeEventListener("hashchange", syncFromWindowHash);
    };
  }, [location.hash, location.pathname, navigate]);

  const activeTab = resolveSettingsTab(location.hash);

  useEffect(() => {
    const normalized = location.hash.replace(/^#/, "").trim().toLowerCase();
    if (normalized === "disclaimer") {
      const target = document.getElementById("disclaimer");
      target?.scrollIntoView?.();
    }
  }, [location.hash, activeTab]);

  const handleTabChange = (nextValue: string) => {
    const nextTab = resolveSettingsTab(nextValue);
    void navigate(
      { pathname: location.pathname, hash: `#${nextTab}` },
      { replace: true },
    );
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

  return (
    <div className="space-y-6">
      <Card as="section">
        <PageHeader
          title="Settings"
          summary={
            <>
              Manage watched locations, notification channels and quiet hours,
              AI budget controls, database retention, the alert ladder, and the
              full disclaimer.
            </>
          }
        />
      </Card>

      {settingsData?.settings_file_problem && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
        >
          <p className="font-semibold">
            Configuration file problem — running on last valid settings
          </p>
          <p className="mt-0.5 font-mono">
            {settingsData.settings_file_problem}
          </p>
        </div>
      )}

      {(settingsData?.restart_keys?.length ?? 0) > 0 && (
        <div
          role="alert"
          className="rounded-lg border border-amber-400 bg-amber-50 p-4 text-sm text-amber-950 dark:border-amber-600 dark:bg-amber-950/70 dark:text-amber-100"
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
                Restart <code>weatherbot serve</code> (or the{" "}
                <code>\Weatherbot\serve</code> scheduled task) to apply:{" "}
                <code>{settingsData?.restart_keys.join(", ")}</code>.
              </p>
            </div>
          </div>
        </div>
      )}

      <Tabs
        value={activeTab}
        onValueChange={handleTabChange}
        idPrefix="settings"
      >
        <TabList aria-label="Settings sections">
          {SETTINGS_TABS.map((tab) => (
            <Tab key={tab.id} value={tab.id}>
              {tab.label}
            </Tab>
          ))}
        </TabList>

        <TabPanel value="locations">
          <LocationsTabContent />
        </TabPanel>

        <TabPanel value="notifications">
          <NotificationChannels />
          <QuietHoursForm />
        </TabPanel>

        <TabPanel value="ai">
          <AiSettingsSection />
        </TabPanel>

        <TabPanel value="retention">
          <RetentionPanel />
        </TabPanel>

        <TabPanel value="about">
          <AboutTabContent
            settingsData={settingsData}
            initialLicenses={initialLicenses}
          />
        </TabPanel>
      </Tabs>
    </div>
  );
}
