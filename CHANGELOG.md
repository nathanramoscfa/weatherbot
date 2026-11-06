# Changelog

All notable changes to Weatherbot will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Phase 7 — Depth
- Add the self-contained HTML threat report (`ReportService`, `render_report`,
  `GET /api/report`, `weatherbot report`, and dashboard export links) (Phase 7
  Step 8):
  - Report builder and renderer (`src/weatherbot/services/report.py`): add
    `ReportService(engine, *, now)` with `build(location=None, *,
    with_briefing=False) -> ReportData` (building each location's entry from
    `AssessmentRepository.latest` through `briefing_context(..., snapshot=None)`
    with a `ContextTooLarge` fallback, `AssessmentRepository.level_points`, and
    — only when `with_briefing=True` — `OutputRepository.latest_briefing` kept
    when unwithheld and marked stale when written for an older assessment) and
    `render_report(data) -> str` producing a single offline HTML5 file with
    inline screen and `@media print` CSS, an inline `<svg>` level sparkline and
    visually hidden `<table>` alternative, `<meta
    http-equiv="Content-Security-Policy" content="default-src 'none'; style-src
    'unsafe-inline'">`, `NOTICE` at the top, `ESSENTIALS` and `DISCLAIMER_URL`
    in the footer, `public_page` `https` links (`rel="noopener noreferrer"`),
    and every dynamic string passed through `html.escape`, while leaving out
    coordinates, `Location.display_name`, zone IDs, forecast offices, raw
    kilometre distances, engine-written sentences, query URLs, and tokens/topics
    (and printing cleanly to PDF from the browser).
  - Web route (`src/weatherbot/web/routes/report.py`,
    `src/weatherbot/web/app.py`): add sync `GET /api/report?location=&briefing=`
    answering `text/html; charset=utf-8` with `Content-Disposition: attachment;
    filename="weatherbot-report-<YYYYMMDDTHHMMZ>.html"` and
    `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline';
    sandbox`, 404 for an unknown location without echoing it, and 409 when no
    assessment is stored.
  - CLI command (`src/weatherbot/cli/report.py`,
    `src/weatherbot/cli/__init__.py`): add `weatherbot report [LOCATION] --out
    PATH [--force] [--with-briefing]` writing atomically via a temporary file
    and `os.replace`, refusing an existing file without `--force` and a missing
    parent directory with exit 2, printing the path and disclaimer notice, and
    never loading the Anthropic SDK.
  - Dashboard export controls (`frontend/src/pages/Dashboard.tsx`): add
    `Export report` download links (`<a href="/api/report?location=..."
    download>`) for all locations and on each location card, an unticked
    `Include the AI briefing` checkbox noting that briefing words quote NWS
    alerts and can name a county or a forecast office, and copy explaining what
    the report leaves out and that it opens offline anywhere and prints to PDF
    from the browser.
