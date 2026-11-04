// frontend/src/settings/LocationManager.test.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client.ts";
import type { components } from "../api/schema.ts";
import { createAppQueryClient } from "../main.tsx";
import locationsFixture from "../test/fixtures/locations.json";
import { asSchema, type JsonFixture } from "../pages/format.ts";
import {
  formatLocationCoverage,
  LocationManager,
  type LocationResponse,
} from "./LocationManager.tsx";

const TYPED_LOCATIONS = asSchema<components["schemas"]["LocationsResponse"]>(
  locationsFixture satisfies JsonFixture<
    components["schemas"]["LocationsResponse"]
  >,
);

const MARINE_LOCATION: LocationResponse = {
  ...TYPED_LOCATIONS.locations[0]!,
  name: "Coastal Buoy",
  nws: {
    cwa: "MFL",
    forecast_zone: "AMZ630",
    county_zone: null,
    time_zone: "America/New_York",
    city: "Miami",
    state: "FL",
  },
};

describe("LocationManager", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders coverage in words for county-covered, marine no-county, and outside-NWS locations", () => {
    const queryClient = createAppQueryClient();
    const list: LocationResponse[] = [
      ...TYPED_LOCATIONS.locations,
      MARINE_LOCATION,
    ];

    render(
      <QueryClientProvider client={queryClient}>
        <LocationManager locations={list} />
      </QueryClientProvider>,
    );

    expect(
      screen.getByText(
        /NWS MFL, zones FLZ173 and FLC086 · America\/New_York/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /NWS MFL, zone AMZ630 \(NWS marine zone, no county\) · America\/New_York/,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Outside NWS coverage: NHC breakpoints/),
    ).toBeInTheDocument();
    expect(formatLocationCoverage(MARINE_LOCATION)).toContain(
      "NWS marine zone, no county",
    );
  });

  it("sends no request while typing a place, searches on submit, keeps the location name empty until typed, and adds the chosen candidate", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    const postSpy = vi.spyOn(apiClient, "POST");

    render(
      <QueryClientProvider client={queryClient}>
        <LocationManager locations={TYPED_LOCATIONS.locations} />
      </QueryClientProvider>,
    );

    const placeInput = screen.getByLabelText("Place search");
    await user.type(placeInput, "Nassau, Bahamas");
    expect(postSpy).not.toHaveBeenCalled();

    postSpy.mockResolvedValueOnce({
      data: {
        candidates: [
          {
            display_name: "Nassau, New Providence, The Bahamas",
            name: "Nassau",
            latitude: 25.08,
            longitude: -77.34,
            country_code: "BS",
            category: "place",
            kind: "city",
          },
          {
            display_name: "Nassau County, Florida, United States",
            name: "Nassau County",
            latitude: 30.61,
            longitude: -81.77,
            country_code: "US",
            category: "boundary",
            kind: "administrative",
          },
        ],
        attribution:
          "Search by OpenStreetMap Nominatim, © OpenStreetMap contributors",
      },
      response: new Response(null, { status: 200 }),
    });

    const searchBtn = screen.getByRole("button", { name: "Search" });
    await user.click(searchBtn);

    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledWith("/api/locations/search", {
      body: { query: "Nassau, Bahamas" },
    });
    expect(searchBtn).toBeDisabled();

    expect(
      screen.getByText(
        "Search by OpenStreetMap Nominatim, © OpenStreetMap contributors",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/This label appears in phone notifications/i),
    ).toBeInTheDocument();

    const radio = screen.getByRole("radio", {
      name: "Nassau, New Providence, The Bahamas",
    });
    await user.click(radio);

    // Location name starts empty and is never filled from the candidate
    const nameInput = screen.getByLabelText("Location name");
    expect(nameInput).toHaveValue("");

    const addBtn = screen.getByRole("button", { name: "Add location" });
    await user.click(addBtn);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a location name and valid decimal latitude and longitude.",
    );
    expect(postSpy).toHaveBeenCalledTimes(1);

    postSpy.mockResolvedValueOnce({
      data: {
        ...TYPED_LOCATIONS.locations[1]!,
        name: "Nassau",
      },
      response: new Response(null, { status: 201 }),
    });

    await user.type(nameInput, "Nassau");
    await user.click(addBtn);

    expect(postSpy).toHaveBeenLastCalledWith("/api/locations", {
      body: {
        name: "Nassau",
        latitude: 25.08,
        longitude: -77.34,
        polygon: null,
      },
    });
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        'Added location "Nassau".',
      );
    });
  });

  it("submits POST /api/locations from the coordinates disclosure and shows plain messages on 409, 422, and 502", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    const postSpy = vi.spyOn(apiClient, "POST");

    render(
      <QueryClientProvider client={queryClient}>
        <LocationManager locations={TYPED_LOCATIONS.locations} />
      </QueryClientProvider>,
    );

    await user.click(screen.getByText("Enter coordinates instead"));

    const nameInput = screen.getByLabelText("Location name");
    const latInput = screen.getByLabelText("Latitude");
    const lonInput = screen.getByLabelText("Longitude");
    const addBtn = screen.getByRole("button", { name: "Add location" });

    // 1. 409 Conflict
    postSpy.mockResolvedValueOnce({
      data: undefined,
      response: new Response(null, { status: 409 }),
    });

    await user.type(nameInput, "Miami-Dade County Hall");
    await user.type(latInput, "25.78");
    await user.type(lonInput, "-80.20");
    await user.click(addBtn);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "A location with that name already exists (/api/locations returned HTTP 409).",
    );

    // 2. 422 Unprocessable Entity
    postSpy.mockResolvedValueOnce({
      data: undefined,
      response: new Response(null, { status: 422 }),
    });
    await user.click(addBtn);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Invalid location parameters or zone polygon requested outside NWS coverage (/api/locations returned HTTP 422).",
    );

    // 3. 502 Bad Gateway with field detail
    postSpy.mockResolvedValueOnce({
      data: undefined,
      error: {
        detail: "nws-points schema error: the points answer: 'county' is missing",
      } as never,
      response: new Response(null, { status: 502 }),
    });
    await user.click(addBtn);

    expect(screen.getByRole("alert")).toHaveTextContent(
      "nws-points schema error: the points answer: 'county' is missing (/api/locations returned HTTP 502).",
    );

    // 4. 201 Created
    postSpy.mockResolvedValueOnce({
      data: TYPED_LOCATIONS.locations[0]!,
      response: new Response(null, { status: 201 }),
    });
    await user.click(addBtn);

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        'Added location "Miami-Dade County Hall".',
      );
    });
  });

  it("removes a location behind a Radix AlertDialog warning that its history goes with it", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    const postSpy = vi.spyOn(apiClient, "POST");

    render(
      <QueryClientProvider client={queryClient}>
        <LocationManager locations={TYPED_LOCATIONS.locations} />
      </QueryClientProvider>,
    );

    const card = screen.getByRole("article", {
      name: "Miami-Dade County Hall",
    });
    await user.click(within(card).getByRole("button", { name: "Remove" }));

    const dialog = await screen.findByRole("alertdialog", {
      name: "Remove Miami-Dade County Hall?",
    });
    expect(dialog).toHaveTextContent(/history goes with it/i);

    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(postSpy).not.toHaveBeenCalled();

    await user.click(within(card).getByRole("button", { name: "Remove" }));
    postSpy.mockResolvedValueOnce({
      data: { removed: "Miami-Dade County Hall" },
      response: new Response(null, { status: 200 }),
    });
    await user.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", {
        name: "Remove location",
      }),
    );

    expect(postSpy).toHaveBeenCalledWith("/api/locations/remove", {
      body: { location: "Miami-Dade County Hall" },
    });
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent(
        'Removed location "Miami-Dade County Hall".',
      );
    });
  });

  it("submits PUT /api/locations/preferences when toggling Toast, Browser, Phone, or changing Phone minimum level, and disables the level select when Phone is off", async () => {
    const user = userEvent.setup();
    const queryClient = createAppQueryClient();
    const putSpy = vi.spyOn(apiClient, "PUT").mockResolvedValue({
      data: TYPED_LOCATIONS.locations[0]!,
      response: new Response(null, { status: 200 }),
    });

    const customLocations: LocationResponse[] = [
      TYPED_LOCATIONS.locations[0]!,
      {
        ...TYPED_LOCATIONS.locations[1]!,
        preferences: {
          toast: true,
          browser: true,
          phone: false,
          phone_min_level: 3,
        },
      },
    ];

    render(
      <QueryClientProvider client={queryClient}>
        <LocationManager locations={customLocations} />
      </QueryClientProvider>,
    );

    const miamiCard = screen.getByRole("article", {
      name: "Miami-Dade County Hall",
    });
    const nassauCard = screen.getByRole("article", {
      name: "Parliament Square",
    });

    expect(
      within(nassauCard).getByLabelText("Phone minimum level"),
    ).toBeDisabled();

    await user.click(within(miamiCard).getByRole("switch", { name: "Toast" }));
    expect(putSpy).toHaveBeenLastCalledWith("/api/locations/preferences", {
      body: {
        location: "Miami-Dade County Hall",
        preferences: {
          toast: false,
          browser: true,
          phone: true,
          phone_min_level: 2,
        },
      },
    });

    await user.selectOptions(
      within(miamiCard).getByLabelText("Phone minimum level"),
      "4",
    );
    expect(putSpy).toHaveBeenLastCalledWith("/api/locations/preferences", {
      body: {
        location: "Miami-Dade County Hall",
        preferences: {
          toast: true,
          browser: true,
          phone: true,
          phone_min_level: 4,
        },
      },
    });
  });
});
