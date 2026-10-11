# Weatherbot v2 — Project Brief

> **Status:** Agreed 2026-10-11 (operator decisions recorded in §3)
> **Owner:** Nathan Ramos, sole maintainer and sole user for now
> **Audience:** The maintainer and the AI coding agents that write and
> execute the roadmaps in `docs/roadmap/`
> **Supersedes:** Weatherbot 1.0.0 (PyPI, September 2025), which this
> brief treats as the first draft: a source of lessons and test fixtures,
> never of code

This brief is the product specification the project roadmap executes.
Where the roadmap departs from it, the roadmap records the change and
the reason. The brief was written after a full read of the v1 codebase
and a live check of every NOAA endpoint named in §5 on 2026-10-11.

---

## 1. Why a second draft

### What v1 is

A Python CLI that pulls National Hurricane Center (NHC) forecast cones
and National Weather Service (NWS) alerts for one configured point,
maps them onto a five-level alert ladder with actions per level, shows
Windows toast notifications, writes one-off HTML reports, and asks
OpenAI models to interpret the official outlook map. About 9,000 lines
in `src/weatherbot/`, 366 heavily mocked tests, published to PyPI as
`weatherbot` 1.0.0.

### What v1 got right (carry forward as requirements)

- **The five-level alert ladder** with concrete actions per level is
  the product. Its semantics (§7) are kept.
- **The priority order** official NWS and NHC watches and warnings
  first, geometric cone analysis second, AI narrative last. v1 states
  it; v2 makes it structural.
- **The data sources**: NHC map services, NHC current-storms feed, NWS
  alerts API, NHC outlook graphics. v2 uses more of them, not different
  ones.
- **The disclaimer posture**: informational only, never a substitute
  for official guidance. v2 keeps it on every surface that shows an
  assessment.

### What v1 got wrong (each is a requirement in the negative)

| Defect in v1 | Requirement for v2 |
| --- | --- |
| The AI picks the alert level from a prompt full of capitalized warnings; code clamps the answer afterwards. | A deterministic engine decides the level from official products. The model explains; it never decides. The application is fully functional with AI off. |
| The "AI web search" never searches the web; two modules ask GPT-3.5 and GPT-4o to recall storm positions from memory, and one ships hardcoded invest positions from September 2025 as a fallback. | No model output is ever used as a storm position, alert, or level. Every fact shown comes from a fetched official product with a recorded source and time. |
| Prompts, URLs, and fallbacks are season-specific: named storms, advisory slots `AT1`–`AT5`, a Nassau default area, "evacuate to the mainland" guidance. | Nothing about a particular season, storm, or the operator's home is in code or defaults. Locations are data. The public repository carries no personal coordinates. |
| Business logic lives in the CLI module; four NHC clients overlap, one scraping storm web pages. | One source client per feed, a pure engine, services around it, and two thin front doors (CLI, web). No HTML scraping of NHC pages. |
| Cooldown skips the whole analysis, so state goes stale. | Cooldown suppresses repeat notifications only. Assessment and history always update. Escalations always notify. |
| Nearly every test mocks the network; no real payload is recorded; CI ignores a long list of ruff rules and disables most mypy error codes. | Recorded real payloads as fixtures, golden replays of historical storms, strict lint and type gates with no blanket ignores. |
| Heavy dependencies (matplotlib, pandas, folium, a tkinter map widget, BeautifulSoup) for a CLI; reports are static one-off files. | Lean runtime dependencies; the web app is the live report; history lives in a database. |

### What v1 leaves behind that is worth harvesting

- `cache/` holds 38 real JSON responses from the NHC map services and
  the ATCF invest files, recorded during the September–October 2025
  storms. They become recorded fixtures before any v1 code is deleted.
- `reports/` holds HTML reports embedding the official outlook
  graphics of specific dates; useful as fixtures for the optional
  vision feature.
- The alert-ladder wording in `alert_levels.py` and `docs/alerts.md`.

---

## 2. Vision

