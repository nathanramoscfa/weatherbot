// frontend/src/pages/Storms.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import stormsFixture from "../test/fixtures/storms.json";
import { asSchema, type JsonFixture } from "./format.ts";
import { Storms } from "./Storms.tsx";

const TYPED_STORMS = asSchema<components["schemas"]["StormsResponse"]>(
  stormsFixture satisfies JsonFixture<components["schemas"]["StormsResponse"]>,
);

describe("Storms", () => {
  it("renders active storms, outlook areas, and wind-speed probabilities from storms.json", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.storms(), TYPED_STORMS);

    render(
      <QueryClientProvider client={queryClient}>
        <Storms />
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole("heading", { name: "Storms" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("article", { name: "Simon (EP202026)" }),
    ).toBeInTheDocument();
    expect(screen.getByText("85 kt")).toBeInTheDocument();
    expect(screen.getByText("969 mb")).toBeInTheDocument();
    expect(screen.getByText("300 deg at 3 mph")).toBeInTheDocument();
    expect(
      screen.getByText(/earliest reasonable arrival times/i),
    ).toBeInTheDocument();

    // Outlook areas
    expect(screen.getAllByText("Atlantic").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Pacific").length).toBeGreaterThan(0);

    // Wind probabilities
    expect(screen.getByText("34 kt threshold")).toBeInTheDocument();
    expect(screen.getByText("50 kt threshold")).toBeInTheDocument();
    expect(screen.getByText("64 kt threshold")).toBeInTheDocument();
  });

  it("renders the quiet-tropics empty state when no active storms are present", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.storms(), {
      ...TYPED_STORMS,
      storms: [],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <Storms />
      </QueryClientProvider>,
    );

    expect(
      screen.getByText(/No active storm in the latest NHC roster/i),
    ).toBeInTheDocument();
  });
});
