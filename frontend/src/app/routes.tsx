// frontend/src/app/routes.tsx
import {
  createBrowserRouter,
  createMemoryRouter,
  Link,
  type RouteObject,
} from "react-router";
import { AppShell, type AppShellProps } from "./AppShell.tsx";
import { ThreatLevelBadge } from "./ThreatLevelBadge.tsx";

interface PlaceholderPageProps {
  readonly title: string;
  readonly summary: string;
  readonly showLevelLegend?: boolean;
  readonly includeDisclaimerAnchor?: boolean;
}

function PlaceholderPage({
  title,
  summary,
  showLevelLegend = false,
  includeDisclaimerAnchor = false,
}: PlaceholderPageProps) {
  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          {title}
        </h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          {summary}
        </p>
        {showLevelLegend && (
          <div className="mt-4 flex flex-wrap gap-2" aria-label="Threat level scale">
            <ThreatLevelBadge level={1} />
            <ThreatLevelBadge level={2} />
            <ThreatLevelBadge level={3} />
            <ThreatLevelBadge level={4} />
            <ThreatLevelBadge level={5} />
          </div>
        )}
      </div>
      {includeDisclaimerAnchor && (
        <section
          id="disclaimer"
          aria-labelledby="disclaimer-heading"
          className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs dark:border-slate-800 dark:bg-slate-900"
        >
          <h2
            id="disclaimer-heading"
            className="text-sm font-semibold text-slate-900 dark:text-slate-100"
          >
            Disclaimer
          </h2>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            Weatherbot is informational only and never a substitute for official
            NHC, NWS, or local emergency-management guidance.
          </p>
        </section>
      )}
    </section>
  );
}

function NotFoundPage() {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-xs dark:border-slate-800 dark:bg-slate-900">
      <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
        Page not found
      </h1>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
        The requested dashboard route does not exist.
      </p>
      <div className="mt-4">
        <Link
          to="/"
          className="inline-flex items-center rounded-md bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:bg-sky-500 dark:text-slate-950"
        >
          Return to Dashboard
        </Link>
      </div>
    </section>
  );
}

export function createAppRoutes(shellProps?: AppShellProps): RouteObject[] {
  return [
    {
      path: "/",
      element: <AppShell {...shellProps} />,
      children: [
        {
          index: true,
          element: (
            <PlaceholderPage
              title="Dashboard"
              summary="Location threat levels, deciding rules, active storms, and official watches and warnings."
              showLevelLegend
            />
          ),
        },
        {
          path: "map",
          element: (
            <PlaceholderPage
              title="Map"
              summary="Official NHC forecast cones, tracks, watch/warning segments, outlook areas, and watched locations."
            />
          ),
        },
        {
          path: "storms",
          element: (
            <PlaceholderPage
              title="Storms"
              summary="Active tropical cyclones and Tropical Weather Outlook areas from the latest NHC snapshot."
            />
          ),
        },
        {
          path: "alerts",
          element: (
            <PlaceholderPage
              title="Alerts"
              summary="Active NWS alerts and NHC breakpoint segments for watched locations."
            />
          ),
        },
        {
          path: "timeline",
          element: (
            <PlaceholderPage
              title="Timeline"
              summary="Stored assessment history, threat changes, and notification delivery decisions."
            />
          ),
        },
        {
          path: "settings",
          element: (
            <PlaceholderPage
              title="Settings"
              summary="Watched locations, evacuation toggles, browser notification controls, effective settings, and licences."
              includeDisclaimerAnchor
            />
          ),
        },
        {
          path: "*",
          element: <NotFoundPage />,
        },
      ],
    },
  ];
}

export function createAppBrowserRouter(shellProps?: AppShellProps) {
  return createBrowserRouter(createAppRoutes(shellProps));
}

export function createAppMemoryRouter(
  initialEntries: string[] = ["/"],
  shellProps?: AppShellProps,
) {
  return createMemoryRouter(createAppRoutes(shellProps), {
    initialEntries,
  });
}
