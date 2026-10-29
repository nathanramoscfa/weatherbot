// frontend/src/app/routes.tsx
import {
  createBrowserRouter,
  createMemoryRouter,
  Link,
  type RouteObject,
} from "react-router";
import { MapView } from "../map/MapView.tsx";
import { Alerts } from "../pages/Alerts.tsx";
import { Dashboard } from "../pages/Dashboard.tsx";
import { Settings } from "../pages/Settings.tsx";
import { Storms } from "../pages/Storms.tsx";
import { Timeline } from "../pages/Timeline.tsx";
import { AppShell, type AppShellProps } from "./AppShell.tsx";

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
          element: <Dashboard />,
        },
        {
          path: "map",
          element: <MapView />,
        },
        {
          path: "storms",
          element: <Storms />,
        },
        {
          path: "alerts",
          element: <Alerts />,
        },
        {
          path: "timeline",
          element: <Timeline />,
        },
        {
          path: "settings",
          element: <Settings />,
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
