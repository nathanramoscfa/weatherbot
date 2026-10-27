// frontend/src/app/AppShell.test.tsx
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient, initCspNonce } from "../main.tsx";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import alertsFixture from "../test/fixtures/alerts.json";
import assessmentsFixture from "../test/fixtures/assessments.json";
import disclaimerFixture from "../test/fixtures/disclaimer.json";
import locationsFixture from "../test/fixtures/locations.json";
import notificationsFixture from "../test/fixtures/notifications.json";
import settingsFixture from "../test/fixtures/settings.json";
import stormsFixture from "../test/fixtures/storms.json";
import timelineFixture from "../test/fixtures/timeline.json";
import type { HealthResponse } from "./AppShell.tsx";
import { createAppMemoryRouter } from "./routes.tsx";

function seedFixtureCache(queryClient: QueryClient): void {
  queryClient.setQueryData(
    queryKeys.assessments(),
    asSchema<components["schemas"]["AssessmentsResponse"]>(
      assessmentsFixture satisfies JsonFixture<
        components["schemas"]["AssessmentsResponse"]
      >,
    ),
  );
  queryClient.setQueryData(
    queryKeys.locations(),
    asSchema<components["schemas"]["LocationsResponse"]>(
      locationsFixture satisfies JsonFixture<
        components["schemas"]["LocationsResponse"]
      >,
    ),
  );
  queryClient.setQueryData(
    queryKeys.storms(),
    asSchema<components["schemas"]["StormsResponse"]>(
      stormsFixture satisfies JsonFixture<
        components["schemas"]["StormsResponse"]
      >,
    ),
  );
  queryClient.setQueryData(
    queryKeys.alerts(),
    asSchema<components["schemas"]["AlertsResponse"]>(
      alertsFixture satisfies JsonFixture<
        components["schemas"]["AlertsResponse"]
      >,
    ),
  );
  queryClient.setQueryData(
    queryKeys.timeline(),
    asSchema<components["schemas"]["TimelineResponse"]>(
      timelineFixture satisfies JsonFixture<
        components["schemas"]["TimelineResponse"]
      >,
    ),
  );
  queryClient.setQueryData(
    queryKeys.notifications(),
    asSchema<components["schemas"]["NotificationsResponse"]>(
      notificationsFixture satisfies JsonFixture<
        components["schemas"]["NotificationsResponse"]
      >,
    ),
  );
  queryClient.setQueryData(
    queryKeys.settings(),
    asSchema<components["schemas"]["SettingsResponse"]>(
      settingsFixture satisfies JsonFixture<
        components["schemas"]["SettingsResponse"]
      >,
    ),
  );
  queryClient.setQueryData(
    queryKeys.disclaimer(),
    asSchema<components["schemas"]["DisclaimerResponse"]>(
      disclaimerFixture satisfies JsonFixture<
        components["schemas"]["DisclaimerResponse"]
      >,
    ),
  );
  queryClient.setQueryData(queryKeys.licenses(), []);
}

class MockEventSource {
  static instances: MockEventSource[] = [];
  private readonly listeners = new Map<string, Set<(event: Event) => void>>();

  constructor(_url: string | URL) {
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    const set = this.listeners.get(type) ?? new Set<(event: Event) => void>();
    const fn =
      typeof listener === "function"
        ? listener
        : (ev: Event) => listener.handleEvent(ev);
    set.add(fn);
    this.listeners.set(type, set);
  }

  removeEventListener(
    type: string,
    listener: EventListenerOrEventListenerObject,
  ) {
    const set = this.listeners.get(type);
    if (!set || typeof listener !== "function") {
      return;
    }
    set.delete(listener);
  }

  close() {
    // No-op in mock
  }

  emitError() {
    const set = this.listeners.get("error");
    if (!set) {
      return;
    }
    const ev = new Event("error");
    for (const listener of set) {
      listener(ev);
    }
  }

  emitOpen() {
    const set = this.listeners.get("open");
    if (!set) {
      return;
    }
    const ev = new Event("open");
    for (const listener of set) {
      listener(ev);
    }
  }
}