**One sentence.** A personal hurricane-threat monitor that watches
named locations around the clock, decides a five-level threat from
official NHC and NWS products, shows it in a modern local web app and
a CLI, notifies on change, keeps history, and uses Claude to explain
the situation in plain language.

**Who it is for.** The operator, on their own Windows machine, in a
browser tab and a terminal. No hosted service, no accounts, no other
users. The package stays public on PyPI under the same name, so
nothing personal may ship in it.

**What "better" means versus v1.**

1. Correct by construction: levels come from official products through
   testable rules, never from a model.
2. Alive without being heavy: the browser receives pushed updates only
   when something changed; the machine idles at near-zero cost.
3. Explains itself: every assessment carries the evidence behind it,
   and Claude turns that evidence into a briefing and answers questions
   grounded on it.
4. Testable in the off-season: historical storms replay through the
   same engine and the same UI.
5. Honest about limits: labeled AI content, a persistent disclaimer, no
   invented data, no claims of coverage the sources do not provide.

---

## 3. Decisions (made 2026-10-11)

The operator accepted the assessment's recommendations and delegated the
open calls. These are final for v2.0 unless the roadmap records a
change.

| # | Decision | Choice | Rationale |
| --- | --- | --- | --- |
| D1 | Application stack | Python 3.13 managed by uv; FastAPI backend; React 19 + Vite + TypeScript + Tailwind single-page app served by the backend | Same frontend stack as the maintainer's other dashboard project; a real map and live updates need a real frontend; Node is a build-time dependency only, the built SPA ships inside the wheel |
| D2 | Coverage scope | NHC basins only: Atlantic, Eastern Pacific, Central Pacific. No "global coverage", no model-driven web search in the core | v1's global coverage was not real; the operator's locations are in the Atlantic basin; a real web-search fallback can be a later option |
| D3 | Locations | The data model supports several named locations from day one; first run configures one; the multi-location UI arrives in a later phase. First location: Miami-Dade County, Florida. First additional location when the UI lands: Nassau, Bahamas | The engine is parametrized by location; shipping one keeps the MVP small; Nassau exercises the non-US watch and warning path (NHC breakpoints instead of NWS zones) |
| D4 | Phone push | In scope, in a later phase, through ntfy (free, no account, self-hostable); Pushover as the alternative | A hurricane alert that reaches only a desktop is incomplete; ntfy is the least setup |
| D5 | Repository and release | Stay public on GitHub and PyPI under `weatherbot`; next release is 2.0.0; CI stays on GitHub-hosted runners (public repository rule); no personal data in defaults, examples, or fixtures | Already public and published; a major version is the honest signal for a rewrite |
| D6 | AI model | Claude Sonnet 5.5 (`claude-sonnet-5-5`) is the default for every AI feature; configurable; Claude Haiku 5.5 is an optional cost lever for high-frequency micro-summaries, off by default | Operator's choice: quality adequate for narration and grounded Q&A at a fraction of Opus cost |
| D7 | AI role | Narrator and analyst only. Levels, positions, alerts, and times come from the engine. AI output is labeled and never cached as fact | See §1 |
| D8 | Network posture | The web app binds to 127.0.0.1 by default; optional LAN access later, behind a token; no telemetry | Personal tool; a phone on the home network is the only reason to ever bind wider |
| D9 | Repository strategy | Rewrite in place on `master`; tag the last v1 commit before v1 code is removed; v1 is never imported, only read | Keeps history, issues, and the PyPI name; avoids a second repository |
| D10 | Planning | roadmodel planning kit in `planning/`; roadmaps in `docs/roadmap/`; one step per agent session with its own branch and PR; the roadmap on `master` is the ledger | The maintainer's standard workflow across projects |

---

## 4. Scope

### In scope for 2.0

- Named locations (point plus optional polygon such as a county or
  island), stored locally, several supported, one configured at first
  run.
- Source clients for every feed in §5, with recorded fixtures and a
  response cache keyed by product and advisory.
- A pure threat engine (§7) producing a level, an evidence list,
  per-storm threat records, time estimates, and a diff against the
  previous assessment.
