// frontend/src/pages/Alerts.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import alertsFixture from "../test/fixtures/alerts.json";
import { Alerts } from "./Alerts.tsx";
import { asSchema, type JsonFixture } from "./format.ts";

const TYPED_ALERTS = asSchema<components["schemas"]["AlertsResponse"]>(
  alertsFixture satisfies JsonFixture<components["schemas"]["AlertsResponse"]>,
);

describe("Alerts", () => {
  it("renders covering NWS alerts, county-zone context alerts, and watch-warning segments from alerts.json", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.alerts(), TYPED_ALERTS);

    render(
      <QueryClientProvider client={queryClient}>
        <Alerts />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Alerts" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("article", { name: "Miami-Dade County Hall" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("article", { name: "Parliament Square" }),
    ).toBeInTheDocument();

    // Covering NWS alert for Miami-Dade
    expect(screen.getByText("Rip Current Statement")).toBeInTheDocument();
    expect(screen.getByText("Covers this location")).toBeInTheDocument();

    // County-zone context alert for Miami-Dade
    expect(
      screen.getByText(
        /County-zone alerts outside this location's zones \(context only — never sets the threat level\)/i,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Coastal Flood Statement")).toBeInTheDocument();
    expect(
      screen.getByText("Does not cover this location (context)"),
    ).toBeInTheDocument();

    // Watch-warning segments for Nassau (outside NWS coverage)
    expect(
      screen.getByText(
        /The NWS does not cover Parliament Square; NHC's segments are its watches and warnings\./i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Hurricane Warning \(HWR\)/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Hurricane Watch \(HWA\)/i)).toBeInTheDocument();
  });
});