- Add the `/replay` historical storm scrubber page, replay timeline and
  assessment routes, shared assessment components, and complete the `changes.py`
  no-cone detail sentence (Phase 7 Step 7, closes #44):
  - `src/weatherbot/engine/changes.py`: complete the unfinished `_storm_detail`
    clause on line 85 from `", whose cone does not"` to `", whose cone does not
    cover the location"` (#44), leaving all eight frozen golden replay timelines
    unchanged.
  - Replay timeline cache and notes (`weatherbot.services.replay`,
    `weatherbot.cli.replay`): move `replay_notes` (`FULL_CONVERSION` and
    `_MISSING`) from `cli/replay.py` to `services/replay.py` and add
    `ReplayTimelines(corpus, thresholds, *, max_size=8)` computing
    `timeline(atcf_id, location) -> tuple[ReplayStep, ...]` once per
    `(atcf_id, ruleset_fingerprint, location.name, location.point,
    location.polygon)` key under a per-key lock with `without_evacuation_order`
    applied internally and LRU eviction past `max_size`.
  - Replay timeline and assessment web routes (`weatherbot.web.routes.replay`,
    `weatherbot.web.routes.assessments`, `weatherbot.web.schemas`,
    `weatherbot.web.app`): expose public assessment response builders in
    `routes/assessments.py`, hold `ReplayTimelines` on `WebState`, add `GET
    /api/replay/{atcf_id}/timeline?location=` (`ReplayTimelineResponse`: compact
    `steps` and `notes`, declared before `/{advisory}`), add `GET
    /api/replay/{atcf_id}/{advisory}/assessment?location=`
    (`ReplayAssessmentResponse` with `origin: "replay"` and `notice`, omitting
    `id` and `stored_at`), and stop passing live assessments to
    `build_map_response` in `GET /api/replay/{atcf_id}/{advisory}` so replay
    map markers carry `level: null` rather than today's live level.
  - Shared assessment components and `/replay` UI
    (`frontend/src/assessment/LevelSummary.tsx`, `EvidenceList.tsx`,
    `OfficialProductList.tsx`, `ThreatTable.tsx`, `frontend/src/pages/Dashboard.tsx`,
    `frontend/src/pages/Replay.tsx`, `frontend/src/charts/LevelHistoryChart.tsx`,
    `frontend/src/app/AppShell.tsx`, `frontend/src/app/routes.tsx`): extract the
    four assessment display components from `Dashboard.tsx` and reuse them in
    `Replay.tsx` alongside storm and location pickers, `LevelHistoryChart` with
    an `activeAsOf` marker, `AdvisorySlider`, a 1.5 s `Play` control (stopping at
    the end, on user input, or when the tab hides, with no background timer
    otherwise), `useLeafletMap`, `notes`, corpus configuration guidance when
    `health.corpus` is `false`, a non-dismissible `"Replay: <storm> advisory <n>,
    issued <instant> — not live"` banner, and neither an AI panel nor an
    evacuation-order switch.
- Add SVG threat-level, wind-probability, and 34-kt arrival charts, location
  comparison strip, and cursor-paginated timeline history (Phase 7 Step 6):
  - Compact chart series and timeline cursor pagination
    (`AssessmentRepository.level_points`, `AssessmentRepository.wind_series`,
    `AssessmentRepository.history(before=...)`,
    `NotificationService.recent(before=...)`, `weatherbot.web.routes.charts`,
    `weatherbot.web.routes.timeline`, `weatherbot.web.schemas`): add
    `level_points(location_name, limit)` reading `id`, `as_of`, `level`, `rule`,
    and `complete` by column without decoding JSON, `wind_series(location_name,
    limit)` keeping one `LocationWindProbability` per `(threshold_kt,
    synoptic_at)`, `GET /api/charts?location=&limit=` (`1`–`500`, default `200`,
    holding no distance, bearing, or coordinate), and `GET
    /api/timeline?before=` with `TimelineResponse.next_before` encoding
    `(occurred_at, kind, id)` so pages ending inside a shared cycle instant skip
    nothing.
  - Pure SVG chart scales and components (`frontend/src/charts/scale.ts`,
    `LevelSparkline.tsx`, `LevelHistoryChart.tsx`, `WindProbabilityChart.tsx`,
    `ArrivalTimeline.tsx`, and `frontend/src/api/keys.ts`): add pure scale
    functions (`timeScale`, `linearScale`, `stepPath`, `bandPath`, `ticksFor`),
    `queryKeys.charts(name)` under the `"timeline"` invalidation prefix, and
    four accessible SVG charts (`role="img"`, `<title>`, visually hidden
    `<table>`, Tailwind `stroke-`/`fill-` classes beside `ThreatLevelBadge`
    with zero `style=` attributes), wired into `Dashboard.tsx` (comparison
    strip, card sparklines, and storm arrival timelines) and `Timeline.tsx`
    (location level-history and wind-probability charts plus `"Show older"`
    pagination).
- Add map depth layers, wind-speed probability bands, nowCOAST radar and
  satellite WMS overlays, and the stored advisory slider (Phase 7 Step 5):
  - Vector depth and wind-probability routes (`weatherbot.web.map_layers`,
    `weatherbot.web.routes.map`, `weatherbot.web.routes.replay`,
    `weatherbot.web.schemas`): add `MapResponse.available_layers`
    (`ALL_MAP_LAYERS`, `STORED_ADVISORY_MAP_LAYERS`, and `REPLAY_MAP_LAYERS`,
    keeping `/api/map`'s recorded payload growth under 1 KB), `GET
    /api/map/depth?snapshot_id=` returning `MapDepthResponse` (`wind_radii`,
    `past_track`, and `past_points` matched by `binnumber == summary.slot` and
    `stormnum == int(atcf_id[2:4])`, antimeridian-unwrapped, with raw `lat` and
    `lon` stripped from `Past Points`, plus `peak_surge` `Polygons` and `Lines`
    reduced to `name` and `layer`), and `GET
    /api/map/wind-probabilities?threshold_kt=34|50|64&snapshot_id=` alongside
    `GET /api/replay/{atcf_id}/{advisory}/wind-probabilities?threshold_kt=34|50|64`
    returning `WindProbabilityResponse` (bands ordered ascending by `lower_pct`,
    simplified with `shapely.simplify(0.03, preserve_topology=True)` and noted in
    `geometry_note` so the recorded 34-kt payload drops from 565 KB to 232 KB,
    well under the 400 KB budget, plus the replay window `coverage` polygon).
  - Stored advisory history (`SnapshotRepository.advisory_steps`,
    `AssessmentRepository.for_snapshot`, `GET /api/map/advisories`, and `GET
    /api/map?snapshot_id=`): deduplicate stored snapshots by `(atcf_id,
    advisory)` newest first from `storm_observations` without decoding product
    geometry, serve historical snapshots through the 8-entry
    `SnapshotLayerCache` with each location's assessment at that snapshot, and
    return a generic 404 on unknown `snapshot_id`.
  - Frontend map layers, WMS overlays, and `AdvisorySlider`
    (`frontend/src/map/layers.ts`, `useLeafletMap.ts`, `AdvisorySlider.tsx`,
    `MapView.tsx`, and `weatherbot.web.guards.CSP_SUFFIX`): add six
    off-by-default layer toggles (`wind_radii`, `past_track`, `peak_surge`,
    `wind_probabilities` with a `34 kt` / `50 kt` / `64 kt` radio selector on a
    shared `L.canvas()` renderer, and browser-loaded NOAA nowCOAST `radar` and
    `satellite` `L.tileLayer.wms` overlays with `https://nowcoast.noaa.gov` added
    to `img-src`), colour tables and legend swatches before `locations`,
    `textContent`-only popups, disabled-toggle explanations on replay (`"not in
    this corpus"`) and stored advisories (`"live only"`), `AdvisorySlider` with
    commit-on-release and `"Back to latest"`, the labelled two-decimal synthetic
    surge fixture (`scripts/synthetic_surge.py`) wired into `scripts/serve_demo.py`,
    the live OpenStreetMap loopback `Referer` test
    (`tests/live/test_osm_referer_live.py`), and issue #95 recording the
    conditional OpenStreetMap caching tile-proxy design in `docs/DATA_SOURCES.md`.
- Add settings editing and database history retention (Phase 7 Step 4):
  - Comment-preserving TOML writer (`weatherbot.services.settings_file`, the
    only importer of `tomlkit==0.15.2`): `EDITABLE` allowlist of 12
    `[notifications]`, `[ai]`, and `[retention]` keys, `apply_changes` with
    optimistic `file_sha256` locking (`StaleSettingsFileError`), environment
    override refusal (`EnvironmentOverrideError`), full-document validation
    through `validate_settings_document`, atomic sibling tempfile replace, and
    `restart_keys` reporting only keys whose running component is constructed at
    startup (`[ai] enabled`, `[ai] daily_cap_usd`, `[notifications] ntfy`, and
    `[notifications] ntfy_server`).
  - `LiveSettings` (`weatherbot.services.config`): reloads `weatherbot.toml` on
    `(st_mtime_ns, st_size)` changes and falls back to the last valid `Settings`
    with a single `WARNING` per broken file signature, wired into
    `MonitorSchedule`, `run_heartbeat_task`, `run_monitor`, and `cli/serve.py` so
    quiet hours, cooldown, AI feature toggles, and `history_days` apply at the
    next cycle without restarting `serve`.
  - Alembic revision `0010_retention_indexes` (`FROZEN`) and `RetentionService`
    (`weatherbot.services.retention`): adds non-unique indexes on
    `raw_responses.sha256`, `snapshot_geometries.content_id`,
    `monitor_cycles.snapshot_id`, and `notifications.assessment_id` (keeping
    second-cycle storage growth under 128 KiB), computes the retention keep-list
    preserving the newest snapshot, every location's latest assessment and
    notification-policy anchor snapshots (so `NotificationService._load_state`
    and `AssessmentService._assess_one` produce identical state and decisions
    before and after pruning), conditional HTTP validator `raw_responses`,
    `/api/outlook` PNGs, today's AI ledger and newest pause control row, and
    `locations`/`settings`/`heartbeats`, creates one pre-prune online SQLite
    backup (`backups/weatherbot-<UTC stamp>-prune.sqlite3`, keeping at most 3
    prune backups), deletes in batches of 50 snapshots under `cycle.lock` with a
    `sleep(0)` yield between batches, and runs `RetentionWorker` daily at `03:30`
    local in `serve` (skipping while any location is at level 3 or above and
    clearing the `watch`/`retention` heartbeat cadence when `history_days = 0`).
  - CLI, web API, and UI: `weatherbot prune [--dry-run] [--days N] [--cutoff
    INSTANT] [--vacuum] [--json]` (`docs/schema/prune.schema.json`, 18 CLI
    documents), `PUT /api/settings`, `GET /api/retention`, and `POST
    /api/retention/run`, `QuietHoursForm.tsx`, editable AI cap and feature
    switches in `AiSettingsSection.tsx`, and `RetentionPanel.tsx` with a
    confirmed `Prune now` dialog on `/settings`.
- Add the `ntfy` phone notification channel and per-location notification
  preferences (Phase 7 Step 3):
  - `weatherbot.services.ntfy` (`NtfyChannel` and `ntfy_channel`): HTTPS root
    JSON `POST` to `[notifications] ntfy_server` (default `https://ntfy.sh`, or
    `http://` on loopback only; `WEATHERBOT_NTFY_TOPIC` and optional
    `WEATHERBOT_NTFY_TOKEN` read only from the environment, never in URLs or
    `weatherbot.toml`), with `follow_redirects=False`, priority mapping (`5`
    urgent for level 5 or an escalation to level 4, `4` high for levels 3–4 or
    an escalation to level 2, and `3` default otherwise), 4,000-byte UTF-8
    boundary truncation, one retry on HTTP 429 (`Retry-After` up to 5 s) or 5xx,
    a 15 s total timeout budget placed last in `Context.channels` and
    `WebState.notification_channels`, and secret redaction for `tk_...` tokens
    and runtime `WEATHERBOT_NTFY_TOPIC`/`WEATHERBOT_NTFY_TOKEN` values in
    `SecretFilter`.
  - Per-location notification preferences (Alembic revision `0009` on
    `locations`: `notify_toast`, `notify_browser`, `notify_phone`, and
    `notify_phone_min_level` in `2..5`): `LocationPreferences` on `Location`,
    `LocationRepository.set_preferences` and `LocationService.set_preferences`,
    `muted` deliveries (`"turned off for this location"` and `"below this
    location's phone level"`) that skip calling the channel and are skipped by
    `NotificationService.latest_delivery`, an `ALL_CLEAR` follow-up exception on
    `ntfy` when the location's previous notification delivered on `ntfy`, and
    `recovered` monitor notifications following a `degraded` alarm delivered on
    any interrupting channel (`toast` or `ntfy`).
  - CLI, web API, and UI: `doctor`'s `ntfy` check, `notify test` checking both
    `toast` and `ntfy` when enabled (`TEST_BODY` updated to
    `("If you can read this, this channel works.",)`), `PUT
    /api/locations/preferences`, `GET /api/notifications/channels`, per-location
    notification controls in `LocationManager.tsx`, the 4-channel status table
    in `Settings.tsx`, muted-delivery styling in `Timeline.tsx`, and
    `docs/NOTIFICATIONS.md`.
- Add multi-location management, Nominatim forward place search, and marine-zone
  `/points` support (Phase 7 Step 2, closing issues #87 and #71):
  - Issue #87 fix: make `NwsCoverage.county_zone` optional (`str | None`),
    widen `NwsCoverage.cwa` to `^[A-Z0-9]{3}$`, declare `OPTIONAL_POINT_FIELDS`
    (`county`) and `OPTIONAL_ZONE_FIELDS` (`state`) in `weatherbot.sources.nws`
    so marine forecast zones without a county (`AMZ630`, `state: null`, `type:
    "coastal"`) parse and fetch alerts from the point and forecast zone only,
    store `""` in `locations.nws_county_zone` when `county_zone` is `None` so
    `nws_coverage_whole` holds without a table rebuild, refuse `polygon="county"`
    when no county exists, and log and return the field-level `SourceError` text
    on `POST /api/locations` `502`.
  - Forward search and `--place` (issue #71): add `GeocodeCandidate` (`display_name`,
    `name`, `latitude`, and `longitude` all `repr=False`), `nominatim.search_url`,
    `parse_search`, `search`, and `SEARCH_FIELDS_READ`, redact `q` in
    `COORDINATE_PARAMETERS` and `_COORDINATE_QUERY`, add `LocationService.search`
    with an in-memory 64-entry 24-hour `SearchCache` (writing no database rows),
    add `POST /api/locations/search` (with a 2-second cooldown) and `POST
    /api/locations/remove` (waiting on `cycle.lock` and deleting the location's
    `<name>` `raw_responses` and unreferenced `response_bodies`), add `--place`
    and `--pick` to `weatherbot locations add`, extract
    `frontend/src/settings/LocationManager.tsx` with place search on submit,
    candidate radio selection, OpenStreetMap attribution, a typed location name,
    coordinates disclosure, and confirmed removal, record
    `tests/fixtures/recorded/geocode-nominatim/2026-11-04/`, and prove the
    Nassau breakpoint path against replayed Dorian advisory 26.
- Parallelize the CI `test` job with `pytest-xdist` (Phase 7 Step 1, closing
  issue #82): add `pytest-xdist>=3.8.0` (`execnet==2.1.2`) to the `dev`
  dependency group, run `.github/workflows/ci.yml`'s `test` job with `uv run
  pytest -n auto` while keeping `pyproject.toml`'s `addopts` serial and all four
  branch-coverage floors (`weatherbot.engine`, `weatherbot.services.policy`,
  `weatherbot.services.ai.context`, and `weatherbot.services.ai.validate` at
  `>=90%`) unchanged, add `tests/test_ci_budget.py` proving the CI configuration
  and worker-process loopback socket and working-directory guards, update
  `README.md`'s `## Status` to Phase 7 in progress, and convert Phase 6's check
  44 (`scripts/verify_phase06.py` and `tests/test_phase06_verification.py`) to
  read `README.md` at `v2.0.0-phase-6`.

### Phase 6 — Claude layer
- Add Phase 6's repeatable verification script (`scripts/verify_phase06.py`),
  its test suite (`tests/test_phase06_verification.py`), the `phase-verify (06)`
  CI matrix entry with its own conditional Node 24 setup before `--security`
  (`.github/workflows/phase-verify.yml`), and the Phase 6 QA findings ledger
  (`docs/phase06-qa-findings.md`), closing Phase 6 (`v2.0.0-phase-6`):
  - `scripts/verify_phase06.py`: 51 standard-library static checks covering
    Steps 1–6 and Step 7 self-checks plus the 28-row V1–V7 post-implementation
    verification matrix (79 total checks in `--post`), supporting `--fast`,
    `--py`, `--node`, `--ui`, `--live`, `--ai`, `--security`, `--all`, and
    `--post`.
  - `tests/test_phase06_verification.py`: offline regression tests covering
    `--fast` (< 30 s), the 28-row V-matrix, `phase-verify.yml` `"06"` matrix
    membership, non-echoing failure continuation, fail-closed skipped JUnit
    evidence, mutually exclusive mode flags, and single-deliverable red-check
    isolation across Steps 1–7 without invoking `--ai`.
  - `docs/phase06-qa-findings.md`: rollup of PR #76 (roadmap) and Steps 1–7
    (PRs #77, #80, #81, #83, #84, #86, and Step 7), the measured token and cost
    distribution vs. roadmap estimates ($1.595 total Phase 6 AI spend across
    Steps 1–6), the 600 s idle CPU measurement with AI ready (`server_cpu=0.3099%`,
    `tab_cpu=0.0025%`), the 38/38 live eval results, model and source drift
    observations (`validate.AREA_LIMIT` 400 -> 600, SDK `output_config.format`
    validation, `nws-points` 502 tracked in Issue #87), the exact vs.
    growth-proof Phase 6 checks for Phase 7, live smoke runs, and pre-ship items.
- Add the AI chassis (Phase 6 Step 1): `anthropic>=2.3.0` and the `[ai]`
  settings table (`enabled`, `model`, `summary_model`, `daily_cap_usd`,
  `change_summaries`, `outlook_narration`) with six literal `WEATHERBOT_AI_*`
  overrides; `weatherbot.services.ai`, the only importer of the SDK, with the
  client factory (the SDK resolves `ANTHROPIC_API_KEY` or an `ant auth login`
  profile; nothing copies the value), fixed reasons for every SDK error and the
  `refusal` and `max_tokens` stops, list prices in integer micro-dollars dated
  2026-10-30, the AI engine (a SQLite authorizer that lets the package write
  only `ai_calls` and `ai_outputs`), and revision 0007's `ai_calls` ledger:
  every request reserved at its ceiling under `BEGIN IMMEDIATE`, sent, and
  settled from the SDK's usage, under a $1.00 daily cap every process shares,
  with a pause and bounded daily allowances.
- `doctor` gains its `ai` check (the credential's source and today's spend,
  proved online by a free `count_tokens` request) and `/api/health` its `ai`
  block (`state`, `reason`, `spent_micro_usd`, `cap_micro_usd`); every log
  record and traceback loses key shapes and authorization values, and the SDK's
  loggers stay at WARNING at every level.
- Tests replay recorded answers through the real SDK (`tests/ai/ai_support.py`);
  `scripts/record_ai_fixtures.py` records response bodies only into
  `tests/fixtures/ai/`. Phase 5's check 47 now reads `README.md`'s Status at
  `v2.0.0-phase-5`. `docs/AI.md` documents the layer.
- Add the briefing and the change summary (Phase 6 Step 2): the frozen system
  prompt rendered from the ladder and hashed into the prompt version, with a
  five-minute cache marker; the privacy-reduced context (structured fields only,
  distances as six bands, bearings as 8 compass points, instants to the hour,
  sources as keys, NOAA text in escaped blocks with its links removed); the
  `Briefing` and `ChangeSummary` schemas, neither with a level; the validators,
  which withhold a product that states another level, cites an unknown source,
  or carries a URL, an unquoted position, an empty section, or text past its
  bound; revision 0008's `ai_outputs`; a briefing streamed and released section
  by section, reused per assessment, model, and prompt; change summaries written
  once per qualifying assessment with `[ai] summary_model`; and `weatherbot brief
  [LOCATION] [--new] [--json] [--cost]` with its `brief` document.
- Add the eval set (`tests/ai/eval/`, 31 cases over the recorded snapshot, the
  replay subset, a failed-input case, and four injection twins) graded offline
  on every run, and `scripts/eval_ai.py` (`--count`, `--live`); the recordings
  cost $0.27, and the measured token distribution in `docs/AI.md` confirms the
  ceilings and the $1.00 cap. CI holds `services/ai/context.py` and
  `services/ai/validate.py` at 90% branch coverage each.
- Add grounded chat and the outlook narration (Phase 6 Step 3): nine read-only
  tools (`list_locations`, `get_assessment`, `get_evidence`, `get_alerts`,
  `get_storms`, `get_storm`, `get_outlook`, `get_ladder`, `get_history`) with
  strict schemas, read through the AI engine, returning the briefing context's
  privacy-reduced shapes, each result bounded at 8,000 characters, and an error
  result listing the allowed values for an unknown tool, a bad input, or an
  unknown location or storm; `ChatService`, the tool loop (`tool_choice` auto,
  at most six rounds a turn, a round's calls answered in one message) over
  conversations held append-only in memory (8 of 20 questions, dropped after 2
  idle hours), each sentence checked for another current level, a URL, or an
  unquoted position before it is shown, and a system message stating new
  official levels when an assessment changes between questions;
  `NarrationService`, off by default, which sends the stored outlook PNG and its
  TWO and withholds a narration that states a level, a position, or a chance the
  TWO does not; and `weatherbot ask QUESTION [--location NAME] [--json]` with
  its `ask` document (17 documents) and `weatherbot brief --outlook
  {atl,pac,cpac} [--horizon {2d0,7d0}]`.
- Record five chat turns (one lookup, parallel lookups over two rounds, the
  ladder, a storm, and the injection twin whose TCP carries hostile lines) and
  two narrations; each recorded turn replays its requests byte for byte, and
  they cost $0.11 at list price.
- Put the AI behind the loopback API (Phase 6 Step 4): the reads `GET /api/ai`
  (state, credential source, models, features, and today's meter),
  `/api/ai/calls` (the ledger: kinds, statuses, tokens, costs, and reasons,
  never text), `/api/ai/briefings`, `/api/ai/summaries`, and
  `/api/ai/narrations` (each source resolved from its stored record and linked
  only to a public NOAA page that names no point); the guarded server-sent event
  streams `POST /api/ai/briefings`, `/api/ai/chat`, and `/api/ai/narrations`
  (503 or 429 with a fixed reason before a stream begins, at most four at once,
  and a closed page cancels its request and settles the ledger); the controls
  `PUT /api/ai/pause` and `POST /api/ai/allowance` (at most one day's cap,
  three a day, a fourth answers 409); and `GET /api/outlook` and
  `/api/outlook/{basin}/{horizon}`, NHC's outlook PNG read from the stored
  snapshot by SHA-256.
- The event stream gains the `ai` kind and the `ai` and `briefings` query keys:
  a settled request or a control change publishes `ai` invalidating `ai`, a
  stored product `ai` invalidating `briefings`, and the cycle watcher's two new
  marks (`ai_calls`, `ai_outputs`) bring what `brief` or `ask` writes in another
  process to an open page; `serve` runs the change summarizer beside the
  watcher, primed so history is never backfilled. The OpenAPI document, the
  frontend's types and query keys, and six new API fixtures follow, and Phase
  5's check 19 now reads the event kinds at `v2.0.0-phase-5`.
- Put the AI in the page (Phase 6 Step 5): `frontend/src/ai/` gains
  `readEventStream` (a typed server-sent event parser over `fetch`, with
  `postStream` sending same-origin JSON through the generated client and
  mapping a 429 or 503 answer to its reason), `AiLabel` (the model's display
  name, the time in the browser's zone and in UTC, and "AI-generated · may be
  wrong · the level above comes from official products"), `AiStateBanner` (off,
  paused, capped, and unavailable), and the hooks `useAiStatus`, `useBriefing`,
  `useChat`, and `useNarration`, with one AI stream per page.
- The dashboard's location cards gain the AI briefing panel (the stored
  briefing with its sources; `Brief me` streaming sections in order; the
  withheld, stale, and state banners), the timeline each change's labeled
  summary, the new Ask page (`/ask`, between Timeline and Settings) its chat
  beneath the engine's level badges, the storms page NHC's six official
  outlook graphics with their narration when it is on, and the settings page
  its AI section (`#ai`: the state, the credential's source, the models,
  today's meter, the recent requests, the pause, and a confirmed allowance).
  Every AI text renders as plain text and links only a URL the API supplied.
- The page now accepts the event stream's `ai` events, which Step 4 added but
  the page's guard dropped, so the AI values refresh without a reload. No
  frontend dependency is added; Vitest grows from 34 to 76 tests.
- Prove the AI end to end (Phase 6 Step 6): `scripts/serve_demo.py` gains
  `--ai-replay` (on by default: a real SDK client whose transport answers each
  request kind from `tests/fixtures/ai/`, streams paced so sections arrive one
  by one, every `ANTHROPIC_*` variable removed), `--ai-cap-usd`, and
  `--ai-fail-auth` (every request answered 401); `frontend/playwright.config.ts`
  starts two more demonstration servers (8800 with a $0.001 cap, 8801 refusing
  the credential); and `frontend/e2e/ai.spec.ts` streams a labeled briefing
  section by section, sees a lookup chip and then the answer, loads NHC's six
  outlook graphics, opens the allowance's confirmation under the policy, sees
  the cap's pause and the third authentication failure's hold, and captures the
  AI blocks in both themes at desktop and phone width. The shared guard now also
  fails a test whose console repeats AI text.
- `scripts/eval_ai.py` grades the chat turns (each run through the real chat
  over a throwaway database) and the narrations beside the briefings and
  summaries: 38 cases, offline by default and with `--live`; the live run of
  2026-11-02 passed all 38, the injection twins included, for $0.38. The first
  live run withheld the Atlantic narration for an area description past 400
  characters, so the narration's area bound is now 600 (twice what the prompt
  asks; ten live samples wrote 240 to 337).
- `scripts/measure_idle.py` measures only with AI `ready` and change summaries
  on: 0.3099% of a core for the server and 0.0025% for the tab over ten idle
  minutes. `doctor --json` fails its `ai` check on a 401 (tested through the
  CLI). `docs/AI.md` records the live numbers, the idle line, the smoke, and a
  runbook (the cap reached during a storm, an authentication failure, rotating
  the key, and turning AI off).

### Phase 5 — Web app (MVP)
- Add Phase 5's repeatable verification script (`scripts/verify_phase05.py`),
  its test suite (`tests/test_phase05_verification.py`), the `phase-verify (05)`
  CI matrix entry with conditional Node 24 setup before `--security`
  (`.github/workflows/phase-verify.yml`), and the Phase 5 QA findings ledger
  (`docs/phase05-qa-findings.md`), closing Phase 5 (`v2.0.0-phase-5`):
  - `scripts/verify_phase05.py`: 53 standard-library static checks covering
    Steps 1–7 and Step 8 self-checks plus the 32-row V1–V8 post-implementation
    verification matrix (85 total checks in `--post`), supporting `--fast`,
    `--py`, `--node`, `--ui`, `--live`, `--security`, `--all`, and `--post`.
  - `tests/test_phase05_verification.py`: offline regression tests covering
    `--fast` (< 30 s), the 32-row V-matrix, `phase-verify.yml` `"05"` matrix
    membership, non-echoing failure continuation, fail-closed skipped JUnit
    evidence, mutually exclusive mode flags, and single-deliverable red-check
    isolation across Steps 1–7.
  - `docs/phase05-qa-findings.md`: rollup of PR #56 and Steps 1–8 (PRs #61,
    #62, #63, #64, #65, #66, #70, #72, and #73), the 600 s idle CPU measurement
    receipts (`server_cpu=0.4843%`, `tab_cpu=0.0020%`), the forward-geocoding
    UX finding (tracked in Issue #71 and Phase 7 §7.3), the seven exact Phase 5
    checks for Phase 6 (`2`, `4`, `14`, `17`, `19`, `25`, `47`), source-drift
    observations (including null-geometry `Forecast Wind Radii` / `Advisory Wind Field`
    rows on weakening storms, fixed in `parse_wind_radii`), high-water mark query
    optimizations in `CycleWatcher` and `MonitorSchedule`, live smoke runs, and
    pre-ship items.
- Add the Playwright browser smoke suite (`frontend/playwright.config.ts`,
  `frontend/e2e/{guard.ts,dashboard.spec.ts,map.spec.ts,screens.spec.ts,idle.spec.ts,blank-tile.png}`),
  the offline demonstration server (`scripts/serve_demo.py`,
  `tests/scripts/test_serve_demo.py`), the 600-second idle CPU measurement
  (`scripts/measure_idle.py`, `tests/scripts/test_measure_idle.py`, with `psutil`
  and `types-psutil` in the `dev` dependency group), and the `browser` CI job in
  `.github/workflows/ci.yml`:
  - `scripts/serve_demo.py`: runs `serve`'s monitor and web server through
    `cli/serve.py`'s `_loop` in a temporary data directory with both public
    landmarks (`"simulated Miami-Dade"` and `"Parliament Square"`), answers all
    outbound requests from recorded fixtures via `respx`, supports `--port`
    (default `8799`), `--corpus DIR`, `--roster-interval-minutes`, and
    `--switch-file PATH` (switching to advisory `023` and the synthetic
    `Hurricane Warning` from `scripts/simulate_advisory.py`), prints its `pid`
    and `address` plus each `roster_poll` and `cycle`, and cleans up on exit.
  - `frontend/e2e/`: verifies landmark cards, the footer disclaimer notice, the
    Radix `DropdownMenu` theme menu under the per-response CSP nonce, live Level
    5 escalation over `/api/events` without a page reload, in-page notification
    toast delivery, `/map` historical replay of Irma (`AL112017`) advisory `031`
    with cone/track/point/location SVG layers under the `"not live"` banner, and
    `1280×800` / `360×740` light/dark screenshots, guarded against unexpected
    origins, CSP violations, page errors, and coordinate leaks in console output.
  - `scripts/measure_idle.py` and `frontend/e2e/idle.spec.ts` (`@idle`): verify
    that over a 600 s window after a 30 s settle at production intervals, both
    `serve_demo.py` (`psutil` `user + system`) and the Chromium dashboard tab
    (CDP `Performance.getMetrics` `TaskDuration`) consume `< 0.5%` of one CPU
    core.
- Add the `/map` page (`frontend/src/map/{MapView.tsx,useLeafletMap.ts,layers.ts}`,
  `layers.test.ts`, and `MapView.test.tsx`) on Leaflet `1.9.4` directly (pinned
  in `frontend/package.json` with `>= 2.0.0` ignored in
  `.github/dependabot.yml`):
  - Render the OpenStreetMap tile layer
    (`https://tile.openstreetmap.org/{z}/{x}/{y}.png`, `maxZoom: 19`,
    `referrerPolicy: "strict-origin-when-cross-origin"`, `crossOrigin` unset,
    and visible `"© OpenStreetMap contributors"` attribution linking to
    `https://www.openstreetmap.org/copyright`) and amend `docs/DATA_SOURCES.md`
    (`basemap-osm-tiles`).
  - Render toggleable layers and a legend for storm cones, forecast tracks,
    forecast points (vector circle markers coloured by classification with UTC +
    local time-zone tooltips and intensity), NHC watch-warning segments (`HWR`
    red, `HWA` pink, `TWR` blue, `TWA` yellow, with breakpoint names), Tropical
    Weather Outlook areas (low yellow, medium orange, high red), and watched
    locations (points and stored NWS zone polygons), preserving exact API
    coordinates (including continuous Central Pacific antimeridian crossings),
    showing each layer's `crs` (`EPSG:4326` or `native (D_Sphere)`) in its
    popup, and building all popups and tooltips with `textContent` only.
  - Fit the map to storms and locations on initial load and when `Fit` is
    clicked (or whole-number Atlantic basin `[25, -65]` zoom `4` when empty)
    without resetting the view on background `snapshot` SSE updates after user
    movement, and provide the historical replay corpus picker (`GET /api/replay`
    and `GET /api/replay/{atcf_id}/{advisory}`) with the `"Replay: <storm>
    advisory <n>, issued <instant> — not live"` banner and `Back to live` button
    when `/api/health` reports `corpus: true`.
- Add the five dashboard and data pages (`frontend/src/pages/{Dashboard,Storms,Alerts,Timeline,Settings}.tsx`
  and `frontend/src/pages/format.ts`), browser notification delivery
  (`frontend/src/notifications/notify.ts` and in-page Radix `Toast` in
  `AppShell.tsx`), and the deterministic API fixture exporter
  (`scripts/export_api_fixtures.py`, `frontend/src/test/fixtures/*.json`, and
  `tests/web/test_api_fixtures.py`):
  - `/` (`Dashboard`): per-location threat level cards with `At least Level N`
    and missing-input floor banners when `complete` is `false`, deciding rule and
    evidence, recommended actions, covering official products and county-zone
    context alerts, storm threats (`0.1 km`, integer `deg`, `0.1 h`, and arrival
    readings with origin), 5 km wind-speed probabilities, changes since the
    previous assessment, evacuation-order toggle (`PUT /api/locations/evacuation`)
    with `toggle_note`, `aria-live="polite"` level announcements, `Check now`
    (`POST /api/cycles`, disabled until a `cycle` `StreamEvent` arrives, with
    plain `409`/`429` messages), and an empty state with disclaimer essentials.
  - `/storms` (`Storms`), `/alerts` (`Alerts`), `/timeline` (`Timeline`), and
    `/settings` (`Settings`): active cyclones and products, graphical outlook
    areas, wind-speed probability summaries, covering vs. county-zone context
    NWS alerts, NHC watch-warning segments, chronological assessment and
    notification history with location filter and delivery/decision badges,
    add-location form (`POST /api/locations` with `409`/`422` handling), browser
    notification permission switch and test notification button
    (`POST /api/notifications/test`), effective settings table with origins and
    `file_modified_since_start` reload banner, 11-rule alert ladder reference,
    full `DISCLAIMER.md` text (`#disclaimer`), and bundled `/licenses.json`
    viewer.
  - `frontend/src/notifications/notify.ts`: sole caller of `new Notification(...)`
    and `Notification.requestPermission()`, firing a background Web Notification
    only when `display: true`, `localStorage['weatherbot.notifications']` is on,
    permission is `granted`, and `document.visibilityState === "hidden"`, while
    `AppShell` shows an in-page Radix `Toast` on every `display: true`
    notification event.
- Add the `frontend/` web chassis on Node 24 (`frontend/.nvmrc`, Vite 8.3.5,
  React 19.3.1, strict TypeScript 5.9.3, Tailwind CSS 4.3.3, TanStack Query
  5.104.5, React Router 8.5.0 in data mode, `radix-ui` 1.8.1, `lucide-react`
  1.61.0, `openapi-typescript` 7.13.0, and `openapi-fetch` 0.17.0):
  - Generate and check `frontend/src/api/schema.d.ts` from
    `docs/api/openapi.json` (`api:generate` and `api:check`), add the same-origin
    typed API client (`frontend/src/api/client.ts`), and define the nine
    server-invalidatable `queryKeys` (`frontend/src/api/keys.ts`) separately
    from static page keys (`replay`, `disclaimer`, `licenses`).
  - Add `useEventStream` (`frontend/src/events/useEventStream.ts`): opens one
    `EventSource('/api/events')` per tab, marks the stream connected on the
    first `hello` without refetching, invalidates all nine query keys on a
    reconnect's `hello`, invalidates the exact `invalidate` list on every other
    event, and forwards `notification` events with `display: true` to a callback.
  - Add the application shell (`AppShell`, `routes`, `ThemeMenu`,
    `ThreatLevelBadge`, `nonce`, `theme`, and `public/theme-init.js`): serves
    the six routes (`/`, `/map`, `/storms`, `/alerts`, `/timeline`, `/settings`)
    plus a not-found route, keyboard and mobile navigation, system/light/dark
    theme selection applied before first paint, a staleness banner driven by
    `/api/health`, per-response CSP nonce forwarding, and the disclaimer footer
    linking to `/settings#disclaimer` on every page.
- Add `frontend/scripts/check-licenses.mjs` (`licenses:check` over Vite's
  `src/weatherbot/web/static/licenses.json` against `{MIT, ISC, BSD-2-Clause,
  BSD-3-Clause, Apache-2.0, 0BSD}`), `scripts/smoke_installed_web.py`
  (verifying an installed wheel serves `/` with its per-response CSP nonce and
  reports `ui.present == true` on `/api/health`), `frontend-lint` and
  `npm-audit` hooks in `.pre-commit-config.yaml`, the `frontend` job and
  updated `package` and `security` jobs in `.github/workflows/ci.yml`, and the
  `/frontend` `npm` ecosystem in `.github/dependabot.yml`.
- Add the live Server-Sent Events stream (`GET /api/events`,
  `weatherbot.web.routes.events`, `EventHub`, `CycleWatcher`, and
  `StalenessTimer` in `weatherbot.services.events`): streams typed `StreamEvent`
  frames (`hello`, `cycle`, `snapshot`, `assessment`, `alert`, `notification`,
  `location`, `health`) naming the `QueryKey` caches to invalidate, bounded at
  16 subscribers (`503` on the 17th) and 100 queued events per subscriber, with
  cross-process SQLite polling (`CycleWatcher`), exact heartbeat-staleness
  wakeups (`StalenessTimer`), and clean stream shutdown on `WebServer` stop.
- Add `BrowserChannel` (`[notifications] browser = true`,
  `WEATHERBOT_NOTIFICATIONS_BROWSER`, `Channel.interrupts`) in `weatherbot
  serve` (`serve_channels`): records `delivered` when a dashboard subscriber is
  open, `unavailable` (`no open dashboard`) when none is connected, and
  `disabled` (`browser notifications off`) when disabled, while keeping CLI
  commands on `Context.channels` (`log` and `toast` only) and suppressing
  interrupting channels (`toast` and `browser`) on quiet-hours alarms.
- Add the four write API routes (`weatherbot.web.routes.actions`):
  `POST /api/locations` (`201`, `409` via `LocationNameTakenError`, `422`,
  `502`), `PUT /api/locations/evacuation` (`200`, `404`), `POST /api/cycles`
  (`202` running a `manual` cycle through `serve`'s `MonitorSchedule` under
  runner `serve`, `409` single-flight, `429` with `Retry-After` on a 60-second
  cooldown), and `POST /api/notifications/test` (`200`, `429` with `Retry-After`
  on a 10-second cooldown), and regenerate `docs/api/openapi.json` with
  `StreamEvent`, `EventKind`, and `QueryKey` in `components.schemas`.
- Add the ten read API routes (`GET /api/locations`, `/api/assessments`,
  `/api/storms`, `/api/alerts`, `/api/timeline`, `/api/notifications`,
  `/api/settings`, `/api/disclaimer`, `/api/map`, and `/api/replay` plus
  `/api/replay/{atcf_id}/{advisory}`) with frozen Pydantic response schemas in
  `weatherbot.web.schemas` (`extra="forbid"`, full field descriptions) and
  regenerate `docs/api/openapi.json`. Every route reading a repository is a
  synchronous `def` function so SQLite reads run on FastAPI's worker threadpool;
  location names are passed as query parameters rather than path segments; and
  only `/api/locations` and the map's location layers carry coordinates.
- Add `weatherbot.web.map_layers` (`build_map_response`,
  `build_storm_map_layers`, `unwrap_longitude`, `SnapshotLayerCache`, and the
  shared 8-snapshot LRU `SNAPSHOT_CACHE` used by `/api/map`, `/api/storms`, and
  `/api/alerts`): serves cones, forecast tracks, forecast points, watch-warning
  segments (with `breakpoint_names` from `segment_ends`), outlook areas, and
  location points and polygons with each geometry's explicit `crs` (`name` and
  `datum`, without `wkt`), unwrapping Central Pacific antimeridian crossings by
  `±360°` relative to the storm's first forecast point and omitting wind radii
  and wind-speed probabilities from `/api/map`.
- Add `ReplayCorpus.advisories(atcf_id)` and
  `ReplayCorpus.snapshot(atcf_id, advisory)`, `[web] corpus`
  (`WEATHERBOT_WEB_CORPUS`), `weatherbot serve --corpus DIR` (validating before
  `monitor.lock` and exiting 2 on a non-corpus directory, while an unusable
  configured `[web] corpus` logs a `WARNING` and starts `serve` with replay
  off), and `HealthResponse.corpus`.
- Add `weatherbot.web` (`create_app`, `WebState`, `WebServer`, `guards`,
  `static_files`, `schemas`, and `routes.health`) and embed Uvicorn inside
  `weatherbot serve [--open|--no-open]` on the same `asyncio` event loop as
  `MonitorSchedule` (`weatherbot.cli` now sits above `weatherbot.web` in the
  downward-only import-linter contract). `WebServer` pre-binds a loopback socket
  (`SO_EXCLUSIVEADDRUSE` on Windows, `SO_REUSEADDR` on POSIX, with five 2-second
  retries on `EADDRINUSE`) and degrades gracefully with one `WARNING` if the
  port cannot be bound, keeping the monitor alive; `weatherbot check` never
  starts the web server. `fastapi`, `starlette`, and `uvicorn` join the runtime
  dependencies.
- Add `[web]` settings (`host` restricted to `"127.0.0.1"`, `"::1"`, or
  `"localhost"`, naming `[web] host` and `Phase 8` on rejection; `port`
  `1024..65535` or `0` for ephemeral test binding, default `8765`) with
  `WEATHERBOT_WEB_HOST` and `WEATHERBOT_WEB_PORT` overrides. `tests/conftest.py`
  sets `WEATHERBOT_WEB_PORT=0`.
- Add loopback security guards (`SecurityHeadersMiddleware` outermost,
  `TrustedHostMiddleware`, and `FetchMetadataAndWriteGuard`), stripping `input`
  from FastAPI validation errors and redacting formatted exception tracebacks in
  `RedactingFormatter`.
- Add the in-memory static bundle loader (`load_static_bundle`,
  `install_static_routes`) with per-response cryptographic style nonces on
  `index.html`, immutable `/assets/*` caching, and an unbuilt fallback HTML page
  naming `CONTRIBUTING.md`.
- Add `GET /api/health` (`HealthResponse`: version, database revision,
  scheduler status and next UTC product hour, heartbeats with staleness, UI
  bundle state, and disclaimer notice), `doctor`'s `web` check, and
  `scripts/export_openapi.py` (`docs/api/openapi.json`).
- Update `scripts/verify_phase04.py` check 46 to read `v2.0.0-phase-4:README.md`
  so `README.md` can advance into Phase 5 while `phase-verify (04)` stays green.

### Phase 4 — Monitoring and notifications
- Add `scripts/verify_phase04.py`: 51 static checks over shared geometry
  storage, the monitor cycle and heartbeats, the notification policy and log,
  the Windows toast channel, the scheduler and watches, and Task Scheduler
  registration and health checks, in the six modes `--fast`, `--py` (with the
  engine and notification-policy branch-coverage floors), `--live`,
  `--security`, `--all`, and `--post` (80 checks: the 29-row V1-V7 matrix built
  from JUnit reports, GitHub readbacks, Phase 3's own `--post`,
  `scripts/simulate_advisory.py`, `doctor --offline --json` on the installed
  tool with its alarm proof, and Task Scheduler readbacks). `phase-verify.yml`
  runs entry `"04"` beside `"01"`, `"02"`, and `"03"` under the required
  aggregate `phase-verify`. `docs/phase04-qa-findings.md` is the phase's
  disposition ledger, and `README.md`'s Status names Phase 4 as complete and
  Phase 5 as next.
- Add Windows Task Scheduler registration and health checks
  (`weatherbot.services.tasks`, `weatherbot install-task`, `weatherbot
  uninstall-task`): registers `\Weatherbot\serve` (`LogonTrigger`, `PT0S`) and
  `\Weatherbot\check` (hourly `TimeTrigger` at 25 minutes past, `PT30M`,
  `StartWhenAvailable`) unelevated under `InteractiveToken` and
  `LeastPrivilege` using `pythonw.exe` and `CREATE_NO_WINDOW`, queries task
  state through Windows PowerShell 5.1 JSON, and ends `serve` and clears its
  heartbeat cadence on uninstall. `install-task` and `uninstall-task` join the
  committed JSON Schemas (fifteen).
- Add the hourly fallback (`weatherbot check --once --if-stale`,
  `run_fallback_check`): waits up to 3 minutes while `monitor.lock` is held for
  the monitor's runner row to be fresh, sends one `stale_monitor` notification
  per stale period when the monitor is not running or not responding, asks Task
  Scheduler to start `\Weatherbot\serve` when the lock is free, runs a
  `fallback` cycle, and records the `fallback` runner heartbeat; `serve`'s
  heartbeat task watches `fallback` while `\Weatherbot\check` is installed and
  notifies if the hourly check stops running.
- Add `doctor`'s `tasks` and `path` machine checks (skipped under a
  `WEATHERBOT_DATA_DIR` override, and `path` skipped for a checkout's
  interpreter) and require a fresh `serve` runner row on the default data
  directory when `\Weatherbot\serve` is installed; `doctor`'s document lists the
  queried tasks. Add `tests/desktop/test_tasks_desktop.py` (`pytest -m desktop`).
- Add the asyncio scheduler (`weatherbot.services.scheduler.Scheduler`, `Job`)
  and the monitor's scheduled jobs (`weatherbot.services.schedule.MonitorSchedule`,
  `run_monitor`, `run_heartbeat_task`): sleeps at most 60 seconds, draws one
  positive jitter per due instant, runs one job at a time without starting a
  running job twice, isolates and records job exceptions on their heartbeats,
  and runs one coalesced `resume` cycle after a wake gap over 60 seconds.
- Add `weatherbot.sources.arcgis.attributes` (`ATTRIBUTE_PARAMETERS`) and
  `weatherbot.sources.nhc_map.fetch_cone_advisories` (`CONE_ADVISORIES_READ`,
  `binnumber` and `advisnum`), which queries the summary service's `Forecast
  Cone` layer without geometry. `MonitorSchedule` runs `startup`, `window` (at
  each of NHC's eight UTC product hours plus 15 minutes with jitter, polling
  every 5 minutes until the roster and the cone layer agree on an advisory at or
  after the product hour, or at +60 minutes), `roster` (every 15 minutes, or 5
  while a location is above level 1, sharing a 60-second roster cache and
  `MemoryValidatorStore`), `alerts` (every 5 minutes while a US location is
  above level 1), `confirm` (at `CycleResult.confirm_at`), and `retry` (5, 10,
  and 20 minutes after a ladder source fails, up to 3 retries), plus an
  independent 5-minute runner heartbeat task.
- Add the degraded-data alarm and recovery (`degraded` notification after 3
  consecutive failures of a ladder source or watch, and `recovered` when it
  answers again, respecting quiet hours at levels 1 and 2) and the database-free
  toast (`deliver_database_refused_toast`) when `open_database` refuses a newer
  revision or fails a migration.
- Add `weatherbot serve` and `weatherbot check` (without `--once`), which take
  `data_dir/monitor.lock` (`ProcessLock`, exiting 2 when another monitor holds
  it), write a rotating log file at `data_dir/logs/weatherbot.log` (1 MiB, five
  files, UTC ISO-8601 timestamps, `RedactingFilter`, and `pythonw.exe`
  `sys.stderr is None` support), and clear the runner heartbeat's expected
  cadence on a clean stop. `[monitor]` gains the eleven schedule settings with
  their `WEATHERBOT_MONITOR_*` overrides, `config path` adds `monitor_lock_file`
  and `log_file`, and `scripts/simulate_advisory.py` proves the scheduled
  advisory-to-toast chain in a temporary directory.
- Add the Windows toast channel, `weatherbot.services.toast.ToastChannel`, over
  pywinrt (`winrt-runtime`, `winrt-Windows.UI.Notifications`,
  `winrt-Windows.Data.Xml.Dom`, `winrt-Windows.Foundation`, and
  `winrt-Windows.Foundation.Collections` 3.2.1, each installed on Windows only).
  A toast shows the notification's title, its first two lines, and the
  disclaimer's notice, every value HTML-escaped, under the application
  identity `Weatherbot.Monitor`. Each delivery is `delivered`, `failed` (with
  the HRESULT), `disabled` (with Windows' notification setting), or
  `unavailable`. `NullChannel` answers off Windows and when the new
  `[notifications] toast` setting (`WEATHERBOT_NOTIFICATIONS_TOAST`, default
  on) is off. Every command that runs a cycle now delivers through the toast
  beside the in-app log.
- Add `weatherbot notify setup [--remove]`, which registers or removes the
  identity under `HKEY_CURRENT_USER\Software\Classes\AppUserModelId` (no
  administrator rights, idempotent; sending never writes the registry), and
  `weatherbot notify test`, which stores a test notification and delivers it
  through every channel. Their `notify-setup` and `notify-test` documents join
  the committed JSON Schemas (thirteen). `doctor` adds a `toast` check judged
  from the stored deliveries, skipped on a fresh install.
- Add the `desktop` test marker, deselected by default, and
  `tests/desktop/test_toast_desktop.py`, the one test that shows a real
  toast. `tests/conftest.py` turns the toast off for every other test, and
  CI's `typecheck` job also runs on Windows, where pyright checks the
  Windows-only code.
- Build the eight replay timelines once for the engine goldens, the
  notification goldens, and the notification replay tests
  (`ladder_data.replay_timelines`); the three suites take 28 s instead of 61 s.
- Add the pure notification policy (`weatherbot.services.policy.decide`), held
  to at least 90 percent branch coverage on its own in CI and verified pure by
  `tests/test_architecture.py`: immediate escalations, held drops on newly
  missing inputs (up to `max_holds = 3`, then decided as `"at least"`) or on an
  unconfirmed drop without a new advisory or expired covering official product,
  per-key cooldowns (`[notifications] cooldown_hours`), quiet hours
  (`quiet_hours_start`, `quiet_hours_end`, `quiet_hours_time_zone`), and at most
  one coordinate-free notification per location per cycle.
- Alembic revision `0006` (expand-only, after the online backup) adds
  `notifications`, `notification_decisions` (unique on `(assessment_id, trigger,
  change_position)` so each stored assessment is decided once), and
  `notification_deliveries`. `NotificationService.decide_cycle` reconstructs
  each location's `PolicyState`, stores decisions and notifications in a `BEGIN
  IMMEDIATE` transaction, and delivers through `LogChannel` (`log`/`delivered`);
  `MonitorService.run_cycle` runs it after assessments commit and records
  `notifications` and `confirm_at` (`[monitor] confirm_after_minutes`) on
  `CycleResult`. `check --once` prints sent notifications and when a
  confirmation cycle is due.
- Add `weatherbot notify log [--limit N] [--json]` and its `notifications`
  document (the eleventh committed JSON Schema), `replay_notifications`, and
  `scripts/build_notification_goldens.py` with the two operator-approved Irma
  notification goldens (`tests/golden/notifications/AL112017-miami-dade.json`
  and `AL112017-nassau.json`).
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