- A monitor service: scheduler aligned to NHC's advisory cadence, change
  detection, notification policy, SQLite history.
- Notifications: Windows toast, browser notifications, in-app log;
  phone push via ntfy in a later phase.
- CLI: status, storms, alerts, check (once or loop), serve, brief, ask,
  locations, replay, notify test, doctor, config.
- Web app: dashboard, map, storms, alerts, timeline and history,
  briefing and chat, settings, replay; dark and light themes; pushed
  updates over server-sent events.
- Claude integration: briefing, per-storm explanation, change summary,
  grounded chat with tools over the live snapshot, optional outlook
  graphic narration; cost meter; structured outputs; prompt caching;
  streaming.
- Historical replay: feed archived advisories of past storms through
  the engine and the UI with a time scrubber.
- Packaging: `pip install weatherbot` installs the CLI and the built
  web app; Windows always-on setup through Task Scheduler.

### Out of scope for 2.0 (non-goals)

- Public hosting, multi-user accounts, authentication beyond an
  optional LAN token.
- Coverage outside the three NHC basins; model-driven web search.
- Mobile applications, SMS, email, Slack or Discord integrations.
- Machine-learning track or intensity prediction; any forecast of
  Weatherbot's own.
- Automated evacuation-order ingestion. No official API publishes
  county evacuation orders reliably; v2 offers a manual "evacuation
  order in effect" toggle per location and shows where to check.
