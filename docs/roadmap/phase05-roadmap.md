# Phase 5 Roadmap — Web app MVP ✅

**Status:** Complete — 2026-10-29

## Overview

Phase 5 opens Weatherbot's second front door: a local web app that looks and
feels like a modern website, served by the same `serve` process that runs the
monitor, from the same database, so the level the browser shows is the level the
terminal shows. A FastAPI API on the loopback interface serves the stored
locations, assessments, storms, alerts, history, and settings, and the map's
geometry; a server-sent event stream tells the open page what changed, so it
never polls; and a React single-page app — dashboard, map, storms, alerts,
timeline, and settings, in dark and light themes, down to phone width — ships
built inside the wheel, so `pip install` and `weatherbot serve` give a dashboard
with no Node. It does not write a briefing or answer a question (Phase 6, which
streams into this phase's dashboard), add the wind-probability, wind-radii,
surge, or radar layers, the replay scrubber, the multi-location settings, quiet
hours in the page, ntfy, or export (Phase 7), or open the server beyond loopback
or publish a release (Phase 8). The work is one phase because the API contract,
the event stream, and the page are one interface: a route no page reads is
untested, a page without its event goes stale, and the guards that keep a
hostile website from reading or changing the operator's data must cover every
route from the first one.

The phase lands in 8 layers:

1. **The web server inside `serve`** — `weatherbot.web.create_app`, served by
   uvicorn as a task beside `run_monitor` in `serve`'s event loop, bound to
   `127.0.0.1:8765` by a new `[web]` table that refuses any non-loopback host;
   the guards every route inherits (the host allowlist against DNS rebinding, no
   cross-origin read permission, same-origin JSON for every write, a strict
   Content-Security-Policy, and `no-store` on every API answer); `GET
   /api/health`; the OpenAPI document committed at `docs/api/openapi.json`;
   `serve --open/--no-open`; `doctor`'s `web` check; and the layers contract
   amended so the CLI may host the web layer. Deployed on the operator's machine
   with the operator's yes.
2. **The read API and the map's geometry** — the web layer's own response models
   and the routes `GET /api/locations`, `/api/assessments`, `/api/storms`,
   `/api/alerts`, `/api/timeline?location=`, `/api/notifications`,
   `/api/settings`, `/api/disclaimer`, `/api/map` (the latest snapshot's cones,
   tracks, forecast points, watch-warning segments, and outlook areas, and the
   locations, cached per snapshot), and, when a replay corpus is open (`[web]
   corpus`, or `serve --corpus DIR`), `/api/replay` and
   `/api/replay/{atcf_id}/{advisory}`.
3. **The event stream, browser notifications, and the API's actions** —
   `weatherbot.services.events.EventHub`, fed by `serve`'s cycle listener, by a
   watcher that notices cycles other processes ran, and by the API's own writes;
   `GET /api/events`, whose events name the queries a page must refetch; the
   browser channel behind Phase 4's `Channel`, with an honest delivery result;
   and the four writes — `POST /api/locations` (first-run setup), `PUT
   /api/locations/evacuation` (the name in the body), `POST /api/cycles` (check
   now, through the running schedule), and `POST /api/notifications/test`.
4. **The frontend chassis, its gate, and the wheel** — `frontend/` with Vite,
   React 19, strict TypeScript, Tailwind CSS, TanStack Query, React Router,
   Radix primitives, and lucide icons, on Node 24; types generated from the
   committed OpenAPI document; the app shell (navigation, themes, the disclaimer
   footer, the staleness banner) and the event subscription that invalidates
   only the named queries; Vitest and Testing Library; ESLint with
   `eslint-plugin-security` and `npm audit` in pre-commit and CI; a `frontend`
   job in the gate; Dependabot's `npm` ecosystem; and the build that the
   `package` job copies into `src/weatherbot/web/static/` before `uv build`,
   proved by a wheel install that serves it.
5. **The dashboard and the pages** — Dashboard (each location's level card with
   its evidence, actions, and missing inputs, its storms and alerts, the next
   product time, and "check now"), Storms, Alerts, Timeline (assessment history,
   change feed, and notifications), and Settings (first-run location setup, the
   evacuation toggle, browser notifications and a test, and every effective
   setting with its origin), with the browser's own notifications.
6. **The map** — Leaflet over OpenStreetMap raster tiles with their attribution:
   cones, forecast tracks and points, watch and warning segments in NHC's
   colours, outlook areas, and the locations, with layer toggles, a fit to what
   matters, longitudes kept continuous across the antimeridian, and a replay
   picker when the server has a corpus.
7. **The browser smoke, idle cost, and the operator's dashboard** — a Playwright
   smoke that loads the dashboard over recorded answers and sees a simulated
   advisory's stored change arrive through the event stream without a reload,
   renders a replayed advisory's cone and track with the location marker, and
   finds no coordinate in the browser's console; the idle CPU of the server and
   the tab, measured and recorded; and the operator's installed copy serving the
   dashboard, with the operator's yes.
8. **QA + `verify_phase05.py`** — `scripts/verify_phase05.py` (`--fast`, `--py`,
   `--node`, `--ui`, `--live`, `--security`, `--all`, `--post`),
   `docs/phase05-qa-findings.md`, and matrix entry `"05"` beside `"01"` to
   `"04"` in `phase-verify.yml`; Phase 5 closed in this roadmap and the project
   roadmap; the `v2.0.0-phase-5` tag.

The ship test for Phase 5 is straightforward: on a runner whose wheel was built
in CI, `weatherbot serve` from a fresh environment answers `/` with the built
interface and `/api/health` with the package version, without Node on the
request path; every read route answers in its committed OpenAPI schema, with a
location's coordinates only in the locations shape and the map shape's location
layer; a request with a foreign `Host` is refused, no route grants another
origin a read, a cross-site write is refused, and every page carries the
Content-Security-Policy; a cycle that `serve` runs, and one another process
runs, each reach a subscribed page as events within 15 seconds; the browser
channel records `delivered` with a page open and `unavailable` without one; the
Playwright smoke sees a simulated advisory's level-5 change appear without a
reload, draws a replayed Irma advisory's cone and track with the marker, and
finds no landmark coordinate in the console; the server and the tab each spend
under 0.5 percent of one core idle over ten minutes; `npm audit
--audit-level=high` and `eslint-plugin-security` are clean in the gate; the
operator's `/api/health` answers from the upgraded copy; Phase 1's to Phase 4's
verification still pass; and `scripts/verify_phase05.py --fast` exits 0 on
Ubuntu CI with `phase-verify (01)` to `(05)` green.

**Pre-requisite:** Phase 4 closed on 2026-10-24 (PRs #52 and #53,
`v2.0.0-phase-4`). Its `serve` process, scheduler, and cycle listeners are where
the web server and the event stream run; its heartbeats, staleness rule, stored
cycles, and notification log with deliveries are what `/api/health`, the
staleness banner, and the timeline serve; its `Channel` interface is what the
browser channel implements; and its installed copy under Task Scheduler is the
surface this phase upgrades. Phase 3's stored assessments with evidence,
threats, and changes are the dashboard's content, and its replay corpus is the
map's off-season data; Phase 2's typed geometry with its CRS is what the map
draws; Phase 1's gate, socket guard, and working-directory guard are what every
Phase 5 commit runs under. The planning kit is roadmodel 0.2.94: PR #54
refreshed it on 2026-10-24, before this roadmap, with the matching lock bump.

**Dependency:** Phase 6 does not start until Phase 5's V-checks are green. Its
briefing and change summary stream into the dashboard over this phase's API and
event stream, behind labeled blocks the page reserves for them, and its cost
meter joins the settings page; Phase 7 adds its layers and charts to this
phase's map and its replay scrubber to the replay routes, and turns the
read-only settings into the multi-location settings page; and Phase 8's LAN mode
widens the bind this phase refuses, behind a token, and its release workflow
builds the interface the way this phase's `package` job does.

**Design rationale (decisions and clarifications of the brief and the project
roadmap).** Eighteen decisions, each made against recorded, measured, or
researched evidence while this roadmap was written (2026-10-24). The project
roadmap records each one that changes it, in this roadmap's own pull request.
Step agents treat them as settled spec unless the operator changes them.

- *The CLI hosts the web app, and the layers contract says so.* `weatherbot
  serve` is a CLI command that must start the web server in its own process, and
  the contract today makes `cli` and `web` independent siblings, so neither may
  import the other. The contract becomes `weatherbot.cli` above `weatherbot.web`
  above `weatherbot.services`: the CLI may import the web layer (to host it),
  and the web layer never imports the CLI. The alternatives were worse: keeping
  the siblings and passing the app through a runtime hook hides a real
  dependency from the contract, and starting the server from the services would
  make a lower layer import a higher one. The contract keeps its name and ends
  with the models (Phase 2's check 3), the database contract keeps both front
  doors among its sources (check 33), and `AGENTS.md` and both package
  docstrings say so.
- *One process, one loop, and the monitor outranks the page.* uvicorn's
  `Server.serve()` runs as an asyncio task beside `run_monitor` inside `cli/
  serve.py`'s loop. Three uvicorn 0.54 behaviours, verified on 2026-10-24, shape
  how: `serve()` replaces the SIGINT, SIGTERM, and SIGBREAK handlers and
  re-raises a captured signal after its own shutdown; a startup failure (a taken
  port) calls `sys.exit(3)` inside `serve()`, which escapes a task and
  `asyncio.run` and would kill the monitor with it; and an open server-sent
  event client keeps the default shutdown waiting forever. So Weatherbot binds
  its own loopback socket first (a taken port is then an `OSError` it handles,
  and the port is known before uvicorn starts; on Windows the socket is
  exclusive, never `SO_REUSEADDR`, which there lets another process share the
  port), passes it to `serve(sockets=[...])` through a `uvicorn.Server` subclass
  whose `capture_signals` is a null context, still catches `SystemExit`, and
  stops by first closing every event stream and then setting `should_exit`, with
  `timeout_graceful_shutdown=2` as the backstop; it runs with `log_config=None`,
  no access log, no `server` header, and `proxy_headers` off. `serve` keeps its
  Ctrl+C, its lock, and its log file, and the web server closes its socket on
  every way out of `serve`. The reverse does not hold: a hurricane monitor's job
  is the 3 a.m. notification, so a web server that cannot bind is logged once,
  the monitor runs on, and `doctor`'s `web` check fails until it answers. `[web]
  host` accepts only `127.0.0.1`, `::1`, and `localhost` — any other value is a
  configuration error naming the key, until Phase 8's LAN mode — and `[web]
  port` defaults to 8765. Every route that reads the database is a plain
  function, which FastAPI runs in its thread pool, so a 384 ms snapshot decode
  never stalls the loop that runs the scheduler and the event stream; SQLAlchemy
  2.1's pool for a file database shares connections across threads (checked
  2026-10-24), and WAL with `BEGIN IMMEDIATE` already serializes writers.
- *Loopback is not a trust boundary against the browser.* Any page the operator
  visits can send requests to `127.0.0.1:8765`; it cannot read the answers
  unless the server lets it, and it can reach them by name through DNS
  rebinding. So the server answers only requests whose `Host` names `127.0.0.1`,
  `localhost`, or `[::1]` (on any port) — Starlette's `TrustedHostMiddleware`,
  which drops the port and refused every rebinding form tried on 2026-10-24
  (`127.0.0.1.evil.example`, `2130706433`, `127.1`, a userinfo trick) — sends no
  `Access-Control-Allow-*` header to anyone — the page is same-origin, and the
  Vite dev server proxies — refuses any `/api/` request a browser marks
  cross-site (`Sec-Fetch-Site`), so a hostile page cannot even hold the event
  stream or time the API, refuses a `POST`, `PUT`, or `DELETE` unless it is
  `application/json` from the served origin (a cross-site form or fetch cannot
  change a location or a toggle), and sends a Content-Security-Policy that
  allows only its own scripts and connections, its own styles plus those
  carrying a fresh nonce that each `index.html` gets (Radix's dialogs, menus,
  selects, and scroll areas inject `<style>` elements, which a strict policy
  blocked in Chrome 156 on 2026-10-24, silently breaking scroll locking), and
  images from itself, `data:` (Vite inlines assets under 4 KiB, and Leaflet
  keeps a `data:` placeholder), and the tile server; with `frame-ancestors
  'none'`, `nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`
  (OpenStreetMap's tile policy requires a Referer and names `no-referrer` and
  `same-origin` unacceptable), and `Cache-Control: no-store` on every `/api/`
  answer and on `index.html`, because they carry the operator's locations or a
  nonce. Chrome, from version 142, also asks before a public page may reach
  loopback; the guards do not rely on it. No route needs a token on loopback;
  Phase 8 adds one for the LAN.
- *The API has its own response models; the CLI's documents stay as they are.*
  The `--json` documents round distances and bearings and keep coordinates to
  `locations list` because they are terminal output that is copied and pasted;
  the browser needs a location's point for its marker and exact geometry for the
  map. So `weatherbot.web.schemas` defines the API's models, built from the same
  stored records the CLI reads, and a parity test holds both front doors to the
  same level, rule, and evidence for the same stored assessment. A location's
  coordinates appear only in the locations shape (`GET` and `POST
  /api/locations`, and the evacuation `PUT`'s answer) and in the map shape's
  location layer (`/api/map` and `/api/replay/{atcf_id}/{advisory}`); a
  validation error never echoes its input (FastAPI's default 422 answer does, so
  the app installs handlers that keep only each error's location, message, and
  type); the page never writes an API answer, or an error carrying one, to the
  console; and no log line above DEBUG — a traceback included, whose text the
  log handlers redact as they redact messages — holds a coordinate, a distance,
  or a bearing.
- *The contract is committed and checked.* `scripts/export_openapi.py` writes
  the app's OpenAPI document to `docs/api/openapi.json` (not `docs/schema/`,
  whose listing `tests/cli/test_documents.py` pins), a test fails while the
  committed file differs from a fresh export, and from Step 4 the frontend's
  types are generated from that file by openapi-typescript, committed, and
  checked in CI with its `--check` flag, so a route change that the page does
  not follow fails the PR. FastAPI documents the event stream with an OpenAPI
  3.2 `itemSchema` inside its 3.1 document and leaves the event models out of
  `components.schemas` (checked 2026-10-24; no generator then types them), so
  the exporter adds those models to the components itself, and a test holds them
  there. The file is written as UTF-8 with LF line endings, and no model takes a
  `Path` default, the one thing the probe found rendering differently on Windows
  and Ubuntu.
- *Events say what changed; the page refetches.* `GET /api/events` is one
  server-sent event stream per open page. An event names what was stored —
  `snapshot`, `assessment`, `alert`, `notification`, `location`, `cycle`, or
  `health` — with the ids involved and the query keys a page must invalidate; it
  never carries a location's coordinates. Each connection starts with a `hello`
  event and the page refetches everything on every (re)connect, so the server
  keeps no replay buffer and a reconnect can never miss a change. Each
  subscriber has a bounded queue (100 events), at most 16 pages subscribe at
  once (a 17th is answered 503), and uvicorn's `limit_concurrency` bounds every
  connection; a subscriber that falls behind is closed and reconnects. FastAPI's
  own `EventSourceResponse` (`fastapi.sse`, since 0.135.0) encodes the events
  and writes a `: ping` comment after 15 idle seconds, so no other package is
  needed (sse-starlette patches uvicorn's exit handler at import and keeps
  process-wide state). The route yields its payload models themselves, which
  FastAPI validates against the route's return annotation. A stale heartbeat is
  a moment in time rather than a write, so the hub sets one timer for the next
  instant a heartbeat would turn stale and sends `health` then: the staleness
  banner moves without any polling.
- *Every writer's cycle reaches the page.* Cycles from `status`, `check --once`,
  `fetch`, `storms`, `alerts`, and the hourly fallback run in other processes,
  which no listener in `serve` hears. The hub therefore checks four high-water
  marks every 10 seconds — the newest completed cycle, the newest notification,
  each location's newest assessment, and the locations themselves (their names
  and toggles, which `locations add` and `locations evacuation` change from a
  terminal) — and publishes what this process did not; four small queries every
  10 seconds cost nothing a person can measure, and a terminal `status` shows up
  in the open page within 15 seconds. The browser itself never polls.
- *Browser notifications are a channel, and its result is honest.* The brief's
  §9 names a browser notification beside the toast, and Phase 4 left it to this
  phase behind `Channel`. `services.events.BrowserChannel` delivers by
  publishing a `notification` event: `delivered` ("to 2 open dashboards") when a
  page is subscribed, `unavailable` ("no open dashboard") when none is, and
  `disabled` when `[notifications] browser` is off. Only `serve` adds it to its
  channels, because only `serve` has pages; `CHANNEL_NAMES` gains `browser`, and
  no notification kind is added (Phase 4's check 43), so the settings page's
  test sends kind `test` through `serve`'s channels. The quiet-hours hold that
  keeps Phase 4's alarms off the toast keeps them off the browser too:
  `NotificationService` holds every channel that interrupts (the toast and the
  browser) and keeps the log, choosing by a channel's `interrupts` property
  rather than by the name `toast`. The page shows an operating-system
  notification only when the operator turned them on for that browser and
  granted permission, and an in-page message otherwise; whether the operating
  system displayed it is not knowable, and the detail says "to N open
  dashboards", not "shown".
- *The map draws what NHC published, as NHC published it.* `/api/map` serves the
  latest snapshot's cones, forecast tracks and points, watch-warning segments,
  and outlook areas, with the locations, as GeoJSON whose every geometry carries
  its CRS, and the page draws the coordinates unchanged: the archive's sphere
  and WGS 84 share latitude and longitude to PROJ's own ballpark (Phase 3
  measured the transformation between them as a zero offset), so nothing is
  transformed or relabelled. Measured on 2026-10-24, those layers are 49 KiB of
  a 1.8 MiB snapshot whose cold load takes 384 ms; snapshots never change once
  stored, so the payload is built once per snapshot id and kept in memory. The
  wind radii (199 KiB a storm), the wind-speed probabilities (1.1 MiB), and the
  surge and radar layers are Phase 7's. A geometry whose longitudes jump by more
  than 180 degrees between vertices is unwrapped for display, so a Central
  Pacific cone never spans the globe. The page loads OpenStreetMap's tiles
  itself, as the register already records (`basemap-osm-tiles`, display-only),
  with the attribution visible and the referrer policy set on the tile layer too
  (Leaflet 1.9.4 sets none; the fix is unreleased). Whether OpenStreetMap keeps
  accepting a bare loopback Referer is unproven — its enforcement runs as a
  brownout — so the recorded fallback, owned by Phase 7 if tiles start failing,
  is a server-side caching tile proxy that sends the project's User-Agent and
  honours the tiles' cache headers.
- *Replay on the map is opt-in, and stores nothing.* The wheel ships no corpus,
  so a corpus opens from `[web] corpus` (a directory, with the literal override
  `WEATHERBOT_WEB_CORPUS`), which the scheduled `serve` reads at start — one
  that will not open is logged and leaves the monitor running with replay off —
  or, for one run, from `serve --corpus DIR` (the `replay` command's option),
  which exits 2 on a directory that is not a corpus. The setting is the way on
  the operator's machine, where the scheduled `serve` holds the monitor's lock
  and a second `serve` exits 2. Either turns on `/api/replay` (the corpus's
  storms and advisories) and `/api/replay/{atcf_id}/{advisory}` (that advisory's
  layers, in the map's shape), and the map offers a picker only when
  `/api/health` says a corpus is open. `ReplayCorpus` gains public
  `advisories(atcf_id)` and `snapshot(atcf_id, advisory)` accessors, so one
  advisory costs one read (39 ms measured), not the storm's 3.3 s. Replay
  assessments stay unstored; Phase 7's scrubber adds the replayed level to these
  routes.
- *The stack is the brief's, pinned to what the strict gates accept.* Python:
  `fastapi>=0.162.0` (typed, with its own `fastapi.sse`; it now depends on
  `opentelemetry-api`, which stays unconfigured and which the audit covers),
  `starlette>=1.10.0` (imported directly; it clears 2026's five Starlette
  advisories, one a `StaticFiles` UNC-path leak on Windows), and plain
  `uvicorn>=0.54.0` (only `click` and `h11`; the `[standard]` extras add uvloop,
  httptools, websockets, and watchfiles, which a loopback server does not need).
  The frontend, read from the npm registry on 2026-10-25 and installed together
  in a probe: Vite 8.3 with `@vitejs/plugin-react` 6.1, React 19.3, TypeScript
  5.9.3 — not 7.0, whose native compiler ships no API, while typescript-eslint
  accepts below 6.1 and openapi-typescript only 5.x — Tailwind CSS 4.3, TanStack
  Query 5, React Router 8 in data mode (no framework mode, no server rendering),
  the unified `radix-ui` package, lucide icons, Leaflet 1.9.4 used directly,
  openapi-typescript 7.13 with openapi-fetch 0.17 (types only, a 6 KB client,
  OpenAPI 3.1, and a `--check` drift gate), Vitest 5 with jsdom 30 and Testing
  Library, Playwright 1.64 (Chromium), and ESLint 10 with typescript-eslint 8,
  `eslint-plugin-react-hooks` 7, and `eslint-plugin-security` 4, whose rules
  only warn, so it runs with `--max-warnings 0`. Leaflet, not react-leaflet:
  react-leaflet 5's licence is the Hippocratic License 2.1, which is not
  OSI-approved and would ship inside the MIT wheel, so a small hook wraps
  Leaflet (BSD-2-Clause) — a change from the project roadmap's 5.2, which this
  PR records there; Leaflet 2.0 is an alpha. Node is 24 (maintenance LTS until
  2028-04-30, at least 24.15): jsdom 30 and React Router 8 refuse the operator's
  22.18, and Node 26 becomes LTS only on 2026-10-28; `frontend/.nvmrc` pins it
  for CI's `actions/setup-node` 7.1.0, and Step 4 asks the operator to install
  it. Exact versions live in `package-lock.json` and `uv.lock`, and Dependabot
  proposes every bump.
- *The built interface ships in the wheel, and Node stays a build tool.* Vite
  writes the build into `src/weatherbot/web/static/` (git-ignored), and
  `uv_build` packs it: checked on 2026-10-24, it ignores `.gitignore` and
  carried an ignored static directory into both the sdist and the wheel, while
  `uv build` without one still succeeded. The `package` job therefore runs `npm
  ci` and the build before `uv build` on both runners, and its wheel smoke
  starts the installed `weatherbot serve` with `HTTPS_PROXY` pointed at a closed
  loopback port (httpx honours it, so the startup cycle's requests fail fast and
  nothing leaves the runner) and reads `/` and `/api/health` with the standard
  library. The server serves the build from an in-memory map of its files, made
  once at start, so no part of a request ever reaches a filesystem call — a UNC
  name, a drive letter, `..`, `NUL`, or `::$DATA` is simply not a key, the class
  behind Starlette's Windows advisory — and an unknown `/assets/` path answers
  404. A checkout that has not built the interface serves a plain page that says
       so and how to build it; the API works without it. Vite 8's
       `build.license` writes `licenses.json` into the build — every bundled
       package's name, version, licence, and text — so the wheel carries its
       notices, the settings page links it, and the frontend job fails when a
       bundled licence is outside MIT, ISC, BSD-2-Clause, BSD-3-Clause,
       Apache-2.0, and 0BSD.
- *The gate covers the frontend.* `package-lock.json` is committed, every
  install is `npm ci`, and CI runs `npm audit signatures` after it; ESLint with
  `eslint-plugin-security` (at `--max-warnings 0`) and `npm audit
  --audit-level=high` run in pre-commit (on the frontend's files and its lock
  file) and in CI's `security` job beside bandit and pip-audit, and
  `phase-verify (05)` installs Node for its `--security`; Dependabot's `npm`
  ecosystem watches `frontend/`; the personal-data check already scans every
  frontend file; and the frontend reads no environment variable, so no build can
  embed a value from the machine that built it (a static check refuses
  `import.meta.env.VITE_` in `frontend/src`).
- *Idle means idle, and it is measured.* No page polls: TanStack Query runs with
  `staleTime: Infinity`, no refetch interval, and no refetch on focus, so a
  query refetches only when an event names it or the stream reconnects. The
  server's timers are the scheduler's (it wakes at most once a minute), the
  stream's 15-second ping, the 10-second watcher, the staleness timer, and
  uvicorn's own main loop, which wakes every 100 ms to watch for shutdown (read
  from the 0.54.0 wheel; a few microseconds a tick). Step 7 measures both sides
  over ten idle minutes with one page open — the server's process CPU time, and
  the tab's main-thread task time through the Chrome DevTools Protocol — and
  holds each under 0.5 percent of one core (3 seconds in ten minutes), recording
  the numbers, and the watch polls and cycles that ran inside the window, in the
  QA findings. The browser smoke and the measurement answer tile requests with a
  blank local image, so CI never asks OpenStreetMap for a tile.
- *`serve` opens a browser only for a person.* `serve` opens the dashboard when
  the process started with a terminal — `sys.__stdout__` is a TTY — and
  `--open/--no-open` overrides it. The original stream is the one to ask:
  `configure_logging` replaces `sys.stdout` with `os.devnull` under
  `pythonw.exe`, and on Windows that stream claims to be a TTY (checked on
  2026-10-24), while `sys.__stdout__` stays `None`; so under Task Scheduler,
  whose `serve` task passes no flag, a logon or a fallback restart never opens a
  window. A second `serve` still exits 2, and its message now names the running
  dashboard's address; `doctor` prints it too.
- *The settings page reads everything and writes three things.* It shows every
  effective setting with its origin as `serve` loaded them at start (and says
  when the file has changed since), and the configuration file's path; its
  writes are the first location (name and point, through `LocationService.add`,
  so the NWS and Nominatim lookups run as in `locations add`), the evacuation
  toggle (recorded at once and, as in `locations evacuation`, assessed by the
  next cycle, with "check now" beside it), and the browser-notification switch,
  which lives in that browser. Editing `weatherbot.toml` from the page,
  per-location preferences, quiet-hours controls, and removing a location are
  Phase 7's.
- *Phase 4's checks stay green, with one planned conversion.* No step adds a
  cycle trigger (check 8: "check now" runs `manual` through the running
  schedule's `execute_cycle`, so a drop it holds still gets its confirmation
  cycle, and its retries and alarms count) or a notification kind (check 43);
  `cli/serve.py` keeps `ProcessLock(paths.monitor_lock_path)` and `run_monitor(`
  (check 36), and `cli/check.py` keeps `run_monitor_loop(ctx, runner="check")`
  (check 37), so the web server joins inside `run_monitor_loop` for the `serve`
  runner only; `scripts/simulate_advisory.py` keeps its behaviour and its final
  line (check 38 and Phase 4's V5.4); and Step 1, the first step to edit
  `README.md`'s `## Status`, converts check 46 to read
  `v2.0.0-phase-4:README.md` and moves its mutation case to the tagged text in
  the same PR. Every other check of Phases 1 to 4 stays live and green as
  written (Current State, "Verification surfaces").
- *The version stays `2.0.0.dev0`, so health names the build.* `/api/health`
  reports the package version, the database revision and head, the scheduler's
  state, every heartbeat's staleness, the next NHC product time, whether a
  corpus is open, and the built interface's identity (whether it is present, and
  the first 12 hex digits of its `index.html`'s SHA-256, which changes with
  every build because Vite hashes asset names), so a Deployed & verified check
  can tell this build from the last without a version bump.

**Branch strategy.** Every step in this phase lands on its own short-lived
feature branch (`feature/phase05-step<M>-<slug>`), opens a pull request against
`main`, waits for the project's CI workflow to go green, and squash-merges with
a Conventional Commits subject line. Direct pushes to `main` are blocked by
branch protection. See the project roadmap's "Branch management strategy" for
the canonical naming convention, PR rules, and release tagging — this paragraph
confirms those rules apply unchanged within this phase. Per-step branches are
listed on each step header below as `**Branch:**` so reviewers can map commits
1:1 to the step they implement.

**Branch-first execution rule.** The very first action of every step — before
reading any files, before running any tool, before drafting any change — is to
check out the branch named in that step's `**Branch:**` line:

```sh
git checkout -b feature/phase05-step<M>-<slug>
```

This is non-negotiable. `main` is protected with `enforce_admins: true`, so a
commit on `main` cannot be pushed and must be rewound or rebased onto the
feature branch before the PR can open — an avoidable round-trip. If you discover
mid-step that you started on `main`, recover by running the same `git checkout
-b` command immediately (uncommitted changes carry over to the new branch), then
continue. AI coding agents executing a step from this roadmap must treat the
branch checkout as Step 0 of every step.

**Worktree rule.** One working tree, one step in flight — the lifecycle below
assumes the primary checkout. A second working tree is created only with `git
worktree add`, and only for the three cases the project roadmap's "Worktree
strategy" sanctions: a `hotfix/` branch interrupting this step (cut from
`origin/main` in its own worktree so this step's tree is untouched); steps the
Execution Order below explicitly draws in parallel (this phase draws none); and
worktree-isolated subagents inside a step (throwaway trees that merge back into
the step branch locally and are removed before the PR opens). In those cases
Stage 1 becomes `git fetch origin && git worktree add -b
feature/phase05-step<M>-<slug> <worktree-path> origin/main`, the worktree is
bootstrapped before any test or build (`uv sync`, and from Step 4 on `npm ci` in
its `frontend/` — a worktree has none of the primary tree's untracked state,
such as `.venv`, `frontend/node_modules`, the built interface, or the replay
cache, and it must never borrow the primary tree's `.venv`), the Stage 4 merge
runs from the primary tree, and Stage 5 removes the worktree BEFORE pruning the
branch. Undeclared parallelism is a lifecycle violation, not a shortcut.
Worktree location for this project: git-ignored `.worktrees/<branch-slug>/`
inside the repository, matching the project roadmap.

**Security-first execution rule.** Security is not a phase — it is a gate on
every commit of every step. Before each `git commit`, the step's work must pass
the local, fail-closed security gate: secret/personal-data scan clean, SAST
clean, dependency audit clean, and a diff review confirming no sensitive data
(the operator's coordinates, credentials, tokens) and no new insecure pattern
(injection, a subprocess built from a shell string, unsafe deserialization, a
path read outside the directory it names, a coordinate in a log line above DEBUG
or in the browser's console, a response readable from another origin, a
state-changing request a cross-site page could send). The gate is wired into the
pre-commit hook and re-run in CI, so a security issue introduced while
implementing a step is caught during development — before it reaches the branch,
the PR, or `main`. See the project roadmap's "Security & privacy strategy" →
"Per-step security gate" for the canonical checks and tooling; each step's XML
`<task>` carries a `<security>` block restating them for the agent, and each
step's Acceptance Criteria ends with a security check. AI coding agents
executing a step MUST treat the security gate as part of the step's definition
of done, exactly like its tests. This phase opens Weatherbot's first network
listener: an HTTP surface on the loopback interface, with no authentication,
whose answers carry the operator's locations — their names, their points (for
the map's marker), and the distances and bearings of storms from them. Any web
page the operator visits can send requests to `127.0.0.1`, so the server is
written against the browser as an adversary as well as a client: it binds
loopback only, answers only to its own host names (DNS rebinding), sends no
cross-origin read permission, refuses a state-changing request that is not a
same-origin JSON request (cross-site request forgery), sends a strict
Content-Security-Policy, and marks every API answer `no-store`. From Step 4 the
gate also covers the frontend: ESLint with `eslint-plugin-security` and `npm
audit --audit-level=high` beside bandit and pip-audit, the personal-data check
over every frontend file, and a build that embeds no environment value. No step
reads, prints, or quotes the operator's coordinates, an assessment of the
operator's location, or a notification sent about it; agents verify with the two
public landmarks in a temporary data directory.

**Deploy-and-verify rule.** Merged is not deployed, and deployed is not
released. Every step header carries a `**Deploys:**` line naming the surface and
environment the step's merge reaches — or `nothing beyond merge` — and when
going live needs a reinstalled copy, a restarted task, or a tag, the line says
so and this step (or a named follow-on step) owns that event. For a step whose
Deploys line names a surface, Stage 4 of the lifecycle does not end at the
squash-merge: the step's acceptance criteria carry a **Deployed & verified**
bullet (`GET http://127.0.0.1:8765/api/health` on the operator's machine answers
from the reinstalled copy with the build this step shipped; the dashboard opens;
`doctor` passes its new `web` check), and that bullet must be green before the
step is declared complete. This phase introduces no secret and no required
environment variable, and no migration: the new `[web]` table and the
`[notifications] browser` key are optional, with literal `WEATHERBOT_WEB_*` and
`WEATHERBOT_NOTIFICATIONS_BROWSER` overrides. Its new local surfaces are the web
server inside the `serve` process on `127.0.0.1:8765`, the built interface
inside the installed package, and the operator's browser. The scheduled task
`\Weatherbot\serve` keeps its definition: it starts the reinstalled copy's
`serve`, which now serves the dashboard too. A step reinstalls the operator's
copy, restarts that task, or opens a page on the operator's desktop only after
the operator says yes to that exact action (AskUserQuestion); an agent verifies
with the public landmarks in a temporary data directory and reads the operator's
database only through `doctor` and `/api/health`. See the project roadmap's
"Release & deployment strategy" for the surfaces table, promotion path, and
rollback.

**Triage rule.** Findings surfaced while executing a step are classified before
they are acted on, per the project roadmap's "Defect handling & triage": spec
rot → edit this roadmap's affected `<task>` block now; upstream gap → patch the
earlier step's prompt and add it to the carry-over checklist; implementation bug
→ fix in-step only if it blocks this step's acceptance criteria, otherwise an
issue and its own branch in a fresh conversation; architectural question → an
issue for a future phase; process improvement → recorded where the next
conversation will read it; security finding → jumps the queue by severity;
source drift (a NOAA layer, field, or product changed or vanished) → re-record
the affected source, update `docs/DATA_SOURCES.md` with the date, and add a
contract test in the same PR. The API's OpenAPI document is a contract: a change
to a route or a response model regenerates `docs/api/openapi.json` and, from
Step 4, the frontend's generated types in the same PR, and CI fails while either
is stale. A golden that changes is never "fixed" by regenerating it: an engine
or policy change that moves a replay or notification golden needs the operator's
approval in the PR, and this phase changes neither. A step's PR contains the
step plus blocking fixes only, and lists the issues it opened. When a merged PR
auto-closes an issue, the environment check is what earns the close — reopen or
follow up if a gap remains. `docs/phase05-qa-findings.md` is the rollup: every
finding, its class, and the guard added so the class cannot recur.

**Status rule.** Every step carries a `**Status:**` line directly under its `##
Step N — …` heading, before the Goal, and this file on `main` is the ledger of
what is done — never a chat transcript, never a later conversation
reconstructing history from `git log`. The line reads `Not started` when this
roadmap is written and is flipped by the step's OWN pull request: at Stage 3,
right after `gh pr create` returns the PR number, the agent sets it to `Complete
— PR #<n> (<YYYY-MM-DD>)`, appends ` ✅` to the step's heading (`## Step 3 — The
event stream, browser notifications, and the API's actions ✅`) so the completion
shows in the rendered preview, the outline, and the table of contents, sets the
step's Summary Table Status cell to `Complete — PR #<n>`, commits that edit on
the step branch, and pushes. The PR therefore carries its own completion mark,
and the roadmap on `main` says a step is complete exactly when that step's PR
merges — never before. This file's phase-level `**Status:**` line (under the
title) and the project roadmap are marked the same way, in the same commit: Step
1's PR flips both from `Not started` to `In progress` (the project roadmap's
`### Phase 5` line reads `In progress — phase05-roadmap.md`, and its row in the
"Phase Complexity Summary" table reads `In progress`), and the final step's PR
flips both to `Complete — …` (the project roadmap's with its row in the "Phase
Complexity Summary" table and the header `> **Status:**` line) and appends ` ✅`
to this file's `# ` title and to the project roadmap's `### Phase 5` heading, so
the project roadmap shows a finished phase the way this file shows a finished
step. There is no separate "update the roadmaps" chore: a step whose PR merged
without its Status line is a lifecycle violation, and the next step's Stage 1
(and `/roadmap-step`) refuses to start until the previous step reads `Complete`.
If a post-merge check fails — a Deployed & verified bullet, an alarm that never
fired — the step is NOT complete despite the merged line; say so, and the
`hotfix/` PR that completes it appends its own number to the line. `grep -n
'^\*\*Status:\*\*'` on this file is the phase's progress report, and the ✅
headings are the same report at a glance.

**Step lifecycle.** Every step in this phase follows the exact same six-stage
lifecycle, in order, with no exceptions. Each stage is a hard checkpoint — if a
stage is skipped, branch protection or the next step's Stage 1 will fail loudly,
and that is the safety net. AI coding agents MUST execute all six stages before
declaring a step complete.

1. **Create the branch.** Before any Read / Edit / Bash, run `git checkout -b
   feature/phase05-step<M>-<slug>` from a clean, up-to-date `main`. The exact
   branch name comes from this step's `**Branch:**` line. When the Worktree rule
   applies, the equivalent is `git fetch origin && git worktree add -b <branch>
   <worktree-path> origin/main`, followed by the worktree's bootstrap.

2. **Work on the branch, passing the security gate before every commit.** All
   commits land here. Never push to `main` directly — branch protection
   (`enforce_admins: true`) rejects it. Before each `git commit`, run the local
   security gate (secret/personal-data scan, SAST, dependency audit,
   sensitive-data diff review — see the step's `<security>` block and the
   project roadmap's "Per-step security gate"). It is fail-closed: a finding
   blocks the commit, so a security issue in this step's work is caught here,
   before the PR and before `main`.

3. **Open the PR, then mark the step.** `gh pr create --base main --head
   <branch>` with a Conventional Commits title and a body that references this
   roadmap step and its acceptance criteria. One PR per step; never bundle two
   steps into one PR. Then, with the PR number in hand, set this step's
   `**Status:**` line (directly under its heading) to `Complete — PR #<n>
   (<YYYY-MM-DD>)`, append ` ✅` to the step's `## Step` heading, set its Summary
   Table Status cell to `Complete — PR #<n>`, commit that edit on the step
   branch (`docs: mark Phase 5 Step <M> complete`), and push — the PR now
   carries its own completion mark, so the roadmap on `main` will say the step
   is complete exactly when the PR merges (Status rule). On the phase's first
   step, the same commit sets this roadmap's phase-level `**Status:**` (under
   its title) and the project roadmap's Phase 5 `**Status:**` to `In progress`;
   on the final step, both to `Complete`, with ` ✅` appended to this roadmap's
   `# ` title and to the project roadmap's `### Phase 5` heading.

4. **Wait for green checks, then squash-merge.** Every required status check
   must report success: the aggregate `gate` check of `ci.yml` (lint, typecheck,
   the test matrix with the coverage floor, the package smoke, the security
   scan, and from Step 4 the `frontend` job) and the aggregate `phase-verify`
   check (`phase-verify (01)` through `(04)`, and `(05)` from Step 8). If the PR
   goes BEHIND main while waiting, refresh with `gh pr update-branch --rebase` —
   never merge `main` into the branch; `required_linear_history: true` enforces
   rebase. Once every check is green:

   ```sh
   gh pr merge <PR_NUMBER> --squash --delete-branch
   ```

   If this step's `**Deploys:**` line names a surface, the merge is not the
   finish line: run the Deployed & verified check from the acceptance criteria
   against the target environment now (see the Deploy-and-verify rule) before
   declaring the step complete.

5. **Retire the branch (remote + local).** The `--delete-branch` flag plus the
   repo's `delete_branch_on_merge: true` setting retire the remote
   automatically. Sync local state and prune the merged branch plus any other
   `[gone]` labels left over from prior PRs:

   ```sh
   git switch main
   git pull --ff-only origin main
   git fetch --prune origin
   git branch -vv | grep ': gone]' | awk '{print $1}' \
     | xargs -r git branch -D
   ```

   If this step ran in its own worktree, remove it FIRST — `git worktree remove
   <worktree-path>`, then `git worktree prune` — because `git branch -D` refuses
   a branch still checked out in a worktree. Confirm with `git branch -vv` that
   only `main` and any intentional long-lived branches remain locally, and with
   `git worktree list` that only the primary tree remains.

6. **Dispose of every finding, declare completion, then new conversation.**
   Before you declare anything, walk the findings this step surfaced and send
   each to its destination per the Triage rule above — a note that a later step
   needs is edited into that step's `<task>` block now; a wrong claim in this
   step's spec is fixed in this roadmap now; an implementation bug is fixed
   in-step or exists as an issue with a number; a judgement call you made in the
   diff is explained in the PR body; a process lesson is written where the next
   conversation reads it. A finding you can only *describe* has not been
   disposed of, and an undisposed finding is an unmet acceptance criterion. Only
   once the PR is merged — and `main` therefore carries this step's `Complete`
   Status line — every acceptance criterion is affirmatively met, and every
   finding has a destination, say so plainly: end your final response with an
   explicit, unhedged completion line — verbatim shape "Step <M> is complete.
   You can now move on to Step <M+1>." — so the operator has a clean stopping
   point at which to close this conversation. That line is the LAST line of the
   response. Nothing follows it: no "Follow-ups (non-blocking)", no "Notes", no
   "Next", no "worth a glance", no suggested improvements. If you want to show
   your work, a short ledger may PRECEDE the line, one entry per finding naming
   its destination (an issue number, a file you edited, the PR body) — never an
   open item. If any acceptance criterion is NOT met, or any finding has no
   destination yet, do the opposite — state plainly that the step is NOT
   complete, name what is outstanding, and do not emit the completion line.
   "Done" means done, not "done, but here is what you still have to do". Then,
   for phase-boundary hygiene, the operator closes this Claude Code / Codex /
   Antigravity session and opens a fresh one before starting Step <M+1>; the new
   conversation begins again at Stage 1 of this lifecycle, with the next step's
   `**Branch:**` line driving the `git checkout -b` command. No work straddles
   two steps.

---

## Current State (as of Phase 4)

### Web surface

- `src/weatherbot/web/` holds only `__init__.py`, whose docstring says the layer
  "sits above the services layer, with the cli layer" and binds to loopback.
  Phase 1's check 9 requires that file to stay tracked; nothing else exists — no
  FastAPI, no uvicorn, no route, no static file. Neither `fastapi`, `starlette`,
  nor `uvicorn` is a dependency; `tests/test_architecture.py` already bans all
  three from the engine and the models.
- The import-linter `layers` contract ("Layers import downward only") lists
  `"weatherbot.cli | weatherbot.web"` as one layer of independent siblings, so
  today neither may import the other. `weatherbot serve` lives in `cli/serve.py`
  and must host the web app, so the contract has to change (Overview, "Design
  rationale"). Phase 2's check 3 reads that contract by its name and requires
  `weatherbot.models` last; its check 33 requires the database contract's
  sources to include `weatherbot.cli` and `weatherbot.web`; Phase 1's check 13
  requires a `forbidden` and a `layers` contract and the engine's
  `source_modules`. The "Only the services touch the database" contract forbids
  `sqlalchemy` and `alembic` in `weatherbot.web`, so the web layer reads the
  database only through `weatherbot.services`.
- `cli/serve.py`'s `run_monitor_loop` takes `data_dir/monitor.lock` without
  waiting (a second monitor exits 2, naming the holder's pid and start), sets up
  the rotating log file, opens the database through `open_monitor_session`
  (which sends the database-free toast and exits 1 when the database cannot
  open), and runs `asyncio.run(_loop(...))` inside
  `contextlib.suppress(KeyboardInterrupt)`; `_loop` awaits
  `services.schedule.run_monitor(engine, paths, settings=, runner="serve",
  stop=asyncio.Event(), clock=, sleep=, make_fetcher=, channels=,
  check_installed=)`. Its docstring already says Phase 5 adds the web server to
  the same process and event loop. Phase 4's check 36 requires `cli/serve.py` to
  define `serve` and `run_monitor_loop` and to contain
  `ProcessLock(paths.monitor_lock_path)` and `run_monitor(`.

### Services surface

- `MonitorService(..., listeners=)` calls each `CycleListener` — a synchronous
  `Callable[[CycleResult], None]` — after every cycle it runs, isolating a
  listener's exception; `run_monitor` and `MonitorSchedule` accept the same
  `listeners` and pass them to every cycle `serve` runs. `CycleResult` carries
  the cycle id, `trigger`, `runner`, `status`, the snapshot, each
  `AssessedLocation(location, stored, created, toggle_changed)`, the stored
  notifications, and `confirm_at`. Cycles that another process runs (`status`,
  `fetch`, `storms`, `alerts`, or `check --once` in a terminal, and the hourly
  fallback) take the same `cycle.lock` and write the same tables, but no
  listener in `serve` hears them; `monitor_cycles` records every cycle with its
  runner, trigger, status, and snapshot id. Phase 4's check 8 requires
  `CycleTrigger` to be exactly its nine values, `manual` among them.
- `services/notifications.py`: `Channel` is a protocol (`name`, `async
  deliver(notification) -> Delivery`), `LogChannel` delivers by storing,
  `CHANNEL_NAMES = ("log", "toast")` with the `ChannelName` literal, and
  `DELIVERY_RESULTS` are `delivered`, `failed`, `disabled`, and `unavailable`.
  `NotificationService.decide_cycle` decides each new assessment once and
  delivers through the channels it is given; `send(kind, title=, body=)` stores
  and delivers a notification that names no location (`notify test`'s);
  `recent(limit)` reads the log. Phase 4's check 43 requires
  `NOTIFICATION_KINDS` to be exactly `location`, `degraded`, `recovered`,
  `stale_monitor`, and `test`; the notifications document types a delivery's
  channel as a plain string.
- The read paths an API needs exist: `LocationRepository.list/get`,
  `SnapshotRepository.latest()/load(id)/drift_warnings(id)`,
  `AssessmentRepository.latest(name)/history(name, limit)/load(id)` returning
  `StoredAssessment(id, assessment, changes, stored_at)`, `HeartbeatRepository`
  `.rows()`, `CycleRepository.recent(limit)/get(id)`,
  `services.health.staleness` (the two-cadence rule), `setting_origins(paths,
  environ)` (every setting with its value and origin),
  `current_revision(engine)`, and `head_revision()`. `LocationService.add(name,
  lat, lon, polygon=None)` (async; NWS `/points` and one Nominatim reverse
  geocode) and `set_evacuation_order(name, on=)` are the write paths. Measured
  on 2026-10-24 over the recorded 2026-10-12 answers (one storm, two landmarks):
  `SnapshotRepository.latest()` takes a median 384 ms, because it decodes the
  whole snapshot — 1.8 MiB as JSON, of which the wind-speed probabilities are
  1.1 MiB, the breakpoint catalogue 386 KiB, and the storm's wind radii 199 KiB
  — while the map's Phase 5 layers (cone 19.8 KiB, track and forecast points 9.3
  KiB, watch-warning segments 1.9 KiB, outlook areas 17.6 KiB) total 49 KiB;
  `AssessmentRepository.latest` takes about 1 ms, and an assessment is about 5
  KiB.
- `ReplayCorpus.open(directory)` reads a corpus directory (the committed subset
  `tests/fixtures/replay/`, 11 MiB, or a `convert --full` output) and yields
  `Snapshot(origin="replay")` per advisory through `snapshots(atcf_id)`; the
  wheel ships no corpus, so `weatherbot replay` takes `--corpus DIR`. Measured
  the same day: Irma's 84 advisories read in 3.3 s (about 39 ms each), one
  advisory's cone, track, points, and segments are about 80 KiB, and replay
  geometry carries the archive's `native` CRS. Replay assessments are never
  stored, and `SnapshotRepository.save` refuses a replay snapshot.
- `services/disclaimer.py` holds `NOTICE` (the one line every read surface ends
  with), `ESSENTIALS` (the first-run paragraphs), and `full_text()` (the
  packaged `weatherbot/DISCLAIMER.md`).

### CLI surface

- `cli/__init__.py` registers every command as a literal `app.command("…")` or
  `app.add_typer(…)` line, which Phase 2's check 36, Phase 3's check 43, and
  Phase 4's check 41 read. `Runtime` (`cli/runtime.py`) is the test seam —
  `environ`, `make_fetcher`, `make_toast`, `identity`, `task_runner`, `windows`,
  `interpreter`, `which`, `now`, `sleep`, `terminal`, `width` — and
  `Context.channels` is `(LogChannel(), runtime.make_toast(settings))`.
- `cli/documents.py` defines the fifteen `--json` documents; its rule is that
  only `locations list --json` holds a location's coordinates and that `status`
  and `alerts` round distances and bearings, and its docstring says "Phase 5's
  API serves geometry". `tests/cli/test_documents.py` asserts that
  `docs/schema/` holds exactly the fifteen schemas, so an OpenAPI file cannot
  live there. The view builders (`cli/status.py`'s `_entry`, `_evidence`,
  `_official`, `_threat`, and the staleness entries) live in the CLI, which the
  web layer may not import.
- `tests/cli/test_serve_command.py` runs `serve` through `CliRunner` with a
  runtime whose `sleep` raises `KeyboardInterrupt` after the startup cycle, and
  Phase 2's V6.2 selects the whole `tests.cli` package, so a test there that
  binds a fixed port, opens a browser, or skips on one platform turns that row
  red. On the operator's machine the installed `\Weatherbot\serve` will hold
  port 8765 from Step 1's deployment on, while `verify_phase04.py --post` runs
  the offline suite beside it.

### Configuration and logging surface

- `Settings` holds `[logging]`, `[http]`, `[engine]`, `[monitor]`, and
  `[notifications]`, each a frozen `_Section`; `ENVIRONMENT_OVERRIDES` maps each
  `(table, key)` to a literal `WEATHERBOT_*` name (Phase 3's check 24 and Phase
  4's check 14 read it as literals); a `ConfigError` names the key, never the
  value; and the module states that a setting is never a secret, a location, or
  a coordinate. `config show` lists every setting with its origin.
- `tests/conftest.py` clears every `WEATHERBOT_*` variable except the two tool
  variables (Phase 2's check 32 reads that pair exactly), points both
  directories into the test's temporary directory, and sets
  `WEATHERBOT_NOTIFICATIONS_TOAST=false`; a new override needs no conftest
  change, and setting another variable there breaks no check.
- `configure_logging(level, *, log_file=None)` installs `RedactingFilter` on
  every handler; under `pythonw.exe` it points `sys.stdout` and `sys.stderr` at
  `os.devnull`, so a library that writes to a standard stream raises nothing.

### Frontend and build surface

- No `frontend/` directory, `package.json`, or lock file exists. The operator's
  machine has Node 22.18.0 and npm 10.9.3 (checked 2026-10-24), below the engine
  floors of jsdom 30 (`^22.22.2 || ^24.15.0 || >=26`) and React Router 8
  (`>=22.22.0`); Node 24 is in maintenance LTS until 2028-04-30, and Node 26
  becomes LTS on 2026-10-28. GitHub's hosted runners carry a preinstalled Node,
  which CI must not rely on; `actions/setup-node`'s latest release is v7.1.0
  (commit `949feb2413d6458794dcd2491c4babbbce0c15c1`, 2026-10-08).
- `uv_build` (0.12.x) ignores `.gitignore`: checked on 2026-10-24 with a probe
  project, a git-ignored `src/<package>/web/static/` (an `index.html` and an
  `assets/` file) landed in both the sdist and the wheel, and the same `uv
  build` without the directory still succeeded. So a built interface copied into
  `src/weatherbot/web/static/` before `uv build` ships in the wheel, and Phase
  1's, 2's, and 3's `--py` modes, which each run `uv build`, stay green with or
  without it.
- `ci.yml`'s `package` job builds the sdist and the wheel on `ubuntu-latest` and
  `windows-latest`, installs the wheel into a fresh environment, compares
  `--version`, and opens a new database at the head (Phase 2's check 35 reads
  `WEATHERBOT_DATA_DIR` and `open_database` there; Phase 4's check 31 reads both
  platforms in the `test`, `typecheck`, and `package` jobs). The `gate` job
  requires every job in its `needs` list; a new job joins by joining that list.
- `.github/dependabot.yml` covers `uv`, `github-actions`, and `pre-commit`, and
  its header says npm joins when `frontend/` exists. `.gitignore` ignores
  `dist/` and `build/` everywhere and `.vscode/`; `.gitattributes` marks only
  `tests/fixtures/**` `-text` and deliberately sets no global line-ending rule,
  so pre-commit's `mixed-line-ending --fix=lf` is what keeps frontend files LF.

### Security & sensitive-data surface

- Data in play: the operator's locations (names, points, NWS zones, the
  evacuation toggle), which the API serves to the browser for the map's marker
  and the dashboard; the distances and bearings of storms from them; the
  notifications about them; and the effective settings. There is no secret: no
  source needs a key, and the web layer adds no token (LAN mode and its token
  are Phase 8's).
- Controls today: the four-check gate in pre-commit and CI's `security` job —
  gitleaks, bandit over `src` and `scripts`, `scripts/audit_deps.py` (pip-audit
  over `uv.lock`), and `scripts/check_personal_data.py`, whose R2 flags any
  coordinate pair or `lat`/`lon` assignment with three or more decimals in any
  tracked text file (no NUL byte in the first 8 KB: TypeScript, TSX, JSON, and
  CSS included) unless it equals one of the two landmarks in
  `scripts/public_landmarks.toml`. Phase 1's check 29 scans every tracked byte
  for a private-key block, an AWS key, and an Anthropic key shape. Phase 2's
  check 16 forbids the text `verify=False` and `follow_redirects=True` in the
  package, its check 20 every standard-library XML module, and its check 28 any
  string literal holding `/points/` or `point=` outside `sources/nws.py` and
  `sources/http.py` — which catches `endpoint=` and `breakpoint=` in a
  docstring, and an API route named `/points/`.
- Patterns every step mirrors: tests use the two landmarks or values generated
  at run time, never another coordinate literal; a message names a rule, a key,
  a route, or a source, never a value; subprocesses take argument lists; the
  operator's database is read only through `doctor` (and, from Step 1, through
  the running service's own `/api/health`); and every new dependency passes its
  audit.

### Operations & observability surface

- Health today: the `heartbeats` table (per source, watch, and runner, with the
  two-cadence staleness rule), the staleness banner in `status`, `doctor`'s
  `settings`, `database`, `migrations`, `locations`, `heartbeat`, `toast`,
  `tasks`, and `path` checks, the degraded-data alarm (a toast and a log entry
  after 3 consecutive failures of a ladder source), the stale-monitor alarm the
  hourly `\Weatherbot\check` raises, and the database-free toast. Phase 2's,
  3's, and 4's alarm proofs run `doctor --offline --json` on a fresh temporary
  database and require exit 0 — so a new `doctor` check reads `skip`, never
  `fail`, until there is something to judge — then stamp an unknown revision and
  require exit 1.
- The operator's machine runs the installed copy (`uv tool install --from
  <checkout> weatherbot`, `~/.local/bin`) at `v2.0.0-phase-4` under
  `\Weatherbot\serve` (at logon, `pythonw.exe`, `InteractiveToken`,
  `LeastPrivilege`) and `\Weatherbot\check` (hourly at HH:25). The project
  roadmap's operations strategy names `/api/health` — version, scheduler state,
  last successful fetch per source, and the Alembic head — as `serve`'s health
  signal, read by `doctor`, the dashboard's staleness banner, and the
  post-upgrade check. The package version stays `2.0.0.dev0` until Phase 8.

### Documentation surface

- `README.md`'s `## Status` says Phases 1 to 4 are complete and Phase 5 is next;
  its `## Commands` lists every command, with `### Running unattended`. Phase
  3's check 47 needs `weatherbot status`, `weatherbot replay`, and `weatherbot
  locations evacuation` inside `## Commands`, and Phase 4's check 46 needs ten
  command strings anywhere and a `## Status` naming Phase 4 and Phase
  5. `CONTRIBUTING.md` documents the checks, local data, every Phase 4 surface,
     and the gate; `AGENTS.md` describes the layers ("`cli` and `web` may import
     `services`"); `CHANGELOG.md` keeps one `## [Unreleased]` heading (Phase 1's
     check 4) with a group per phase. `docs/` holds `ALERT-LADDER.md`,
     `DATA_SOURCES.md`, the QA ledgers, `schema/`, and the roadmaps; no API
     document exists. Version 1 deleted `docs/api-reference.md` and
     `.vscode/settings.json`, and Phase 1's check 10 fails if either is tracked
     again.

### Verification surfaces

- `scripts/verify_phase04.py` is the structural template: 51 standard-library
  static checks, the modes `--fast`, `--py`, `--live`, `--security`, `--all`,
  and `--post`, and 29 V rows built from JUnit runs (offline with the engine and
  policy coverage floors, live, and desktop) in which every selection must match
  a test, a failure fails, and a skip is never a pass. Its `--post` nests Phase
  3's (80 checks), which nests Phase 2's (73) and Phase 1's (75); it reads
  `main`'s latest `ci.yml` run, so the canonical run waits for that run to
  finish.
- `.github/workflows/phase-verify.yml` runs matrix entries `"01"` to `"04"`
  (`--fast` and `--security` each) under the required aggregate `phase-verify`.
  Step 8 appends `"05"`; the four entries stay.
- Checks of the earlier phases that this phase's growth could turn red, and how
  each stays green:

| Check | Reads | How Phase 5 keeps it green |
| ----- | ----- | -------------------------- |
| P1 10 | v1's 70 deleted paths | no `docs/api-reference.md`, no `.vscode/` |
| P1 25, 26 | every workflow `uses:` and top-level `permissions:` | SHA pins |
| P1 29 | key shapes in every tracked byte | no key in `frontend/` |
| P2 3, 33 | layers contract name, models last; db contract | kept as they are |
| P2 28 | `point=` and `/points/` literals | no such route or docstring |
| P2 V6.2 | the whole `tests.cli` package | web tests in `tests/web/` |
| P3 8 | unique `test_*.py` basenames | names checked first |
| P3 47 | README `## Commands` names three commands | lines kept |
| P4 8 | the nine `CycleTrigger` values | "check now" uses `manual` |
| P4 36 | `ProcessLock(...)` and `run_monitor(` in `cli/serve.py` | kept there |
| P4 37 | `check`'s `run_monitor_loop(ctx, runner="check")` | call untouched |
| P4 38, V5.4 | `simulate_advisory.py`'s tokens and last line | behaviour kept |
| P4 43 | the five `NOTIFICATION_KINDS` | browser test uses `test` |
| P4 46 | README `## Status` names Phases 4 and 5 | read at the tag |
| P4 47, 48 | 51 checks; three test names in its test file | both kept |

- Phase 4's check 46 and its mutation case in
  `tests/test_phase04_verification.py` (which asserts the README phrase "and
  Phase 4 (monitoring and notifications) are complete" is present) break on the
  first edit to `README.md`'s `## Status`; the step that makes that edit
  converts the check to read `v2.0.0-phase-4:README.md` and the test to a
  tagged-tree case, in the same PR, as Phase 3 Step 1 did for Phase 2's check
  31. Phase 2's and 3's mutation cases also pin `.gitignore`'s `*.sqlite3-*`
      line, `cli/__init__.py`'s `app.command("replay")`, and `README.md`'s
      `weatherbot locations evacuation`; edits keep each. Taken test basenames
      include `test_health`, `test_config`, `test_status`, `test_locations`,
      `test_notifications`, `test_replay`, `test_privacy`, `test_commands`,
      `test_documents`, and `test_serve_command`.

### Carry-over from Phase 4

Every item Phase 4 handed to this phase, and where it lands:

| Item | Source | Lands in |
| ---- | ------ | -------- |
| FastAPI app and `/api/events` inside `serve` | P4 pre-ship items | 1, 3 |
| Keep check 36's calls in `cli/serve.py` | P4 pre-ship items | Step 1 |
| Convert check 46 when README's Status changes | P4 pre-ship items | Step 1 |
| Serve the heartbeat and the staleness banner | P4 Dependency line | 1, 2, 5 |
| Serve the notification log | P4 Dependency line | Steps 2, 5 |
| Browser notifications behind `Channel` | P4 "Not in scope" | Steps 3, 5 |
| Dependabot `npm` for `frontend/` | Project 1.2, 5.3 | Step 4 |
| Issue #44 (`advisory_issued` wording) | P4 QA ledger | its own `fix/` |
| Issue #33 (surge and extreme wind) | P4 QA ledger | the operator |
| The `PATH` shadow of version 1 | P4 QA ledger | the operator |
| Dependabot PRs #8, #31, #47, #48 | open on 2026-10-24 | maintenance |

---

## Execution Order

```
Step 1  (web server in serve)             create_app + uvicorn beside
                                          run_monitor + [web] + guards
                                          + /api/health + OpenAPI + doctor
                                          → implement
  ↓
Step 2  (read API + map geometry)         locations, assessments, storms,
                                          alerts, timeline, notifications,
                                          settings, map, replay map
                                          → implement
  ↓
Step 3  (events + actions)                EventHub + /api/events + cycle
                                          watcher + BrowserChannel + POST
                                          routes (location, toggle, check,
                                          test notification)
                                          → implement
  ↓
Step 4  (frontend chassis)                frontend/ (Vite, React, TS,
                                          Tailwind, Query) + generated
                                          types + gate + CI + wheel
                                          → implement
  ↓
Step 5  (dashboard + pages)               Dashboard, Storms, Alerts,
                                          Timeline, Settings, banner,
                                          browser notifications
                                          → implement
  ↓
Step 6  (map)                             Leaflet (direct) + OSM tiles
                                          + layers + replay picker
                                          → implement
  ↓
Step 7  (browser smoke + idle cost)       Playwright smoke + idle CPU +
                                          the operator's dashboard
                                          → implement
  ↓
Step 8  (QA + verify_phase05.py)          scripts/verify_phase05.py
                                          + docs/phase05-qa-findings.md
                                          + phase-verify.yml entry "05"
                                          → create

--- post-implementation ---

V1  serve hosts the API on loopback only; the guards hold;
    /api/health answers on the operator's machine.
V2  Every read route matches its schema; coordinates only
    where the map needs them; the map layers are cached.
V3  A stored cycle reaches a subscriber as its events; the
    browser channel reports honestly; actions refuse CSRF.
V4  The interface builds, lints, audits, and ships in the
    wheel; a wheel install serves it without Node.
V5  Every page renders from fixtures; the disclaimer and
    the staleness banner show; queries refetch on events.
V6  The map draws cones, tracks, points, segments, and
    areas, live and replayed, with the location markers.
V7  The browser smoke sees a stored change without a
    reload; idle CPU is near zero; the dashboard is live.
V8  verify_phase05.py --fast and --security exit 0 in
    phase-verify (05); the phase is closed.
```

Steps are sequential by dependency. Step 1 puts the server into the `serve`
process with every guard, the health route, and the OpenAPI pipeline, so each
later route inherits the guards and joins the committed contract; Step 2's read
routes are what Step 3's events tell a page to refetch, and Step 3's actions
reuse Step 2's response models; Step 4's generated types come from the OpenAPI
document Steps 1 to 3 completed, and its build pipeline is what Steps 5 and 6
add pages to; Step 5's shell, navigation, and event subscription are what Step
6's map page plugs into; Step 7 drives Steps 1 to 6 end to end and deploys the
result; Step 8 verifies every prior step. Steps 5 and 6 touch different pages,
but both edit the router, the navigation, the shared query keys, and the
frontend's tests and documents, so this phase draws no steps in parallel, and
the Worktree rule permits no concurrent steps.

---

## Step 1 — The web server inside serve ✅

**Status:** Complete — PR #61 (2026-10-26)

> **Goal:** Put a guarded web server into the `serve` process before any route
> carries data. `weatherbot.web.create_app(state)` builds the FastAPI app with
> Swagger UI and ReDoc off (both load scripts from a CDN) and its OpenAPI
> document at `/api/openapi.json`; `weatherbot.web.guards` adds, as pure ASGI
> middleware, the host allowlist, the same-origin JSON rule for writes, and the
> security headers on every answer; `GET /api/health` reports the version, the
> database revision and head, the scheduler, every heartbeat's staleness, the
> next NHC product time, the built interface's identity, and whether a corpus is
> open; the built interface (when present) is served from
> `src/weatherbot/web/static/` with a history fallback, and a plain page says so
> when it is not; `weatherbot.web.server.WebServer` runs uvicorn as a task
> beside `run_monitor` in `cli/serve.py`'s loop, on `[web] host` and `[web]
> port` (loopback only, default `127.0.0.1:8765`), surviving a taken port and
> shutting down cleanly on every way out; `serve --open/--no-open` opens the
> dashboard only for a person; `doctor` gains its `web` check;
> `scripts/export_openapi.py` commits `docs/api/openapi.json`; the layers
> contract puts `weatherbot.cli` above `weatherbot.web`; and Phase 4's check 46
> moves to its tag as `README.md`'s Status turns to Phase 5. This step lands the
> chassis; Steps 2 and 3 add the routes.

**Branch:** `feature/phase05-step1-web-server`

**Deploys:** the operator's machine → with the operator's yes, and away from the
hourly fallback at HH:25, `\Weatherbot\serve` is stopped (`schtasks /End`,
because a running `pythonw.exe` holds the tool's files), the installed copy is
reinstalled from the merged `main` (`uv tool install --reinstall --from
<checkout> weatherbot`), and the task is started again (`/Run`), so the running
`serve` hosts the web server: `http://127.0.0.1:8765/api/health` must answer
from it, and the installed copy's `doctor --offline --json` must pass its `web`
check. GitHub Actions → the first `ci.yml` and `phase-verify.yml` runs on `main`
must be green.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.18/1M           | $4.00/1M*          | $8.46/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.56/1M           | $6.02/1M           | $4.00/1M*          |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | XHigh              | XHigh              |
|               | AA       | not measured       | 51                 | 52.4               |
|               | Price    | $2.40/1M*          | $4.00/1M           | $16.36/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out) ×
the tokens the model uses at that level; * token use not yet measured, a typical
model's at that level assumed.

**Conversation:** New

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that
column's usage pool reads `tight` or `exhausted`, run the first of its Runner-up
and Backup whose pool has headroom; on a `tight` pool an option marked ↓ (the
Pick one level lower) also runs. With none, a `tight` column runs the Cost
column and an `exhausted` one its Backup.

> Settings updated 2026-10-25 (rerank): each column's Runner-up and Backup now come from makers other than its Pick; every Pick is unchanged.
>
> Ran 2026-10-26: Balanced Pick — Gemini 4 Argon · Effort High · Thinking On on Antigravity. Selected by the **Runs:** rule (Google AI Pro pool reads headroom).

**Model rationale:** Step 1 is coding with an agentic secondary category: an
ASGI server embedded in an asyncio loop that already runs the scheduler,
browser-facing guards, a settings table, a health route, the OpenAPI pipeline, a
new `doctor` check, a layering change, a historical check conversion, and an
on-machine deployment under Task Scheduler. Its overall complexity is High —
signal handling and shutdown on Windows and Ubuntu, a port that may be taken,
DNS rebinding and cross-site requests, and tests that must never bind the
operator's port — and it is not novel: this roadmap fixes the layering, the
guards, the server's behaviour, and the health contents. The columns differ in
depth and maker: Balanced runs Gemini 4 Argon on Antigravity at Effort High with
thinking on; Quality runs Opus 5.5 on Claude Code at Effort XHigh (always
thinking, so no Thinking field) for the closest audit of the guards and the
shutdown paths; Cost moves it to GPT-6.1 Sol on Codex at Intelligence High.
Google AI Pro, the claude.ai Max subscription, and ChatGPT Pro 5x fund the three
platforms, so each column costs nothing at the margin while its pool has
headroom; when a column's pool reads `tight` or `exhausted`, the **Runs:** rule
moves the step to that column's Runner-up or Backup. The conversation is new per
phase-boundary hygiene.

```xml
<task>
  <lifecycle>
    This step MUST follow all six
    stages, in order. Stages 1, 3,
    4, 5, 6 are AS BINDING as any
    `<requirement>` below. Do not
    emit the Stage 6 completion
    line until the PR is merged and
    every acceptance criterion for
    this step is affirmatively met.

    1. CREATE THE BRANCH. Before
       any Read / Edit / Bash, run
       `git checkout -b
       feature/phase05-step1-web-server`
       from a clean, up-to-date
       `main`. The exact branch
       name is in this step's
       `**Branch:**` line above.
       If the Worktree rule
       applies, use `git fetch
       origin && git worktree add
       -b <branch> <path>
       origin/main` instead, then
       bootstrap the worktree.

    2. WORK ON THE BRANCH. All
       commits land here. `main`
       is protected with
       `enforce_admins: true` —
       direct pushes will be
       rejected.

    3. OPEN THE PR, THEN MARK THE
       STEP. `gh pr create --base
       main --head <branch>` with a
       Conventional Commits title
       and a body that references
       this roadmap step and its
       acceptance criteria. One PR
       per step. Then, in this
       roadmap file: set this
       step's `**Status:**` line
       (directly under its heading)
       to `Complete — PR #<n>
       (<YYYY-MM-DD>)`, append ` ✅`
       to the step's `## Step`
       heading, and set its
       Summary Table Status cell to
       `Complete — PR #<n>`. Commit
       that edit on the step
       branch and push — the PR
       carries its own completion
       mark, so the roadmap on
       `main` marks this step
       complete exactly when the PR
       merges (Status rule). Same
       commit: on the phase's first
       step, set this roadmap's
       phase-level `**Status:**`
       (under its title) and the
       parent project roadmap's
       Phase 5 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 5`
       heading.

    4. WAIT FOR GREEN CHECKS, THEN
       SQUASH-MERGE. Every required
       check must pass. If the PR
       falls behind main, refresh
       with `gh pr update-branch
       --rebase` — never merge main
       into the branch
       (`required_linear_history:
       true`). Once green:
       `gh pr merge <PR> --squash
       --delete-branch`. If this
       step's `**Deploys:**` line
       names a surface, the merge
       is not the finish line: run
       the Deployed & verified
       check against the target
       environment before
       declaring the step complete.

    5. RETIRE THE BRANCH. Sync
       local: `git switch main &&
       git pull --ff-only origin
       main && git fetch --prune
       origin`. Prune any local
       `[gone]` branches. If the
       step ran in a worktree,
       `git worktree remove <path>`
       FIRST — the branch prune
       fails while the branch is
       checked out there.

    6. DISPOSE OF EVERY FINDING,
       DECLARE COMPLETION, THEN
       NEW CONVERSATION. First
       send every finding this
       step surfaced to its
       destination (Triage rule):
       a note for a later step →
       edit that step's <task>
       block now; spec rot → edit
       this roadmap now; a bug →
       fixed in-step or an issue
       number; a judgement call in
       the diff → the PR body; a
       process lesson → written
       where the next conversation
       reads it. A finding you can
       only describe is NOT
       disposed of, and counts as
       an unmet criterion. Only
       once the PR is merged — and
       `main` therefore carries
       this step's `Complete`
       Status line — every
       acceptance criterion is
       affirmatively met, and every
       finding has a destination,
       say so plainly: end your
       final response with an
       explicit, unhedged
       completion line — verbatim
       shape "Step 1 is
       complete. You can now move
       on to Step 2." That
       line is the LAST line of
       the response. NOTHING
       follows it — no "Follow-ups
       (non-blocking)", "Notes",
       "Next", "worth a glance",
       or suggested improvements.
       A short ledger may PRECEDE
       it, one entry per finding
       naming its destination
       (issue #, file edited, PR
       body) — never an open item.
       If any criterion is unmet
       or any finding has no
       destination, state plainly
       that the step is NOT
       complete, name what is
       outstanding, and omit the
       completion line. "Done"
       means done. Then, for
       phase-boundary hygiene, the
       operator closes this
       session and opens a fresh
       one before Step 2.
  </lifecycle>

  <security>
    Security is a gate on THIS
    step, not a later phase. It is
    AS BINDING as any
    `<requirement>` below. Before
    the Stage-2 commit, this
    step's work MUST pass the
    local, fail-closed security
    gate — the SAME gate wired
    into the pre-commit hook and
    re-run in CI:

    1. SECRET / PII SCAN. No
       credentials, API keys,
       tokens, or real PII in the
       diff (gitleaks /
       detect-secrets or the
       project's equivalent).
       Secrets go in the secrets
       manager, never in source or
       committed env files.

    2. SAST. No new injection,
       unsafe deserialization,
       weak crypto, path
       traversal, or unsafe-eval
       pattern (bandit / semgrep /
       eslint-plugin-security per
       the stack). Suppress a
       finding ONLY with an inline
       justification comment.

    3. DEPENDENCY AUDIT. Any new
       or bumped dependency passes
       the audit (pip-audit / npm
       audit / osv-scanner); no
       known-vulnerable, yanked,
       or typo-squatted package.

    4. SENSITIVE-DATA REVIEW.
       Whatever this step touches
       stays least-privilege,
       encrypted in transit + at
       rest, and out of logs and
       client bundles. If the step
       adds a data path, name how
       PII/secrets are protected.

    A finding blocks the commit —
    fix it in this step, do not
    defer. Do not declare the step
    complete until the gate is
    clean. This is the safety net
    that stops a security issue
    from reaching the branch, the
    PR, or `main`.

    THIS STEP opens Weatherbot's first network listener. It binds
    loopback only: `[web] host` accepts `127.0.0.1`, `::1`, and
    `localhost`, and any other value is a configuration error
    naming the key (never the value) until Phase 8's LAN mode. The
    guards are part of the step's definition of done, each with a
    test: a request whose `Host` names anything but `127.0.0.1`,
    `localhost`, or `[::1]` (any port) answers 400 (DNS
    rebinding); no answer carries an `Access-Control-Allow-*`
    header, an `OPTIONS` preflight included; a `POST`, `PUT`,
    `PATCH`, or `DELETE` answers 415 unless its `Content-Type` is
    `application/json`, and 403 when its `Origin` is present and
    is not `http://` plus its own `Host`, or its `Sec-Fetch-Site`
    is present and is not `same-origin` (cross-site request
    forgery); any `/api/` request whose `Sec-Fetch-Site` is
    present and neither `same-origin` nor `none` answers 403;
    every answer carries the Content-Security-Policy,
    `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
    `Referrer-Policy`, `Cross-Origin-Opener-Policy: same-origin`,
    `Cross-Origin-Resource-Policy: same-origin`, and a
    `Permissions-Policy` that turns off geolocation, camera, and
    microphone; and every `/api/` answer, errors included, carries
    `Cache-Control: no-store`. FastAPI's `/docs` and `/redoc` are
    off, because both load scripts from a CDN. `/api/health` holds
    no coordinate, no location name, and no path. The built
    interface is served from a map of its files made at start, so
    no request text reaches a filesystem call (a UNC path on
    Windows would otherwise send the operator's credentials to
    another host). Validation errors answer without their input.
    uvicorn's access log is off and its loggers reach Weatherbot's
    handlers, which redact tracebacks as they redact messages; a
    request's path or query never reaches a log line above DEBUG.
    `doctor`'s probe of the running server goes to loopback with
    `trust_env=False`, so no proxy setting can carry it elsewhere.
    No test binds port 8765 or opens a
    browser: `tests/conftest.py` sets `WEATHERBOT_WEB_PORT=0`, and
    the browser opens only through `Runtime.open_browser`. New
    dependencies (`fastapi`, `starlette`, and `uvicorn` without
    extras) pass `pip-audit --strict`; no docstring or string
    literal in the
    package writes `point=` or `/points/` (Phase 2's check 28
    catches `endpoint=`).
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 5 (Web app MVP). Step 1:
    the web server inside `serve`.

    Current state (as of Phase 4):

    - `src/weatherbot/web/__init__.py` is the whole web layer; no
      FastAPI, Starlette, or uvicorn is installed.
      `tests/test_architecture.py` bans all three from the engine
      and the models. The import-linter `layers` contract ("Layers
      import downward only") has `"weatherbot.cli |
      weatherbot.web"` as one layer of independent siblings; Phase
      2's check 3 reads that contract by name with
      `weatherbot.models` last, its check 33 needs the database
      contract's sources to include `weatherbot.cli` and
      `weatherbot.web`, and Phase 1's check 13 needs a `forbidden`
      and a `layers` contract. `AGENTS.md` says "`cli` and `web`
      may import `services`".
    - `cli/serve.py`: `serve(ctx)` calls `run_monitor_loop(ctx,
      runner="serve")`, which takes `ProcessLock(paths.
      monitor_lock_path)` without waiting (a second monitor exits 2
      with `monitor_already_running_message`), configures the log
      file, opens the database through `open_monitor_session`, and
      runs `asyncio.run(_loop(...))` inside
      `contextlib.suppress(KeyboardInterrupt)`; `_loop` awaits
      `run_monitor(...)` with a fresh `asyncio.Event` stop. `check`
      (without `--once`) shares `run_monitor_loop` with `runner=
      "check"` and must not host the web server. Phase 4's check 36
      needs `cli/serve.py` to define `serve` and
      `run_monitor_loop` and to contain
      `ProcessLock(paths.monitor_lock_path)` and `run_monitor(`.
    - `tests/cli/test_serve_command.py` runs `serve` through
      `CliRunner` with a runtime whose `sleep` raises
      `KeyboardInterrupt` after the startup cycle, and asserts the
      lock is released and the runner's cadence cleared; Phase 2's
      V6.2 selects all of `tests.cli`, so nothing there may skip on
      a platform or bind a fixed port. `pytest` runs with
      `filterwarnings = ["error"]`, so an unclosed socket's
      `ResourceWarning` fails a test.
    - `Runtime` (`cli/runtime.py`) holds the seams (`environ`,
      `make_fetcher`, `make_toast`, `identity`, `task_runner`,
      `windows`, `interpreter`, `which`, `now`, `sleep`,
      `terminal`, `width`); `Settings` (`services/config.py`) holds
      frozen `_Section` tables with literal `ENVIRONMENT_OVERRIDES`
      (Phase 3's check 24 and Phase 4's check 14 read them);
      `tests/conftest.py` clears `WEATHERBOT_*` (keeping the two
      tool variables, Phase 2's check 32) and sets
      `WEATHERBOT_NOTIFICATIONS_TOAST=false`.
    - `doctor` (`services/doctor.py`, `cli/doctor.py`) runs
      `settings`, `database`, `migrations`, `locations`,
      `heartbeat`, `toast`, `tasks`, and `path`; `tasks` and `path`
      skip under `WEATHERBOT_DATA_DIR`. The alarm proofs of Phases
      2 to 4 run `doctor --offline --json` on a fresh temporary
      data directory and need exit 0, so a new check skips until
      there is something to judge.
    - Read from the wheels on 2026-10-24: FastAPI 0.162.0 (typed;
      Starlette 1.10.0; built-in `fastapi.sse`, which Step 3
      uses) and uvicorn 0.54.0 (typed; needs only `click` and
      `h11` without extras). uvicorn's `Server.serve()` wraps its
      work in `capture_signals()`, which replaces the SIGINT,
      SIGTERM, and SIGBREAK handlers and re-raises a captured
      signal after shutdown; its `main_loop` wakes every 100 ms to
      read `should_exit`; after startup `server.started` is true
      and `server.servers[0].sockets` holds the bound socket.
      FastAPI's default `/docs` and `/redoc` pages load assets from
      cdn.jsdelivr.net.
    - Verified on 2026-10-24 with those versions, on Windows and
      Ubuntu: a uvicorn startup failure (a taken port) calls
      `sys.exit(3)` inside `serve()`, and that `SystemExit`
      escapes a task and `asyncio.run`, killing the process; with
      an open server-sent event client the default shutdown never
      returns (`timeout_graceful_shutdown` bounds it); an idle
      server takes about 200 ms to stop; `server.started` stays
      true after shutdown, so the task's completion is the
      liveness signal; and `host="localhost"` with port 0 binds
      two sockets on different ports. Since Starlette 1.2.0,
      importing `fastapi.testclient` or `starlette.testclient`
      without `httpx2` warns, which `filterwarnings = error` turns
      into a failure, and httpx's `ASGITransport` buffers a whole
      response. Starlette's `TrustedHostMiddleware` drops the
      port, matches case-insensitively, needs IPv6 bracketed
      (`[::1]`), and refused `127.0.0.1.evil.example`,
      `2130706433`, `127.1`, and `127.0.0.1:8765@evil.example`.
      FastAPI's OpenAPI JSON was byte-identical on both platforms
      but for `Path`-typed defaults and CRLF from a text-mode
      write. Starlette below 1.3.1 carries five 2026 advisories,
      one a `StaticFiles` UNC-path leak on Windows.
    - `tests/cli/test_documents.py` pins `docs/schema/`'s listing
      to the fifteen CLI documents, so the OpenAPI document lives
      at `docs/api/openapi.json`; `scripts/export_schemas.py` is
      the pattern for its exporter (two-space indent,
      `ensure_ascii=False`, trailing newline, `--check`).
    - Phase 4's check 46 (`scripts/verify_phase04.py`) reads
      `README.md`'s `## Status` for "Phase 4" and "Phase 5", and
      its mutation case in `tests/test_phase04_verification.py`
      asserts the phrase "and Phase 4 (monitoring and
      notifications) are complete" is present before replacing it;
      `scripts/verify_phase01.py` (checks 7, 9, and 12) and
      `scripts/verify_phase02.py` (check 31) show how a check
      reads a file at a tag (`git show <tag>:<path>`).
    - The operator's machine runs the installed copy at
      `v2.0.0-phase-4` under `\Weatherbot\serve` (at logon,
      `pythonw.exe`, no console) and `\Weatherbot\check` (hourly
      at HH:25); `services.tasks` registers both, and `Runtime`
      carries `task_runner` for `schtasks`.

    Files to read (every file before drafting):
    - docs/roadmap/phase05-roadmap.md (Overview and its design
      rationale, Current State, this step, and Steps 2, 3, and 7,
      which build on it).
    - docs/roadmap/ROADMAP.md (Phase 5; §3; §5 "Security &
      privacy strategy" and "Operations & observability
      strategy").
    - pyproject.toml, AGENTS.md, tests/test_architecture.py,
      tests/conftest.py.
    - src/weatherbot/web/__init__.py, cli/__init__.py,
      cli/serve.py, cli/runtime.py, cli/doctor.py,
      cli/documents.py; services/config.py, services/doctor.py,
      services/schedule.py (`run_monitor`, `PRODUCT_HOURS`),
      services/monitor.py, services/health.py, services/logs.py,
      services/disclaimer.py, services/persistence/database.py.
    - scripts/export_schemas.py, scripts/verify_phase04.py,
      tests/test_phase04_verification.py,
      scripts/verify_phase01.py (its tagged reads),
      tests/cli/test_serve_command.py, tests/cli/cli_support.py.
    - README.md, CONTRIBUTING.md, CHANGELOG.md.
  </context>

  <goal>
    Ship the app factory, the guards, the health route, the
    built-interface serving, the embedded server, `[web]`, `serve
    --open/--no-open`, `doctor`'s `web` check, the OpenAPI export,
    the layering change, and check 46's conversion; prove every
    guard, every shutdown path, and the taken-port path offline;
    and deploy the server on the operator's machine.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Dependencies and layering. Add `fastapi>=0.162.0`,
      `starlette>=1.10.0` (imported directly), and
      `uvicorn>=0.54.0` (no extras: no uvloop, httptools,
      websockets, or watchfiles) to `[project] dependencies`, lock,
      and pass `pip-audit --strict` and strict pyright with no stub
      package and no new ignore; a transitive package the audit
      flags is bumped in its own `fix(deps)` commit, as Phase 3
      Step 6 and Phase 4 did. Change the `layers` contract's
      first layer from `"weatherbot.cli | weatherbot.web"` to two
      layers, `"weatherbot.cli"` above `"weatherbot.web"`, keeping
      its name and `weatherbot.models` last; leave the database
      and engine contracts as they are. Update `AGENTS.md`'s layer
      list and import rule ("`cli` may import `web`, because
      `serve` hosts it; `web` never imports `cli`"), and the
      docstrings of `weatherbot/cli/__init__.py` and
      `weatherbot/web/__init__.py`. `tests/test_architecture.py`
      asserts the order (`weatherbot.cli` before `weatherbot.web`
      in the layers list).
    </requirement>

    <requirement>
      Settings. `services/config.py` gains `WebSettings` (`[web]`):
      `host: str = "127.0.0.1"`, validated to one of `127.0.0.1`,
      `::1`, `localhost` (the error names `[web] host` and Phase 8,
      never the value), and `port: int = 8765` with `ge=0,
      le=65535`, where 0 picks a free port (tests and the browser
      smoke) and 1 to 1023 is refused. `NotificationSettings`
      gains nothing yet (Step 3 adds `browser`). Literal
      `ENVIRONMENT_OVERRIDES` entries: `("web", "host"):
      "WEATHERBOT_WEB_HOST"` and `("web", "port"):
      "WEATHERBOT_WEB_PORT"`. `config show` lists both. Any
      committed schema that changes is re-exported.
      `tests/conftest.py`'s isolation fixture adds
      `monkeypatch.setenv("WEATHERBOT_WEB_PORT", "0")` beside the
      toast line.
    </requirement>

    <requirement>
      The app. `src/weatherbot/web/app.py`: `WebState` (a frozen
      dataclass: the database handle `Database | None` from
      `weatherbot.services.persistence.database` — as shipped in PR
      #61 so `weatherbot.web` never imports `sqlalchemy` under the
      database layer contract — the paths, the settings, the clock,
      the start instant, and the built interface's directory, `None`
      when absent; Steps 2 and 3 add the corpus, the event hub, the
      channels, and the fetcher factory) and `create_app(state) ->
      FastAPI` with `title="Weatherbot"`, `version=__version__`,
      `openapi_url="/api/openapi.json"`, `docs_url=None`,
      `redoc_url=None`, no lifespan, the guards, the routers, and
      the built-interface routes registered after them — the same
      routes whether or not a build is present, each with
      `include_in_schema=False`, so `docs/api/openapi.json` never
      depends on the machine. It installs handlers for
      `RequestValidationError` (422) and `ResponseValidationError`
      (500) that answer each error's `loc`, `msg`, and `type` only:
      FastAPI's default 422 echoes `input`, which can hold a
      coordinate. FastAPI's own OpenTelemetry stays unconfigured
      (no exporter; its automatic setup left off). `WebState` also
      holds the setting origins `serve` loaded at start, which Step
      2's `/api/settings` serves. Every route that reads the
      database is a plain `def` (FastAPI runs it in its thread
      pool), never `async def`. No compression middleware: answers
      travel over loopback.
    </requirement>

    <requirement>
      The guards, `src/weatherbot/web/guards.py`, as pure ASGI
      middleware (not `BaseHTTPMiddleware`, whose context and
      ordering limits the Starlette docs list):

      - The order, outermost first: the header middleware (so
        every answer, a refused host's 400 included, carries the
        headers below), then Starlette's
        `TrustedHostMiddleware(allowed_hosts=["127.0.0.1",
        "localhost", "[::1]"])`, so a foreign `Host` answers 400
        before the routes run, then the fetch-metadata and write
        rules below.
      - Writes: `POST`, `PUT`, `PATCH`, and `DELETE` need
        `Content-Type: application/json` (else 415) and, when the
        request carries `Origin`, an origin equal to `http://`
        followed by the request's own `Host`, which the allowlist
        already vetted (else 403); when it carries
        `Sec-Fetch-Site`, the value `same-origin` (else 403). A
        request with neither header (a local script, the CLI) is
        allowed: loopback is the boundary for processes, and a
        browser always sends one of them on a write.
      - Reads: every `/api/` request, `GET` included, whose
        `Sec-Fetch-Site` is present and is neither `same-origin`
        nor `none` answers 403, so a cross-site page can neither
        hold the event stream (and the browser's six connections to
        this host) nor time the API; a navigation to the page
        itself from another site still loads it.
      - No `Access-Control-Allow-*` header on any answer; an
        `OPTIONS` request answers 405 with none.
      - On every answer: `Content-Security-Policy: default-src
        'self'; script-src 'self'; style-src 'self'; img-src
        'self' data: https://tile.openstreetmap.org; connect-src
        'self'; font-src 'self'; object-src 'none'; base-uri
        'none'; form-action 'self'; frame-ancestors 'none'` (an
        `index.html` answer adds its nonce to `style-src`, below),
        `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
        `Referrer-Policy: strict-origin-when-cross-origin` (the tile
        server requires a Referer), `Cross-Origin-Opener-Policy:
        same-origin`, `Cross-Origin-Resource-Policy: same-origin`,
        and `Permissions-Policy: geolocation=(), camera=(),
        microphone=()`; on every `/api/` answer, `Cache-Control:
        no-store`.
    </requirement>

    <requirement>
      `GET /api/health` (`src/weatherbot/web/routes/health.py`),
      its model in `src/weatherbot/web/schemas.py`: `version`;
      `started_at` and `now`; `database` (`revision`, `head`,
      `current` — revision equals head); `scheduler` (the `serve`
      runner row's last success, expected cadence, and staleness);
      `heartbeats` (each row's kind, name, last success, age,
      consecutive failures, and staleness, by
      `services.health.staleness`); `stale` (any row stale);
      `next_product_at` (the next of `PRODUCT_HOURS` after now, in
      UTC); `ui` (`present`, and `index_sha256`, the first 12 hex
      digits of the built `index.html`'s SHA-256, or `null`);
      `corpus` (false until Step 2); and `notice`
      (`services.disclaimer.NOTICE`). It answers 200 whenever the
      server runs.
    </requirement>

    <requirement>
      The built interface, `src/weatherbot/web/static_files.py`.
      `src/weatherbot/web/static/` is git-ignored
      (`.gitignore` gains `/src/weatherbot/web/static/`). When it
      holds `index.html`, the app walks it once at start and keeps
      a map from each file's URL path (`/assets/index-abc.js`,
      `/theme-init.js`) to its bytes or its resolved file, and a
      `GET` is served only when its path is a key of that map: no
      part of a request ever reaches a filesystem call, so a UNC
      name (`%5C%5Chost%5Cshare`), a drive letter, `..`, `NUL`, or
      `::$DATA` — the class behind Starlette's Windows advisory —
      is simply not a key. A file under `assets/` (content-hashed
      names) is served with `Cache-Control: public,
      max-age=31536000, immutable`, any other (`theme-init.js`,
      `licenses.json`, the icon) with `no-cache`; an unknown
      `/assets/` path answers 404; `/` and every other `GET` outside
      `/api/` answer
      `index.html`, read once, with each `__CSP_NONCE__`
      placeholder replaced by a fresh `secrets.token_urlsafe(16)`,
      `Cache-Control: no-store`, and the policy's `style-src
      'self' 'nonce-<that value>'` (FastAPI's `app.frontend()`
      serves `index.html` as a static file, so it cannot carry a
      per-answer nonce); and an unknown `/api/` path answers a JSON
      404 from a catch-all registered after every API route, so
      the history fallback never answers one. When it is absent:
      every non-`/api/` `GET` answers a small built-in HTML page
      (no script) saying the web interface is not built in this
      installation, how to build it (`CONTRIBUTING.md`), and that
      `/api/health` works. Every answer carries the guards'
      headers.
    </requirement>

    <requirement>
      The server, `src/weatherbot/web/server.py`: `WebServer(app,
      host, port, before_stop=())`. `async serve(stop:
      asyncio.Event)` first binds its own socket — to `127.0.0.1`
      when the host is `localhost` (one socket, one port), with
      `SO_EXCLUSIVEADDRUSE` on Windows and never `SO_REUSEADDR`
      there (which would let another process share the port), and
      `SO_REUSEADDR` elsewhere (as uvicorn does, so a restart is not
      refused by connections in `TIME_WAIT`) — retrying a refused
      bind five times, two seconds apart, because a quick task
      restart can meet the old socket's connections; a port still
      taken is an `OSError` it logs once at WARNING ("the web server
      could not start: <error class>") before returning without
      raising, and `bound_port` is known before uvicorn starts. It
      then runs a `uvicorn.Server` subclass
      whose `capture_signals` is a null context, with
      `serve(sockets=[that socket])`, `log_config=None`,
      `access_log=False`, `server_header=False`,
      `proxy_headers=False`, `lifespan="off"`,
      `limit_concurrency=64`, and `timeout_graceful_shutdown=2`,
      and sets `started` (an
      `asyncio.Event`) once listening. On `stop`, on cancellation,
      or on an exception elsewhere in the loop it calls each
      `before_stop` callable (Step 3 passes the event hub's
      `close`, which ends every stream), sets `should_exit`, and
      awaits the task, so the socket closes on every path. It
      catches `SystemExit` from uvicorn (logged like a bind
      failure), so no web-server failure ends the monitor.
    </requirement>

    <requirement>
      `serve`. Inside `run_monitor_loop`, for the `serve` runner
      only, the loop runs `run_monitor(...)` and
      `WebServer.serve(stop)` together; `cli/check.py`'s
      `run_monitor_loop(ctx, runner="check")` call stays exactly as
      it is (Phase 4's check 37), and `check` keeps the monitor
      alone. `cli/serve.py` imports `weatherbot.web` inside the
      `serve` path, not at module level, so the other commands,
      which import `cli/serve.py` through `cli/__init__.py`, never
      load FastAPI. When `run_monitor` returns or raises (Ctrl+C, a
      test's `KeyboardInterrupt`, an error), the server is stopped
      and awaited first, and `clear_runner_heartbeat_cadence` still
      runs. Once the server listens, `serve` logs "dashboard at
      <address>" at INFO — the address built from the bound host
      and port, with `::1` bracketed — and, when it should open a
      browser, calls `Runtime.open_browser(address)`. `serve
      --open/--no-open`: by default it opens only when the process
      started with a terminal (`Runtime.terminal`, or, when that is
      `None`, `sys.__stdout__ is not None and
      sys.__stdout__.isatty()`). Not `sys.stdout`: under
      `pythonw.exe`, `configure_logging` has already replaced it
      with `os.devnull`, which on Windows reports `isatty()` true,
      while `sys.__stdout__` stays `None`; the scheduled task passes
      no flag, so this is what keeps a logon or a fallback restart
      from opening a window. `cli_support.runtime()` gains a
      recording fake for `open_browser`. `Runtime`
      gains `open_browser: Callable[[str], None]`, defaulting to
      `webbrowser.open` called through `asyncio.to_thread` (a
      text-mode `BROWSER` would otherwise block the loop), with
      its errors logged and swallowed. The "already
      running" message adds the dashboard's address from `[web]`.
      `cli/serve.py` keeps `ProcessLock(paths.monitor_lock_path)`
      and `run_monitor(` (Phase 4's check 36).
    </requirement>

    <requirement>
      `doctor`'s `web` check (`services/doctor.py`, a
      `Check("web", …)` in the report's checks, which the `doctor`
      document lists like any other — a check's name is a string,
      so no committed schema changes): it runs with and without
      `--offline`, which skips only the probes of outside sources,
      because this probe stays on loopback. On the default data
      directory (it skips under `WEATHERBOT_DATA_DIR`, like `tasks`
      and `path`), when the `serve` runner row promises a cadence
      (`expected_every_s` is set) and is not stale — a `serve`
      stopped on purpose clears its cadence and is skipped as "serve
      is not running" — it sends `GET http://<host>:<port>/api/health`
      with a 2-second timeout through `httpx` with `trust_env=False`,
      and passes when the answer's `version` and `database.head`
      equal this installation's, with the dashboard's address in its
      detail; it fails when `serve` is running but nothing answers or
      the answer differs. The alarm proofs (a fresh temporary data
      directory) still exit 0.
    </requirement>

    <requirement>
      Logging. uvicorn's loggers reach Weatherbot's handlers, and
      `RedactingFilter` today rewrites only `record.getMessage()`;
      a traceback logged with `exc_info` (uvicorn's "Exception in
      ASGI application" among them) reaches the file unredacted.
      `services/logs.py`'s handlers also redact the formatted
      traceback (`formatException`, and any cached `exc_text`) with
      the same rules, keeping the rotating handler Phase 4's check
      35 reads.
    </requirement>

    <requirement>
      The OpenAPI document. `scripts/export_openapi.py` builds the
      app with a placeholder state, writes
      `docs/api/openapi.json` as UTF-8 bytes with LF line endings
      (two-space indent, `ensure_ascii=False`, trailing newline),
      and `--check` writes nothing and exits 1 when the committed
      file is stale. No response or request model takes a
      `Path`-typed default (Windows renders its separators
      differently).
      `tests/web/test_openapi_export.py` fails while the committed
      document differs from a fresh export, and runs on both
      runners (the export must not depend on the platform).
    </requirement>

    <requirement>
      Phase 4's check 46. `scripts/verify_phase04.py` gains
      `PHASE_4_TAG = "v2.0.0-phase-4"` and a tagged-read helper
      modelled on `verify_phase01.py`'s, and check 46 reads
      `README.md` at that tag (its commands and its Status), so the
      working tree's README may change. In
      `tests/test_phase04_verification.py`, the README case leaves
      the parametrized working-tree mutations and becomes a test
      that edits the tagged text (monkeypatching the tagged read)
      and sees exactly check 46 turn red; every other case stays,
      and the three test names Phase 4's check 48 reads
      (`test_fast_verification_passes_all_static_checks_within_thirty_seconds`,
      `test_phase_verify_workflow_includes_phase_04`, and
      `test_a_changed_deliverable_turns_exactly_its_check_red`)
      keep their names. `verify_phase04.py --fast` still reports 51
      checks (its check 47 counts them), all green.
    </requirement>

    <requirement>
      Tests, offline, under unique basenames, none of which skips
      on Windows or Ubuntu or binds port 8765. No test imports
      `fastapi.testclient` or `starlette.testclient` (the import
      warns, and the suite turns warnings into errors): a finite
      answer is read through `httpx.AsyncClient(transport=
      httpx.ASGITransport(app=app))` inside `asyncio.run`, as the
      suite's other async tests run, and anything that streams or
      needs a socket goes through a real `WebServer` on
      `127.0.0.1:0`. No test asserts a stop faster than a second.
      `tests/web/` is not a package (ruff's `INP001` is ignored
      for tests); if it gains a shared support module, add
      `tests/web` to `[tool.pytest.ini_options] pythonpath` and to
      pyright's `extraPaths`, as `tests/cli` is. Inside
      `recorded_services()`, respx intercepts every httpx request,
      the server's own included (`assert_all_mocked` stays on), so a
      test that reads the local server there either adds
      `router.route(host="127.0.0.1").pass_through()` (a helper in
      `tests/cli/cli_support.py`) or reads it with `urllib`.

      - `tests/web/test_web_app.py`: the app's metadata, `/docs`
        and `/redoc` absent, `/api/openapi.json` served, health's
        fields on a fresh database and after a stored cycle (the
        heartbeats, the staleness, `next_product_at` across a day
        boundary, `ui` absent and present).
      - `tests/web/test_api_guards.py`: every guard — a foreign
        `Host` (a rebinding name) answers 400; a foreign `Origin`
        gets no `Access-Control-Allow-Origin`; `OPTIONS` answers
        405 with no `Access-Control-*` header; a write with a
        foreign `Origin`, with `Sec-Fetch-Site: cross-site`, or
        without JSON is refused; an `/api/` read with
        `Sec-Fetch-Site: cross-site` or `same-site` is refused
        while one with `same-origin`, `none`, or no such header
        passes; a same-origin JSON write passes
        the guard; every header on an HTML answer, a JSON answer,
        and an error; `no-store` on `/api/` only. The guard tests
        use a small throwaway route mounted for the test, never a
        test-only route in the package.
      - `tests/web/test_built_interface.py`: the not-built page;
        a temporary built directory's `index.html` with a fresh
        nonce in each answer (two answers differ, and each answer's
        policy names its own nonce), `no-store`, the history
        fallback, immutable assets, a root file with `no-cache`, an
        unknown `/assets/` path's 404, the requests
        `/%5C%5Chost%5Cshare%5Cx`, `/C:%5Cwindows`, `/..%2F..%2Fx`,
        `/NUL`, and `/index.html::$DATA` answered without any
        filesystem call (the walk at start is the only one), and an
        unknown `/api/` path's JSON 404 even with `Accept:
        text/html`.
      - `tests/web/test_web_server.py`: `WebServer` on
        `127.0.0.1:0` reports its port before uvicorn starts,
        answers `/api/health` over a real socket, calls its
        `before_stop` callables, and closes its socket on stop and
        on cancellation (under `filterwarnings = error`); a taken
        port logs the warning and returns, and a `SystemExit` from
        uvicorn does not escape.
      - `tests/web/test_web_settings.py`: `[web]`'s defaults,
        bounds, loopback validation, and overrides.
      - `tests/cli/test_serve_web.py`: `serve` (port 0) runs its
        startup cycle and answers `/api/health` while the monitor
        runs, then stops cleanly on the test's `KeyboardInterrupt`;
        with the port taken it still runs the startup cycle;
        `--open` calls `Runtime.open_browser` with the dashboard
        address and the default does not, including when
        `sys.stdout` is a stream whose `isatty()` is true while
        `sys.__stdout__` is `None` (the `pythonw.exe` case); the
        "already running" message names the address. The existing
        `tests/cli/test_serve_command.py` passes unchanged.
      - `tests/services/test_doctor_web.py`: `web` skips under
        `WEATHERBOT_DATA_DIR`, without a `serve` row, and for a
        `serve` row whose cadence was cleared; runs under
        `--offline`; passes against a running app; and fails when a
        `serve` row is fresh and nothing answers (the injected
        alarm).
      - `tests/web/test_api_errors.py`: a request whose body fails
        validation (a latitude of 95) answers 422 with `loc`,
        `msg`, and `type` and no `input`, and a logged traceback
        whose exception text holds a coordinate is redacted in the
        log file.
      - `tests/web/test_openapi_export.py` as above, and the
        architecture assertion.
    </requirement>

    <requirement>
      Documents. `README.md`: `## Status` says Phase 5 (the web app
      MVP) is in progress and `serve` now serves a local dashboard
      and API on `http://127.0.0.1:8765/`; `## Commands` shows
      `weatherbot serve` (opens the dashboard; `--no-open`) and
      keeps Phase 3's and Phase 4's lines; `### Running unattended`
      says the task's `serve` serves the dashboard (bookmark the
      address). `CONTRIBUTING.md`: "The web server" (the layering,
      the guards and why, `[web]`, the OpenAPI export, and that no
      test binds 8765). `CHANGELOG.md`: a "Phase 5 — Web app MVP"
      group under `## [Unreleased]` (one such heading stays).
      `AGENTS.md` as above.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with its repo-relative path as a comment, as every
      existing one does.
    </requirement>
  </requirements>
</task>
```

### Step 1 acceptance criteria

- `weatherbot.cli` sits above `weatherbot.web` in the layers contract,
  `lint-imports` passes, and `AGENTS.md` says so; Phase 2's checks 3 and 33 and
  Phase 1's check 13 stay green.
- `serve` hosts the web server beside the monitor: on port 0 it runs the startup
  cycle and answers `/api/health`, it stops cleanly (socket closed) on a clean
  stop, Ctrl+C, and an exception, and with the port taken it logs once and
  monitors on; `check` hosts no server.
- Every guard has its test: a foreign `Host` is refused, no answer grants a
  cross-origin read, a cross-site or non-JSON write is refused, every answer
  carries the security headers, and every `/api/` answer is `no-store`; `/docs`
  and `/redoc` are absent.
- `/api/health` reports the version, the database revision and head, the
  scheduler, every heartbeat's staleness, the next product time, the built
  interface's identity, and `notice`; the not-built page and the built
  interface's history fallback both serve, and only files mapped at start are
  ever served (UNC, drive-letter, traversal, and device-name requests reach no
  filesystem call).
- A validation error answers without echoing its input, a logged traceback is
  redacted like a message, and a start with `sys.__stdout__` absent (the
  `pythonw.exe` case) opens no browser.
- `docs/api/openapi.json` equals a fresh export on both runners; `doctor`'s
  `web` check skips, passes, and fails as specified, and the alarm proofs still
  exit 0.
- Phase 4's check 46 reads `v2.0.0-phase-4:README.md`, its mutation test edits
  the tagged text, and `verify_phase04.py --fast` passes 51 of 51; no test binds
  port 8765 or opens a browser.
- **Deployed & verified:** with the operator's yes, away from HH:25,
  `\Weatherbot\serve` was stopped, the installed copy reinstalled from `main`,
  and the task started again; `GET http://127.0.0.1:8765/api/health` answers
  from it with this build's version and the operator's database at its head; the
  installed copy's `doctor --offline --json` passes its `web` check; and the
  first `ci.yml` and `phase-verify.yml` runs on `main` are green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, SAST
  clean, and the dependency audit clean with `fastapi`, `starlette`, and
  `uvicorn` added — and the server binds loopback only, its guards are tested,
  and no log line above DEBUG holds a request's path or query.

---

## Step 2 — The read API and the map's geometry ✅

**Status:** Complete — PR #62 (2026-10-27)

> **Goal:** Serve everything the pages read, in the web layer's own models.
> `weatherbot.web.schemas` gains the response models and `weatherbot.web.routes`
> the read routes — `GET /api/locations`, `/api/assessments` (each location's
> latest assessment: level, label, deciding rule, evidence, actions, missing
> inputs, official products, wind readings, storm threats, changes, and the
> evacuation toggle), `/api/storms`, `/api/alerts`,
> `/api/timeline?location=&limit=` (assessments with their changes, and
> notifications, newest first), `/api/notifications?limit=`, `/api/settings`
> (every effective setting with its origin), `/api/disclaimer`, and `/api/map`
> (the latest snapshot's cones, forecast tracks and points, watch-warning
> segments, and outlook areas, with the locations, as GeoJSON whose geometry
> carries its CRS, built once per snapshot id and kept in memory); a replay
> corpus — from the new `[web] corpus` setting, which the scheduled `serve`
> reads at start, or from `serve --corpus DIR` for one run — opens `/api/replay`
> and `/api/replay/{atcf_id}/{advisory}`, through new public
> `ReplayCorpus.advisories` and `ReplayCorpus.snapshot` accessors; and
> `docs/api/openapi.json` grows to the whole read contract, with a parity test
> holding the API and `status --json` to the same level, rule, and evidence and
> a privacy test holding coordinates to the locations shape and the map shape's
> location layer. This step lands the content; Step 3 tells the page when it
> changed.

**Branch:** `feature/phase05-step2-read-api`

**Deploys:** nothing beyond merge — the operator's copy keeps Step 1's build
until Step 7 redeploys it. GitHub Actions → the first `ci.yml` and
`phase-verify.yml` runs on `main` must be green.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.18/1M           | $4.00/1M*          | $8.46/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.56/1M           | $6.02/1M           | $4.00/1M*          |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | XHigh              | XHigh              |
|               | AA       | not measured       | 51                 | 52.4               |
|               | Price    | $2.40/1M*          | $4.00/1M           | $16.36/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out) ×
the tokens the model uses at that level; * token use not yet measured, a typical
model's at that level assumed.

**Conversation:** New

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that
column's usage pool reads `tight` or `exhausted`, run the first of its Runner-up
and Backup whose pool has headroom; on a `tight` pool an option marked ↓ (the
Pick one level lower) also runs. With none, a `tight` column runs the Cost
column and an `exhausted` one its Backup.

> Settings updated 2026-10-25 (rerank): each column's Runner-up and Backup now come from makers other than its Pick; every Pick is unchanged.
>
> Ran 2026-10-27: Balanced Pick — Gemini 4 Argon · Effort High · Thinking On on Antigravity. Selected by the **Runs:** rule (Google AI Pro pool reads headroom).

**Model rationale:** Step 2 is coding with a knowledge secondary category: ten
read routes over stored domain records, a GeoJSON rendering of NHC's products
that must keep each geometry's CRS, a cache keyed by immutable snapshots, a
replay accessor, and two cross-cutting tests (parity with the CLI, privacy of
coordinates). Its overall complexity is High — many interacting response models,
the privacy rule, CRS and antimeridian handling, and the OpenAPI contract — and
it is not novel: this roadmap fixes every route, its model's content, and where
coordinates may appear. The columns differ in depth and maker: Balanced runs
Gemini 4 Argon on Antigravity at Effort High with thinking on; Quality runs Opus
5.5 on Claude Code at Effort XHigh (always thinking, so no Thinking field) for
the closest audit of the models against the domain records; Cost moves it to
GPT-6.1 Sol on Codex at Intelligence High. Google AI Pro, the claude.ai Max
subscription, and ChatGPT Pro 5x fund the three platforms, so each column costs
nothing at the margin while its pool has headroom; when a column's pool reads
`tight` or `exhausted`, the **Runs:** rule moves the step to that column's
Runner-up or Backup. The conversation is new per phase-boundary hygiene.

```xml
<task>
  <lifecycle>
    This step MUST follow all six
    stages, in order. Stages 1, 3,
    4, 5, 6 are AS BINDING as any
    `<requirement>` below. Do not
    emit the Stage 6 completion
    line until the PR is merged and
    every acceptance criterion for
    this step is affirmatively met.

    1. CREATE THE BRANCH. Before
       any Read / Edit / Bash, run
       `git checkout -b
       feature/phase05-step2-read-api`
       from a clean, up-to-date
       `main`. The exact branch
       name is in this step's
       `**Branch:**` line above.
       If the Worktree rule
       applies, use `git fetch
       origin && git worktree add
       -b <branch> <path>
       origin/main` instead, then
       bootstrap the worktree.

    2. WORK ON THE BRANCH. All
       commits land here. `main`
       is protected with
       `enforce_admins: true` —
       direct pushes will be
       rejected.

    3. OPEN THE PR, THEN MARK THE
       STEP. `gh pr create --base
       main --head <branch>` with a
       Conventional Commits title
       and a body that references
       this roadmap step and its
       acceptance criteria. One PR
       per step. Then, in this
       roadmap file: set this
       step's `**Status:**` line
       (directly under its heading)
       to `Complete — PR #<n>
       (<YYYY-MM-DD>)`, append ` ✅`
       to the step's `## Step`
       heading, and set its
       Summary Table Status cell to
       `Complete — PR #<n>`. Commit
       that edit on the step
       branch and push — the PR
       carries its own completion
       mark, so the roadmap on
       `main` marks this step
       complete exactly when the PR
       merges (Status rule). Same
       commit: on the phase's first
       step, set this roadmap's
       phase-level `**Status:**`
       (under its title) and the
       parent project roadmap's
       Phase 5 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 5`
       heading.

    4. WAIT FOR GREEN CHECKS, THEN
       SQUASH-MERGE. Every required
       check must pass. If the PR
       falls behind main, refresh
       with `gh pr update-branch
       --rebase` — never merge main
       into the branch
       (`required_linear_history:
       true`). Once green:
       `gh pr merge <PR> --squash
       --delete-branch`. If this
       step's `**Deploys:**` line
       names a surface, the merge
       is not the finish line: run
       the Deployed & verified
       check against the target
       environment before
       declaring the step complete.

    5. RETIRE THE BRANCH. Sync
       local: `git switch main &&
       git pull --ff-only origin
       main && git fetch --prune
       origin`. Prune any local
       `[gone]` branches. If the
       step ran in a worktree,
       `git worktree remove <path>`
       FIRST — the branch prune
       fails while the branch is
       checked out there.

    6. DISPOSE OF EVERY FINDING,
       DECLARE COMPLETION, THEN
       NEW CONVERSATION. First
       send every finding this
       step surfaced to its
       destination (Triage rule):
       a note for a later step →
       edit that step's <task>
       block now; spec rot → edit
       this roadmap now; a bug →
       fixed in-step or an issue
       number; a judgement call in
       the diff → the PR body; a
       process lesson → written
       where the next conversation
       reads it. A finding you can
       only describe is NOT
       disposed of, and counts as
       an unmet criterion. Only
       once the PR is merged — and
       `main` therefore carries
       this step's `Complete`
       Status line — every
       acceptance criterion is
       affirmatively met, and every
       finding has a destination,
       say so plainly: end your
       final response with an
       explicit, unhedged
       completion line — verbatim
       shape "Step 2 is
       complete. You can now move
       on to Step 3." That
       line is the LAST line of
       the response. NOTHING
       follows it — no "Follow-ups
       (non-blocking)", "Notes",
       "Next", "worth a glance",
       or suggested improvements.
       A short ledger may PRECEDE
       it, one entry per finding
       naming its destination
       (issue #, file edited, PR
       body) — never an open item.
       If any criterion is unmet
       or any finding has no
       destination, state plainly
       that the step is NOT
       complete, name what is
       outstanding, and omit the
       completion line. "Done"
       means done. Then, for
       phase-boundary hygiene, the
       operator closes this
       session and opens a fresh
       one before Step 3.
  </lifecycle>

  <security>
    Security is a gate on THIS
    step, not a later phase. It is
    AS BINDING as any
    `<requirement>` below. Before
    the Stage-2 commit, this
    step's work MUST pass the
    local, fail-closed security
    gate — the SAME gate wired
    into the pre-commit hook and
    re-run in CI:

    1. SECRET / PII SCAN. No
       credentials, API keys,
       tokens, or real PII in the
       diff (gitleaks /
       detect-secrets or the
       project's equivalent).
       Secrets go in the secrets
       manager, never in source or
       committed env files.

    2. SAST. No new injection,
       unsafe deserialization,
       weak crypto, path
       traversal, or unsafe-eval
       pattern (bandit / semgrep /
       eslint-plugin-security per
       the stack). Suppress a
       finding ONLY with an inline
       justification comment.

    3. DEPENDENCY AUDIT. Any new
       or bumped dependency passes
       the audit (pip-audit / npm
       audit / osv-scanner); no
       known-vulnerable, yanked,
       or typo-squatted package.

    4. SENSITIVE-DATA REVIEW.
       Whatever this step touches
       stays least-privilege,
       encrypted in transit + at
       rest, and out of logs and
       client bundles. If the step
       adds a data path, name how
       PII/secrets are protected.

    A finding blocks the commit —
    fix it in this step, do not
    defer. Do not declare the step
    complete until the gate is
    clean. This is the safety net
    that stops a security issue
    from reaching the branch, the
    PR, or `main`.

    THIS STEP serves the operator's locations to the browser. A
    location's latitude and longitude (and its zone polygon)
    appear only in the locations shape (`/api/locations`, and Step
    3's write answers) and in the map shape's location layer
    (`/api/map`, `/api/replay/{atcf_id}/{advisory}`), and in no
    other answer; `/api/assessments` carries the exact
    distances and bearings the CLI's documents round, because the
    page is the operator's own screen, and no log line above DEBUG
    holds any of them. Every answer keeps Step 1's guards and its
    `Cache-Control: no-store`. A location's name travels in a
    query string or a JSON body, never a path segment (a name may
    hold a slash), and every name a route reads is looked up in
    the database, never used to build a path or a query string.
    `/api/settings` shows setting values and the configuration
    file's path, which hold no secret (a setting is never a
    secret, a location, or a coordinate). The replay routes read
    only inside the corpus directory `serve` was given, through
    `ReplayCorpus`'s existing path and checksum rules, and answer
    404 when no corpus is open. No dependency is added.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 5 (Web app MVP). Step 2:
    the read API and the map's geometry.

    Current state (as of Phase 5 Step 1):

    - Step 1's `create_app(state: WebState)` mounts the guards,
      `GET /api/health`, and the built-interface routes;
      `WebState` holds `database: Database | None` (from
      `weatherbot.services.persistence.database`, passing
      `state.database.engine` to repository and service
      constructors so `weatherbot.web` never imports `sqlalchemy`,
      PR #61), the paths, the settings, `setting_origins`, the
      clock, the start instant, and the interface directory; every
      route that reads the database is a plain function (thread
      pool), never `async def`. `scripts/export_openapi.py` writes
      `docs/api/openapi.json`, and `tests/web/test_openapi_export.py`
      fails while it is stale. Read Step 1's PR body (#61) for
      anything it changed from this roadmap.
    - The read paths exist (Current State, "Services surface"):
      `LocationRepository.list/get`, `SnapshotRepository.latest()/
      load(id)/drift_warnings(id)`, `AssessmentRepository.latest/
      history/load` with `StoredAssessment(id, assessment, changes,
      stored_at)`, `NotificationService.recent(limit)`,
      `setting_origins(paths, environ)`, and
      `services.disclaimer.NOTICE`, `ESSENTIALS`, `full_text()`.
      `AlertLevel` has `label` and `actions`; the engine's
      `Assessment` holds the evidence, the official products, the
      wind readings, the threats, and the unavailable inputs;
      `cli/status.py` shows how each becomes a document entry, and
      `cli/snapshots.py` how a snapshot becomes the storms and
      alerts documents — read them for the meaning, not to import
      them (the web layer may not import the CLI).
    - Measured on 2026-10-24 (Current State): the latest snapshot
      loads in a median 384 ms because it decodes everything (1.8
      MiB as JSON); the map's layers are 49 KiB of it; an
      assessment loads in about 1 ms. Replay: `ReplayCorpus`
      yields a storm's snapshots in order (`snapshots(atcf_id)`, 39
      ms each, 3.3 s for Irma's 84), through the private
      `_snapshot(atcf_id, advisory, so_far)`; replay geometry is
      `Crs(name="native", wkt=..., datum=...)`, live geometry
      `EPSG:4326`.
    - Phase 2's check 28 forbids any string literal holding
      `/points/` or `point=` in the package (`endpoint=` and
      `breakpoint=` included), so no route, model description, or
      docstring writes either.

    Files to read (every file before drafting):
    - docs/roadmap/phase05-roadmap.md (Overview and its design
      rationale, Current State, Step 1, this step, and Steps 3, 5,
      and 6, which consume these routes).
    - src/weatherbot/web/ (all of Step 1), scripts/export_openapi.py,
      tests/web/.
    - src/weatherbot/models/ (assessment.py, ladder.py, storms.py,
      outlook.py, alerts.py, geometry.py, location.py, snapshot.py,
      products.py).
    - src/weatherbot/services/persistence/repositories.py,
      services/notifications.py, services/replay.py,
      services/config.py, services/disclaimer.py,
      services/health.py, services/schedule.py (`PRODUCT_HOURS`).
    - src/weatherbot/cli/status.py, cli/snapshots.py,
      cli/documents.py, cli/notify.py, cli/replay.py,
      cli/serve.py, cli/runtime.py.
    - tests/cli/cli_support.py (`recorded_services()`,
      `add_landmark()`, `run()`), scripts/public_landmarks.toml.
  </context>

  <goal>
    Ship the read routes, their response models, the map layers
    with their cache, the replay routes behind `serve --corpus
    DIR`, the public replay accessors, the regenerated OpenAPI
    document, and the parity and privacy tests.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `src/weatherbot/web/schemas.py`: one Pydantic model per
      answer, frozen, `extra="forbid"`, with field descriptions
      that become the OpenAPI document's (integer bounds and
      defaults only where a bound is needed; no description says
      `endpoint=`). Instants are UTC ISO-8601; each location entry
      carries its NWS time zone (or none), so the page can show
      both, as `status` does. Levels carry their number, label, and
      actions; a missing input names its kind and source, never a
      coordinate. The models are the page's contract: no route
      returns a domain model directly.
    </requirement>

    <requirement>
      The routes, each a plain function in its own module under
      `src/weatherbot/web/routes/`, registered by `create_app`:

      - `GET /api/locations` — every location: name, display name,
        country code, latitude, longitude, NWS coverage (office,
        forecast and county zones, time zone) or none, breakpoint
        span, the evacuation toggle and when it was set, and the
        zone polygon when one is stored.
      - `GET /api/assessments` — per location, its latest stored
        assessment (none before the first): id, stored and
        assessed instants, snapshot id and age, level (number,
        label, actions), deciding rule, evidence, complete or "at
        least" with the missing inputs, the official products that
        cover it and the county-zone context alerts outside its
        zones (labelled as context that never sets the level, issue
        #10), the wind-speed probabilities there, each storm's
        threat (in cone, distance, bearing, closest approach,
        arrival readings with their source), the changes since the
        previous assessment, and the toggle-changed note (the
        location's `evacuation_order_set_at` is later than the
        assessment's `stored_at` — the rule `AssessmentService`
        applies).
      - `GET /api/storms` — the latest snapshot's id, instants,
        status, and source outcomes, its drift warnings, every
        storm (ATCF id, name, classification, intensity, movement,
        pressure, advisory number and issuance, the products it
        carries), and the outlook areas (basin, two- and seven-day
        chances).
      - `GET /api/alerts` — per location, the NWS alerts (id,
        event, headline, severity, certainty, urgency, effective,
        expires, codes, and whether it covers the location or is
        context) and the NHC watch-warning segments that cover it.
      - `GET /api/timeline?location=&limit=` — newest first, at
        most `limit` (default 50, at most 500) entries of two kinds:
        an assessment (level, rule, complete, and its changes) and
        a notification (kind, title, level, escalation, created
        instant, and its deliveries); without `location`, every
        location's.
      - `GET /api/notifications?limit=` — `notify log`'s content
        (default 20, at most 500): each notification with its
        decisions and deliveries.
      - `GET /api/settings` — the configuration file's path,
        whether it exists, every setting's table, key, value,
        origin, and variable as `serve` loaded them at start (the
        origins `WebState` holds, never a fresh read of the file,
        which could show values the running process is not using
        or fail), and whether the file has changed since then (its
        modification time), so the page can say "restart `serve`
        to apply".
      - `GET /api/disclaimer` — `NOTICE`, `ESSENTIALS`, and the
        packaged full text.
      - `GET /api/map` — described below.

      An unknown location in a query answers 404 naming the
      parameter, not echoing the value; with no stored snapshot,
      the snapshot-backed routes answer with empty collections and
      a `snapshot` of `null`, never an error.
    </requirement>

    <requirement>
      The map layers, in `src/weatherbot/web/map_layers.py` (pure:
      domain models in, response models out) and served by `GET
      /api/map`:

      - Per storm: its cone (Feature), forecast track (Feature),
        forecast points (FeatureCollection, each point with its
        forecast instant, intensity, and classification), and
        watch-warning segments (FeatureCollection, each with its
        type and breakpoint names); the snapshot's outlook areas
        (FeatureCollection, each with its basin and chances); and
        the locations (FeatureCollection of points, and polygons
        where stored). Wind radii, wind-speed probabilities,
        breakpoints, and surge are not served (Phase 7).
      - Every geometry is RFC 7946 GeoJSON with a `crs` member
        beside its `type` and `coordinates` carrying the domain
        `Crs` (name, datum; the WKT stays out of the answer), and
        coordinates are never transformed, rounded, or relabelled.
        A storm whose geometry crosses the antimeridian is unwrapped
        against one reference longitude for the whole storm (its
        first forecast point's), shifting longitudes by 360 so the
        cone, the track, the points, and the segments draw together
        as one shape; a test builds a Central Pacific storm that
        crosses 180 degrees from literals with at most two decimals.
      - The answer names the snapshot id and instant it was built
        from. It is built once per snapshot id and kept in memory
        (the latest few ids, at most 8), because a stored snapshot
        never changes: a request reads the newest id through
        `SnapshotRepository.latest_id()` and decodes the snapshot
        only on a miss. `/api/storms` and `/api/alerts` share that
        cache (each answer built once per snapshot id), so the
        384 ms decode happens once per new snapshot, not per
        request. A test proves a second request for the same
        snapshot does not load it again, and one after a newer
        snapshot does.
    </requirement>

    <requirement>
      Replay. `ReplayCorpus` gains `advisories(atcf_id) ->
      tuple[str, ...]` (the manifest's order) and
      `snapshot(atcf_id, advisory) -> Snapshot` (the same snapshot
      `snapshots` yields for that advisory, read on its own with
      the advisories before it as `so_far`); a test proves the two
      agree for every Irma advisory in the committed subset.
      The corpus comes from `[web] corpus` (a directory; empty, the
      default, means none; the literal override
      `WEATHERBOT_WEB_CORPUS`), which `serve` opens at start — a
      directory that will not open is logged at WARNING and leaves
      replay off while the monitor runs, because the scheduled
      `serve` must never stop for it — or, for one run, from `serve
      --corpus DIR`, which overrides the setting and exits 2 on a
      directory that is not a corpus, as `replay` does, before
      taking the monitor's lock. The opened corpus goes into
      `WebState`. On the operator's machine the setting is the
      way: the scheduled `serve` holds the monitor's lock, so a
      second `serve` exits 2. `GET /api/replay` lists its storms and
      advisories (ids, names, issuance instants), and `GET
      /api/replay/{atcf_id}/{advisory}` answers that advisory's
      layers in `/api/map`'s shape, with the stored locations as
      its location layer; no assessment is computed or stored.
      Both answer 404 when no corpus is open, and an
      unknown storm or advisory answers 404. `/api/health`'s
      `corpus` field turns true. The ids are validated against the
      manifest before any read, so neither reaches a path.
    </requirement>

    <requirement>
      `docs/api/openapi.json` is regenerated with every route and
      model, and `tests/web/test_openapi_export.py` still passes on
      both runners. `README.md`'s Commands line for `serve` names
      `--corpus DIR`; `CONTRIBUTING.md` lists the routes and the
      rule of where coordinates may appear; `CHANGELOG.md` gains
      this step's entries.
    </requirement>

    <requirement>
      Tests, offline, under unique basenames in `tests/web/`
      (none of them skips on Windows or Ubuntu), each building the
      database through `recorded_services()` and the public
      landmarks in the test's temporary data directory:

      - `test_api_reads.py`: every route answers 200 and validates
        against its model and the committed OpenAPI document's
        schema for that route; the empty-database answers; an
        unknown location answers 404 without echoing it; the
        limits' bounds.
      - `test_api_cli_parity.py`: for the same stored assessment,
        `/api/assessments` and `status --json --no-fetch` agree on
        the level, the deciding rule, the evidence's products and
        codes, the official products' codes, and the missing
        inputs.
      - `test_api_privacy.py`, mirroring
        `tests/cli/test_cli_privacy.py`: a location stored at
        `synthetic_coordinates()` (generated at run time, never a
        literal, answered by the Miami-Dade landmark's recorded
        NWS and Nominatim captures) and the committed corpus open;
        every read answer, the replay answer included, with the
        locations-shaped objects and the map shape's location layer
        removed, holds none of the renderings that test checks; and
        the log records captured at INFO while every route answers
        hold none of them and no standalone decimal of three or
        more places.
      - `test_map_layers.py`: the recorded snapshot's layers
        (counts, properties, `crs` names), the unwrapped Central
        Pacific cone, the cache's reuse and refresh, and no wind
        radii or probabilities in the answer.
      - `test_replay_routes.py`: with the committed subset as the
        corpus, Irma's advisories list, one advisory's layers carry
        the `native` CRS, unknown ids answer 404, the routes answer
        404 without a corpus, `ReplayCorpus.snapshot` equals the
        streamed snapshot for every Irma advisory, and a non-corpus
        directory makes `serve --corpus` exit 2.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, TOML, and JSON
      Schema file starts with its repo-relative path as a comment
      where the format allows, as every existing one does.
    </requirement>
  </requirements>
</task>
```

### Step 2 acceptance criteria

- Every read route answers in its committed OpenAPI schema on both runners, and
  `docs/api/openapi.json` equals a fresh export.
- `/api/assessments` and `status --json --no-fetch` agree on the level, rule,
  evidence, official products, and missing inputs of the same stored assessment.
- Outside the locations shape and the map shape's location layer, no answer (the
  replay answer included) holds a stored location's coordinates in any rendering
  the CLI's privacy test checks, and no INFO log record holds a coordinate, a
  distance, or a bearing.
- `/api/map` serves the cones, tracks, points, segments, outlook areas, and
  locations with each geometry's CRS, unwraps an antimeridian crossing, builds
  once per snapshot id, and serves no wind radii or probabilities.
- With the committed corpus open — through `[web] corpus` or `serve --corpus
  tests/fixtures/replay` — the server serves Irma's advisories and one
  advisory's layers in the `native` CRS; a corpus that will not open leaves
  `serve` running with replay off; without a corpus the replay routes answer
  404; `ReplayCorpus.snapshot` equals the streamed snapshot.
- **Deployed & verified:** the first `ci.yml` and `phase-verify.yml` runs on
  `main` after the merge are green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, SAST
  clean, dependency audit clean with no dependency added — and coordinates
  appear only in the two routes that need them, names never reach a path, and
  the replay routes read only inside the corpus.

---

## Step 3 — The event stream, browser notifications, and the API's actions ✅

**Status:** Complete — PR #63 (2026-10-27)

> **Goal:** Tell an open page what changed, and let it act. A new
> `weatherbot.services.events` holds `EventHub` (publish from any thread; one
> bounded queue per subscriber), its cycle listener (a cycle's snapshot,
> assessments, alert changes, and its own completion become events naming the
> queries to refetch), `CycleWatcher` (cycles, notifications, and assessments
> that another process stored, found every 10 seconds), the staleness timer (a
> `health` event at the instant a heartbeat turns stale), and `BrowserChannel`
> (Phase 4's `Channel`, delivering a notification to the open pages, with an
> honest result and a `[notifications] browser` switch); `GET /api/events`
> streams them through FastAPI's `EventSourceResponse`, starting each connection
> with `hello`; `serve` wires the hub into `run_monitor` and adds the browser
> channel to its channels; and four guarded writes join the API — `POST
> /api/locations` (first-run setup through `LocationService.add`), `PUT
> /api/locations/evacuation`, `POST /api/cycles` (check now, trigger `manual`),
> and `POST /api/notifications/test` (kind `test` through `serve`'s channels).
> This step lands the live link; Step 4 builds the page that follows it.

**Branch:** `feature/phase05-step3-event-stream`

**Deploys:** nothing beyond merge — the operator's copy keeps Step 1's build
until Step 7 redeploys it. GitHub Actions → the first `ci.yml` and
`phase-verify.yml` runs on `main` must be green.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.18/1M           | $4.00/1M*          | $8.46/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.56/1M           | $6.02/1M           | $4.00/1M*          |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | XHigh              | XHigh              |
|               | AA       | not measured       | 51                 | 52.4               |
|               | Price    | $2.40/1M*          | $4.00/1M           | $16.36/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out) ×
the tokens the model uses at that level; * token use not yet measured, a typical
model's at that level assumed.

**Conversation:** New

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that
column's usage pool reads `tight` or `exhausted`, run the first of its Runner-up
and Backup whose pool has headroom; on a `tight` pool an option marked ↓ (the
Pick one level lower) also runs. With none, a `tight` column runs the Cost
column and an `exhausted` one its Backup.

> Settings updated 2026-10-25 (rerank): each column's Runner-up and Backup now come from makers other than its Pick; every Pick is unchanged.
>
> Ran 2026-10-27: Balanced Pick — Gemini 4 Argon · Effort High · Thinking On on Antigravity. Selected by the **Runs:** rule (Google AI Pro pool reads headroom).

**Model rationale:** Step 3 is coding with an agentic secondary category: a
publish-subscribe hub that receives from the event loop and from worker threads,
a server-sent event route, a polling watcher with high-water marks, a timer
derived from the heartbeats, a new delivery channel, and four writes that call
the network and the monitor, with a live run. Its overall complexity is High —
concurrency, back-pressure, exactly-once publication across two event sources,
cross-site refusal on every write — and it is not novel: this roadmap fixes the
events, their payloads, the watcher's marks, and the channel's results. The
columns differ in depth and maker: Balanced runs Gemini 4 Argon on Antigravity
at Effort High with thinking on; Quality runs Opus 5.5 on Claude Code at Effort
XHigh (always thinking, so no Thinking field) for the closest audit of the hub's
concurrency; Cost moves it to GPT-6.1 Sol on Codex at Intelligence High. Google
AI Pro, the claude.ai Max subscription, and ChatGPT Pro 5x fund the three
platforms, so each column costs nothing at the margin while its pool has
headroom; when a column's pool reads `tight` or `exhausted`, the **Runs:** rule
moves the step to that column's Runner-up or Backup. The conversation is new per
phase-boundary hygiene.

```xml
<task>
  <lifecycle>
    This step MUST follow all six
    stages, in order. Stages 1, 3,
    4, 5, 6 are AS BINDING as any
    `<requirement>` below. Do not
    emit the Stage 6 completion
    line until the PR is merged and
    every acceptance criterion for
    this step is affirmatively met.

    1. CREATE THE BRANCH. Before
       any Read / Edit / Bash, run
       `git checkout -b
       feature/phase05-step3-event-stream`
       from a clean, up-to-date
       `main`. The exact branch
       name is in this step's
       `**Branch:**` line above.
       If the Worktree rule
       applies, use `git fetch
       origin && git worktree add
       -b <branch> <path>
       origin/main` instead, then
       bootstrap the worktree.

    2. WORK ON THE BRANCH. All
       commits land here. `main`
       is protected with
       `enforce_admins: true` —
       direct pushes will be
       rejected.

    3. OPEN THE PR, THEN MARK THE
       STEP. `gh pr create --base
       main --head <branch>` with a
       Conventional Commits title
       and a body that references
       this roadmap step and its
       acceptance criteria. One PR
       per step. Then, in this
       roadmap file: set this
       step's `**Status:**` line
       (directly under its heading)
       to `Complete — PR #<n>
       (<YYYY-MM-DD>)`, append ` ✅`
       to the step's `## Step`
       heading, and set its
       Summary Table Status cell to
       `Complete — PR #<n>`. Commit
       that edit on the step
       branch and push — the PR
       carries its own completion
       mark, so the roadmap on
       `main` marks this step
       complete exactly when the PR
       merges (Status rule). Same
       commit: on the phase's first
       step, set this roadmap's
       phase-level `**Status:**`
       (under its title) and the
       parent project roadmap's
       Phase 5 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 5`
       heading.

    4. WAIT FOR GREEN CHECKS, THEN
       SQUASH-MERGE. Every required
       check must pass. If the PR
       falls behind main, refresh
       with `gh pr update-branch
       --rebase` — never merge main
       into the branch
       (`required_linear_history:
       true`). Once green:
       `gh pr merge <PR> --squash
       --delete-branch`. If this
       step's `**Deploys:**` line
       names a surface, the merge
       is not the finish line: run
       the Deployed & verified
       check against the target
       environment before
       declaring the step complete.

    5. RETIRE THE BRANCH. Sync
       local: `git switch main &&
       git pull --ff-only origin
       main && git fetch --prune
       origin`. Prune any local
       `[gone]` branches. If the
       step ran in a worktree,
       `git worktree remove <path>`
       FIRST — the branch prune
       fails while the branch is
       checked out there.

    6. DISPOSE OF EVERY FINDING,
       DECLARE COMPLETION, THEN
       NEW CONVERSATION. First
       send every finding this
       step surfaced to its
       destination (Triage rule):
       a note for a later step →
       edit that step's <task>
       block now; spec rot → edit
       this roadmap now; a bug →
       fixed in-step or an issue
       number; a judgement call in
       the diff → the PR body; a
       process lesson → written
       where the next conversation
       reads it. A finding you can
       only describe is NOT
       disposed of, and counts as
       an unmet criterion. Only
       once the PR is merged — and
       `main` therefore carries
       this step's `Complete`
       Status line — every
       acceptance criterion is
       affirmatively met, and every
       finding has a destination,
       say so plainly: end your
       final response with an
       explicit, unhedged
       completion line — verbatim
       shape "Step 3 is
       complete. You can now move
       on to Step 4." That
       line is the LAST line of
       the response. NOTHING
       follows it — no "Follow-ups
       (non-blocking)", "Notes",
       "Next", "worth a glance",
       or suggested improvements.
       A short ledger may PRECEDE
       it, one entry per finding
       naming its destination
       (issue #, file edited, PR
       body) — never an open item.
       If any criterion is unmet
       or any finding has no
       destination, state plainly
       that the step is NOT
       complete, name what is
       outstanding, and omit the
       completion line. "Done"
       means done. Then, for
       phase-boundary hygiene, the
       operator closes this
       session and opens a fresh
       one before Step 4.
  </lifecycle>

  <security>
    Security is a gate on THIS
    step, not a later phase. It is
    AS BINDING as any
    `<requirement>` below. Before
    the Stage-2 commit, this
    step's work MUST pass the
    local, fail-closed security
    gate — the SAME gate wired
    into the pre-commit hook and
    re-run in CI:

    1. SECRET / PII SCAN. No
       credentials, API keys,
       tokens, or real PII in the
       diff (gitleaks /
       detect-secrets or the
       project's equivalent).
       Secrets go in the secrets
       manager, never in source or
       committed env files.

    2. SAST. No new injection,
       unsafe deserialization,
       weak crypto, path
       traversal, or unsafe-eval
       pattern (bandit / semgrep /
       eslint-plugin-security per
       the stack). Suppress a
       finding ONLY with an inline
       justification comment.

    3. DEPENDENCY AUDIT. Any new
       or bumped dependency passes
       the audit (pip-audit / npm
       audit / osv-scanner); no
       known-vulnerable, yanked,
       or typo-squatted package.

    4. SENSITIVE-DATA REVIEW.
       Whatever this step touches
       stays least-privilege,
       encrypted in transit + at
       rest, and out of logs and
       client bundles. If the step
       adds a data path, name how
       PII/secrets are protected.

    A finding blocks the commit —
    fix it in this step, do not
    defer. Do not declare the step
    complete until the gate is
    clean. This is the safety net
    that stops a security issue
    from reaching the branch, the
    PR, or `main`.

    THIS STEP adds the API's writes and a stream an open page
    holds for hours. Every write inherits Step 1's guards (JSON
    only; a foreign `Origin` or a cross-site `Sec-Fetch-Site`
    refused), and a test proves the refusal on each of the four.
    Request bodies are Pydantic models with `extra="forbid"`; a
    location's name and point are validated before any request,
    by `LocationService`'s own checks, and the point leaves the
    machine only in the NWS and Nominatim requests `locations add`
    already sends. No event carries a coordinate, a distance, or
    a bearing: events name ids, location names, levels, kinds, and
    query keys, and a browser notification's title and body are
    Phase 4's, which name and never locate. Error answers name
    the problem (a taken name, an unknown location, a source that
    did not answer), never a coordinate. `POST /api/cycles` and
    `POST /api/notifications/test` are rate-limited (one cycle in
    flight and one a minute; one test every 10 seconds), so a page
    cannot hammer NOAA or the toast. Each subscriber's queue is
    bounded, and one that falls behind is closed, so a stuck tab
    cannot grow the server's memory. No dependency is added:
    `fastapi.sse` ships with FastAPI.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 5 (Web app MVP). Step 3:
    the event stream, browser notifications, and the API's
    actions.

    Current state (as of Phase 5 Step 2):

    - Steps 1 and 2 serve the guarded read API from `serve`'s
      loop: `create_app(WebState)`, `WebServer`, the read routes
      in `src/weatherbot/web/routes/`, the response models in
      `web/schemas.py`, and `docs/api/openapi.json`. Every route
      that reads the database is a plain function in FastAPI's
      thread pool. Read both PR bodies for anything they changed
      from this roadmap.
    - `MonitorService(..., listeners=)` calls each listener
      synchronously, on the event loop's thread, with the
      `CycleResult` (cycle id, trigger, runner, status, snapshot,
      `assessed` with `created` and the stored assessment's
      changes, `notifications`); `run_monitor(..., listeners=,
      channels=)` passes both to every cycle `serve` runs. The
      change kinds are `level_changed`, `advisory_issued`,
      `official_added`, `official_changed`, `official_removed`,
      `cone_entered`, and `cone_left`; Phase 3's check 32 holds
      them at seven.
    - `services/notifications.py`: `Channel` (`name`, `async
      deliver(notification) -> Delivery`), `CHANNEL_NAMES = ("log",
      "toast")` with the `ChannelName` literal, `DELIVERY_RESULTS`,
      `NotificationService.send(kind, title=, body=)`,
      `TEST_TITLE`, and `TEST_BODY`; Phase 4's check 43 holds the
      five notification kinds. `Context.channels` is `(log,
      toast)`; only `serve` will add the browser channel.
    - `LocationService.add(name, lat, lon, polygon=None)` (async;
      raises `LocationError`, whose message never repeats the
      coordinates, for every refusal — a taken name included: it
      checks the name before any request and also turns the
      repository's `LocationExistsError` into `LocationError`) and
      `set_evacuation_order(name, on=)`. `locations evacuation`
      records the toggle and says the next cycle assesses with it;
      the API does the same.
    - `HeartbeatRepository.rows()` gives each row's last success
      and expected cadence; `services.health.staleness` is the
      two-cadence rule. `CycleRepository.recent(limit)` and
      `NotificationService.recent(limit)` read the newest rows;
      `AssessmentRepository.latest(name)` each location's newest.
    - FastAPI 0.162.0's `fastapi.sse` (since 0.135.0; read from
      the wheel and probed on 2026-10-24): a path operation with
      `response_class=EventSourceResponse` that `yield`s
      `ServerSentEvent(data=, event=, id=, retry=, comment=)` (or a
      bare model, sent as JSON `data:`); the routing layer writes
      `: ping` after 15 idle seconds, sets `Cache-Control:
      no-cache`, and cancels the generator when the client leaves.
      Items are validated and documented from the route's return
      annotation (`AsyncIterable[Model]`), not from
      `response_model=`; a `ServerSentEvent` item skips that
      validation (and does not type-check against a model
      annotation), so the route yields the payload models
      themselves.
      FastAPI documents the stream with an OpenAPI 3.2
      `itemSchema` inside its 3.1 document and leaves the payload
      models out of `components.schemas`. An open stream keeps
      uvicorn's default shutdown waiting, which is why Step 1's
      `WebServer` calls its `before_stop` callables (the hub's
      `close`) before `should_exit`. httpx's `ASGITransport`
      buffers a whole response and `fastapi.testclient` warns on
      import, so a stream is read in tests over a real socket:
      `WebServer` on `127.0.0.1:0` and `httpx.AsyncClient.stream`.

    Files to read (every file before drafting):
    - docs/roadmap/phase05-roadmap.md (Overview and its design
      rationale, Steps 1 and 2, this step, and Steps 4 and 5,
      which consume the events).
    - src/weatherbot/web/ (all), cli/serve.py, cli/runtime.py,
      cli/notify.py, cli/locations.py.
    - src/weatherbot/services/monitor.py, schedule.py
      (`run_monitor`), notifications.py, toast.py, locations.py,
      health.py, config.py, persistence/repositories.py.
    - tests/web/ (Steps 1 and 2), tests/cli/cli_support.py,
      tests/services/test_notifications.py,
      tests/live/test_monitor_live.py.
  </context>

  <goal>
    Ship the hub, its cycle listener, the watcher, the staleness
    timer, the browser channel, the event route, the four writes,
    their wiring in `serve`, and their tests, offline and live.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `src/weatherbot/services/events.py`:

      - `HubEvent` (frozen; the API's payload model is
        `StreamEvent` in `web/schemas.py`, so the two names never
        collide): a process-wide increasing `id`, a
        `kind` — `hello`, `cycle`, `snapshot`, `assessment`,
        `alert`, `notification`, `location`, or `health` — the ids
        and names it concerns, and `invalidate`, the query keys a
        page must refetch, drawn from `health`, `locations`,
        `assessments`, `storms`, `alerts`, `map`, `timeline`,
        `notifications`, and `settings`.
      - `EventHub(loop)`: `publish(event_kind, data, invalidate)`
        is safe from the loop's thread and from a worker thread
        (it hands off through `call_soon_threadsafe`);
        `subscribe()` returns an async iterator over a bounded
        queue (100 events) that ends when the queue overflows (the
        page reconnects and refetches) or the hub closes, and
        refuses a seventeenth subscriber (`subscriber_count` at
        most 16; the route answers 503); `close()`. The hub keeps
        the newest cycle id it has seen in memory (read once at
        start, off the loop's thread), so the stream's `hello` reads
        no database. Every "already published?" decision — the
        listener's, the watcher's, the channel's — is made on the
        loop's thread, where publishing lands.
      - `EventHub.cycle_listener(result)`: a `cycle` event (id,
        runner, trigger, status; invalidates `health`); for a
        stored snapshot, `snapshot` (invalidates `storms`, `map`,
        and `alerts`); for each created assessment, `assessment`
        (location, assessment id, level; invalidates
        `assessments` and `timeline`); for each assessment whose
        changes hold an `official_*` change, `alert` (location;
        invalidates `alerts`); and for each notification the cycle
        stored, `notification` without `display` (invalidates
        `notifications` and `timeline`), so the lists refresh even
        when the browser channel is off. It records what it
        published, so the watcher never repeats it.
      - `CycleWatcher(engine, hub, interval_s=10)`: every interval,
        off the loop's thread, it reads four high-water marks — the
        newest completed cycle's id, the newest notification's id,
        each location's newest assessment id, and the locations
        themselves (their names, toggles, and toggle instants,
        which a terminal `locations add`, `remove`, or `evacuation`
        changes) — and publishes `cycle`, `snapshot`, `assessment`,
        `notification` (without a title or body, invalidating
        `notifications` and `timeline`), and `location` events for
        anything newer that this process did not publish. Its first
        read sets the marks and publishes nothing.
      - The staleness timer: at start, after each `cycle` event,
        and after it fires, it reads the heartbeats (off the loop's
        thread) and schedules one `health` event at the earliest
        future instant a row with a cadence would turn stale (its
        last success plus twice its cadence), replacing any earlier
        schedule; with no such instant it schedules nothing.
      - `BrowserChannel(hub, enabled)` implements `Channel` with
        `name == "browser"`: when disabled it returns `disabled`;
        with no subscriber, `unavailable` ("no open dashboard");
        otherwise it publishes a `notification` event carrying the
        notification's id, kind, level, escalation, title, body,
        and `display: true` (invalidating `notifications` and
        `timeline`), and returns `delivered` ("to N open
        dashboards"). `CHANNEL_NAMES` and `ChannelName` gain
        `browser`; no notification kind is added.
      - Quiet hours. `NotificationService`'s `include_toast=False`
        (the hold Phase 4's schedule applies to the `degraded`,
        `recovered`, and `stale_monitor` alarms) today drops only
        the channel named `toast`, so the browser would still
        interrupt. Every channel gains an `interrupts` property
        (`log` false; the toast and the browser true), the hold
        keeps only the channels that do not interrupt, and its
        docstring and the tests say so; the parameter keeps its
        name, so Phase 4's call sites stand.
    </requirement>

    <requirement>
      `[notifications] browser: bool = True` with the literal
      override `WEATHERBOT_NOTIFICATIONS_BROWSER` (`config show`
      lists it; Phase 4's check 14 stays green).
    </requirement>

    <requirement>
      `serve` wiring (`cli/serve.py`, in one loop function that
      takes the runtime's seams, so Step 7's demonstration server
      calls the same code): `run_monitor` gains an `on_schedule`
      callback that hands `serve` its `MonitorSchedule`, and
      `WebState` gets `request_cycle`, a single-flight call of
      `schedule.execute_cycle("manual")`, so a check-now cycle
      records its `confirm_at`, retries, and alarm bookkeeping like
      any scheduled cycle; one `EventHub` on the running loop;
      `run_monitor(..., listeners=[hub.cycle_listener],
      channels=(*context.channels, BrowserChannel(hub,
      settings.notifications.browser)))`; the watcher and the
      staleness timer as tasks that stop with the monitor; the
      hub's `close` among `WebServer`'s `before_stop` callables, so
      every open stream ends before uvicorn shuts down; and the
      hub, the channels, and the network in `WebState`. `check`,
      `check --once`, and every other command keep their channels:
      they have no page to deliver to.
    </requirement>

    <requirement>
      `GET /api/events` (`src/weatherbot/web/routes/events.py`),
      `async def` with `response_class=EventSourceResponse` and the
      return annotation `AsyncIterable[StreamEvent]` (the payload
      model, in `web/schemas.py`, whose `invalidate` is a list of a
      `QueryKey` literal of the nine keys, so the generated types
      carry the vocabulary): it subscribes, yields a `hello`
      `StreamEvent` first (the server's start instant and the
      newest cycle id), then each hub event as its `StreamEvent`
      model — FastAPI validates each against the annotation and
      sends it as JSON `data:`, so the page reads `kind` and `id`
      from the payload (strict pyright would refuse a
      `ServerSentEvent` yielded from that annotation, and no
      `Last-Event-ID` resume is needed: a reconnect refetches);
      it ends when the subscription ends (the hub closed it, or it
      overflowed). `scripts/export_openapi.py`
      adds `StreamEvent` and every model it references to the
      document's `components.schemas`, which FastAPI leaves out,
      and `tests/web/test_openapi_export.py` asserts they are
      there, so Step 4's generated types carry every event's shape.
    </requirement>

    <requirement>
      The writes (`src/weatherbot/web/routes/actions.py`), each
      publishing its events:

      - `POST /api/locations` `{name, latitude, longitude,
        polygon: "county" | "forecast" | null}` → 201 with the
        stored location in `/api/locations`' shape; 409 for a taken
        name (`LocationService.add` today raises a plain
        `LocationError` for it, so the step adds
        `LocationNameTakenError(LocationError)`, raised in both of
        its taken-name branches, and the CLI's `except
        LocationError` still catches it); 422 for a body that fails
        validation or another `LocationError` (a polygon outside NWS
        coverage); 502 naming the source when NWS or Nominatim does
        not answer. It is a plain function that runs
        `LocationService.add` under `asyncio.run` in its worker
        thread, so neither the network nor SQLite's busy wait (up to
        30 seconds) stalls the server's loop. Publishes `location`
        (invalidates `locations`, `assessments`, `map`).
      - `PUT /api/locations/evacuation` `{location, on}` → 200 with
        the location and whether it changed; 404 for an unknown
        location. A plain function. Publishes `location`. The next
        cycle assesses with it, as in `locations evacuation`.
      - `POST /api/cycles` `{}` → 202; hands `WebState.
        request_cycle` to the server's loop as a background task
        (trigger `manual`, no new trigger: Phase 4's check 8; its
        database work runs where the scheduler's own cycles run);
        409 while one it started is running; 429 within 60 seconds
        of the last one it started.
      - `POST /api/notifications/test` `{}` → 200 with the stored
        notification and its deliveries, sent with kind `test`
        through `serve`'s channels (log, toast, browser) on the
        server's loop, as the scheduler's alarms are; 429 within 10
        seconds of the last.
    </requirement>

    <requirement>
      `docs/api/openapi.json` is regenerated. `CONTRIBUTING.md`:
      "The event stream" (the events, their keys, `hello` and
      reconnects, the watcher, the staleness timer, the browser
      channel's results, and the writes with their limits).
      `CHANGELOG.md`: this step's entries.
    </requirement>

    <requirement>
      Tests, offline unless marked, under unique basenames, none of
      which skips on Windows or Ubuntu:

      - `tests/services/test_event_hub.py`: ordered delivery to two
        subscribers; a publish from a worker thread arrives; an
        overflowing subscriber's iterator ends while the other
        continues; the cycle listener's events for a recorded
        cycle (cycle, snapshot, one assessment per created one, an
        alert for an `official_*` change, none for an assessment
        already stored); no event holds a coordinate (the renderings
        `tests/cli/test_cli_privacy.py` checks).
      - `tests/services/test_cycle_watcher.py`: a cycle, a
        notification, an assessment, and a location toggled by
        another process reach the hub within one interval (a short
        interval in the test); what the listener published is not
        repeated; the first read publishes nothing.
      - `tests/services/test_staleness_timer.py`: on a fake clock,
        one `health` event at the earliest boundary, rescheduled
        after a cycle and again after it fires, and none when no
        row has a cadence.
      - `tests/services/test_browser_channel.py`: `delivered` with
        two subscribers (and the event's `display`), `unavailable`
        with none, `disabled` by the setting; `serve`'s channels
        include `browser`, `Context.channels` does not; a quiet-hours
        alarm (`include_toast=False`) reaches the log only, neither
        the toast nor the browser.
      - `tests/web/test_event_stream.py`: over a real socket on
        `127.0.0.1:0` (inside `recorded_services()`, with Step 1's
        loopback pass-through), `hello` comes first, a published
        cycle arrives as its events in order with increasing ids, a
        disconnected client's subscription is released, a
        seventeenth subscriber is answered 503, and the hub's
        `close` ends an open stream so `WebServer` stops.
      - `tests/web/test_api_actions.py`: each write's success and
        error answers over recorded answers (`recorded_services()`
        for `POST /api/locations`), its events, its rate limit,
        and its refusal when cross-site or not JSON; check now
        runs through `request_cycle`, stores a cycle with trigger
        `manual` under runner `serve`, and schedules the
        confirmation of a drop it holds; a taken name answers 409
        through `LocationNameTakenError`.
      - `tests/live/test_web_live.py` (`live` and `enable_socket`):
        `serve`'s app with the live fetcher, both landmarks in a
        temporary data directory, `POST /api/cycles`, and the
        stream's `cycle`, `snapshot`, and `assessment` events.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with its repo-relative path as a comment, as every
      existing one does.
    </requirement>
  </requirements>
</task>
```

### Step 3 acceptance criteria

- A cycle that `serve` runs reaches a subscribed client as its `cycle`,
  `snapshot`, `assessment`, and `alert` events, in order, each naming the
  queries to refetch; a cycle another process runs reaches it within one watcher
  interval and is never published twice.
- Every connection starts with `hello`; a slow subscriber is closed without
  affecting the others; a heartbeat turning stale sends one `health` event at
  that instant.
- The browser channel records `delivered` with a page open, `unavailable`
  without one, and `disabled` when switched off; only `serve` carries it, and no
  notification kind or cycle trigger is added.
- The four writes answer as specified, publish their events, honour their rate
  limits, and are refused when cross-site or not JSON; check now stores a
  `manual` cycle under the `serve` runner.
- `docs/api/openapi.json` carries the event route and the event payloads, and
  equals a fresh export.
- Check now runs through the running schedule, so a drop it holds gets its
  confirmation cycle; a quiet-hours alarm reaches neither the toast nor the
  browser; at most 16 pages subscribe.
- **Deployed & verified:** the first `ci.yml` and `phase-verify.yml` runs on
  `main` after the merge are green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, SAST
  clean, dependency audit clean with no dependency added — and no event holds a
  coordinate, every write is refused cross-site, and the queues, the
  subscribers, and the two rate-limited writes are bounded.

---

## Step 4 — The frontend chassis, its gate, and the wheel ✅

**Status:** Complete — PR #64 (2026-10-27)

> **Goal:** Stand up the page every later step fills, and ship it in the wheel.
> `frontend/` holds a Vite 8 + React 19 + strict TypeScript 5.9.3 app on Node 24
> (`frontend/.nvmrc`) with Tailwind CSS 4, TanStack Query 5, React Router 8 in
> data mode, the unified `radix-ui` package, and lucide icons;
> `frontend/src/api/schema.d.ts` is generated from `docs/api/openapi.json` by
> openapi-typescript and checked with its `--check` flag; one typed
> openapi-fetch client and one module of query keys match the server's
> `invalidate` vocabulary; `useEventStream` holds one `EventSource` per tab and
> invalidates exactly the queries each event names (everything on a reconnect's
> `hello`); the app shell gives the six routes, the navigation, the themes (the
> system's by default, a stored pick applied before first paint by
> `public/theme-init.js`), the staleness banner, and the disclaimer footer on
> every page; `main.tsx` reads the per-answer nonce and hands it to the
> components that inject styles; Vitest with jsdom and Testing Library covers
> it; ESLint (typescript-eslint, `eslint-plugin-react-hooks`, and
> `eslint-plugin-security` at `--max-warnings 0`) and `npm audit
> --audit-level=high` join pre-commit and CI; a `frontend` job joins the gate;
> Dependabot gains `npm`; and the `package` job builds the interface into
> `src/weatherbot/web/static/` (with `licenses.json`) before `uv build`, then
> proves an installed wheel serves it. Steps 5 and 6 fill the pages.

**Branch:** `feature/phase05-step4-frontend-chassis`

**Deploys:** nothing beyond merge for the product — the operator's copy keeps
Step 1's build until Step 7. On the operator's machine → with the operator's
yes, Node 24 (at least 24.15) replaces Node 22.18 as the frontend's build tool
before the first `npm ci`. GitHub Actions → the `frontend` job joins `gate` and
the `package` job builds the interface; the first `ci.yml` and
`phase-verify.yml` runs on `main` must be green.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.18/1M           | $4.00/1M*          | $8.46/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.56/1M           | $6.02/1M           | $4.00/1M*          |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | XHigh              | XHigh              |
|               | AA       | not measured       | 51                 | 52.4               |
|               | Price    | $2.40/1M*          | $4.00/1M           | $16.36/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out) ×
the tokens the model uses at that level; * token use not yet measured, a typical
model's at that level assumed.

**Conversation:** New

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that
column's usage pool reads `tight` or `exhausted`, run the first of its Runner-up
and Backup whose pool has headroom; on a `tight` pool an option marked ↓ (the
Pick one level lower) also runs. With none, a `tight` column runs the Cost
column and an `exhausted` one its Backup.

> Settings updated 2026-10-25 (rerank): each column's Runner-up and Backup now come from makers other than its Pick; every Pick is unchanged.
> Ran 2026-10-27: Balanced Pick — Gemini 4 Argon · Effort High · Thinking On on Antigravity. Selected by the **Runs:** rule (Google AI Pro pool reads headroom).

**Model rationale:** Step 4 is coding with an agentic secondary category: a new
toolchain on a new Node line, generated types and a drift gate, the shell and
the event subscription every page relies on, the frontend's half of the security
gate in pre-commit and CI, two workflow jobs, and the wheel's build and smoke.
Its overall complexity is High — strict versions with known peer conflicts, a
Content-Security-Policy nonce threaded through the page, query invalidation
driven by the server's vocabulary, and Windows and Ubuntu builds — and it is not
novel: this roadmap fixes every package, version, script, and job. The columns
differ in depth and maker: Balanced runs Gemini 4 Argon on Antigravity at Effort
High with thinking on; Quality runs Opus 5.5 on Claude Code at Effort XHigh
(always thinking, so no Thinking field) for the closest audit of the gate and
the CI wiring; Cost moves it to GPT-6.1 Sol on Codex at Intelligence High.
Google AI Pro, the claude.ai Max subscription, and ChatGPT Pro 5x fund the three
platforms, so each column costs nothing at the margin while its pool has
headroom; when a column's pool reads `tight` or `exhausted`, the **Runs:** rule
moves the step to that column's Runner-up or Backup. The conversation is new per
phase-boundary hygiene.

```xml
<task>
  <lifecycle>
    This step MUST follow all six
    stages, in order. Stages 1, 3,
    4, 5, 6 are AS BINDING as any
    `<requirement>` below. Do not
    emit the Stage 6 completion
    line until the PR is merged and
    every acceptance criterion for
    this step is affirmatively met.

    1. CREATE THE BRANCH. Before
       any Read / Edit / Bash, run
       `git checkout -b
       feature/phase05-step4-frontend-chassis`
       from a clean, up-to-date
       `main`. The exact branch
       name is in this step's
       `**Branch:**` line above.
       If the Worktree rule
       applies, use `git fetch
       origin && git worktree add
       -b <branch> <path>
       origin/main` instead, then
       bootstrap the worktree.

    2. WORK ON THE BRANCH. All
       commits land here. `main`
       is protected with
       `enforce_admins: true` —
       direct pushes will be
       rejected.

    3. OPEN THE PR, THEN MARK THE
       STEP. `gh pr create --base
       main --head <branch>` with a
       Conventional Commits title
       and a body that references
       this roadmap step and its
       acceptance criteria. One PR
       per step. Then, in this
       roadmap file: set this
       step's `**Status:**` line
       (directly under its heading)
       to `Complete — PR #<n>
       (<YYYY-MM-DD>)`, append ` ✅`
       to the step's `## Step`
       heading, and set its
       Summary Table Status cell to
       `Complete — PR #<n>`. Commit
       that edit on the step
       branch and push — the PR
       carries its own completion
       mark, so the roadmap on
       `main` marks this step
       complete exactly when the PR
       merges (Status rule). Same
       commit: on the phase's first
       step, set this roadmap's
       phase-level `**Status:**`
       (under its title) and the
       parent project roadmap's
       Phase 5 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 5`
       heading.

    4. WAIT FOR GREEN CHECKS, THEN
       SQUASH-MERGE. Every required
       check must pass. If the PR
       falls behind main, refresh
       with `gh pr update-branch
       --rebase` — never merge main
       into the branch
       (`required_linear_history:
       true`). Once green:
       `gh pr merge <PR> --squash
       --delete-branch`. If this
       step's `**Deploys:**` line
       names a surface, the merge
       is not the finish line: run
       the Deployed & verified
       check against the target
       environment before
       declaring the step complete.

    5. RETIRE THE BRANCH. Sync
       local: `git switch main &&
       git pull --ff-only origin
       main && git fetch --prune
       origin`. Prune any local
       `[gone]` branches. If the
       step ran in a worktree,
       `git worktree remove <path>`
       FIRST — the branch prune
       fails while the branch is
       checked out there.

    6. DISPOSE OF EVERY FINDING,
       DECLARE COMPLETION, THEN
       NEW CONVERSATION. First
       send every finding this
       step surfaced to its
       destination (Triage rule):
       a note for a later step →
       edit that step's <task>
       block now; spec rot → edit
       this roadmap now; a bug →
       fixed in-step or an issue
       number; a judgement call in
       the diff → the PR body; a
       process lesson → written
       where the next conversation
       reads it. A finding you can
       only describe is NOT
       disposed of, and counts as
       an unmet criterion. Only
       once the PR is merged — and
       `main` therefore carries
       this step's `Complete`
       Status line — every
       acceptance criterion is
       affirmatively met, and every
       finding has a destination,
       say so plainly: end your
       final response with an
       explicit, unhedged
       completion line — verbatim
       shape "Step 4 is
       complete. You can now move
       on to Step 5." That
       line is the LAST line of
       the response. NOTHING
       follows it — no "Follow-ups
       (non-blocking)", "Notes",
       "Next", "worth a glance",
       or suggested improvements.
       A short ledger may PRECEDE
       it, one entry per finding
       naming its destination
       (issue #, file edited, PR
       body) — never an open item.
       If any criterion is unmet
       or any finding has no
       destination, state plainly
       that the step is NOT
       complete, name what is
       outstanding, and omit the
       completion line. "Done"
       means done. Then, for
       phase-boundary hygiene, the
       operator closes this
       session and opens a fresh
       one before Step 5.
  </lifecycle>

  <security>
    Security is a gate on THIS
    step, not a later phase. It is
    AS BINDING as any
    `<requirement>` below. Before
    the Stage-2 commit, this
    step's work MUST pass the
    local, fail-closed security
    gate — the SAME gate wired
    into the pre-commit hook and
    re-run in CI:

    1. SECRET / PII SCAN. No
       credentials, API keys,
       tokens, or real PII in the
       diff (gitleaks /
       detect-secrets or the
       project's equivalent).
       Secrets go in the secrets
       manager, never in source or
       committed env files.

    2. SAST. No new injection,
       unsafe deserialization,
       weak crypto, path
       traversal, or unsafe-eval
       pattern (bandit / semgrep /
       eslint-plugin-security per
       the stack). Suppress a
       finding ONLY with an inline
       justification comment.

    3. DEPENDENCY AUDIT. Any new
       or bumped dependency passes
       the audit (pip-audit / npm
       audit / osv-scanner); no
       known-vulnerable, yanked,
       or typo-squatted package.

    4. SENSITIVE-DATA REVIEW.
       Whatever this step touches
       stays least-privilege,
       encrypted in transit + at
       rest, and out of logs and
       client bundles. If the step
       adds a data path, name how
       PII/secrets are protected.

    A finding blocks the commit —
    fix it in this step, do not
    defer. Do not declare the step
    complete until the gate is
    clean. This is the safety net
    that stops a security issue
    from reaching the branch, the
    PR, or `main`.

    THIS STEP brings npm into the repository. `package-lock.json`
    is committed and every install is `npm ci`; CI runs `npm audit
    signatures` after it and `npm audit --audit-level=high`, and
    pre-commit runs the audit whenever `frontend/package.json` or
    its lock changes. ESLint's `eslint-plugin-security` is the
    frontend's SAST and runs at `--max-warnings 0` (its rules only
    warn); a finding is fixed, or suppressed on its line with a
    justification, never turned off globally. The frontend reads
    no environment variable: no `import.meta.env.VITE_*` in
    `frontend/src`, no `.env` file (Phase 1's check 30), so no
    build can embed a value from the machine that built it. The
    page never writes an API answer, or an error carrying one, to
    the console: errors log a route and a status. Test fixtures
    use the two landmarks or generated values, never another
    coordinate with three or more decimals (the personal-data
    check scans every frontend file, and its R2 rule flags any two
    numbers of three or more decimals in degree range on one line:
    SVG path data is written to at most two decimals and CSS keeps
    no such pair). The dev server binds
    `127.0.0.1` only. Every bundled package's licence lands in
    `licenses.json`, and a licence outside MIT, ISC, BSD-2-Clause,
    BSD-3-Clause, Apache-2.0, and 0BSD fails the build check;
    react-leaflet (Hippocratic-2.1) is not used. `actions/setup-node`
    is pinned to its full commit SHA with a version comment
    (Phase 1's check 25), and every workflow keeps its top-level
    `permissions:` (check 26).
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 5 (Web app MVP). Step 4:
    the frontend chassis, its gate, and the wheel.

    Current state (as of Phase 5 Step 3):

    - Steps 1 to 3 serve the guarded API from `serve`:
      `/api/health` (with `notice` and `stale`), the read routes,
      `/api/events` (`StreamEvent` with `kind`, ids, and
      `invalidate` drawn from `health`, `locations`,
      `assessments`, `storms`, `alerts`, `map`, `timeline`,
      `notifications`, `settings`), and the four writes, all in
      `docs/api/openapi.json` with the event models in its
      components. `index.html` is served with a fresh nonce for
      each `__CSP_NONCE__` placeholder, `no-store`, and `style-src
      'self' 'nonce-…'`; root files under
      `src/weatherbot/web/static/` are served with `no-cache` and
      `assets/` immutable; unknown non-API paths answer
      `index.html`. Writes need `Content-Type: application/json`
      and an `Origin` of `http://` plus the request's own `Host`.
      Read the three PR bodies for anything they changed.
    - Read on 2026-10-25 from the npm registry and installed
      together in a probe (Overview, "Design rationale"): Vite
      8.3.5 (`build.rolldownOptions` replaces
      `build.rollupOptions`; `build.license` writes every bundled
      package's licence; `html.cspNonce` puts a placeholder on
      Vite's own tags and a `<meta property="csp-nonce">`),
      `@vitejs/plugin-react` 6.1.2 (Vite 8 only), React 19.3.1,
      TypeScript 5.9.3 (typescript-eslint 8.72 accepts below 6.1;
      openapi-typescript 7.13 only 5.x; TypeScript 7.0 ships no
      API), Tailwind CSS 4.3.3 with `@tailwindcss/vite`, TanStack
      Query 5.104, React Router 8.5 (ESM only; Node 22.22 and React
      19.2.7 at least), `radix-ui` 1.8.1, lucide-react 1.61,
      openapi-typescript 7.13.0 and openapi-fetch 0.17.0, Vitest
      5.0.5, jsdom 30.1.3, `@testing-library/react` 16.3.3 (needs
      `@testing-library/dom` 10 installed beside it),
      `@testing-library/user-event` 14.6.8,
      `@testing-library/jest-dom` 7.0.1, ESLint 10.13 with
      `@eslint/js` 10, typescript-eslint 8.72,
      `eslint-plugin-react-hooks` 7.1 (flat config
      `configs.flat.recommended`), `eslint-plugin-security` 4.2
      (flat config `configs.recommended`; all rules warn), and
      `globals` 17. `actions/setup-node` v7.1.0 is commit
      `949feb2413d6458794dcd2491c4babbbce0c15c1`; its v7 README
      revised its caching advice to mitigate cache poisoning.
    - Probed in Chrome 156 under the planned policy: Vite's built
      `index.html` has no inline script or style; Tailwind's CSS is
      a linked file; Radix's Dialog, AlertDialog, DropdownMenu,
      Select, modal Popover, and ScrollArea inject `<style>`
      elements, which pass only with the nonce
      (`react-remove-scroll` reads `globalThis.__webpack_nonce__`;
      `ScrollArea.Viewport` and `Select.Viewport` take a `nonce`
      prop); a synchronous external script in `<head>` applies a
      stored theme before first paint without any inline script.
    - `ci.yml` jobs: `lint`, `typecheck` (both runners), `test`
      (both), `package` (both), `security`, and `gate` (its `needs`
      list is the whole membership). Phase 2's check 35 reads
      `WEATHERBOT_DATA_DIR` and `open_database` in `package`;
      Phase 4's check 31 reads both runners in `test`, `typecheck`,
      and `package`; Phase 1's check 24 reads the `security` job's
      four tools, and its checks 25 and 26 every `uses:` pin and
      every workflow's `permissions:`. `.github/dependabot.yml`
      covers `uv`, `github-actions`, and `pre-commit`.
    - `.gitattributes` sets no global line-ending rule; pre-commit's
      `mixed-line-ending --fix=lf` keeps frontend files LF. The
      httpx client honours `HTTPS_PROXY`, so the wheel smoke can
      keep the startup cycle's requests on the runner.

    Files to read (every file before drafting):
    - docs/roadmap/phase05-roadmap.md (Overview and its design
      rationale, Steps 1 to 3, this step, and Steps 5 to 7).
    - docs/api/openapi.json, src/weatherbot/web/ (all).
    - .github/workflows/ci.yml, .github/dependabot.yml,
      .pre-commit-config.yaml, .gitignore, .gitattributes,
      pyproject.toml.
    - scripts/verify_phase01.py (checks 24 to 26),
      scripts/verify_phase02.py (check 35),
      scripts/verify_phase04.py (check 31).
    - README.md, CONTRIBUTING.md, CHANGELOG.md.
  </context>

  <goal>
    Ship `frontend/` with its toolchain, generated types, client,
    query keys, event subscription, shell, themes, nonce plumbing,
    and tests; the frontend's gate in pre-commit and CI; the
    `frontend` job; Dependabot's `npm` entry; and the `package`
    job's build, licence check, and installed-wheel smoke.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
      At kickoff, confirm `node --version` is at least 24.15 on
      the operator's machine; if it is not, ask the operator
      (AskUserQuestion) to install Node 24 before anything runs
      `npm`, and do not proceed on an older Node.
    </requirement>

    <requirement>
      `frontend/`: `package.json` (`"private": true`, `"type":
      "module"`, `engines.node` `>=24.15`, exact versions for every
      dependency from the context's list, and the scripts `dev`,
      `build`, `typecheck` (`tsc --noEmit`), `lint` (`eslint .
      --max-warnings 0`), `test` (`vitest run`), `api:generate` and
      `api:check` (openapi-typescript over
      `../docs/api/openapi.json` into `src/api/schema.d.ts`, the
      second with `--check`), `licenses:check`, and `audit` (`npm
      audit --audit-level=high`)); `package-lock.json`; `.nvmrc`
      (`24`); `tsconfig.json` (strict, `noUncheckedIndexedAccess`,
      `verbatimModuleSyntax`); `eslint.config.js` (flat:
      `@eslint/js`, typescript-eslint's type-checked config,
      `eslint-plugin-react-hooks`' flat recommended, and
      `eslint-plugin-security`'s recommended); `vite.config.ts`;
      `index.html`; `public/` (`theme-init.js` and an SVG icon of
      the project's own); and `src/`. No file under `frontend/`
      names a path version 1 deleted, and no `.vscode/` file is
      added (Phase 1's check 10).
    </requirement>

    <requirement>
      `vite.config.ts`: the React and Tailwind plugins;
      `build.outDir: "../src/weatherbot/web/static"` with
      `emptyOutDir: true`; `build.license: { fileName:
      "licenses.json" }`; `build.sourcemap: false`; `html.cspNonce:
      "__CSP_NONCE__"`; and a dev server on `127.0.0.1` with
      `strictPort` that proxies `/api` to `http://127.0.0.1:8765`
      with `changeOrigin: true` and `Origin` rewritten to the
      proxied origin, so the write guard accepts the dev server's
      writes, and with `Sec-Fetch-Site` passed through untouched
      (the guards themselves are unchanged). `index.html` carries
      the nonce meta, links
      `/theme-init.js` synchronously in `<head>`, and has no inline
      script or style. `frontend/scripts/check-licenses.mjs`
      (`licenses:check`) reads the build's `licenses.json` and
      exits 1 naming any package whose licence is outside MIT, ISC,
      BSD-2-Clause, BSD-3-Clause, Apache-2.0, and 0BSD.
    </requirement>

    <requirement>
      `frontend/src/`:

      - `main.tsx`: before rendering, sets
        `globalThis.__webpack_nonce__` from
        `document.querySelector('meta[property="csp-nonce"]')
        ?.nonce` — the `nonce` property, because once a policy
        applies the browser blanks the attribute, so
        `getAttribute("nonce")` reads an empty string (jsdom would
        not show it; Step 7's smoke does) — and exports the nonce
        for the `ScrollArea.Viewport` and `Select.Viewport` that
        take it; creates one `QueryClient`
        with `staleTime: Infinity`, no refetch interval, no refetch
        on window focus or reconnect, and `retry: 1`; and renders
        the router.
      - `api/schema.d.ts` (generated, committed), `api/client.ts`
        (one openapi-fetch client on the same origin, JSON writes
        with `Content-Type: application/json`), and `api/keys.ts`:
        the nine invalidatable query keys, typed by the generated
        `invalidate` literal so a key the server does not name fails
        to compile, kept apart from the page's own static keys
        (`replay`, `disclaimer`, `licenses`), which no event names.
      - `events/useEventStream.ts`: one `EventSource('/api/events')`
        per tab, opened by the shell, reading each `message` as a
        `StreamEvent` (typed by the generated schema) and
        dispatching on its `kind`: the shell opens the stream as it
        mounts; the first `hello` marks the stream connected without
        refetching, and every later `hello` (a reconnect) invalidates
        every query; each other event invalidates
        exactly its `invalidate` keys; a `notification` event with
        `display` is handed to a callback the shell provides (Step
        5 shows it).
      - The shell (`app/`): React Router 8 data mode with the
        routes `/`, `/map`, `/storms`, `/alerts`, `/timeline`, and
        `/settings` (each a placeholder Steps 5 and 6 replace) and a
        not-found page; a navigation that works by keyboard and
        collapses at phone width (down to 360 px) without
        horizontal scrolling; a theme menu (a Radix DropdownMenu:
        system, light, dark — it injects a `<style>`, so Step 7's
        smoke proves the nonce through it) stored as
        `weatherbot.theme` in `localStorage` and applied by
        `public/theme-init.js` and by the menu through a `dark`
        class (Tailwind's `@custom-variant dark`); a
        staleness banner when `/api/health` says `stale`, naming the
        stale sources and their ages; a footer on every page with
        `/api/health`'s `notice` linking to the disclaimer; and a
        connection indicator that says when the event stream is
        reconnecting. Level colours always come with their number
        and label in text.
      - Nothing logs an API answer: a failed request logs its route
        and status only.
    </requirement>

    <requirement>
      Tests (Vitest, jsdom, Testing Library, jest-dom), each file
      named for what it covers under `frontend/src/**/*.test.tsx`:
      the event subscription with a fake `EventSource` (no refetch
      on the first `hello`, every query on the second, exactly the
      named keys on an event, the `display` callback); the shell
      (navigation, the six routes, the footer's notice, the banner
      from a stale health answer, the reconnecting indicator); the
      theme menu (stored, applied, system by default); the
      client's write headers; and `api/keys.ts` against the
      generated vocabulary.
    </requirement>

    <requirement>
      Pre-commit: two `local` hooks — `frontend-lint` (`npm
      --prefix frontend run lint`, on `^frontend/` changes, not
      passing file names) and `npm-audit` (`npm --prefix frontend
      audit --audit-level=high`, on `^frontend/package(-lock)?\.json$`)
      — beside the existing gate, whose required hook ids stay
      (Phase 1's check 21).
    </requirement>

    <requirement>
      CI (`ci.yml`):

      - A `frontend` job on `ubuntu-latest`: checkout,
        `actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1
        # v7.1.0` with `node-version-file: frontend/.nvmrc`, `npm
        ci`, `npm audit signatures`, `npm run api:check`, `lint`,
        `typecheck`, `test`, `build`, and `licenses:check`; it joins
        `gate`'s `needs`.
      - The `security` job adds setup-node, `npm ci` in
        `frontend/`, `npm audit --audit-level=high`, and the ESLint
        run at `--max-warnings 0` — the frontend's dependency audit
        and SAST beside pip-audit and bandit — keeping its four
        existing tools and their names (Phase 1's check 24).
      - The `package` job, on both runners, sets up Node and runs
        `npm ci` and `npm run build` before `uv build`, asserts the
        wheel holds `weatherbot/web/static/index.html` and
        `weatherbot/web/static/licenses.json`, keeps its version
        and migration smokes (`WEATHERBOT_DATA_DIR`,
        `open_database`), and adds the web smoke below.
      - Dependency caching follows setup-node v7.1.0's README or is
        left off; `npm ci` from the lock takes about a minute.
    </requirement>

    <requirement>
      `scripts/smoke_installed_web.py` (standard library only, run
      by the installed wheel's Python outside the checkout): starts
      `weatherbot serve --no-open` with a temporary data and
      configuration directory, `WEATHERBOT_WEB_PORT` set to a free
      port it picks, `WEATHERBOT_NOTIFICATIONS_TOAST=false`,
      `HTTPS_PROXY=http://127.0.0.1:9`, and `NO_PROXY=127.0.0.1,
      localhost` (so the startup cycle's requests fail fast and
      nothing leaves the machine); waits up to 60 seconds for
      `/api/health`; requires `/` to answer the built `index.html`
      with a `Content-Security-Policy` naming a nonce, and
      `/api/health`'s `version` and `ui.present`; then stops the
      process. It starts `weatherbot` as the existing scripts start
      a tool — the executable resolved to an absolute path, an
      argument list, never a shell, and a justified `# nosec` that
      bandit (which scans `scripts/`) accepts. The `package` job
      runs it on both runners with no Node on the request path (the
      server never invokes one).
    </requirement>

    <requirement>
      `.github/dependabot.yml` gains `package-ecosystem: npm` for
      `directory: /frontend`, weekly, `chore(deps)`, with a
      minor-and-patch group and an `ignore` rule for `typescript`
      at 6 and above (typescript-eslint and openapi-typescript do
      not accept it yet), and its header comment drops the "npm
      joins later" note. `.gitignore` gains
      `/frontend/node_modules/`, `/frontend/coverage/`,
      `/frontend/test-results/`, `/frontend/playwright-report/`,
      and `*.tsbuildinfo` (keeping every line Phase 1's check 18
      and Phase 2's mutation case read).
    </requirement>

    <requirement>
      Documents. `CONTRIBUTING.md`: "The frontend" (Node 24 and
      `.nvmrc`, `npm ci`, the dev loop — `weatherbot serve
      --no-open` beside `npm run dev` on 127.0.0.1 with the proxy —
      the scripts, regenerating the types after an API change, the
      build into the package and why it is git-ignored, the
      licence allowlist, and the frontend's half of the gate).
      `README.md`'s development quickstart: building the interface.
      `CHANGELOG.md`: this step's entries. `docs/DATA_SOURCES.md`
      is unchanged.
    </requirement>

    <requirement>
      Filepath comment: every new TypeScript, JavaScript, YAML, and
      CSS file starts with its repo-relative path as a comment
      (`// frontend/src/main.tsx`, `/* frontend/src/index.css */`);
      JSON files, which take no comments, are exempt.
    </requirement>
  </requirements>
</task>
```

### Step 4 acceptance criteria

- `frontend/` builds on Node 24 with the pinned versions; `npm run api:check`,
  `lint` (at `--max-warnings 0`), `typecheck`, `test`, `build`, and
  `licenses:check` pass in the `frontend` job, which `gate` requires.
- The event subscription refetches nothing on the first `hello`, everything on a
  reconnect's, and exactly the named keys on an event; the query keys compile
  only against the server's vocabulary; no query polls or refetches on focus.
- The shell renders the six routes, the navigation down to 360 px, the themes
  with no flash and no inline script, the staleness banner, and the disclaimer
  footer on every page; the nonce reaches the style-injecting components.
- The wheel built in the `package` job holds `index.html` and `licenses.json`,
  and `scripts/smoke_installed_web.py` sees the installed `serve` answer `/`
  (with a nonce in its policy) and `/api/health` on both runners, with nothing
  leaving the runner.
- Dependabot watches `frontend/`; `.gitignore` covers the frontend's outputs;
  Phase 1's checks 18, 21, 24, 25, and 26, Phase 2's check 35, and Phase 4's
  check 31 stay green.
- **Deployed & verified:** `node --version` reads 24.15 or later on the
  operator's machine, and the first `ci.yml` run on `main` after the merge shows
  `frontend`, `package`, and `security` green inside `gate`, with
  `phase-verify.yml` green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, bandit
  and `eslint-plugin-security` clean, `pip-audit` and `npm audit
  --audit-level=high` clean, `npm audit signatures` verified — and the frontend
  reads no environment variable, logs no API answer, and bundles only
  allowlisted licences.

---

## Step 5 — The dashboard and the pages ✅

**Status:** Complete — PR #65 (2026-10-27)

> **Goal:** Fill the shell with the pages the operator reads at 3 a.m. The
> Dashboard shows, per location, a level card (number, label, and colour; the
> deciding rule and its evidence; the actions; "at least" with the missing
> inputs; the evacuation toggle's state; when it was assessed, in UTC and the
> location's own time zone; the disclaimer's notice), the storms and alerts that
> concern it, the next NHC product time, and "check now"; with no location, it
> shows the disclaimer's essentials and the way to the first-run setup. Storms,
> Alerts, and Timeline render `/api/storms`, `/api/alerts`, and `/api/timeline`;
> Settings holds the first-run location form, the evacuation toggles, the
> browser-notification switch with its permission state and a test, the
> effective settings with their origins, the disclaimer's full text, and the
> third-party licences. The shell's `display` callback becomes an in-page
> message, and an operating-system notification when the operator turned them on
> and the page is hidden. Every page renders from fixtures that
> `scripts/export_api_fixtures.py` writes from the real API over recorded
> answers, so the pages and the API cannot drift apart. Step 6 adds the map.

**Branch:** `feature/phase05-step5-pages`

**Deploys:** nothing beyond merge — the operator's copy keeps Step 1's build
until Step 7 redeploys it. GitHub Actions → the first `ci.yml` and
`phase-verify.yml` runs on `main` must be green.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.18/1M           | $4.00/1M*          | $8.46/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.56/1M           | $6.02/1M           | $4.00/1M*          |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | XHigh              | XHigh              |
|               | AA       | not measured       | 51                 | 52.4               |
|               | Price    | $2.40/1M*          | $4.00/1M           | $16.36/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out) ×
the tokens the model uses at that level; * token use not yet measured, a typical
model's at that level assumed.

**Conversation:** New

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that
column's usage pool reads `tight` or `exhausted`, run the first of its Runner-up
and Backup whose pool has headroom; on a `tight` pool an option marked ↓ (the
Pick one level lower) also runs. With none, a `tight` column runs the Cost
column and an `exhausted` one its Backup.

> Settings updated 2026-10-25 (rerank): each column's Runner-up and Backup now come from makers other than its Pick; every Pick is unchanged.

> Ran 2026-10-27: Balanced Pick — Gemini 4 Argon · Effort High · Thinking On on Antigravity. Selected by the **Runs:** rule (Google AI Pro pool reads headroom).

**Model rationale:** Step 5 is coding with a multimodal secondary category: five
pages over a fixed contract, a level card whose evidence and missing inputs must
read correctly, a first-run form with server-side validation, browser
notifications with their permission states, two themes, and phone width, checked
by looking at the rendered pages. Its overall complexity is High — many
interacting components, the disclaimer on every assessment view, time zones,
units, and empty, loading, and error states — and it is not novel: the API and
this roadmap fix every field shown and every action taken. The columns differ in
depth and maker: Balanced runs Gemini 4 Argon on Antigravity at Effort High with
thinking on; Quality runs Opus 5.5 on Claude Code at Effort XHigh (always
thinking, so no Thinking field) for the closest audit of what each page says;
Cost moves it to GPT-6.1 Sol on Codex at Intelligence High. Google AI Pro, the
claude.ai Max subscription, and ChatGPT Pro 5x fund the three platforms, so each
column costs nothing at the margin while its pool has headroom; when a column's
pool reads `tight` or `exhausted`, the **Runs:** rule moves the step to that
column's Runner-up or Backup. The conversation is new per phase-boundary
hygiene.

```xml
<task>
  <lifecycle>
    This step MUST follow all six
    stages, in order. Stages 1, 3,
    4, 5, 6 are AS BINDING as any
    `<requirement>` below. Do not
    emit the Stage 6 completion
    line until the PR is merged and
    every acceptance criterion for
    this step is affirmatively met.

    1. CREATE THE BRANCH. Before
       any Read / Edit / Bash, run
       `git checkout -b
       feature/phase05-step5-pages`
       from a clean, up-to-date
       `main`. The exact branch
       name is in this step's
       `**Branch:**` line above.
       If the Worktree rule
       applies, use `git fetch
       origin && git worktree add
       -b <branch> <path>
       origin/main` instead, then
       bootstrap the worktree.

    2. WORK ON THE BRANCH. All
       commits land here. `main`
       is protected with
       `enforce_admins: true` —
       direct pushes will be
       rejected.

    3. OPEN THE PR, THEN MARK THE
       STEP. `gh pr create --base
       main --head <branch>` with a
       Conventional Commits title
       and a body that references
       this roadmap step and its
       acceptance criteria. One PR
       per step. Then, in this
       roadmap file: set this
       step's `**Status:**` line
       (directly under its heading)
       to `Complete — PR #<n>
       (<YYYY-MM-DD>)`, append ` ✅`
       to the step's `## Step`
       heading, and set its
       Summary Table Status cell to
       `Complete — PR #<n>`. Commit
       that edit on the step
       branch and push — the PR
       carries its own completion
       mark, so the roadmap on
       `main` marks this step
       complete exactly when the PR
       merges (Status rule). Same
       commit: on the phase's first
       step, set this roadmap's
       phase-level `**Status:**`
       (under its title) and the
       parent project roadmap's
       Phase 5 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 5`
       heading.

    4. WAIT FOR GREEN CHECKS, THEN
       SQUASH-MERGE. Every required
       check must pass. If the PR
       falls behind main, refresh
       with `gh pr update-branch
       --rebase` — never merge main
       into the branch
       (`required_linear_history:
       true`). Once green:
       `gh pr merge <PR> --squash
       --delete-branch`. If this
       step's `**Deploys:**` line
       names a surface, the merge
       is not the finish line: run
       the Deployed & verified
       check against the target
       environment before
       declaring the step complete.

    5. RETIRE THE BRANCH. Sync
       local: `git switch main &&
       git pull --ff-only origin
       main && git fetch --prune
       origin`. Prune any local
       `[gone]` branches. If the
       step ran in a worktree,
       `git worktree remove <path>`
       FIRST — the branch prune
       fails while the branch is
       checked out there.

    6. DISPOSE OF EVERY FINDING,
       DECLARE COMPLETION, THEN
       NEW CONVERSATION. First
       send every finding this
       step surfaced to its
       destination (Triage rule):
       a note for a later step →
       edit that step's <task>
       block now; spec rot → edit
       this roadmap now; a bug →
       fixed in-step or an issue
       number; a judgement call in
       the diff → the PR body; a
       process lesson → written
       where the next conversation
       reads it. A finding you can
       only describe is NOT
       disposed of, and counts as
       an unmet criterion. Only
       once the PR is merged — and
       `main` therefore carries
       this step's `Complete`
       Status line — every
       acceptance criterion is
       affirmatively met, and every
       finding has a destination,
       say so plainly: end your
       final response with an
       explicit, unhedged
       completion line — verbatim
       shape "Step 5 is
       complete. You can now move
       on to Step 6." That
       line is the LAST line of
       the response. NOTHING
       follows it — no "Follow-ups
       (non-blocking)", "Notes",
       "Next", "worth a glance",
       or suggested improvements.
       A short ledger may PRECEDE
       it, one entry per finding
       naming its destination
       (issue #, file edited, PR
       body) — never an open item.
       If any criterion is unmet
       or any finding has no
       destination, state plainly
       that the step is NOT
       complete, name what is
       outstanding, and omit the
       completion line. "Done"
       means done. Then, for
       phase-boundary hygiene, the
       operator closes this
       session and opens a fresh
       one before Step 6.
  </lifecycle>

  <security>
    Security is a gate on THIS
    step, not a later phase. It is
    AS BINDING as any
    `<requirement>` below. Before
    the Stage-2 commit, this
    step's work MUST pass the
    local, fail-closed security
    gate — the SAME gate wired
    into the pre-commit hook and
    re-run in CI:

    1. SECRET / PII SCAN. No
       credentials, API keys,
       tokens, or real PII in the
       diff (gitleaks /
       detect-secrets or the
       project's equivalent).
       Secrets go in the secrets
       manager, never in source or
       committed env files.

    2. SAST. No new injection,
       unsafe deserialization,
       weak crypto, path
       traversal, or unsafe-eval
       pattern (bandit / semgrep /
       eslint-plugin-security per
       the stack). Suppress a
       finding ONLY with an inline
       justification comment.

    3. DEPENDENCY AUDIT. Any new
       or bumped dependency passes
       the audit (pip-audit / npm
       audit / osv-scanner); no
       known-vulnerable, yanked,
       or typo-squatted package.

    4. SENSITIVE-DATA REVIEW.
       Whatever this step touches
       stays least-privilege,
       encrypted in transit + at
       rest, and out of logs and
       client bundles. If the step
       adds a data path, name how
       PII/secrets are protected.

    A finding blocks the commit —
    fix it in this step, do not
    defer. Do not declare the step
    complete until the gate is
    clean. This is the safety net
    that stops a security issue
    from reaching the branch, the
    PR, or `main`.

    THIS STEP puts the operator's situation on screen. Text from
    NOAA and NWS products (storm names, alert headlines,
    descriptions) is rendered as text by React, never as HTML: no
    `dangerouslySetInnerHTML` anywhere (a static check holds it),
    and links to NHC and NWS open with `rel="noreferrer
    noopener"`. The page never logs an API answer or an error
    carrying one. The fixtures that `scripts/export_api_fixtures.py`
    writes come from the two public landmarks over recorded
    answers, with every geometry coordinate rounded to two
    decimals (the personal-data check's R2 flags pairs with three
    or more), and a coordinate a test writes uses the landmarks or
    at most two decimals. The first-run form sends the point only to the API
    (which sends it to NWS and Nominatim, as `locations add`
    does); the browser-notification switch and the theme live in
    `localStorage` and hold no coordinate. A browser notification
    shows Phase 4's text, which names and never locates. No
    dependency is added.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 5 (Web app MVP). Step 5:
    the dashboard and the pages.

    Current state (as of Phase 5 Step 4):

    - Step 4's shell: React Router 8 routes `/`, `/map`,
      `/storms`, `/alerts`, `/timeline`, `/settings` (placeholders)
      and a not-found page; the navigation; the themes; the
      staleness banner and the footer's notice from
      `/api/health`; `useEventStream`, which invalidates the named
      queries and hands a `notification` event with `display` to a
      callback; the typed client (`api/client.ts`), the query keys
      (`api/keys.ts`), and `api/schema.d.ts`; the nonce for the
      Radix components that inject styles; Vitest with jsdom and
      Testing Library. Read Step 4's PR body for anything it
      changed.
    - The API (Steps 1 to 3): `/api/health` (`next_product_at`,
      `stale`, `heartbeats`, `notice`, `ui`, `corpus`),
      `/api/locations`, `/api/assessments` (per location: level,
      label, actions, rule, evidence, complete or "at least" with
      the missing inputs, official products and context alerts,
      wind readings, storm threats, changes, toggle and its note),
      `/api/storms`, `/api/alerts`, `/api/timeline`,
      `/api/notifications`, `/api/settings`, `/api/disclaimer`, and
      the writes `POST /api/locations`, `PUT
      /api/locations/evacuation`, `POST /api/cycles`, and `POST
      /api/notifications/test`, with their error answers (409, 422,
      429, 502) and events.
    - `status` (`cli/status.py`) is the meaning of every field on
      the level card — read it for how evidence, missing inputs,
      official products, context alerts, threats, and the toggle's
      note are worded, and keep the page's wording consistent with
      it. `docs/ALERT-LADDER.md` holds the levels, triggers, and
      actions. Units follow the official names: the roster's
      intensities in mph and knots as the API names them.
    - Browser notifications: a page on `127.0.0.1` is a secure
      context, so the Notification API is available; permission
      must be requested from a user gesture; when denied, only the
      browser's own settings can re-enable it.

    Files to read (every file before drafting):
    - docs/roadmap/phase05-roadmap.md (Overview and its design
      rationale, Steps 2 to 4, this step, and Steps 6 and 7).
    - docs/api/openapi.json; frontend/ (all of Step 4).
    - src/weatherbot/web/schemas.py and routes/; cli/status.py,
      cli/snapshots.py, cli/notify.py; docs/ALERT-LADDER.md;
      DISCLAIMER.md.
    - tests/cli/cli_support.py (`recorded_services()`,
      `add_landmark()`), scripts/export_openapi.py.
  </context>

  <goal>
    Ship the five pages, the in-page and operating-system
    notifications, the API fixtures and their exporter, and the
    page tests, each page checked at desktop and phone width in
    both themes.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      The pages live in `frontend/src/pages/` (`Dashboard.tsx`,
      `Storms.tsx`, `Alerts.tsx`, `Timeline.tsx`, `Settings.tsx`),
      each with its `*.test.tsx` beside it, and the browser
      notification code in `frontend/src/notifications/notify.ts`.
      Dashboard (`/`): for each location, a level card with the
      level's number, label, and colour (colour never alone), the
      deciding rule and each piece of evidence (product, code,
      issuance, distance), the actions, "at least" with each
      missing input when incomplete, the evacuation toggle's state
      and its note, the assessed instant in UTC and in the
      location's time zone, the snapshot's age, and `notice`; the
      storms that concern it (in cone or not, distance, bearing,
      closest approach, and arrival readings with their source),
      the official products that cover it, and the context alerts
      outside its zones, labelled as never setting the level; the
      next NHC product time; and "check now" (`POST /api/cycles`,
      disabled while a cycle it started runs, its 409 and 429 said
      plainly). A level change announces itself to screen readers
      (an `aria-live` region). With no location, the page shows
      `ESSENTIALS` and a link to Settings' first-run form.
    </requirement>

    <requirement>
      Storms (`/storms`): the snapshot's instant, status, and every
      failed source; each storm's name, classification, intensity,
      movement, pressure, and advisory with its issuance; the
      outlook areas with their chances; drift warnings; and links to
      NHC's pages for each storm and the outlook. Alerts
      (`/alerts`): per location, each NWS alert (event, headline,
      severity, certainty, urgency, effective, expires) marked as
      covering or context, and the NHC segments that cover it.
      Timeline (`/timeline`): a location filter (a native `select`
      or Radix Select with the nonce), and the entries newest
      first — an assessment with its level, rule, completeness, and
      changes, and a notification with its title, kind, level,
      decisions, and deliveries — with "show more" raising the
      limit to the API's maximum.
    </requirement>

    <requirement>
      Settings (`/settings`):

      - Locations: each with its display name, NWS coverage,
        breakpoint span, and evacuation toggle (a Radix Switch,
        `PUT /api/locations/evacuation`, saying the next cycle
        assesses with it, with "check now" beside it). With no
        location, the first-run form: name, latitude, longitude,
        and the zone polygon (none, county, or forecast); client
        validation mirrors the API's bounds; `POST /api/locations`;
        its 409, 422, and 502 shown as messages that repeat no
        coordinate. A second location is added with `weatherbot
        locations add` until Phase 7, and the page says so.
      - Browser notifications: a switch for this browser
        (`localStorage` `weatherbot.notifications`) that asks for
        permission when turned on, the permission's state
        (granted, denied — with how to re-enable it in the browser —
        or not asked), and "send a test notification" (`POST
        /api/notifications/test`), showing each channel's result.
      - Settings: every effective setting with its table, key,
        value, origin, and variable as `serve` loaded them, the
        configuration file's path, a note when the file has changed
        since `serve` started, and how to change one (edit
        `weatherbot.toml` or set the variable, then restart
        `serve`); nothing is editable here.
      - The disclaimer's full text (`/api/disclaimer`), which the
        footer's notice links to, and the third-party licences
        (`/licenses.json`).
    </requirement>

    <requirement>
      Notifications in the page: the shell's `display` callback
      shows an in-page message (a Radix Toast with the title and
      body, the level's colour, and the time) and, when the switch
      is on, permission is granted, and the page is hidden, an
      operating-system notification (`new Notification(title,
      {body, tag: "weatherbot-<id>"})`). A notification event
      without `display` (one another process stored) refreshes the
      lists only.
    </requirement>

    <requirement>
      Every page has loading, empty, and error states (an error
      names the route and the status), works by keyboard with a
      visible focus, uses semantic landmarks and headings, and
      reads at 360 px without horizontal scrolling (tables become
      stacked cards). Instants show in UTC and, where a location is
      involved, its time zone. Distances show to a tenth of a
      kilometre and bearings to a whole degree, as `status` prints
      them.
    </requirement>

    <requirement>
      Fixtures. `scripts/export_api_fixtures.py` (a development
      tool) builds the database over recorded answers with both
      landmarks in a temporary data directory, on the recorded
      answers' fixed clock (`source_support.NOW`) and with the
      committed corpus open, calls every read route — the replay
      routes for one Irma advisory included, which Step 6's map
      tests use — through `httpx.ASGITransport`, and writes each
      answer to
      `frontend/src/test/fixtures/<route>.json` (UTF-8, LF, sorted
      keys), with every id that is random by design (a live
      snapshot's `uuid4`) replaced by a stable placeholder in order
      of appearance, every path (the configuration file's, which
      would carry the user's name) replaced by a placeholder,
      `ui.index_sha256` replaced, and every GeoJSON coordinate
      rounded to two decimals:
      the personal-data check's R2 flags any coordinate pair with
      three or more decimals outside `tests/fixtures/recorded/`
      and `tests/fixtures/replay/`, and NHC's geometry has
      hundreds. `--check` writes nothing and exits 1 when a
      committed fixture is stale, and `tests/web/test_api_fixtures.py`
      runs it. The page tests type the fixtures with the generated
      types (`satisfies`), so an API change that the pages do not
      follow fails `typecheck`.
    </requirement>

    <requirement>
      Tests (Vitest, under `frontend/src/**/*.test.tsx`): each page
      over its fixtures and its empty and error answers; the level
      card's evidence, "at least" and missing inputs, the toggle's
      note, and the notice; "check now"'s disabled state and its 409
      and 429 messages; the first-run form's validation and its
      server errors; the evacuation switch's request; the
      notification switch's permission states (a fake
      `Notification`); the toast for a `display` event and the
      operating-system notification only when hidden, switched on,
      and granted; and that no component uses
      `dangerouslySetInnerHTML`.
    </requirement>

    <requirement>
      Look at every page in a real browser — the dev server over
      `serve`, or the built interface — at 1280 and 360 px wide in
      both themes, and record in the PR body what was checked; fix
      what does not read well. (Step 7's browser job keeps those
      screenshots as artifacts.)
    </requirement>

    <requirement>
      Documents: `CONTRIBUTING.md` (the pages, the fixtures and
      their exporter, and the notification behaviour);
      `CHANGELOG.md`: this step's entries.
    </requirement>

    <requirement>
      Filepath comment: every new TypeScript, Python, and CSS file
      starts with its repo-relative path as a comment; JSON
      fixtures are exempt.
    </requirement>
  </requirements>
</task>
```

### Step 5 acceptance criteria

- The Dashboard shows each location's level card with its rule, evidence,
  actions, missing inputs, toggle, instants, and notice, its storms and alerts,
  the next product time, and "check now"; with no location it shows the
  essentials and the way to setup.
- Storms, Alerts, Timeline, and Settings render their routes' fixtures with
  loading, empty, and error states; the first-run form, the evacuation switch,
  the notification switch, and the test send their requests and show their
  results and errors.
- A `display` event shows an in-page message, and an operating-system
  notification only when switched on, granted, and hidden; an event without
  `display` only refreshes.
- `export_api_fixtures.py --check` passes on both runners (its fixtures hold no
  random id, no path, and no coordinate of three or more decimals), and the page
  tests type their fixtures against the generated types; every page reads at 360
  px in both themes.
- **Deployed & verified:** the first `ci.yml` and `phase-verify.yml` runs on
  `main` after the merge are green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean,
  `eslint-plugin-security` and bandit clean, both audits clean with no
  dependency added — and no component renders product text as HTML, no page logs
  an API answer, and the fixtures hold only landmark coordinates.

---

## Step 6 — The map ✅

**Status:** Complete — PR #66 (2026-10-28)

> **Goal:** Draw what NHC published around the operator's locations. The map
> page (`/map`) wraps Leaflet 1.9.4 directly — `frontend/src/map/` holds
> `useLeafletMap` (one map per mount, torn down cleanly, safe under React's
> strict double mount) and the pure functions that turn `/api/map`'s GeoJSON
> into Leaflet layers — over OpenStreetMap's raster tiles with their attribution
> visible and `referrerPolicy: "strict-origin-when-cross-origin"` on the tile
> layer; it draws each storm's cone, forecast track, and forecast points
> (labelled with time and intensity), the watch and warning segments in NHC's
> colours, the outlook areas by chance, and the locations (points and zone
> polygons) as vector shapes (no image icons), with layer toggles, a legend, a
> fit to the storms and locations, and text-only popups; it follows `snapshot`
> events through `/api/map`'s query; and when `/api/health` says a corpus is
> open, a replay picker loads `/api/replay/{atcf_id}/{advisory}` into the same
> layers, labelled as a replay. `docs/DATA_SOURCES.md`'s basemap section records
> how the page meets the tile policy. Step 7 drives it in a real browser.

**Branch:** `feature/phase05-step6-map`

**Deploys:** nothing beyond merge — the operator's copy keeps Step 1's build
until Step 7 redeploys it. GitHub Actions → the first `ci.yml` and
`phase-verify.yml` runs on `main` must be green.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.18/1M           | $4.00/1M*          | $8.46/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.56/1M           | $6.02/1M           | $4.00/1M*          |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | XHigh              | XHigh              |
|               | AA       | not measured       | 51                 | 52.4               |
|               | Price    | $2.40/1M*          | $4.00/1M           | $16.36/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out) ×
the tokens the model uses at that level; * token use not yet measured, a typical
model's at that level assumed.

**Conversation:** New

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that
column's usage pool reads `tight` or `exhausted`, run the first of its Runner-up
and Backup whose pool has headroom; on a `tight` pool an option marked ↓ (the
Pick one level lower) also runs. With none, a `tight` column runs the Cost
column and an `exhausted` one its Backup.

> Settings updated 2026-10-25 (rerank): each column's Runner-up and Backup now come from makers other than its Pick; every Pick is unchanged.
> Ran 2026-10-28: Balanced Pick — Gemini 4 Argon · Effort High · Thinking On on Antigravity. Selected by the **Runs:** rule (Google AI Pro pool reads headroom).

**Model rationale:** Step 6 is coding with a knowledge secondary category:
Leaflet layers for NHC's products, drawn faithfully to their CRS and continuous
across the antimeridian, the tile server's usage policy under a strict
Content-Security-Policy, NHC's conventional colours, and a replay mode over the
corpus. Its overall complexity is High — a stateful map inside React's
lifecycle, geometry that must never be transformed or mislabelled, and a third
party's policy to honour — and it is not novel: this roadmap fixes the layers,
the colours' meaning, the tile settings, and the replay routes. The columns
differ in depth and maker: Balanced runs Gemini 4 Argon on Antigravity at Effort
High with thinking on; Quality runs Opus 5.5 on Claude Code at Effort XHigh
(always thinking, so no Thinking field) for the closest audit of the geometry
handling; Cost moves it to GPT-6.1 Sol on Codex at Intelligence High. Google AI
Pro, the claude.ai Max subscription, and ChatGPT Pro 5x fund the three
platforms, so each column costs nothing at the margin while its pool has
headroom; when a column's pool reads `tight` or `exhausted`, the **Runs:** rule
moves the step to that column's Runner-up or Backup. The conversation is new per
phase-boundary hygiene.

```xml
<task>
  <lifecycle>
    This step MUST follow all six
    stages, in order. Stages 1, 3,
    4, 5, 6 are AS BINDING as any
    `<requirement>` below. Do not
    emit the Stage 6 completion
    line until the PR is merged and
    every acceptance criterion for
    this step is affirmatively met.

    1. CREATE THE BRANCH. Before
       any Read / Edit / Bash, run
       `git checkout -b
       feature/phase05-step6-map`
       from a clean, up-to-date
       `main`. The exact branch
       name is in this step's
       `**Branch:**` line above.
       If the Worktree rule
       applies, use `git fetch
       origin && git worktree add
       -b <branch> <path>
       origin/main` instead, then
       bootstrap the worktree.

    2. WORK ON THE BRANCH. All
       commits land here. `main`
       is protected with
       `enforce_admins: true` —
       direct pushes will be
       rejected.

    3. OPEN THE PR, THEN MARK THE
       STEP. `gh pr create --base
       main --head <branch>` with a
       Conventional Commits title
       and a body that references
       this roadmap step and its
       acceptance criteria. One PR
       per step. Then, in this
       roadmap file: set this
       step's `**Status:**` line
       (directly under its heading)
       to `Complete — PR #<n>
       (<YYYY-MM-DD>)`, append ` ✅`
       to the step's `## Step`
       heading, and set its
       Summary Table Status cell to
       `Complete — PR #<n>`. Commit
       that edit on the step
       branch and push — the PR
       carries its own completion
       mark, so the roadmap on
       `main` marks this step
       complete exactly when the PR
       merges (Status rule). Same
       commit: on the phase's first
       step, set this roadmap's
       phase-level `**Status:**`
       (under its title) and the
       parent project roadmap's
       Phase 5 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 5`
       heading.

    4. WAIT FOR GREEN CHECKS, THEN
       SQUASH-MERGE. Every required
       check must pass. If the PR
       falls behind main, refresh
       with `gh pr update-branch
       --rebase` — never merge main
       into the branch
       (`required_linear_history:
       true`). Once green:
       `gh pr merge <PR> --squash
       --delete-branch`. If this
       step's `**Deploys:**` line
       names a surface, the merge
       is not the finish line: run
       the Deployed & verified
       check against the target
       environment before
       declaring the step complete.

    5. RETIRE THE BRANCH. Sync
       local: `git switch main &&
       git pull --ff-only origin
       main && git fetch --prune
       origin`. Prune any local
       `[gone]` branches. If the
       step ran in a worktree,
       `git worktree remove <path>`
       FIRST — the branch prune
       fails while the branch is
       checked out there.

    6. DISPOSE OF EVERY FINDING,
       DECLARE COMPLETION, THEN
       NEW CONVERSATION. First
       send every finding this
       step surfaced to its
       destination (Triage rule):
       a note for a later step →
       edit that step's <task>
       block now; spec rot → edit
       this roadmap now; a bug →
       fixed in-step or an issue
       number; a judgement call in
       the diff → the PR body; a
       process lesson → written
       where the next conversation
       reads it. A finding you can
       only describe is NOT
       disposed of, and counts as
       an unmet criterion. Only
       once the PR is merged — and
       `main` therefore carries
       this step's `Complete`
       Status line — every
       acceptance criterion is
       affirmatively met, and every
       finding has a destination,
       say so plainly: end your
       final response with an
       explicit, unhedged
       completion line — verbatim
       shape "Step 6 is
       complete. You can now move
       on to Step 7." That
       line is the LAST line of
       the response. NOTHING
       follows it — no "Follow-ups
       (non-blocking)", "Notes",
       "Next", "worth a glance",
       or suggested improvements.
       A short ledger may PRECEDE
       it, one entry per finding
       naming its destination
       (issue #, file edited, PR
       body) — never an open item.
       If any criterion is unmet
       or any finding has no
       destination, state plainly
       that the step is NOT
       complete, name what is
       outstanding, and omit the
       completion line. "Done"
       means done. Then, for
       phase-boundary hygiene, the
       operator closes this
       session and opens a fresh
       one before Step 7.
  </lifecycle>

  <security>
    Security is a gate on THIS
    step, not a later phase. It is
    AS BINDING as any
    `<requirement>` below. Before
    the Stage-2 commit, this
    step's work MUST pass the
    local, fail-closed security
    gate — the SAME gate wired
    into the pre-commit hook and
    re-run in CI:

    1. SECRET / PII SCAN. No
       credentials, API keys,
       tokens, or real PII in the
       diff (gitleaks /
       detect-secrets or the
       project's equivalent).
       Secrets go in the secrets
       manager, never in source or
       committed env files.

    2. SAST. No new injection,
       unsafe deserialization,
       weak crypto, path
       traversal, or unsafe-eval
       pattern (bandit / semgrep /
       eslint-plugin-security per
       the stack). Suppress a
       finding ONLY with an inline
       justification comment.

    3. DEPENDENCY AUDIT. Any new
       or bumped dependency passes
       the audit (pip-audit / npm
       audit / osv-scanner); no
       known-vulnerable, yanked,
       or typo-squatted package.

    4. SENSITIVE-DATA REVIEW.
       Whatever this step touches
       stays least-privilege,
       encrypted in transit + at
       rest, and out of logs and
       client bundles. If the step
       adds a data path, name how
       PII/secrets are protected.

    A finding blocks the commit —
    fix it in this step, do not
    defer. Do not declare the step
    complete until the gate is
    clean. This is the safety net
    that stops a security issue
    from reaching the branch, the
    PR, or `main`.

    THIS STEP draws the operator's locations on a map whose tiles
    come from a third party. The browser asks
    `tile.openstreetmap.org` for the tiles the view shows — which
    tells that server roughly where the map is looking, as every
    map page does; the register records it, and no other request
    leaves the page (the policy's `img-src` names only that host).
    The tile layer never prefetches beyond the view, keeps
    Leaflet's tile cache, and sends the Referer the policy
    requires. Popups and tooltips are built from text nodes —
    storm names, segment names, and location names never reach
    `innerHTML` or a `DivIcon`'s HTML. Map tests use the exported
    fixtures (coordinates rounded to two decimals) and literals
    with at most two decimals or the landmarks. Leaflet
    (BSD-2-Clause) and its PNGs land in `licenses.json`; no
    react-leaflet. No other dependency is added.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 5 (Web app MVP). Step 6:
    the map.

    Current state (as of Phase 5 Step 5):

    - `/api/map` (Step 2): the latest snapshot's id and instant;
      per storm its cone (Feature), forecast track (Feature),
      forecast points (each with its instant, intensity, and
      classification), and watch-warning segments (each with its
      type and breakpoint names); the outlook areas (basin and
      chances); and the locations (points, and zone polygons where
      stored). Every geometry carries `crs` (`EPSG:4326` live,
      `native` replayed); a geometry crossing the antimeridian
      comes unwrapped. `/api/replay` and
      `/api/replay/{atcf_id}/{advisory}` answer in the same shape
      when `serve --corpus DIR` opened a corpus, and
      `/api/health`'s `corpus` says so. `snapshot` events
      invalidate the `map` key.
    - Steps 4 and 5: the shell, the query keys, the fixtures
      (`frontend/src/test/fixtures/map.json` among them, rounded to
      two decimals), the nonce, and the policy: `img-src 'self'
      data: https://tile.openstreetmap.org`, with
      `Referrer-Policy: strict-origin-when-cross-origin`.
    - Probed on 2026-10-24 (Overview, "Design rationale"):
      Leaflet 1.9.4 sets element styles only through the CSSOM
      (no `style` attribute, no `<style>` element), so it runs
      under `style-src 'self'`; it needs `img-src data:` for its
      placeholder GIF and Vite's inlined PNGs; its default marker
      icon resolves its image path from CSS and breaks once Vite
      hashes or inlines the PNGs (Leaflet issue 4968); and
      `TileLayer`'s `referrerPolicy` option defaults to none in
      1.9.4 (the fix is merged but unreleased). The tile policy
      requires visible attribution ("© OpenStreetMap
      contributors"), a Referer from web pages (`no-referrer` and
      `same-origin` are refused), caching per the tiles' headers,
      and no bulk download or prefetch; its enforcement runs as a
      brownout, and nothing official says whether a loopback
      Referer is accepted (Overview: the fallback is a Phase 7
      tile proxy).
    - Read on 2026-10-25: react-leaflet 5 and `@react-leaflet/core`
      are licensed Hippocratic-2.1, which is not OSI-approved;
      Leaflet is BSD-2-Clause; Leaflet 2.0 is an alpha.
    - NHC's conventional colours: Hurricane Warning red, Hurricane
      Watch pink, Tropical Storm Warning blue, Tropical Storm Watch
      yellow; the outlook's chances low yellow, medium orange, high
      red; the cone a light fill with a darker outline. Read the
      segment and outlook models' fields for the codes the API
      carries.

    Files to read (every file before drafting):
    - docs/roadmap/phase05-roadmap.md (Overview and its design
      rationale, Steps 2, 4, and 5, this step, and Step 7).
    - docs/api/openapi.json; frontend/ (all);
      src/weatherbot/web/map_layers.py and routes/.
    - docs/DATA_SOURCES.md ("OpenStreetMap: basemap and geocoding"
      and the register's `basemap-osm-tiles` row).
  </context>

  <goal>
    Ship the map page on Leaflet, its pure layer functions, the
    tile layer that honours the policy, the replay picker, the
    register amendment, and the map's tests.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Add `leaflet` 1.9.4 and `@types/leaflet` 1.9.22 (exact
      versions; never react-leaflet), and give
      `.github/dependabot.yml`'s npm entry an `ignore` rule for
      `leaflet` at 2 and above (an alpha today).
      `frontend/src/map/useLeafletMap.ts` creates
      one `L.map` in a container ref on mount and removes it on
      unmount (React's strict double mount must leave exactly one
      map and no leaked listener); `frontend/src/map/layers.ts`
      holds pure functions — GeoJSON in, Leaflet layer options,
      styles, legends, bounds, and popup text out — that the page
      and the tests share. Points and locations are vector circle
      markers, so Leaflet's default-icon path never matters.
      Leaflet's stylesheet is imported once.
    </requirement>

    <requirement>
      The tile layer: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`
      with `maxZoom` 19, `referrerPolicy:
      "strict-origin-when-cross-origin"`, `crossOrigin` left unset,
      no `keepBuffer` above Leaflet's default, and the attribution
      "© OpenStreetMap contributors" linking to
      openstreetmap.org/copyright, always visible (never behind a
      toggle or covered at phone width).
    </requirement>

    <requirement>
      The layers, each with a toggle (a native checkbox group, all
      on by default) and a legend: per storm, the cone (light fill,
      outline), the forecast track (a line), and the forecast
      points (circle markers coloured by classification, each with
      a tooltip of its instant in UTC and the location's time zone
      and its intensity); the watch and warning segments in NHC's
      colours by type, each with its breakpoint names; the outlook
      areas coloured by chance with their basin and two- and
      seven-day chances; and the locations (circle markers, and
      their zone polygons) with their names. The view fits the
      storms and the locations on first load and after the user
      asks ("fit"), never on its own after the user has moved the
      map; with nothing to fit, it shows the Atlantic basin from a
      centre and zoom written as whole numbers (no coordinate
      literal of three or more decimals, which the personal-data
      check would flag). Coordinates are drawn as the API gives
      them: no
      transformation, no rounding, and the layer's `crs` shown in
      its popup. The map follows the `map` query, so a `snapshot`
      event redraws it.
    </requirement>

    <requirement>
      Replay: when `/api/health`'s `corpus` is true, a panel with a
      storm `select` and an advisory `select` (native elements)
      loads `/api/replay/{atcf_id}/{advisory}` into the same layers
      with a banner "Replay: <storm> advisory <n>, issued <instant>
      — not live", fitting the view to the replayed layers, and
      "back to live" restores `/api/map`. The replay query is keyed
      apart from the live one, so no event overwrites a replay on
      screen. A corpus is open when `serve --corpus DIR` names one
      or the `[web] corpus` setting does (the scheduled `serve`
      reads the setting; Step 2).
    </requirement>

    <requirement>
      The map page reads at phone width (the map fills the width,
      the toggles and legend fold below it) and in both themes
      (tiles stay as served; the controls follow the theme).
    </requirement>

    <requirement>
      `docs/DATA_SOURCES.md`, the basemap bullet of "OpenStreetMap:
      basemap and geocoding", dated the step's date: the page loads
      tiles directly with `referrerPolicy:
      "strict-origin-when-cross-origin"` and the same response
      header, keeps the attribution visible, prefetches nothing,
      and relies on the browser's cache; a loopback Referer's
      acceptance is unproven, and the fallback (a server-side
      caching proxy with the project's User-Agent) belongs to
      Phase 7. The register's header and its row's columns stay as
      they are (Phase 1's checks 31 and 32 read them); only the
      row's `Verified` date may move, as an ISO date.
    </requirement>

    <requirement>
      Tests (Vitest; no network): `layers.ts` over the fixture —
      every storm's cone, track, points, and segments, the outlook
      areas, and the locations become the expected layers with
      NHC's colours, legends, and popup text; a two-decimal
      Central Pacific geometry crossing the antimeridian keeps
      continuous longitudes; bounds cover storms and locations;
      popup text is text (a name holding `<b>` renders literally).
      `MapView` mounts in jsdom and the tests assert the layers
      through Leaflet's API (`eachLayer`), not through pixels; the
      toggles add and remove layers; the replay panel appears only
      with a corpus, loads an advisory, shows the banner, fits the
      view, and returns to live; strict double mount leaves one
      map. The tests live in `frontend/src/map/` beside the code
      (`layers.test.ts`, `MapView.test.tsx`) and read Step 5's
      replay fixture. Step 7's browser smoke covers real rendering,
      with the tiles answered locally; once, in a real browser on
      the operator's machine, confirm OpenStreetMap's tiles load
      under the policy, and record it in the PR body.
    </requirement>

    <requirement>
      Documents: `CONTRIBUTING.md` ("The map": the layers, the tile
      policy and its fallback, replay with `serve --corpus DIR` or
      the `[web] corpus` setting);
      `README.md`'s Commands line for `serve --corpus DIR` says it
      shows the corpus on the map; `CHANGELOG.md`: this step's
      entries.
    </requirement>

    <requirement>
      Filepath comment: every new TypeScript and CSS file starts
      with its repo-relative path as a comment.
    </requirement>
  </requirements>
</task>
```

### Step 6 acceptance criteria

- The map page draws the cones, forecast tracks and points, watch and warning
  segments in NHC's colours, outlook areas, and the locations from `/api/map`,
  each layer toggleable and in the legend, with coordinates exactly as served,
  and redraws on a `snapshot` event.
- The tile layer sends `strict-origin-when-cross-origin`, the attribution stays
  visible at every width, and nothing but tiles from `tile.openstreetmap.org`
  leaves the page.
- With a corpus, the replay panel loads a replayed advisory into the same layers
  under a "not live" banner and returns to live; without one, it is absent.
- Strict double mount leaves one map; popups render names as text; a Central
  Pacific geometry stays continuous; `docs/DATA_SOURCES.md` records how the page
  meets the tile policy.
- One manual check in a real browser on the operator's machine shows
  OpenStreetMap's tiles loading under the policy, recorded in the PR body.
- **Deployed & verified:** the first `ci.yml` and `phase-verify.yml` runs on
  `main` after the merge are green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean,
  `eslint-plugin-security` and bandit clean, both audits clean, and
  `licenses:check` passing with Leaflet added — and no product or location text
  reaches `innerHTML`, and the map's only third-party request is the tiles.

---

## Step 7 — The browser smoke, idle cost, and the operator's dashboard ✅

**Status:** Complete — PR #70 (2026-10-29)

> **Goal:** Prove the whole chain in a real browser, measure what it costs to
> leave open, and put it on the operator's machine. `scripts/serve_demo.py` runs
> the `serve` process's monitor and web server in a temporary data directory
> with both landmarks, every request answered by the recorded fixtures through
> respx, the replay corpus open, and a switch that serves the next advisory with
> a synthetic Hurricane Warning (Phase 4's simulation); `frontend/e2e/` holds
> the Playwright smoke (Chromium), which loads the dashboard, flips the switch,
> presses "check now", and sees the Miami-Dade landmark's card reach level 5
> through the event stream without a reload, draws a replayed Irma advisory's
> cone and track with the location markers, captures desktop and phone
> screenshots in both themes, and finds no landmark coordinate and no policy
> violation in the console; a `browser` job runs it in CI and joins the gate;
> `scripts/measure_idle.py` holds the server's process and a page's main thread
> to under 0.5 percent of one core over ten idle minutes and prints both
> numbers; and the operator's installed copy, rebuilt with the interface, serves
> the dashboard under `\Weatherbot\serve`.

**Branch:** `feature/phase05-step7-browser-smoke`

**Deploys:** the operator's machine → with the operator's yes, the interface is
built in the checkout (`npm ci`, `npm run build`); then, away from 25 past the
hour, `\Weatherbot\serve` is ended, the installed copy is reinstalled from the
checkout, and the task is run again: `/api/health` must report `ui.present` with
this build's `index_sha256`, `doctor` must pass `web`, and the operator opens
`http://127.0.0.1:8765/` and confirms the dashboard. GitHub Actions → the
`browser` job joins `gate`; the first `ci.yml` and `phase-verify.yml` runs on
`main` must be green.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.18/1M           | $4.00/1M*          | $8.46/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.56/1M           | $6.02/1M           | $4.00/1M*          |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6.1 Sol**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | High               | XHigh              |
|               | AA       | not measured       | 50.2               | 51                 |
|               | Price    | $2.40/1M*          | $2.18/1M           | $4.00/1M           |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out) ×
the tokens the model uses at that level; * token use not yet measured, a typical
model's at that level assumed.

**Conversation:** New

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that
column's usage pool reads `tight` or `exhausted`, run the first of its Runner-up
and Backup whose pool has headroom; on a `tight` pool an option marked ↓ (the
Pick one level lower) also runs. With none, a `tight` column runs the Cost
column and an `exhausted` one its Backup.

> Ran 2026-10-29: Balanced Pick — Gemini 4 Argon · Effort High · Thinking On on Antigravity. Selected by the **Runs:** rule (Google AI Pro pool reads headroom).

> Settings updated 2026-10-29 (rerank): was Gemini 4 Argon · High. Every Pick is unchanged; roadmodel 0.2.100 changes two Backups: Balanced's GPT-6.1 Sol now runs at High (was XHigh), and Quality's is GPT-6.1 Sol · XHigh (was GPT-6 Astra · XHigh), at a quarter of its price.

> Settings updated 2026-10-25 (rerank): each column's Runner-up and Backup now come from makers other than its Pick; every Pick is unchanged.

**Model rationale:** Step 7 is coding with an agentic secondary category: a
demonstration server built on Phase 4's recorded-answer simulation, a Playwright
smoke that waits on a live event, CPU measurement on both sides of the
connection, a CI job with a browser, and an on-machine deployment. Its overall
complexity is High — timing that must not flake, a reload that must provably not
happen, console capture for privacy and policy, and a measurement whose method
must not disturb what it measures — and it is not novel: this roadmap fixes what
the smoke drives, what it asserts, the idle budget, and the deployment. The
columns differ in depth and maker: Balanced runs Gemini 4 Argon on Antigravity
at Effort High with thinking on; Quality runs Opus 5.5 on Claude Code at Effort
XHigh (always thinking, so no Thinking field) for the closest audit of the
smoke's assertions; Cost moves it to GPT-6.1 Sol on Codex at Intelligence High.
GPT-6.1 Sol on Codex backs up both Balanced (at Intelligence High) and Quality
(at XHigh). Google AI Ultra, the claude.ai Max subscription, and ChatGPT Pro
fund the three platforms, so each column costs nothing at the margin while its
pool has headroom; when a column's pool reads `tight` or `exhausted`, the
**Runs:** rule moves the step to that column's Runner-up or Backup. The
conversation is new per phase-boundary hygiene.

```xml
<task>
  <lifecycle>
    This step MUST follow all six
    stages, in order. Stages 1, 3,
    4, 5, 6 are AS BINDING as any
    `<requirement>` below. Do not
    emit the Stage 6 completion
    line until the PR is merged and
    every acceptance criterion for
    this step is affirmatively met.

    1. CREATE THE BRANCH. Before
       any Read / Edit / Bash, run
       `git checkout -b
       feature/phase05-step7-browser-smoke`
       from a clean, up-to-date
       `main`. The exact branch
       name is in this step's
       `**Branch:**` line above.
       If the Worktree rule
       applies, use `git fetch
       origin && git worktree add
       -b <branch> <path>
       origin/main` instead, then
       bootstrap the worktree.

    2. WORK ON THE BRANCH. All
       commits land here. `main`
       is protected with
       `enforce_admins: true` —
       direct pushes will be
       rejected.

    3. OPEN THE PR, THEN MARK THE
       STEP. `gh pr create --base
       main --head <branch>` with a
       Conventional Commits title
       and a body that references
       this roadmap step and its
       acceptance criteria. One PR
       per step. Then, in this
       roadmap file: set this
       step's `**Status:**` line
       (directly under its heading)
       to `Complete — PR #<n>
       (<YYYY-MM-DD>)`, append ` ✅`
       to the step's `## Step`
       heading, and set its
       Summary Table Status cell to
       `Complete — PR #<n>`. Commit
       that edit on the step
       branch and push — the PR
       carries its own completion
       mark, so the roadmap on
       `main` marks this step
       complete exactly when the PR
       merges (Status rule). Same
       commit: on the phase's first
       step, set this roadmap's
       phase-level `**Status:**`
       (under its title) and the
       parent project roadmap's
       Phase 5 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 5`
       heading.

    4. WAIT FOR GREEN CHECKS, THEN
       SQUASH-MERGE. Every required
       check must pass. If the PR
       falls behind main, refresh
       with `gh pr update-branch
       --rebase` — never merge main
       into the branch
       (`required_linear_history:
       true`). Once green:
       `gh pr merge <PR> --squash
       --delete-branch`. If this
       step's `**Deploys:**` line
       names a surface, the merge
       is not the finish line: run
       the Deployed & verified
       check against the target
       environment before
       declaring the step complete.

    5. RETIRE THE BRANCH. Sync
       local: `git switch main &&
       git pull --ff-only origin
       main && git fetch --prune
       origin`. Prune any local
       `[gone]` branches. If the
       step ran in a worktree,
       `git worktree remove <path>`
       FIRST — the branch prune
       fails while the branch is
       checked out there.

    6. DISPOSE OF EVERY FINDING,
       DECLARE COMPLETION, THEN
       NEW CONVERSATION. First
       send every finding this
       step surfaced to its
       destination (Triage rule):
       a note for a later step →
       edit that step's <task>
       block now; spec rot → edit
       this roadmap now; a bug →
       fixed in-step or an issue
       number; a judgement call in
       the diff → the PR body; a
       process lesson → written
       where the next conversation
       reads it. A finding you can
       only describe is NOT
       disposed of, and counts as
       an unmet criterion. Only
       once the PR is merged — and
       `main` therefore carries
       this step's `Complete`
       Status line — every
       acceptance criterion is
       affirmatively met, and every
       finding has a destination,
       say so plainly: end your
       final response with an
       explicit, unhedged
       completion line — verbatim
       shape "Step 7 is
       complete. You can now move
       on to Step 8." That
       line is the LAST line of
       the response. NOTHING
       follows it — no "Follow-ups
       (non-blocking)", "Notes",
       "Next", "worth a glance",
       or suggested improvements.
       A short ledger may PRECEDE
       it, one entry per finding
       naming its destination
       (issue #, file edited, PR
       body) — never an open item.
       If any criterion is unmet
       or any finding has no
       destination, state plainly
       that the step is NOT
       complete, name what is
       outstanding, and omit the
       completion line. "Done"
       means done. Then, for
       phase-boundary hygiene, the
       operator closes this
       session and opens a fresh
       one before Step 8.
  </lifecycle>

  <security>
    Security is a gate on THIS
    step, not a later phase. It is
    AS BINDING as any
    `<requirement>` below. Before
    the Stage-2 commit, this
    step's work MUST pass the
    local, fail-closed security
    gate — the SAME gate wired
    into the pre-commit hook and
    re-run in CI:

    1. SECRET / PII SCAN. No
       credentials, API keys,
       tokens, or real PII in the
       diff (gitleaks /
       detect-secrets or the
       project's equivalent).
       Secrets go in the secrets
       manager, never in source or
       committed env files.

    2. SAST. No new injection,
       unsafe deserialization,
       weak crypto, path
       traversal, or unsafe-eval
       pattern (bandit / semgrep /
       eslint-plugin-security per
       the stack). Suppress a
       finding ONLY with an inline
       justification comment.

    3. DEPENDENCY AUDIT. Any new
       or bumped dependency passes
       the audit (pip-audit / npm
       audit / osv-scanner); no
       known-vulnerable, yanked,
       or typo-squatted package.

    4. SENSITIVE-DATA REVIEW.
       Whatever this step touches
       stays least-privilege,
       encrypted in transit + at
       rest, and out of logs and
       client bundles. If the step
       adds a data path, name how
       PII/secrets are protected.

    A finding blocks the commit —
    fix it in this step, do not
    defer. Do not declare the step
    complete until the gate is
    clean. This is the safety net
    that stops a security issue
    from reaching the branch, the
    PR, or `main`.

    THIS STEP runs a browser against a server and deploys to the
    operator's machine. `scripts/serve_demo.py` answers every
    request from the recorded fixtures through respx and refuses
    any other, in a temporary data directory, with the two public
    landmarks only, and binds `127.0.0.1`; the smoke and the idle
    measurement never touch the operator's database or locations,
    and every spec answers tile requests with a local blank image,
    so neither calls OpenStreetMap's servers. The console scan
    uses the landmarks' renderings (and a
    standalone-decimal pattern) so a leak fails the job without
    printing a value. CI artifacts hold screenshots and
    Playwright traces of the demonstration data only. The
    deployment reads the operator's service only through
    `/api/health` and `doctor`, and the operator, not the agent,
    looks at the operator's dashboard. New development
    dependencies — `@playwright/test` (npm) and `psutil` with
    `types-psutil` (the dev group) — pass both audits; the
    `upload-artifact` action is pinned to a full SHA with a
    version comment.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 5 (Web app MVP). Step 7:
    the browser smoke, idle cost, and the operator's dashboard.

    Current state (as of Phase 5 Step 6):

    - Steps 1 to 6: `serve` hosts the guarded API, the event
      stream, the writes, and the built interface (Dashboard,
      Map, Storms, Alerts, Timeline, Settings); `serve --corpus
      DIR` opens a replay corpus for the map; the `frontend` and
      `package` jobs build, test, and ship the interface, and
      `scripts/smoke_installed_web.py` proves an installed wheel
      serves it. Read the six PR bodies for anything they changed.
    - `scripts/simulate_advisory.py` (Phase 4 Step 5) starts the
      `serve` schedule in a temporary data directory with both
      landmarks (Miami-Dade stored as "simulated Miami-Dade"),
      every request answered by recorded fixtures through respx,
      and the roster watch at its 1-minute minimum; after the
      startup cycle it serves the next advisory and a synthetic
      Hurricane Warning on the landmark's forecast zone (FLZ173),
      and the next cycle stores a level-5 escalation. Phase 4's
      check 38 and `tests/scripts/test_simulate_advisory.py` read
      it, so it keeps its behaviour and those tokens.
    - Playwright 1.64.1 (`@playwright/test`) needs Node 20 or
      later; `webServer` starts a command and waits for a URL;
      the Chrome DevTools Protocol's `Performance.getMetrics`
      reports `TaskDuration`, the main thread's task time.
    - The idle budget (Overview, "Design rationale"): under 0.5
      percent of one core each for the server process and the
      page's main thread, over ten idle minutes with one page
      open; uvicorn's main loop wakes every 100 ms, the stream
      pings after 15 idle seconds, and the watcher reads every 10
      seconds.
    - The operator's machine runs the installed copy of Step 1's
      build under `\Weatherbot\serve`, and `\Weatherbot\check` runs
      `check --once --if-stale` at 25 past every hour, alarming and
      starting `serve` when the monitor is not fresh; `uv tool
      install --reinstall --from <checkout> weatherbot` packs
      whatever `src/weatherbot/web/static/` holds, so the interface
      is built first.

    Files to read (every file before drafting):
    - docs/roadmap/phase05-roadmap.md (Overview and its design
      rationale, Steps 1 to 6, this step, and Step 8).
    - scripts/simulate_advisory.py,
      tests/scripts/test_simulate_advisory.py,
      scripts/smoke_installed_web.py, cli/serve.py,
      src/weatherbot/web/ (all), frontend/ (all).
    - .github/workflows/ci.yml, pyproject.toml, README.md,
      CONTRIBUTING.md, CHANGELOG.md.
  </context>

  <goal>
    Ship the demonstration server, the Playwright smoke and its
    CI job, the idle measurement with its numbers, the README's
    dashboard section, and the operator's deployment.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `scripts/serve_demo.py` (a development tool): runs the
      `serve` process's monitor and web server through
      `cli/serve.py`'s own loop function (Step 3), handing it the
      demonstration's fetcher and clock as the tests do, in a
      temporary data directory with both landmarks stored
      (Miami-Dade as "simulated Miami-Dade"), every request
      answered by the recorded fixtures through respx (all others
      refused), `--port` (default 8799), `--corpus DIR`,
      `--roster-interval-minutes` (1 for the smoke; the default
      keeps production's intervals for the idle measurement), and
      `--switch-file PATH`: once that file exists, the roster
      serves the next advisory and the forecast zone the synthetic
      Hurricane Warning, reusing Phase 4's simulation (factor the
      shared answers into a module both scripts import if that is
      cleaner). `simulate_advisory.py` keeps its behaviour, its
      test, what Phase 4's check 38 reads in the file itself (a
      `SIMULATED_MIAMI` constant assigned "simulated Miami-Dade",
      `main`, `TemporaryDirectory`, and a `recorded_services()`
      call), and its final stdout line, in which Phase 4's V5.4
      probe looks for `simulated Miami-Dade`, `level=5`,
      `escalation=True`, and `toast=delivered`. `serve_demo.py`
      prints its process id and address and one line per roster
      poll and per cycle, removes its temporary directory on exit,
      and writes nothing in the checkout.
    </requirement>

    <requirement>
      `frontend/playwright.config.ts` (Chromium only; `webServer`
      runs `serve_demo.py` through `uv run` and waits for
      `/api/health`, unless `E2E_BASE_URL` names a running
      server) and `frontend/e2e/`:

      - `dashboard.spec.ts`: the dashboard shows both landmarks'
        cards and the footer's notice; it opens the theme menu (a
        Radix DropdownMenu, whose injected `<style>` passes only
        with the nonce), picks dark, and returns to system; it
        marks the page (a
        `window` property), creates the switch file, presses
        "check now", and within 90 seconds sees "simulated
        Miami-Dade" at level 5, "Hurricane Warning", with the mark
        still set (no reload) and the in-page notification shown.
      - `map.spec.ts`: on `/map`, the replay panel loads Irma
        (`AL112017`) at a mid-storm advisory, and the map holds the
        cone's and the track's SVG paths, the forecast points, and
        both location markers, under the "not live" banner.
      - `screens.spec.ts`: the dashboard and the map at 1280 x 800
        and 360 x 740, in light and dark, saved as screenshots.
      - In every spec, `idle.spec.ts` included: requests to
        `https://tile.openstreetmap.org/**` are answered by a route
        with a blank 256 x 256 PNG kept in `frontend/e2e/`, so no
        spec loads a real tile or depends on the tile server, and a
        request to any other origin than the server's fails the
        test; console messages and page errors are collected, along
        with `securitypolicyviolation` events
        (registered by an init script); each test fails on any
        policy violation, any page error, or any console text
        holding a landmark coordinate's rendering (the forms
        `tests/cli/test_cli_privacy.py` checks).
      - `idle.spec.ts`, tagged `@idle` and excluded from the
        default run: after the page settles for 30 seconds, it
        reads `TaskDuration` through a DevTools Protocol session,
        waits 600 seconds, reads it again, and writes the
        difference to a JSON file the measurement reads.

      `package.json` gains `@playwright/test` 1.64.1 (exact) and
      the scripts `e2e` and `e2e:idle`.
    </requirement>

    <requirement>
      `scripts/measure_idle.py` (a development tool, with `psutil`
      and `types-psutil` added to the dev group): builds nothing,
      starts `serve_demo.py` at production intervals, runs
      `e2e:idle` against it (`E2E_BASE_URL`), samples the server
      process's CPU time (user plus system) through `psutil` at the
      same window's start and end, prints both shares of one core
      with the window and the number of roster polls and cycles
      `serve_demo.py` reported inside it (so a cycle that lands in
      the window is visible beside the numbers), and exits 1 when
      either share is 0.5 percent or more. Run it on the
      operator's machine and record the numbers in the PR body
      (Step 8's QA findings carry them). Both scripts
      start their subprocesses as the existing scripts do (an
      absolute executable from `shutil.which`, an argument list,
      never a shell, a justified `# nosec`), because bandit scans
      `scripts/`.
    </requirement>

    <requirement>
      CI: a `browser` job on `ubuntu-latest` — checkout, setup-uv,
      `uv sync --locked`, setup-node (pinned as in Step 4), `npm
      ci`, `npm run build`, `npx playwright install --with-deps
      chromium`, and `npm run e2e` — uploading the screenshots
      always and the traces on failure through `actions/
      upload-artifact` pinned to its latest release's full SHA with
      a version comment; it joins `gate`'s `needs`. The idle spec
      does not run in CI (ten minutes per run); `--post` runs it.
    </requirement>

    <requirement>
      Documents: `README.md` gains a dashboard section (what each
      page shows, the address, `serve --no-open`, `serve --corpus
      DIR` for replay on the map, browser notifications, and that
      it is informational only) while `## Commands` keeps every
      line Phases 3 and 4 need; `CONTRIBUTING.md` ("The browser
      smoke": `serve_demo.py`, the specs, the idle measurement and
      its budget); `CHANGELOG.md`: this step's entries.
    </requirement>

    <requirement>
      Deploy, with the operator's yes for each action: in the
      checkout on `main`, `npm ci` and `npm run build`; then, in
      this order and well clear of 25 past the hour (when
      `\Weatherbot\check` would find `serve` stopped, alarm, and
      start it in the middle of the reinstall):
      `schtasks /End /TN \Weatherbot\serve`;
      `uv tool install --reinstall --from <checkout> weatherbot`
      (Windows keeps a running tool's files locked, so `serve`
      stops first); and `schtasks /Run /TN \Weatherbot\serve`. Then
      `/api/health` reports `ui.present` true and an
      `index_sha256` equal to the first 12 hex digits of the
      SHA-256 of the checkout's built `index.html`, the installed
      copy's `doctor` passes `web`, and the operator opens
      `http://127.0.0.1:8765/` and confirms the dashboard shows
      their locations' levels. The agent does not read the
      operator's dashboard itself.
    </requirement>

    <requirement>
      Filepath comment: every new TypeScript, Python, and YAML
      file starts with its repo-relative path as a comment.
    </requirement>
  </requirements>
</task>
```

### Step 7 acceptance criteria

- The browser smoke passes in the `browser` job and locally: the dashboard's
  Miami-Dade card reaches level 5 through the event stream without a reload, the
  replayed Irma advisory's cone and track draw with both markers, the theme
  menu's injected `<style>` passes under the policy, every tile request is
  answered locally and no other origin is contacted, and no policy violation,
  page error, or landmark coordinate appears in the console.
- Desktop and phone screenshots in both themes are kept as CI artifacts.
- `scripts/measure_idle.py` reports the server process and the page's main
  thread each under 0.5 percent of one core over ten idle minutes, with both
  numbers and the polls and cycles inside the window in the PR body.
- `scripts/simulate_advisory.py` still passes on its own, its last line naming
  `simulated Miami-Dade` at `level=5` with `escalation=True` and
  `toast=delivered`.
- **Deployed & verified:** with the operator's yes, `\Weatherbot\serve` was
  ended, the installed copy rebuilt with the interface, and the task run again,
  away from 25 past the hour; `/api/health` reports `ui.present` and this
  build's `index_sha256`; `doctor` passes `web`; the operator saw their
  dashboard; and the first `ci.yml` and `phase-verify.yml` runs on `main` are
  green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, bandit
  and `eslint-plugin-security` clean, both audits clean with `@playwright/test`
  and `psutil` added — and the smoke and the measurement ran only on
  demonstration data, with no coordinate in any console or artifact.

---

## Step 8 — QA & Verification Script ✅

**Status:** Complete — PR #72, #73 (2026-10-29)

> **Goal:** Package the verification matrix into `scripts/verify_phase05.py`
> (with `--fast`, `--py`, `--node`, `--ui`, `--live`, `--security`, `--all`, and
> `--post` modes), produce `docs/phase05-qa-findings.md`, add `"05"` to the
> `phase-verify.yml` matrix beside `"01"` to `"04"`, and close the phase. The
> script reads every Step 1 through Step 7 deliverable with standard-library
> static checks; builds the V1–V8 matrix from JUnit evidence — one offline
> pytest run with the coverage floors, the frontend's commands and its Vitest
> run, the Playwright run, and the live run — and in `--post`, on the operator's
> machine, adds Phase 4's own `--post` sweep, the operator's service through
> `/api/health` and `doctor`, the live check-now cycle, and the idle
> measurement; the closure marks Phase 5 complete in both roadmaps and in
> `README.md`, names the checks Phase 6 must keep or convert, and tags
> `v2.0.0-phase-5`.

**Branch:** `feature/phase05-step8-verify`

**Deploys:** GitHub Actions → `phase-verify (05)` runs on every push and pull
request from the merge on, under the required aggregate `phase-verify`; its
first run on `main` must be green, and the annotated `v2.0.0-phase-5` tag must
peel to the merge commit.

Settings — ladder (`roadmodel ladder --category coding --complexity medium`):

|               |          | Cost                 | Balanced             | Quality            |
| ------------- | -------- | -------------------- | -------------------- | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**      | **GPT-6.1 Sol**      | **Gemini 4 Argon** |
|               | Platform | Codex                | Codex                | Antigravity        |
|               | Level    | Low                  | High                 | High               |
|               | AA       | 42.1                 | 50.2                 | 52.6               |
|               | Price    | $1.36/1M             | $2.18/1M             | $4.00/1M*          |
| **Runner‑up** | Model    | **Gemini 3.8 Flash** | **Sonnet 5.5**       | **Opus 5.5**       |
|               | Platform | Antigravity          | Claude Code          | Claude Code        |
|               | Level    | Medium               | High                 | High               |
|               | AA       | 39.8                 | 46.8                 | 53.6               |
|               | Price    | $2.19/1M             | $3.03/1M             | $6.02/1M           |
| **Backup**    | Model    | **Sonnet 5.5**       | **Gemini 3.8 Flash** | **GPT-6.1 Sol**    |
|               | Platform | Claude Code          | Antigravity          | Codex              |
|               | Level    | Medium               | High                 | High               |
|               | AA       | 40.8                 | 40.9                 | 50.2               |
|               | Price    | $2.69/1M             | $4.29/1M             | $2.18/1M           |

Ranked for coding, medium complexity. Price: list $ per 1M tokens (3 in : 1 out)
× the tokens the model uses at that level; * token use not yet measured, a
typical model's at that level assumed.

**Conversation:** New

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that
column's usage pool reads `tight` or `exhausted`, run the first of its Runner-up
and Backup whose pool has headroom; on a `tight` pool an option marked ↓ (the
Pick one level lower) also runs. With none, a `tight` column runs the Cost
column and an `exhausted` one its Backup.

> Ran 2026-10-29: Quality Pick — Gemini 4 Argon · Effort High · Thinking On on Antigravity. Session hosted on Antigravity; Quality column Pick selected (`Google AI Ultra` pool `abundant`).

> Settings updated 2026-10-29 (rerank): was Gemini 4 Argon · High. roadmodel 0.2.100 re-ranks coding at medium complexity: Balanced is now GPT-6.1 Sol · High on Codex (Runner-up Sonnet 5.5 · High, Backup Gemini 3.8 Flash · High; were Opus 5.5 · Medium and GPT-6.1 Sol · High), and Quality is now Gemini 4 Argon · High (Runner-up Opus 5.5 · High, Backup GPT-6.1 Sol · High; was Opus 5.5 · High, Gemini 4 Argon · High, GPT-6 Astra · High). Cost is unchanged.

> Settings updated 2026-10-25 (rerank): each column's Runner-up and Backup now come from makers other than its Pick; every Pick is unchanged.

**Model rationale:** Step 8 is coding with an agentic secondary category —
GitHub readbacks, on-machine sweeps, and the closure — at Medium complexity: it
translates this roadmap's acceptance criteria into numbered checks, a V-matrix,
a matrix entry, and a findings rollup, with `scripts/verify_phase04.py` as the
structural template, and it is not novel. The columns differ in depth and maker:
Balanced runs GPT-6.1 Sol on Codex at Intelligence High, enough for enumerated
checks whose content this roadmap writes down, with Sonnet 5.5 on Claude Code at
Effort High as its Runner-up; Quality runs Gemini 4 Argon on Antigravity at
Effort High with thinking on, with Opus 5.5 on Claude Code at Effort High as its
Runner-up, for a deeper audit of each check against its deliverable; Cost keeps
GPT-6.1 Sol on Codex at Intelligence Low. Google AI Ultra, the
claude.ai Max subscription, and ChatGPT Pro fund the three platforms, so each
column costs nothing at the margin while its pool has headroom; when a column's
pool reads `tight` or `exhausted`, the **Runs:** rule moves the step to that
column's Runner-up or Backup. The conversation is new per phase-boundary
hygiene.

```xml
<task>
  <lifecycle>
    This step MUST follow all six
    stages, in order. Stages 1, 3,
    4, 5, 6 are AS BINDING as any
    `<requirement>` below. Do not
    emit the Stage 6 completion
    line until the PR is merged and
    every acceptance criterion for
    this step is affirmatively met.

    1. CREATE THE BRANCH. Before
       any Read / Edit / Bash, run
       `git checkout -b
       feature/phase05-step8-verify`
       from a clean, up-to-date
       `main`. The exact branch
       name is in this step's
       `**Branch:**` line above.
       If the Worktree rule
       applies, use `git fetch
       origin && git worktree add
       -b <branch> <path>
       origin/main` instead, then
       bootstrap the worktree.

    2. WORK ON THE BRANCH. All
       commits land here. `main`
       is protected with
       `enforce_admins: true` —
       direct pushes will be
       rejected.

    3. OPEN THE PR, THEN MARK THE
       STEP. `gh pr create --base
       main --head <branch>` with a
       Conventional Commits title
       and a body that references
       this roadmap step and its
       acceptance criteria. One PR
       per step. Then, in this
       roadmap file: set this
       step's `**Status:**` line
       (directly under its heading)
       to `Complete — PR #<n>
       (<YYYY-MM-DD>)`, append ` ✅`
       to the step's `## Step`
       heading, and set its
       Summary Table Status cell to
       `Complete — PR #<n>`. Commit
       that edit on the step
       branch and push — the PR
       carries its own completion
       mark, so the roadmap on
       `main` marks this step
       complete exactly when the PR
       merges (Status rule). Same
       commit: on the phase's first
       step, set this roadmap's
       phase-level `**Status:**`
       (under its title) and the
       parent project roadmap's
       Phase 5 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 5`
       heading.

    4. WAIT FOR GREEN CHECKS, THEN
       SQUASH-MERGE. Every required
       check must pass. If the PR
       falls behind main, refresh
       with `gh pr update-branch
       --rebase` — never merge main
       into the branch
       (`required_linear_history:
       true`). Once green:
       `gh pr merge <PR> --squash
       --delete-branch`. If this
       step's `**Deploys:**` line
       names a surface, the merge
       is not the finish line: run
       the Deployed & verified
       check against the target
       environment before
       declaring the step complete.

    5. RETIRE THE BRANCH. Sync
       local: `git switch main &&
       git pull --ff-only origin
       main && git fetch --prune
       origin`. Prune any local
       `[gone]` branches. If the
       step ran in a worktree,
       `git worktree remove <path>`
       FIRST — the branch prune
       fails while the branch is
       checked out there.

    6. DISPOSE OF EVERY FINDING,
       DECLARE COMPLETION, THEN
       NEW CONVERSATION. First
       send every finding this
       step surfaced to its
       destination (Triage rule):
       a note for a later step →
       edit that step's <task>
       block now; spec rot → edit
       this roadmap now; a bug →
       fixed in-step or an issue
       number; a judgement call in
       the diff → the PR body; a
       process lesson → written
       where the next conversation
       reads it. A finding you can
       only describe is NOT
       disposed of, and counts as
       an unmet criterion. Only
       once the PR is merged — and
       `main` therefore carries
       this step's `Complete`
       Status line — every
       acceptance criterion is
       affirmatively met, and every
       finding has a destination,
       say so plainly: end your
       final response with an
       explicit, unhedged
       completion line — verbatim
       shape "Step 8 is
       complete. Phase 5 is
       complete. You can now move
       on to Phase 6." That
       line is the LAST line of
       the response. NOTHING
       follows it — no "Follow-ups
       (non-blocking)", "Notes",
       "Next", "worth a glance",
       or suggested improvements.
       A short ledger may PRECEDE
       it, one entry per finding
       naming its destination
       (issue #, file edited, PR
       body) — never an open item.
       If any criterion is unmet
       or any finding has no
       destination, state plainly
       that the step is NOT
       complete, name what is
       outstanding, and omit the
       completion line. "Done"
       means done. Then, for
       phase-boundary hygiene, the
       operator closes this
       session and opens a fresh
       one before Phase 6.
  </lifecycle>

  <security>
    Security is a gate on THIS
    step, not a later phase. It is
    AS BINDING as any
    `<requirement>` below. Before
    the Stage-2 commit, this
    step's work MUST pass the
    local, fail-closed security
    gate — the SAME gate wired
    into the pre-commit hook and
    re-run in CI:

    1. SECRET / PII SCAN. No
       credentials, API keys,
       tokens, or real PII in the
       diff (gitleaks /
       detect-secrets or the
       project's equivalent).
       Secrets go in the secrets
       manager, never in source or
       committed env files.

    2. SAST. No new injection,
       unsafe deserialization,
       weak crypto, path
       traversal, or unsafe-eval
       pattern (bandit / semgrep /
       eslint-plugin-security per
       the stack). Suppress a
       finding ONLY with an inline
       justification comment.

    3. DEPENDENCY AUDIT. Any new
       or bumped dependency passes
       the audit (pip-audit / npm
       audit / osv-scanner); no
       known-vulnerable, yanked,
       or typo-squatted package.

    4. SENSITIVE-DATA REVIEW.
       Whatever this step touches
       stays least-privilege,
       encrypted in transit + at
       rest, and out of logs and
       client bundles. If the step
       adds a data path, name how
       PII/secrets are protected.

    A finding blocks the commit —
    fix it in this step, do not
    defer. Do not declare the step
    complete until the gate is
    clean. This is the safety net
    that stops a security issue
    from reaching the branch, the
    PR, or `main`.

    THIS STEP also AUTHORS the `--security` verify mode, so its
    own diff must still pass the gate before commit. The script
    runs subprocesses from argument lists, never a shell; prints
    check ids, rule names, and exception types, never scanned
    content; reads GitHub settings read-only; reads the operator's
    database only through `doctor` and the running service only
    through `/api/health`, printing only the version, the
    revision and head, the interface's identity, and check
    statuses; runs every build, live, browser, and idle probe in a
    temporary data directory over the public landmarks; and never
    runs `status`, `check`, or `replay` against the operator's
    stored locations, nor prints a notification about them.
    `--post` starts a demonstration server and a headless browser,
    and says so before it starts. It never reads or prints the
    personal-data denylist.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 5 (Web app MVP). Step 8:
    QA + verification script.

    Steps 1 through 7 have been implemented. Now create the
    verification script, the QA findings, and the matrix entry,
    and close the phase.

    Reference scripts (pattern templates):
    - scripts/verify_phase04.py (the structural precedent: 51
      static checks, the six modes, V rows built from JUnit
      reports where every selection must match a test, a failure
      fails, and a skip is never a pass, the GitHub readbacks, the
      nested `--post`, the operator's-machine rows) and
      tests/test_phase04_verification.py.
    - scripts/verify_phase03.py (the nested-timeout handling) and
      scripts/verify_phase01.py (the tagged reads).

    Phase 5 deliverables to verify (53 static checks: 47 across
    Steps 1 through 7, and 6 Step 8 self-checks):

    Step 1 (the web server) — checks 1-11:
    1.  `pyproject.toml` lists `fastapi`, `starlette`, and
        `uvicorn` among `[project] dependencies`, without
        `uvicorn[standard]`.
    2.  The `layers` contract keeps its name, puts
        `weatherbot.cli` before `weatherbot.web` as separate
        layers, and ends with `weatherbot.models`; no layer reads
        `weatherbot.cli | weatherbot.web`.
    3.  `web/app.py` defines `create_app` and `WebState`, passes
        `docs_url=None`, `redoc_url=None`, and
        `openapi_url="/api/openapi.json"` (AST).
    4.  `web/guards.py` mounts `TrustedHostMiddleware` with
        `127.0.0.1`, `localhost`, and `[::1]`, reads
        `Sec-Fetch-Site`, and holds the policy's `frame-ancestors
        'none'`, `script-src 'self'`, and tile host, `nosniff`,
        `strict-origin-when-cross-origin`, and `no-store`; no
        package module imports or references `CORSMiddleware` or
        `BaseHTTPMiddleware` (AST names and attributes, so a
        comment or docstring explaining the choice does not count).
    5.  `web/server.py` defines `WebServer`, subclasses
        `uvicorn.Server` overriding `capture_signals`, names
        `SO_EXCLUSIVEADDRUSE` and `timeout_graceful_shutdown`, and
        catches `SystemExit` (AST).
    6.  `services/config.py` defines `WebSettings` with `host` and
        `port`, `ENVIRONMENT_OVERRIDES` holds the literal
        `WEATHERBOT_WEB_HOST` and `WEATHERBOT_WEB_PORT`, and
        `tests/conftest.py` sets `WEATHERBOT_WEB_PORT` to `"0"`.
    7.  `cli/serve.py` keeps `ProcessLock(paths.monitor_lock_path)`
        and `run_monitor(`, uses `WebServer`, and offers
        `--open/--no-open`; `Runtime` defines `open_browser`.
    8.  `services/doctor.py` calls `Check` with the literal
        `"web"` as its first argument (AST); `doctor.schema.json`
        lists no check names, so it is not read.
    9.  `scripts/export_openapi.py` offers `--check`;
        `docs/api/openapi.json` is tracked, declares OpenAPI 3.1,
        holds `/api/health`, and no `/docs` or `/redoc` path.
    10. `.gitignore` holds `/src/weatherbot/web/static/`, and
        `verify_phase04.py`'s check 46 reads `v2.0.0-phase-4`.
    11. The Step 1 tests are tracked (`tests/web/test_web_app.py`,
        `test_api_guards.py`, `test_built_interface.py`,
        `test_web_server.py`, `test_web_settings.py`,
        `test_openapi_export.py`, `tests/cli/test_serve_web.py`,
        and `tests/services/test_doctor_web.py`).

    Step 2 (the read API) — checks 12-18:
    12. `web/routes/` holds the locations, assessments, storms,
        alerts, timeline, notifications, settings, disclaimer,
        map, and replay modules, and `create_app` includes each.
    13. `docs/api/openapi.json` holds every read path of Step 2.
    14. `web/map_layers.py` defines the layer builder and the
        antimeridian unwrap, and its cache holds at most 8
        snapshots.
    15. `ReplayCorpus` defines `advisories` and `snapshot` (AST).
    16. `serve` offers `--corpus`, and `/api/health`'s model has
        `corpus`.
    17. No `web/` module defines an `async def` route that reads
        a repository (the database routes are plain functions).
    18. The Step 2 tests are tracked (`test_api_reads.py`,
        `test_api_cli_parity.py`, `test_api_privacy.py`,
        `test_map_layers.py`, `test_replay_routes.py`).

    Step 3 (the event stream) — checks 19-25:
    19. `services/events.py` defines `EventHub`, `CycleWatcher`,
        and `BrowserChannel`, and its event kinds are exactly
        `hello`, `cycle`, `snapshot`, `assessment`, `alert`,
        `notification`, `location`, and `health`.
    20. `CHANNEL_NAMES` holds `browser`; `NotificationSettings`
        has `browser` with the literal
        `WEATHERBOT_NOTIFICATIONS_BROWSER`.
    21. `web/routes/events.py` uses `EventSourceResponse` with the
        return annotation `AsyncIterable[StreamEvent]`, and
        `docs/api/openapi.json`'s components hold `StreamEvent`
        and its `QueryKey` values.
    22. `web/routes/actions.py` defines the four writes, and the
        cycle it starts uses the trigger `manual`.
    23. `cli/serve.py` passes the hub's cycle listener to
        `run_monitor` and the hub's `close` to `WebServer`.
    24. The Step 3 tests are tracked, and
        `tests/live/test_web_live.py` is marked `live`.
    25. No event model in `web/schemas.py` (`StreamEvent` and the
        models it references) declares a field named `lat`, `lon`,
        `latitude`, `longitude`, `coordinates`, `geometry`,
        `distance_km`, or `bearing_deg` (AST): events never locate.

    Step 4 (the frontend chassis) — checks 26-35:
    26. `frontend/package.json` is private, its `engines.node` is
        at least 24.15, and it pins `react`, `react-dom`,
        `typescript`, `vite`, `openapi-typescript`, and
        `eslint-plugin-security` as exact versions (no range
        operator, so Dependabot's bumps keep the check green),
        `typescript` at major 5; `frontend/.nvmrc` reads `24`;
        `frontend/package-lock.json` is tracked.
    27. Its scripts include `lint` with `--max-warnings 0`,
        `api:check` with `--check`, `licenses:check`, `audit`, and
        `test`.
    28. `vite.config.ts` writes to `../src/weatherbot/web/static`,
        names `licenses.json` and `__CSP_NONCE__`, and binds the
        dev server to `127.0.0.1`.
    29. `eslint.config.js` loads `eslint-plugin-security` and
        typescript-eslint.
    30. `frontend/src/api/schema.d.ts`, `api/keys.ts`, and
        `events/useEventStream.ts` are tracked, and no file under
        `frontend/src` names `import.meta.env.VITE_`.
    31. `frontend/index.html` has no inline `<script>` or
        `<style>`, links `/theme-init.js`, and carries the nonce
        meta.
    32. `ci.yml` has a `frontend` job in `gate`'s `needs`, the
        `security` job runs `npm audit --audit-level=high`, and the
        `package` job builds the interface before `uv build` and
        runs `scripts/smoke_installed_web.py`.
    33. Every `actions/setup-node` use, in `ci.yml` and
        `phase-verify.yml`, is pinned to a full SHA with a version
        comment.
    34. `.github/dependabot.yml` has `package-ecosystem: npm` for
        `/frontend`; `.pre-commit-config.yaml` has `frontend-lint`
        and `npm-audit`.
    35. `.gitignore` holds the frontend's outputs, and
        `frontend/scripts/check-licenses.mjs` names the six allowed
        licences.

    Step 5 (the pages) — checks 36-39:
    36. `frontend/src/pages/` tracks `Dashboard.tsx`,
        `Storms.tsx`, `Alerts.tsx`, `Timeline.tsx`, and
        `Settings.tsx`, each with its `.test.tsx`.
    37. No file under `frontend/src` uses `dangerouslySetInnerHTML`.
    38. `scripts/export_api_fixtures.py` offers `--check`, the
        fixtures are tracked under `frontend/src/test/fixtures/`,
        and `tests/web/test_api_fixtures.py` is tracked.
    39. `new Notification(` appears under `frontend/src` only in
        `notifications/notify.ts`, which reads the switch, the
        permission, and the page's visibility.

    Step 6 (the map) — checks 40-43:
    40. `frontend/package.json` pins `leaflet` as an exact version
        at major 1, and neither it nor the lock names
        `react-leaflet`.
    41. `frontend/src/map/useLeafletMap.ts` and `map/layers.ts`
        are tracked, with the tile URL, `referrerPolicy`, and the
        "OpenStreetMap contributors" attribution.
    42. `docs/DATA_SOURCES.md`'s basemap bullet names
        `strict-origin-when-cross-origin`.
    43. `frontend/src/map/layers.test.ts` and `MapView.test.tsx`
        are tracked.

    Step 7 (the browser smoke) — checks 44-47:
    44. `scripts/serve_demo.py` and `scripts/measure_idle.py` are
        tracked; `psutil` and `types-psutil` are in the dev group.
    45. `frontend/playwright.config.ts` and the four specs are
        tracked, `idle.spec.ts` tagged `@idle`.
    46. `ci.yml` has a `browser` job in `gate`'s `needs`, its
        `upload-artifact` pinned to a full SHA.
    47. `README.md` has the dashboard section, and its `##
        Commands` still names `weatherbot status`, `weatherbot
        replay`, and `weatherbot locations evacuation`.

    Step 8 self-checks — checks 48-53:
    48. `scripts/verify_phase05.py` is tracked and declares its
        eight modes.
    49. `tests/test_phase05_verification.py` is tracked.
    50. `docs/phase05-qa-findings.md` exists with a section per
        step, the idle numbers, and "Pre-ship items".
    51. `docs/roadmap/phase05-roadmap.md` exists (this doc), and
        the project roadmap holds `### Phase 5 — Web app MVP`.
    52. `.github/workflows/phase-verify.yml`'s flow-list matrix
        includes `"01"`, `"02"`, `"03"`, `"04"`, and `"05"`, and
        its setup-node and `npm ci` steps run only for `"05"`.
    53. The security gate is wired: the gate hooks and the
        frontend hooks in `.pre-commit-config.yaml`, and
        `--security` in every phase entry.

    Files to read:
    - scripts/verify_phase04.py (primary structural template) and
      tests/test_phase04_verification.py.
    - scripts/verify_phase03.py and scripts/verify_phase01.py.
    - all Phase 5 implementation files from Steps 1 through 7, and
      docs/phase04-qa-findings.md (the ledger's shape).
    - docs/roadmap/phase05-roadmap.md (this step, every step's
      acceptance criteria, and Post-Implementation Verification)
      and docs/roadmap/ROADMAP.md (Phase 5 and Phase 6).
  </context>

  <goal>
    Create scripts/verify_phase05.py with 53 static checks (47 for
    Steps 1 through 7, and 6 Step 8 self-checks) plus the 32-row
    V1-V8 matrix (85 in `--post`); create
    docs/phase05-qa-findings.md; add `"05"` to the
    phase-verify.yml matrix; close Phase 5 in both roadmaps and
    the README; and tag `v2.0.0-phase-5`.
  </goal>

  <requirements>
    <requirement>
      Read scripts/verify_phase04.py end-to-end for structure,
      flag parsing, output format, the PASS / FAIL / SKIP
      conventions, and the final summary. Mirror it so the Phase 5
      output is continuous with Phase 4's in CI logs.
    </requirement>

    <requirement>
      scripts/verify_phase05.py modes, mutually exclusive; no flag
      runs `--fast` and `--py`:

      - `--fast`: the 53 static checks only, standard library only
        and offline, CI-safe on Ubuntu, under 30 seconds; AST,
        `tomllib`, `json`, and `git ls-files` reads.
      - `--py`: static checks + ruff, ruff format, strict pyright,
        lint-imports, and one offline pytest run with the engine
        and policy coverage floors and `--junitxml` (its
        `COVERAGE_FILE` in a temporary directory), the OpenAPI and
        fixture `--check` runs, and the wheel smoke with the built
        interface and `scripts/smoke_installed_web.py`.
      - `--node`: static checks + in `frontend/`, `npm ci`, `npm
        audit signatures`, `api:check`, `lint`, `typecheck`,
        Vitest with a JUnit reporter, `build`, and
        `licenses:check`.
      - `--ui`: static checks + the Playwright run (Chromium) with
        a JUnit reporter.
      - `--live`: static checks + one `pytest -m live` run with
        `--junitxml` (the landmarks only).
      - `--security`: the gate over both stacks — gitleaks, bandit
        over `src` and `scripts`, `scripts/audit_deps.py`,
        `scripts/check_personal_data.py` (`--ci` in CI, or with the
        denylist locally), `npm audit --audit-level=high`, and
        ESLint at `--max-warnings 0`. CI-safe on Ubuntu; non-zero
        on any finding.
      - `--all`: py + node + ui + live + security.
      - `--post`: static checks + V1-V8, announcing the
        demonstration server and the browser first, and `gh pr
        checks` on a branch.

      At least one static check is security-oriented and confirms
      the gate is wired, not bypassed (check 53), and the checks
      continue after a failure without echoing content.
    </requirement>

    <requirement>
      Post-implementation V-checks (32 rows; JUnit or command
      evidence per row, every selection matching at least one
      test):

      V1 — The web server
      - V1.1 Static checks 1-11 all PASS.
      - V1.2 The guard, health, built-interface, settings, and
        doctor-web tests pass (`--py`).
      - V1.3 The serve-web and web-server tests pass: `serve`
        hosts the server on port 0, closes its socket on every
        path, and monitors on when the port is taken.
      - V1.4 `verify_phase04.py --post` reports all 80 checks PASS
        (Phase 3's, 2's, and 1's inside it), with a nested timeout
        long enough for all four (record the measured time).
      - V1.5 On the operator's machine, `/api/health` answers from
        the installed copy with the database at its head, and the
        installed copy's `doctor` passes `web` (only the version,
        revision, head, and statuses printed).

      V2 — The read API
      - V2.1 Static checks 12-18 all PASS.
      - V2.2 The read-route, CLI-parity, and privacy tests pass.
      - V2.3 The map-layer and replay-route tests pass.
      - V2.4 `export_openapi.py --check` passes.

      V3 — The event stream, browser notifications, and actions
      - V3.1 Static checks 19-25 all PASS.
      - V3.2 The hub, watcher, staleness-timer, and stream tests
        pass.
      - V3.3 The browser-channel and action tests pass, the
        cross-site refusals included.
      - V3.4 The live check-now test passes (the live run).

      V4 — The frontend chassis
      - V4.1 Static checks 26-35 all PASS.
      - V4.2 The `--node` run exits 0: `npm ci`, `npm audit
        signatures`, `api:check`, `lint`, `typecheck`, `build`,
        and `licenses:check`.
      - V4.3 `npm audit --audit-level=high` passes (`--security`).
      - V4.4 The wheel holds the interface and
        `smoke_installed_web.py` passes.

      V5 — The pages
      - V5.1 Static checks 36-39 all PASS.
      - V5.2 Every page's Vitest file passes.
      - V5.3 The event-subscription tests pass (exactly the named
        keys; everything on a reconnect).
      - V5.4 The screenshots spec passes (the Playwright run).

      V6 — The map
      - V6.1 Static checks 40-43 all PASS.
      - V6.2 The map's Vitest files pass.
      - V6.3 The map spec passes with no policy violation.

      V7 — The browser smoke and the operator's dashboard
      - V7.1 Static checks 44-47 all PASS.
      - V7.2 The dashboard spec passes: the level-5 change without
        a reload, and no coordinate in the console.
      - V7.3 `scripts/measure_idle.py` reports both shares under
        0.5 percent of one core (`--post`, about 11 minutes).
      - V7.4 The operator's `/api/health` reports `ui.present` and
        the `index_sha256` of the checkout's build.

      V8 — CI integration + security
      - V8.1 `verify_phase05.py --fast` exits 0 on Ubuntu CI.
      - V8.2 `phase-verify.yml`'s matrix includes `"01"` to `"05"`.
      - V8.3 All 53 static checks pass.
      - V8.4 `verify_phase05.py --security` exits 0.

      The offline run's exit is a constituent of V1.2, the
      frontend run's of V4.2, the Playwright run's of V7.2, and the
      live run's of V3.4, so no failure escapes `--post`. On
      `main`, a GitHub readback requires the latest run to be at
      HEAD; run the canonical `--post` on clean `main` only after
      `main`'s `ci.yml` and `phase-verify.yml` runs finish (Phase
      4's lesson). Before adding a selection, grep the local run's
      SKIPPED lines: a selection that skips on the operator's
      account reads SKIP.
    </requirement>

    <requirement>
      Create `tests/test_phase05_verification.py`, mirroring Phase
      4's: the roadmap and QA documents exist; `--fast` runs; the
      matrix includes `"05"`; checks continue after a failure
      without echoing content; there are exactly 53 static checks;
      skipped evidence cannot pass; the mode flags are exclusive;
      JUnit selections must match; the post matrix reports exactly
      32 rows; and editing a deliverable in memory turns exactly
      its check red (one case per step at least).
    </requirement>

    <requirement>
      Update `.github/workflows/phase-verify.yml` to include `"05"`
      in the matrix — append it to the flow list `matrix.phase`,
      which keeps `"01"` to `"04"`; this is an additive change
      (Phases 1 to 4 read that flow list). Because `--security` for
      `"05"` runs `npm audit` and ESLint, the job gains, before its
      security gate and only for that entry (an `if:` holding both
      `!cancelled()` and `matrix.phase == '05'`, since the gate's
      steps run after a failed `--fast`), `actions/setup-node`
      pinned to the same
      full SHA as `ci.yml` with its version comment and
      `node-version-file: frontend/.nvmrc`, and `npm ci` in
      `frontend/`; the other entries run exactly the steps they run
      today. Raise `timeout-minutes` only if a measured run needs
      it.
    </requirement>

    <requirement>
      Create docs/phase05-qa-findings.md with rollup sections for
      this roadmap's PR and every Step 1 through Step 7 PR, a Step
      8 rollup, the source-drift observations, the live-smoke runs,
      the idle measurement (both numbers, the window, the machine),
      and a "Pre-ship items" section: Phase 6 streams its briefing
      into the dashboard over the API and the event stream and
      joins the settings page; Phase 7 adds its layers, charts, and
      scrubber to the map and the replay routes, turns the
      read-only settings into the multi-location page, and owns the
      tile-proxy fallback if OpenStreetMap starts refusing loopback
      Referers; Phase 8's LAN mode widens the bind behind a token
      and its release workflow builds the interface as the
      `package` job does. Every finding has a destination.
    </requirement>

    <requirement>
      Name every Phase 5 check that a later phase's normal growth
      would turn red (as Phase 4 did for checks 8, 17, 20, 36, 40,
      43, and 46 — check 19's event kinds and check 47's README are
      the likely ones), make each either growth-proof (inclusion)
      or exact by intent, and record the exact ones and their
      historical conversion in the project roadmap's Phase 6 entry
      and the QA ledger.
    </requirement>

    <requirement>
      Mark the phase complete in the parent project roadmap
      (docs/roadmap/ROADMAP.md, beside this file) in the SAME
      Stage-3 commit that marks this step (Status rule):

      - `### Phase 5` gets `**Status:** Complete — <YYYY-MM-DD>;
        PR #<n>; v2.0.0-phase-5; phase05-roadmap.md` directly
        under its heading, and the heading ends in ✅.
      - Its row in the "Phase Complexity Summary" table reads
        `Complete` (Step 1's PR set it to `In progress`).
      - The header `> **Status:**` line names Phase 5 as shipped
        and Phase 6 as next.
      - Consistency audit: the Phase 5 "Acceptance criteria" there
        match this roadmap's V1-V8 checks.

      And in THIS roadmap, same commit: its phase-level
      `**Status:**` line (under the title) reads `Complete —
      <YYYY-MM-DD>`, the title and every step heading end in ✅,
      and every step's Summary Table Status cell reads `Complete —
      PR #<n>`. And `README.md`'s Status section, same commit:
      Phase 5 complete and Phase 6 next (Phase 4's check 46 reads
      its tag since Step 1, so this edit cannot turn it red).
    </requirement>

    <requirement>
      After the merge, create the annotated tag `v2.0.0-phase-5`
      on the merge commit and push it; `git ls-remote --tags
      origin v2.0.0-phase-5` must show it peeling to the merge
      commit. The package version stays `2.0.0.dev0`.
    </requirement>

    <requirement>
      The script exits 0 on success and 1 on any failure, prints a
      clear PASS / FAIL / SKIP line per check, and mirrors
      `verify_phase04.py`'s output format, check numbering, and
      summary so CI log diffing across phases is frictionless.
      `--fast` must complete in under 30 seconds on Ubuntu CI and
      on the operator's Windows machine. `CHANGELOG.md` and
      `CONTRIBUTING.md` describe it.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative path
      as the first line.
    </requirement>
  </requirements>
</task>
```

### Step 8 acceptance criteria

- `scripts/verify_phase05.py` exists and passes on a clean tree after
  implementation; all eight modes exist.
- The script has 53 static checks plus the V1–V8 post-implementation checks (85
  in total).
- `--fast` runs in under 30 seconds on Ubuntu CI and on the operator's Windows
  machine.
- `--post` runs cleanly on the operator's Windows machine with `gh` signed in,
  reporting V1.1 through V8.4 green, Phase 4's 80 checks among them.
- `docs/phase05-qa-findings.md` is complete, with every rollup section, the idle
  numbers, and a destination for every finding.
- `.github/workflows/phase-verify.yml` runs matrix entries `"01"` to `"05"` on
  every pull request, under the required aggregate `phase-verify`, with Node set
  up only for `"05"`.
- `--security` exits 0 over both stacks; V8.4 is green.
- Branch protection still passes on the resulting PR.
- **Deployed & verified:** the first `phase-verify.yml` run on `main` after the
  merge is green with all five entries; `gh api
  repos/nathanramoscfa/weatherbot/branches/main/protection --jq
  .required_status_checks` still names `gate` and `phase-verify`; and `git
  ls-remote --tags origin v2.0.0-phase-5` shows the tag at the merge commit.
- **Operations:** every runtime surface this phase added has a health signal and
  an alarm that has been seen to fire: `/api/health` and `doctor`'s `web` check,
  whose failure was injected (a fresh `serve` heartbeat with nothing answering,
  V1.2) and seen on the operator's machine passing (V1.5); the staleness banner,
  driven by the timed `health` event (V3.2, V5.3); and the browser channel's
  `unavailable` result with no page open (V3.3).
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff, and the `security` job and all five
  `phase-verify` entries are green.
- **Phase closed, nothing carried.** Every finding recorded in
  `docs/phase05-qa-findings.md` has a destination (fixed, an issue number, or a
  named phase that owns it), the "Not in scope" section below is current, and no
  untracked item remains. Every step of this roadmap, this one included, reads
  `**Status:** Complete — PR #…` on `main` under a ✅ heading, the Summary
  Table's Status column and this roadmap's phase-level Status line say
  `Complete` under a ✅ title, and the project roadmap's Phase 5 entry (under a ✅
  heading), its summary-table row, and its header status line say `Complete` —
  all landed in this step's PR. This step's final response ends with the line
  "Step 8 is complete. Phase 5 is complete. You can now move on to Phase 6." in
  place of the usual "Step 8 is complete. You can now move on to Step 9." — same
  Stage 6 rule: no "Follow-ups", no trailer.

---

## Post-Implementation Verification

Every V1–V8 check below runs **automatically in CI** on every push and pull
request, except these. Phase 4's own `--post` sweep (V1.4), the operator's
running service and `doctor` (V1.5, V7.4), the live check-now cycle (V3.4), and
the idle measurement (V7.3) run in `--post` on the operator's Windows machine,
because they need the operator's environment, the installed copy, or ten quiet
minutes. The live suite (V3.4 and every live test) runs in `--live` locally and
in `live-smoke.yml`, which is dispatched by hand.

| Mode         | Workflow                        | Runner  | Coverage          |
| ------------ | ------------------------------- | ------- | ----------------- |
| `--fast`     | `phase-verify.yml` (`"05"`)     | Ubuntu  | static checks     |
| `--py`       | `ci.yml` test, package          | both    | Python rows       |
| `--node`     | `ci.yml` frontend               | Ubuntu  | frontend rows     |
| `--ui`       | `ci.yml` browser                | Ubuntu  | V5.4, V6.3, V7.2  |
| `--security` | `ci.yml` security, phase-verify | Ubuntu  | V4.3, V8.4        |
| `--live`     | `live-smoke.yml` (dispatch)     | Ubuntu  | V3.4, live tests  |
| `--all`      | none (local)                    | Windows | all but `--post`  |
| `--post`     | local, operator's machine       | Windows | every V row       |

In the tables, `fast` is `phase-verify.yml`'s `--fast`, `ci` is `ci.yml`'s
`test` job (`--py`), `pkg` its `package` job, `node` its `frontend` job
(`--node`), `ui` its `browser` job (`--ui`), `sec` the `security` job and
`--security`, `live` the dispatched live suite, and `post` the operator's
machine only.

Local invocations remain available for ad-hoc runs and pre-release sweeps:

```bash
uv run python scripts/verify_phase05.py --post   # static + V1-V8 + post checks
```

`--post` is the canonical command to run before tagging `v2.0.0-phase-5`. It
starts a demonstration server and a headless browser in a temporary data
directory, reads the operator's running service only through `/api/health` and
`doctor`, and says so before it starts.

Other modes:

```bash
uv run python scripts/verify_phase05.py --fast      # static only (CI-safe)
uv run python scripts/verify_phase05.py --py        # + lint, types, tests
uv run python scripts/verify_phase05.py --node      # + frontend toolchain
uv run python scripts/verify_phase05.py --ui        # + browser smoke
uv run python scripts/verify_phase05.py --live      # + live, landmarks only
uv run python scripts/verify_phase05.py --security  # the gate, both stacks
uv run python scripts/verify_phase05.py --all       # every mode but --post
```

The script reports each V-check by id (V1.1, V2.1, ...) so a failure in any
workflow above maps directly to the corresponding row below.

### V1 — The web server inside serve

> **Automated in CI.** `phase-verify.yml` → V1.1; `ci.yml` → V1.2 and V1.3;
> `--post` on the operator's machine → V1.4 and V1.5.

| ID   | Check                                                         | Runs |
| ---- | ------------------------------------------------------------- | ---- |
| V1.1 | Static checks 1–11 all PASS.                                  | fast |
| V1.2 | Guard, health, built-files, settings, and doctor tests pass.  | ci   |
| V1.3 | `serve` hosts the server on port 0; a taken port spares it.   | ci   |
| V1.4 | `verify_phase04.py --post` passes all 80 (and 3, 2, 1).       | post |
| V1.5 | The operator's `/api/health` answers; `doctor` `web` passes.  | post |

### V2 — The read API and the map's geometry

> **Automated in CI.** `phase-verify.yml` → V2.1; `ci.yml` → V2.2 to V2.4.

| ID   | Check                                                         | Runs |
| ---- | ------------------------------------------------------------- | ---- |
| V2.1 | Static checks 12–18 all PASS.                                 | fast |
| V2.2 | Read-route, CLI-parity, and privacy tests pass.               | ci   |
| V2.3 | Map-layer and replay-route tests pass.                        | ci   |
| V2.4 | `export_openapi.py --check` passes on both runners.           | ci   |

### V3 — The event stream, browser notifications, and the actions

> **Automated in CI.** `phase-verify.yml` → V3.1; `ci.yml` → V3.2 and V3.3;
> `live-smoke.yml` and `--live` → V3.4.

| ID   | Check                                                         | Runs |
| ---- | ------------------------------------------------------------- | ---- |
| V3.1 | Static checks 19–25 all PASS.                                 | fast |
| V3.2 | Hub, stream, watcher, and staleness-timer tests pass.         | ci   |
| V3.3 | Browser-channel and action tests pass, cross-site writes too. | ci   |
| V3.4 | A live check-now cycle stores and emits its events.           | live |

### V4 — The frontend chassis, its gate, and the wheel

> **Automated in CI.** `phase-verify.yml` → V4.1; the `frontend` job → V4.2; the
> `security` job → V4.3; the `package` job → V4.4.

| ID   | Check                                                         | Runs |
| ---- | ------------------------------------------------------------- | ---- |
| V4.1 | Static checks 26–35 all PASS.                                 | fast |
| V4.2 | `--node` exits 0: signatures, types, lint, build, licences.   | node |
| V4.3 | `npm audit --audit-level=high` passes in `--security`.        | sec  |
| V4.4 | The wheel holds the build; installed `serve` answers `/`.     | pkg  |

### V5 — The dashboard and the pages

> **Automated in CI.** `phase-verify.yml` → V5.1; the `frontend` job → V5.2 and
> V5.3; the `browser` job → V5.4.

| ID   | Check                                                         | Runs |
| ---- | ------------------------------------------------------------- | ---- |
| V5.1 | Static checks 36–39 all PASS.                                 | fast |
| V5.2 | Every page's component tests pass, empty states included.     | node |
| V5.3 | An event invalidates exactly the queries it names.            | node |
| V5.4 | Desktop and phone-width screenshots render in both themes.    | ui   |

### V6 — The map

> **Automated in CI.** `phase-verify.yml` → V6.1; the `frontend` job → V6.2; the
> `browser` job → V6.3.

| ID   | Check                                                         | Runs |
| ---- | ------------------------------------------------------------- | ---- |
| V6.1 | Static checks 40–43 all PASS.                                 | fast |
| V6.2 | Map tests draw live and replay layers and the markers.        | node |
| V6.3 | The map loads with no CSP violation in the console.           | ui   |

### V7 — The browser smoke, idle cost, and the operator's dashboard

> **Automated in CI.** `phase-verify.yml` → V7.1; the `browser` job → V7.2;
> `--post` on the operator's machine → V7.3 and V7.4.

| ID   | Check                                                         | Runs |
| ---- | ------------------------------------------------------------- | ---- |
| V7.1 | Static checks 44–47 all PASS.                                 | fast |
| V7.2 | The smoke sees the change, the replay map, and no coordinate. | ui   |
| V7.3 | Server and tab each stay under 0.5% of a core idle.           | post |
| V7.4 | The operator's service serves this build's interface.         | post |

### V8 — CI integration + security

> **Automated in CI.** `phase-verify.yml` → V8.1 through V8.4 on every push/PR.

| ID   | Check                                                         | Runs |
| ---- | ------------------------------------------------------------- | ---- |
| V8.1 | `verify_phase05.py --fast` exits 0 on Ubuntu CI.              | fast |
| V8.2 | `phase-verify.yml`'s matrix includes `"01"` to `"05"`.        | fast |
| V8.3 | All 53 static checks in `verify_phase05.py` pass.             | fast |
| V8.4 | `--security` exits 0 over both stacks.                        | sec  |

---

## Summary Table

| Step | Scope                          | Model          | Status             |
| ---- | ------------------------------ | -------------- | ------------------ |
| 1    | Web server inside serve        | Gemini 4 Argon | Complete — PR #61  |
| 2    | Read API + map geometry        | Gemini 4 Argon | Complete — PR #62  |
| 3    | Events + browser + actions     | Gemini 4 Argon | Complete — PR #63  |
| 4    | Frontend chassis + wheel       | Gemini 4 Argon | Complete — PR #64  |
| 5    | Dashboard + pages              | Gemini 4 Argon | Complete — PR #65  |
| 6    | Map                            | Gemini 4 Argon | Complete — PR #66  |
| 7    | Browser smoke + idle + deploy  | Gemini 4 Argon | Complete — PR #70  |
| 8    | QA + verify_phase05.py         | GPT-6.1 Sol    | Complete — PR #72, #73 |
| V1   | Web server inside serve        | CI             | --                 |
| V2   | Read API + map geometry        | CI             | --                 |
| V3   | Events + browser + actions     | CI             | --                 |
| V4   | Frontend chassis + wheel       | CI             | --                 |
| V5   | Dashboard + pages              | CI             | --                 |
| V6   | Map                            | CI             | --                 |
| V7   | Browser smoke + idle + deploy  | CI             | --                 |
| V8   | CI integration                 | CI             | --                 |

Each step's row restates the Pick of the Balanced column its **Runs:** line
names; the platform, the dials, the Runner-up and the Backup, the Cost and
Quality columns, and the rule for a pool that reads `tight` or `exhausted` live
in the step's own Settings.

---

## Model selection blocks

Each block restates the Balanced column the step's **Runs:** line names (its
Pick, and its Backup from another maker); the Runner-up, which the **Runs:**
rule tries first when the Pick's pool reads `tight` or `exhausted`, is named in
the rationale.

```text
PROMPT: Step 1 — The web server inside serve
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — an
ASGI server embedded in an existing asyncio loop, browser-facing
guards, a layering change, health, the OpenAPI pipeline, and an
on-machine deployment, High complexity. PICK: Gemini 4 Argon
is S-tier in coding (AA Intelligence Index 52.6 at High), the
ladder's Balanced pick; Runner-up Opus 5.5 on Claude Code at
High. EFFORT: High fits a security-sensitive chassis whose
design this roadmap fixes.

PROMPT: Step 2 — The read API and the map's geometry
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a knowledge secondary — ten read
routes, GeoJSON that keeps each geometry's CRS, a per-snapshot
cache, replay accessors, and parity and privacy tests, High
complexity. PICK: Gemini 4 Argon, S-tier in coding (AA 52.6),
the ladder's Balanced pick; Runner-up Opus 5.5 at High.
EFFORT: High fits many models over known records.

PROMPT: Step 3 — The event stream, browser notifications, and the API's actions
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — a
publish-subscribe hub with bounded queues, a cross-process
watcher, a staleness timer, a server-sent event route, a new
channel, and four guarded writes, High complexity. PICK:
Gemini 4 Argon, S-tier in coding (AA 52.6), the ladder's
Balanced pick; Runner-up Opus 5.5 at High. EFFORT: High fits
concurrency whose rules this roadmap states.

PROMPT: Step 4 — The frontend chassis, its gate, and the wheel
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — a new
toolchain, generated types, the app shell, the event
subscription, the frontend's security gate, CI jobs, and the
wheel's build, High complexity. PICK: Gemini 4 Argon, S-tier
in coding (AA 52.6), the ladder's Balanced pick; Runner-up
Opus 5.5 at High. EFFORT: High fits a cross-cutting setup
with pinned choices.

PROMPT: Step 5 — The dashboard and the pages
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a multimodal secondary — five
pages, the level card's evidence, browser notifications,
first-run setup, themes and phone width checked by screenshot,
High complexity. PICK: Gemini 4 Argon, S-tier in coding and
multimodal work (AA 52.6), the ladder's Balanced pick;
Runner-up Opus 5.5 at High. EFFORT: High fits broad UI work on
a fixed contract.

PROMPT: Step 6 — The map
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a knowledge secondary — Leaflet
layers for NHC's products, CRS-faithful drawing, antimeridian
continuity, tile attribution under a strict CSP, and the replay
picker, High complexity. PICK: Gemini 4 Argon, S-tier in coding
(AA 52.6), the ladder's Balanced pick; Runner-up Opus 5.5 at
High. EFFORT: High fits geospatial rendering with set rules.

PROMPT: Step 7 — The browser smoke, idle cost, and the operator's dashboard
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — a
Playwright smoke over a simulated advisory, CPU measurement
through the DevTools Protocol, and an on-machine deployment,
High complexity. PICK: Gemini 4 Argon, S-tier in coding and
agentic work (AA 52.6), the ladder's Balanced pick; Runner-up
Opus 5.5 at High. EFFORT: High fits end-to-end proof work.

PROMPT: Step 8 — QA + verify_phase05.py
MODEL: GPT-6.1 Sol
BACKUP: Gemini 3.8 Flash
PLATFORM: Codex
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: mechanical translation of this roadmap's
acceptance criteria into a verification script, a matrix entry,
and a findings rollup. PICK: known pattern, no novel reasoning —
GPT-6.1 Sol on Codex (AA 50.2 at High), the ladder's Balanced
pick; Runner-up Sonnet 5.5 at High. EFFORT: High is the level
the ladder prints for this column; enumerated checks whose
content this roadmap writes down need no more.
```

---

## Not in scope (from product roadmap)

The project roadmap's Phase 5 section carries no "Not in scope" list; these
items follow from its phase boundaries and its §6 "Out of Scope":

- Claude: the briefing, the change summary, the grounded chat, the outlook
  narration, and the cost meter. Phase 6 streams them into this phase's
  dashboard over the same API and event stream, labeled as AI.
- The wind-probability and arrival charts, the wind-radii, wind-speed
  probability, surge, radar, and satellite layers, the advisory time slider, the
  replay scrubber with the replayed level and evidence, the multi-location
  settings page with per-location notification preferences, quiet hours, and
  retention, ntfy push, and the report export. Phase 7, on this phase's map,
  replay routes, and settings page.
- LAN access, its bearer token, and its rate limiting; the PyPI release and the
  release workflow's build of the interface. Phase 8, which widens the bind this
  phase refuses only behind its readiness gate.
- Public hosting, accounts, mobile apps, and every channel beyond the toast, the
  browser, the in-app log, and Phase 7's ntfy (§6).

Additionally not in scope for this phase:

- The official outlook graphics in the page. Phase 6 shows the graphic beside
  its narration; until then the storms page links to NHC's outlook.
- Editing `weatherbot.toml` from the page, removing a location from the page,
  and a second location's setup beyond the first. Phase 7's settings page; the
  CLI keeps doing all three.
- WebSockets, server-side rendering, a service worker, offline use, and an
  installable web app. The event stream is one-way by design (brief §6), and the
  interface is served by the local process it reports on.
- A token or a login on loopback. The guards in the Overview's design rationale
  stand in for one until Phase 8's LAN mode needs it.
- Firefox and WebKit in the browser smoke, and a formal accessibility audit. The
  smoke runs Chromium; the pages use Radix primitives, semantic landmarks,
  keyboard navigation, and text beside every level colour, and Phase 8's
  documentation pass can add an audit.
- Sharing one event-stream connection across tabs. Each tab holds one
  connection, and HTTP/1.1 allows six to one origin; the operator rarely opens
  six dashboards.
- A package version bump. The version stays `2.0.0.dev0` until the release
  candidate in Phase 8; `/api/health` names the build, and the milestone tag
  marks the phase.
- Issue #44 (the `advisory_issued` wording) and issue #33 (whether surge and
  extreme-wind products move the ladder). The first is its own `fix/` branch
  with a fresh golden review if a timeline's text changes; the second is the
  operator's call.
- Removing the version 1 copies from the operator's `PATH`. The operator's
  housekeeping; `doctor`'s `path` check names it.
- Dependabot PRs (#8, #31, #47, and #48 open on 2026-10-24). They are
  independent maintenance, outside every step.

---

_This roadmap is the execution plan for Phase 5. Each step's `**Status:**` line
is flipped by that step's own PR (Status rule), so this file on `main` is the
phase's ledger — `grep -n '^\*\*Status:\*\*'` reports progress. After all steps
and verification pass, and every finding has a destination, Phase 5 is complete
— declared with the line "Phase 5 is complete. You can now move on to Phase 6."
and nothing after it — and Phase 6 (Claude layer) inherits a loopback API with
its guards and committed OpenAPI contract, an event stream that tells the page
what was stored, a dashboard with room for a labeled briefing beside each level,
a settings page its cost meter joins, the browser channel beside the toast, and
the stored assessments, evidence, and change events its prompts read._
