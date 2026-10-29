<!-- docs/phase05-qa-findings.md -->
# Phase 5 QA Findings Ledger — Web App MVP

This ledger records every judgement call, verification receipt, source-drift observation, live smoke run, and carry-over disposition across Phase 5 (`v2.0.0-phase-5`). Every finding has a concrete disposition (fixed in-phase, assigned to a specific later phase and section, or tracked as a GitHub issue); none is left open without a destination.

## PR #56 — Phase 5 Roadmap

- **Summary:** Authored `docs/roadmap/phase05-roadmap.md` breaking Phase 5 (Web App MVP) into eight executable steps (`Step 1` through `Step 8`) with the V1–V8 post-implementation verification matrix, and updated `docs/roadmap/ROADMAP.md` (§2 "The CLI hosts the web app", §3 threat model for hostile browser pages, and Phase 5).
- **Key design decisions recorded:**
  - `weatherbot.cli` sits above `weatherbot.web` in the `layers` contract so `weatherbot serve` hosts the embedded FastAPI server while `weatherbot.web` imports only `weatherbot.services` and `weatherbot.models` (never `cli`, `sources`, or `engine`).
  - Loopback-only binding (`127.0.0.1`, `localhost`, `::1`) with pure ASGI guards (`SecurityHeadersMiddleware`, `TrustedHostMiddleware`, `FetchAndWriteGuardMiddleware`), per-response CSP nonce on `index.html`, no CORS headers, and `Cache-Control: no-store` on `/api/*`.
  - In-memory static asset map (`StaticBundle`) built once at startup so no request text ever reaches a filesystem call.
  - Node 24 LTS (`frontend/.nvmrc`), Vite 8, React 19, TypeScript 5.9, Tailwind CSS 4, TanStack Query 5, `openapi-typescript` + `openapi-fetch`, Radix UI, and Leaflet 1.9 used directly (not `react-leaflet`, whose Hippocratic License 2.1 is not OSI-approved) with exact pinned versions.
- **Disposition:** Merged in PR #56 (`56650fc`, `2026-10-25`).

## Step 1 — The web server inside `serve` (PR #61)

- **Summary:** Added `fastapi>=0.162.0`, `starlette>=1.10.0`, and `uvicorn>=0.54.0`; placed `weatherbot.cli` above `weatherbot.web` in `pyproject.toml`; implemented `WebSettings` (`[web]`), `create_app`, `guards.py`, `static_files.py`, `GET /api/health`, `WebServer`, `serve --open/--no-open`, `doctor`'s `web` check, `scripts/export_openapi.py`, and converted Phase 4's Check 46 to read `v2.0.0-phase-4:README.md`.
- **Findings & judgement calls:**
  - `WebState.database` holds `Database | None` from `weatherbot.services.persistence.database` rather than `sqlalchemy.Engine` directly so `weatherbot.web` never imports `sqlalchemy` under `"Only the services touch the database"`. Fixed in PR #61 and recorded in `docs/roadmap/phase05-roadmap.md`.
  - Wrapped `EmbeddedUvicornServer.serve()` in an inner task inside `WebServer.serve` so `SystemExit` raised by Uvicorn on a startup failure is caught and logged as a warning without terminating the monitor loop. Fixed in PR #61.
  - Monkeypatched `importlinter.cli._configure_logging` in `tests/test_architecture.py::test_import_contracts_are_kept` so `lint_imports()` does not disable `weatherbot.*` loggers for subsequent tests. Fixed in PR #61.
  - Closed the rotating file handler in `run_monitor_loop`'s `finally:` block after releasing `monitor.lock`. Fixed in PR #61.
- **Disposition:** Merged in PR #61 (`34142c5`, `2026-10-26`).

## Step 2 — The read API and the map's geometry (PR #62)