- Commercial API, enterprise features, multi-hazard monitoring (items
  on v1's wishlist that v2 does not inherit).

---

## 5. Data sources (verified live on 2026-10-11)

All sources are public, keyless NOAA services except the basemap tiles
and the optional reverse geocoder. Every client identifies itself with
a project User-Agent that carries the repository URL, never a personal
email. Cadence drives the scheduler: NHC full advisories at 5 and 11
AM/PM Eastern, intermediates at 2 and 8 when watches or warnings are in
effect, the Tropical Weather Outlook at 2 and 8 AM/PM, NWS alerts at
any time.

| Source | What it provides | Use in v2 |
| --- | --- | --- |
| `https://www.nhc.noaa.gov/CurrentStorms.json` | Active storms: id, name, classification, intensity, movement, last update, product links | Storm roster; advisory-change detection |
| ArcGIS MapServer `tropical/NHC_tropical_weather` | Per storm slot (`AT1`…, `EP1`…, `CP1`…): Forecast Points, Forecast Track, Forecast Cone, Watch-Warning lines, Past Points and Track, Past Cumulative Wind Swath, Forecast and Past Wind Radii, Advisory Wind Field, Earliest Reasonable and Most Likely Arrival Time of tropical-storm-force winds, Inundation. Group layers for the Tropical Weather Outlook: Two-Day Current Location, Seven-Day Current Location, Development Motion, Seven-Day Potential Development Region (polygons with formation chances) | Geometry for the engine and the map; watch and warning breakpoints cover the Bahamas, Cuba and other non-US coasts without scraping |
| ArcGIS MapServer `tropical/NHC_tropical_weather_summary` | The same products consolidated across storms, plus Probabilistic Winds at 34, 50 and 64 knots | Wind-speed probability at a location as quantitative evidence; one query instead of one per slot |
| ArcGIS MapServers `tropical/NHC_Breakpoints`, `tropical/NHC_PeakStormSurge`, `tropical/StormSurgeRisk` | Coastal breakpoint catalogue; peak surge forecast; surge risk | Breakpoint names for evidence text; surge layers on the map and in the evidence for coastal locations |
| NHC GIS archive `https://www.nhc.noaa.gov/gis/archive_forecast.php?year=YYYY` and `gis-at.xml` | Per-advisory shapefiles and KMZ for past storms; RSS of current GIS products | Historical replay fixtures (Irma 2017, Dorian 2019, Ian 2022, Milton 2024); change detection |
| NHC text products (TCP public advisory, TWO outlook text) via `https://www.nhc.noaa.gov/text/refresh/…` | Advisory number, headline, watches and warnings in words | Narrative context for Claude; cross-check of advisory numbers |
| NHC outlook graphics `https://www.nhc.noaa.gov/xgtwo/two_{atl,epac,cpac}_{2d0,7d0}.png` | Official two- and seven-day outlook maps | Shown in the UI; optional vision narration by Claude (never a source of levels) |
| NWS API `https://api.weather.gov/points/{lat},{lon}`, `/alerts/active?point=`, `/alerts/active/zone/{zone}`, `/zones/…` | Point metadata (forecast zone, county zone, office, radar), active alerts at a point, active alerts for a county or zone | Official watches and warnings for US locations. Query both the point and the county zone: on 2026-10-11 the Miami point returned no alerts while the county zone carried one |
| OpenStreetMap tiles; NOAA or Iowa Environmental Mesonet radar and GOES WMS layers (to confirm in Phase 1) | Basemap; radar and satellite overlays | Map layers, raster, no WebGL requirement |
| Nominatim reverse geocoding | A display name for coordinates at first-run setup | Once per location, cached; respects the usage policy; never per cycle |

On 2026-10-11 the current-storms feed listed three active systems, one
of them a major hurricane, so early phases can record live fixtures.
The Atlantic season ends 30 November; later phases must rely on replay.

---

## 6. Architecture

One Python package, `weatherbot`, in a `src/` layout, with four layers
and two front doors.

```
sources/   async httpx clients, one per feed, returning typed models;
           every response shape has a recorded fixture
engine/    pure functions: Snapshot + Location -> Assessment
           (level, evidence, per-storm threats, timing, diff)
services/  scheduler, change detection, notification policy and
           channels, SQLite persistence, Claude integration
cli/       Typer commands over the services
web/       FastAPI API (REST + server-sent events) serving the built SPA
frontend/  Vite + React + TypeScript + Tailwind source; built output is
           packaged into weatherbot/web/static
```

Principles:

- The engine imports nothing from sources, services, or the web. It is
  deterministic and fully unit-tested with recorded and replayed data.
- Sources never interpret. They fetch, validate, and return models with
  provenance (URL, fetched-at, product issuance time, advisory number).
- Services own time, state, and side effects. The scheduler runs
  inside the `serve` process and also as a one-shot `check --once` for
  Task Scheduler.
- The web app and the CLI share the same services and the same SQLite
  database, so a level shown in the terminal and in the browser is the
  same assessment.
- Pushed updates: the server emits a server-sent event when a new
  assessment, storm, or alert is stored. The browser never polls.
- Persistence: SQLite through SQLAlchemy 2, migrations through Alembic,
  tables for locations, snapshots, storms, advisories, alerts,
  assessments, evidence, notifications, briefings, settings, and a raw
  response cache.
- Configuration: a local config file in the user's config directory
  plus environment variables; secrets only through environment or the
  OS credential store; nothing personal in the repository.

---

## 7. Threat engine specification

### The ladder (semantics carried from v1)

| Level | Name | Triggers, highest first | Actions shown |
| --- | --- | --- | --- |
| 5 | Hurricane Warning | Hurricane Warning in effect for the location (NWS zone or NHC breakpoint segment) | Shelter if not evacuated; expect outages; follow local orders |
| 4 | Warning / Watch / Evacuation | Tropical Storm Warning, or Hurricane Watch, or the operator's evacuation-order toggle | Evacuate vulnerable areas; secure transport; assume routes close |
| 3 | Watch / Hurricane Threat | Tropical Storm Watch, or the location inside the forecast cone of a hurricane with arrival inside the forecast window, or wind probabilities above a threshold | Stock supplies; pack; set an exit plan |
| 2 | Tropical Storm Threat | Location inside the cone of a tropical storm or depression, or inside a Seven-Day Potential Development Region, or 34-knot wind probability above a low threshold | Monitor daily; review plans |
| 1 | All Clear | None of the above | Normal activities |

Rules are evaluated in priority order and stop at the first match.
Every match records evidence: the product, its issuance time, the
advisory number, the geometry test that fired, distances, and the time
estimate. Thresholds (wind probabilities, cone horizon, development
chance) are configuration with defaults set in Phase 3 after replay
calibration; the brief fixes none of them.

### Inputs

- Official alerts: NWS active alerts for the point and its county zone;
  NHC watch and warning segments whose breakpoint span contains the
  location's coast (for non-US locations).
- Geometry: forecast cone polygons, forecast track and points, wind
  radii, arrival-time contours, outlook development regions,
  probabilistic wind polygons; tested against the location point and,
  when configured, its polygon.
- Storm metadata: classification, intensity, movement, advisory number
  and time.

### Outputs

- `Assessment`: level, evidence list, per-storm threats (category,
  in-cone, distance, bearing, earliest and most-likely arrival, wind
  probabilities), the products and times it was computed from, and a
  diff against the previous assessment for the same location.

### Verification

- Golden replays of archived advisories for Irma 2017, Dorian 2019,
  Ian 2022, and Milton 2024 against Miami-Dade and Nassau, asserting
  the ladder over time.
- Recorded live fixtures from the 2026 season.
- Property tests on the geometry helpers (antimeridian, polygon
  validity, distance symmetry).

---

## 8. Claude integration

- **Model:** `claude-sonnet-5-5` by default (D6), through the official
  `anthropic` Python SDK, with adaptive thinking, structured outputs
  for every machine-read response (`client.messages.parse()`), prompt
  caching on the stable system prompt and ladder definitions, and
  streaming to the UI. The key comes from `ANTHROPIC_API_KEY` or an
  `ant auth login` profile, never from a file in the repository.
- **Features:** situation briefing for a location; per-storm
  explanation; "what changed since the last advisory" summary; grounded
  chat whose tools read the stored snapshot, assessment, and evidence
  (no tool can fetch arbitrary URLs); optional narration of the
  official outlook graphic, labeled as interpretation.
- **Guardrails:** every AI block is labeled and timestamped; the model
  never writes to the assessment, storm, or alert tables; a daily token
  budget and a cost meter are visible in settings; all features degrade
  to "AI unavailable" without affecting levels or notifications.
- **Prompt hygiene:** no season-specific content; the system prompt is
  frozen text plus the ladder; volatile context arrives after the cache
  breakpoint.

---

## 9. Notifications

- Channels: Windows toast (first), browser notification from the web
  app, in-app notification log, ntfy push (later phase; Pushover as the
  alternative).
- Policy: notify on level change in either direction, on a new advisory
  for a storm whose cone contains the location, and on a new or changed
  official alert for the location. Cooldown applies to repeats of the
  same event only. Escalations always notify. Quiet hours apply to
  levels 1 and 2 only.
- Every notification is stored with its trigger and delivery result;
  `notify test` exercises each channel.

---

## 10. Web app

- Pages: Dashboard (level hero card with evidence, storms, alerts, next
  advisory time), Map (cones, tracks, points, watch and warning lines,
  wind-probability and surge layers, radar and satellite overlays, your
  locations, time slider), Storms, Alerts, Timeline (assessment history
  and a feed of changes), Briefing and Chat, Replay, Settings.
- Behaviour: the page loads from the local API, subscribes to the event
  stream, and re-fetches only what changed; Leaflet with raster tiles;
  dark and light themes; responsive down to phone width.
- Budgets: first paint under two seconds on the operator's machine;
  idle CPU near zero in both server and browser; no WebGL requirement.
- Build: Vite output copied into the package at build time; CI builds
  the SPA and the wheel; development runs the Vite dev server proxied to
  FastAPI.

---

## 11. CLI

`weatherbot` with subcommands: `serve`, `check [--once]`, `status`,
`storms`, `alerts`, `brief`, `ask`, `locations add|list|remove`,
`replay <storm>`, `notify test`, `doctor`, `config`. Rich output in the
terminal; `--json` on read commands for scripting. The CLI uses the
same services and database as the server.

---

## 12. Quality, security, privacy

- Tooling: uv, ruff (strict, no blanket ignores), mypy or pyright in
  strict mode, pytest with recorded fixtures and golden replays,
  pre-commit with a security gate (secret scanning, dependency audit),
  GitHub-hosted CI on Ubuntu and Windows.
- Security: localhost binding by default; CORS restricted to the local
  origin; no secrets in the repository; dependency audit in CI; the
  model's tools are read-only over local data.
- Privacy: locations and settings live only on the operator's machine;
  no telemetry; the public repository and package contain no personal
  coordinates, keys, or names of places beyond documentation examples.
- Disclaimer: shown on first run in the CLI, on the web app's footer and
  every assessment view, and in the package README and `DISCLAIMER.md`.

---

## 13. Proposed phases

The roadmap refines these into phases with steps, branches, and
acceptance criteria. Each phase is independently shippable.

1. **Discovery and fixtures.** Record live payloads for every source in
   §5, harvest v1's cached responses into fixtures, write the
   data-source register, tag v1, decide the detailed schema.
2. **Scaffold and sources.** uv project on Python 3.13, strict tooling,
   CI, domain models, source clients with fixture tests, SQLite schema,
   first CLI read commands. This step also moves the roadmodel kit's
   environment to the project's new `.venv` (pip seeded, `roadmodel` in
   a `planning` dependency group) and drops the registry override in
   `~/.config/roadmodel/projects.txt`.
