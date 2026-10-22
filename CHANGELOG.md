# Changelog

All notable changes to Weatherbot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Phase 4 — Monitoring and notifications
- Alembic revision `0004` (expand-only, after the online backup) stores each
  product's content once: `geometry_contents` holds the zlib-compressed
  canonical JSON of a product's kind, CRS, GeoJSON, and fields, keyed by its
  SHA-256 and never its provenance; `snapshot_provenances` holds each
  response's provenance once per snapshot; and `snapshot_geometries` links
  each product to both. `SnapshotRepository` writes every new snapshot that
  way and reads a snapshot stored before the revision from
  `product_geometries` as it is; the downgrade copies every linked product
  back before it drops the tables. A second `status` over unchanged answers
  now grows the database by 64 KiB, where it grew by 2.0 MiB.
- `README.md`'s Status names Phase 4 as in progress.
- Add `MonitorService.run_cycle`, the one path that fetches, stores, assesses,
  and records, under a cycle lock every process shares
  (`weatherbot.services.locks.ProcessLock`, the operating system's lock on
  `cycle.lock`, standard library only). `fetch`, `storms`, `alerts`, and
  `status` now run through it (the first three fetch-only), print what they
  printed before, and say "another cycle is running; try again" with exit 1
  when another cycle holds the lock past `[monitor] cycle_lock_wait_seconds`.
- Alembic revision `0005` (expand-only, after the online backup) adds
  `heartbeats` (per source, watch, and monitor process: last attempt, last
  success, consecutive failures, the cadence its writer expects) and
  `monitor_cycles`. The staleness rule flags a heartbeat past twice its
  cadence; `status` shows a banner and lists every heartbeat in its document's
  new `staleness` field, and `doctor` adds a `heartbeat` check, skipped until a
  scheduled monitor promises a cadence.
- Every writing transaction begins `BEGIN IMMEDIATE`, the busy timeout is 30
  seconds, and two processes that open a database behind the head migrate it
  once under `migrate.lock`.
