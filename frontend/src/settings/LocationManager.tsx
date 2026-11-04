// frontend/src/settings/LocationManager.tsx
import { useQueryClient } from "@tanstack/react-query";
import { MapPin } from "lucide-react";
import { AlertDialog } from "radix-ui";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { apiClient } from "../api/client.ts";
import { queryKeys } from "../api/keys.ts";
import type { components } from "../api/schema.ts";
import {
  formatBothTimes,
  formatBreakpointSpan,
  formatRouteError,
} from "../pages/format.ts";

export type LocationResponse = components["schemas"]["LocationResponse"];
export type LocationPreferencesResponse =
  components["schemas"]["LocationPreferencesResponse"];
export type LocationSearchCandidateResponse =
  components["schemas"]["LocationSearchCandidateResponse"];
export type PolygonKind = "county" | "forecast";

const DEFAULT_PREFERENCES: LocationPreferencesResponse = {
  toast: true,
  browser: true,
  phone: true,
  phone_min_level: 2,
};

const PHONE_MIN_LEVEL_OPTIONS: ReadonlyArray<{
  readonly level: number;
  readonly label: string;
}> = [
  { level: 2, label: "Level 2 — Watch / Advisory" },
  { level: 3, label: "Level 3 — Prepare" },
  { level: 4, label: "Level 4 — Act Now" },
  { level: 5, label: "Level 5 — Extreme Threat" },
];

const SEARCH_COOLDOWN_MS = 2000;
const DEFAULT_ATTRIBUTION =
  "Search by OpenStreetMap Nominatim, © OpenStreetMap contributors";

interface Feedback {
  readonly kind: "success" | "error";
  readonly text: string;
}

async function extractErrorDetail(
  error: unknown,
  response: Response,
): Promise<string | null> {
  if (
    typeof error === "object" &&
    error !== null &&
    "detail" in error &&
    typeof error.detail === "string"
  ) {
    return error.detail;
  }
  try {
    const raw: unknown = await response.clone().json();
    if (
      typeof raw === "object" &&
      raw !== null &&
      "detail" in raw &&
      typeof raw.detail === "string"
    ) {
      return raw.detail;
    }
  } catch {
    // Response had no JSON body
  }
  return null;
}

export function formatLocationCoverage(loc: LocationResponse): string {
  if (!loc.nws) {
    return "Outside NWS coverage: NHC breakpoints";
  }
  if (loc.nws.county_zone) {
    return `NWS ${loc.nws.cwa}, zones ${loc.nws.forecast_zone} and ${loc.nws.county_zone} · ${loc.nws.time_zone}`;
  }
  return `NWS ${loc.nws.cwa}, zone ${loc.nws.forecast_zone} (NWS marine zone, no county) · ${loc.nws.time_zone}`;
}

export interface LocationManagerProps {
  readonly locations: ReadonlyArray<LocationResponse>;
}

