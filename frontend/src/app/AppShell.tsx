// frontend/src/app/AppShell.tsx
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Radio, ShieldAlert, WifiOff } from "lucide-react";
import { Link, NavLink, Outlet } from "react-router";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import {
  type StreamEvent,
  useEventStream,
} from "../events/useEventStream.ts";
import { ThemeMenu } from "./ThemeMenu.tsx";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type HeartbeatHealth = components["schemas"]["HeartbeatHealth"];

export const DEFAULT_DISCLAIMER_NOTICE =
  "Informational only — never a substitute for official NHC, NWS, or local emergency-management guidance. Keep a NOAA Weather Radio and multiple independent warning sources.";

export const NAV_ITEMS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/map", label: "Map", end: false },
  { to: "/storms", label: "Storms", end: false },
  { to: "/alerts", label: "Alerts", end: false },
  { to: "/timeline", label: "Timeline", end: false },
  { to: "/settings", label: "Settings", end: false },
] as const;

export function formatHeartbeatAge(ageSeconds: number | null): string {
  if (ageSeconds === null || !Number.isFinite(ageSeconds) || ageSeconds < 0) {
    return "never succeeded";
  }
  const rounded = Math.round(ageSeconds);
  if (rounded < 60) {
    return `${String(rounded)}s ago`;
  }
  const totalMinutes = Math.floor(rounded / 60);
  if (totalMinutes < 60) {
    return `${String(totalMinutes)}m ago`;
  }
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (minutes === 0) {
    return `${String(hours)}h ago`;
  }
  return `${String(hours)}h ${String(minutes)}m ago`;
}

export function formatStaleHeartbeats(health: HealthResponse): string[] {
  const staleRows = health.heartbeats.filter((row) => row.stale);
  if (staleRows.length > 0) {
    return staleRows.map(
      (row) => `${row.name} (${formatHeartbeatAge(row.age_s)})`,
    );
  }
  if (health.scheduler.stale) {
    return ["scheduler heartbeat stale"];
  }
  return ["monitor heartbeat stale"];
}

export interface AppShellProps {
  readonly onNotificationDisplay?: (event: StreamEvent) => void;
  readonly fetchHealth?: () => Promise<HealthResponse>;
}

async function defaultFetchHealth(): Promise<HealthResponse> {
  const { data, response } = await apiClient.GET("/api/health");
  if (!response.ok || !data) {
    throw new ApiRequestError("/api/health", response.status);
  }
  return data;
}

export function AppShell({
  onNotificationDisplay,
  fetchHealth = defaultFetchHealth,
}: AppShellProps) {
  const eventStream = useEventStream({ onNotificationDisplay });
  const healthQuery = useQuery({
    queryKey: queryKeys.health(),
    queryFn: fetchHealth,
  });

  const health = healthQuery.data;
  const staleItems = health?.stale ? formatStaleHeartbeats(health) : [];
  const noticeText = health?.notice ?? DEFAULT_DISCLAIMER_NOTICE;

  return (
    <div className="flex min-h-screen w-full max-w-full flex-col overflow-x-hidden bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-3 py-2.5 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Link
              to="/"
              className="inline-flex items-center gap-2 rounded-md text-base font-bold tracking-tight text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:text-slate-100"
            >
              <ShieldAlert
                className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
                aria-hidden="true"
              />
              <span>Weatherbot</span>
            </Link>

            <div className="flex flex-wrap items-center gap-2">
              {eventStream.status === "reconnecting" ? (
                <div
                  role="status"
                  aria-live="polite"
                  className="inline-flex items-center gap-1.5 rounded-md border border-amber-400 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-900 dark:border-amber-600 dark:bg-amber-950/60 dark:text-amber-200"
                >
                  <WifiOff className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <span>Reconnecting…</span>
                </div>
              ) : (
                <div
                  className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-100 px-2 py-1 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-800/70 dark:text-slate-300"
                  aria-label="Live event stream status"
                >
                  <Radio
                    className="h-3 w-3 shrink-0 text-emerald-600 dark:text-emerald-400"
                    aria-hidden="true"
                  />
                  <span>Live</span>
                </div>
              )}
              <ThemeMenu />
            </div>
          </div>

          <nav
            aria-label="Primary navigation"
            className="grid grid-cols-3 gap-1 sm:flex sm:flex-wrap sm:items-center sm:gap-1.5"
          >
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-md px-2.5 py-1.5 text-center text-xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 sm:text-sm ${
                    isActive
                      ? "bg-sky-600 text-white dark:bg-sky-500 dark:text-slate-950"
                      : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      {health?.stale && (
        <div
          role="alert"
          className="border-b border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950 sm:px-6 dark:border-amber-700/80 dark:bg-amber-950/70 dark:text-amber-100"
        >
          <div className="mx-auto flex max-w-6xl items-start gap-2">
            <AlertTriangle
              className="mt-0.5 h-4 w-4 shrink-0 text-amber-700 dark:text-amber-400"
              aria-hidden="true"
            />
            <div>
              <span className="font-semibold">Stale monitor data: </span>
              <span>{staleItems.join(", ")}</span>
            </div>
          </div>
        </div>
      )}

      <main className="mx-auto w-full max-w-6xl flex-1 px-3 py-5 sm:px-6">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white px-3 py-3 text-xs text-slate-600 sm:px-6 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
        <div className="mx-auto flex max-w-6xl flex-col justify-between gap-2 sm:flex-row sm:items-center">
          <p>{noticeText}</p>
          <Link
            to="/settings#disclaimer"
            className="shrink-0 font-medium text-sky-700 underline underline-offset-2 hover:text-sky-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:text-sky-400 dark:hover:text-sky-300"
          >
            Read full disclaimer
          </Link>
        </div>
      </footer>
    </div>
  );
}