- Add `weatherbot check --once` (one cycle on demand; exit 0, 1, or 2),
  `weatherbot config show` (each setting's value and origin), and `weatherbot
  config path`; their `check`, `config`, and `config-path` documents join the
  committed JSON Schemas (ten).

### Phase 3 — Threat engine
- Add `scripts/verify_phase03.py`: 52 static checks over the geodesy, replay
  snapshots, ladder rules, threats and change events, calibration and goldens,
  and the stored assessments and commands, in the six modes `--fast`, `--py`
  (with the engine branch-coverage floor), `--live`, `--security`, `--all`
  (with the cached corpus), and `--post` (80 checks: the V1-V7 matrix built
  from JUnit reports, GitHub readbacks, Phase 2's own `--post`, `doctor` with
  its alarm proof, and the replay time budget). `phase-verify.yml` runs entry
  `"03"` beside `"01"` and `"02"` under the required aggregate `phase-verify`.
  `docs/phase03-qa-findings.md` is the phase's disposition ledger.
- Add `weatherbot status`, which fetches a snapshot (or reads the latest stored one
  with `--no-fetch`), assesses and stores every location, and prints each level
  with its deciding rule and evidence, the actions, "at least" with the missing
  inputs, the covering official products and the county-zone alerts outside the
  location's zones, the wind-speed probabilities, each storm's threat, the
  changes since the previous stored assessment, the breakpoint span, and the
  evacuation-order toggle, in UTC and the location's time zone. It exits 1 on a
  partial snapshot. When the toggle was set after a snapshot's stored
  assessment, `status --no-fetch` says that level did not read it.
- Add `weatherbot replay ATCF_ID --location NAME --corpus DIR`, which prints a
  storm's transitions (or every advisory with `--every`) with the toggle off,
  names `convert --full` where the landmark windows do not cover the location,
  and stores nothing; and `weatherbot locations evacuation NAME on|off`.
  `locations list` shows the toggle with its instant and the breakpoint span,
  and `alerts` says which alerts and segments cover the location (issue #10),
  the segments that cover it first outside NWS coverage.
- Alembic revision `0003` (expand-only, after the online backup) adds
  `assessments`, `assessment_evidence`, and `assessment_changes`, and
  `locations.evacuation_order_set_at`; removing a location removes its
  assessments in the same transaction. `AssessmentRepository` and
  `AssessmentService` store each assessment once per snapshot, location, and
  ruleset, diff it against the previous stored one, and fill the breakpoint
  span from the snapshot's catalogue. The toggle's evidence names when it was
  turned on. `status` and `replay` documents join the committed JSON Schemas.
- Add `ReplayService.timeline`, six calibrated threshold intervals and their
  witnesses, eight operator-reviewed golden replay timelines, rule/threshold
  mutation guards, and `docs/ALERT-LADDER.md` with three tables rendered from code.
  The calibration records measured ordering/reversal exceptions approved on
  2026-10-20 while retaining at least 48 hours before each first covering watch.
  The cached full-products cross-check shares one conversion with the existing
  archive and arrival checks. Golden changes require approval of their exact digest.
- Add `weatherbot.engine.geodesy`: `Figure` and `figure_of`, which gives each CRS
  its figure (WGS 84 for `EPSG:4326`; for a native CRS, the one spheroid its WKT
  names, read by a strict parser that refuses a projected CRS, a missing or
  repeated spheroid, a unit other than the degree, or a meridian other than
  Greenwich), and `distance_km` and `initial_bearing_deg` through `pyproj.Geod`.
  `pyproj` joins the runtime dependencies.
- Add `weatherbot.engine.geometry`: `place` (a location's WGS 84 point is used
  unchanged in both geographic CRSs, as PROJ's own ballpark transformation
  shows), antimeridian-safe `covers` and `intersects`, `repair` (polygonal
  parts of `shapely.make_valid`, with the reason and no coordinate in its
  note), `nearest_on_line` (geodesic edges, and whether the nearest point is
  the line's end), and `closest_approach` (the forecast track's nearest
  instant, interpolated along each geodesic in time).
- Test them on the replay corpus against the public landmarks and with
  Hypothesis property tests under a derandomized `weatherbot` profile; CI's
  `test` job now fails below 90 percent branch coverage of `weatherbot.engine`.
  Hypothesis and `pytest-cov` join the dev dependencies.
- `tests/test_architecture.py` scans the engine for clock, random,
  filesystem, environment, and logging use, and allows `pyproj` only as
  `from pyproj import Geod`.
- `scripts/verify_phase02.py` check 31 reads the migration revisions at
  `v2.0.0-phase-2` and requires them unchanged, so a later phase's revision
  leaves `phase-verify (02)` green.
- Replay snapshots. `Snapshot.origin` is `live` or `replay`; a replay snapshot
  has an `nhc-gis-archive` outcome and no roster outcome, its storms carry an
  `ArchiveStorm` (the ATCF id, name, and type as the archive spells them) in
  place of the roster's `StormSummary`, and its records cite only the archive
  and `nhc-arrival-times`. `StormProducts` holds exactly one header and reads
  `atcf_id` and `name` from it. `WindProbabilityProduct.coverage` records the
  area an extract covers, and `WindProbabilityBand.geometry_note` says how a
  band's shape differs from the source's. `SnapshotRepository.save` refuses a
  replay snapshot: history is live only.
- Add `weatherbot.sources.nhc_gis_archive`: `parse_manifest` and parsers from a
  converted collection's bytes and its manifest entries to cones, tracks,
  points, watch-warning segments, wind-speed-probability products, and
  `ArchiveStorm`, through a declared `FIELDS_READ` per kind that a contract
  test keeps equal to the register's lists.
- Add `weatherbot.services.replay`: `ReplayCorpus.open(directory)`, `storms()`,
  and `snapshots(atcf_id)`, one replay snapshot per advisory with its
  associated probabilities and, where the corpus holds them, the arrival-time
  pair of the latest full advisory; every file's path, size, and SHA-256 are
  checked before it is parsed (`ReplayError`).
- The committed replay subset gains 507 landmark-window extracts of the 5 km
  wind-speed probabilities (0.75 MiB), and the manifest records
  `recorded_on`. `fetch_replay_corpus.py convert --full --out DIR` writes a
  complete conversion outside the checkout, and `convert --refresh-subset`
  rewrites only the manifest's subset deliberately. `replay-corpus.yml` also
  runs on changes to the models, the archive parser, and the replay reader.
- Correct the one-vertex watch-warning count in the register and the replay
  notice: 36 records in 12 Dorian advisories, not 39 in 13.
- The alert ladder. `weatherbot.models.ladder` defines `AlertLevel` (the
  brief's five levels with their names and actions), `RuleId` (the eleven
  rules in their fixed order), and `Thresholds` (coastal reach, segment end
  tolerance, cone horizon, and three floors, at provisional defaults, with
  ranges and a SHA-256 `fingerprint()` over the thresholds and the rule
  order). `weatherbot.models.assessment` defines `Assessment`, `Evidence`,
  `OfficialProduct`, `LocationWindProbability`, `UnavailableInput`,
  `BreakpointSpan`, and `Citation`, a provenance that drops the request URL of
  a source whose URLs carry a location, so no evidence holds a coordinate.
  `Location.breakpoint_span` is a `BreakpointSpan`, and the location
  repository stores it.
- Add `weatherbot.engine.assess` (`assess(snapshot, location, thresholds)` and
  `read`) and `weatherbot.engine.rules` (`RULES`): the first rule with a match
  decides the level, its matches are the evidence, every official product
  considered is listed, and every input the rules lacked (NWS alerts, a failed
  roster or map source, a cone, forecast points, a probability product, the
  outlook) is named, making the level a floor. `engine.official` applies issue
  #10's rule to NWS alerts (a county query's alert outside the location's
  zones is context and sets no level) and the coverage rule to NHC segments;
  `engine.breakpoints` gives a location's breakpoint span and names a
  segment's ends; `engine.cones`, `engine.probabilities`, and `engine.outlook`
  read the cones, the location's wind-speed-probability bands, and the
  seven-day development regions.
- `weatherbot.toml` gains the `[engine]` table, with a
  `WEATHERBOT_ENGINE_<KEY>` override for each threshold.
- The breakpoint parser reads `objectid` (the catalogue's coastal order) and
  `idp_filedate` (its load date); the register's field list is amended.
- `tests/engine/scenarios.py` names the scenarios the engine tests and Phase
  3's mutation suite share, from the recorded fixtures and the replay corpus.
- Storm threats. `weatherbot.models.assessment` gains `StormThreat` (a storm's
  advisory, its Saffir-Simpson category and development text at tau 0,
  whether its cone covers the location, the distance and initial bearing from
  its tau-0 center, the forecast track's closest approach and its lead, and
  whether it is a hurricane by then), `ArrivalReading`, and `ChangeEvent`;
  `Assessment.threats` holds one threat per storm, and `OfficialProduct`
  records an alert's `references`. A threat's distances, bearing, and instants
  stay out of every `repr`, and no threat holds a wind-speed probability
  (issue #12). `engine.threats` builds the threats; a storm without forecast
  points, or without an arrival-time product of a kind, is an unavailable
  input of its assessment. The level's rules do not change.
- Add `weatherbot.engine.arrivals`: `read_arrival` reads an arrival-time product
  along the straight path from the storm's tau-0 center to the location — the
  latest labelled isochrone the path crosses starts the interval, the next
  ends it — and gives `before`, `between`, `after`, `outside` the 5 percent
  contour, or `unresolved` with the product's own reason (a map layer, a
  withheld KMZ, an unresolved line), never parsing a label (issue #11). A path
  that leaves the 5 percent contour and comes back, or a reading later than a
  closed isochrone that holds the location, is unresolved. A storm with no
  product reads the forecast track's closest approach, labelled "track closest
  approach, not a wind arrival". `engine.geometry` gains `stretches_inside`.
- Add `weatherbot.engine.changes`: `diff(previous, current)`, exported from
  `weatherbot.engine`, returns the typed change events in a fixed order — the
  level (up, down, or initial), each new advisory, each covering official
  product added, replaced, or removed (an NWS alert by id and its
  `references`; NHC segments by storm and code, so a Hurricane Watch upgraded
  to a Warning is one change), and each cone entered or left — and refuses two
  locations or a current assessment older than the previous one.
- `tests/engine/test_cached_arrivals.py` (`pytest -m corpus`) reads every
  cached arrival product at both landmarks through a full conversion, and
  `replay-corpus.yml` now also runs on changes to the engine and its tests.

### Phase 1 verification
- Add the 50-check foundation verifier, full V1-V7 post sweep, QA findings ledger,
  and the required aggregate phase-verify workflow. Keep fixture bytes unchanged
  while guarding LF line endings for repository text.

### Phase 2 verification
- Add `scripts/verify_phase02.py`: 47 static checks over the models, clients,
  persistence, and commands, and the 26-row V1-V7 matrix in `--post` (with
  Phase 1's own sweep, GitHub readbacks, and `doctor` on the operator's
  database and against a database stamped with an unknown revision). Add the
  Phase 2 QA findings ledger and matrix entry `"02"` under the required
  aggregate `phase-verify`.


### Added
- The first commands: `weatherbot locations add|list|remove`, `fetch`,
  `storms`, `alerts`, and `doctor`. `locations add NAME --lat LAT --lon LON
  [--polygon county|forecast]` checks the name and the point before any
  request, looks up the point's NWS coverage, stores a zone's shape on
  request, and reverse-geocodes the point once through Nominatim.
  `locations list` is the only command, and `locations list --json` the
  only document, that shows a location's coordinates. `fetch` stores a
  snapshot and prints each source's outcome. `storms` prints the active
  storms, the products the snapshot holds for each (with the arrival
  times' origin), the outlook per basin, and the wind-probability synoptic
  time. `alerts` prints a location's NWS alerts in UTC and its own time
  zone. Outside NWS coverage it lists the storms' watch-warning segments
  verbatim. `storms` and `alerts` take `--no-fetch` to read the latest
  stored snapshot and print its age. `doctor` reports the paths, the
  database's Alembic revision against the head, the number of locations,
  one location-free probe per register source, the resolution of every
  register layer name, and the Source-drift warnings of the latest
  snapshot. It never probes Nominatim. Output is Rich tables in a terminal
  and plain text otherwise. `--json` prints one document whose JSON
  Schema is committed under `docs/schema/`. The exit status is 0 for
  complete, 1 for a partial or failed snapshot or a failed check, and 2
  for a usage error. `--verbose` logs at DEBUG.
- The snapshot service, `weatherbot.services.snapshots`. It reads the
  roster first, then every other source concurrently under the per-host
  pacing, and records one outcome per source: `ok`, `not_modified`,
  `failed` with the error's kind, or `skipped` with the reason. A failed
  source leaves its part of the snapshot empty. An arrival-time KMZ
  product supersedes the map-layer product of the same storm, advisory,
  and kind (issue #11). The snapshot, its raw responses, and the run's
  Source-drift warnings are stored in one transaction. The locations
  service is `weatherbot.services.locations`.
- Alembic revision `0002` adds `drift_warnings`, the table that keeps each
  snapshot's Source-drift warnings for `doctor`.
- The disclaimer ships in the package as `weatherbot/DISCLAIMER.md`, equal
  byte for byte to the repository's copy (a test compares them). The
  first command prints its essentials (to standard error under `--json`)
  and records the time. Every read command ends with a one-line notice,
  and every `--json` document carries it.
- `scripts/export_schemas.py` writes the five `--json` schemas (JSON
  Schema 2020-12) to `docs/schema/`; a test fails while a committed schema
  differs from a fresh export.
- The CLI configures logging once: the `[logging] level` setting or
  `--verbose`, and one standard-error handler with the coordinate-
  redacting filter. httpx, httpcore, and Alembic stay at WARNING unless
  the level is DEBUG.
- `open_client` takes the `[http] timeout_seconds` setting.
- Live tests of every command for both public landmarks
  (`tests/live/test_cli_live.py`). New runtime dependencies: `rich`, and
  `tzdata` on Windows. New development dependencies: `jsonschema` and
  `types-jsonschema`.
- Local state for the application. `weatherbot.services.config` resolves
  the configuration and data directories through `platformdirs`, with
  `WEATHERBOT_CONFIG_DIR` and `WEATHERBOT_DATA_DIR` as overrides, and reads
  an optional `weatherbot.toml`. Its two settings are `[logging] level` and
  `[http] timeout_seconds`, and `WEATHERBOT_LOG_LEVEL` and
  `WEATHERBOT_HTTP_TIMEOUT_SECONDS` override them. An error names the key
  and never echoes the value. `weatherbot.services.persistence` adds
  SQLAlchemy 2 tables for the data Phase 2 writes, created by an Alembic
  baseline (`0001`) that ships inside the package. `open_database` sets
  foreign keys, WAL, and a busy timeout on every connection. It copies an
  existing database through SQLite's online backup API before any upgrade,
  and keeps that copy if the upgrade fails. It refuses a revision the code
  does not know and never downgrades. The repositories store a whole
  `Snapshot` in one transaction and load it back equal, and also hold
  locations and application settings. The raw-response cache keeps every
  answer with its allowlisted headers. It stores each body once, by
  SHA-256 and zlib-compressed, and serves as the HTTP layer's persistent
  validator store, so conditional requests and 304s work across runs.
  Tests pin both directories to their temporary directory. A new
  import-linter contract keeps SQLAlchemy and Alembic inside
  `weatherbot.services`. CI's `package` job opens a new database through
  the installed wheel on Ubuntu and Windows. New runtime dependencies:
  `sqlalchemy`, `alembic`, and `platformdirs`.
- The NWS client, `weatherbot.sources.nws`. `lookup_point` resolves a point
  to its forecast zone, county, office, and time zone, and returns
  `OutsideNwsCoverage` for the documented `InvalidPoint` 404. `fetch_alerts`
  queries the point, the county, and the forecast zone and merges the
  answers by alert id. Each alert keeps `found_by`, its affected zones, and
  both geocode lists, which issue #10's rule needs in Phase 3, and nothing
  is filtered by zone. A location outside NWS coverage sends no alert
  request. `fetch_zone` reads a zone's metadata and shape with conditional
  requests. `format_point` writes every point with four decimals, the
  precision the API serves (recorded in the register 2026-10-17). It is
  the only function that writes a coordinate into a URL, and the fixture
  recorder now uses it too.
- The Nominatim client, `weatherbot.sources.nominatim`: `reverse_geocode`
  returns the place's display name, country, and the licence text for the
  attribution. It sends one request per location, at setup, never per
  fetch, and returns none when Nominatim finds no place.
- The first recorded NWS alert: a Rip Current Statement (2026-10-17) that
  the point, county, and forecast-zone queries all returned, recorded
  beside the 2026-10-12 set. The register's points, alerts, and Nominatim
  "Fields v2 uses" lists now name nested members as `object.member`.
- The register source `nhc-arrival-times` (issue #11): the arrival-time KMZ
  that the roster links, with its row, an "Arrival-time KMZ" section, and a
  narrowed "Not used" row in `docs/DATA_SOURCES.md` (verified 2026-10-17).
  The recorder records the archived Dorian 036 pair, whose checksums the
  replay corpus manifest pins, and every active storm's linked pair.
  `scripts/check_personal_data.py` now scans every member of a zip capture,
  under the client's bounds.
- The arrival-time client, `weatherbot.sources.nhc_arrival_times`. It opens
  the KMZ in memory under member, size, ratio, and path limits, parses its
  KML with `defusedxml`, and resolves every labelled line to an instant from
  the product's `timezone` and `pubAdvTime`. When the KMZ disagrees with the
  roster or with its own URL, every line stays unresolved and the reason is
  given. `prefer_kmz` applies the snapshot rule: a KMZ product supersedes
  the map-layer product of the same storm, advisory, and kind. Links outside
  the arrival-time pattern are never fetched.
- The text-product client, `weatherbot.sources.nhc_text_products`: the
  newest TCP of each storm's slot and the newest English TWO of each basin,
  from the NWS API. A TCP from a reused slot is logged and not attributed
  to the storm, and an older TCP keeps its own advisory number.
- The outlook-graphic client, `weatherbot.sources.nhc_outlook_graphics`:
  the six `two_{atl,pac,cpac}_{2d0,7d0}.png` maps, fetched with conditional
  requests, with the PNG signature checked and the size read from `IHDR`.
- The GIS RSS client, `weatherbot.sources.nhc_gis_rss`: the three feeds,
  parsed with `defusedxml`. The no-storm placeholder item is recognized.
- The catalog client, `weatherbot.sources.catalogs`: the `StormSurgeRisk`
  catalog, with the five US East and Gulf Coast images resolved by group
  path, and the nowCOAST radar and satellite WMS capabilities. All network
  XML goes through `weatherbot.sources.markup`, which uses `defusedxml` and
  refuses any DTD. `defusedxml` is a new runtime dependency.
- The HTTP layer, `weatherbot.sources.http`: one `httpx` client per run with the
  register's User-Agent (`weatherbot.sources.USER_AGENT`, which the fixture
  recorder now imports with the per-host intervals and the ArcGIS query
  parameters), TLS verification on, redirects refused, and fixed timeouts;
  per-host pacing, at most four attempts with full-jitter backoff and
  `Retry-After`, an 8 MiB body cap, conditional requests through a
  `ValidatorStore`, typed errors in `weatherbot.sources.errors`, and log
  records that never carry a request coordinate above DEBUG.
- The roster client (`nhc_current_storms`), the ArcGIS client (`arcgis`:
  catalogs, layer resolution by name or group path, paging, counts), and the
  NHC map clients (`nhc_map`), which parse every register layer of the
  tropical, summary, breakpoint, and peak-surge services into the shared
  models, including one wind-probability product per threshold held by the
  snapshot (issue #12), and log Source-drift warnings where the products
  disagree. `tests/contract/test_field_coverage.py` keeps each parser's
  fields equal to the register's "Fields v2 uses".
- `.github/workflows/live-smoke.yml`, which runs `pytest -m live` when
  dispatched by hand.
- The version 2 scaffold (2.0.0.dev0): a uv project on Python 3.13 with a
  `uv_build` backend and a committed `uv.lock`; the `src/weatherbot/`
  package skeleton with the `sources`, `engine`, `services`, `cli`, and
  `web` layers and a `weatherbot --version` command; import-linter layer
  contracts and a test that bans I/O libraries from the engine; strict ruff
  and pyright; pytest with a network guard and a temporary working
  directory for every test; and a CI workflow on Ubuntu and Windows whose
  aggregate `gate` job is the required check on `main`.
- `docs/DATA_SOURCES.md`, the data-source register, verified live on
  2026-10-12: a stable id, endpoint, format, fixture class, cadence, and
  terms for every source in the brief's §5; every ArcGIS layer by name,
  with its fields and the query parameters shared by the fixture recorder
  and the source clients; the per-basin answer on arrival-time,
  probabilistic-wind, and surge layers; the NWS, text-product, graphic,
  RSS, archive, overlay, and geocoding endpoints with their etiquette; the
  project User-Agent; and the sources version 2 does not use.
- `scripts/record_fixtures.py`, the fixture recorder, and `tests/fixtures/recorded/`: a
  capture of every `required` source in the register, taken live on 2026-10-12 with the
  project User-Agent and stored with a checksummed `manifest.json` per directory; the six
  seven-day Atlantic outlook maps recovered from the 2025 version 1 reports; a notice of the
  third-party terms; and contract tests that keep the register, the recorder, and the
  recorded service catalogs in agreement and hold the fixtures to a 25 MiB budget.

- A checksum-pinned NHC replay corpus for Irma, Dorian, Ian, and Milton, with
  deterministic compressed advisory geometry, explicit native CRS provenance, an
  ignored cache for original forecast, wind-probability, and arrival-time archives,
  offline and full-cache tests, and a twice-weekly cache-verification workflow.
- `weatherbot.models`, the domain models every layer shares and the lowest
  layer of the import contracts: frozen, strict Pydantic models with a
  `Provenance` on every record; GeoJSON-shaped geometry with an explicit
  CRS and Shapely's validity verdict, never relabeled or transformed; UTC
  instants with NOAA's local text kept beside them and parsed only by the
  tested functions of `weatherbot.models.times`; coded values that keep
  unknown official codes; units in field names only where NHC states them;
  `ArrivalTimeProduct`, resolved from the arrival-time KMZ's own zone and
  publication time (issue #11); `WindProbabilityProduct`, held by the
  snapshot with no storm field (issue #12); and `Snapshot` with one outcome
  per source. `pydantic` and `shapely` join the runtime dependencies.

### Changed
- Phase 1 verification checks 7, 9, and 12 read Phase 1's version, its
  eight-file skeleton, and its Typer-only dependency list from the
  `v2.0.0-phase-1` tag, so the package can grow while `phase-verify (01)`
  stays green; the identity, entry-point, and still-tracked halves stay
  live, and a missing tag fails.
- Version 1 is retired; it remains installable with
  `pip install weatherbot==1.0.0`, and its source is preserved at the
  `v1.0.0` tag. Version 2 is a from-scratch rewrite specified in
  [the v2 brief](docs/brief/weatherbot-v2-brief.md).
- `README.md`, `CONTRIBUTING.md`, and `AGENTS.md` describe version 2.

### Removed
- Version 1's code, tests, documentation, scripts, and packaging
  (setuptools metadata, Makefile, and v1's CI workflow, including its
  Safety scan and the `SAFETY_API_KEY` secret). The v1 default coverage
  polygon and `env.example` leave the tree with them.

## [1.0.0] - 2025-09-29

### Added
- Comprehensive documentation suite
- API reference documentation
- Development guide for contributors
- Configuration reference guide
- User guide with examples
- **Security scanning implementation**:
  - Bandit security vulnerability scanner
  - Safety dependency vulnerability checker
  - Automated CI/CD security checks
  - Makefile commands for local security scanning
  - Security best practices documentation

### Changed
- Enhanced README with better organization
- Improved code documentation and type hints
- Updated development workflow to include security scanning

### Security
- **Security Issues Identified**: 13 security issues found and documented
  - 4 High priority (MD5 usage in cache keys)
  - 1 Medium priority (insecure tempfile usage)
  - 8 Low priority (assert statements, exception handling)
  - 1 Dependency vulnerability (outdated pip)
- **CI/CD Security**: Automated security scanning on every commit
- **Security Documentation**: Comprehensive security guidelines added

### Added
- Initial release of Weatherbot
- 5-level hurricane alert system
- National Hurricane Center (NHC) forecast cone integration
- National Weather Service (NWS) alert monitoring
- AI-powered threat analysis using OpenAI
- Global weather coverage via AI web search
- Windows toast notification system
- Geometric point-in-polygon and county-level intersection detection
- Comprehensive HTML report generation with interactive maps
- State management for alert deduplication
- API response caching for performance
- Coverage validation for NOAA data sources
- Command-line interface with multiple commands
- Configuration management via environment variables
- Logging system with configurable levels
- Pre-commit hooks for code quality
- Comprehensive test suite with pytest
- Type hints throughout codebase
- PEP 8 compliance with Black formatting
- Ruff linting for code quality

### Features
- **Real-time Hurricane Tracking**: Monitors active NHC forecast cones
- **NWS Alert Integration**: Processes official hurricane watches and warnings
- **AI-Enhanced Analysis**: Optional OpenAI integration for intelligent threat assessment
- **Multi-level Alert System**: 5-tier system from "All Clear" to "Hurricane Warning"
- **Toast Notifications**: Windows 10/11 native notifications with sounds
- **Geometric Precision**: Point-in-polygon and county-level intersection analysis
- **Comprehensive Reporting**: HTML reports with storm tracking maps
- **Global Coverage**: AI web search fallback for locations outside NOAA coverage
- **Flexible Configuration**: Point-based or county-based threat detection
- **State Persistence**: Prevents duplicate alerts and tracks storm advisories

### Commands
- `weatherbot run` - Main monitoring cycle
- `weatherbot ai-analysis` - AI-powered threat analysis
- `weatherbot test-alert` - Test notification systems
- `weatherbot check-coverage` - Validate coordinate coverage
- `weatherbot show-map` - Open official NOAA maps
- `weatherbot state show/clear` - State management
- `weatherbot debug` - Debug commands for development

### Configuration
- **Required**: HOME_LAT, HOME_LON coordinates
- **Optional**: OpenAI API key for AI features
- **Optional**: County-level intersection with GeoJSON files
- **Optional**: Notification and alert behavior settings
- **Optional**: Logging configuration

### Data Sources
- **NHC MapServer**: Real-time hurricane forecast cones
- **NWS API**: Official weather alerts and warnings
- **NOAA Maps**: Tropical weather outlook imagery
- **CurrentStorms.json**: Active storm position data
- **AI Web Search**: Global weather service integration

### Coverage Areas
- **Primary**: Atlantic Basin, Eastern Pacific, Central Pacific (NOAA coverage)
- **Secondary**: Global coverage via AI web search fallback
- **Optimal**: US East Coast, Caribbean, Gulf of Mexico

### Technical Details
- **Python**: 3.11+ required
- **Platform**: Windows 10/11 (primary), Linux/macOS (limited)
- **Dependencies**: Typer, Pydantic, Shapely, OpenAI, Requests, Rich
- **Architecture**: Modular design with dependency injection
- **Testing**: Comprehensive test suite with pytest
- **Code Quality**: Black formatting, Ruff linting, MyPy type checking

### Installation
- Standard installation via pip
- Development installation with pre-commit hooks
- Virtual environment support
- Configuration via .env files

### Documentation
- Comprehensive README with setup instructions
- API documentation for all modules
- User guide with examples
- Development guide for contributors
- Configuration reference
- Troubleshooting guide

## Version History

### Pre-1.0.0 Development

#### [0.9.0] - Development Phase
- Core hurricane tracking functionality
- Basic NHC and NWS integration
- Initial AI features
- Command-line interface development

#### [0.8.0] - Alpha Phase
- Geometric analysis implementation
- State management system
- Notification framework
- Testing infrastructure

#### [0.7.0] - Prototype Phase
- Basic weather data integration
- Alert level system design
- Configuration management
- Logging system

#### [0.6.0] - Proof of Concept
- Initial NHC data parsing
- Basic coordinate validation
- Simple notification system
- Core architecture design

## Migration Guide

### From 0.x to 1.0.0

#### Configuration Changes
- Environment variables now use consistent naming
- `.env` file format standardized
- New coverage validation system

#### API Changes
- Standardized function signatures
- Improved type hints throughout
- Better error handling

#### Feature Changes
- Enhanced 5-level alert system
- Improved AI integration
- Better global coverage support

#### Breaking Changes
- Configuration file format updated
- Some function names changed for consistency
- Alert level numbering system revised

## Future Roadmap

### Planned Features (v1.1.0)
- [ ] Docker container support
- [ ] Web dashboard interface
- [ ] Mobile app notifications
- [ ] Email notification support
- [ ] Slack/Discord integration
- [ ] Multiple location monitoring
- [ ] Historical storm tracking
- [ ] Advanced weather maps

### Planned Improvements (v1.2.0)
- [ ] Enhanced AI models
- [ ] Better global coverage
- [ ] Performance optimizations
- [ ] Advanced reporting features
- [ ] Real-time streaming updates
- [ ] Machine learning predictions
- [ ] Social media integration
- [ ] Emergency contact system

### Long-term Goals (v2.0.0)
- [ ] Multi-hazard monitoring (earthquakes, floods, etc.)
- [ ] Commercial API offering
- [ ] Mobile applications
- [ ] Enterprise features
- [ ] Advanced analytics
- [ ] Predictive modeling
- [ ] Integration with emergency services
- [ ] Community features

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details on:
- Development setup
- Code standards
- Testing requirements
- Pull request process

## Support

- **Documentation**: See `docs/` directory
- **Issues**: Report bugs on GitHub
- **Discussions**: Join project discussions
- **Email**: Contact maintainers for support

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **NOAA/NHC**: For providing comprehensive hurricane data
- **National Weather Service**: For official weather alerts
- **OpenAI**: For AI analysis capabilities
- **Python Community**: For excellent libraries and tools
- **Contributors**: All developers who have contributed to this project

## Security

### Reporting Security Issues

Please report security vulnerabilities to the maintainers privately before public disclosure.

### Security Considerations

- API keys are stored in environment variables
- No sensitive data is logged
- Network requests use HTTPS
- Input validation prevents injection attacks

## Performance

### System Requirements
- **RAM**: 512MB minimum, 1GB recommended
- **Storage**: 100MB for installation, 500MB for cache/logs
- **Network**: Broadband internet connection recommended
- **CPU**: Modern multi-core processor recommended

### Performance Metrics
- **Startup Time**: < 5 seconds
- **Analysis Time**: 10-30 seconds per cycle
- **Memory Usage**: 50-100MB typical
- **Network Usage**: 1-5MB per analysis cycle

### Optimization Tips
- Use appropriate alert cooldown periods
- Enable caching for frequent API calls
- Adjust logging levels for performance
- Monitor system resources during continuous operation