- **Summary:** Implemented all ten read routes (`GET /api/locations`, `/api/assessments`, `/api/storms`, `/api/alerts`, `/api/timeline`, `/api/notifications`, `/api/settings`, `/api/disclaimer`, `/api/map`, `/api/replay`, and `/api/replay/{atcf_id}/{advisory}`), `src/weatherbot/web/map_layers.py` (GeoJSON layer builder with antimeridian unwrapping, explicit `crs` without `wkt`, and bounded 8-snapshot LRU cache `SNAPSHOT_CACHE`), `ReplayCorpus.advisories(atcf_id)` and `ReplayCorpus.snapshot(atcf_id, advisory)`, `NotificationService.recent(limit)`, `serve --corpus`, and regenerated `docs/api/openapi.json`.
- **Findings & judgement calls:**
  - Shared the 8-snapshot LRU `SNAPSHOT_CACHE` (`CachedSnapshotBundle`) across `/api/map`, `/api/storms`, and `/api/alerts` so fetching all three decodes the latest snapshot once. Fixed in PR #62.
  - Typed `GeoJsonCrsResponse.datum` as `str | None = None` (`None` for `EPSG:4326`, `"D_Sphere"` for `native`) and omitted `wkt`. Fixed in PR #62.
  - Validated CLI `--corpus DIR` before acquiring `monitor.lock` so a bad path exits 2 immediately, whereas an invalid `[web] corpus` setting logs a `WARNING` and starts `serve` with `corpus=None`. Fixed in PR #62.
- **Disposition:** Merged in PR #62 (`86a1964`, `2026-10-27`).

## Step 3 — The event stream, browser notifications, and the API's actions (PR #63)

- **Summary:** Added `src/weatherbot/services/events.py` (`EventHub`, `HubEvent`, `Subscription`, `SubscriberLimitError`, `CycleWatcher`, `StalenessTimer`, `BrowserChannel`), `NotificationSettings.browser: bool = True` (`WEATHERBOT_NOTIFICATIONS_BROWSER`), `"browser"` in `CHANNEL_NAMES`, `GET /api/events` (`fastapi.sse.EventSourceResponse` annotated `AsyncIterable[StreamEvent]`), and `src/weatherbot/web/routes/actions.py` (`POST /api/locations`, `PUT /api/locations/evacuation`, `POST /api/cycles`, `POST /api/notifications/test`), plus `tests/live/test_web_live.py`.
- **Findings & judgement calls:**
  - `EventHub` enforces `MAX_SUBSCRIBERS = 16` (`503 Service Unavailable` on the 17th subscriber) and `MAX_QUEUE_SIZE = 100` (slow subscriber closed cleanly without affecting other subscribers), and performs loop-thread deduplication in `EventHub._publish_on_loop`. Fixed in PR #63.
  - `StreamEvent`, `EventKind`, and `QueryKey` schemas are explicitly injected into `components.schemas` by `scripts/export_openapi.py` so `openapi-typescript` generates named types for the SSE contract. Fixed in PR #63.
  - Shielded executor reads are drained on `CancelledError` in `CycleWatcher.poll()` and `StalenessTimer.refresh()` so SQLite connections close before shutdown. Fixed in PR #63.
- **Disposition:** Merged in PR #63 (`9efe407`, `2026-10-27`).

## Step 4 — The frontend chassis, its gate, and the wheel (PR #64)

- **Summary:** Created the `frontend/` workspace (Node 24 in `frontend/.nvmrc`, Vite 8.3.5, React 19.3.1, TypeScript 5.9.3, Tailwind CSS 4.3.3, TanStack Query 5.104.5, React Router 8.5.0 in data mode, Radix UI 1.8.1, `lucide-react` 1.61.0, `openapi-fetch` 0.17.0, `openapi-typescript` 7.13.0, Vitest 5.0.5, ESLint with `eslint-plugin-security`), generated `frontend/src/api/schema.d.ts`, implemented `apiClient`, `queryKeys`, `useEventStream`, `AppShell`, `ThemeMenu`, `ThreatLevelBadge`, `nonce.ts`, `theme.ts`, `public/theme-init.js`, `frontend/scripts/check-licenses.mjs`, and `scripts/smoke_installed_web.py`, and wired `frontend-lint` and `npm-audit` into `.pre-commit-config.yaml`, `ci.yml`, and `.github/dependabot.yml`.
- **Findings & judgement calls:**
  - Reconciled `docs/roadmap/phase05-roadmap.md` Step 4 `<task>` wording so `useEventStream` marks the stream connected on the first `hello` without refetching and invalidates all nine keys on a reconnect's `hello` (matching the Step 4 Goal, Test requirement, Acceptance Criteria, and Step 8 V5.3). Fixed in PR #64.
  - Checked `entry.identifier ?? entry.license` in `frontend/scripts/check-licenses.mjs` for Vite 8's `licenses.json` output, and resolved `Path(sys.executable).parent` before `Path(sys.executable).resolve().parent` in `scripts/smoke_installed_web.py` for POSIX `uv venv` symlinks. Fixed in PR #64.
- **Disposition:** Merged in PR #64 (`014bfbe`, `2026-10-27`).

## Step 5 — The dashboard and the pages (PR #65)