export function LocationManager({ locations }: LocationManagerProps) {
  const queryClient = useQueryClient();

  const [placeQuery, setPlaceQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchCooldown, setSearchCooldown] = useState(false);
  const [candidates, setCandidates] = useState<
    ReadonlyArray<LocationSearchCandidateResponse>
  >([]);
  const [selectedCandidateIdx, setSelectedCandidateIdx] = useState<
    number | null
  >(null);
  const [hasSearched, setHasSearched] = useState(false);
  const [attribution, setAttribution] = useState(DEFAULT_ATTRIBUTION);
  const [searchFeedback, setSearchFeedback] = useState<Feedback | null>(null);
  const cooldownTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [locName, setLocName] = useState("");
  const [locLat, setLocLat] = useState("");
  const [locLon, setLocLon] = useState("");
  const [locPolygon, setLocPolygon] = useState<"" | PolygonKind>("");
  const [locSubmitting, setLocSubmitting] = useState(false);
  const [locFeedback, setLocFeedback] = useState<Feedback | null>(null);

  const [removingName, setRemovingName] = useState<string | null>(null);
  const [savingPrefsName, setSavingPrefsName] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (cooldownTimerRef.current !== null) {
        clearTimeout(cooldownTimerRef.current);
      }
    };
  }, []);

  const startSearchCooldown = () => {
    setSearchCooldown(true);
    if (cooldownTimerRef.current !== null) {
      clearTimeout(cooldownTimerRef.current);
    }
    cooldownTimerRef.current = setTimeout(() => {
      setSearchCooldown(false);
      cooldownTimerRef.current = null;
    }, SEARCH_COOLDOWN_MS);
  };

  const invalidateLocationViews = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.locations() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.assessments() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.map() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.alerts() }),
      queryClient.invalidateQueries({ queryKey: queryKeys.timeline() }),
    ]);
  };

  const handleSearch = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSearchFeedback(null);

    const trimmed = placeQuery.trim();
    if (trimmed.length < 3) {
      setSearchFeedback({
        kind: "error",
        text: "Enter at least 3 characters to search for a place.",
      });
      return;
    }

    setSearching(true);
    startSearchCooldown();
    try {
      const { data, error, response } = await apiClient.POST(
        "/api/locations/search",
        {
          body: { query: trimmed },
        },
      );
      if (response.ok && data) {
        setCandidates(data.candidates);
        setAttribution(data.attribution || DEFAULT_ATTRIBUTION);
        setHasSearched(true);
        setSelectedCandidateIdx(data.candidates.length === 1 ? 0 : null);
        return;
      }
      if (response.status === 429) {
        setSearchFeedback({
          kind: "error",
          text: "Please wait a moment before searching again (/api/locations/search returned HTTP 429).",
        });
        return;
      }
      const detail = await extractErrorDetail(error, response);
      if (detail) {
        setSearchFeedback({
          kind: "error",
          text: `${detail} (/api/locations/search returned HTTP ${String(response.status)}).`,
        });
      } else {
        setSearchFeedback({
          kind: "error",
          text: formatRouteError("/api/locations/search", response.status),
        });
      }
    } catch {
      setSearchFeedback({
        kind: "error",
        text: formatRouteError("/api/locations/search"),
      });
    } finally {
      setSearching(false);
    }
  };

  const handleAddLocation = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLocFeedback(null);

    const trimmedName = locName.trim();
    const hasManualCoords = locLat.trim() !== "" || locLon.trim() !== "";
    const selectedCandidate =
      selectedCandidateIdx !== null && selectedCandidateIdx >= 0
        ? (candidates.at(selectedCandidateIdx) ?? null)
        : null;

    let latNum = NaN;
    let lonNum = NaN;
    if (hasManualCoords) {
      if (locLat.trim() !== "" && locLon.trim() !== "") {
        latNum = Number(locLat);
        lonNum = Number(locLon);
      }
    } else if (selectedCandidate !== null) {
      latNum = selectedCandidate.latitude;
      lonNum = selectedCandidate.longitude;
    }

    if (!trimmedName || !Number.isFinite(latNum) || !Number.isFinite(lonNum)) {
      setLocFeedback({
        kind: "error",
        text: "Enter a location name and valid decimal latitude and longitude.",
      });
      return;
    }

    setLocSubmitting(true);
    try {
      const { data, error, response } = await apiClient.POST("/api/locations", {
        body: {
          name: trimmedName,
          latitude: latNum,
          longitude: lonNum,
          polygon: locPolygon === "" ? null : locPolygon,
        },
      });

      if (response.status === 201 && data) {
        setLocName("");
        setLocLat("");
        setLocLon("");
        setLocPolygon("");
        setSelectedCandidateIdx(null);
        setCandidates([]);
        setHasSearched(false);
        setPlaceQuery("");
        setLocFeedback({
          kind: "success",
          text: `Added location "${data.name}".`,
        });
        await invalidateLocationViews();
        return;
      }

      if (response.status === 409) {
        setLocFeedback({
          kind: "error",
          text: "A location with that name already exists (/api/locations returned HTTP 409).",
        });
      } else if (response.status === 422) {
        const detail = await extractErrorDetail(error, response);
        setLocFeedback({
          kind: "error",
          text: detail
            ? `${detail} (/api/locations returned HTTP 422).`
            : "Invalid location parameters or zone polygon requested outside NWS coverage (/api/locations returned HTTP 422).",
        });
      } else if (response.status === 502) {
        const detail = await extractErrorDetail(error, response);
        setLocFeedback({
          kind: "error",
          text: detail
            ? `${detail} (/api/locations returned HTTP 502).`
            : formatRouteError("/api/locations", response.status),
        });
      } else {
        setLocFeedback({
          kind: "error",
          text: formatRouteError("/api/locations", response.status),
        });
      }
    } catch {
      setLocFeedback({
        kind: "error",
        text: formatRouteError("/api/locations"),
      });
    } finally {
      setLocSubmitting(false);
    }
  };

  const handleUpdatePreferences = async (
    loc: LocationResponse,
    next: LocationPreferencesResponse,
  ) => {
    setSavingPrefsName(loc.name);
    setLocFeedback(null);
    try {
      const { data, response } = await apiClient.PUT(
        "/api/locations/preferences",
        {
          body: {
            location: loc.name,
            preferences: next,
          },
        },
      );
      if (response.ok && data) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.locations() });
        return;
      }
      setLocFeedback({
        kind: "error",
        text: formatRouteError("/api/locations/preferences", response.status),
      });
    } catch {
      setLocFeedback({
        kind: "error",
        text: formatRouteError("/api/locations/preferences"),
      });
    } finally {
      setSavingPrefsName(null);
    }
  };

  const handleRemoveLocation = async (name: string) => {
    setRemovingName(name);
    setLocFeedback(null);
    try {
      const { data, response } = await apiClient.POST("/api/locations/remove", {
        body: { location: name },
      });
      if (response.ok && data) {
        setLocFeedback({
          kind: "success",
          text: `Removed location "${data.removed}".`,
        });
        await invalidateLocationViews();
        return;
      }
      if (response.status === 409) {
        setLocFeedback({
          kind: "error",
          text: "A monitor cycle is in progress; try removing the location again in a moment (/api/locations/remove returned HTTP 409).",
        });
      } else {
        setLocFeedback({
          kind: "error",
          text: formatRouteError("/api/locations/remove", response.status),
        });
      }
    } catch {
      setLocFeedback({
        kind: "error",
        text: formatRouteError("/api/locations/remove"),
      });
    } finally {
      setRemovingName(null);
    }
  };

  return (
    <section
      aria-labelledby="locations-heading"
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-xs sm:p-5 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex items-center gap-2">
        <MapPin
          className="h-5 w-5 shrink-0 text-sky-600 dark:text-sky-400"
          aria-hidden="true"
        />
        <h2
          id="locations-heading"
          className="text-base font-bold text-slate-900 dark:text-slate-100"
        >
          Watched Locations
        </h2>
      </div>

      {locations.length > 0 && (
        <div className="mt-3 space-y-2">
          {locations.map((loc) => (
            <article
              key={loc.name}
              aria-label={loc.name}
              className="rounded-md border border-slate-200 bg-slate-50/70 p-3 text-xs dark:border-slate-800 dark:bg-slate-800/40"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-bold text-slate-900 dark:text-slate-100">
                  {loc.name}
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-slate-600 dark:text-slate-300">
                    {String(loc.latitude)}, {String(loc.longitude)}
                  </span>
                  <AlertDialog.Root>
                    <AlertDialog.Trigger asChild>
                      <button
                        type="button"
                        disabled={removingName === loc.name}
                        className="rounded-md border border-red-300 bg-white px-2.5 py-1 text-xs font-semibold text-red-700 hover:bg-red-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 disabled:opacity-60 dark:border-red-800 dark:bg-slate-900 dark:text-red-300 dark:hover:bg-red-950/50"
                      >
                        Remove
                      </button>
                    </AlertDialog.Trigger>
                    <AlertDialog.Portal>
                      <AlertDialog.Overlay className="fixed inset-0 z-40 bg-slate-950/50" />
                      <AlertDialog.Content className="fixed top-1/2 left-1/2 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-slate-200 bg-white p-4 text-xs text-slate-800 shadow-lg dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
                        <AlertDialog.Title className="text-sm font-bold text-slate-900 dark:text-slate-100">
                          Remove {loc.name}?
                        </AlertDialog.Title>
                        <AlertDialog.Description className="mt-2">
                          Removing <strong>{loc.name}</strong> deletes its
                          stored assessment history, alerts, notifications, and
                          geocoding records. Its history goes with it and cannot
                          be restored.
                        </AlertDialog.Description>
                        <div className="mt-4 flex justify-end gap-2">
                          <AlertDialog.Cancel asChild>
                            <button
                              type="button"
                              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 font-semibold text-slate-800 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                            >
                              Cancel
                            </button>
                          </AlertDialog.Cancel>
                          <AlertDialog.Action asChild>
                            <button
                              type="button"
                              onClick={() => void handleRemoveLocation(loc.name)}
                              className="rounded-md bg-red-600 px-3 py-1.5 font-semibold text-white hover:bg-red-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 dark:bg-red-500 dark:text-slate-950"
                            >
                              Remove location
                            </button>
                          </AlertDialog.Action>
                        </div>
                      </AlertDialog.Content>
                    </AlertDialog.Portal>
                  </AlertDialog.Root>
                </div>
              </div>
              <div className="mt-1 text-slate-600 dark:text-slate-400">
                {loc.display_name ? `${loc.display_name} · ` : ""}
                {formatLocationCoverage(loc)}
                {loc.has_polygon ? " · Zone polygon stored" : ""}
              </div>
              <div className="mt-1 text-slate-600 dark:text-slate-400">
                Breakpoint span: {formatBreakpointSpan(loc.breakpoint_span)} ·
                Evacuation order:{" "}
                <strong>{loc.evacuation_order_in_effect ? "On" : "Off"}</strong>
                {loc.evacuation_order_set_at
                  ? ` (since ${formatBothTimes(loc.evacuation_order_set_at, loc.nws?.time_zone)})`
                  : ""}
              </div>
              {(() => {
                const prefs = loc.preferences ?? DEFAULT_PREFERENCES;
                const busy = savingPrefsName === loc.name;
                return (
                  <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-slate-200/80 pt-2 dark:border-slate-700/70">
                    <span className="font-medium text-slate-700 dark:text-slate-300">
                      Notifications:
                    </span>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={prefs.toast}
                      aria-label="Toast"
                      disabled={busy}
                      onClick={() =>
                        void handleUpdatePreferences(loc, {
                          ...prefs,
                          toast: !prefs.toast,
                        })
                      }
                      className={`rounded px-2 py-0.5 font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:opacity-60 ${
                        prefs.toast
                          ? "bg-sky-600 text-white hover:bg-sky-700 dark:bg-sky-500 dark:text-slate-950"
                          : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                      }`}
                    >
                      Toast: {prefs.toast ? "On" : "Off"}
                    </button>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={prefs.browser}
                      aria-label="Browser"
                      disabled={busy}
                      onClick={() =>
                        void handleUpdatePreferences(loc, {
                          ...prefs,
                          browser: !prefs.browser,
                        })
                      }
                      className={`rounded px-2 py-0.5 font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:opacity-60 ${
                        prefs.browser
                          ? "bg-sky-600 text-white hover:bg-sky-700 dark:bg-sky-500 dark:text-slate-950"
                          : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                      }`}
                    >
                      Browser: {prefs.browser ? "On" : "Off"}
                    </button>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={prefs.phone}
                      aria-label="Phone"
                      disabled={busy}
                      onClick={() =>
                        void handleUpdatePreferences(loc, {
                          ...prefs,
                          phone: !prefs.phone,
                        })
                      }
                      className={`rounded px-2 py-0.5 font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:opacity-60 ${
                        prefs.phone
                          ? "bg-sky-600 text-white hover:bg-sky-700 dark:bg-sky-500 dark:text-slate-950"
                          : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300"
                      }`}
                    >
                      Phone: {prefs.phone ? "On" : "Off"}
                    </button>
                    <label className="inline-flex items-center gap-1.5 text-slate-700 dark:text-slate-300">
                      <span>Phone minimum level</span>
                      <select
                        aria-label="Phone minimum level"
                        disabled={!prefs.phone || busy}
                        value={String(prefs.phone_min_level)}
                        onChange={(e) =>
                          void handleUpdatePreferences(loc, {
                            ...prefs,
                            phone_min_level: Number(e.target.value),
                          })
                        }
                        className="rounded border border-slate-300 bg-white px-2 py-0.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                      >
                        {PHONE_MIN_LEVEL_OPTIONS.map((opt) => (
                          <option key={opt.level} value={String(opt.level)}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                );
              })()}
            </article>
          ))}
        </div>
      )}

      <div className="mt-4 space-y-4 border-t border-slate-200 pt-4 text-xs dark:border-slate-800">
        <h3 className="font-semibold text-slate-900 dark:text-slate-100">
          Add a watched location
        </h3>

        <form
          onSubmit={(e) => void handleSearch(e)}
          className="space-y-2"
          aria-label="Search for a place"
        >
          <label
            htmlFor="location-place-input"
            className="block font-medium text-slate-700 dark:text-slate-300"
          >
            Place search
          </label>
          <div className="flex flex-wrap gap-2">
            <input
              id="location-place-input"
              aria-label="Place search"
              type="text"
              value={placeQuery}
              onChange={(e) => setPlaceQuery(e.target.value)}
              placeholder="e.g. Nassau, Bahamas"
              className="min-w-56 flex-1 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <button
              type="submit"
              disabled={searching || searchCooldown}
              className="inline-flex items-center rounded-md border border-slate-300 bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-800 hover:bg-slate-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:hover:bg-slate-700"
            >
              Search
            </button>
          </div>
          {searchFeedback && (
            <div
              role={searchFeedback.kind === "error" ? "alert" : "status"}
              className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
            >
              {searchFeedback.text}
            </div>
          )}
          {hasSearched && (
            <div className="space-y-2 rounded-md border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-800/40">
              {candidates.length === 0 ? (
                <p className="text-slate-600 dark:text-slate-400">
                  No matching places found.
                </p>
              ) : (
                <fieldset className="space-y-1.5">
                  <legend className="font-medium text-slate-800 dark:text-slate-200">
                    Matching places
                  </legend>
                  {candidates.map((candidate, idx) => (
                    <label
                      key={`${candidate.display_name}-${String(idx)}`}
                      className="flex cursor-pointer items-start gap-2 rounded px-1.5 py-1 hover:bg-slate-100 dark:hover:bg-slate-800"
                    >
                      <input
                        type="radio"
                        name="location-candidate"
                        checked={selectedCandidateIdx === idx}
                        onChange={() => {
                          setSelectedCandidateIdx(idx);
                          setLocLat("");
                          setLocLon("");
                        }}
                        className="mt-0.5"
                      />
                      <span className="text-slate-800 dark:text-slate-200">
                        {candidate.display_name}
                      </span>
                    </label>
                  ))}
                </fieldset>
              )}
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                {attribution}
              </p>
            </div>
          )}
        </form>

        <form
          onSubmit={(e) => void handleAddLocation(e)}
          className="space-y-3"
        >
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label
                htmlFor="location-name-input"
                className="block font-medium text-slate-700 dark:text-slate-300"
              >
                Location name
              </label>
              <input
                id="location-name-input"
                aria-label="Location name"
                type="text"
                value={locName}
                onChange={(e) => setLocName(e.target.value)}
                placeholder="e.g. Home"
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
              <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">
                This label appears in phone notifications, AI requests, logs,
                and reports. Use something like Home, not an address.
              </p>
            </div>
            <div>
              <label
                htmlFor="location-polygon-select"
                className="block font-medium text-slate-700 dark:text-slate-300"
              >
                Zone polygon
              </label>
              <select
                id="location-polygon-select"
                aria-label="Zone polygon"
                value={locPolygon}
                onChange={(e) =>
                  setLocPolygon(e.target.value as "" | PolygonKind)
                }
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              >
                <option value="">None (point only)</option>
                <option value="forecast">Forecast zone</option>
                <option value="county">County zone</option>
              </select>
            </div>
          </div>

          <details className="rounded-md border border-slate-200 bg-slate-50/50 p-2.5 dark:border-slate-800 dark:bg-slate-800/30">
            <summary className="cursor-pointer font-medium text-slate-700 dark:text-slate-300">
              Enter coordinates instead
            </summary>
            <div className="mt-2.5 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="location-lat-input"
                  className="block font-medium text-slate-700 dark:text-slate-300"
                >
                  Latitude
                </label>
                <input
                  id="location-lat-input"
                  aria-label="Latitude"
                  type="text"
                  inputMode="decimal"
                  value={locLat}
                  onChange={(e) => setLocLat(e.target.value)}
                  placeholder="-90 to 90"
                  className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                />
              </div>
              <div>
                <label
                  htmlFor="location-lon-input"
                  className="block font-medium text-slate-700 dark:text-slate-300"
                >
                  Longitude
                </label>
                <input
                  id="location-lon-input"
                  aria-label="Longitude"
                  type="text"
                  inputMode="decimal"
                  value={locLon}
                  onChange={(e) => setLocLon(e.target.value)}
                  placeholder="-180 to 180"
                  className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                />
              </div>
            </div>
          </details>

          <div>
            <button
              type="submit"
              disabled={locSubmitting}
              className="inline-flex items-center rounded-md bg-sky-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 disabled:opacity-60 dark:bg-sky-500 dark:text-slate-950"
            >
              Add location
            </button>
          </div>

          {locFeedback && (
            <div
              role={locFeedback.kind === "error" ? "alert" : "status"}
              className={`rounded-md border px-3 py-2 text-xs ${
                locFeedback.kind === "error"
                  ? "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950/60 dark:text-red-200"
                  : "border-emerald-300 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-200"
              }`}
            >
              {locFeedback.text}
            </div>
          )}
        </form>
      </div>
    </section>
  );
}
