// frontend/src/app/AppShell.tsx
import { useQuery } from "@tanstack/react-query";
import {
  ChartLine,
  LayoutDashboard,
  Map as MapIcon,
  MessageCircle,
  Radio,
  Rewind,
  Settings as SettingsIcon,
  ShieldAlert,
  Siren,
  TriangleAlert,
  WifiOff,
  Wind,
  X,
} from "lucide-react";
import { Toast } from "radix-ui";
import { useCallback, useState } from "react";
import { Link, NavLink, Outlet } from "react-router";
import { ApiRequestError, apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import {
  type StreamEvent,
  useEventStream,
} from "../events/useEventStream.ts";
import { deliverBrowserNotification } from "../notifications/notify.ts";
import { formatUtc } from "../pages/format.ts";
import { Callout } from "../ui/Callout.tsx";
import { cx, threatClasses } from "../ui/threat.ts";
import { type NavBadge, useNavBadges } from "./navStatus.ts";
import { ThreatLevelBadge } from "./ThreatLevelBadge.tsx";
import { ThemeMenu } from "./ThemeMenu.tsx";

export type HealthResponse = components["schemas"]["HealthResponse"];
export type HeartbeatHealth = components["schemas"]["HeartbeatHealth"];

export const DEFAULT_DISCLAIMER_NOTICE =
  "Informational only — never a substitute for official NHC, NWS, or local emergency-management guidance. Keep a NOAA Weather Radio and multiple independent warning sources.";

export const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/map", label: "Map", icon: MapIcon, end: false },
  { to: "/replay", label: "Replay", icon: Rewind, end: false },
  { to: "/storms", label: "Storms", icon: Wind, end: false },
  { to: "/alerts", label: "Alerts", icon: Siren, end: false },
  { to: "/timeline", label: "Timeline", icon: ChartLine, end: false },
  { to: "/ask", label: "Ask", icon: MessageCircle, end: false },
  { to: "/settings", label: "Settings", icon: SettingsIcon, end: false },
] as const;

// The id of the hidden sentence that describes a link's badge.
export function navBadgeId(path: string): string {
  return path === "/" ? "nav-status-dashboard" : `nav-status-${path.slice(1)}`;
}

const BADGE_TONE: Readonly<Record<Exclude<NavBadge["tone"], "level">, string>> = {
  count: "border-line-strong bg-surface-card text-ink",
  ai: "border-violet-300 bg-violet-50 text-violet-900 dark:border-violet-700 dark:bg-violet-950 dark:text-violet-100",
  warning:
    "border-amber-500 bg-amber-100 text-amber-950 dark:border-amber-500 dark:bg-amber-900 dark:text-amber-50",
};