- **Summary:** Added `scripts/export_api_fixtures.py` and the twelve deterministic JSON fixtures under `frontend/src/test/fixtures/`, implemented `Dashboard.tsx`, `Storms.tsx`, `Alerts.tsx`, `Timeline.tsx`, `Settings.tsx`, `format.ts`, and `frontend/src/notifications/notify.ts`, and added component tests across all five pages and `notify.ts`.
- **Findings & judgement calls:**
  - `scripts/export_api_fixtures.py` rounds GeoJSON geometry coordinates in the exported test fixtures to 2 decimal places and replaces random UUIDs and paths with deterministic placeholders so `scripts/check_personal_data.py` rule R2 passes without exception rules. Fixed in PR #65.
  - Added `JsonFixture<T>` and `asSchema<T>` in `frontend/src/pages/format.ts` for compile-time fixture type checking under TypeScript `resolveJsonModule`. Fixed in PR #65.
  - `deliverBrowserNotification` in `frontend/src/notifications/notify.ts` is the sole caller of `new Notification(...)` and fires an OS Web Notification only when `event.kind === "notification"`, `event.display === true`, `readBrowserNotificationsEnabled()` is true, `Notification.permission === "granted"`, and `document.visibilityState === "hidden"`. Fixed in PR #65.
- **Disposition:** Merged in PR #65 (`a48d5a8`, `2026-10-27`).

## Step 6 — The map (PR #66)

- **Summary:** Pinned `leaflet` `1.9.4` and `@types/leaflet` `1.9.22` (ignoring `leaflet >= 2.0.0` in `.github/dependabot.yml`), implemented `frontend/src/map/layers.ts`, `frontend/src/map/useLeafletMap.ts`, and `frontend/src/map/MapView.tsx`, amended `docs/DATA_SOURCES.md` (§5.1 OpenStreetMap standard tile layer entry), and added unit and component tests in `frontend/src/map/layers.test.ts` and `frontend/src/map/MapView.test.tsx`.
- **Findings & judgement calls:**
  - `OSM_TILE_OPTIONS` sets `referrerPolicy: "strict-origin-when-cross-origin"` and `attribution: '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>'`, and `DEFAULT_ATLANTIC_CENTER` uses whole-number coordinates `[25, -65]` at zoom `4`. Fixed in PR #66.
  - All popup and tooltip content is built as DOM `HTMLElement` nodes using `document.createElement` and `textContent` (never string HTML), and legend swatches use Tailwind utility classes (`swatchClass`) so strict CSP `style-src 'self' 'nonce-...'` is respected without inline `style={{ ... }}`. Fixed in PR #66.
- **Disposition:** Merged in PR #66 (`6bbc386`, `2026-10-28`).

## Step 7 — The browser smoke, idle cost, and the operator's dashboard (PR #70)