3. **Threat engine.** Rules, evidence, geodesy, polygons, replay harness
   over the GIS archive, golden tests, the written ladder specification.
4. **Monitoring and notifications.** Scheduler, change detection,
   Windows toast, notification log, `check --once`, Task Scheduler
   registration, `doctor`.
5. **Web app MVP.** FastAPI API with server-sent events, the SPA with
   dashboard, map, storms, alerts, timeline, settings; packaged into the
   wheel; `serve` opens the browser.
6. **Claude layer.** Briefing, change summary, grounded chat, optional
   outlook narration, cost meter, labeling; `brief` and `ask`.
7. **Depth.** Wind-probability and arrival charts, surge layers, replay
   scrubber, multi-location UI (Nassau), history views, on-demand
   report export, ntfy push, quiet hours.
8. **Release 2.0.** Documentation, PyPI release, always-on setup guide,
   optional LAN access behind a token.

---

## 14. Risks and open questions

- **Endpoint drift.** NOAA renames layers and retires services. Source
  clients discover layers by name, fail loudly, and are covered by
  fixtures that CI can re-record on demand.
- **Off-season development.** Most work happens with no live storms;
  replay and fixtures are not optional. The roadmap places them first.
- **Rate limits and etiquette.** The NWS API requires a User-Agent and
  discourages tight polling; Nominatim allows one request per second
  and no bulk use. The scheduler respects both.
- **Windows toast libraries** churn. Isolate the channel behind an
  interface with a tested fallback.
- **Claude costs** during an active storm. A daily budget, caching, and
  Sonnet 5.5 keep this in the cents-to-dollars range; the meter makes
  it visible.
- **Public repository.** Fixtures and documentation must not leak the
  operator's coordinates; a pre-commit check guards the patterns.
- **Open question:** whether the arrival-time and probabilistic-wind
  layers are populated for every storm in every basin, or only for some
  products. Phase 1 records what each layer actually returns.

---

## 15. Success criteria for 2.0

- `pip install weatherbot` then `weatherbot serve` opens a working
  dashboard with no Node, no API key, and no personal data required.
- During an active storm the level, evidence, map, and notifications
  update within one scheduler interval of a new NHC advisory or NWS
  alert, with no browser polling.
- Replaying Irma 2017 against Miami-Dade reproduces the expected ladder
  over time in the test suite and in the UI scrubber.
- With `ANTHROPIC_API_KEY` set, the briefing and chat work and are
  labeled; without it, everything else is unchanged.
- The test suite passes on GitHub-hosted Ubuntu and Windows runners with
  strict lint and type gates and no network access.
- The repository contains no personal coordinates, keys, or
  season-specific logic.