// A live mark beside a navigation link: aria-hidden, and described to
// assistive technology by the link's aria-describedby, so the link's text and
// accessible name stay its label (docs/DESIGN.md, "Navigation").
function NavStatusBadge({ path, badge }: { path: string; badge: NavBadge }) {
  const toneClass =
    badge.tone === "level" && badge.level !== undefined
      ? threatClasses(badge.level).solid
      : BADGE_TONE[badge.tone === "level" ? "count" : badge.tone];
  return (
    <>
      <span
        aria-hidden="true"
        data-testid={`nav-badge-${navBadgeId(path).slice("nav-status-".length)}`}
        className={cx(
          "pointer-events-none absolute -top-2 right-0 inline-flex min-w-5 items-center justify-center rounded-pill border px-1.5 text-caption leading-tight font-semibold tabular-nums",
          toneClass,
        )}
      >
        {badge.tone === "warning" ? (
          <TriangleAlert className="my-0.5 h-3.5 w-3.5" aria-hidden="true" />
        ) : (
          badge.text
        )}
      </span>
      <span id={navBadgeId(path)} hidden>
        {badge.description}
      </span>
    </>
  );
}

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
  const [toastEvents, setToastEvents] = useState<StreamEvent[]>([]);

  const handleNotificationDisplay = useCallback(
    (event: StreamEvent) => {
      onNotificationDisplay?.(event);
      deliverBrowserNotification(event);
      setToastEvents((prev) => [...prev.slice(-4), event]);
    },
    [onNotificationDisplay],
  );

  const eventStream = useEventStream({
    onNotificationDisplay: handleNotificationDisplay,
  });
  const healthQuery = useQuery({
    queryKey: queryKeys.health(),
    queryFn: fetchHealth,
  });

  const health = healthQuery.data;
  const navBadges = useNavBadges(health, healthQuery.dataUpdatedAt);
  const staleItems = health?.stale ? formatStaleHeartbeats(health) : [];
  const noticeText = health?.notice ?? DEFAULT_DISCLAIMER_NOTICE;

  return (
    <Toast.Provider swipeDirection="right" duration={10000}>
      <div className="flex min-h-screen w-full max-w-full flex-col bg-surface-page text-ink">
      <header className="border-b border-line bg-surface-card">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-3 py-2.5 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Link
              to="/"
              className="inline-flex items-center gap-2 rounded-control text-lg font-bold tracking-tight text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              <ShieldAlert
                className="h-5 w-5 shrink-0 text-brand"
                aria-hidden="true"
              />
              <span>Weatherbot</span>
            </Link>

            <div className="flex flex-wrap items-center gap-2">
              {eventStream.status === "reconnecting" ? (
                <div
                  role="status"
                  aria-live="polite"
                  className="inline-flex items-center gap-1.5 rounded-pill border border-amber-400 bg-amber-50 px-2.5 py-1 text-sm font-medium text-amber-900 dark:border-amber-600 dark:bg-amber-950/60 dark:text-amber-200"
                >
                  <WifiOff className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>Reconnecting…</span>
                </div>
              ) : (
                <div
                  className="inline-flex items-center gap-1.5 rounded-pill border border-line bg-surface-inset px-2.5 py-1 text-sm text-ink-muted"
                  aria-label="Live event stream status"
                >
                  <Radio
                    className="h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400"
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
            className="grid grid-cols-4 gap-x-1 gap-y-2 pt-1.5 sm:flex sm:flex-wrap sm:items-center sm:gap-1.5"
          >
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const badge = navBadges[item.to];
              return (
                <div key={item.to} className="relative min-w-0">
                  <NavLink
                    to={item.to}
                    end={item.end}
                    aria-describedby={badge ? navBadgeId(item.to) : undefined}
                    className={({ isActive }) =>
                      cx(
                        "flex min-h-6 flex-col items-center gap-0.5 rounded-control px-1 py-1.5 text-center text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand sm:flex-row sm:gap-1.5 sm:px-3",
                        isActive
                          ? "bg-brand text-on-brand"
                          : "text-ink-muted hover:bg-surface-inset hover:text-ink",
                      )
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    {item.label}
                  </NavLink>
                  {badge && <NavStatusBadge path={item.to} badge={badge} />}
                </div>
              );
            })}
          </nav>
        </div>
      </header>

      {health?.stale && (
        <div className="mx-auto w-full max-w-6xl px-3 pt-4 sm:px-6">
          <Callout tone="warning" role="alert">
            <span className="font-semibold">Stale monitor data: </span>
            <span>{staleItems.join(", ")}</span>
          </Callout>
        </div>
      )}

      <main className="mx-auto w-full max-w-6xl flex-1 px-3 py-5 sm:px-6">
        <Outlet />
      </main>

      <footer className="border-t border-line bg-surface-card px-3 py-4 text-sm text-ink-subtle sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-col justify-between gap-2 sm:flex-row sm:items-center">
          <p>{noticeText}</p>
          <Link
            to="/settings#disclaimer"
            className="shrink-0 font-medium text-brand underline underline-offset-2 hover:text-brand-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            Read full disclaimer
          </Link>
        </div>
      </footer>

      {toastEvents.map((toastEvt) => (
        <Toast.Root
          key={toastEvt.id}
          open
          onOpenChange={(open) => {
            if (!open) {
              setToastEvents((prev) =>
                prev.filter((item) => item.id !== toastEvt.id),
              );
            }
          }}
          className="rounded-card border border-line-strong bg-surface-raised p-3.5 text-sm text-ink shadow-raised"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                {toastEvt.level !== null && toastEvt.level !== undefined && (
                  <ThreatLevelBadge level={toastEvt.level} size="sm" />
                )}
                <Toast.Title className="font-bold text-ink">
                  {toastEvt.title ?? "Weatherbot notification"}
                </Toast.Title>
              </div>
              {toastEvt.body && toastEvt.body.length > 0 && (
                <Toast.Description className="space-y-0.5 text-ink-muted">
                  {toastEvt.body.map((line, idx) => (
                    <span key={idx} className="block">
                      {line}
                    </span>
                  ))}
                </Toast.Description>
              )}
              <time
                dateTime={toastEvt.at}
                className="block text-caption tabular-nums text-ink-subtle"
              >
                {formatUtc(toastEvt.at)}
              </time>
            </div>
            <Toast.Close
              aria-label="Dismiss notification"
              className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-control text-ink-subtle hover:bg-surface-inset hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Toast.Close>
          </div>
        </Toast.Root>
      ))}
      <Toast.Viewport className="fixed right-4 bottom-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2" />
    </div>
    </Toast.Provider>
  );
}