- **Summary:** Added `scripts/serve_demo.py`, `scripts/measure_idle.py`, `frontend/playwright.config.ts`, `frontend/e2e/guard.ts`, `frontend/e2e/blank-tile.png`, `frontend/e2e/dashboard.spec.ts`, `frontend/e2e/map.spec.ts`, `frontend/e2e/screens.spec.ts`, and `frontend/e2e/idle.spec.ts`, wired the `browser` job into `.github/workflows/ci.yml` on `ubuntu-latest`, and deployed the built web app to the operator's Windows 11 machine (`\Weatherbot\serve` answering `http://127.0.0.1:8765/api/health` with `ui.present=True`, `index_sha256="44608164d969"`, `database.current=True`).
- **600 s idle CPU measurement receipt (`uv run python scripts/measure_idle.py` on the operator's Windows 11 machine):**
  - `idle measurement: window=600.1s server_cpu=0.4843% (2.906s) tab_cpu=0.0020% (0.012s) roster_polls=0 cycles=0 budget=<0.5%`
  - Both `serve_demo.py` (`0.4843% < 0.5%`, `2.906 s` `user + system` via `psutil`) and the Chromium dashboard tab (`0.0020% < 0.5%`, `0.012 s` CDP `Performance.getMetrics` `TaskDuration`) stayed strictly under the `0.5%` single-core idle budget over the `600.1 s` window after the `30 s` settle, with `0` roster polls and `0` cycles during the window.
- **Operator UX finding — forward geocoding (`City, State / Country` place search):**
  - During Step 7's live confirmation of the dashboard on `http://127.0.0.1:8765/settings`, the operator noted that adding a watched location currently requires entering raw decimal `Latitude` and `Longitude` rather than searching by `City, State / Country` (e.g., `Miami, FL`).
  - **Disposition:** Tracked in GitHub issue #71 (`https://github.com/nathanramoscfa/weatherbot/issues/71`) and assigned to **Phase 7 §7.3** (`docs/roadmap/ROADMAP.md` Phase 7 — "Locations and channels"), which adds Nominatim forward geocoding (`geocode-nominatim` `/search` with 1 req/s pacing and candidate disambiguation) for both `/settings`'s location setup and `weatherbot locations add --place` (retaining raw `Latitude` / `Longitude` as an explicit fallback).
- **Disposition:** Merged in PR #70 (`e452d77`, `2026-10-29`).

## Step 8 — QA & Verification Script (PR #72)

- **Summary:** Authored `scripts/verify_phase05.py` (53 static checks and 32 V1–V8 post-implementation verification matrix rows across `--fast`, `--py`, `--node`, `--ui`, `--live`, `--security`, `--all`, and `--post`, totaling 85 checks in `--post`), `tests/test_phase05_verification.py` (including in-memory deliverable mutation tests across Steps 1–7), appended `"05"` to `.github/workflows/phase-verify.yml` with conditional Node 24 setup before `--security`, updated `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `docs/roadmap/ROADMAP.md`, and `docs/roadmap/phase05-roadmap.md`, and recorded this ledger.
- **Phase 5 checks designed for Phase 6+ growth vs. exact checks requiring historical conversion:**
  - Most checks in `scripts/verify_phase05.py` are written by inclusion so Phase 6, 7, and 8 growth keeps them green without edits: route modules and OpenAPI paths (Checks 12, 13), `CHANNEL_NAMES` (Check 20, subset `{"log", "toast", "browser"}`), `QueryKey` values (Check 21, subset of the 9 Phase 5 keys), `frontend/package.json` scripts and dependencies (Checks 26, 27, 40), `frontend/src/pages/` files (Check 36), and `.github/workflows/phase-verify.yml` matrix entries (Check 52, subset `{"01", "02", "03", "04", "05"}`).
  - **Seven exact checks stay live until a later phase deliberately changes what they read (convert to `tagged(...)` at `v2.0.0-phase-5` in the PR that changes them):**
    1. **Check 2:** The `layers` contract in `pyproject.toml` keeps its name (`"Layers import downward only"`), puts `weatherbot.cli` before `weatherbot.web` as separate layers, and ends with `weatherbot.models`.
    2. **Check 4:** `src/weatherbot/web/guards.py` mounts `TrustedHostMiddleware` with `127.0.0.1`, `localhost`, and `[::1]` (when Phase 8's optional LAN mode widens the host allowlist, keep those three loopback hosts in the default tuple or convert Check 4 to read `v2.0.0-phase-5:src/weatherbot/web/guards.py`), and no package module imports or references `CORSMiddleware` or `BaseHTTPMiddleware`.
    3. **Check 14:** `src/weatherbot/web/map_layers.py` keeps `MAX_SNAPSHOT_CACHE_SIZE = 8` on the snapshot layer cache.
    4. **Check 17:** No `src/weatherbot/web/` module defines an `async def` route that reads a repository or `state.database` directly (synchronous `def` routes run SQLite reads on FastAPI's worker threadpool).
    5. **Check 19:** `src/weatherbot/services/events.py` defines `EventKind` with the exact eight Phase 5 literals (`hello`, `cycle`, `snapshot`, `assessment`, `alert`, `notification`, `location`, `health`). If Phase 6 adds a new `EventKind` literal for streaming briefings, convert Check 19 in that PR to read `v2.0.0-phase-5:src/weatherbot/services/events.py` via `tagged("src/weatherbot/services/events.py")`.
    6. **Check 25:** No event model in `src/weatherbot/web/schemas.py` (`StreamEvent` and any model it references) declares `lat`, `lon`, `latitude`, `longitude`, `coordinates`, `geometry`, `distance_km`, or `bearing_deg`.
    7. **Check 47:** `README.md` has `### The dashboard`, its `## Commands` names `weatherbot status`, `weatherbot replay`, and `weatherbot locations evacuation`, and its `## Status` names Phase 5 complete and Phase 6 next. When Phase 6 Step 1 or closure updates `README.md`'s `## Status`, convert Check 47's `## Status` assertion in that same PR to read `v2.0.0-phase-5:README.md` via `tagged("README.md")` (matching how Phase 5 Step 1 converted Phase 4's Check 46).
- **Disposition:** Completed in Step 8 (`2026-10-29`).

## Source-drift observations

- Across Phase 5's live runs (`2026-10-26` through `2026-10-29`), all 19 register sources were probed by `weatherbot doctor` and `tests/live/test_web_live.py`.
- Zero `DriftWarning` records were logged in the latest snapshots (`The latest snapshot logged no Source drift`).
- All five NHC ArcGIS MapServer catalogs (`nhc-map-tropical-weather`, `nhc-map-tropical-summary`, `nhc-map-breakpoints`, `nhc-map-peak-surge`, `nhc-map-surge-risk`) resolved 100% of their register layer names, and both WMS capabilities documents (`overlay-radar`, `overlay-satellite`) resolved their expected layers.

## Live smoke runs

1. **`pytest -m live tests/live/test_web_live.py` (`2026-10-27` in PR #63 and `2026-10-29` in Step 8):**
   - Added both public landmarks (`Miami-Dade County Hall` and `Parliament Square`) in an isolated temporary data directory, started `WebServer` on an ephemeral loopback port with the real HTTP fetcher, opened `GET /api/events`, triggered `POST /api/cycles`, and verified that `hello`, `cycle`, `snapshot`, and `assessment` events streamed in order for both landmarks and persisted `MonitorCycle(trigger="manual", status="complete")`. Result: **PASS**.
2. **`uv run weatherbot doctor` (`2026-10-29` on operator's Windows 11 machine):**
   - Local checks: `settings` (`pass`), `database` (`pass`, SQLite in WAL mode), `migrations` (`pass`, at revision `0006`, the head), `locations` (`pass`), `heartbeat` (`pass`, 11 with a cadence, none stale), `toast` (`pass`, the latest toast delivered), `tasks` (`pass`, `serve (Running)` and `check (Ready)` enabled), `path` (`skip`, running from a source checkout environment), `web` (`pass`, `dashboard reachable at http://127.0.0.1:8765`).
   - Online probes and layer discovery: all 19 register sources and all 5 MapServer layer sets passed with zero missing layers and zero source-drift warnings. Result: **PASS** (exit 0).

## Pre-ship items

| Item | Origin | Target destination | Status |
| :--- | :--- | :--- | :--- |
| Claude briefing, change summary, grounded chat, outlook narration, and cost meter streamed into the dashboard over the API and `/api/events` and joined to `/settings` | Brief §8 / Phase 5 boundary | Phase 6 (`docs/roadmap/ROADMAP.md` §6.1–§6.3) | Assigned to Phase 6 |
| Convert Phase 5 Check 47 (`README.md` `## Status`) — and Check 19 if `EventKind` grows — to read `v2.0.0-phase-5` via `tagged(...)` | Phase 5 Step 8 | Phase 6 (`docs/roadmap/ROADMAP.md` Phase 6) | Documented in `ROADMAP.md` Phase 6 |
| Wind-probability and arrival charts, wind-radii/WSP/surge/radar/satellite map layers, advisory time slider, replay scrubber, multi-location settings page, ntfy push, quiet hours, retention, and HTML/PDF report export | Brief §6, §7, §9 / Phase 5 boundary | Phase 7 (`docs/roadmap/ROADMAP.md` §7.1–§7.4) | Assigned to Phase 7 |
| Forward geocoding (`City, State / Country` place search on `/settings` and `weatherbot locations add --place` via Nominatim `/search`) | Phase 5 Step 7 operator UX verification | Issue #71 & Phase 7 §7.3 (`docs/roadmap/ROADMAP.md`) | Tracked in Issue #71 & Phase 7 §7.3 |
| Local tile-proxy fallback with disk caching and a custom `User-Agent` if OpenStreetMap ever starts refusing loopback `Referer` headers | Phase 5 Step 6 & Step 8 | Phase 7 §7.1 (`docs/roadmap/ROADMAP.md`) | Assigned to Phase 7 §7.1 |
| `advisory_issued` detail wording (`"whose cone does not."`) | Phase 3 QA ledger | Issue #44 | Tracked in Issue #44 |
| Storm-surge watch/warning & extreme-wind warning ladder placement | Phase 3 QA ledger | Issue #33 | Tracked in Issue #33 |
| Optional LAN mode (widening `[web] host` bind behind a bearer token and rate limiting) and building the frontend bundle inside the PyPI release workflow (`package` job recipe) | Brief §6 / Phase 5 Step 1 & Step 4 | Phase 8 (`docs/roadmap/ROADMAP.md` §8.1–§8.3) | Assigned to Phase 8 |