function buildHealthResponse(
  overrides: Partial<HealthResponse> = {},
): HealthResponse {
  return {
    version: "2.0.0.dev0",
    started_at: "2026-10-12T14:00:00Z",
    now: "2026-10-12T15:00:00Z",
    database: {
      revision: "0006",
      head: "0006",
      current: true,
    },
    scheduler: {
      last_success_at: "2026-10-12T14:58:00Z",
      expected_every_s: 300,
      stale: false,
    },
    heartbeats: [
      {
        kind: "source",
        name: "nhc-current-storms",
        last_success_at: "2026-10-12T14:58:00Z",
        age_s: 120,
        consecutive_failures: 0,
        expected_every_s: 300,
        stale: false,
      },
    ],
    stale: false,
    next_product_at: "2026-10-12T15:00:00Z",
    ui: {
      present: true,
      index_sha256: "abcdef012345",
    },
    corpus: false,
    notice:
      "Informational only — never a substitute for official NHC, NWS, or local emergency-management guidance.",
    ...overrides,
  };
}

describe("AppShell and routes", () => {
  const originalEventSource = globalThis.EventSource;

  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    vi.stubGlobal("EventSource", originalEventSource);
  });

  it("renders the six routes, keyboard navigation, threat level text+number badges, and footer notice", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    seedFixtureCache(queryClient);
    const health = buildHealthResponse({
      notice: "Custom health notice — verify with NHC and NWS.",
    });
    const router = createAppMemoryRouter(["/"], {
      fetchHealth: () => Promise.resolve(health),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Dashboard" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Level 1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("All Clear").length).toBeGreaterThanOrEqual(1);

    await waitFor(() => {
      expect(
        screen.getByText("Custom health notice — verify with NHC and NWS."),
      ).toBeInTheDocument();
    });

    const disclaimerLink = screen.getByRole("link", {
      name: "Read full disclaimer",
    });
    expect(disclaimerLink).toHaveAttribute("href", "/settings#disclaimer");

    const routeExpectations: readonly {
      readonly linkName: string;
      readonly heading: string;
    }[] = [
      { linkName: "Map", heading: "Map" },
      { linkName: "Storms", heading: "Storms" },
      { linkName: "Alerts", heading: "Alerts" },
      { linkName: "Timeline", heading: "Timeline" },
      { linkName: "Settings", heading: "Settings" },
      { linkName: "Dashboard", heading: "Dashboard" },
    ];

    for (const item of routeExpectations) {
      await user.click(screen.getByRole("link", { name: item.linkName }));
      expect(
        await screen.findByRole("heading", { name: item.heading }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: "Read full disclaimer" }),
      ).toBeInTheDocument();
    }
  });

  it("renders the not-found page on an unknown route", () => {
    const queryClient = createAppQueryClient();
    const router = createAppMemoryRouter(["/does-not-exist"], {
      fetchHealth: () => Promise.resolve(buildHealthResponse()),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Page not found" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Return to Dashboard" }),
    ).toBeInTheDocument();
  });

  it("displays the staleness banner naming stale sources and their ages, and the reconnecting indicator", async () => {
    const queryClient = createAppQueryClient();
    seedFixtureCache(queryClient);
    const staleHealth = buildHealthResponse({
      stale: true,
      heartbeats: [
        {
          kind: "source",
          name: "nhc-current-storms",
          last_success_at: "2026-10-12T14:15:00Z",
          age_s: 2700,
          consecutive_failures: 3,
          expected_every_s: 300,
          stale: true,
        },
        {
          kind: "source",
          name: "nws-alerts-point",
          last_success_at: "2026-10-12T12:45:00Z",
          age_s: 8100,
          consecutive_failures: 2,
          expected_every_s: 900,
          stale: true,
        },
      ],
    });
    const router = createAppMemoryRouter(["/"], {
      fetchHealth: () => Promise.resolve(staleHealth),
    });

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    const alertBanner = await screen.findByRole("alert");
    expect(alertBanner).toHaveTextContent("Stale monitor data:");
    expect(alertBanner).toHaveTextContent("nhc-current-storms (45m ago)");
    expect(alertBanner).toHaveTextContent("nws-alerts-point (2h 15m ago)");

    const source = MockEventSource.instances[0]!;
    act(() => {
      source.emitError();
    });

    expect(screen.getByRole("status")).toHaveTextContent("Reconnecting…");

    act(() => {
      source.emitOpen();
    });

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("reads the CSP nonce property from the meta element and sets globalThis.__webpack_nonce__", () => {
    const meta = document.createElement("meta");
    meta.setAttribute("property", "csp-nonce");
    meta.nonce = "nonce-test-token-42";
    document.head.appendChild(meta);

    try {
      const nonce = initCspNonce(document);
      expect(nonce).toBe("nonce-test-token-42");
      expect(globalThis.__webpack_nonce__).toBe("nonce-test-token-42");
    } finally {
      meta.remove();
    }
  });
});
