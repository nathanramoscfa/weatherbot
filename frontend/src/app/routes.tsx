// frontend/src/app/routes.tsx
import {
  createBrowserRouter,
  createMemoryRouter,
  Link,
  type RouteObject,
} from "react-router";
import { MapView } from "../map/MapView.tsx";
import { Alerts } from "../pages/Alerts.tsx";
import { Ask } from "../pages/Ask.tsx";
import { Dashboard } from "../pages/Dashboard.tsx";
import { Replay } from "../pages/Replay.tsx";
import { Settings } from "../pages/Settings.tsx";
import { Storms } from "../pages/Storms.tsx";
import { Timeline } from "../pages/Timeline.tsx";
import { AppShell, type AppShellProps } from "./AppShell.tsx";
import { Card } from "../ui/Card.tsx";

function NotFoundPage() {
  return (
    <Card as="section" padding="none" className="p-6">
      <h1 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
        Page not found
      </h1>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
        The requested dashboard route does not exist.
      </p>
      <div className="mt-4">
        <Link
          to="/"
          className="inline-flex items-center rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-on-brand hover:bg-brand-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          Return to Dashboard
        </Link>
      </div>
    </Card>
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
          path: "replay",
          element: <Replay />,
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
          path: "ask",
          element: <Ask />,
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
