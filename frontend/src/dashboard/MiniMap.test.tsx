// frontend/src/dashboard/MiniMap.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import mapFixture from "../test/fixtures/map.json";
import { MiniMap } from "./MiniMap.tsx";

const TYPED_MAP = asSchema<components["schemas"]["MapResponse"]>(
  mapFixture satisfies JsonFixture<components["schemas"]["MapResponse"]>,
);

describe("MiniMap", () => {
  it("renders the mini-map container with queryKeys.map() data, storm count, snapshot age, and a link to /map", () => {
    const queryClient = createAppQueryClient();
    queryClient.setQueryData(queryKeys.map(), TYPED_MAP);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <MiniMap ageSeconds={240} timeZone="America/New_York" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("dashboard-mini-map")).toBeInTheDocument();
    expect(screen.getByTestId("mini-map-container")).toBeInTheDocument();
    expect(screen.getByTestId("mini-map-caption")).toHaveTextContent(
      "1 active storm · Snapshot 4 min old",
    );
    const openMapLink = screen.getByRole("link", { name: "Open the map" });
    expect(openMapLink).toHaveAttribute("href", "/map");
  });
});
