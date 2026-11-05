# Phase 7 Roadmap — Depth

**Status:** In progress

## Overview

Phase 7 turns a correct monitor into a tool the operator uses every day: their
own place found by name and watched beside Nassau; a phone that buzzes through
ntfy, with quiet hours and per-location preferences; the wind radii, past track,
probabilistic winds, peak surge, radar, and satellite on the map, with a slider
over the stored advisories; charts of a location's level and wind probability; a
past storm scrubbed advisory by advisory through the same engine and the same
components; history that the operator can keep or prune; and a static report to
share. It moves no level: no ladder rule, threshold, golden, change kind, cycle
trigger, or notification kind changes, and the policy decides exactly what it
decided in Phase 6 (a location's preferences choose channels, never decisions).
It adds no AI product, no model-driven search, and no forecast of Weatherbot's
own, and it opens nothing beyond loopback and publishes nothing (Phase 8). The
work is one phase because every feature lands on the same settings page, map,
and history, and it is many steps because each feature must ship alone: the
project roadmap's answer to scope creep here is one feature, one step, one PR.

The phase lands in 10 layers:

1. **The test budget** — `pytest-xdist` in the dev group and `-n auto` on the
   `ci.yml` `test` job, with the coverage floors unchanged. The Windows job took
   35m17s of its 40-minute bound on Phase 6's last PR, and every later step adds
   tests; measured locally, the whole suite passes under `-n 6` in 4m09s with no
   test changed. Closes issue #82, and flips the phase to In progress.
2. **Locations** — issue #87 fixed from its probed cause (a marine-zone
   `/points` answer omits `county`) and logged; issue #71's forward search
   (`POST /api/locations/search`, `weatherbot locations add --place`, candidates
   to choose from, and never a keystroke's request); and the multi-location
   page: add by place or by coordinates, remove with a confirmation, and the
   Nassau profile through the breakpoint path. Deployed on the operator's
   machine with the operator's yes, so their own location is watched from here
   on.
3. **The phone** — `services/ntfy.py`, a `Channel` that publishes JSON to the
   server's root with the topic and token read from the environment, never from
   a setting or a URL; `[notifications] ntfy` and `ntfy_server`; per-location
   preferences (revision 0009) that choose channels; `doctor`'s `ntfy` check;
   redaction in every log record; quiet hours proved through the real channel;
   and the operator's phone buzzing from `weatherbot notify test`.
4. **Settings and retention** — `PUT /api/settings`, which writes
   `weatherbot.toml` through `tomlkit` with its comments kept, refuses a key the
   environment sets, and refuses a stale write; the page's editors for quiet
   hours, cooldown, the AI cap, and retention; and `services/retention.py`, one
   `[retention] history_days` knob, off by default, with a keep-list that leaves
   the policy's state and the next diff exactly as they were, `weatherbot prune
   --dry-run`, a daily worker in `serve`, and revision 0010, which indexes the
   foreign keys a delete has to check.
5. **The map's depth** — wind radii, past track and points, and peak surge from
   the stored snapshot; probabilistic winds on demand from a route of their own;
   radar and satellite from NOAA's nowCOAST, requested only while toggled on,
   with the CSP's `img-src` widened by exactly that host; and a time slider over
   stored advisories.
6. **Charts and history** — `GET /api/charts`; hand-drawn SVG, with no new
   dependency: a level sparkline on every card, a comparison strip across
   locations, the wind probability chart (how the location's official 120-hour
   band moved across synoptic times), the arrival-time display, and the
   timeline's history with a location's charts and older pages.
7. **Replay in the UI** — `GET /api/replay/{atcf_id}/timeline` and its
   per-advisory assessment through `ReplayService`, nothing stored; the
   `/replay` page, with the scrubber, the level, the evidence, and the map from
   the same components as live; Dorian 2019 at Nassau showing its breakpoint
   ladder; and issue #44's wording, which this page would otherwise print.
8. **The report** — `services/report.py`, `GET /api/report`, and `weatherbot
   report --out`: one static HTML file with no script and no remote resource,
   built only from what Phase 6 already allows off the machine (no coordinate,
   address, zone, URL, or engine sentence), carrying the disclaimer, with an AI
   briefing and its label only when asked for, and printing to PDF from the
   browser.
9. **The whole phase on the operator's machine** — the Playwright flow across
   every new surface with no network, the idle measurement, each new alarm
   injected and seen, and the operator's service upgraded, with Nassau beside
   their location and a storm scrubbing. Deployed on the operator's machine with
   the operator's yes.
10. **QA + `verify_phase07.py`** — `scripts/verify_phase07.py` (`--fast`,
    `--py`, `--node`, `--ui`, `--live`, `--security`, `--all`, `--post`),
    `docs/phase07-qa-findings.md`, and matrix entry `"07"` beside `"01"` to
    `"06"` in `phase-verify.yml`, with its own Node steps; Phase 7 closed in
    this roadmap and the project roadmap; the `v2.0.0-phase-7` tag.

The ship test for Phase 7 is straightforward: the Windows `test` job finishes
well inside its bound with the coverage floors unchanged; a point whose
`/points` answer has no county is added and watched, and a place found by name
is added from the page and with `locations add --place`, with no search text in
any log; Dorian 2019 replayed at Nassau reads level 4 at advisory 24 and level 5
at advisory 26 from breakpoint segments, in the test suite and in the scrubber;
a test notification reaches the operator's phone through ntfy, quiet hours
suppress a level-2 repeat while an escalation still arrives, and the topic and
token appear in no log, database row, answer, export, or fixture; a setting
edited from the page lands in `weatherbot.toml` with its comments intact, and a
key the environment sets is refused; a prune removes only what its dry run said,
and every location's policy state reads the same afterwards; every new map layer
and chart renders from recorded fixtures with no network, no overlay is
requested until it is toggled on, and the services are documented with their
terms; the exported report opens offline with the disclaimer and the AI labels
and holds no coordinate; the server and the tab each stay under 0.5 percent of a
core idle; the operator's `/api/health` reports the upgraded copy at the new
head; Phase 1's to Phase 6's verification still pass; and
`scripts/verify_phase07.py --fast` exits 0 on Ubuntu CI with `phase-verify (01)`
to `(07)` green.

**Pre-requisite:** Phase 6 closed on 2026-11-02 (PR #88; `v2.0.0-phase-6`). Its
validators and privacy-reduced context are what the report reuses, so nothing
new has to be proved about what may leave the machine; its ledger, outputs, and
authorizer are what retention must leave intact. Phase 5's guarded API, event
stream, pages, map, and replay picker are what this phase deepens, and its
same-origin rule is what keeps a hostile page from editing settings, pruning
history, or sending a notification. Phase 4's `Channel` protocol, pure policy,
quiet hours, and heartbeats are what the phone and the retention worker plug
into. Phase 3's replay corpus, `ReplayService`, and golden ladders are what the
scrubber shows, and Phase 2's stored display layers and wind radii are what the
new map layers read. The planning kit is roadmodel 0.2.111: its export on
2026-11-03 was byte-identical to the committed 0.2.108 kit, so nothing was
uncommitted and no kit PR preceded this roadmap, and `uv.lock` stays at 0.2.108
until a refresh changes the kit.

**Dependency:** Phase 8 does not start until Phase 7's V-checks are green. Its
documentation describes every setting, channel, layer, and export this phase
adds; its fresh-install smoke proves `serve` with no ntfy topic, no corpus, and
no key; its readiness scan covers the report and the ntfy paths; and its LAN
mode reuses the write guards this phase's new writes pass through.

**Design rationale (decisions and clarifications of the brief and the project
roadmap).** Twenty decisions, each made against recorded, measured, probed, or
researched evidence while this roadmap was written (2026-11-03) and checked by
an independent review of the draft against the code; the steps cite them by
number. The project roadmap records each one that changes it, in this roadmap's
own pull request. Step agents treat them as settled spec unless the operator
changes them.

1. *Nothing here moves a level.* No ladder rule, threshold, golden, change kind,
   cycle trigger, or notification kind changes, so Phase 3's digest-pinned
   replay goldens and Phase 4's approved notification goldens (`df7c5f86...`)
   stay byte-identical, and no step asks the operator to approve one. The new
   surfaces read the engine's stored output; a surge layer, a radar image, and a
   chart are display, and none is an input to any rule. Issue #33 (whether a
   surge or extreme-wind product should move the ladder) stays the operator's
   call: this phase neither answers it nor forecloses it.
2. *The test budget comes first, and parallelism pays for it (probed
   2026-11-03).* The Windows `test` job took 35m17s of its 40-minute bound on PR
   #88, and every step here adds tests, so the bound would break mid-phase.
   Issue #82 offered per-test database templates, a Windows subset, or another
   raised bound. `pytest-xdist` beats all three: through an ephemeral overlay,
   with no test changed, the whole offline suite passed (3,800 passed, 2
   skipped) in 4m09s at `-n 6`, and with CI's exact coverage flags at `-n 4` in
   8m42s at 98.52 percent, the three per-file `coverage report` floors reading
   the combined data (policy 100, `context.py` 96, `validate.py` 98).
   `windows-latest` has 4 vCPUs. `-n auto` goes on the job and never in
   `addopts`, because Phase 1's and Phase 4's checks read `addopts`, a
   developer's filtered run should stay serial, and six subprocess tests carry a
   30-second timeout that a developer's loaded machine should not race. Only
   Phase 3's check 5 reads the job's tokens, and they all stay.
3. *Issue #87 is a marine-zone answer, and the schema has to take it (probed
   2026-11-03).* `/points` at public water and shoreline points (Biscayne Bay,
   Lake Okeechobee, the Florida Straits) answers 200 with a marine
   `forecastZone` such as `AMZ630` and no `county` or `fireWeatherZone` key at
   all, and open water can answer `cwa: "NH2"`; `fields.text("county")` raises
   on the absent key (`the points answer: 'county' is missing`), and
   `NwsCoverage.cwa`'s `^[A-Z]{3}$` refuses the digit. That is `parse_point`'s
   failure in the issue, though only the operator's own run can say it was
   their field, so Step 2 starts by asking them to run the issue's recipe,
   which prints the field and never the point. `NwsCoverage.county_zone`
   becomes `str | None`, `cwa` becomes `^[A-Z0-9]{3}$`, and `parse_point` reads
   `county` only when `fields.has` says it is there.
   `alerts/active/zone/AMZ630` and `zones/forecast/AMZ630` both answer 200
   (probed), so a location with no county reads alerts by its point and its
   forecast zone, and only `polygon="county"` is refused. The zone's own answer
   reads `state: null` and `type: coastal`, so `parse_zone` reads `state`
   through `fields.optional_text` and `NwsZone.state` becomes `str | None`;
   without that, `polygon="forecast"` on a marine zone would answer 502 again.
   The `locations` table's `nws_coverage_whole` CHECK ties the six NWS columns'
   nullness together, and it cannot be relaxed: changing a SQLite CHECK needs a
   table rebuild, and Phase 3 measured a rebuild of `locations` cascading
   deletes through its foreign keys. So the column stores an empty string for
   "no county", which `_location` and `_location_row` map to and from `None` in
   one place, with a comment on the column and a round-trip test; no revision
   is needed. `POST /api/locations` logs the source error's text at WARNING (it
   names the field, never the point) and puts it in the 502's detail.
4. *A place search runs when the operator submits it, on the server, and is
   never logged.* Nominatim's usage policy forbids autocomplete outright ("you
   must not implement such a service on the client side using the API"), allows
   searches a user directly triggers, caps the service at one request a second,
   and requires results to be cached and the licence attributed. So the page
   searches on a button, the CLI on its one invocation, and neither on a
   keystroke. `POST /api/locations/search` is a same-origin JSON write rather
   than a `GET`, so the text never enters a URL, a browser history, or an access
   log, and it answers 429 within 2 seconds of the last search.
   `nominatim.search` asks
   `/search?q=...&format=jsonv2&addressdetails=1&limit=5` (probed: an unknown
   place answers `[]`, and every field the register needs is present), `q` joins
   `COORDINATE_PARAMETERS`, so the fetcher's own log records redact it, and the
   answer is cached in memory only, by the SHA-256 of the normalized text, for
   24 hours, so repeating a search asks nothing and the typed place never
   reaches the database: `raw_responses.url` keeps a URL in clear, and each
   search would be the newest row of its own key, which retention never removes.
   A candidate's coordinates go only to the operator's own page; the CLI lists
   names and `--pick N` chooses, so `locations list` stays the only command that
   prints a coordinate. The page shows the OpenStreetMap attribution beside the
   results. Adding a candidate then follows the existing `add` path, so the one
   reverse geocode and the `/points` lookup are unchanged. The location's name
   is typed, never defaulted from a candidate, because `Location.name` reaches
   ntfy titles, AI requests, INFO logs, and the report, and a search's
   `display_name` can be a street address.
5. *ntfy is a `Channel`, its topic and token live only in the environment, and
   the topic never enters a URL.* The project roadmap's 7.3 said "topic token in
   configuration"; its data classification says the token is handled like the
   API key. The classification wins, and it reaches the topic too: without an
   account "the topic name is your password" (ntfy's own FAQ). So
   `services/ntfy.py` reads `WEATHERBOT_NTFY_TOPIC` and the optional
   `WEATHERBOT_NTFY_TOKEN` from the runtime's environment, neither is a
   `Settings` field or an `ENVIRONMENT_OVERRIDES` entry, and `[notifications]`
   gains only `ntfy` (off by default) and `ntfy_server` (`https://ntfy.sh`,
   `https` required unless the host is loopback, for a self-hosted server). The
   channel posts JSON to the server's root, as ntfy documents ("not
   https://ntfy.sh/mytopic"), so the topic is in the body and never in a URL, a
   log line, or a proxy's access log, with `Authorization: Bearer` when a token
   is set, redirects refused, a 5-second timeout, and one retry after 3 seconds
   on a timeout, a 429, or a 5xx, because an escalation lost to a blip is the
   failure this channel exists to prevent. Deliveries run one after another
   under the cycle lock, whose waiters give up after 120 seconds, so a delivery
   spends at most 15 seconds and the channel comes last in every tuple, where
   nothing waits on it. `title` is the notification's title (ntfy allows 1 KB),
   `message` its body lines and the disclaimer's notice, cut to 4,000 bytes
   (ntfy turns anything past 4,096 into an attachment), and `priority` 5 for an
   escalation to level 5, 4 for any other escalation or level 4, 3 otherwise
   (priority 3 and above vibrate and sound by default), with `tags` from a fixed
   table. What leaves the machine is the location name, the level, and the
   engine's change sentences, which hold no distance (`engine/changes.py` reads
   names, numbers, and codes only; a test holds it there). ntfy.sh caches a
   message 12 hours, logs topics and addresses, forwards to Firebase for
   Android, and allows 250 messages a day; `docs/NOTIFICATIONS.md` says all of
   it, and that a self-hosted server avoids it. The channel's `interrupts` is
   true, so whatever holds a toast back holds it back too. With `[notifications]
   ntfy` off, `Context.channels` omits the channel entirely, because `notify
   test` exits 1 on any channel that reads `disabled`.
6. *A location's preferences choose channels, never decisions.* The pure policy
   decides what it decided before, so `decide` and the goldens are untouched.
   `LocationPreferences` (`toast`, `browser`, `phone`, each on by default, and
   `phone_min_level`, 2 by default) joins `Location`, stored in four plain
   `add_column` columns in revision 0009, and `NotificationService._deliver_one`
   skips a channel the location turned off, storing a delivery row that reads
   `muted` with the reason, so every notification still lands in the log with
   its trigger and its result (brief §9). `muted` is a new result, apart from
   `disabled`, because it says what a location chose and nothing about the
   channel: `latest_delivery` skips it, so a muted location can neither fail
   `doctor` nor hide a real failure. `phone_min_level` never strands the
   operator: a notification below it still reaches the phone when the location's
   previous notification did, because a drop carries the level it drops to, and
   an all-clear at level 1 must follow the alarm it ends. Escalations always
   notify in the policy's sense: an operator who silences every channel for a
   location has chosen the log for it, and the page says so. Quiet hours stay
   global, because the policy already holds them and the brief's rule is about
   levels, not places.
7. *The page edits `weatherbot.toml`, the one place settings live.* Settings
   load before any database opens and `weatherbot config show` needs no
   database, so a database-backed overlay would add a fourth origin to resolve
   at a moment the database is not there. `PUT /api/settings` takes a list of
   changes and applies them all or none: each `(table, key)` must be on a fixed
   allowlist (`[notifications]`: `cooldown_hours`, the three `quiet_hours_*`,
   `toast`, `browser`, `ntfy`; `[ai]`: `enabled`, `daily_cap_usd`,
   `change_summaries`, `outlook_narration`; `[retention]`: `history_days`), so
   no page can move `[web]`, `[engine]`, `[http]`, `[logging]`, `[monitor]`, or
   `ntfy_server`; a key the environment sets is refused with its variable's
   name; the result, merged with the environment exactly as `load_settings`
   merges it, must validate as `Settings` before a byte is written, so no save
   can leave `serve` unable to start; the request carries the SHA-256 of the
   file as `GET /api/settings` read it, and a mismatch answers 409, so a hand
   edit is never overwritten; and the write is a temporary file in the same
   directory and `os.replace`. `tomlkit` 0.15.2 (MIT, pure Python, no
   dependencies; checked 2026-11-03) keeps the operator's comments, which
   `tomllib` cannot write and `tomli-w` would drop. Each key states when it
   applies: the policy's keys and retention at the next cycle, because
   `MonitorSchedule`, which outlives the per-cycle `MonitorService`, re-reads
   the file then through a `live_settings` seam and keeps the last good settings
   if it stopped parsing; every other key at the next start, which the page's
   banner now names key by key, because `file_modified_since_start` turns true
   at every save. `GET /api/settings` re-reads the file on each request, or a
   saved value would snap back on the page.
8. *Retention is off by default, has one knob, and cannot disturb the policy or
   the next diff.* Deleting a person's history is the one irreversible thing
   this project does on its own, so `[retention] history_days` defaults to 0,
   which keeps everything; otherwise it is 30 to 3,650. The schema dictates the
   rest. `assessments.snapshot_id` is `ON DELETE CASCADE`, so a snapshot cannot
   outlive its assessments or go without taking them, their evidence, changes,
   notifications, decisions, deliveries, and AI outputs, which is why one window
   governs all of it. `_load_state` rebuilds a location's policy state from its
   decisions, so losing the last announcing row would read as a first assessment
   and send a duplicate escalation; and `AssessmentService` diffs against the
   latest assessment. So the keep-list holds the newest snapshot; each
   location's newest assessment; the assessment of its newest non-held `level`
   decision and of every decision after it; the snapshot of each; and the
   ledger's newest `pause` or `resume` row, whatever its age, because `Ledger`
   reads that row to decide `paused`. `raw_responses` rows go only when no
   outcome links them, and never the newest of a `(source_id, product_key)`,
   which is the validator store; `response_bodies` and `geometry_contents` go
   when nothing references them (the rows Phases 2 and 4 left for this phase);
   `ai_calls` older than the window go, and never one of the last 31 days. Work
   runs in batches of 100 snapshots and then of 500 orphans, each under `BEGIN
   IMMEDIATE` and `cycle.lock`, with the lock released and a second's pause
   after every batch, because `ProcessLock` polls and exposes no waiter, so a
   cycle is delayed by one batch at most. Revision 0010 first indexes four
   foreign keys, because SQLite checks each deleted parent by scanning an
   unindexed child: on this schema at 1.74 million synthetic links, 500
   `geometry_contents` deletes took 30.8 seconds, past the 30-second busy
   timeout, and 500 `response_bodies` deletes 9.1 seconds, against 2 ms and 1 ms
   with the indexes, which cost about 8 bytes a link (measured 2026-11-03). A
   run copies the database before its first delete, at most weekly, keeping two
   such copies, so the one irreversible thing has a way back. `weatherbot prune
   --dry-run` and the page state exactly what would go, and a run given that
   plan's cutoff removes nothing newer, because `run` takes the cutoff and never
   computes its own. `serve` always runs a daily worker beside the cycle
   watcher, because it starts once and the page can turn the knob on later: at 0
   it does nothing and promises no cadence, and above it a day any location
   reads level 3 or above counts as a success and prunes nothing. SQLite reuses
   freed pages, so growth stops; only `prune --vacuum`, refused while the
   monitor lock is held, shrinks the file. The worker's heartbeat (`watch`,
   `retention`) is its health signal, so the staleness alarm comes with it.
9. *The map's new vector layers come from what is already stored.*
   `StormProducts.wind_radii` holds the forecast radii and advisory wind field
   (Phase 5 served neither), and `Snapshot.display_layers` holds the summary
   service's `Past Points` and `Past Track`, which carry `binnumber`. But
   `/api/map` is the page's first paint, and the recorded radii alone hold 8,396
   vertices, so these layers travel apart: `GET /api/map/depth?snapshot_id=`
   serves each storm's `wind_radii`, `past_track`, and `past_points`, matched by
   slot and storm number and unwrapped like its other layers, with the
   snapshot's peak surge, the first time one of those toggles turns on.
   Probabilistic winds are heavier (568, 364, and 197 KB for the three recorded
   thresholds) and belong to the snapshot, not a storm (issue #12), so `GET
   /api/map/wind-probabilities?threshold_kt=&snapshot_id=` serves one threshold
   at a time, drawn by a Leaflet canvas renderer in NHC's band order. Every new
   layer starts off, so the default map and its first paint do not change, and a
   replay shows what the corpus holds: cones, tracks, points, watches, and its
   probability windows, and says plainly that past track, radii, and surge are
   not in the committed subset. The wind swath stays stored and undrawn.
10. *Peak surge is display-only, and its first proof is synthetic on purpose.*
    The `NHC_PeakStormSurge` layers were empty on 2026-10-12 and again on
    2026-11-03 (no active storm), so no live capture fixes their fields; the
    archived Milton file (`AL142024_PeakStormSurge_008adv.kml`, read 2026-11-03:
    1.16 MB, 38 placemarks) shows the semantics, a placemark named `Charlotte
    Harbor...5-10 ft` with a JSON description holding `peak_surge_range` and
    `color`. So `MapDepthResponse.peak_surge` passes through the `Polygons` and
    `Lines` display layers with only their `name` and geometry, the page colours
    each by the range after `...` through a fixed table and shows an
    unrecognized range in a neutral colour with its text, and a test fixture
    built in code at two decimals, labelled synthetic, drives the unit tests and
    the smoke (the personal-data rule refuses finer coordinates outside the
    recorded trees). The first live capture with features re-records under
    Source drift and replaces it. `StormSurgeRisk`, the static hazard raster, is
    not drawn: the project roadmap's 7.1 names peak surge, a catalog read stays
    `doctor`'s, and the register row says so.
11. *Radar and satellite are requested only while toggled on.* nowCOAST answered
    both WMS `GetMap` requests on 2026-11-03 with `Cache-Control: max-age=240,
    public`, and its capabilities state no fees or access constraints, so
    `L.tileLayer.wms` loads `conus_base_reflectivity_mosaic` from
    `weather_radar/ows` and `goes_longwave_imagery` (day and night) from
    `satellite/ows` in the browser, and `CSP_SUFFIX`'s `img-src` gains exactly
    `https://nowcoast.noaa.gov`. A tile request names a map tile, never a
    location, as OpenStreetMap's already does, and the project roadmap's §3
    records the new outbound host. Nothing polls: a layer loads when toggled and
    when the map moves, says how old a tile can be, and shows "Radar
    unavailable" on `tileerror`. They are live only: a replay or a stored
    advisory turns them off and says so, because today's imagery must not sit
    over a past storm. The Iowa Environmental Mesonet stays the register's
    documented fallback (its tile answered 200 today) and is not wired, because
    a second host needs a second CSP entry for a failure that has not happened.
12. *The time slider walks stored advisories, not every stored snapshot.* An
    unchanged cycle stores a snapshot too, so `GET /api/map/advisories` lists
    only the newest snapshot that carried each storm's advisory, read from the
    `storm_observations` summaries, newest first (the first could hold the
    previous cone, because Phase 4 measured the roster leading the GIS layers),
    and `GET /api/map?snapshot_id=` renders one through the existing eight-entry
    cache (a miss costs about 384 ms). The slider is a native `<input
    type="range">`, labelled by advisory and time, with "Back to latest", and a
    stored advisory reads as such so that it is never mistaken for the present.
    It reaches as far back as retention left, and the page's live updates pause
    while it sits in the past.
13. *The tile proxy stays unbuilt until OpenStreetMap refuses.* The project
    roadmap makes it conditional. Its condition has not fired: a tile requested
    on 2026-11-03 with a loopback `Referer` answered 200, and the operator's
    page has shown tiles since Phase 5. OpenStreetMap's policy says "We
    generally do not recommend putting your own caching proxy in front of
    tile.openstreetmap.org", and a server-side proxy would add a disk cache, a
    new route, and a new outbound path for a failure that does not exist. So
    Step 5 adds a live test that fetches one tile with a loopback `Referer`,
    which turns the condition into a signal, and an issue that holds the design
    (policy headers honoured, seven days' cache, a contactable User-Agent), and
    `docs/DATA_SOURCES.md` points at it.
14. *The wind-probability chart shows what NOAA publishes.* The project
    roadmap's 7.1 says "over the forecast period", but the `Probabilistic Winds`
    layers hold one cumulative 120-hour band per threshold per synoptic time,
    and a per-forecast-hour curve exists only in the GRIB2 files the register
    ruled out ("Gridded data would add a GRIB dependency for no rule in the
    brief"). So the chart plots, for each threshold, the location's official
    band at each stored synoptic time: a range, never a point, with `<5%` and
    `outside coverage` drawn as what they are. It answers the question an
    operator actually asks, whether the odds are rising, from products with
    provenance, and the project roadmap records the change. The arrival display
    reads the same `ArrivalReading`s the dashboard already prints and invents no
    time between them.
15. *Charts are hand-drawn SVG, with no new dependency.* Four small charts do
    not justify a chart library: the CSP has no `unsafe-inline`, so the
    project's rule is no `style=` attribute (Phase 6 used `<meter>` for the same
    reason); the main chunk is already 772 kB; and the report needs the same
    sparkline with no JavaScript at all, which `services/report.py` writes as a
    plain `<svg>` string. So `frontend/src/charts/` holds pure scale functions
    with tests and React components that render `<path>` and `<rect>` with
    Tailwind `stroke-`/`fill-` classes, each with `role="img"`, a `<title>`, and
    a visually hidden table of its values. `frontend/package.json`'s names do
    not change, so Phase 6's check 39 stays as it stands. Chart queries live
    under the `timeline` key and map listings under `map`, as Phase 6's did
    under `ai`, so server events reach them and no `QueryKey` is added.
16. *Replay is the same engine and the same components, and stores nothing.* The
    scrubber's data is `ReplayService.timeline`, which already assesses each
    advisory (measured 2026-11-03: 5.6 s for Dorian's 117, 4.3 s for Irma's 84),
    so `GET /api/replay/{atcf_id}/timeline?location=` computes it once in a
    worker thread and keeps at most eight timelines in memory, keyed by storm,
    location, and the ruleset's fingerprint; `GET
    /api/replay/{atcf_id}/{advisory}/assessment?location=` reads one step. The
    web layer imports the service, never the engine. The location's
    evacuation-order toggle is off for a past storm
    (`without_evacuation_order`), and the page says so. The `/replay` page
    reuses the dashboard's level, evidence, official-product, and threat
    components, which Step 7 extracts to `frontend/src/assessment/` rather than
    copies, and the map through `useLeafletMap`. Its "not live" banner cannot be
    dismissed, it shows no AI panel, and it publishes no event, sends no
    notification, and writes no row. Replay fits a monitor's first principle:
    the page shows that a level came from a named product at a named advisory.
    Issue #44's unfinished sentence ("whose cone does not.") would print on this
    page at every step outside a cone, so Step 7 finishes it.
17. *The corpus stays a directory the operator names.* Phase 3's ledger left
    this to Phase 7: ship it, download it, or keep it a path. The committed
    subset is 7.6 MiB of test fixtures, a download needs a new outbound host and
    a checksum story for a demo, and `[web] corpus` already exists. So an
    installed copy with no corpus shows the `/replay` page with what to set, a
    checkout's `tests/fixtures/replay` serves every acceptance here, and
    `convert --full` remains the way to replay an arbitrary location. Phase 8
    may revisit it for the release; nothing here blocks that.
18. *The report holds only what may already leave the machine, and the AI
    briefing joins it only when asked.* It is written to be handed to someone,
    and the data classification says coordinates are "redacted from exports". An
    assessment's `Evidence.detail` prints a whole-kilometre distance and the
    minute of closest approach, which with the public track pins a home (Phase
    6's review found it), and `Location.display_name` is a street address in
    words. So `services/report.py` renders from `services/ai/context.py`'s
    `briefing_context`, the model Phase 6 proved safe to send to Anthropic:
    levels, rules, distance bands, 8-point bearings, hours, and source titles,
    with no coordinate, polygon, address, zone, URL, path, or engine sentence,
    under that module's 90 percent floor. An issuer prints as `NWS` or `NHC`,
    because `OfficialRef.issuer` is the alert's `senderName`, which names the
    forecast office. It adds the location's chosen name and the level history as
    an inline SVG. The stored briefing joins only on request, because its words
    quote alert text: a recorded one says "NWS Miami covers coastal Miami-Dade
    County" (`tests/fixtures/ai/eval-briefing-recorded-miami-dade.sse`), which
    no scan can tell from prose. When asked for, it prints the newest briefing
    with its full label and a stale note if an older assessment wrote it, or
    nothing if it is withheld or absent, and the page says what the box adds.
    One self-contained HTML file: inline CSS, no script, no remote resource, a
    `<meta>` CSP of its own, every value escaped, and the disclaimer's notice at
    the top and in full at the end. PDF is the browser's print, styled by
    `@media print` and proved by Chromium's `page.pdf()`, because a PDF library
    would be a heavy dependency for what every browser already does. The map
    stays out: a static map needs tiles or a marker at the location.
19. *The earlier phases' checks stay green, with one planned conversion.*
    Earlier roadmaps' lists of exact checks were incomplete, so this one rests
    on an audit of all six verifiers and their mutation tests against every
    planned change (2026-11-03). Only Phase 6's check 44 (`README.md`'s `##
    Status`) converts: Step 1 first edits that section, so the check moves to
    `tagged("README.md", tag=PHASE_6_TAG)` in the same PR, with its mutation
    case, as Phase 6 Step 1 did for Phase 5's check 47 (`tagged` defaults to the
    Phase 5 tag, so the keyword matters). Every other collision is kept green by
    how the work is done, which the table under "Verification surfaces" states
    check by check, and which the project roadmap's Phase 7 note now points at.
    This matters more than it looks: Phases 3 to 6 assert `failed == [check]` in
    their mutation tests, so one live red check fails every case in that file.
    No check is added to an older script, because each phase's `--post` pins the
    last phase's total (Phase 7 must assert 79). Phase 7's own verifier pins
    check 44's conversion, as Phase 6's check 31 pinned Phase 5's, and adds the
    absolute ban no script has today: no `style=` attribute under
    `frontend/src`, which only the CSP and the smoke enforce.
20. *The version stays `2.0.0.dev0`, so health names the build.* `/api/health`
    keeps naming the built interface and the database head, so a Deployed &
    verified check tells this build from the last without a version bump; the
    `v2.0.0-phase-7` tag marks the phase, and Phase 8 owns the release
    candidate.

**Branch strategy.** Every step in this phase lands on its own short-lived
feature branch (`feature/phase07-step<M>-<slug>`), opens a pull request against
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
git checkout -b feature/phase07-step<M>-<slug>
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
feature/phase07-step<M>-<slug> <worktree-path> origin/main`, the worktree is
bootstrapped before any test or build (`uv sync` and `npm ci` in its `frontend/`
— a worktree has none of the primary tree's untracked state, such as `.venv`,
`frontend/node_modules`, the built interface, or the replay cache, and it must
never borrow the primary tree's `.venv`), the Stage 4 merge runs from the
primary tree, and Stage 5 removes the worktree BEFORE pruning the branch.
Undeclared parallelism is a lifecycle violation, not a shortcut. Worktree
location for this project: git-ignored `.worktrees/<branch-slug>/` inside the
repository, matching the project roadmap.

**Security-first execution rule.** Security is not a phase — it is a gate on
every commit of every step. Before each `git commit`, the step's work must pass
the local, fail-closed security gate: secret/personal-data scan clean, SAST
clean, dependency audit clean, and a diff review confirming no sensitive data
(the operator's coordinates, address, or typed place, credentials, tokens, an
ntfy topic) and no new insecure pattern (injection, a subprocess built from a
shell string, unsafe deserialization, a path read outside the directory it
names, a coordinate or a search text in a log line above DEBUG or in the
browser's console, a key or token in a fixture, a response readable from another
origin, a state-changing request a cross-site page could send). The gate is
wired into the pre-commit hook and re-run in CI, so a security issue introduced
while implementing a step is caught during development — before it reaches the
branch, the PR, or `main`. See the project roadmap's "Security & privacy
strategy" → "Per-step security gate" for the canonical checks and tooling; each
step's XML `<task>` carries a `<security>` block restating them for the agent,
and each step's Acceptance Criteria ends with a security check. AI coding agents
executing a step MUST treat the security gate as part of the step's definition
of done, exactly like its tests. This phase brings a second secret (the ntfy
topic, which on a public server is itself the password, and its optional token),
three new ways for the operator's data to leave the machine (a typed place to
Nominatim, a location name and level to the ntfy server, and a report the
operator hands to someone), and the project's first destructive job. So the
topic and token live only in the environment and never in a setting, a URL, a
log record, a row, an answer, or a fixture; a search runs only when the operator
submits it, its text is redacted like a coordinate and kept only in memory, and
the location's name is one the operator typed; the report holds only what Phase
6's context already allows off the machine, and an AI briefing only when asked;
and a prune deletes nothing newer than its plan's cutoff, after a copy of the
database. No step reads, prints, or quotes the operator's coordinates, their
place, an assessment of it, or a topic or token; agents verify with the two
public landmarks in a temporary data directory.

**Deploy-and-verify rule.** Merged is not deployed, and deployed is not
released. Every step header carries a `**Deploys:**` line naming the surface and
environment the step's merge reaches — or `nothing beyond merge` — and when
going live needs a reinstalled copy, a restarted task, a migration, or a tag,
the line says so and this step (or a named follow-on step) owns that event.
Steps 2, 3, and 9 deploy to the operator's machine; the steps between them merge
to `main`, and the operator's copy takes them at Step 9. For a step whose
Deploys line names a surface, Stage 4 of the lifecycle does not end at the
squash-merge: the step's acceptance criteria carry a **Deployed & verified**
bullet (`GET http://127.0.0.1:8765/api/health` on the operator's machine answers
from the reinstalled copy with this step's build, and the changed behaviour is
exercised there by the hands-off recipe the step names), and that bullet must be
green before the step is declared complete. Step 3 introduces a required secret
for its feature: it verifies at kickoff — before writing code that depends on it
— that the operator has a place to set `WEATHERBOT_NTFY_TOPIC` (and
`WEATHERBOT_NTFY_TOKEN` if their server needs one), and it proves them by an
authenticated round-trip, a real delivery the operator confirms on the phone,
never by listing a variable's name. No value ever transits a chat, a PR, a log,
or a fixture, and an agent hands the operator a command to run rather than
asking for a value. Migrations run at the service's start after its backup,
expand-only, with plain `add_column`, never a batch rebuild (Phase 3 measured a
rebuild of `locations` cascading deletes). A step reinstalls the operator's
copy, restarts `\Weatherbot\serve`, edits the operator's `weatherbot.toml`,
sends a notification to the operator's phone, or opens a page on the operator's
desktop only after the operator says yes to that exact action (AskUserQuestion);
an agent verifies with the public landmarks in a temporary data directory and
reads the operator's service only through `/api/health`, `doctor`, and the
notification log's delivery results. See the project roadmap's "Release &
deployment strategy" for the surfaces table, promotion path, and rollback.

**Triage rule.** Findings surfaced while executing a step are classified before
they are acted on, per the project roadmap's "Defect handling & triage": spec
rot → edit this roadmap's affected `<task>` block now; upstream gap → patch the
earlier step's prompt and add it to the carry-over checklist; implementation bug
→ fix in-step only if it blocks this step's acceptance criteria, otherwise an
issue and its own branch in a fresh conversation; architectural question → an
issue for a future phase; process improvement → recorded where the next
conversation will read it; security finding → jumps the queue by severity;
source drift (a NOAA, Nominatim, or ntfy shape changed or vanished) → re-record
the affected source, update `docs/DATA_SOURCES.md` with the date, and add a
contract test in the same PR. The OpenAPI document is a contract: a change to a
route or a response model regenerates `docs/api/openapi.json` and the frontend's
generated types in the same PR, and CI fails while either is stale. A golden
that changes is never "fixed" by regenerating it: an engine or policy change
that moves a replay or notification golden needs the operator's approval in the
PR, and this phase changes neither. A step's PR contains the step plus blocking
fixes only, and lists the issues it opened. When a merged PR auto-closes an
issue, the environment check is what earns the close — reopen or follow up if a
gap remains. `docs/phase07-qa-findings.md` is the rollup: every finding, its
class, and the guard added so the class cannot recur.

**Status rule.** Every step carries a `**Status:**` line directly under its `##
Step N — …` heading, before the Goal, and this file on `main` is the ledger of
what is done — never a chat transcript, never a later conversation
reconstructing history from `git log`. The line reads `Not started` when this
roadmap is written and is flipped by the step's OWN pull request: at Stage 3,
right after `gh pr create` returns the PR number, the agent sets it to `Complete
— PR #<n> (<YYYY-MM-DD>)`, appends ` ✅` to the step's heading (`## Step 7 —
Replay in the UI ✅`) so the completion shows in the rendered preview, the
outline, and the table of contents, sets the step's Summary Table Status cell to
`Complete — PR #<n>`, commits that edit on the step branch, and pushes. The PR
therefore carries its own completion mark, and the roadmap on `main` says a step
is complete exactly when that step's PR merges — never before. This file's
phase-level `**Status:**` line (under the title) and the project roadmap are
marked the same way, in the same commit: Step 1's PR flips both from `Not
started` to `In progress` (the project roadmap's `### Phase 7` line reads `In
progress — phase07-roadmap.md`, and its row in the "Phase Complexity Summary"
table reads `In progress`), and the final step's PR flips both to `Complete — …`
(the project roadmap's with its row in the "Phase Complexity Summary" table and
the header `> **Status:**` line) and appends ` ✅` to this file's `# ` title and
to the project roadmap's `### Phase 7` heading, so the project roadmap shows a
finished phase the way this file shows a finished step. There is no separate
"update the roadmaps" chore: a step whose PR merged without its Status line is a
lifecycle violation, and the next step's Stage 1 (and `/roadmap-step`) refuses
to start until the previous step reads `Complete`. If a post-merge check fails —
a Deployed & verified bullet, an alarm that never fired — the step is NOT
complete despite the merged line; say so, and the `hotfix/` PR that completes it
appends its own number to the line. `grep -n '^\*\*Status:\*\*'` on this file is
the phase's progress report, and the ✅ headings are the same report at a glance.

**Step lifecycle.** Every step in this phase follows the exact same six-stage
lifecycle, in order, with no exceptions. Each stage is a hard checkpoint — if a
stage is skipped, branch protection or the next step's Stage 1 will fail loudly,
and that is the safety net. AI coding agents MUST execute all six stages before
declaring a step complete.

1. **Create the branch.** Before any Read / Edit / Bash, run `git checkout -b
   feature/phase07-step<M>-<slug>` from a clean, up-to-date `main`. The exact
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
   branch (`docs: mark Phase 7 Step <M> complete`), and push — the PR now
   carries its own completion mark, so the roadmap on `main` will say the step
   is complete exactly when the PR merges (Status rule). On the phase's first
   step, the same commit sets this roadmap's phase-level `**Status:**` (under
   its title) and the project roadmap's Phase 7 `**Status:**` to `In progress`;
   on the final step, both to `Complete`, with ` ✅` appended to this roadmap's
   `# ` title and to the project roadmap's `### Phase 7` heading.

4. **Wait for green checks, then squash-merge.** Every required status check
   must report success: the aggregate `gate` check of `ci.yml` (lint, typecheck,
   the test matrix with the coverage floors, the package smoke, the frontend,
   the browser smoke, and the security scan) and the aggregate `phase-verify`
   check (`phase-verify (01)` through `(07)`, and `(07)` from Step 10). If the
   PR goes BEHIND main while waiting, refresh with `gh pr update-branch
   --rebase` — never merge `main` into the branch; `required_linear_history:
   true` enforces rebase. Once every check is green:

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

## Current State (as of Phase 6)

### Location surface

- `services/locations.py`'s `LocationService.add(name, lat, lon, polygon)`
  checks the name and the point, asks NWS `/points`, optionally fetches a zone
  shape, reverse-geocodes once through `sources/nominatim.py`, and stores the
  location. `sources/nominatim.py` holds `reverse_geocode` and no search; the
  register's `geocode-nominatim` row and fixtures describe `/reverse` only.
- `sources/nws.py`'s `parse_point` reads `forecastZone`, `county`, `cwa`,
  `timeZone`, and `relativeLocation`'s city and state with `fields.text`, which
  raises on an absent or null field, and `models/location.py`'s `NwsCoverage`
  types `county_zone` as `str` and `cwa` as `^[A-Z]{3}$`. A marine-zone point's
  answer omits `county` (Decision 3), which is issue #87. `fetch_alerts` builds
  its three requests with `zone_alerts_url(coverage.county_zone)`, and
  `LocationRow`'s `nws_coverage_whole` CHECK ties the six NWS columns' nullness
  together.
- `web/routes/actions.py`'s `POST /api/locations` is a sync route running
  `asyncio.run(service.add(...))`; it maps any `SourceError` to the fixed detail
  `<source> did not answer (<kind>)` and logs nothing. There is no remove route
  and no search route. `cli/locations.py`'s `add` requires `--lat` and `--lon`,
  and `frontend/src/pages/Settings.tsx` (839 lines) has one add form with
  decimal fields, a list, and no remove.
- The fetcher paces each host per run (`api.weather.gov` 1.2 s, Nominatim 1.5
  s), and a run's fetcher lives for one request here, so pacing does not span
  two searches: the route needs its own cooldown. `redact_text` and the query
  redaction in `sources/http.py` key on `COORDINATE_PARAMETERS` (`point`, `lat`,
  `lon`, `latitude`, `longitude`).

### Notification surface

- `services/notifications.py` defines the `Channel` protocol (`name`,
  `interrupts`, `deliver`), `LogChannel`, `CHANNEL_NAMES` (`log`, `toast`,
  `browser`), the four `DELIVERY_RESULTS`, the five `NOTIFICATION_KINDS`, and
  `_deliver_one`, which runs each channel in turn and stores one
  `notification_deliveries` row per attempt. `notification_deliveries.channel`
  is free text with no CHECK, so a new channel needs no revision.
- `Context.channels` (`cli/runtime.py`) is the log and the toast; `cli/serve.py`
  adds `BrowserChannel`; `check` and `notify test` use the context's. `notify
  test` exits 1 when `delivery_failed` reads a failed or disabled result, so a
  channel that is merely off must not be in the tuple at all. `TEST_BODY` says
  "toasts work".
- `services/policy.py` is pure and holds at 90 percent branches on its own:
  `QuietHours`, `QUIET_HOURS_MAX_LEVEL`, cooldown per event, and an escalation
  that always sends. Quiet hours already work: `[notifications]
  quiet_hours_start`, `quiet_hours_end`, and `quiet_hours_time_zone` reach
  `decide` through `Settings.policy_settings`. `MonitorService._locked` builds a
  `NotificationService` per cycle from the `Settings` it was given at start.
- `services/logs.py`'s `SecretFilter` and `redact_secrets` remove Anthropic key
  shapes and `Authorization` and `X-Api-Key` values from every record and
  traceback, so a Bearer header is covered already and an ntfy token's shape and
  a topic's value are not. `services/doctor.py` has the `toast` check as the
  pattern for a channel check.

### Settings surface

- `services/config.py` reads `weatherbot.toml` with `tomllib`, applies the
  literal `ENVIRONMENT_OVERRIDES`, and validates frozen sections with
  `extra="forbid"`; its docstring states the rule that a setting is never a
  secret, a location, or a coordinate. `setting_origins` says where each value
  came from and needs every key to have an override entry. Nothing writes the
  file, and no runtime dependency can.
- `GET /api/settings` lists every value, origin, and variable, and
  `file_modified_since_start`, which the page shows as a restart note. The
  page's AI section reads `[ai]` and cannot edit it (Phase 6, Decision 13 left
  editing to this phase).

### Persistence surface

- Revisions 0001 to 0008 are pinned in `FROZEN`
  (`tests/services/test_database.py`), `tests/services/test_tables.py` asserts
  the exact table set, and revisions use plain `add_column` on `locations`,
  never a batch rebuild, because a rebuild with foreign keys on cascades deletes
  (measured in Phase 3). Every connection sets `foreign_keys=ON`, WAL, and a
  30-second busy timeout, and every writing transaction begins `BEGIN
  IMMEDIATE`.
- `assessments.snapshot_id` and `assessments.location_id` are `ON DELETE
  CASCADE`; so are evidence, changes, notifications, decisions, and `ai_outputs`
  through the assessment. `raw_responses` are linked by `outcome_responses` with
  no cascade, and `monitor_cycles.snapshot_id` and `notifications.cycle_id` are
  `SET NULL`. `geometry_contents` no snapshot links "stays until Phase 7's
  retention" (`persistence/repositories.py`, `tables.py`, and `CONTRIBUTING.md`
  say so). No code deletes history today.
- `NotificationService._load_state` rebuilds a location's `PolicyState` from
  every decision row, and `AssessmentService._assess_one` diffs against the
  latest assessment at or before the snapshot: the two readers a prune must not
  disturb. Storage grows 64 KiB per unchanged cycle, as Phase 4 measured, and
  about 2 MiB per new advisory's geometry.

### Map surface

- `web/map_layers.py` builds `MapResponse` and `StormMapLayersResponse` (cone,
  track, forecast points, and watch-warning segments per storm, outlook areas,
  locations) through an eight-entry `SnapshotLayerCache`, unwrapping
  antimeridian crossings from each storm's first point. Its docstring leaves
  wind radii, wind probabilities, and surge to this phase. `GET /api/map` serves
  the latest snapshot and takes no parameter.
- The snapshot already holds what the new layers need:
  `StormProducts.wind_radii` (`threshold_kt`, `tau_h`, `valid_at`, and four
  extents), `Snapshot.wind_probabilities` (one product per threshold, 11 bands
  each in the recording), and `Snapshot.display_layers` (the raw `Past Points`,
  `Past Track`, `Past Cumulative Wind Swath`, and peak-surge `Points`, `Lines`,
  and `Polygons` collections). Past Track features carry `binnumber`, such as
  `EP5`.
- `frontend/src/map/layers.ts` defines six `MapLayerKey`s, `LAYER_TOGGLE_ITEMS`,
  `MAP_LEGEND_SECTIONS`, and the style functions; `useLeafletMap.ts` keeps one
  `L.Map` per container and rebuilds layers on change; `MapView.tsx` holds the
  replay picker. Popups and tooltips are DOM nodes built with `textContent`
  (Leaflet treats a string as HTML), and legend swatches use Tailwind classes,
  because the CSP has no `unsafe-inline`.
- `web/guards.py`'s `CSP_SUFFIX` allows `img-src 'self' data:
  https://tile.openstreetmap.org`. `frontend/e2e/guard.ts` aborts and fails any
  request to another origin and fulfils OSM tiles with a blank PNG.

### Charts and history surface

- `GET /api/timeline` merges assessments and notifications, newest first, to at
  most 500; `AssessmentRepository.history(name, limit)` decodes each row's JSON,
  about 1 ms a row. `frontend/src/pages/Timeline.tsx` filters by location on the
  client and has no older-page control.
- `frontend/src/pages/Dashboard.tsx`'s `LocationLevelCard` prints the level,
  rule, evidence, official products, and a threat table with the arrival
  readings as text; the wind readings are `LocationWindProbability` records
  (`threshold_kt`, `synoptic_at`, `reading`, `label`, `lower_pct`, `upper_pct`)
  in each assessment. No chart exists. `frontend/package.json` has no chart
  library, and the main chunk is 772 kB.

### Replay surface

- `services/replay.py`'s `ReplayCorpus` reads the committed subset or a full
  conversion, `ReplayService.timeline(atcf_id, location, thresholds)` assesses
  every advisory in memory, and `without_evacuation_order` clears the toggle.
  `cli/replay.py` prints the transitions. `GET /api/replay` and `GET
  /api/replay/{atcf_id}/{advisory}` serve the corpus's list and one advisory's
  map; `/api/health`'s `corpus` tells the page to show `MapView`'s picker and
  its "not live" banner. Assessments are not served: Phase 5 left the level to
  this phase.
- The golden ladders fix what the scrubber must show. Dorian 2019 at Nassau
  reads level 3 at advisory 8, level 4 at 24 (`HWA`), level 5 at 26 (`HWR`),
  level 4 at 41A (`TWR`), and level 1 at 44, across 117 advisories; Irma 2017 at
  Miami-Dade reads level 4 at 34, level 5 at 36, level 4 at 48, level 2 at 49,
  and level 1 at 51, across 84. An advisory in the committed subset holds its
  cone, track, points, and watch-warning files, and its probabilities are
  windows around the two landmarks; there is no radii, surge, or past-track
  file.
- Issue #44: `engine/changes.py` writes `NHC issued advisory {n} for {storm},
  whose cone does not.` for an advisory whose cone does not cover the location.

### Security & sensitive-data surface

- The operator's coordinates live in the local database and `repr=False` fields;
  `tests/cli/test_cli_privacy.py` and `tests/web/test_api_privacy.py` scan
  output for them, and `scripts/check_personal_data.py`'s R2 refuses a
  coordinate pair at three or more decimals in any tracked text outside
  `tests/fixtures/recorded` and `tests/fixtures/replay`.
- The Anthropic key is the SDK's to resolve; Phase 6's rule (no copy, no log, no
  row, no answer, no bundle) is the pattern for the ntfy secrets. Tests build
  fake keys at run time, because Phase 1's check 29 and gitleaks read every
  tracked byte. `tests/conftest.py` deletes every `ANTHROPIC_*` and
  `WEATHERBOT_*` variable, the ntfy secrets included, and sets
  `WEATHERBOT_NOTIFICATIONS_TOAST=false`, so `toast` reads as environment-set in
  every test.
- `services/ai/context.py` holds the privacy-reduced models (`LevelRef`,
  `EvidenceRef`, `OfficialRef`, `WindRef`, `ArrivalRef`, `ThreatRef`,
  `ChangeRef`) and the public `briefing_context`, with `distance_band`,
  `compass8`, and `to_hour`, under its own 90 percent floor. It imports no I/O,
  so the report can use it without loading the SDK. Writes are same-origin JSON
  under `FetchMetadataAndWriteGuard`; `/api/` answers are `no-store`.

### Operations & observability surface

- `/api/health` reports the version, the schema head, the scheduler, heartbeats,
  the built interface, and the AI block; `doctor` runs its named checks;
  `next_staleness_boundary` and `StalenessTimer` raise the dashboard's banner
  when a heartbeat passes twice its cadence, and `doctor`'s `heartbeat` check
  reads the same rows. `HeartbeatRepository.record(kind, name, ...)` takes
  `source`, `watch`, or `runner`.
- The operator's service runs under `\Weatherbot\serve` from
  `C:\Users\Admin\.local\bin\weatherbot.exe`, with `\Weatherbot\check` as the
  hourly fallback at HH:25. A deploy is `schtasks /End`, `npm ci` and the build,
  `uv tool install --reinstall --from <checkout> weatherbot`, and `/Run`. Bare
  `weatherbot` on `PATH` is version 1. The scheduled task sees a new
  user-environment variable only after it restarts. Idle was 0.2500% server and
  0.0026% tab over 600 s at Phase 6's close.

### Documentation surface

- `docs/DATA_SOURCES.md` is the register, whose tables are generated and whose
  field lists contract tests parse; `docs/ALERT-LADDER.md` holds the ladder;
  `docs/AI.md` the Claude layer; `README.md` the Status, Commands, and
  dashboard; `CONTRIBUTING.md` the developer loop. No document covers ntfy,
  retention, or the report yet.

### Verification surfaces

- `scripts/verify_phase06.py` is the structural template: 51 standard-library
  static checks, nine modes (`--fast`, `--py`, `--node`, `--ui`, `--live`,
  `--ai`, `--security`, `--all`, `--post`), and 28 V rows built from JUnit
  evidence in which every selection must match a test, a failure fails, and a
  skip is never a pass. Its `--post` nests Phase 5's (which nests 4, 3, 2, and
  1), reads the operator's service, and runs the ten-minute idle measurement.
  The totals, 75, 73, 80, 80, 85, and 79, are pinned by each phase's test file
  and by the next phase's `--post`.
- `.github/workflows/phase-verify.yml` runs matrix entries `"01"` to `"06"`
  (`--fast` and `--security` each) under the required aggregate `phase-verify`,
  with gitleaks pinned by checksum. Its matrix must stay a one-line list,
  because six checks read it with `phase:\s*\[`. Node is set up by separate
  steps under the literal conditions `matrix.phase == '05'` and `'06'`, which
  Phase 5's check 52 and Phase 6's check 50 read. Step 10 appends `"07"` with
  Node steps of its own; the six entries stay. `ci.yml`'s timeouts are lint 10,
  typecheck 10, frontend 10, test 40, package 15, browser 15, security 15, and
  gate 5.
- Checks of the earlier phases that this phase's growth could turn red, and how
  each stays green:

| Check | Reads | How Phase 7 keeps it green |
| ----- | ----- | -------------------------- |
| P1 4 | one `## [Unreleased]` | one heading stays |
| P1 10 | v1's deleted paths | new docs and tests avoid them |
| P1 32 | register ids hyphenated | ntfy is not a register source |
| P2 16, 20 | `verify=False`, xml imports | neither is added |
| P2 28 | `point=`, `/points/` literals | also `endpoint=`, `checkpoint=` |
| P2 30 | literal `create_table` names | 0009 uses literals |
| P3 5 | the job's coverage tokens | kept; `-n auto` added |
| P3 8 | unique test basenames | checked against `git ls-files` |
| P3 24, P4 14 | literal overrides | literal new entries |
| P5 6, 20, P6 3 | `literal_eval` of overrides | no comprehension or `**` |
| P2 36, P3 43 | `app.command` literals | `prune`, `report` are literal |
| P3 47 | `locations evacuation` | kept in README |
| P3 V6.5 | `--lat=` forms | `--lat`, `--lon` stay valid |
| P4 8, 17, 43 | triggers, decisions, kinds | none added |
| P4 20 | two notification goldens | unchanged |
| P4 36, P5 7, 23 | `serve`'s calls | kept; append only |
| P4 V2.5 | a fresh `doctor` exits 0 | `ntfy` skips while off |
| P5 4 | CSP tokens | append to `img-src` |
| P5 14 | cache size 8 | kept; `snapshot_id` uses it |
| P5 17, P6 32 | sync routes | new read routes are `def` |
| P5 40, P6 39 | pins and dependency names | no npm change |
| P5 41, 47 | OSM URL, `### The dashboard` | kept |
| P5 52, P6 50 | `'05'`, `'06'` conditions | separate `'07'` steps |
| P6 5 | `AI_TABLES` exactly two | retention uses the main engine |
| P6 10 | `SILENT_LIBRARIES` exactly | left as it is |
| P6 14 | `context.py`'s pure imports | report imports it, not reverse |
| P6 30 | literal kinds and keys | no kind or key added |
| P6 34 | `serve`'s summarizer calls | kept; append only |
| P6 38 | `innerHTML`, tests included | tests use `querySelector` |
| P6 40 | `/ask` between two items | `/replay` goes after `/map` |
| P6 41 | `serve_demo.py` flags | kept |
| P6 42 | ports 8799, 8800, 8801 | kept; a new port may join |
| P6 44 | README's Status | read at the tag (Step 1) |

- Pinned tests no verifier names, each updated in the step that touches it. Step
  2: `tests/contract/test_nws_captures.py` (every `geocode-nominatim` capture is
  parsed as a reverse lookup, so filter on the `reverse-` prefix at lines 258
  and 376; a deletion test expects `county` to raise, so give it the branch
  `OPTIONAL_ALERT_FIELDS` has; `FIELDS_READ` must equal the section's first
  "Fields v2 uses" bullet, so search gets `SEARCH_FIELDS_READ` and a bullet
  after it), `tests/sources/source_support.py` and `tests/cli/cli_support.py`
  (the newest live directory must hold `reverse-*.json`, so a new dated
  directory re-records the reverse captures with the search ones and the old
  directory goes in the same PR), `tests/scripts/test_record_fixtures.py` (its
  fake server has no `/search`), `tests/models/test_conventions.py` (`SAMPLES`
  needs each new public model), and `scripts/export_schemas.py`
  (`docs/schema/locations.schema.json` embeds `NwsCoverage`). Step 4:
  `tests/cli/test_documents.py` (`len(DOCUMENTS)`, 17 to 18; `holding ==
  {"locations"}`, so no other document holds a coordinate key). Step 5:
  `frontend/src/map/layers.test.ts` (six legend categories; every item needs
  `crsText`), `MapView.test.tsx` (every toggle checked, so iterate the
  default-on six), `frontend/e2e/guard.ts` (one tile origin), and
  `tests/web/test_map_layers.py` line 118 (`wind_radii` stays out of
  `/api/map`'s answer; it travels in `/api/map/depth`). Step 7:
  `frontend/src/app/AppShell.test.tsx` (seven navigation labels). Each new route
  joins `tests/web/test_api_privacy.py`. `frontend/e2e/map.spec.ts` counts two
  radius-8 markers, so no default-on layer may draw one.
  `tests/services/test_database.py` holds `FROZEN` (0009 and 0010 join it) and
  the two AI tables' exact index sets, so revision 0010 leaves those tables
  alone.
- Two traps no test catches. `sources/http.py`'s `_COORDINATE_QUERY` is
  hard-coded, so adding `q` to `COORDINATE_PARAMETERS` alone reaches
  `redact_url` and not `redact_text`: extend both. `services/ai/ledger.py`'s
  `paused` is the newest `pause` or `resume` row, of any age, so retention must
  keep it, and `raw_responses`, `outcome_responses`, and `snapshot_geometries`
  have no cascade to their parents, so delete order matters. Phase 3's check 8
  also means `services/` and `web/` cannot both hold `test_report.py`; Step 8
  uses `test_report_render.py`, `test_api_report.py`, and
  `test_report_command.py`. The schema exporter is `scripts/export_schemas.py`.

### Carry-over from Phase 6

Every item earlier phases handed to this phase, and where it lands:

| Item | Source | Lands in |
| ---- | ------ | -------- |
| Issue #87 (`parse_point`, no log line) | P6 QA ledger | Step 2 |
| Issue #71 (forward geocoding) | P5, P6 QA ledgers | Step 2 |
| Issue #82 (Windows test duration) | P6 QA ledger | Step 1 |
| Issue #44 (`advisory_issued` wording) | P4, P5, P6 ledgers | Step 7 |
| ntfy, quiet hours in the page | P4, P6 ledgers | Steps 3, 4 |
| Per-location notification settings | P4 QA ledger | Step 3 |
| Editing `[ai]` from the page | P6 Decision 13 | Step 4 |
| Retention (`geometry_contents`, raw) | P2, P4 ledgers | Step 4 |
| Retention (`ai_calls`, `ai_outputs`) | P6 QA ledger | Step 4 |
| Display layers, wind radii, surge | P2, P5 ledgers | Step 5 |
| Radar, satellite, overlay terms | P1, P5 ledgers | Step 5 |
| Tile-proxy fallback | P5 QA ledger | Step 5 (Decision 13) |
| Peak-surge fields at first capture | P2 QA ledger | Step 5 (Decision 10) |
| Charts, comparison, history views | P5, P6 ledgers | Step 6 |
| Replay in the UI; how a copy gets it | P3, P5 ledgers | Step 7 (Decision 17) |
| Report export with AI blocks | P5, P6 ledgers | Step 8 |
| Convert the checks Phase 7 changes | P6 ledger | Decision 19 |
| Issue #79 (`minimatch`, dev tooling) | P6 QA ledger | its issue |
| Issue #33 (surge and extreme wind) | P5, P6 ledgers | the operator |
| The `PATH` shadow of version 1 | P5, P6 ledgers | the operator |
| Dependabot #8, #31, #47, #78, #85 | open 2026-11-03 | maintenance |

---

## Execution Order

```
Step 1  (test budget)                     pytest-xdist + -n auto on the ci
                                          test job + README Status
                                          → implement
  ↓
Step 2  (locations)                       #87 + #71 search + --place +
                                          add and remove in the page +
                                          Nassau + the operator's place
                                          → implement
  ↓
Step 3  (the phone)                       ntfy channel + secrets +
                                          preferences (0009) + doctor +
                                          quiet hours proved + a real buzz
                                          → implement
  ↓
Step 4  (settings + retention)            PUT /api/settings + tomlkit +
                                          the page's editors + prune (0010) +
                                          daily worker + keep-list
                                          → implement
  ↓
Step 5  (map depth)                       radii + past track + surge +
                                          wind probabilities + radar and
                                          satellite + time slider + CSP
                                          → implement
  ↓
Step 6  (charts + history)                /api/charts + SVG charts +
                                          comparison strip + older pages
                                          → implement
  ↓
Step 7  (replay in the UI)                timeline + assessment routes +
                                          /replay page + shared components
                                          + #44
                                          → implement
  ↓
Step 8  (report)                          services/report.py + GET
                                          /api/report + weatherbot report
                                          + print to PDF
                                          → implement
  ↓
Step 9  (whole phase, operator's copy)    full smoke + idle + alarms
                                          + the operator's service
                                          → implement
  ↓
Step 10 (QA + verify_phase07.py)          scripts/verify_phase07.py
                                          + docs/phase07-qa-findings.md
                                          + phase-verify.yml entry "07"
                                          → create

--- post-implementation ---

V1  The test job runs in parallel inside its bound, with every
    coverage floor unchanged.
V2  A no-county point is watched; search finds a place on submit
    only; add and remove work; Nassau reads the breakpoint path.
V3  ntfy delivers; topic and token appear nowhere; quiet hours
    hold a repeat and pass an escalation; a phone buzzed.
V4  The page edits weatherbot.toml safely; a prune removes only
    its dry run, and every policy state reads the same.
V5  Every layer renders from fixtures; overlays load only on
    toggle; the slider walks stored advisories.
V6  Charts draw official bands from stored history, with no new
    dependency and no style attribute.
V7  The scrubber shows the golden ladders from the same
    components; nothing is stored, sent, or published.
V8  The report opens offline with its disclaimer and AI labels,
    and holds no coordinate, address, zone, URL, or sentence.
V9  The whole flow passes offline; idle is unchanged; each alarm
    fired; the operator's service runs the phase.
V10 verify_phase07.py --fast and --security exit 0 in
    phase-verify (07); the phase is closed.
```

Steps are sequential by dependency. Step 1 buys the CI time every later step
spends. Step 2's fix is what lets the operator watch their own place, and its
`Location` change is what Step 3's preferences extend. Step 4's settings write
is what the quiet-hours form needs, so the phone ships first with the file as
its editor, and Step 4 follows. Steps 5, 6, and 7 all edit `web/schemas.py`, the
OpenAPI document, and the frontend fixtures, and Step 7 reuses Step 5's slider
and map layers and Step 6's sparkline; Step 8's report reuses that sparkline's
scale and the fixtures of every step before it; Step 9 drives Steps 1 to 8 end
to end and deploys them; Step 10 verifies every prior step. Steps 2 to 8 share
`web/schemas.py`, `docs/api/openapi.json`, and `frontend/src/test/fixtures/`, so
this phase draws no steps in parallel, and the Worktree rule permits no
concurrent steps.

---

## Step 1 — The test budget ✅

**Status:** Complete — PR #90 (2026-11-03)

> **Goal:** Buy the CI time every later step spends. `pytest-xdist` joins the
> dev group, and the `test` job in `.github/workflows/ci.yml` runs the same `uv
> run pytest` line with `-n auto`, keeping its four `--cov` flags,
> `--cov-branch`, `--cov-fail-under=90`, and the three per-file `coverage
> report` steps; `pyproject.toml`'s `addopts` stays serial, so a developer's
> `pytest -k ...` and the verifiers' own runs do not change. Whatever the
> parallel run exposes in a test is fixed there, not skipped. `README.md`'s
> Status turns to Phase 7 in progress, Phase 6's check 44 moves to its tag in
> the same PR, and both roadmaps flip to In progress. Closes issue #82.

**Branch:** `feature/phase07-step1-test-budget`

**Deploys:** GitHub Actions → `ci.yml`'s `test` job changes for every later PR
at the merge; the first `ci.yml` and `phase-verify.yml` runs on `main` must be
green, and the Windows `test` job must finish under 20 minutes there.

Settings — ladder (`roadmodel ladder --category coding --complexity medium`):

|               |          | Cost                 | Balanced             | Quality            |
| ------------- | -------- | -------------------- | -------------------- | ------------------ |
| **Pick**      | Model    | **Gemini 3.8 Flash** | **GPT-6.1 Sol**      | **Gemini 4 Argon** |
|               | Platform | Antigravity          | Codex                | Antigravity        |
|               | Level    | Medium               | High                 | High               |
|               | AA       | 39.8                 | 50.2                 | 52.6               |
|               | Price    | $1.90/1M             | $2.86/1M             | $6.13/1M           |
| **Runner‑up** | Model    | **GPT-6.1 Sol**      | **Sonnet 5.5**       | **Opus 5.5**       |
|               | Platform | Codex                | Claude Code          | Claude Code        |
|               | Level    | Low                  | High                 | High               |
|               | AA       | 42.1                 | 46.8                 | 53.6               |
|               | Price    | $2.35/1M             | $3.40/1M             | $6.76/1M           |
| **Backup**    | Model    | **Sonnet 5.5**       | **Gemini 3.8 Flash** | **GPT-6.1 Sol**    |
|               | Platform | Claude Code          | Antigravity          | Codex              |
|               | Level    | Medium               | High                 | High               |
|               | AA       | 40.8                 | 40.9                 | 50.2               |
|               | Price    | $3.18/1M             | $2.98/1M             | $2.86/1M           |

Ranked for coding, medium complexity. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level.

> Ran 2026-11-03: Quality Pick — Gemini 4 Argon · High.

**Conversation:** New

**Model rationale:** Step 1 is coding with an agentic secondary category — a
dependency, one workflow line, and whatever a parallel run exposes — at Medium
complexity, not novel: Decision 2's probe already ran the whole suite in
parallel. On the step alone, the Balanced Pick fits best: GPT-6.1 Sol on Codex
at Intelligence High is ample for a small, well-bounded change whose proof is
one CI run. The Cost Pick, Gemini 3.8 Flash at Medium, saves money and would
serve if the run stays clean, but it has less margin if a test turns out to
depend on order. The Quality Pick, Gemini 4 Argon at High, buys depth that this
step does not need. The conversation is new, per phase-boundary hygiene.

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
       feature/phase07-step1-test-budget`
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
       Phase 7 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 7`
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

    THIS STEP changes a workflow, which is a security-relevant diff
    (the project roadmap's gate rule 5). `ci.yml` keeps its SHA-pinned
    actions and its permissions, and gains no secret. `pytest-xdist`
    and `execnet` are dev-group only, pass `pip-audit --strict` over
    the regenerated `uv.lock`, and are checked for licence and for
    typo-squatting by name. The socket guard
    (`--allow-hosts=127.0.0.1,::1`) and the working-directory guard
    must hold inside every worker: a test proves a worker refuses a
    non-loopback socket.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 7 (Depth). Step 1: the test
    budget.

    Current state (as of Phase 6):

    - `.github/workflows/ci.yml`'s `test` job (`ubuntu-latest`,
      `windows-latest`) has `timeout-minutes: 40` and runs `uv run
      pytest --cov=weatherbot.engine --cov=weatherbot.services.policy
      --cov=weatherbot.services.ai.context
      --cov=weatherbot.services.ai.validate --cov-branch
      --cov-report=term-missing:skip-covered --cov-fail-under=90`,
      then three `uv run coverage report --include=...` steps over
      `COVERAGE_FILE` in the runner's temporary directory.
    - Measured: the Windows job took 35m17s on PR #88 (Ubuntu 20m59s),
      and about 21 to 36 minutes across Phase 6. Decision 2's probe,
      with `uv run --no-sync --with pytest-xdist`, passed all 3,800
      tests with no change, in 4m09s at `-n 6` and 8m42s at `-n 4`
      with CI's coverage flags, on a 24-thread machine.
    - Phase 3's check 5 reads the job for its `COVERAGE_FILE` under
      `runner.temp`, `--cov=weatherbot.engine`, `--cov-branch`, and
      `--cov-fail-under=90`; no check reads `-n`. Phase 1's check 17
      and Phase 4's check 25 read `addopts`. Six subprocess tests
      carry `timeout=30`, and the `--fast` verifiers take 2.8 to 6.9
      seconds here, so CPU contention on a 4-vCPU runner is the risk
      to watch.
    - `tests/conftest.py` holds the socket guard's environment and
      clears `ANTHROPIC_*`; `pyproject.toml`'s `addopts` holds
      `--allow-hosts`, `--strict-markers`, `--strict-config`, and the
      marker filter, and `filterwarnings = ["error"]`.
    - Issue #82 lists the options, and this step takes neither the
      Windows subset nor another raised bound.

    Files to read (every file before drafting):

    - docs/roadmap/phase07-roadmap.md (Decisions 2 and 19, and this
      step).
    - .github/workflows/ci.yml and pyproject.toml.
    - tests/conftest.py and tests/test_architecture.py.
    - scripts/verify_phase03.py's check 5 and
      scripts/verify_phase06.py's check 44, with their mutation cases
      in tests/test_phase03_verification.py and
      tests/test_phase06_verification.py.
    - README.md's `## Status`.
  </context>

  <goal>
    Add `pytest-xdist` to the dev group, run the `test` job with `-n
    auto`, keep every coverage floor, and move README's Status to
    Phase 7 with Phase 6's check 44 reading its tag.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `uv add --group dev pytest-xdist`, and confirm `uv.lock`'s diff
      adds only `pytest-xdist` and `execnet`. Do not add `-n` to
      `addopts`: a bare `pytest` stays serial, so the verifiers'
      `--py` runs and a developer's filtered run are unchanged.
    </requirement>

    <requirement>
      In `ci.yml`'s `test` job, add `-n auto` to the pytest line,
      keeping every existing token that Phase 3's check 5 and Phase 6
      read, and replace the job's comment with the new measured
      durations. Keep `timeout-minutes: 40`: the bound stays as a
      ceiling, and the headroom is the point. `pytest-cov` combines
      the workers' data into `COVERAGE_FILE`, so the three `coverage
      report` steps read what they read before (Decision 2's probe).
    </requirement>

    <requirement>
      Run the suite with `-n auto` locally and on both CI runners. A
      test that fails only in parallel is fixed in the test (a shared
      temporary path, an order dependence, an exclusive resource), or
      grouped with `pytest.mark.xdist_group` and `--dist=loadgroup` if
      it truly needs exclusivity, such as a timing budget; no test is
      skipped or deleted to pass, and any test changed is named in the
      PR body.
    </requirement>

    <requirement>
      Add a test in `tests/test_ci_budget.py` that asserts the job's
      pytest line holds `-n auto` and the coverage flags and that
      `pyproject.toml`'s `addopts` does not hold `-n`, and a test that
      fails if a worker process can open a non-loopback socket.
    </requirement>

    <requirement>
      `README.md`'s `## Status` says Phase 7 (depth) is in progress.
      In the same PR, convert Phase 6's check 44 to read `README.md`
      at `v2.0.0-phase-6` through `tagged("README.md",
      tag=PHASE_6_TAG)`, as Phase 6 Step 1 did for Phase 5's check 47.
      `tests/test_phase06_verification.py` has no mutation case for
      check 44 yet, so add the pair
      `tests/test_phase05_verification.py` holds for check 47: an edit
      to the live `## Status` fails nothing, and an edit to the tagged
      text fails exactly `44`. `verify_phase06.py`'s counts stay 51
      and 28.
    </requirement>

    <requirement>
      `CONTRIBUTING.md` says the CI job runs in parallel, that `pytest
      -n auto` is the fast local run, and that a serial run stays the
      default. `CHANGELOG.md` opens its Phase 7 group under its one
      `## [Unreleased]` heading (Phase 1's check 4). The PR body
      records the before and after durations of both runners and
      closes issue #82.
    </requirement>

    <requirement>
      Filepath comment: every new Python, TypeScript, YAML, or
      Markdown file gets its repository-relative path as its first
      line where the file type accepts comments, matching the sibling
      files.
    </requirement>
  </requirements>
</task>
```

### Step 1 acceptance criteria

- `uv.lock` adds only `pytest-xdist` and `execnet`, both dev-only; `addopts` has
  no `-n`; a bare `uv run pytest` still passes serially.
- `ci.yml`'s `test` job runs with `-n auto`; every coverage floor still applies,
  and the three per-file `coverage report` steps pass and print the same files.
- The Windows `test` job finishes under 20 minutes on the PR and on `main`.
- No test was skipped or deleted; every test changed is named in the PR body.
- `tests/test_ci_budget.py` passes; a worker cannot open a non-loopback socket.
- Phase 6's check 44 reads `v2.0.0-phase-6`; `verify_phase01`–`06 --fast` pass,
  with their counts unchanged.
- **Deployed & verified:** the first `ci.yml` and `phase-verify.yml` runs on
  `main` after the merge are green, with the Windows job's duration recorded in
  the PR body and issue #82 closed.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean (`pip-audit --strict` over the new lock) — and the
  workflow diff grants no new permission, secret, or unpinned action.

---

## Step 2 — Locations ✅

**Status:** Complete — PR #91 (2026-11-04)

> **Goal:** Let the operator watch their own place, and find any place by name.
> Issue #87: `NwsCoverage.county_zone` becomes optional and `cwa` takes a digit,
> `parse_point` accepts an answer with no county, `fetch_alerts` skips the
> county query, the empty-string column mapping keeps `nws_coverage_whole` true,
> and `POST /api/locations` logs the source error's text at WARNING and returns
> it in its 502. Issue #71: `sources/nominatim.py` gains `search`, `q` is
> redacted like a coordinate, `LocationService.search` caches by the text's
> SHA-256, `POST /api/locations/search` answers on submit under a 2-second
> cooldown, and `weatherbot locations add NAME --place TEXT [--pick N]` joins
> `--lat`/`--lon`. `POST /api/locations/remove` and
> `frontend/src/settings/LocationManager.tsx` make the page a real
> multi-location manager, with candidates to choose from, coordinates behind a
> disclosure, and a confirmed remove. The Nassau profile is proved through the
> breakpoint path, the register gains forward search with a recording, and the
> operator's own location is added on their installed copy. Closes issues #87
> and #71.

**Branch:** `feature/phase07-step2-locations`

**Deploys:** the operator's machine → with the operator's yes, and away from the
hourly fallback at HH:25, `\Weatherbot\serve` is stopped (`schtasks /End`), the
frontend is rebuilt, the installed copy is reinstalled from the merged `main`
(`uv tool install --reinstall --from <checkout> weatherbot`), and the task is
started again (`/Run`); there is no migration,
`http://127.0.0.1:8765/api/health` must answer with the new `ui.index_sha256`,
and the operator adds their own location from the page. GitHub Actions → the
first `ci.yml` and `phase-verify.yml` runs on `main` must be green.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.86/1M           | $6.13/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.72/1M           | $6.76/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | XHigh              | XHigh              |
|               | AA       | ≈45.2              | 51                 | 52.4               |
|               | Price    | $2.31/1M           | $4.00/1M           | $17.73/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels.

> Ran 2026-11-04: Balanced Pick or Quality Runner-up — Gemini 4 Argon · High.

**Conversation:** New

**Model rationale:** Step 2 is coding with a knowledge secondary category — a
source, a domain model, a column mapping that must not disturb a CHECK, two
routes, a CLI change, a page, a recording, and an on-machine deployment — at
High complexity, not novel: Decisions 3 and 4 fix each mechanism from a probe or
a published policy. On the step alone, the Quality Pick fits best: Opus 5.5 on
Claude Code at Effort XHigh (it always thinks, so there is no Thinking dial)
gives the closest reading of how a typed address or a coordinate could escape
through a URL, a log line, or a provenance, and this is the first step that
handles the operator's real place. The Balanced Pick, Gemini 4 Argon at High,
would deliver the features at less cost and is a sound choice with Decision 4's
rules written down; the Cost Pick, GPT-6.1 Sol at High, trades away some of that
audit. The conversation is new, per phase-boundary hygiene.

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
       feature/phase07-step2-locations`
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
       Phase 7 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 7`
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

    THIS STEP sends the operator's typed place to Nominatim, the
    project's first free-text outbound query. The text is sent only on
    an explicit submit, never per keystroke (a test counts requests);
    it travels in a same-origin JSON body, never a URL of ours; `q` is
    redacted in `COORDINATE_PARAMETERS` and `_COORDINATE_QUERY`; no
    record above DEBUG, no error message, and no answer echoes it; it
    is cached in memory only, under its SHA-256, and never reaches the
    database. A candidate's names and coordinates reach only the
    operator's own page, and are `repr=False`. The location's name is
    typed, never taken from a candidate, because it leaves the machine
    in phone titles and AI requests. Removing a location removes the
    raw rows that hold its point and its address. `locations add
    --place` prints names, never coordinates, so `locations list`
    stays the only printing command. Search and remove are same-origin
    JSON writes; a cross-site attempt is refused, with a test each.
    Recordings use the two public landmarks' places only; the marine
    answer is built in test code from a recorded answer, because the
    personal-data check accepts no other request coordinate. The agent
    never reads, prints, or quotes the operator's point or place: the
    operator runs the issue's recipe in their own terminal and adds
    their own location in their own browser, and the agent reads only
    `/api/health` and the count of locations.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 7 (Depth). Step 2: locations.

    Current state (as of Phase 6, post-Phase-7 Step 1):

    - The operator's v2 copy has only the public Miami-Dade landmark:
      adding their own place answered 502 (issue #87). Decision 3
      gives the probed cause; only the operator's run can confirm
      their field.
    - `parse_point` uses `fields.text` for `county` and `_zone_of`;
      `fields.optional_text` still raises on an absent key,
      `fields.has` asks, and `nws.OPTIONAL_ALERT_FIELDS` is the
      pattern for a field a product may omit. A marine answer's
      `county` and `fireWeatherZone` keys are absent, not null.
      `NwsCoverage` is in `models/location.py`; readers of
      `county_zone`: `sources/nws.py`'s `fetch_alerts`,
      `services/locations.py`'s `add`, `engine/official.py`,
      `cli/locations.py`, `cli/snapshots.py`, `cli/documents.py`,
      `web/routes/alerts.py`, `web/schemas.py`, and
      `frontend/src/pages/Settings.tsx` and `Alerts.tsx`.
    - `repositories.py`'s `_location_row` and `_location` map the row;
      `tables.py`'s `nws_coverage_whole` CHECK stays as it is.
    - `sources/nominatim.py` has `reverse_url`, `parse_reverse`,
      `reverse_geocode`, and `FIELDS_READ`; the register's section is
      "OpenStreetMap: basemap and geocoding", and `tests/contract/`
      parses its field lists.
    - `scripts/record_fixtures.py` records the register's sources;
      `tests/fixtures/recorded/geocode-nominatim/` holds the reverse
      answers. `scripts/public_landmarks.toml` spells the landmarks
      (`Parliament Square`, `Miami-Dade County Hall`). A Nominatim
      `/search` for `Nassau, Bahamas` answered one candidate on
      2026-11-03 with `address`, `addresstype`, `boundingbox`,
      `category`, `display_name`, `importance`, `lat`, `licence`,
      `lon`, `name`, `osm_id`, `osm_type`, `place_id`, `place_rank`,
      and `type`; a nonsense query answered `[]`.
    - Sync write routes in `web/routes/actions.py` run
      `asyncio.run(...)` in the thread pool and hold their cooldowns
      in `WebState._actions`. `hub.record_location_change` publishes a
      `location` event. Location names go in a query or a JSON body,
      never a path segment.
    - Frontend: `Settings.tsx` holds the add form and the list;
      generated types are in `src/api/schema.d.ts`; Radix
      `AlertDialog` is the confirmation pattern
      (`AiSettingsSection.tsx`). `tests/cli/cli_support.py` asserts
      test data directories are in any custom `environ`.

    Files to read (every file before drafting):

    - docs/roadmap/phase07-roadmap.md (Decisions 3, 4, and 19, and
      this step).
    - src/weatherbot/sources/nws.py, nominatim.py, http.py, and
      fields.py.
    - src/weatherbot/models/location.py and engine/official.py.
    - src/weatherbot/services/locations.py,
      services/persistence/repositories.py, tables.py, and
      raw_cache.py.
    - src/weatherbot/web/routes/actions.py, routes/locations.py,
      schemas.py, and app.py.
    - src/weatherbot/cli/locations.py.
    - frontend/src/pages/Settings.tsx and Settings.test.tsx,
      src/ai/AiSettingsSection.tsx, and src/test/fixtures/.
    - docs/DATA_SOURCES.md ("OpenStreetMap: basemap and geocoding",
      "Points"), scripts/record_fixtures.py,
      scripts/export_api_fixtures.py, and tests/contract/.
    - GitHub issues #87 and #71.
  </context>

  <goal>
    Fix #87 from its cause, add forward search and `--place`, add
    remove and a multi-location page, prove Nassau, and let the
    operator add their own place.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Kickoff: before writing code, ask the operator (AskUserQuestion)
      to run the issue's recipe in their own terminal and tell you
      only the error's field name:
      `C:\Users\Admin\.local\bin\weatherbot.exe locations add "<name>"
      --lat <lat> --lon <lon>` prints the field-level message, which
      holds no coordinate. Never ask for the point or the place. If
      the field is one Decision 3 does not cover, widen the fix to it
      the same way and record it in the PR body.
    </requirement>

    <requirement>
      Issue #87, source and model. `NwsCoverage.county_zone` becomes
      `str | None` (pattern kept) and `cwa` becomes `^[A-Z0-9]{3}$`.
      `OPTIONAL_POINT_FIELDS` names `county`, `parse_point` reads it
      through `_zone_of` only when `fields.has` says it is there (a
      present-but-null value reads as absent too), and
      `tests/contract/test_nws_captures.py`'s deletion test gains the
      branch its alert sibling has, so the register's list stands.
      `fetch_alerts` builds the county request only when `county_zone`
      is set, so a marine-zone location asks the point and the
      forecast zone. `LocationService.add` refuses `polygon="county"`
      with no county, with a message that names no coordinate.
      `polygon="forecast"` works for a marine zone:
      `zones/forecast/AMZ630` answers 200 with `state: null` and
      `type: coastal` (probed 2026-11-03), and `parse_zone`'s
      `fields.text("state")` raises on a null, so it reads `state`
      through `fields.optional_text`, `NwsZone.state` becomes `str |
      None`, that model's `type` description gains `coastal`, the
      register's `nws-zones` list says so, and
      `tests/contract/test_nws_captures.py` gains the branch. Every
      reader prints a missing county or state as absent, not as
      `None`.

      Build the marine answer in test code from a recorded `/points`
      answer (`county` and `fireWeatherZone` deleted, `forecastZone`
      ending `AMZ630`, `cwa` `NH2` in a second case), and the marine
      zone's from a recorded zone answer (`state` null, `type`
      `coastal`); never record a water point, because the
      personal-data check accepts no coordinate but the landmarks'.
    </requirement>

    <requirement>
      Issue #87, storage. `_location_row` stores `""` in
      `nws_county_zone` for a covered location with no county, and
      `_location` reads `""` as `None`, in those two places only, with
      a comment on the `LocationRow` column saying why: the
      `nws_coverage_whole` CHECK cannot change without a table
      rebuild, and a rebuild cascades deletes. A test proves a
      no-county location round-trips and the CHECK still holds for an
      outside-coverage location. No revision.
    </requirement>

    <requirement>
      Issue #87, reporting. `POST /api/locations` logs `str(error)` at
      WARNING (it names the field, never the point; a test proves it
      through the logging filter) and puts it in the 502's detail, so
      the page says which field failed. The CLI's message does not
      change.
    </requirement>

    <requirement>
      Forward search, source. `nominatim.SEARCH_URL`,
      `search_url(query)` (`q` percent-encoded, `format=jsonv2`,
      `addressdetails=1`, `limit=5`), `parse_search(body, provenance)
      -> tuple[GeocodeCandidate, ...]` (`[]` is no result), and `async
      search(fetcher, query)`. `GeocodeCandidate` in `models/` holds
      `display_name`, `name`, `latitude`, `longitude` (all four
      `repr=False`, because a search's `display_name` can be a street
      address), `country_code`, `category`, `kind` (the answer's
      `type`), `osm_type`, `osm_id`, `licence`, and its provenance.
      `q` joins `COORDINATE_PARAMETERS` and `_COORDINATE_QUERY` in
      `sources/http.py` (the regex is hard-coded, so both must
      change). `scripts/check_personal_data.py`'s
      `request_coordinates()` does not learn `q`, whose value is text:
      R3 would read `Nassau` as a bad coordinate, so the contract test
      pins each recorded query to its landmark instead.
      `SEARCH_FIELDS_READ` is separate from `FIELDS_READ`, because
      `tests/contract/test_nws_captures.py` holds the section's first
      "Fields v2 uses" bullet to the reverse list; search gets its own
      bullet after it, and its own contract test.
    </requirement>

    <requirement>
      Forward search, service and route.
      `LocationService.search(query)` strips and bounds the text (3 to
      200 characters, printable), looks in `SearchCache`, a bounded
      in-memory map (64 entries, 24 hours, keyed by the SHA-256 of the
      casefolded text) that `WebState` holds, because
      `web/routes/actions.py` builds a `LocationService` per request,
      and otherwise fetches once and keeps the answer there. A
      `--place` run is one request and needs no cache. Nothing about a
      search reaches the database: `save_fetch` is not called for it.
      `POST /api/locations/search` takes `{"query": ...}`, answers
      candidates with their coordinates, `429` with `Retry-After`
      within 2 seconds of the last search (the cooldown lives in
      `WebState._actions`; the fetcher's pacing does not span runs),
      and `502` with the source's text on a failure. It is a sync
      route, like `create_location`.
    </requirement>

    <requirement>
      CLI. `weatherbot locations add NAME` takes exactly one of
      `--lat`/`--lon` or `--place TEXT` (exit 2 otherwise), plus
      `--pick N` (1-based) and `--polygon`. One candidate is added;
      several print as a numbered list of `display_name`s, with no
      coordinate, and exit 2 asking for `--pick`; none exits 1 saying
      so. The OpenStreetMap attribution prints with the result.
    </requirement>

    <requirement>
      Remove. `POST /api/locations/remove` takes `{"location": ...}`,
      calls `LocationService.remove`, answers 404 for an unknown name
      without echoing it, and publishes the `location` event
      invalidating `locations`, `assessments`, `map`, `alerts`, and
      `timeline`. It uses `POST` with a JSON body because the write
      guard requires one. `LocationService` gains `paths`, from both
      callers, and `remove` takes `cycle.lock`, because `_save_alerts`
      raises on a snapshot whose alerts name a location no longer
      stored, so a remove during a cycle would fail that cycle; a lock
      held past `[monitor] cycle_lock_wait_seconds` answers 409 on the
      page and exits 1 at the CLI. In the same transaction it deletes
      the `raw_responses` rows `_key` named for the location
      (`product_key` ending `<name>`, matched as a literal suffix),
      whose bodies hold its point and its address, and any
      `response_bodies` nothing else names, because the dialog says
      its history goes with it and those rows would otherwise stay for
      good as the newest of their own keys.
    </requirement>

    <requirement>
      Page. `frontend/src/settings/LocationManager.tsx`, used by
      `Settings.tsx`: a place box and a Search button (submit only,
      disabled for 2 seconds after a search, and never on change), the
      candidates as a radio list of display names with "Search by
      OpenStreetMap Nominatim, © OpenStreetMap contributors" beneath
      them, a required name the operator types, empty at first and
      never filled from a candidate, with "This label appears in phone
      notifications, AI requests, logs, and reports. Use something
      like Home, not an address." beneath it, the polygon choice
      (forecast zone, county when one exists), and "Add location";
      "Enter coordinates instead" behind a disclosure holds the
      existing fields; each stored location shows its coverage in
      words ("NWS MFL, zones ...", "NWS marine zone, no county",
      "Outside NWS coverage: NHC breakpoints") and a Remove control
      behind a Radix `AlertDialog` that says its history goes with it.
      The add form moves here from `Settings.tsx`, whose existing
      tests move with it.
    </requirement>

    <requirement>
      The Nassau profile. A test adds Nassau with `--place "Nassau,
      Bahamas"` over the recorded search and reverse answers and
      `/points`'s `InvalidPoint`, and asserts `nws` is `None` and
      `country_code` is `BS`, and that the location as added, assessed
      against replayed Dorian advisory 26, reads level 5 by
      `hurricane_warning` from an NHC watch-warning segment (code
      `HWR`). A replay snapshot holds no breakpoint catalogue, so its
      evidence names the segment and never its breakpoints; the live
      path names them, which `tests/engine/` already proves. The
      recorded candidate is the city's node, not the landmark, so the
      test routes `/points` and `/reverse` for its exact coordinates,
      read from the recording at run time, because
      `tests/cli/cli_support.py`'s `_any_point` answers any other
      point with Miami-Dade's. `README.md` documents the two-line
      recipe, naming Nassau, since it is a public place.
    </requirement>

    <requirement>
      Register and recording. Add the forward-search endpoint, its
      fields, and the marine `/points` shape (without a coordinate) to
      `docs/DATA_SOURCES.md`, dated, with the policy lines Decision 4
      quotes. `record_nominatim` in `scripts/record_fixtures.py` also
      records `search-nassau.json` (`Nassau, Bahamas`),
      `search-miami.json` (`Miami, Florida`), and `search-none.json`,
      and `tests/scripts/test_record_fixtures.py`'s fake server learns
      `/search`. Run it with `record --source geocode-nominatim`:
      `tests/sources/source_support.py` and `tests/cli/cli_support.py`
      read the source's newest directory, which must hold the
      `reverse-*.json` files too, so the reverse captures re-record
      with it and the `2026-10-12` directory goes in the same PR. In
      `tests/contract/test_nws_captures.py`, `GEOCODE_CAPTURES` and
      the `DOCUMENT_RULES` deletions filter on the `reverse-` prefix,
      and search gets its own rules. A `live` test searches for one
      landmark's place. `scripts/export_api_fixtures.py`,
      `docs/api/openapi.json`, and `scripts/export_schemas.py`
      regenerate (`docs/schema/locations.schema.json` embeds
      `NwsCoverage`); `frontend/src/api/schema.d.ts` follows; and
      `tests/models/test_conventions.py`'s `SAMPLES` gains
      `GeocodeCandidate`.
    </requirement>

    <requirement>
      Tests (basenames checked against `git ls-files`):
      `tests/sources/test_nws_no_county.py`,
      `tests/sources/test_nominatim_search.py`,
      `tests/services/test_location_search.py` (a repeat within the
      day asks nothing, and no search adds a row to any table),
      `tests/services/test_location_no_county.py`
      (`polygon="forecast"` on a marine zone among them),
      `tests/services/test_location_remove.py` (the `<name>` rows and
      their bodies go, a body another row names stays, and a cycle in
      progress finishes first), `tests/web/test_location_writes.py`
      (search, cooldown, remove, a busy lock's 409, cross-site
      refusals, the 502's detail), `tests/cli/test_locations_place.py`
      (one, several, none, `--pick`, both forms refused),
      `tests/cli/test_location_nassau.py`, a privacy test proving the
      search text is in no log record at INFO and no error message,
      `frontend/src/settings/LocationManager.test.tsx` (no request
      while typing; candidates; the name starts empty and blocks the
      add until typed; add; remove behind its dialog; the coordinates
      disclosure), and `frontend/e2e/locations.spec.ts` (search,
      choose, add, and remove on the demonstration server, with
      `scripts/serve_demo.py` replaying the recorded `/search` answer
      and, for its candidate's exact coordinates read from the
      recording at run time, `/points`'s `InvalidPoint` and the
      recorded Nassau `/reverse`, because the test routes' fallback
      answers any other point with Miami-Dade's; Nominatim is never
      reached).
    </requirement>

    <requirement>
      `README.md`'s Commands and dashboard sections,
      `CONTRIBUTING.md`, and `CHANGELOG.md`'s Phase 7 group describe
      the change. The PR body lists any earlier check it converted
      (Decision 19) and closes #87 and #71, whose close the deployed
      check earns.
    </requirement>

    <requirement>
      Deploy (Stage 4), after the operator's yes to the exact actions:
      stop the task, rebuild, reinstall, and run it again, away from
      HH:25; read `/api/health`; then ask the operator to add their
      own location from `/settings` and confirm it answered 201. They
      may also remove the temporary Miami-Dade landmark. Never read
      the location back; count the `locations` array's length only.
    </requirement>

    <requirement>
      Filepath comment: every new Python, TypeScript, YAML, or
      Markdown file gets its repository-relative path as its first
      line where the file type accepts comments, matching the sibling
      files.
    </requirement>
  </requirements>
</task>
```

### Step 2 acceptance criteria

- A `/points` answer with no `county` key and one with `cwa: "NH2"` parse; such
  a location is stored with the CHECK intact, round-trips, and reads alerts from
  its point and forecast zone with no county request.
- `POST /api/locations` logs and returns the source error's field-level text,
  with no coordinate.
- `POST /api/locations/search` answers candidates; a second search within 2
  seconds answers 429; a repeated search reaches the cache, not Nominatim; a
  test counts one request per submit and none while typing; and no search writes
  a row.
- `weatherbot locations add NAME --place TEXT` handles one, several (`--pick`),
  and no candidates, prints no coordinate, and refuses both forms together.
- The page adds by place and by coordinates, with a name the operator types, and
  removes behind a confirmation; a remove waits for a running cycle and takes
  the location's raw rows with it; the attribution shows beside the results.
- Nassau adds through `--place` as a location outside NWS coverage, and replayed
  Dorian advisory 26 reads level 5 from an NHC watch-warning segment.
- The register states forward search, its fields, its policy, and the marine
  shape; the recordings and the contract tests pass; `--check` exporters pass.
- **Deployed & verified:** `GET http://127.0.0.1:8765/api/health` answers from
  the reinstalled copy with the new `ui.index_sha256`; the operator's own
  location was added from the page and answered 201 (the operator's
  confirmation, with no value read); and `doctor`'s `web`, `migrations`, and
  `locations` checks pass.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — and the search path handles the operator's text per
  the project roadmap's "Security & privacy strategy": no log, URL of ours, or
  error holds it, a request leaves only on submit, and both new writes refuse a
  cross-site caller.

---

## Step 3 — The phone ✅

**Status:** Complete — PR #92 (2026-11-04)

> **Goal:** Reach the operator's phone. `src/weatherbot/services/ntfy.py` holds
> `NtfyChannel`, a `Channel` that posts JSON to the server's root with the topic
> and optional token read from `WEATHERBOT_NTFY_TOPIC` and
> `WEATHERBOT_NTFY_TOKEN`, and `ntfy_channel(settings, environ)`, which the
> runtime's new `make_ntfy` seam calls; `[notifications]` gains `ntfy` and
> `ntfy_server`; `Context.channels` and `serve` add the channel only while it is
> on; `LocationPreferences` joins `Location` through revision 0009, with `PUT
> /api/locations/preferences` and `_deliver_one` choosing channels; `doctor`
> gains its `ntfy` check, `GET /api/notifications/channels` the page's view, and
> the log filters the topic and token; quiet hours are proved through the real
> channel; `docs/NOTIFICATIONS.md` says what leaves the machine; and a real
> `notify test` buzzes the operator's phone.

**Branch:** `feature/phase07-step3-ntfy`

**Deploys:** the operator's machine → after the kickoff's provisioning and the
operator's yes, and away from HH:25, `\Weatherbot\serve` is stopped, the copy is
rebuilt and reinstalled from the merged `main`, and the task is started again,
so it sees the new environment variables; revision 0009 runs at its start after
the backup, `/api/health` must read `database.revision` `0009` at head, the
operator sets `[notifications] ntfy = true`, and the installed copy's `notify
test` must read `ntfy: delivered` with the phone buzzing. GitHub Actions → the
first `ci.yml` and `phase-verify.yml` runs on `main` must be green.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.86/1M           | $6.13/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.72/1M           | $6.76/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | XHigh              | XHigh              |
|               | AA       | ≈45.2              | 51                 | 52.4               |
|               | Price    | $2.31/1M           | $4.00/1M           | $17.73/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels.

> Ran 2026-11-04: Balanced Pick — Gemini 4 Argon · High.

**Conversation:** New

**Model rationale:** Step 3 is coding with an agentic secondary category — a
second secret, a third-party channel, a migration, a delivery filter, logging
redaction, a `doctor` check, a document, and a deployment whose proof is a phone
in the operator's hand — at High complexity, not novel: Decisions 5 and 6 fix
the mechanism. On the step alone, the Quality Pick fits best: Opus 5.5 on Claude
Code at Effort XHigh (it always thinks, so there is no Thinking dial) gives the
closest audit of every path a topic could take into a log, a row, or an answer,
and of the delivery filter's edge cases. The Balanced Pick, Gemini 4 Argon at
High, is a sound choice on a channel protocol this well worn; the Cost Pick,
GPT-6.1 Sol at High, trades away some of that review of a secret. The
conversation is new, per phase-boundary hygiene.

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
       feature/phase07-step3-ntfy`
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
       Phase 7 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 7`
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

    THIS STEP adds a second secret. `WEATHERBOT_NTFY_TOPIC` and
    `WEATHERBOT_NTFY_TOKEN` are read from the runtime's environment
    and held only by the channel object; they are not `Settings`
    fields, not in `ENVIRONMENT_OVERRIDES`, not in `config show`, not
    in an API answer, not in a row, and not in a `Delivery.detail`.
    The channel's `repr` shows neither. The topic travels only in the
    JSON body, the token only in the `Authorization` header.
    `redact_secrets` learns the token's `tk_` shape and, from
    `configure_logging`, the topic's and token's values, so a
    traceback holding the body is clean; a test puts each in a record
    and a traceback at DEBUG. `ntfy_server` must be `https` unless its
    host is loopback, redirects are refused, and TLS verification
    stays on. Tests build a fake token at run time, and
    `tests/conftest.py` already deletes every `WEATHERBOT_*` variable.
    A notification body carries no coordinate: a test asserts
    `engine/changes.py`'s sentences and `policy.py`'s lines hold no
    distance. No value ever transits this chat: the operator sets both
    in the Windows Environment Variables dialog, never on a command
    line, where shell history keeps it, and the agent verifies by
    presence and by a real delivery.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 7 (Depth). Step 3: the phone.

    Current state (as of Phase 6, post-Phase-7 Step 2):

    - `services/notifications.py`: `Channel` (`name`, `interrupts`,
      `async deliver(notification) -> Delivery`), `CHANNEL_NAMES`,
      `ChannelName`, `DELIVERY_RESULTS`, and
      `_deliver_one(notification, decisions, *, include_toast=True)`,
      which filters on `interrupts`. `services/toast.py` holds the
      pattern: `ToastChannel`, `NullChannel`,
      `toast_channel(settings)`, `delivery_failed`, and `TOAST_OFF`.
    - `cli/runtime.py`: `Runtime.make_toast`, `Context.channels`
      (log + toast); `cli/serve.py` line 123 adds `BrowserChannel`;
      `web/app.py`'s `WebState` builds default channels when none
      are given.
    - `notify test` stores a `test` notification and exits 1 when
      `delivery_failed` reads a result, which treats `disabled` as a
      failure; `TEST_BODY` says "toasts work", which a phone must not
      read.
    - ntfy (read 2026-11-03): `POST https://ntfy.sh/` with JSON fields
      `topic` (required), `message`, `title`, `tags`, `priority` (1 to
      5), `click`, and `actions`; `Authorization: Bearer <token>`;
      4,096 bytes a message, title 1 KB, tags 512 bytes (past either,
      HTTP 400); 60 requests a burst, one more per 5 seconds; 250
      messages a day on ntfy.sh; a 12-hour cache; messages forwarded
      to Firebase unless `Firebase: no`, without which an Android
      phone not on instant delivery may wait up to 15 minutes. The
      phone app vibrates and sounds at priority 3 and above, and pops
      over at 4 and 5. Confirm each on the live docs before relying on
      it.
    - `services/logs.py`: `redact_secrets`, `SecretFilter`, and
      `configure_logging`; `_HEADER_VALUE` already covers
      `Authorization`.
    - `services/config.py`: `NotificationSettings`,
      `ENVIRONMENT_OVERRIDES`, and `setting_origins`, which needs an
      override entry for every key.
    - `repositories.py`: `_location_row`, `_location`,
      `LocationRepository`; `migrations/versions/` ends at 0008;
      `FROZEN` pins each merged revision; revision 0003 is the plain
      `add_column` precedent.
    - `LocationManager.tsx` (Step 2) lists locations; `Settings.tsx`
      has the notifications section and the test button.

    Files to read (every file before drafting):

    - docs/roadmap/phase07-roadmap.md (Decisions 1, 5, 6, and 19, and
      this step).
    - src/weatherbot/services/notifications.py, toast.py, policy.py,
      logs.py, config.py, and doctor.py.
    - src/weatherbot/cli/runtime.py, serve.py, check.py, and
      notify.py.
    - src/weatherbot/engine/changes.py (what a body can say).
    - src/weatherbot/web/routes/notifications.py, routes/locations.py,
      and schemas.py.
    - src/weatherbot/services/persistence/repositories.py, tables.py,
      and migrations/versions/0003_assessments.py.
    - tests/conftest.py, tests/services/test_tables.py, and
      tests/services/test_database.py.
    - frontend/src/settings/LocationManager.tsx and
      src/pages/Settings.tsx.
  </context>

  <goal>
    Add the ntfy channel and its secrets, per-location preferences,
    the `doctor` check, and the channel view; prove quiet hours
    through it; document what leaves the machine; and buzz the
    operator's phone.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Kickoff, before code depends on it (AskUserQuestion): tell the
      operator what this needs and let them choose ntfy.sh with a long
      random topic or a server of their own. Hand them, for their own
      terminal, `python -c "import secrets; print('weatherbot-' +
      secrets.token_urlsafe(18))"`, and have them set
      `WEATHERBOT_NTFY_TOPIC` (and `WEATHERBOT_NTFY_TOKEN`, if their
      server needs one) in the Windows Environment Variables dialog
      and subscribe on their phone. Never ask for either value. Verify
      presence by `[Environment]::GetEnvironmentVariable` piped to a
      length check, printing only whether it is set.
    </requirement>

    <requirement>
      `services/ntfy.py`. `NtfyChannel(server, topic, token, *,
      client=None)`: `name` `ntfy`, `interrupts` true, and `async
      deliver` posting JSON to the server's root through an
      `httpx.AsyncClient` with the project's User-Agent,
      `follow_redirects=False`, TLS verification on, and a 5-second
      timeout, retrying once after 3 seconds on a timeout, a
      connection error, a 429 (honouring `Retry-After` up to 5
      seconds), or a 5xx, so a delivery spends at most 15 seconds.
      Payload per Decision 5: `title`; `message` from the body lines
      and the disclaimer's `NOTICE`, cut to 4,000 bytes at a character
      boundary; `priority` from `NotificationKind`, level, and
      `escalation`; `tags` from a fixed table (`warning`,
      `rotating_light`, `white_check_mark`, `test_tube`). A 2xx is
      `delivered`; anything else is `failed` with a `detail` naming
      the status or the error's class only, never a body. `__repr__`
      names the server's host only.
    </requirement>

    <requirement>
      `ntfy_channel(settings, environ) -> Channel | None`: `None` when
      `[notifications] ntfy` is off; when it is on with no topic, a
      channel whose `deliver` answers `unavailable` with
      `WEATHERBOT_NTFY_TOPIC is not set`. `Runtime.make_ntfy` is the
      seam, as `make_toast` is; `Context.channels` becomes the log,
      the toast, and the ntfy channel when there is one;
      `cli/serve.py`'s tuple is the log, the toast, `BrowserChannel`,
      and ntfy, which stays last, because `MonitorService._locked`
      awaits every delivery under the cycle lock and no other channel
      should wait on its retries. `CHANNEL_NAMES` and `ChannelName`
      gain `ntfy`. `TEST_TITLE` and `TEST_BODY` stop naming toasts
      (`If you can read this, this channel works.`), and
      `delivery_failed` keeps its signature and its meaning, because
      it knows nothing of the channel: `notify test` applies it to the
      `toast` row and reads anything but `delivered` as a failure on
      the `ntfy` row (`d.channel` is there), so an unconfigured
      channel fails off Windows too.
    </requirement>

    <requirement>
      `NotificationSettings` gains `ntfy: bool = False` and
      `ntfy_server: str = "https://ntfy.sh"`, validated (`https`, or
      `http` on a loopback host; no path, query, or user info), with
      literal `WEATHERBOT_NOTIFICATIONS_NTFY` and
      `WEATHERBOT_NOTIFICATIONS_NTFY_SERVER` overrides. The module
      docstring's rule stands: the topic and token are not settings.
    </requirement>

    <requirement>
      Preferences. `LocationPreferences(toast: bool = True, browser:
      bool = True, phone: bool = True, phone_min_level: int = 2)`, a
      field of `Location` with that default. Revision
      `0009_location_preferences.py`: four `add_column`s on
      `locations` with server defaults, never a batch, with a
      downgrade by `drop_column`, pinned in `FROZEN`.
      `LocationRepository.set_preferences` and `PUT
      /api/locations/preferences` (`{"location", "preferences"}`),
      invalidating `locations`. `LocationResponse` gains
      `preferences`. The AI context does not: `services/ai/` reads no
      preference.
    </requirement>

    <requirement>
      Delivery. `DELIVERY_RESULTS`, `DeliveryResult`, and
      `web/schemas.py`'s literal gain `muted`. `_deliver_one` reads
      the location's preferences when the notification has a location,
      and for a channel it turns off stores a `muted` delivery with
      the detail `turned off for this location` (or `below this
      location's phone level`) without calling it. A notification
      below `phone_min_level` still goes to `ntfy` when the location's
      previous notification has a `delivered` `ntfy` row, because
      `policy.py` titles a drop with the level it drops to, so with
      the default of 2 an all-clear would otherwise never arrive.
      `latest_delivery` skips `muted` rows: `doctor` reads the newest
      row through `delivery_failed`, `GET /api/notifications/channels`
      shows it, and a location's choice is neither a channel failing
      nor a reason to hide one. `log` is never filtered. A
      notification with no location (`test`, `degraded`, `recovered`,
      `stale_monitor`) reaches every channel. `decide` is not touched,
      and `services/policy.py`'s diff is empty.
    </requirement>

    <requirement>
      `recovered`. `MonitorSchedule._toast_delivered` records whether
      any interrupting channel delivered the `degraded` alarm, not
      `d.channel == "toast"`, because `_check_degraded_alarms`
      otherwise sends `recovered` with `include_toast=False`, which
      drops ntfy too: a phone told of a failure must hear of the
      recovery. `tests/services/test_recovered_phone.py` degrades and
      recovers with the toast off and ntfy on.
    </requirement>

    <requirement>
      `doctor` gains `Check("ntfy", ...)`: `skip` while off; `fail`
      while on with no topic, or when the latest delivery failed,
      naming the runbook; `pass` with the latest result; presence
      only, never a request. `GET /api/notifications/channels` answers
      each channel's name, state (`on`, `off`, `unconfigured`), latest
      result, and time, with no server URL path, topic, or token. The
      fresh-temporary-directory `doctor --offline --json` proofs of
      Phases 2 to 6 still exit 0.
    </requirement>

    <requirement>
      Redaction. `redact_secrets` removes `tk_` tokens by shape
      (assembled so that no tracked byte holds one), and
      `configure_logging` registers the topic's and token's values
      with `SecretFilter` when set. A fake topic in a record and in a
      traceback is removed at every level.
    </requirement>

    <requirement>
      Page. `frontend/src/settings/NotificationChannels.tsx` shows
      each channel's state and latest result, the test button, and for
      ntfy what to set when unconfigured, with the variable names and
      never a value; `LocationManager.tsx` gains each location's
      toggles and phone level, saying that turning everything off
      leaves the log alone and that an all-clear always follows an
      alarm the phone received.
    </requirement>

    <requirement>
      `docs/NOTIFICATIONS.md`, with `## What leaves the machine` and
      `## Runbook` among its headings: what each channel is; how to
      choose a topic; what leaves the machine (the location name, the
      level, the sentences) and what ntfy.sh does with it (Decision 5,
      with the date read); priorities; preferences; quiet hours; the
      daily limit; and the runbook: a failed delivery, a rotated token
      (rotate at the server, set the new value, restart the task,
      `notify test`), and a leaked topic (choose a new one). The
      project roadmap's runbooks and health-signal table gain the row
      in this PR's Status commit.
    </requirement>

    <requirement>
      Tests: `tests/services/test_ntfy.py` (`respx`: the payload, the
      root URL, the Bearer header, no token, a body at the size bound,
      a multi-byte cut, 401, 429 then 200, 500 twice, a timeout, a
      redirect refused, `repr`),
      `tests/services/test_location_preferences.py` (round trip,
      `muted` rows, `log` untouched, a no-location kind, `doctor`
      passing and a real failure showing behind a muted row, and a
      drop from level 3 to 1 reaching the phone at the default level),
      `tests/services/test_recovered_phone.py`,
      `tests/services/test_quiet_hours_phone.py` (through
      `NotificationService` with a respx-backed `NtfyChannel` and
      Phase 3's level-2 scenario: a repeat inside quiet hours sends
      nothing, an escalation at the same instant reaches ntfy),
      `tests/services/test_doctor_ntfy.py`,
      `tests/cli/test_notify_phone.py` (`notify test` with the channel
      on, off, and unconfigured; `--json` holds no topic), additions
      to the logging tests, `tests/web/test_notification_channels.py`,
      `tests/live/test_ntfy_live.py` (a `live` test posting to a
      random throwaway topic on ntfy.sh, asserting the answer's `id`,
      `time`, and `topic`), and frontend tests. Revision 0009 adds
      columns only, so `tests/services/test_tables.py`'s table set
      does not change. `frontend/e2e/guard.ts` is unchanged, because
      the browser never talks to ntfy.
    </requirement>

    <requirement>
      `scripts/export_api_fixtures.py`, `docs/api/openapi.json`,
      `docs/schema/`, and `frontend/src/api/schema.d.ts` regenerate,
      and `tests/models/test_conventions.py`'s `SAMPLES` gains
      `LocationPreferences`. `README.md` and `CHANGELOG.md` describe
      the channel. The Phase 4 notification goldens and their digest
      are unchanged, and `git diff` shows no change under
      `tests/golden/`.
    </requirement>

    <requirement>
      Deploy (Stage 4), after the operator's yes to each exact action:
      reinstall as the Deploys line says, have the operator set
      `[notifications] ntfy = true`, restart the task, run the
      installed `notify test --json` and read only the deliveries'
      results, and ask the operator whether the phone buzzed.
    </requirement>

    <requirement>
      Filepath comment: every new Python, TypeScript, YAML, or
      Markdown file gets its repository-relative path as its first
      line where the file type accepts comments, matching the sibling
      files.
    </requirement>
  </requirements>
</task>
```

### Step 3 acceptance criteria

- `NtfyChannel` posts to the server's root with the topic in the body, the token
  in the header, the size bounds kept, and one retry; every failure is a
  `failed` delivery with a safe detail.
- With `[notifications] ntfy` off, `Context.channels` omits the channel and
  `notify test` exits 0 as before; on with no topic, it reads `unavailable` and
  `doctor` fails with the runbook.
- The topic and token appear in no log record at any level, row, API answer,
  document, `Delivery.detail`, or fixture.
- A location's preferences turn channels off with a `muted` delivery row that no
  channel check reads; an all-clear follows an alarm the phone received, and a
  `recovered` alarm follows a `degraded` one it received; the policy's source
  and every notification golden are byte-identical.
- Quiet hours hold a level-2 repeat and pass an escalation through the real
  channel, in a test.
- Revision 0009 upgrades and downgrades with no row lost; it is pinned in
  `FROZEN`.
- `docs/NOTIFICATIONS.md` states what leaves the machine, and the runbook covers
  a failed delivery and a rotated secret.
- **Deployed & verified:** `/api/health` reads revision `0009` at head from the
  reinstalled copy; the installed `notify test --json` reports `ntfy:
  delivered`, and the operator confirms the phone buzzed; `doctor`'s `ntfy`
  check passes.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — and the ntfy secrets are handled per the project
  roadmap's data classification: environment only, redacted from every log, and
  absent from every export.

---

## Step 4 — Settings and retention ✅

**Status:** Complete — PR #93 (2026-11-04)

> **Goal:** Let the page edit settings, and let history be kept or pruned on
> purpose. `src/weatherbot/services/settings_file.py` applies a list of changes
> to `weatherbot.toml` through `tomlkit`, atomically, with its comments kept,
> refusing a key off the allowlist, a key the environment sets, a result that
> fails validation, and a file that changed since it was read; `PUT
> /api/settings` exposes it, `MonitorSchedule` re-reads the policy's keys each
> cycle through a `live_settings` seam, and `frontend/src/settings/` gains the
> quiet-hours, cooldown, AI, and retention editors.
> `src/weatherbot/services/retention.py` plans and runs a prune under Decision
> 8's keep-list; `[retention] history_days` defaults to 0; `weatherbot prune
> [--dry-run] [--days N] [--cutoff INSTANT] [--vacuum] [--json]`, `GET
> /api/retention`, and `POST /api/retention/run` expose it; a daily worker in
> `serve` runs it, with a heartbeat as its health signal, and revision 0010
> indexes the foreign keys a delete has to check.

**Branch:** `feature/phase07-step4-settings-retention`

**Deploys:** nothing beyond merge — the operator's copy takes this step at Step
9, where revision 0010 runs at its start. The default keeps everything, so that
upgrade deletes nothing.

Settings — ladder (`roadmodel ladder --category coding --complexity high
--novel`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **Gemini 4 Argon** | **Opus 5.5**       | **Opus 5.5**       |
|               | Platform | Antigravity        | Claude Code        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 52.6               | 53.6               | 56                 |
|               | Price    | $6.13/1M           | $6.76/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **Opus 5.5**       | **Gemini 4 Argon** | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Antigravity        | Antigravity        |
|               | Level    | Medium             | Medium             | High               |
|               | AA       | 51.2               | ≈49.8              | 52.6               |
|               | Price    | $6.39/1M           | $2.37/1M           | $6.13/1M           |
| **Backup**    | Model    | **GPT-6 Astra**    | **GPT-6 Astra**    | **GPT-6 Astra**    |
|               | Platform | Codex              | Codex              | Codex              |
|               | Level    | Medium             | High               | XHigh              |
|               | AA       | 49.6               | 50.9               | 52.4               |
|               | Price    | $11.85/1M          | $13.01/1M          | $17.73/1M          |

Ranked for coding, high complexity, novel. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level. ≈
estimated from the model's measured levels.

> Ran 2026-11-04: Cost Pick / Quality Runner-up — Gemini 4 Argon · High.

**Conversation:** New

**Model rationale:** Step 4 is coding with a planning secondary category at High
complexity, and novel: the keep-list is an argument about what the policy and
the diff read, in the first code this project has that deletes a person's
history, and the settings write is the first write to a file the operator also
edits by hand. On the step alone, the Quality Pick fits best: Opus 5.5 on Claude
Code at Effort XHigh (it always thinks, so there is no Thinking dial) is the
strongest reasoner the ladder offers for a cascade-aware delete, and a mistake
here cannot be undone. The Balanced Pick, the same model at High, is the
economical alternative with a little less depth; the Cost Pick, Gemini 4 Argon
at High, trades away the closest audit of the cascades. The conversation is new,
per phase-boundary hygiene.

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
       feature/phase07-step4-settings-retention`
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
       Phase 7 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 7`
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

    THIS STEP deletes history and writes a file on a browser's say-so,
    so both are guarded. `PUT /api/settings` and `POST
    /api/retention/run` are same-origin JSON writes under
    `FetchMetadataAndWriteGuard`, with a cross-site test each. The
    allowlist is a literal, so no request can reach `[web]` (the
    loopback bind), `ntfy_server`, `[engine]`, or any other key; a
    test walks every other key and expects a refusal. Secrets stay
    out: the allowlist holds none, and an error names the key, never
    the value (`services/config.py`'s rule). The temporary file sits
    beside the target with owner-only permissions on POSIX and is
    replaced atomically, so a crash leaves the old file whole.
    `tomlkit` passes `pip-audit --strict` and the licence check, and
    only `services/settings_file.py` imports it. The prune deletes
    nothing newer than its plan's cutoff, and its log records carry
    counts, never a location's name above INFO, a coordinate, or a
    query. Retention never touches `locations`, `settings`, or
    `heartbeats`, and never the current day's ledger: a test asserts
    each.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 7 (Depth). Step 4: settings
    and retention.

    Current state (as of Phase 6, post-Phase-7 Step 3):

    - `services/config.py`: `load_settings(paths, environ)`,
      `setting_origins`, `ENVIRONMENT_OVERRIDES`, `_Section`
      (`extra="forbid"`, frozen), and `ConfigError`, whose messages
      name keys and never values. `AppPaths` has `settings_path`,
      `database_path`, `backup_dir`, `cycle_lock_path`, and
      `monitor_lock_path`.
    - `web/routes/settings.py` serves `GET /api/settings`;
      `SettingsResponse` holds `settings_file`,
      `settings_file_exists`, `file_modified_since_start`, and each
      `SettingOriginResponse`. `WebState.settings` and
      `WebState.setting_origins` are frozen for the process,
      `WebState` holds no environment, and `Settings.tsx`'s banner
      tells the operator to restart whenever
      `file_modified_since_start` is true.
    - `MonitorSchedule.execute_cycle` (`services/schedule.py`) builds
      a new `MonitorService` each cycle from `self._settings`, and
      `MonitorService._locked` hands those to `NotificationService`;
      the alarms read them too (`_check_degraded_alarms`, and
      `_quiet_holds_toast` under `run_heartbeat_task`).
      `cli/serve.py`'s `run_monitor_loop` calls `run_monitor` for both
      `serve` and `check`; `run_fallback_check` and `cli/snapshots.py`
      build their own `MonitorService` and read the file at each
      start. `_read_file` lets `UnicodeDecodeError` and
      `PermissionError` escape.
    - Row relationships (Decision 8): `snapshots` cascade to
      `source_outcomes`, `storm_observations`, `product_geometries`,
      `snapshot_provenances` (and through them `snapshot_geometries`),
      `text_product_observations`, `feed_item_observations`,
      `alert_observations`, `drift_warnings`, and `assessments`;
      `assessments` cascade to evidence, changes,
      `notification_decisions`, `notifications` (and their
      deliveries), and `ai_outputs`; `monitor_cycles.snapshot_id`,
      `notifications.cycle_id`,
      `notification_decisions.notification_id`, and
      `ai_outputs.call_id` are `SET NULL`;
      `outcome_responses.raw_response_id` and `raw_responses.sha256`
      have no cascade. `notifications` with no location (`test`,
      `degraded`) reach no assessment.
    - `NotificationService._load_state` walks a location's decisions
      in id order: the last row with `level_after` sets
      `announced_level`; the last `level` row that is not `held` names
      the announcing assessment; `held` rows after it build
      `pending_held`; and `sent` rows fill `last_sent`, which cooldown
      (at most 48 hours) reads. `AssessmentRepository.latest` answers
      the next diff. `RawResponseCache` answers validators from the
      newest row of a key, and `raw_cache.stored_png` reads the newest
      snapshot's outlook graphics by SHA-256. `Ledger` reads today's
      rows for the cap.
    - `cli/serve.py`'s `_start_background(stop, hub, database,
      summarizer, now=)` starts the watcher, timer, and summarizer
      tasks. `ProcessLock` guards the cycle (`cycle.lock`) and the
      monitor (`monitor.lock`); it polls every 0.5 seconds and exposes
      no waiter. `HeartbeatRepository.record` with `expected_every_s`
      is what `doctor` and the staleness banner read, and two cadences
      without a success read stale. `backup_database(source,
      backup_dir, revision, now)` copies a live database through
      SQLite's online backup API; only a migration calls it today.
      `_begin` starts a transaction on every engine connection.
      `migrations/versions/` ends at 0009 (Step 3), and
      `tests/services/test_database.py` pins each merged revision in
      `FROZEN`.
    - `frontend/src/ai/AiSettingsSection.tsx` shows the AI's state and
      controls; `Settings.tsx`'s sections carry `id`s;
      `/api/settings`'s `file_modified_since_start` shows a restart
      note. `queryKeys` lives in `frontend/src/api/keys.ts`, which
      mirrors `QueryKey`; a prefix under `settings` needs no new key.

    Files to read (every file before drafting):

    - docs/roadmap/phase07-roadmap.md (Decisions 7, 8, and 19, and
      this step).
    - src/weatherbot/services/config.py, monitor.py, schedule.py,
      doctor.py, health.py, and locks.py.
    - src/weatherbot/services/persistence/tables.py, repositories.py,
      raw_cache.py, and database.py, tests/services/test_database.py,
      and tests/cli/test_storage_growth.py.
    - src/weatherbot/services/notifications.py's `_load_state`.
    - src/weatherbot/services/ai/ledger.py and outputs.py.
    - src/weatherbot/cli/serve.py, check.py, config.py, documents.py,
      and __init__.py, and tests/cli/test_documents.py.
    - src/weatherbot/web/routes/settings.py, web/app.py, and
      web/schemas.py.
    - frontend/src/pages/Settings.tsx, src/ai/AiSettingsSection.tsx,
      and src/api/keys.ts.
    - CONTRIBUTING.md (the retention note).
  </context>

  <goal>
    Add the safe settings write and the page's editors, and add
    retention (service, CLI, routes, worker, and page), with the
    keep-list proved against the policy and the diff.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `uv add tomlkit`, confirm the lock adds only it, and record its
      licence in the PR body. `services/settings_file.py` is the only
      module that imports it: `EDITABLE`, the literal allowlist of
      Decision 7; `SettingChange(table, key, value)`; and
      `apply_changes(paths, changes, *, expected_sha256, environ) ->
      SettingsUpdate`, which reads the file's bytes, compares their
      SHA-256 (a missing file's digest is that of empty bytes),
      refuses an unlisted key and a key whose `ENVIRONMENT_OVERRIDES`
      variable is set, applies the changes to a `tomlkit.parse`
      document (creating a table when it is absent), renders it,
      validates the result through `tomllib` and the same merge
      `load_settings` runs, environment included (a split of
      `services/config.py`'s loader, so that a quiet start a variable
      sets with its end cleared is refused here, and not by `serve` at
      its next start), writes a temporary file in the same directory,
      and `os.replace`s it, retrying for up to a second on
      `PermissionError`, because Windows refuses a replace while a
      reader holds the target. Errors subclass `ConfigError` and name
      keys, never values. `SettingsUpdate` says which keys apply at
      the next cycle and which at the next start.
    </requirement>

    <requirement>
      `GET /api/settings` re-reads the file on every request, through
      `setting_origins(paths, state.environ)` and a new
      `WebState.environ` that `serve` sets, because the frozen
      `state.setting_origins` would put a saved value back on the page
      at once. When the file no longer parses, the answer keeps the
      last origins and adds `settings_file_problem`, which gives a
      position and never the file's text. It gains
      `settings_file_sha256`, each key's `editable` and `applies`, and
      `restart_keys`, the next-start keys whose value differs from
      what the process started with. `Settings.tsx`'s banner reads
      `restart_keys` and lists them: `file_modified_since_start`,
      which stays in the answer, turns true at every save, and a saved
      quiet hour needs no restart. `PUT /api/settings` takes
      `{"expected_sha256", "changes": [...]}` and answers the update,
      409 for a stale digest, 409 naming the variable for an
      environment-set key, and 422 for a bad value or a file that no
      longer parses, without echoing either; it publishes a `settings`
      invalidation. It is a sync route, because it reads and writes a
      file.
    </requirement>

    <requirement>
      `[retention]`: `RetentionSettings(history_days: int = 0)`, 0 or
      30 to 3,650, a new `Settings` field, with the literal
      `WEATHERBOT_RETENTION_HISTORY_DAYS` override. The `Settings`
      docstring and `tests/services/test_config.py` follow.
    </requirement>

    <requirement>
      `live_settings`. `services/config.py`'s `LiveSettings(paths,
      environ, first)` is a callable that reads the file and returns
      `first` with its `notifications` and `retention` tables replaced
      (`model_copy`), so every other key stays as the process started.
      A `ConfigError`, an `OSError`, or a `UnicodeDecodeError` returns
      the last good settings and logs one WARNING until the file
      parses again, so a hand edit never stops the monitor.
      `run_monitor(..., live_settings=None)` hands it to
      `MonitorSchedule` and `run_heartbeat_task`. `MonitorSchedule`
      holds it, because the `MonitorService` it builds each cycle can
      keep nothing: it assigns `self._settings` from the seam at the
      top of `execute_cycle`, so the cycle and the alarms after it
      read the same values, and `run_heartbeat_task` reads it each
      tick for `_quiet_holds_toast`. `cli/serve.py`'s
      `run_monitor_loop` builds one for `serve` and `check`.
      `tests/services/test_live_settings.py`: a quiet-hours change
      between two cycles decides the second; an alarm reads the new
      hours; and a file that stops parsing, one of invalid UTF-8, and
      one that cannot be opened each keep the last good settings with
      one WARNING.
    </requirement>

    <requirement>
      Revision `0010_retention_indexes.py`, before any delete exists:
      `op.create_index`, never a batch, on
      `snapshot_geometries.content_id`, `raw_responses.sha256`,
      `monitor_cycles.snapshot_id`, and `notifications.assessment_id`,
      with `index=True` on those columns in `tables.py`, a downgrade
      by `drop_index`, and `FROZEN` pinning it. Decision 8 gives the
      measurement. The two `ai_outputs` foreign keys stay unindexed:
      that table is small, and `tests/services/test_database.py` pins
      its index set. `tests/services/test_foreign_key_indexes.py`
      walks `Base.metadata` and asserts that every foreign key's child
      column leads an index or a unique key, those two alone excepted.
      `tests/cli/test_storage_growth.py` stays under its 128 KiB
      budget, and the PR body records the new figure beside the 64 KiB
      measured before.
    </requirement>

    <requirement>
      `services/retention.py`. `RetentionPlan` (the cutoff; `counts`,
      one entry for every table a run deletes from; the kept reasons;
      and the estimated bytes), `RetentionService(engine, paths, *,
      now)`, `plan(days) -> RetentionPlan` (read only), and
      `run(cutoff) -> RetentionResult`. `run` takes the plan's cutoff
      and never computes its own, so it removes nothing newer than the
      plan the operator read, and it reads the keep-list afresh for
      each batch, because a cycle can run between two. It holds
      `retention.lock`, a `ProcessLock` in the data directory, so the
      page, the CLI, and the worker cannot overlap. It deletes in
      batches of 100 snapshots, oldest first, and then orphans in
      batches of 500 rows, each batch its own `writing_session` under
      `cycle.lock`, released after every batch with a one-second pause
      before the next, because a poller that sleeps 0.5 seconds would
      lose a lock taken back at once. A `LockBusyError` ends the run
      as `partial`, and the next run resumes. The orphans:
      `raw_responses` no `outcome_responses` row links, never the
      newest of a `(source_id, product_key)`, older than the cutoff;
      `response_bodies` no raw row names; `geometry_contents` no
      `snapshot_geometries` row names; `text_products`, `feed_items`,
      and `alerts` no observation names, older than the cutoff;
      `monitor_cycles` older than the cutoff; no-location
      `notifications` older than it; `ai_calls` older than both the
      cutoff and 31 days; `ai_outputs` with no assessment older than
      it. `storms` and `advisories` stay: they are small and name the
      history that remains.
    </requirement>

    <requirement>
      The copy. Before its first delete, `run` copies the database
      through `backup_database`, under the name
      `weatherbot-<stamp>-<revision>-prune.sqlite3`, unless a prune
      copy younger than 7 days exists. It keeps the two newest prune
      copies, never touches a migration's, and deletes nothing if the
      copy fails. A run with nothing to delete copies nothing. The
      project roadmap's runbook restores from this file, because a
      migration's copy can be months old.
    </requirement>

    <requirement>
      The keep-list, exactly: the newest snapshot; each location's
      newest assessment (`AssessmentRepository.latest`); the
      assessment of each location's newest non-`held` `level` decision
      and of every decision row after it; each of those assessments'
      snapshots; and the ledger's newest `pause` or `resume` row,
      whatever its age (`Ledger` reads it to decide `paused`).
      Everything a cascade would remove from a kept assessment stays
      with it. Delete children before parents where no cascade runs:
      `outcome_responses` are gone with their outcomes before
      `raw_responses`, then `response_bodies`, and
      `snapshot_geometries` before `geometry_contents`. A cutoff
      inside the window of a pending held drop removes nothing that
      drop reads.
    </requirement>

    <requirement>
      Proof, in `tests/services/test_retention_keeplist.py`: build
      each location's history through the real `MonitorService` and
      `NotificationService` from live-origin snapshots, because
      `SnapshotRepository.save` and `AssessmentService` refuse a
      replay's (levels 1 to 5, a held drop pending, and a level
      unchanged for longer than the window), prune, and assert
      `_load_state` equals what it read before, apart from `last_sent`
      entries older than the longest cooldown, that the next cycle's
      `diff` and decisions equal those of an unpruned copy of the
      database (copied with `database_template`), that no level-1
      location re-announces, and that no escalation repeats.
      `tests/services/test_retention.py`: the plan equals what the run
      removes, row for row, on every table; `history_days = 0` removes
      nothing; a repeated run removes nothing more; the validators of
      the newest responses survive, so the next fetch is still
      conditional; `/api/outlook`'s PNGs survive; today's ledger
      survives; a pause set a year ago still reads `paused`;
      `locations`, `settings`, and `heartbeats` do not change; a cycle
      waiting on `cycle.lock` takes it between batches; a run at a
      plan's cutoff after a later cycle removes nothing newer than it;
      a second run overlapping the first is refused; a failed copy
      deletes nothing; and a run copies at most weekly and keeps two
      copies.
    </requirement>

    <requirement>
      `weatherbot prune [--dry-run] [--days N] [--cutoff INSTANT]
      [--vacuum] [--json]`: `--days` overrides the setting for one run
      (30 to 3,650); with neither it reports that retention is off and
      exits 0; `--dry-run` prints the plan with its cutoff, and
      `--cutoff` runs exactly that plan, within the same bounds.
      `--vacuum` runs `VACUUM` afterwards on its own autocommit
      `sqlite3` connection, as `backup_database` opens one, because
      `VACUUM` refuses to run inside the transaction `_begin` starts;
      it is refused with exit 2 while `monitor.lock` is held, and it
      holds `cycle.lock`. `docs/schema/prune.schema.json` joins
      `DOCUMENTS`, and `tests/cli/test_documents.py` counts 18. The
      command is registered as `app.command("prune")`, literally.
    </requirement>

    <requirement>
      `GET /api/retention`: the database's and WAL's sizes, the oldest
      and newest snapshots, row counts, the setting, the last run and
      its result, and the plan for `?days=` (30 to 3,650), with its
      cutoff. `POST /api/retention/run` takes `{"cutoff": ...}`, the
      plan's, refused with 422 unless it lies 30 to 3,650 days ago,
      and runs one prune as a background task, 409 while
      `retention.lock` is held, publishing `settings` when it ends.
    </requirement>

    <requirement>
      `RetentionWorker` beside the cycle watcher in
      `_start_background`, always started, because `_start_background`
      runs once and the page can turn retention on later, and shielded
      and drained at shutdown as the watcher is. It wakes at 03:30
      local and reads `live_settings`. While `history_days` is 0 it
      does nothing else, and clears the heartbeat's cadence as
      `_clear_idle_alerts_cadence` does, so turning retention off
      leaves `doctor` no promise to fail. Above 0 it makes one
      attempt, recording `HeartbeatRepository.record("watch",
      "retention", ..., expected_every_s=172800)`. While any
      location's latest level is 3 or above it records `success` and
      prunes nothing, because a long storm must not read stale;
      otherwise it plans and runs with `asyncio.to_thread`, and a
      failed run records a failure and logs an ERROR with its class. A
      worker that stops running is then stale in `doctor` and on the
      dashboard.
    </requirement>

    <requirement>
      Page. `frontend/src/settings/QuietHoursForm.tsx` (start, end,
      zone, and cooldown, with an explanation that levels 1 and 2
      alone are held and that an escalation always arrives), the AI
      section's editable cap and feature switches, and
      `frontend/src/settings/RetentionPanel.tsx` (the sizes, the
      setting, the plan for a chosen number of days, and "Prune now"
      behind a Radix `AlertDialog` that states what goes). A key the
      environment sets shows its variable and is read-only; each save
      says when it applies; a 409 for a stale file reloads and asks
      again. `CONTRIBUTING.md`'s retention note and `README.md`
      follow, and `docs/NOTIFICATIONS.md` gains the page's quiet
      hours.
    </requirement>

    <requirement>
      Tests besides those above:
      `tests/services/test_settings_file.py` (comments and order
      preserved byte for byte outside the changed lines, a missing
      file, a new table, every refusal, the atomic replace, a stale
      digest), `tests/web/test_settings_writes.py` (every
      non-allowlisted key refused, the environment refusal, a
      cross-field refusal through a variable, a saved value read back
      by the next `GET`, `restart_keys`, a file that stops parsing,
      and cross-site refusal; `tests/conftest.py` sets
      `WEATHERBOT_NOTIFICATIONS_TOAST`, so a test that edits `toast`
      deletes it first), `tests/web/test_retention_routes.py`,
      `tests/cli/test_prune_command.py`,
      `tests/services/test_retention_worker.py`, a
      `tests/test_architecture.py` scan that only `settings_file.py`
      imports `tomlkit`, and frontend tests for each new component.
      `scripts/export_api_fixtures.py`, `docs/api/openapi.json`, and
      `frontend/src/api/schema.d.ts` regenerate.
    </requirement>

    <requirement>
      Filepath comment: every new Python, TypeScript, YAML, or
      Markdown file gets its repository-relative path as its first
      line where the file type accepts comments, matching the sibling
      files.
    </requirement>
  </requirements>
</task>
```

### Step 4 acceptance criteria

- A setting edited from the page lands in `weatherbot.toml` with every comment
  and unrelated line byte-identical; the file is replaced atomically.
- A key off the allowlist, a key the environment sets, a stale digest, and a bad
  value are each refused, with nothing written and no value echoed.
- A quiet-hours change applies at the next cycle with no restart, alarms
  included; a file that stops parsing logs one WARNING and leaves the monitor
  running on its last good settings; the page reads a saved value back at once
  and names only the keys that need a restart.
- `weatherbot prune --dry-run`'s counts equal what a run at its cutoff then
  removes, on every table, and the page's run takes the same cutoff;
  `history_days = 0` removes nothing.
- After a prune, every location's policy state and the next cycle's diff and
  decisions equal an unpruned copy's; nothing re-announces and no escalation
  repeats.
- The next fetch stays conditional, the outlook graphics still serve, today's
  ledger and an old pause stand, and `locations`, `settings`, and `heartbeats`
  are untouched; a run copies the database before its first delete, and a failed
  copy deletes nothing.
- Revision 0010 indexes the four foreign keys, and growth stays under its 128
  KiB budget; a cycle waiting on the lock takes it between batches.
- The worker always runs: with retention off it promises no cadence, a day
  skipped for a storm counts as a success, and a worker that stops running reads
  stale in `doctor`.
- `tomlkit` is imported only by `services/settings_file.py`; `pip-audit
  --strict` passes on the new lock.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — and both new writes refuse a cross-site caller, while
  the settings write cannot reach `[web]` or any secret, per the project
  roadmap's "Security & privacy strategy".

---

## Step 5 — The map's depth ✅

**Status:** Complete — PR #96 (2026-11-04)

> **Goal:** Put the storm's whole official picture on the map, from what is
> stored, and the live overlays only when asked. `GET /api/map/depth` serves
> wind radii, past track, and past points per storm and peak surge per snapshot
> on demand; `GET /api/map/wind-probabilities` serves one threshold;
> `MapResponse` gains only `available_layers`; `GET /api/map/advisories` and
> `GET /api/map?snapshot_id=` give the time slider its steps; `web/guards.py`'s
> `img-src` gains nowCOAST; and `frontend/src/map/` gains six layer keys, each
> off by default, a canvas renderer for the probability bands, WMS layers for
> radar and satellite, their legends and attributions, and `AdvisorySlider.tsx`.
> `docs/DATA_SOURCES.md` records each service's terms and what is drawn; a live
> test watches OpenStreetMap's loopback `Referer`; and an issue holds the
> proxy's design.

**Branch:** `feature/phase07-step5-map-layers`

**Deploys:** nothing beyond merge — the operator's copy takes this step at
Step 9. A browser that opens the new build makes no overlay request until a
toggle is turned on.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.86/1M           | $6.13/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.72/1M           | $6.76/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | XHigh              | XHigh              |
|               | AA       | ≈45.2              | 51                 | 52.4               |
|               | Price    | $2.31/1M           | $4.00/1M           | $17.73/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels.

> Ran 2026-11-04: Balanced Pick / Quality Runner-up — Gemini 4 Argon · High.

**Conversation:** New

**Model rationale:** Step 5 is coding with a multimodal secondary category — a
map whose result must be looked at, across a response model, three routes, a CSP
change, and six layers — at High complexity, not novel: Decisions 9 to 13 fix
each layer's source and behaviour. On the step alone, the Balanced Pick fits
best: Gemini 4 Argon on Antigravity at Effort High, with Thinking On, pairs
S-tier coding with strong visual judgement for colour ramps, legends, and layer
order. The Quality Pick, Opus 5.5 at XHigh, adds audit depth this display-only
step needs less than the steps around it, and the Cost Pick, GPT-6.1 Sol at
High, saves money with less eye for the result. The conversation is new, per
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
       feature/phase07-step5-map-layers`
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
       Phase 7 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 7`
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

    THIS STEP widens the CSP by one host, so the widening is exact:
    `img-src` gains only `https://nowcoast.noaa.gov`, a test pins the
    whole header, and no `connect-src`, `script-src`, or `style-src`
    changes. The browser requests an overlay only while its toggle is
    on: a smoke asserts no request to that host otherwise, and no
    overlay URL carries anything but a map tile's box. Layer text
    reaches the page through `textContent`-built popups (Leaflet
    treats a string as HTML), and a surge name holding markup renders
    literally, with a test. `GET /api/map/wind-probabilities` and
    `snapshot_id` validate their parameters and answer a generic 404,
    echoing nothing. `/api/map` keeps its location coordinates to the
    operator's own page, as it does today, and no new layer carries a
    location's coordinate. The personal-data rule still holds:
    fixtures round to two decimals, and the synthetic surge fixture
    says it is one. The live test sends one tile request with a
    loopback `Referer` and the project's own User-Agent, and never
    bulk-fetches (OpenStreetMap's policy).
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 7 (Depth). Step 5: the map's
    depth.

    Current state (as of Phase 6, post-Phase-7 Step 4):

    - `web/map_layers.py`: `build_storm_map_layers`,
      `build_map_response`, `SnapshotLayerCache` (`get_or_load`,
      `get_or_build`, eight entries), `storm_reference_longitude`,
      `unwrap_coordinates`, and `_feature`, which pass geometry
      through unrounded. `web/routes/map.py` has one route.
      `SnapshotRepository` has `latest_id`, `load`, and
      `drift_warnings`.
    - `WindRadii`: `threshold_kt`, `tau_h`, `valid_at`, `synoptic_at`,
      four `*_extent_nmi`, `advisory`, and a geometry. `DisplayLayer`:
      `layer_name`, a raw `feature_collection`, `crs`, and provenance;
      layer names are `Past Points`, `Past Track`, `Past Cumulative
      Wind Swath`, `Points`, `Lines`, and `Polygons`. Recorded Past
      Track features hold `stormtype`, `ss`, and `binnumber`; Past
      Points hold `stormname`, `stormtype`, `intensity`, `mslp`,
      `dtg`, `ss`, and `binnumber` (and `lat` and `lon`, which the
      response must drop). `StormSummary.slot` holds a storm's
      `binnumber`.
    - `WindProbabilityProduct`: `threshold_kt`, `synoptic_at`, `bands`
      (`lower_pct`, `upper_pct`, `label`, and geometry), and
      `coverage` for an extract. Recorded GeoJSON: 568 KB (34 kt), 364
      KB (50), 197 KB (64).
    - `frontend/src/map/layers.ts`: `MapLayerKey`, `LayerVisibility`,
      `LAYER_TOGGLE_ITEMS`, `DEFAULT_LAYER_VISIBILITY`,
      `MAP_LEGEND_SECTIONS`, the style functions, `buildMapLayers`,
      and `createPopupElement`. `useLeafletMap.ts`'s
      `getCategoryItems` and `MapView.tsx`'s `updateVisibility` are
      exhaustive switches over the keys. Swatches are Tailwind
      classes.
    - `web/guards.py`'s `CSP_SUFFIX`; `tests/web/` pins the CSP.
      `frontend/e2e/guard.ts` fails on any origin it does not route.
    - `scripts/serve_demo.py` serves a recorded snapshot plus its
      simulated advisory, and `scripts/export_api_fixtures.py` writes
      `frontend/src/test/fixtures/`, rounding GeoJSON to two decimals.
    - The register: `docs/DATA_SOURCES.md` "Overlays",
      "OpenStreetMap", `tropical/NHC_PeakStormSurge`,
      `tropical/StormSurgeRisk`, and its peak-surge and overlay rows.

    Files to read (every file before drafting):

    - docs/roadmap/phase07-roadmap.md (Decisions 1, 9 to 13, and 19,
      and this step).
    - src/weatherbot/web/map_layers.py, routes/map.py,
      routes/storms.py, schemas.py, and guards.py.
    - src/weatherbot/models/storms.py, products.py, and outlook.py.
    - src/weatherbot/services/persistence/repositories.py
      (`SnapshotRepository`).
    - frontend/src/map/ (every file and test) and frontend/e2e/.
    - scripts/serve_demo.py and scripts/export_api_fixtures.py.
    - docs/DATA_SOURCES.md (the sections above) and
      tests/web/test_csp*.py or wherever `CSP_SUFFIX` is asserted.
  </context>

  <goal>
    Serve radii, past track, surge, and probability bands; add the
    slider's two routes; widen the CSP by one host; and draw six new
    layers, off by default, with legends, attributions, and failure
    states.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `GET /api/map/depth?snapshot_id=` answers `MapDepthResponse`:
      `snapshot_id`, `storms` (each with `atcf_id` and the
      `wind_radii`, `past_track`, and `past_points` collections,
      possibly empty), `peak_surge`, and the notice, built in
      `web/map_layers.py` from the cached bundle, defaulting to the
      latest snapshot, on a sync route. Radii features carry
      `threshold_kt`, `tau_h`, `valid_at`, the four extents, and
      `advisory`, unwrapped by the storm's reference longitude. The
      builder selects Past Track and Past Points by `binnumber ==
      summary.slot` and `stormnum` equal to the ATCF id's number,
      because a later storm reuses a slot (`sources/nhc_map.py`'s
      `_same_storm`); a replay storm has no slot and gets empty
      collections, and past features keep only `stormtype`, `ss`,
      `intensity`, `mslp`, and `dtg`.
    </requirement>

    <requirement>
      `peak_surge` is a collection from the `Polygons` and `Lines`
      display layers with `properties` reduced to `name` and `layer`.
      `MapResponse` gains only `available_layers`, naming which layers
      this payload can hold (a replay's reads without radii, past
      track, surge, radar, and satellite, and a stored advisory's
      without radar and satellite), so that the page can say so; a
      test pins `/api/map`'s recorded answer at under 1 KB larger than
      today's. `scripts/synthetic_surge.py`, on pytest's `pythonpath`
      and beside `serve_demo.py`, builds a labelled synthetic layer in
      code at two decimals, with the archived file's names (`Tampa
      Bay...8-12 ft`); `scripts/serve_demo.py` stores it in the
      demonstration snapshot.
    </requirement>

    <requirement>
      `GET
      /api/map/wind-probabilities?threshold_kt=34|50|64&snapshot_id=`:
      one `WindProbabilityResponse` (`synoptic_at`, `threshold_kt`,
      bands as features with `lower_pct`, `upper_pct`, and `label`,
      and `coverage`), from the cached bundle, defaulting to the
      latest snapshot, sync, with replay's sibling `GET
      /api/replay/{atcf_id}/{advisory}/wind-probabilities`. Measure
      the 34-kt answer on the recorded snapshot; above 400 KB,
      simplify each band with Shapely at a tolerance under the
      product's 5 km grid, state it in the band's `geometry_note`, and
      record the tolerance in the PR body.
    </requirement>

    <requirement>
      `GET /api/map/advisories?limit=` (1 to 200, default 96): newest
      first, the newest snapshot that carried each `(atcf_id,
      advisory)`, because a roster cycle can store an advisory's first
      snapshot beside the previous advisory's cone, read by a new
      `SnapshotRepository.advisory_steps(limit)` from
      `storm_observations` without decoding geometry. `GET
      /api/map?snapshot_id=`: that snapshot through the cache, with an
      unknown id a generic 404. The locations layer stays today's, a
      past snapshot being drawn around the locations as they are now,
      and each marker reads the assessment stored for that snapshot (a
      new `AssessmentRepository.for_snapshot`), or no level, never
      today's.
    </requirement>

    <requirement>
      `CSP_SUFFIX`'s `img-src` gains exactly
      `https://nowcoast.noaa.gov`, and the tests that pin the header
      follow. Nothing else in the policy changes.
    </requirement>

    <requirement>
      Frontend. `MapLayerKey` gains `wind_radii`, `past_track`,
      `peak_surge`, `wind_probabilities`, `radar`, and `satellite`,
      all off in `DEFAULT_LAYER_VISIBILITY`, with toggles, legends,
      and every exhaustive switch updated. Radii: outlines by
      threshold, 34, 50, 64 kt, on the existing SVG renderer. Past
      track: a solid line and points, styled by `ss`. Surge: polygons
      and lines coloured by the range after `...` through a fixed
      table, an unknown range neutral, the name in a DOM popup. Radii,
      past track, and surge read a `useQuery` of `/api/map/depth`
      under the `map` key, enabled once one of them is on.
      Probabilities: a threshold choice, a `useQuery` under the `map`
      key enabled only while toggled, bands in ascending order, NHC's
      ramp as Tailwind-free hex constants, and the note "Chance of
      winds at this speed within 120 hours"; an extract's coverage is
      outlined and labelled. Radar and satellite: `L.tileLayer.wms`
      with `version: "1.3.0"`, `format: "image/png"`, `transparent:
      true`, opacity 0.6, and the layers Decision 11 names, added only
      while toggled, removed on toggle off, with the attribution `NOAA
      nowCOAST` and a note that an image can be some minutes old;
      `tileerror` shows "Radar unavailable" in the legend. No timer
      refreshes them.
    </requirement>

    <requirement>
      The overlay path. `useLeafletMap` receives only `mapData`,
      `MapLayerItem` requires `style` and `latLngs`, and
      `syncLayersOnMap` removes and re-adds everything on any change,
      so bands and WMS layers cannot go through `buildMapLayers`. The
      hook gains an `overlays` option (the probability payload and
      which raster layers are on) with an effect of its own that adds
      and removes only those layers, one `L.canvas()` renderer per map
      rather than per rebuild, and an `onOverlayError` callback for
      `tileerror`. jsdom's `getContext` returns null, so
      `MapView.test.tsx` stubs it before a canvas path is added.
    </requirement>

    <requirement>
      `frontend/src/map/AdvisorySlider.tsx`: a native `<input
      type="range">` over a list of steps, with a label naming the
      storm, the advisory, and the time, keyboard operable, and shared
      with Step 7. `MapView.tsx` shows it when more than one stored
      step exists; a past step fetches `/api/map?snapshot_id=` and
      shows "Stored advisory: <storm> <n>, <time> — not the latest"
      and "Back to latest". While it sits in the past, an invalidated
      `map` query does not move the view; the banner notes a newer
      advisory arrived. A step costs one fetch, with no request while
      the thumb moves: the fetch fires on release.
    </requirement>

    <requirement>
      A replay in `MapView` disables the toggles `available_layers`
      excludes and says why ("not in this corpus"), and a stored
      advisory does the same for radar and satellite ("live only"); a
      replay's probability windows draw through the replay sibling
      route.
    </requirement>

    <requirement>
      Register and terms. `docs/DATA_SOURCES.md`, dated: the overlays
      are drawn (by the browser, off by default), with their terms and
      attribution; the Mesonet is a documented fallback, not wired;
      `StormSurgeRisk` is not drawn, and its row says so; peak surge
      is drawn from `name`, with its first-capture rule.
      `tests/live/test_osm_referer_live.py` requests one tile with a
      loopback `Referer` (Decision 13), and the Step opens an issue
      holding the proxy's design, which the register links.
    </requirement>

    <requirement>
      Tests: `tests/web/test_map_depth.py` (each new layer from the
      recorded snapshot, selection by slot, an antimeridian case, an
      empty replay's `available_layers`, dropped `lat` and `lon`),
      `tests/web/test_map_history.py` (`advisory_steps`, an unknown
      id, the cache), `tests/web/test_wind_probability_route.py`, the
      CSP test, `frontend/src/map/layers.test.ts` additions (colour
      tables, an unknown range, markup in a name; its legend test pins
      the categories and needs `crsText` on every item),
      `frontend/src/map/MapView.test.tsx` additions (its toggle test
      expects every toggle checked, so it iterates the default-on
      six), `AdvisorySlider.test.tsx`, and
      `frontend/e2e/layers.spec.ts`, which writes
      `test-results/smoke-switch.flag` and presses "Check now" itself,
      as `dashboard.spec.ts` does, so that two stored advisories exist
      in any spec order, routes `nowcoast.noaa.gov` to the blank tile,
      asserts no such request before the toggle and at least one
      after, and turns each layer on. `guard.ts` gains that origin as
      routed, with the same fulfil as OpenStreetMap's.
      `scripts/export_api_fixtures.py`, `docs/api/openapi.json`, and
      `frontend/src/api/schema.d.ts` regenerate.
    </requirement>

    <requirement>
      New legend sections go before `locations`, because legend order
      is draw order and a location's marker stays on top.
      `README.md`'s dashboard section and `CHANGELOG.md` describe the
      layers. The project roadmap's §3 already names the host (this
      roadmap's PR).
    </requirement>

    <requirement>
      Filepath comment: every new Python, TypeScript, YAML, or
      Markdown file gets its repository-relative path as its first
      line where the file type accepts comments, matching the sibling
      files.
    </requirement>
  </requirements>
</task>
```

### Step 5 acceptance criteria

- Wind radii, past track, past points, peak surge, and probability bands render
  from recorded or labelled synthetic fixtures with no network, each off by
  default.
- The default map makes no new request, and `/api/map` grows by under 1 KB: a
  smoke sees no request to `nowcoast.noaa.gov` until a toggle is on.
- The CSP differs from Phase 6's by exactly one `img-src` host.
- The time slider steps through stored advisories, with no request while
  dragging; a past step says it is not the latest, and "Back to latest" returns.
- A surge name holding markup renders as text; an unknown range is neutral, with
  its text.
- A replay names the layers its corpus lacks and fabricates none.
- `docs/DATA_SOURCES.md` records each overlay's terms and attribution, and the
  live `Referer` test passes; the proxy's issue exists and the register links
  it.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean
  (ESLint with `eslint-plugin-security` at no warnings), dependency audit clean
  — and the map's new requests carry no location, per the project roadmap's
  "Security & privacy strategy": an overlay request names a tile only, and only
  while toggled on.

---

## Step 6 — Charts and history

**Status:** Not started

> **Goal:** Show how a location's picture has moved. `GET
> /api/charts?location=&limit=` answers a location's level history from the
> assessments' columns and its wind bands per synoptic time from their stored
> readings; `frontend/src/charts/` draws `LevelSparkline`, `LevelHistoryChart`,
> `WindProbabilityChart`, and `ArrivalTimeline` as plain SVG over pure scale
> functions, with no new dependency; every dashboard card gains its sparkline
> and arrival display, the dashboard gains a comparison strip across locations,
> and `Timeline.tsx` gains a location's charts and older pages through `GET
> /api/timeline?before=`.

**Branch:** `feature/phase07-step6-charts`

**Deploys:** nothing beyond merge — the operator's copy takes this step at
Step 9.

Settings — ladder (`roadmodel ladder --category coding --complexity medium`):

|               |          | Cost                 | Balanced             | Quality            |
| ------------- | -------- | -------------------- | -------------------- | ------------------ |
| **Pick**      | Model    | **Gemini 3.8 Flash** | **GPT-6.1 Sol**      | **Gemini 4 Argon** |
|               | Platform | Antigravity          | Codex                | Antigravity        |
|               | Level    | Medium               | High                 | High               |
|               | AA       | 39.8                 | 50.2                 | 52.6               |
|               | Price    | $1.90/1M             | $2.86/1M             | $6.13/1M           |
| **Runner‑up** | Model    | **GPT-6.1 Sol**      | **Sonnet 5.5**       | **Opus 5.5**       |
|               | Platform | Codex                | Claude Code          | Claude Code        |
|               | Level    | Low                  | High                 | High               |
|               | AA       | 42.1                 | 46.8                 | 53.6               |
|               | Price    | $2.35/1M             | $3.40/1M             | $6.76/1M           |
| **Backup**    | Model    | **Sonnet 5.5**       | **Gemini 3.8 Flash** | **GPT-6.1 Sol**    |
|               | Platform | Claude Code          | Antigravity          | Codex              |
|               | Level    | Medium               | High                 | High               |
|               | AA       | 40.8                 | 40.9                 | 50.2               |
|               | Price    | $3.18/1M             | $2.98/1M             | $2.86/1M           |

Ranked for coding, medium complexity. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level.

**Conversation:** New

**Model rationale:** Step 6 is coding with a multimodal secondary category —
pure scales, SVG, a read route, and pages whose result must be looked at — at
Medium complexity, not novel: Decisions 14 and 15 fix what is drawn and how. On
the step alone, the Quality Pick fits best: Gemini 4 Argon on Antigravity at
Effort High, with Thinking On, brings the strongest visual judgement in this
ladder to charts that have to read at a glance in both themes. The Balanced
Pick, GPT-6.1 Sol at High, would deliver the same structure at lower cost with
less eye for the result, and the Cost Pick, Gemini 3.8 Flash at Medium, suits
the scale functions better than the design. The conversation is new, per
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
       feature/phase07-step6-charts`
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
       Phase 7 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 7`
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

    THIS STEP draws history, so it adds no new input and no
    dependency: `frontend/package.json`'s names stay equal to
    `v2.0.0-phase-5`'s (Phase 6's check 39). No `style=` attribute,
    `dangerouslySetInnerHTML`, or `innerHTML` enters: charts are SVG
    elements with class names and computed `d` attributes. `GET
    /api/charts` names a location in a query, answers an unknown name
    with a generic 404, and holds no distance, bearing, or coordinate:
    a privacy test scans its answer. It stays a sync route, so Phase
    5's check 17 and Phase 6's check 32 hold.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 7 (Depth). Step 6: charts and
    history.

    Current state (as of Phase 6, post-Phase-7 Step 5):

    - `AssessmentRepository.history(location_name, limit)` decodes the
      whole JSON, about 1 ms a row; `assessments` has `as_of`,
      `level`, `rule`, and `complete` as columns, and `(location_id,
      as_of)` is indexed.
    - Each `Assessment` holds `wind_probabilities`:
      `LocationWindProbability(threshold_kt, synoptic_at, reading,
      label, lower_pct, upper_pct, ...)`, where `reading` is `band`,
      `below_every_band`, or `outside_coverage`. Consecutive
      assessments repeat a synoptic time.
    - `StormThreatResponse` already carries `earliest_arrival` and
      `most_likely_arrival` (`ArrivalReadingResponse`: `reading`,
      `start`, `end`, `approach_at`, `label`, `reason`), and
      `Dashboard.tsx` prints them as text.
    - `frontend/src/app/ThreatLevelBadge.tsx` holds the level colours
      as classes; `frontend/src/pages/format.ts` the time formatters
      and `asSchema`; `Timeline.tsx` the feed and a client-side
      location filter; `queryKeys` the `timeline` prefix, which the
      server's events already invalidate.
    - `GET /api/timeline` takes `location` and `limit`.

    Files to read (every file before drafting):

    - docs/roadmap/phase07-roadmap.md (Decisions 14, 15, and 19, and
      this step).
    - src/weatherbot/web/routes/timeline.py, routes/assessments.py,
      and schemas.py.
    - src/weatherbot/services/persistence/repositories.py
      (`AssessmentRepository`).
    - src/weatherbot/models/assessment.py.
    - frontend/src/pages/Dashboard.tsx, Timeline.tsx, and format.ts,
      with their tests, and src/app/ThreatLevelBadge.tsx.
    - frontend/src/api/keys.ts and src/test/fixtures/.
  </context>

  <goal>
    Add the charts route and four SVG components, and put them on the
    dashboard and the timeline, with older pages and no new
    dependency.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `AssessmentRepository.level_points(location_name, limit)` reads
      `as_of`, `level`, and `complete` by column, newest first,
      without decoding JSON, and `wind_series(location_name, limit)`
      decodes the same rows' readings and keeps one per
      `(threshold_kt, synoptic_at)`. `GET
      /api/charts?location=&limit=` (limit 1 to 500, default 200)
      answers `ChartsResponse`: `location`, `time_zone`, `levels`,
      `wind`, and the notice. A location with one assessment still
      answers.
    </requirement>

    <requirement>
      `GET /api/timeline` gains `before`, an opaque cursor of
      `(occurred_at, kind, id)` that `TimelineResponse.next_before`
      returns, because locations in one cycle share an instant and a
      page can end inside one: entries sort after the cursor by the
      route's existing key, so none is skipped.
      `AssessmentRepository.history` and `NotificationService.recent`
      each gain the bound, so older notifications are reachable too.
      The default answer changes only by `next_before`.
    </requirement>

    <requirement>
      `frontend/src/charts/scale.ts`: pure functions (`timeScale`,
      `linearScale`, `stepPath`, `bandPath`, `ticksFor`), tested on
      their own, including one point, two equal instants, and a gap.
      `LevelSparkline` (a stepped line, 80 by 20, an incomplete
      assessment drawn dashed, the current level as a dot, coloured
      through a table of `stroke-` and `fill-` classes beside
      `ThreatLevelBadge`'s, which hold only border, background, and
      text classes). `LevelHistoryChart` (the same over labelled axes,
      with a marker at each change). `WindProbabilityChart` (Decision
      14: one row per threshold, a band per synoptic time from
      `lower_pct` to `upper_pct`, `<5%` drawn below the first
      gridline, `outside_coverage` left blank with a note, and the
      caption "The official chance of these winds within 120 hours, as
      each advisory cycle put it"). `ArrivalTimeline` (a bar from the
      assessment's `as_of`, a prop and never the clock, so that Step 7
      can draw a past storm, to the earliest reasonable and most
      likely arrivals when `start` and `end` exist, the reading's
      words otherwise, and nothing invented between them).
    </requirement>

    <requirement>
      Every chart has `role="img"`, a `<title>`, and a visually hidden
      table of its values; colour is never the only signal (level
      numbers in the table and the dashes for an incomplete point); it
      holds at phone width with no horizontal scroll; and it reads in
      both themes. No `style=` attribute anywhere: positions are SVG
      attributes, and colours are classes.
    </requirement>

    <requirement>
      Dashboard: each `LocationLevelCard` gains its sparkline beside
      the level and `ArrivalTimeline` in the threat table; above the
      cards, with two or more locations, a comparison strip lists
      every location's level, sparkline, and deciding rule, linking to
      its card. Chart queries use `queryKeys.charts(name)` =
      `["timeline", "charts", name]`, so the server's `timeline`
      invalidation reaches them with no new `QueryKey`, and one query
      serves a card's sparkline and the strip.
    </requirement>

    <requirement>
      Timeline: choosing a location shows its `LevelHistoryChart` and
      `WindProbabilityChart` above the feed; "Show older" pages
      through `before`; and the empty states say what will appear.
      `README.md`'s dashboard section and `CHANGELOG.md` follow.
    </requirement>

    <requirement>
      Tests: `tests/web/test_charts_route.py` (levels by column, one
      wind point per synoptic time, a bound, an unknown location, the
      privacy scan, sync-route shape),
      `tests/web/test_timeline_before.py` (including a page that ends
      inside one instant, and older notifications), repository tests,
      `frontend/src/charts/scale.test.ts`, a test per chart (paths,
      the hidden table, `outside_coverage`, one point, and no `style`
      attribute, asserted with `querySelector("[style]")`, because
      Phase 6's check 38 bans the word `innerHTML` in test files too),
      Dashboard and Timeline additions, and
      `frontend/e2e/charts.spec.ts` (the sparkline and the wind chart
      on the demonstration server, with the guard's CSP check).
      `scripts/export_api_fixtures.py` adds `charts.json`, and
      `docs/api/openapi.json` and `schema.d.ts` regenerate.
    </requirement>

    <requirement>
      Filepath comment: every new Python, TypeScript, YAML, or
      Markdown file gets its repository-relative path as its first
      line where the file type accepts comments, matching the sibling
      files.
    </requirement>
  </requirements>
</task>
```

### Step 6 acceptance criteria

- `GET /api/charts` answers a location's levels and one wind reading per
  threshold and synoptic time, reads levels without decoding JSON, and holds no
  distance or coordinate.
- The wind chart draws official bands as ranges, says what the 120-hour product
  means, and leaves `outside_coverage` blank with a note.
- Every chart has a text alternative, reads in both themes, and fits a phone's
  width.
- The dashboard shows a sparkline per card and, with two locations, a comparison
  strip; the timeline shows a location's charts and pages back with `before`,
  skipping no entry.
- An event updates a chart with no new `QueryKey` and no poll.
- `frontend/package.json`'s names are unchanged, and no file under
  `frontend/src` holds a `style=` attribute.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean
  (ESLint with `eslint-plugin-security` at no warnings), dependency audit clean
  — and the charts route holds no location data beyond a name, per the project
  roadmap's "Security & privacy strategy".

---

## Step 7 — Replay in the UI

**Status:** Not started

> **Goal:** Let a past storm scrub advisory by advisory through the same engine
> and the same components. `services/replay.py` gains `ReplayTimelines`, an
> eight-entry in-memory cache over `ReplayService.timeline`, and `replay_notes`,
> moved from the CLI; `GET /api/replay/{atcf_id}/timeline?location=` and `GET
> /api/replay/{atcf_id}/{advisory}/assessment?location=` serve it;
> `frontend/src/assessment/` extracts the dashboard's level, evidence,
> official-product, and threat components; and `frontend/src/pages/Replay.tsx`,
> at `/replay`, shows the storm and location pickers, the level ladder, Step 5's
> slider, the map, and the assessment, under a banner that cannot be dismissed.
> Dorian 2019 at Nassau reads its breakpoint ladder there, and `weatherbot
> replay` shares the notes. `engine/changes.py`'s unfinished sentence is
> finished. Closes issue #44.

**Branch:** `feature/phase07-step7-replay`

**Deploys:** nothing beyond merge — the operator's copy takes this step at
Step 9.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.86/1M           | $6.13/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.72/1M           | $6.76/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | XHigh              | XHigh              |
|               | AA       | ≈45.2              | 51                 | 52.4               |
|               | Price    | $2.31/1M           | $4.00/1M           | $17.73/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels.

> Ran 2026-11-04: Balanced Pick / Quality Runner-up — Gemini 4 Argon · High.

**Conversation:** New

**Model rationale:** Step 7 is coding with a multimodal secondary category — a
cache, two routes, a component extraction that must not change the dashboard,
and a page whose result must be looked at — at High complexity, not novel:
Decisions 16 and 17 fix the shape, and the goldens fix the answer. On the step
alone, the Balanced Pick fits best: Gemini 4 Argon on Antigravity at Effort
High, with Thinking On, is strong at broad UI work on a fixed contract. The
Quality Pick, Opus 5.5 at XHigh, adds audit depth that a read-only,
golden-checked feature needs less, and the Cost Pick, GPT-6.1 Sol at High, saves
money with less eye for the page. The conversation is new, per phase-boundary
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
       feature/phase07-step7-replay`
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
       Phase 7 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 7`
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

    THIS STEP serves an assessment of the operator's own location
    against a past storm, to the operator's own page, so its answers
    hold what `/api/assessments` holds and go nowhere else. Both
    routes are sync reads under the existing guards, name the location
    in a query, and answer a generic 404 for an unknown storm,
    advisory, or name, echoing nothing. Replay writes nothing: a test
    counts every table before and after a whole scrub, and asserts no
    `HubEvent` and no notification. The web layer imports
    `services.replay`, never `weatherbot.engine`, which the layers
    contract holds. The corpus is read only through `ReplayCorpus`,
    whose path and checksum rules stand. No AI block appears on this
    page, and nothing here reaches Anthropic.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 7 (Depth). Step 7: replay in
    the UI.

    Current state (as of Phase 6, post-Phase-7 Step 6):

    - `services/replay.py`: `ReplayCorpus` (`storms`, `advisories`,
      `snapshot`, `snapshots`), `ReplayService.timeline(atcf_id,
      location, thresholds)`, and `without_evacuation_order`. Measured
      2026-11-03: Dorian's 117 advisories in 5.6 s, Irma's 84 in 4.3
      s, one snapshot in 53 ms, an assessment's JSON about 5 KB.
    - `cli/replay.py`: `_step`, `transitions`, and `_notes` (the
      toggle, the windows that do not cover a location, the inputs
      replay lacks), which the web layer cannot import, because `cli`
      sits above `web`.
    - `web/routes/replay.py` declares
      `/api/replay/{atcf_id}/{advisory}`, so `/timeline` must be
      declared before it. `web/routes/assessments.py`'s private
      builders (`_evidence_response`, `_official_response`,
      `_wind_response`, `_threat_response`, `_unavailable_response`,
      and `change_responses`) back `stored_assessment_to_response`;
      `StoredAssessmentResponse` requires an `id` and `stored_at`,
      which a replay does not have. `WebState.corpus` is the opened
      corpus or `None`; advisory ids in the corpus are zero-padded,
      such as `026`.
    - `Dashboard.tsx`'s `LocationLevelCard` renders the level, the
      rule, the evidence, the official products, and the threat table
      inline, at about 380 lines. `MapView.tsx` keeps its picker;
      `frontend/e2e/map.spec.ts` drives it; `useLeafletMap` takes
      `mapData`, `visibility`, and `viewModeKey`;
      `frontend/src/map/AdvisorySlider.tsx` came with Step 5 and
      `frontend/src/charts/LevelHistoryChart.tsx` with Step 6.
    - `AppShell.tsx`'s `NAV_ITEMS` must keep `/timeline`, `/ask`, and
      `/settings` in that order (Phase 6's check 40), and
      `AppShell.test.tsx` pins seven labels. `scripts/serve_demo.py`
      opens `tests/fixtures/replay` by default, with both landmarks
      stored.
    - The goldens (`tests/golden/replay/`): Dorian at Nassau, 1 at 1,
      3 at 8, 2 at 12, 4 at 24 (`HWA`), 5 at 26 (`HWR`), 4 at 41A
      (`TWR`), 1 at 44; Irma at Miami-Dade, 4 at 34, 5 at 36, 4 at 48,
      2 at 49, 1 at 51.
    - Issue #44's sentence lives in `engine/changes.py`; `ChangeRef`
      carries no sentence, so no AI request or recording changes, no
      golden quotes it, and
      `frontend/src/test/fixtures/timeline.json`, which does,
      regenerates with `scripts/export_api_fixtures.py`. A replay
      snapshot holds no `breakpoints` (`services/replay.py`), so
      `engine/official.py` names no segment ends: the evidence at
      Dorian 026 reads "NHC Hurricane Warning (HWR) segment for
      Dorian, advisory 26: ...". Adding a catalogue would change the
      engine's inputs, so the page shows what the evidence holds.

    Files to read (every file before drafting):

    - docs/roadmap/phase07-roadmap.md (Decisions 1, 16, 17, and 19,
      and this step).
    - src/weatherbot/services/replay.py and cli/replay.py.
    - src/weatherbot/web/routes/replay.py, routes/assessments.py, and
      schemas.py.
    - src/weatherbot/engine/changes.py and its tests.
    - frontend/src/pages/Dashboard.tsx and Dashboard.test.tsx,
      src/map/MapView.tsx, src/map/useLeafletMap.ts,
      src/map/AdvisorySlider.tsx, src/app/AppShell.tsx, and
      src/app/routes.tsx.
    - frontend/e2e/map.spec.ts and scripts/serve_demo.py.
  </context>

  <goal>
    Add the timeline cache and two routes, extract the assessment
    components, build the `/replay` page, prove Dorian's ladder at
    Nassau there, and finish issue #44's sentence.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `services/replay.py`: `ReplayTimelines(corpus, thresholds, *,
      max_size=8)` with `timeline(atcf_id, location) ->
      tuple[ReplayStep, ...]`, keyed by the storm, the ruleset's
      fingerprint, and the location's name, point, and polygon, so
      that a location removed and re-added elsewhere never reads
      another's timeline; it applies `without_evacuation_order`,
      computes once under a per-key lock so that two requests do not
      both compute, and evicts least recently used.
      `replay_notes(location, steps)` moves here from `cli/replay.py`,
      which imports it, so its output is unchanged.
    </requirement>

    <requirement>
      `GET /api/replay/{atcf_id}/timeline?location=`, declared before
      `/{advisory}`: `ReplayTimelineResponse` (`atcf_id`, `name`,
      `location`, `notes`, `steps`, and the disclaimer's `notice`,
      because AGENTS.md puts it on every assessment surface), each
      step holding the corpus's advisory id, the printed advisory,
      `issued_at`, `level`, `rule`, `rule_trigger`, `complete`,
      `official_codes`, and `changes`. `GET
      /api/replay/{atcf_id}/{advisory}/assessment?location=`:
      `ReplayAssessmentResponse`, whose nested models are the live
      ones, built by the same builders, which
      `web/routes/assessments.py` exposes, with `origin: "replay"`,
      the `notice`, no `id`, and no `stored_at`. Both are sync routes;
      a first timeline takes seconds in a worker thread, which the
      page shows.
    </requirement>

    <requirement>
      `GET /api/replay/{atcf_id}/{advisory}` stops passing the latest
      live assessments to `build_map_response`, so that a location's
      marker shows no present-day level beside the scrubbed one; a
      replay marker has no level. `frontend/e2e/map.spec.ts` counts
      markers, not levels, so it still passes.
    </requirement>

    <requirement>
      `frontend/src/assessment/`: `LevelSummary.tsx`,
      `EvidenceList.tsx`, `OfficialProductList.tsx`, and
      `ThreatTable.tsx`, extracted from `LocationLevelCard` and typed
      on the shared generated models, so that `Dashboard.tsx` renders
      exactly what it rendered: its tests pass unchanged apart from
      imports. The AI panel, the evacuation switch, and the sparkline
      stay in the dashboard's card.
    </requirement>

    <requirement>
      `frontend/src/pages/Replay.tsx`, at `path: "replay"`, with
      navigation "Replay" after "Map" (`AppShell.test.tsx`'s labels
      follow; `/ask` stays between `/timeline` and `/settings`): a
      storm picker, a location picker (stored locations; none stored
      says so), `LevelHistoryChart` over the advisories with a marker
      at the current step, `AdvisorySlider` over the steps, "Play"
      (one step every 1.5 seconds, stopping at the end, on any input,
      and when the tab is hidden, with no timer otherwise), the map
      from `useLeafletMap` over `/api/replay/{atcf_id}/{advisory}`
      with the layers a replay holds, the level, the evidence, the
      official products, and the threats from
      `frontend/src/assessment/`, the changes at that step, and
      `notes`. A banner that cannot be dismissed reads "Replay:
      <storm> advisory <n>, issued <instant> — not live". There is no
      AI panel, and the evacuation switch is absent. With no corpus
      (`health.corpus` false) the page says what to set: `[web]
      corpus` naming a checkout's `tests/fixtures/replay`, or a
      `convert --full` directory. `MapView`'s picker stays, and
      `frontend/e2e/map.spec.ts` passes unchanged.
    </requirement>

    <requirement>
      Issue #44: `engine/changes.py` writes `..., whose cone does not
      cover the location.` The event stays informational, so no
      notification golden changes; confirm with `git diff --stat
      tests/golden/` that it is empty, and that the engine's
      digest-pinned goldens, which hold change kinds, are unchanged.
    </requirement>

    <requirement>
      Tests: `tests/services/test_replay_timelines.py` (one
      computation for two requests, eviction, a moved location,
      `replay_notes`), `tests/web/test_replay_scrub.py` (every step of
      Dorian at Parliament Square and Irma at Miami-Dade County Hall
      equals its golden through the API; the assessment at Dorian 026
      reads level 5 by `hurricane_warning` from a
      `watch_warning_segment` with code `HWR`; 404s echo nothing; the
      route order), `tests/web/test_replay_writes_nothing.py` (table
      counts before and after, no event, no notification), new routes
      in `tests/web/test_api_privacy.py`,
      `frontend/src/pages/Replay.test.tsx`, a test per extracted
      component where the dashboard's did not cover it, and
      `frontend/e2e/replay.spec.ts` (Dorian at Parliament Square:
      slide to advisory 024 and read Level 4, to 026 and read Level 5,
      with the segment's `HWR` in the evidence and the banner up; no
      request to Anthropic and no `notification` event).
      `scripts/export_api_fixtures.py` adds `replay-timeline.json` and
      `replay-assessment.json`, and `docs/api/openapi.json` and
      `schema.d.ts` regenerate.
    </requirement>

    <requirement>
      `README.md`'s dashboard section and `CHANGELOG.md` describe the
      page; `docs/phase03-qa-findings.md`'s Phase 7 line is honoured
      by Decision 17, which `README.md` states in one line.
    </requirement>

    <requirement>
      Filepath comment: every new Python, TypeScript, YAML, or
      Markdown file gets its repository-relative path as its first
      line where the file type accepts comments, matching the sibling
      files.
    </requirement>
  </requirements>
</task>
```

### Step 7 acceptance criteria

- Through `GET /api/replay/{atcf_id}/timeline`, every step of Dorian 2019 at
  Parliament Square and Irma 2017 at Miami-Dade County Hall equals its golden.
- In the scrubber, Dorian at Parliament Square reads level 4 at advisory 24 and
  level 5 at 26, from NHC's watch-warning segments (`HWA`, then `HWR`) shown in
  the evidence, with the banner up.
- A timeline computes once for concurrent requests, and a location moved and
  re-added never reads the old timeline.
- A whole scrub changes no table, publishes no event, and sends no notification.
- `frontend/src/assessment/` serves the dashboard and the replay page; the
  dashboard's tests pass with imports alone changed.
- With no corpus, the page says what to set; `weatherbot replay`'s output is
  unchanged.
- Issue #44's sentence is complete, and no golden moved.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean
  (ESLint with `eslint-plugin-security` at no warnings), dependency audit clean
  — and replay stays read-only per the project roadmap's "Security & privacy
  strategy": nothing stored, sent, or published, and no route echoes its input.

---

## Step 8 — The report

**Status:** Not started

> **Goal:** Give the operator something safe to hand to someone.
> `src/weatherbot/services/report.py` builds `ReportData` from
> `briefing_context`, the model Phase 6 proved may leave the machine, plus each
> location's chosen name and level history, and its stored briefing only when
> asked for, and `render_report(data) -> str` writes one self-contained HTML
> file: inline CSS, an inline SVG sparkline, no script, no remote resource, a
> `<meta>` CSP of its own, every value escaped, and print styles. `GET
> /api/report?location=&briefing=` answers it as a download, `weatherbot report
> [LOCATION] --out PATH [--with-briefing]` writes it, and the dashboard links
> it.

**Branch:** `feature/phase07-step8-report`

**Deploys:** nothing beyond merge — the operator's copy takes this step at
Step 9.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Codex              | Antigravity        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 50.2               | 52.6               | 56                 |
|               | Price    | $2.86/1M           | $6.13/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Claude Code        | Antigravity        |
|               | Level    | XHigh              | High               | High               |
|               | AA       | 51.9               | 53.6               | 52.6               |
|               | Price    | $3.72/1M           | $6.76/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6.1 Sol**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | XHigh              | XHigh              |
|               | AA       | ≈45.2              | 51                 | 52.4               |
|               | Price    | $2.31/1M           | $4.00/1M           | $17.73/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels.

> Ran 2026-11-04: Balanced Pick / Quality Runner-up — Gemini 4 Argon · High.

**Conversation:** New

**Model rationale:** Step 8 is coding with a knowledge secondary category at
High complexity, not novel: a renderer is simple, but it is the phase's one
artifact meant to leave the operator's hands, and Decision 18 fixes what it may
hold. On the step alone, the Balanced Pick fits best: Gemini 4 Argon on
Antigravity at Effort High, with Thinking On, handles print and page layout
well, and the privacy rule is carried by reusing Phase 6's model, not by
judgement. The Quality Pick, Opus 5.5 at XHigh, would add audit depth to the
same rule at higher cost, and the Cost Pick, GPT-6.1 Sol at High, trades away
some eye for the printed page. The conversation is new, per phase-boundary
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
       feature/phase07-step8-report`
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
       Phase 7 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 7`
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
       complete. You can now move
       on to Step 9." That
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
       one before Step 9.
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

    THIS STEP writes the only artifact made to be shared, so the data
    classification's line governs it: coordinates are "redacted from
    exports", and the token is too. The report reads
    `briefing_context`'s model, never `Evidence.detail`,
    `OfficialProduct.reason`, `Location.display_name`, a zone id, a
    URL of an NWS query, a polygon, a path, or a setting; a test scans
    the whole file for both landmarks' coordinates at two or more
    decimals, their display names, their zones, each assessment's
    kilometre figures, and a fake ntfy token and topic. Every value
    passes `html.escape`, with a test holding `<script>`, an event
    attribute, and a quote in a location name, an official title, and
    AI text. The file holds no `<script>`, `<link>`, `<img>`,
    `<iframe>`, `<object>`, or `<base>`, and its `<meta>` CSP is
    `default-src 'none'; style-src 'unsafe-inline'`, which is safe
    here because the file holds no script and no remote resource. The
    route serves it as an attachment with `Content-Security-Policy:
    default-src 'none'; style-src 'unsafe-inline'; sandbox`, so it
    never runs in the app's origin. It is a read, under the guards'
    cross-site refusal. `report --out` refuses to overwrite without
    `--force`. A report holds no AI text and no forecast office unless
    the briefing is asked for: a test stores
    `eval-briefing-recorded-miami-dade.sse`'s text for a neutrally
    named location at the Miami-Dade landmark, and asserts that
    `Miami`, `Dade`, `MFL`, and the alert's `areaDesc` appear nowhere
    in the default report. Asked for, only a stored, unwithheld
    briefing appears, and always with its label.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 7 (Depth). Step 8: the
    report.

    Current state (as of Phase 6, post-Phase-7 Step 7):

    - `services/ai/context.py`: `briefing_context(assessment, changes,
      snapshot, stale=())` returns `BriefingContext` (`location`,
      `as_of` to the hour, `level`, `rule`, `trigger`, `complete`,
      `unavailable`, `evidence`, `official`, `wind_probabilities`,
      `threats`, `changes`, `stale_sources`, `sources`, and `noaa`).
      With `snapshot=None`, it holds no NOAA text, and the report
      wants none. `distance_band`, `compass8`, `to_hour`, and
      `whole_hours` are public. The module imports no I/O and no SDK;
      Phase 6's check 14 holds that, so `report.py` imports it and
      never the reverse.
    - `services/ai/outputs.py`: `OutputRepository`,
      `latest_briefing(location)`, and `StoredOutput`.
      `services/ai/briefing.py` says how a briefing is stale and
      `frontend/src/ai/AiLabel.tsx` how it is labeled: the model's
      display name, the time, and "AI-generated · may be wrong · the
      level above comes from official products".
      `services/ai/display.py`'s `public_page` gives a source's public
      link. `tests/ai/test_ai_imports.py` proves a non-AI command
      never loads the SDK, so neither may `weatherbot report` nor `GET
      /api/report`.
    - `services/disclaimer.py`: `NOTICE` and `ESSENTIALS`. The full
      `DISCLAIMER.md` holds `162.400-162.550 MHz`, which a coordinate
      scan would trip, so the report ends with `ESSENTIALS` and
      `DISCLAIMER_URL`.
    - `AssessmentRepository.level_points` (Step 6) reads a location's
      level history; `frontend/src/charts/scale.ts` is the sparkline's
      shape, which Python mirrors as one small function with its own
      test.
    - `web/guards.py`'s `SecurityHeadersMiddleware` keeps a route's
      own `Content-Security-Policy` and adds the fixed headers.
      `Sec-Fetch-Site: same-origin` passes the guard for a link on the
      page.
    - Phase 3's check 8 requires unique test basenames, and
      `services/` and `web/` cannot both hold `test_report.py`. Phase
      1's check 10 forbids `tests/test_reports.py`, one of version 1's
      paths.

    Files to read (every file before drafting):

    - docs/roadmap/phase07-roadmap.md (Decisions 15, 18, and 19, and
      this step).
    - src/weatherbot/services/ai/context.py, outputs.py, briefing.py,
      and display.py.
    - src/weatherbot/services/disclaimer.py and
      persistence/repositories.py.
    - src/weatherbot/web/guards.py and routes/assessments.py.
    - src/weatherbot/cli/brief.py and __init__.py (the output and
      exit-code patterns).
    - frontend/src/ai/AiLabel.tsx, src/pages/Dashboard.tsx, and
      src/charts/scale.ts.
    - tests/web/test_api_privacy.py and tests/cli/test_cli_privacy.py.
  </context>

  <goal>
    Add the report's model, renderer, route, command, and link, and
    prove that it opens offline, prints to PDF, carries the disclaimer
    and the AI labels, and holds nothing that locates the operator.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `services/report.py`: `ReportService(engine, *, now)` with
      `build(location=None, *, with_briefing=False) -> ReportData`
      (every stored location when none is named, in name order; each
      from `AssessmentRepository.latest` through
      `briefing_context(..., snapshot=None)`, falling back to no
      evidence detail rather than failing on `ContextTooLarge`, and
      the location's `level_points`; with `with_briefing`, also
      `OutputRepository.latest_briefing`, kept only when not withheld,
      marked stale when it was written for an older assessment), and
      `render_report(data) -> str`. It reads stored rows only and
      writes nothing. `ReportData` holds no `Location`: a location's
      name is the only field it takes from one.
    </requirement>

    <requirement>
      The file: a `<title>`; the notice at the top; for each location
      its name, level and label, actions, trigger, the assessment's
      hour, and "at least" when incomplete; the evidence and official
      products as their titles, issuing agency, and hours (`NWS` or
      `NHC`, read from the source id, never `OfficialRef.issuer` or
      `SourceRef.issuer`, which name the forecast office); the wind
      bands; each storm's distance band, 8-point bearing, closest
      approach to the hour, and arrival words; recent changes;
      unavailable inputs and stale sources; the level history as an
      inline `<svg>` with a text alternative; when asked for, the
      briefing's sections beneath an "AI briefing · <model> · written
      <time> · may be wrong" label reading as `AiLabel` does, with a
      stale note and its sources; and at the end the generation time,
      `ESSENTIALS`, and `DISCLAIMER_URL`. Inline CSS for screen and
      `@media print` (no page break inside a location's heading, black
      on white). Links are only `public_page`'s `https` URLs, each
      `rel="noopener noreferrer"`.
    </requirement>

    <requirement>
      `GET /api/report?location=&briefing=` in `web/routes/report.py`:
      a sync route answering `text/html; charset=utf-8` with
      `Content-Disposition: attachment;
      filename="weatherbot-report-<YYYYMMDDTHHMMZ>.html"` and the CSP
      this step's security block names, 404 for an unknown name
      without echoing it, and 409 when no assessment is stored. In
      `docs/api/openapi.json` it is `text/html`.
    </requirement>

    <requirement>
      `cli/report.py`: `weatherbot report [LOCATION] --out PATH
      [--force] [--with-briefing]`, registered as
      `app.command("report")`, writing the file with a temporary file
      and `os.replace`, refusing an existing file without `--force`
      and a missing parent directory with exit 2, and printing the
      path and the disclaimer's notice. It never loads the SDK
      (`tests/ai/test_ai_imports.py` gains the case).
    </requirement>

    <requirement>
      The page: "Export report" beside each location card and for all
      locations on the dashboard, as `<a
      href="/api/report?location=..." download>`, with a line saying
      what it holds and that it opens anywhere and prints to PDF from
      the browser, and an unticked "Include the AI briefing" box
      saying that its words quote NWS alerts and can name a county or
      a forecast office.
    </requirement>

    <requirement>
      Tests (basenames checked):
      `tests/services/test_report_render.py` (a location at each level
      from the scenarios; an incomplete assessment; a stale and a
      withheld briefing; none stored; no AI at all; the SVG; no
      forbidden tag, through `html.parser`),
      `tests/services/test_report_privacy.py` (the scan the security
      block lists, over a level-5 assessment with its distances,
      zones, and a stored briefing, by default and with the briefing
      asked for), `tests/services/test_report_escape.py`,
      `tests/web/test_api_report.py` (headers, CSP, attachment,
      `briefing=true`, 404, 409, cross-site refusal, and
      `test_api_privacy`'s scan), `tests/cli/test_report_command.py`
      (a file, no overwrite, `--force`, `--with-briefing`, a missing
      parent, no SDK), and `frontend/e2e/report.spec.ts`, which ticks
      the briefing box, downloads the report through the guarded page,
      then opens the saved file in a second `browser.newContext({
      offline: true })` outside the guard, continuing only that
      `file:` URL and failing any other request, so the document is
      the one request made; it sees the disclaimer and the AI label,
      and `page.pdf()` returns bytes beginning `%PDF`.
    </requirement>

    <requirement>
      `README.md`'s Commands and dashboard sections and `CHANGELOG.md`
      describe the report, say what it leaves out, and say PDF is the
      browser's print. `report` takes no `--json`, so `DOCUMENTS`
      stays at Step 4's count.
    </requirement>

    <requirement>
      Filepath comment: every new Python, TypeScript, YAML, or
      Markdown file gets its repository-relative path as its first
      line where the file type accepts comments, matching the sibling
      files.
    </requirement>
  </requirements>
</task>
```

### Step 8 acceptance criteria

- The exported file opens offline with no request beyond the file itself, and
  carries the notice, `ESSENTIALS`, each location's level, and the AI label on
  any AI text.
- A privacy scan over a level-5 report finds no landmark coordinate at two or
  more decimals, no display name, no zone id, no raw distance, no URL of a
  query, and no ntfy token or topic; without the briefing it names no forecast
  office or county.
- Markup in a location name, an official title, or AI text is escaped; the file
  holds no script, external resource, or embedded frame.
- `GET /api/report` answers an attachment with its own sandboxed CSP; a
  cross-site request is refused.
- `weatherbot report --out PATH` refuses to overwrite without `--force` and
  never loads the SDK.
- The briefing appears only when asked for; a withheld one is absent; a stale
  one says so; with no AI at all the report is complete without it.
- Chromium's `page.pdf()` renders the report to a PDF.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — and the report satisfies the project roadmap's data
  classification: the operator's coordinates and the ntfy token are absent from
  the export.

---

## Step 9 — The whole phase on the operator's machine

**Status:** Not started

> **Goal:** Prove the phase end to end and put it in the operator's hands.
> `frontend/e2e/phase7.spec.ts` walks one flow across every new surface with no
> network: search and add a place, read the channels, set quiet hours, read the
> retention plan, turn on each layer, step the slider, read the charts, scrub
> Dorian at Parliament Square, and export a report. `screens.spec.ts` gains the
> new pages, `scripts/measure_idle.py` holds its budgets with the new surfaces
> mounted, each new alarm is injected and seen, and the operator's service takes
> the phase, with Nassau beside their own location, the corpus configured, the
> phone buzzing, and a storm scrubbing.

**Branch:** `feature/phase07-step9-smoke-deploy`

**Deploys:** the operator's machine → with the operator's yes to each exact
action, and away from HH:25: `schtasks /End`, `npm ci` and the build, `uv tool
install --reinstall --from <checkout> weatherbot`, and `/Run`;
`http://127.0.0.1:8765/api/health` must answer with the new `ui.index_sha256`
and the database at head, `corpus` true, and the installed `doctor --json` must
pass `web`, `migrations`, `ntfy`, `ai`, and `heartbeat`. GitHub Actions → the
first `ci.yml` and `phase-verify.yml` runs on `main` must be green.

Settings — ladder (`roadmodel ladder --category agentic --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Sonnet 5.5**     | **Opus 5.5**       |
|               | Platform | Codex              | Claude Code        | Claude Code        |
|               | Level    | Medium             | XHigh              | XHigh              |
|               | AA       | 47.8               | 51.9               | 56                 |
|               | Price    | $2.50/1M           | $3.72/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **GPT-6.1 Sol**    | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Codex              | Antigravity        |
|               | Level    | High               | XHigh              | High               |
|               | AA       | 46.8               | 51                 | 52.6               |
|               | Price    | $3.40/1M           | $4.00/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **Gemini 4 Argon** | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Antigravity        | Codex              |
|               | Level    | Low                | Medium             | XHigh              |
|               | AA       | ≈45.2              | ≈49.8              | 52.4               |
|               | Price    | $2.31/1M           | $2.37/1M           | $17.73/1M          |

Ranked for agentic, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels.

**Conversation:** New

**Model rationale:** Step 9 is agentic with a coding secondary category — a long
end-to-end run, a ten-minute measurement, injected failures, and an on-machine
deployment that pauses for the operator — at High complexity, not novel. On the
step alone, the Balanced Pick fits best: Sonnet 5.5 on Claude Code at Effort
XHigh (it always thinks, so there is no Thinking dial) sustains a long,
tool-heavy session well at a fraction of the Quality Pick's price, and the risky
decisions were made in earlier steps. The Quality Pick, Opus 5.5 at XHigh, adds
judgement if the deployment turns up something new, and the Cost Pick, GPT-6.1
Sol at Medium, has less margin for a flaky end-to-end run. The conversation is
new, per phase-boundary hygiene.

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
       feature/phase07-step9-smoke-deploy`
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
       Phase 7 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 7`
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
       shape "Step 9 is
       complete. You can now move
       on to Step 10." That
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
       one before Step 10.
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

    THIS STEP touches the operator's real service, so its limits are
    Phase 6's: the agent reads only `/api/health`, `doctor`'s results,
    the count of locations, and delivery results, never a coordinate,
    a place, an assessment of it, a topic, or a token. Each deployment
    action is confirmed first, by name. The operator edits their own
    `weatherbot.toml` for `[web] corpus`, and adds Nassau themselves,
    or says yes to the exact command, since Nassau is public. Alarm
    injection happens only in a temporary data directory with a fake
    token against a local stub, never against the operator's server.
    The smoke's guard fails on any unexpected origin, CSP violation,
    or coordinate in the console, and the new specs add no exception.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 7 (Depth). Step 9: the whole
    phase on the operator's machine.

    Current state (as of Phase 6, post-Phase-7 Step 8):

    - `frontend/e2e/` holds `dashboard`, `map`, `screens`, `idle`,
      `ai`, and each of Steps 2 and 5 to 8's specs; `guard.ts` fails
      on unexpected origins, CSP violations, coordinates, and AI text
      in the console; `playwright.config.ts` starts demonstration
      servers on 8799, 8800, and 8801, and Phase 6's check 42 reads
      those three ports.
    - `scripts/serve_demo.py` serves a temporary database with both
      landmarks, the recorded snapshot, the simulated advisory, the
      corpus, and recorded AI answers. Step 2 taught it the recorded
      Nominatim answers, and Step 5 the synthetic surge.
    - `scripts/measure_idle.py` runs `serve_demo.py` and a headless
      Chromium for 600 seconds, requires `/api/ai` ready with change
      summaries on, and prints a line holding `budget=<0.5%`,
      `ai_state=ready`, and `change_summaries=on`, which Phase 6's
      `--post` reads. Phase 6's close measured 0.2500% and 0.0026%.
    - The operator's copy took Steps 2 and 3 (revision 0009). Steps 4
      to 8 are on `main` only, and revision 0010 (Step 4) runs at the
      reinstalled copy's first start, after its backup. The running
      task keeps `pythonw.exe` holding the tool's files, so `/End`
      comes first, and `\Weatherbot\check` runs at HH:25. Deploy
      recipe: memory `weatherbot-phase06-smoke-conventions`.
    - The health signals this phase added: `doctor`'s `ntfy` check and
      `GET /api/notifications/channels` (Step 3), the `retention`
      watch heartbeat and `GET /api/retention` (Step 4), and the map's
      "Radar unavailable" state (Step 5).

    Files to read (every file before drafting):

    - docs/roadmap/phase07-roadmap.md (the Deploy-and-verify rule,
      Decisions 8 and 19, and this step).
    - frontend/e2e/ (every spec), playwright.config.ts, and guard.ts.
    - scripts/serve_demo.py and scripts/measure_idle.py.
    - docs/NOTIFICATIONS.md and the project roadmap's runbooks.
    - Memories `weatherbot-phase06-smoke-conventions` and
      `weatherbot-phase05-browser-smoke-conventions`.
  </context>

  <goal>
    Add the whole-phase smoke, hold the idle budget, inject and see
    each alarm, and upgrade the operator's service with their yes.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `frontend/e2e/phase7.spec.ts`, one flow on the demonstration
      server with no network: search for `Nassau, Bahamas` (the
      recorded answer), add it, and see its card read as outside NWS
      coverage; open the channel view; save quiet hours and see them
      applied in `/api/settings`; read the retention plan; turn on
      every map layer in turn, with `nowcoast.noaa.gov` fulfilled by
      the blank tile, and then see "Radar unavailable" with that route
      aborted; step the slider (writing the switch file itself, so
      that no spec depends on another's order); read the sparkline and
      the wind chart; scrub Dorian at Parliament Square to advisory
      026; and export the report. `screens.spec.ts` adds `/replay` and
      the new settings sections at desktop and phone widths in both
      themes. A failure screenshot goes to `frontend/test-results/`.
    </requirement>

    <requirement>
      `scripts/measure_idle.py` keeps its tokens and budgets: 600
      seconds, under 0.5 percent of a core on each side, 0 roster
      polls, and 0 cycles, with the dashboard (charts mounted) and
      with `RetentionWorker` running: `serve_demo.py --retention-days
      30`, which `measure_idle.py` passes, writes the demonstration's
      `weatherbot.toml` (an environment variable would make `PUT
      /api/settings` refuse the key). The window stays on `/`, which
      mounts no map, so the overlay rule is proved by `layers.spec.ts`
      and `phase7.spec.ts`, not here. Record the line in the PR body;
      Step 10 copies it into the QA ledger.
    </requirement>

    <requirement>
      Alarms, each injected and seen: (a) ntfy: a throwaway data
      directory, a local stub answering 401, and a fake token: `notify
      test` exits 1, `doctor`'s `ntfy` fails naming the runbook, and
      `GET /api/notifications/channels` reads `failed`. (b) retention:
      a worker whose run raises records a failed heartbeat, and a
      heartbeat aged past its cadence reads stale in `doctor` and on
      the dashboard. (c) overlays: the smoke's aborted route shows the
      unavailable state. (d) a settings file that stops parsing logs
      one WARNING and the next cycle still runs. Each has a test;
      `tests/services/test_phase7_alarms.py` holds (a), (b), and (d).
    </requirement>

    <requirement>
      Deploy (Stage 4), after the operator's yes to each exact action,
      away from HH:25: stop the task, `npm ci` and build, reinstall,
      and run; read `/api/health`. Then ask the operator to set `[web]
      corpus` to their checkout's `tests/fixtures/replay` and restart
      the task; to add Nassau (from the page, or by the exact
      `locations add` command, with their yes); to run the installed
      `notify test`; to scrub Dorian at Nassau on `/replay`; and to
      export a report. Each answer comes back as yes or no, and no
      value is read. If the operator reports a page that looks wrong,
      it is a finding with a destination, not a note.
    </requirement>

    <requirement>
      `README.md`'s Status stays in progress here (Step 10 closes it);
      `CHANGELOG.md` records the step. A finding from the operator's
      walk-through is fixed here if it blocks a criterion, and is
      otherwise an issue with a number.
    </requirement>

    <requirement>
      Filepath comment: every new Python, TypeScript, YAML, or
      Markdown file gets its repository-relative path as its first
      line where the file type accepts comments, matching the sibling
      files.
    </requirement>
  </requirements>
</task>
```

### Step 9 acceptance criteria

- `frontend/e2e/phase7.spec.ts` passes on Ubuntu CI with no unexpected origin,
  CSP violation, or coordinate in the console.
- `screens.spec.ts` covers `/replay` and the new settings sections at both
  widths in both themes.
- `measure_idle.py` holds under 0.5 percent of a core on each side over 600
  seconds, with 0 polls and 0 cycles, and with the retention worker running.
- Each alarm was injected and seen: a failed ntfy delivery in `doctor` and the
  channel view, a failed and a stale retention heartbeat, the overlay's
  unavailable state, and a settings file that stopped parsing.
- **Deployed & verified:** `GET http://127.0.0.1:8765/api/health` answers from
  the reinstalled copy with the new `ui.index_sha256`, the database at head, and
  `corpus` true; the installed `doctor --json` passes `web`, `migrations`,
  `ntfy`, `ai`, and `heartbeat`, with only the known `path` finding; the
  operator confirms that Nassau reads beside their location, the phone buzzed,
  Dorian scrubbed to level 5 at advisory 26, and a report opened offline; and
  the first `ci.yml` and `phase-verify.yml` runs on `main` are green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — and the deployment read no coordinate, place, topic,
  or token, per the project roadmap's "Security & privacy strategy".

---

## Step 10 — QA & Verification Script

**Status:** Not started

> **Goal:** Package the verification matrix into `scripts/verify_phase07.py`
> (with `--fast`, `--py`, `--node`, `--ui`, `--live`, `--security`, `--all`, and
> `--post` modes), produce `docs/phase07-qa-findings.md`, add `"07"` to the
> `phase-verify.yml` matrix beside `"01"` to `"06"`, and close the phase. The
> script reads every Step 1 through Step 9 deliverable with standard-library
> static checks and builds the V1–V10 matrix from JUnit evidence: the offline
> pytest run with its coverage floors, the frontend's commands and Vitest run,
> and the Playwright run; in `--post` on the operator's machine it adds Phase
> 6's own `--post` sweep, the operator's service, and the idle measurement. The
> closure marks Phase 7 complete in both roadmaps and in `README.md`, names the
> checks Phase 8 must keep or convert, and tags `v2.0.0-phase-7`.

**Branch:** `feature/phase07-step10-verify`

**Deploys:** GitHub Actions → `phase-verify (07)` runs on every push and pull
request from the merge on, under the required aggregate `phase-verify`; its
first run on `main` must be green, and the annotated `v2.0.0-phase-7` tag must
peel to the merge commit.

Settings — ladder (`roadmodel ladder --category coding --complexity medium`):

|               |          | Cost                 | Balanced             | Quality            |
| ------------- | -------- | -------------------- | -------------------- | ------------------ |
| **Pick**      | Model    | **Gemini 3.8 Flash** | **GPT-6.1 Sol**      | **Gemini 4 Argon** |
|               | Platform | Antigravity          | Codex                | Antigravity        |
|               | Level    | Medium               | High                 | High               |
|               | AA       | 39.8                 | 50.2                 | 52.6               |
|               | Price    | $1.90/1M             | $2.86/1M             | $6.13/1M           |
| **Runner‑up** | Model    | **GPT-6.1 Sol**      | **Sonnet 5.5**       | **Opus 5.5**       |
|               | Platform | Codex                | Claude Code          | Claude Code        |
|               | Level    | Low                  | High                 | High               |
|               | AA       | 42.1                 | 46.8                 | 53.6               |
|               | Price    | $2.35/1M             | $3.40/1M             | $6.76/1M           |
| **Backup**    | Model    | **Sonnet 5.5**       | **Gemini 3.8 Flash** | **GPT-6.1 Sol**    |
|               | Platform | Claude Code          | Antigravity          | Codex              |
|               | Level    | Medium               | High                 | High               |
|               | AA       | 40.8                 | 40.9                 | 50.2               |
|               | Price    | $3.18/1M             | $2.98/1M             | $2.86/1M           |

Ranked for coding, medium complexity. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level.

**Conversation:** New

**Model rationale:** Step 10 is coding with an agentic secondary category at
Medium complexity, not novel: a mechanical translation of this roadmap's
acceptance criteria into a verification script, a matrix entry, and a findings
rollup, on a template five phases old. On the step alone, the Balanced Pick fits
best: GPT-6.1 Sol on Codex at Intelligence High handles a long, enumerated
translation reliably at a moderate price. The Quality Pick, Gemini 4 Argon at
High, has depth a known pattern does not need, and the Cost Pick, Gemini 3.8
Flash at Medium, has less margin over 65 checks and their mutation cases. The
conversation is new, per phase-boundary hygiene.

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
       feature/phase07-step10-verify`
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
       Phase 7 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 7`
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
       shape "Step 10 is
       complete. Phase 7 is
       complete. You can now move
       on to Phase 8." That
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
       one before Phase 8.
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

    THIS STEP AUTHORS the `--security` verify mode, so its own diff
    must still pass the gate before commit. `--security` runs
    gitleaks, bandit, `pip-audit --strict`, the personal-data check,
    `npm audit --audit-level=high`, ESLint at no warnings, and a scan
    for key and `tk_` shapes over the phase's paths. `--post` reads
    the operator's service only through `/api/health`, `doctor`, and
    delivery results, and says so before it starts; its nested
    `verify_phase06.py --post` runs that phase's live AI eval, so
    `--post` states its cost (about $0.40) and asks first. No check
    prints a coordinate, a topic, or a token. The `"07"` Node steps
    use the same pinned `actions/setup-node` SHA with its version
    comment.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 7 (Depth). Step 10: QA +
    verification script.

    Steps 1 through 9 have been implemented. Now create the
    verification script, the QA findings document, and the CI matrix
    update, and close the phase.

    Reference scripts (pattern templates):

    - scripts/verify_phase06.py (the structural precedent: 51 static
      checks, nine modes, V rows from JUnit reports in which every
      selection must match a test, a failure fails, and a skip is
      never a pass, the GitHub readbacks, the nested `--post`, and the
      operator's-machine rows) and tests/test_phase06_verification.py.
    - scripts/verify_phase05.py and scripts/verify_phase01.py (the
      tagged reads).

    Phase 7 deliverables to verify (65 static checks: 59 across Steps
    1 through 9, and 6 Step 10 self-checks):

    Step 1 (the test budget) — checks 1-4:

    1.  `pyproject.toml`'s dev group lists `pytest-xdist`, and
        `addopts` holds no `-n`.
    2.  `ci.yml`'s `test` job's pytest line holds `-n auto` and its
        four `--cov` flags.
    3.  `verify_phase06.py`'s check 44 reads `v2.0.0-phase-6` (its
        function names the tagged read), pinning the conversion as
        Phase 6's check 31 pinned Phase 5's.
    4.  `tests/test_ci_budget.py` is tracked.

    Step 2 (locations) — checks 5-13:

    5.  `NwsCoverage.county_zone` is optional and `cwa`'s pattern
        takes a digit (AST).
    6.  `sources/nws.py` defines `OPTIONAL_POINT_FIELDS` naming
        `county`, and `fetch_alerts` builds no county request without
        a county.
    7.  `LocationRow` keeps `nws_coverage_whole`, and no revision
        after 0008 rebuilds `locations` (no `batch_alter_table`).
    8.  `sources/http.py`'s `COORDINATE_PARAMETERS` and
        `_COORDINATE_QUERY` both hold `q`.
    9.  `sources/nominatim.py` defines `search`, `parse_search`, and
        `SEARCH_FIELDS_READ`; the register states forward search with
        its policy.
    10. `web/routes/actions.py` declares `/api/locations/search` and
        `/api/locations/remove`, and `docs/api/openapi.json` holds
        both.
    11. `cli/locations.py` offers `--place` and `--pick` beside
        `--lat` and `--lon`.
    12. `frontend/src/settings/LocationManager.tsx` and its test are
        tracked.
    13. The Step 2 tests, `frontend/e2e/locations.spec.ts`, and the
        `search-*.json` recordings are tracked.

    Step 3 (the phone) — checks 14-23:

    14. `services/ntfy.py` defines `NtfyChannel` and `ntfy_channel`,
        sets `follow_redirects=False`, and no f-string there joins the
        topic to a URL (AST).
    15. `CHANNEL_NAMES` includes `ntfy`, `DELIVERY_RESULTS` includes
        `muted`, and `NOTIFICATION_KINDS` is still the five.
    16. `NotificationSettings` has `ntfy` and `ntfy_server` with
        literal overrides, and no settings class declares a field
        naming a topic or token (AST).
    17. `Runtime` defines `make_ntfy`, and `tests/conftest.py` still
        deletes every `WEATHERBOT_` variable.
    18. `models/location.py` defines `LocationPreferences`, and
        `Location` holds it.
    19. Revision `0009_location_preferences.py` follows `0008`, uses
        plain `add_column`, and `FROZEN` pins it.
    20. `services/policy.py` is byte-identical to `v2.0.0-phase-6`,
        and `tests/golden/` holds the same tracked files.
    21. `services/doctor.py` calls `Check` with the literal `"ntfy"`
        (AST).
    22. `services/logs.py` redacts the token's shape and registers the
        secrets' values.
    23. `docs/NOTIFICATIONS.md` holds `## What leaves the machine` and
        `## Runbook`, and the Step 3 tests are tracked.

    Step 4 (settings and retention) — checks 24-32:

    24. `pyproject.toml` lists `tomlkit`, and only
        `services/settings_file.py` imports it (AST).
    25. `EDITABLE` is a literal holding no key of `web`, `engine`,
        `http`, `logging`, or `monitor`, and not `ntfy_server` (AST).
    26. `web/routes/settings.py` declares `PUT /api/settings`; OpenAPI
        holds it.
    27. `RetentionSettings.history_days` defaults to 0, with its
        literal override.
    28. `services/retention.py` defines `RetentionService` with `plan`
        and `run`, uses `writing_session`, calls `backup_database`,
        and names neither `ai_engine` nor `LocationRow` deletion.
    29. `cli/__init__.py` registers `app.command("prune")`, and
        `docs/schema/prune.schema.json` is tracked and in `DOCUMENTS`.
    30. `/api/retention` and `/api/retention/run` are declared, and
        OpenAPI holds them.
    31. `cli/serve.py` starts `RetentionWorker` and keeps Phase 6's
        check 34 calls.
    32. The Step 4 tests are tracked,
        `tests/services/test_retention_keeplist.py` among them, and
        revision `0010_retention_indexes.py` follows `0009`, creates
        four indexes and no table, and `FROZEN` pins it.

    Step 5 (the map's depth) — checks 33-40:

    33. `MapDepthResponse` declares `storms` and `peak_surge`, with
        `wind_radii`, `past_track`, and `past_points` per storm, and
        `MapResponse` declares `available_layers` (AST).
    34. OpenAPI holds `/api/map/depth`, `/api/map/wind-probabilities`,
        and `/api/map/advisories`.
    35. `CSP_SUFFIX`'s `img-src` is exactly `'self' data:
        https://tile.openstreetmap.org https://nowcoast.noaa.gov`, and
        its other directives equal `v2.0.0-phase-6`'s.
    36. `layers.ts`'s `MapLayerKey` holds the twelve keys, and the six
        new ones read `false` in `DEFAULT_LAYER_VISIBILITY`.
    37. `L.tileLayer.wms` appears only under `frontend/src/map/`, and
        no file there calls `setInterval`.
    38. `frontend/src/map/AdvisorySlider.tsx` and its test are
        tracked.
    39. `docs/DATA_SOURCES.md` records the overlays' terms and
        attribution and that `StormSurgeRisk` is not drawn, and
        `tests/live/test_osm_referer_live.py` is tracked.
    40. `frontend/e2e/layers.spec.ts` and the Step 5 tests are
        tracked.

    Step 6 (charts and history) — checks 41-45:

    41. OpenAPI holds `/api/charts`, and `/api/timeline` takes
        `before`.
    42. `frontend/src/charts/` holds `scale.ts` and the four charts,
        each with its test.
    43. `frontend/package.json`'s dependency and devDependency names
        equal `v2.0.0-phase-6`'s.
    44. No file under `frontend/src` holds a `style=` attribute (the
        absolute ban no earlier script has).
    45. `frontend/src/api/keys.ts` holds `charts` under the `timeline`
        prefix, and `QUERY_KEYS` equals `v2.0.0-phase-6`'s.

    Step 7 (replay in the UI) — checks 46-50:

    46. `web/routes/replay.py` declares `/timeline` before
        `/{advisory}` and declares `/assessment`; OpenAPI holds both.
    47. `services/replay.py` defines `ReplayTimelines` and
        `replay_notes`, `cli/replay.py` imports the latter, and
        `web/routes/replay.py` imports no engine module (AST).
    48. `NAV_ITEMS` lists `/replay` after `/map` and keeps Phase 6's
        check 40 order, and `routes.tsx` routes `path: "replay"` to
        `<Replay />`.
    49. `frontend/src/assessment/` holds its four components, and both
        `Dashboard.tsx` and `Replay.tsx` import them.
    50. `engine/changes.py` holds `does not cover the location` and no
        `does not"` literal, and `frontend/e2e/replay.spec.ts` is
        tracked.

    Step 8 (the report) — checks 51-55:

    51. `services/report.py` defines `ReportService` and
        `render_report`, uses `briefing_context`, and names neither
        `display_name`, `distance_km`, `.issuer`, nor
        `Evidence.detail`'s `.detail` (AST).
    52. `services/report.py` holds no `<script`, `<link`, `<img`, or
        `src=` literal, and it calls `html.escape`.
    53. `web/routes/report.py` is a sync route declaring
        `/api/report`, `cli/__init__.py` registers
        `app.command("report")`, and OpenAPI holds the path.
    54. The Step 8 tests are tracked,
        `tests/services/test_report_privacy.py` and
        `frontend/e2e/report.spec.ts` among them.
    55. `README.md`'s `## Commands` names `weatherbot prune`,
        `weatherbot report`, and `--place`.

    Step 9 (the whole phase) — checks 56-59:

    56. `frontend/e2e/phase7.spec.ts` is tracked, and `guard.ts`
        routes `nowcoast.noaa.gov`.
    57. `scripts/measure_idle.py` keeps `budget=<0.5%`,
        `ai_state=ready`, and `change_summaries=on`, and
        `scripts/serve_demo.py` offers `--retention-days`.
    58. `tests/services/test_phase7_alarms.py` is tracked.
    59. `README.md`'s `## Status` names Phase 7 complete and Phase 8
        next (exact: Phase 8 converts it when it edits that section).

    Step 10 self-checks — checks 60-65:

    60. `scripts/verify_phase07.py` is tracked, valid, holds 65 static
        checks and 42 V rows, and declares its eight modes.
    61. `tests/test_phase07_verification.py` is tracked with its named
        tests.
    62. `docs/phase07-qa-findings.md` holds a section per step, the
        idle line, the live smoke runs, and "Pre-ship items".
    63. `docs/roadmap/phase07-roadmap.md` exists with Steps 1 to 10,
        and the project roadmap holds `### Phase 7 — Depth`.
    64. `.github/workflows/phase-verify.yml`'s matrix is the one-line
        list `"01"` to `"07"`, its Node steps for `"07"` stand apart,
        and the `'05'` and `'06'` conditions are unchanged.
    65. The security gate is wired: the gate and frontend hooks in
        `.pre-commit-config.yaml`, `--security` in every phase entry,
        and no key or `tk_` shape under the phase's paths.

    Files to read:

    - scripts/verify_phase06.py (primary structural template) and
      tests/test_phase06_verification.py.
    - scripts/verify_phase05.py and scripts/verify_phase01.py.
    - all Phase 7 implementation files from Steps 1 through 9, and
      docs/NOTIFICATIONS.md.
    - docs/phase06-qa-findings.md (the ledger's shape).
    - docs/roadmap/phase07-roadmap.md (every step's acceptance
      criteria and Post-Implementation Verification) and
      docs/roadmap/ROADMAP.md (Phases 7 and 8).
  </context>

  <goal>
    Create scripts/verify_phase07.py with 65 static checks (59 for
    Steps 1 through 9, and 6 Step 10 self-checks) plus the 42-row
    V1-V10 matrix (107 in `--post`); create
    docs/phase07-qa-findings.md; add `"07"` to the phase-verify.yml
    matrix with its own Node steps; close Phase 7 in both roadmaps and
    the README; and tag `v2.0.0-phase-7`.
  </goal>

  <requirements>
    <requirement>
      Read scripts/verify_phase06.py end to end for structure, flag
      parsing, output format, the PASS / FAIL / SKIP conventions, and
      the final summary. Mirror it so the Phase 7 output is continuous
      with Phase 6's in CI logs.
    </requirement>

    <requirement>
      scripts/verify_phase07.py modes, mutually exclusive; no flag
      runs `--fast` and `--py`:

      - `--fast`: the 65 static checks only — standard library only,
        offline, CI-safe on Ubuntu, under 30 seconds; AST, `tomllib`,
        `json`, and `git ls-files` reads.
      - `--py`: static checks plus ruff, ruff format, strict pyright
        (host and Linux), lint-imports, and one offline pytest run
        with the four coverage floors and `--junitxml` (its
        `COVERAGE_FILE` in a temporary directory), the OpenAPI,
        fixture, and schema `--check` runs
        (`scripts/export_openapi.py`, `export_api_fixtures.py`, and
        `export_schemas.py`), and the wheel smoke.
      - `--node`: static checks plus, in `frontend/`, `npm ci`, `npm
        audit signatures`, `api:check`, `lint`, `typecheck`, Vitest
        with a JUnit reporter, `build`, and `licenses:check`.
      - `--ui`: static checks plus the Playwright run (Chromium) with
        a JUnit reporter, every Phase 7 spec included.
      - `--live`: static checks plus one `pytest -m live` run (the
        landmarks, a throwaway ntfy topic, and one OSM tile; no AI
        request).
      - `--security`: the gate over both stacks; CI-safe on Ubuntu;
        non-zero on any finding.
      - `--all`: `--py`, `--node`, `--ui`, `--live`, and `--security`.
      - `--post`: everything in `--all`, then the nested
        `verify_phase06.py --post` after the operator's yes to its
        stated cost, the idle measurement, and the operator's service
        through `/api/health`, `doctor --json`, and `GET
        /api/notifications/channels`, evaluating every V row.

      Phase 7 adds no `--ai` mode of its own, because it changes no
      prompt, model, or AI product. Static checks: 65, numbered as
      listed in context, each independent, each printing a PASS / FAIL
      line naming its deliverable. At least one is security-oriented
      (check 65: the gate wired, and no key shape committed under the
      phase's paths) — the CI-side backstop to the per-commit gate.
      `EXPECTED_STATIC_CHECKS = 65`, `EXPECTED_POST_ROWS = 42`, and
      `EXPECTED_V_DISTRIBUTION = (3, 5, 5, 4, 4, 4, 4, 4, 5, 4)`; the
      script asserts `verify_phase06.py`'s total of 79 in `--post`.
    </requirement>

    <requirement>
      Post-implementation V-checks, mirroring Phase 6's structure
      (V1-V10, 42 rows), exactly as the Post-Implementation
      Verification section below lists them: V1 (3), V2 (5), V3 (5),
      V4 (4), V5 (4), V6 (4), V7 (4), V8 (4), V9 (5), and V10 (4:
      `--fast` on Ubuntu CI; the matrix includes `"07"`; all 65 static
      checks; `--security`).
    </requirement>

    <requirement>
      Create tests/test_phase07_verification.py with
      `test_fast_verification_passes_all_static_checks_within_thirty_seconds`,
      `test_phase_verify_workflow_includes_phase_07`,
      `test_a_changed_deliverable_turns_exactly_its_check_red` (one
      case per step at least), and cases for missing or skipped JUnit
      evidence and failed probes; the nested `--post` is never invoked
      by a test.
    </requirement>

    <requirement>
      Update .github/workflows/phase-verify.yml: append `"07"` to the
      one-line matrix and add a Node setup step and an `npm --prefix
      frontend ci` step for it under their own condition,
      `"!cancelled() && matrix.phase == '07'"`, before the security
      gate, leaving the `'05'` and `'06'` steps and their literal
      conditions untouched. Every prior entry stays; the new
      `actions/setup-node` use is pinned to the same full SHA with its
      `# vX.Y.Z` comment.
    </requirement>

    <requirement>
      Create docs/phase07-qa-findings.md with a section for this
      roadmap's PR and for every Step 1 through Step 9 PR, a Step 10
      rollup, the measured test durations (before and after Step 1),
      the idle line, the live smoke runs, the source-drift
      observations (the first peak-surge capture, if one came), a
      table of the exact against the growth-proof Phase 7 checks for
      Phase 8, and a "Pre-ship items" section of documented
      limitations and downstream follow-ups, each with a destination.
    </requirement>

    <requirement>
      Mark the phase complete in the parent project roadmap
      (docs/roadmap/ROADMAP.md, beside this file) in the SAME Stage-3
      commit that marks this step (Status rule):

      - `### Phase 7` gets `**Status:** Complete — <YYYY-MM-DD>; PR
        #<n>; v2.0.0-phase-7; phase07-roadmap.md` directly under its
        heading, and the heading ends in ✅.
      - Its row in the "Phase Complexity Summary" table reads
        `Complete`.
      - The header `> **Status:**` line names Phase 7 as shipped and
        Phase 8 as next.
      - The Phase 8 section names the Phase 7 checks that are exact
        (and which step must convert each to read `v2.0.0-phase-7`)
        and the checks that grow by inclusion.
      - Consistency audit: the Phase 7 "Acceptance criteria" there
        match this roadmap's V1-V10 checks.

      And in THIS roadmap, same commit: its phase-level `**Status:**`
      line reads `Complete — <YYYY-MM-DD>`, the title and every step
      heading end in ✅, and every step's Summary Table Status cell
      reads `Complete — PR #<n>`. `README.md`'s Status names Phase 7
      complete and Phase 8 next; `CHANGELOG.md` and `CONTRIBUTING.md`
      close the phase. After the merge, create the annotated tag
      `v2.0.0-phase-7` at the merge commit and push it.
    </requirement>

    <requirement>
      The script prints a clear PASS / FAIL / SKIP line per check,
      exits 0 on success and 1 on any failure, and mirrors
      verify_phase06.py's output format, check numbering, and summary
      so CI logs diff cleanly across phases. `--fast` completes in
      under 30 seconds on Ubuntu CI.
    </requirement>

    <requirement>
      Filepath comment: every new Python, TypeScript, YAML, or
      Markdown file gets its repository-relative path as its first
      line where the file type accepts comments, matching the sibling
      files.
    </requirement>
  </requirements>
</task>
```

### Step 10 acceptance criteria

- `scripts/verify_phase07.py` exists and passes on a clean tree after
  implementation; all eight modes exist.
- The script has 65 static checks plus the V1–V10 post-implementation checks
  (107 in total).
- `--fast` runs in under 30 seconds on Ubuntu CI and on the operator's Windows
  machine.
- `--post` runs cleanly on the operator's Windows machine with `gh` signed in
  and the operator's yes to the nested live eval, reporting V1.1 through V10.4
  green, Phase 6's 79 checks among them.
- `docs/phase07-qa-findings.md` is complete, with every rollup section, the idle
  line, and a destination for every finding.
- `.github/workflows/phase-verify.yml` runs matrix entries `"01"` to `"07"` on
  every pull request under the required aggregate `phase-verify`, with Node set
  up for `"05"`, `"06"`, and `"07"` by separate steps.
- `--security` exits 0 over both stacks; V10.4 is green.
- Branch protection still passes on the resulting PR.
- **Deployed & verified:** the first `phase-verify.yml` run on `main` after the
  merge is green with all seven entries; `gh api
  repos/nathanramoscfa/weatherbot/branches/main/protection --jq
  .required_status_checks` still names `gate` and `phase-verify`; and `git
  ls-remote --tags origin v2.0.0-phase-7` shows the tag at the merge commit.
- **Operations:** every runtime surface this phase added has a health signal and
  an alarm that has been seen to fire: the ntfy channel's delivery results,
  `doctor`'s `ntfy` check, and the channel view, whose failure was injected
  (V9.4) and whose pass was seen on the operator's machine (V3.5); the retention
  worker's heartbeat, read stale and failed (V9.4); and the map overlays'
  unavailable state (V9.2).
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff, and the `security` job and all seven
  `phase-verify` entries are green.
- **Phase closed, nothing carried.** Every finding recorded in
  `docs/phase07-qa-findings.md` has a destination (fixed, an issue number, or a
  named phase that owns it), the "Not in scope" section below is current, and no
  untracked item remains. Every step of this roadmap, this one included, reads
  `**Status:** Complete — PR #…` on `main` under a ✅ heading, the Summary
  Table's Status column and this roadmap's phase-level Status line say
  `Complete` under a ✅ title, and the project roadmap's Phase 7 entry (under a ✅
  heading), its summary-table row, and its header status line say `Complete` —
  all landed in this step's PR. This step's final response ends with the line
  "Step 10 is complete. Phase 7 is complete. You can now move on to Phase 8." in
  place of the usual "Step 10 is complete. You can now move on to Step 11." —
  same Stage 6 rule: no "Follow-ups", no trailer.

---

## Post-Implementation Verification

Every V1–V10 check below runs **automatically in CI** on every push and pull
request, except these. Phase 6's own `--post` sweep (V1.3), the operator's
running service (V2.5, V3.5, V9.5), and the idle measurement (V9.3) run in
`--post` on the operator's Windows machine, because they need the operator's
environment, the installed copy, or ten quiet minutes; the nested Phase 6 sweep
also spends about $0.40 on its live AI eval, after the operator's yes. CI never
holds an ntfy topic or token or an Anthropic credential: every test there uses a
fake built at run time or a recording, and the `live` run's ntfy test uses a
throwaway topic.

| Mode         | Workflow                        | Runner  | Coverage          |
| ------------ | ------------------------------- | ------- | ----------------- |
| `--fast`     | `phase-verify.yml` (`"07"`)     | Ubuntu  | static checks     |
| `--py`       | `ci.yml` test, package          | both    | Python rows       |
| `--node`     | `ci.yml` frontend               | Ubuntu  | frontend rows     |
| `--ui`       | `ci.yml` browser                | Ubuntu  | browser rows      |
| `--security` | `ci.yml` security, phase-verify | Ubuntu  | V10.4             |
| `--live`     | `live-smoke.yml` (dispatch)     | Ubuntu  | live tests        |
| `--all`      | none (local)                    | Windows | all but post      |
| `--post`     | local, operator's machine       | Windows | every V row       |

In the tables, `fast` is `phase-verify.yml`'s `--fast`, `ci` is `ci.yml`'s
`test` job (`--py`), `node` its `frontend` job (`--node`), `ui` its `browser`
job (`--ui`), `sec` the `security` job and `--security`, and `post` the
operator's machine only.

Local invocations remain available for ad-hoc runs and pre-release sweeps:

```bash
uv run python scripts/verify_phase07.py --post   # static + V1-V10 + post checks
```

`--post` is the canonical command to run before tagging `v2.0.0-phase-7`. It
starts a demonstration server and a headless browser in a temporary data
directory, asks before the nested live AI eval and states its cost, reads the
operator's running service only through `/api/health`, `doctor`, and the
channels' delivery results, and says so before it starts.

Other modes:

```bash
uv run python scripts/verify_phase07.py --fast      # static only (CI-safe)
uv run python scripts/verify_phase07.py --py        # + lint, types, tests
uv run python scripts/verify_phase07.py --node      # + frontend toolchain
uv run python scripts/verify_phase07.py --ui        # + browser smoke
uv run python scripts/verify_phase07.py --live      # + live, landmarks only
uv run python scripts/verify_phase07.py --security  # the gate, both stacks
uv run python scripts/verify_phase07.py --all       # all but --post
```

The script reports each V-check by id (V1.1, V2.1, ...) so a failure in any
workflow above maps directly to the corresponding row below.

### V1 — The test budget

> **Automated in CI.** `phase-verify.yml` → V1.1; `ci.yml` → V1.2; `--post` on
> the operator's machine → V1.3.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V1.1  | Static checks 1–4 all PASS.                                  | fast |
| V1.2  | `test_ci_budget.py` passes; a worker stays on loopback.      | ci   |
| V1.3  | `verify_phase06.py --post` passes all 79 (and 5 to 1).       | post |

### V2 — Locations

> **Automated in CI.** `phase-verify.yml` → V2.1; `ci.yml` → V2.2 and V2.3; the
> `browser` job → V2.4; `--post` on the operator's machine → V2.5.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V2.1  | Static checks 5–13 all PASS.                                 | fast |
| V2.2  | No-county, search, place, and remove tests pass.             | ci   |
| V2.3  | Nassau reads the breakpoint path; contract tests pass.       | ci   |
| V2.4  | `locations.spec.ts`: search, add, remove in the page.        | ui   |
| V2.5  | The operator's service holds a location, at head.            | post |

### V3 — The phone

> **Automated in CI.** `phase-verify.yml` → V3.1; `ci.yml` → V3.2 to V3.4;
> `--post` on the operator's machine → V3.5.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V3.1  | Static checks 14–23 all PASS.                                | fast |
| V3.2  | Channel, preference, doctor, and redaction tests pass.       | ci   |
| V3.3  | Quiet hours hold a repeat; an escalation reaches ntfy.       | ci   |
| V3.4  | The policy and every notification golden are unchanged.      | ci   |
| V3.5  | The operator's `doctor` passes `ntfy`; a delivery landed.    | post |

### V4 — Settings and retention

> **Automated in CI.** `phase-verify.yml` → V4.1; `ci.yml` → V4.2 to V4.4.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V4.1  | Static checks 24–32 all PASS.                                | fast |
| V4.2  | Settings write tests pass; every refusal holds.              | ci   |
| V4.3  | A prune equals its plan; policy state and diff hold.         | ci   |
| V4.4  | Prune command, route, and worker tests pass.                 | ci   |

### V5 — The map's depth

> **Automated in CI.** `phase-verify.yml` → V5.1; `ci.yml` → V5.2; the
> `frontend` job → V5.3; the `browser` job → V5.4.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V5.1  | Static checks 33–40 all PASS.                                | fast |
| V5.2  | Layer, slider, and CSP route tests pass.                     | ci   |
| V5.3  | `--node` exits 0: types, lint, Vitest, build, licences.      | node |
| V5.4  | `layers.spec.ts`: no overlay request before its toggle.      | ui   |

### V6 — Charts and history

> **Automated in CI.** `phase-verify.yml` → V6.1; `ci.yml` → V6.2; the
> `frontend` job → V6.3; the `browser` job → V6.4.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V6.1  | Static checks 41–45 all PASS.                                | fast |
| V6.2  | Charts and timeline routes pass; neither holds a distance.   | ci   |
| V6.3  | Chart scales and components pass; no `style` renders.        | node |
| V6.4  | `charts.spec.ts`: sparkline and wind chart, no CSP event.    | ui   |

### V7 — Replay in the UI

> **Automated in CI.** `phase-verify.yml` → V7.1; `ci.yml` → V7.2 and V7.3; the
> `browser` job → V7.4.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V7.1  | Static checks 46–50 all PASS.                                | fast |
| V7.2  | Every scrubbed step equals its golden through the API.       | ci   |
| V7.3  | A whole scrub writes, publishes, and sends nothing.          | ci   |
| V7.4  | `replay.spec.ts`: Dorian at Nassau reads 4, then 5.          | ui   |

### V8 — The report

> **Automated in CI.** `phase-verify.yml` → V8.1; `ci.yml` → V8.2 and V8.3; the
> `browser` job → V8.4.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V8.1  | Static checks 51–55 all PASS.                                | fast |
| V8.2  | The report renders every state; markup stays escaped.        | ci   |
| V8.3  | The privacy scan finds nothing that locates the operator.    | ci   |
| V8.4  | `report.spec.ts`: opens offline, prints to PDF.              | ui   |

### V9 — The whole phase on the operator's machine

> **Automated in CI.** `phase-verify.yml` → V9.1; the `browser` job → V9.2;
> `ci.yml` → V9.4; `--post` on the operator's machine → V9.3 and V9.5.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V9.1  | Static checks 56–59 all PASS.                                | fast |
| V9.2  | `phase7.spec.ts`: the whole flow, the overlay's failure.     | ui   |
| V9.3  | Server and tab each stay under 0.5% of a core idle.          | post |
| V9.4  | Each alarm fires: ntfy, retention, and bad settings.         | ci   |
| V9.5  | The operator's `/api/health` reads head and corpus.          | post |

### V10 — CI integration + security

> **Automated in CI.** `phase-verify.yml` → V10.1 through V10.4 on every
> push/PR.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V10.1 | `verify_phase07.py --fast` exits 0 on Ubuntu CI.             | fast |
| V10.2 | `phase-verify.yml`'s matrix includes `"01"` to `"07"`.       | fast |
| V10.3 | All 65 static checks in `verify_phase07.py` pass.            | fast |
| V10.4 | `--security` exits 0 over both stacks.                       | sec  |

---

## Summary Table

| Step | Scope                          | Model          | Status             |
| ---- | ------------------------------ | -------------- | ------------------ |
| 1    | Test budget (xdist)            | GPT-6.1 Sol    | Complete — PR #90  |
| 2    | Locations + place search       | Gemini 4 Argon | Complete — PR #91  |
| 3    | ntfy + preferences             | Gemini 4 Argon | Complete — PR #92  |
| 4    | Settings + retention           | Gemini 4 Argon | Complete — PR #93  |
| 5    | Map layers + time slider       | Gemini 4 Argon | Not started        |
| 6    | Charts + history               | Gemini 4 Argon | Not started        |
| 7    | Replay scrubber                | Gemini 4 Argon | Not started        |
| 8    | Report export                  | Gemini 4 Argon | Not started        |
| 9    | Full smoke + idle + deploy     | Sonnet 5.5     | Not started        |
| 10   | QA + verify_phase07.py         | GPT-6.1 Sol    | Not started        |
| V1   | Test budget (xdist)            | CI             | --                 |
| V2   | Locations + place search       | CI             | --                 |
| V3   | ntfy + preferences             | CI             | --                 |
| V4   | Settings + retention           | CI             | --                 |
| V5   | Map layers + time slider       | CI             | --                 |
| V6   | Charts + history               | CI             | --                 |
| V7   | Replay scrubber                | CI             | --                 |
| V8   | Report export                  | CI             | --                 |
| V9   | Full smoke + idle + deploy     | CI             | --                 |
| V10  | CI integration                 | CI             | --                 |

Each step's row restates the option its Model rationale names as the best fit on
the step's merits; the platform, the dials, and the other ranks and columns live
in the step's own Settings, and the operator picks the option.

---

## Model selection blocks

Each block restates the option the step's Model rationale names as its best fit
— its Pick and that column's Backup from another maker; the Runner-up is named
in the rationale, and the operator picks the option.

```text
PROMPT: Step 1 — The test budget
MODEL: GPT-6.1 Sol
BACKUP: Gemini 3.8 Flash
PLATFORM: Codex
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — a dependency
and one workflow line, whose parallel run a probe already
proved, Medium complexity. PICK: GPT-6.1 Sol on Codex (AA 50.2
at High), the ladder's Balanced pick; Runner-up Sonnet 5.5 at
High. EFFORT: High is the level the ladder prints for this
column, ample for a small change with one proof.

PROMPT: Step 2 — Locations
MODEL: Opus 5.5
BACKUP: GPT-6 Astra
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a knowledge secondary — a source, a
domain model, a column mapping beside a CHECK, routes, a
command, a page, a recording, and a deployment, High complexity.
PICK: Opus 5.5, S-tier in coding (AA Intelligence Index 56 at
XHigh), the ladder's Quality pick; Runner-up Gemini 4 Argon on
Antigravity at High. EFFORT: XHigh fits the first step that
handles the operator's real place.

PROMPT: Step 3 — The phone
MODEL: Opus 5.5
BACKUP: GPT-6 Astra
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — a second
secret, a third-party channel, a migration, redaction, and a
deployment proved on a phone, High complexity. PICK: Opus 5.5,
S-tier in coding (AA 56 at XHigh), the ladder's Quality pick;
Runner-up Gemini 4 Argon at High. EFFORT: XHigh fits auditing
every path a secret could take.

PROMPT: Step 4 — Settings and retention
MODEL: Opus 5.5
BACKUP: GPT-6 Astra
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a planning secondary — a safe write
to a hand-edited file, and the project's first deletion of
history, High complexity and novel. PICK: Opus 5.5, S-tier in
coding (AA 56 at XHigh), the ladder's Quality pick; Runner-up
Gemini 4 Argon at High. EFFORT: XHigh fits a cascade-aware
delete that cannot be undone.

PROMPT: Step 5 — The map's depth
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a multimodal secondary — routes, a
CSP change, and six layers whose result must be looked at, High
complexity. PICK: Gemini 4 Argon, S-tier in coding with
multimodal strength (AA 52.6 at High), the ladder's Balanced
pick; Runner-up Opus 5.5 at High. EFFORT: High fits display work
this roadmap specifies.

PROMPT: Step 6 — Charts and history
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a multimodal secondary — pure
scales, SVG, and a read route, Medium complexity. PICK: Gemini 4
Argon (AA 52.6 at High), the ladder's Quality pick; Runner-up
Opus 5.5 at High. EFFORT: High fits charts that must read at a
glance in both themes.

PROMPT: Step 7 — Replay in the UI
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a multimodal secondary — a cache,
two routes, a component extraction, and a page, High complexity.
PICK: Gemini 4 Argon, S-tier in coding (AA 52.6), the ladder's
Balanced pick; Runner-up Opus 5.5 at High. EFFORT: High fits
broad UI work on a fixed, golden-checked contract.

PROMPT: Step 8 — The report
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a knowledge secondary — a renderer,
a route, a command, and an offline proof, High complexity. PICK:
Gemini 4 Argon, S-tier in coding (AA 52.6), the ladder's
Balanced pick; Runner-up Opus 5.5 at High. EFFORT: High fits a
privacy rule carried by reusing Phase 6's model.

PROMPT: Step 9 — The whole phase on the operator's machine
MODEL: Sonnet 5.5
BACKUP: Gemini 4 Argon
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: agentic with a coding secondary — a long
end-to-end run, a ten-minute measurement, injected alarms, and
an on-machine deployment, High complexity. PICK: Sonnet 5.5 (AA
51.9 at XHigh), the ladder's Balanced pick for agentic work;
Runner-up GPT-6.1 Sol at XHigh. EFFORT: XHigh fits a long,
tool-heavy session.

PROMPT: Step 10 — QA + verify_phase07.py
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

The project roadmap's Phase 7 section carries no "Not in scope" list; these
items follow from its phase boundaries and its §6 "Out of Scope":

- Any change to the ladder, its thresholds, or the policy, and the answer to
  issue #33 (whether a surge or extreme-wind product moves the ladder). A rule
  change follows Phase 3's golden process with the operator's approval, in a
  change of its own.
- Documentation for release, the PyPI release, the always-on guide, and LAN
  access. Phase 8, whose readiness scan covers the report and the ntfy paths.
- Public hosting, accounts, mobile apps, SMS, email, Slack, and Discord (§6).
  Pushover, the brief's alternative to ntfy, is not built.
- Coverage outside the three NHC basins, model-driven search, any forecast of
  Weatherbot's own, and automated evacuation orders (§6).

Additionally not in scope for this phase:

- The tile proxy, until OpenStreetMap refuses (Decision 13). Its issue holds the
  design, and a live test watches the condition.
- Wiring the Iowa Environmental Mesonet as a second overlay host. The register
  keeps it as the documented fallback, for a failure that has not happened.
- The `StormSurgeRisk` hazard rasters, the inundation mosaics, and the past wind
  swath. Each is stored or catalogued, and none is in the project roadmap's 7.1
  list.
- Wind probabilities per forecast hour. They exist only in GRIB2, which the
  register ruled out; the chart shows the published 120-hour band (Decision 14).
- A PDF library and a map in the report. The browser prints the PDF, and a map
  would need tiles or a marker at the location (Decision 18).
- Shipping or downloading the replay corpus (Decision 17). Phase 8 may revisit
  it.
- Per-location quiet hours and cooldowns. Quiet hours stay global (Decision 6).
- AI in a replay, AI text in a notification or a phone message, and any new AI
  product. This phase changes no prompt or model, so no recording changes.
- Editing `[web]`, `[engine]`, `[http]`, `[logging]`, `[monitor]`, or
  `ntfy_server` from the page, a `weatherbot config set` command, and a restart
  control. The allowlist is deliberate (Decision 7), and the file stays
  hand-editable.
- Pruning a migration's copies in `backups/`, and an automatic `VACUUM`. A
  migration's copy is its rollback, a prune rotates only its own two, and a
  vacuum needs the monitor stopped.
- The Windows Credential Manager for the ntfy secrets. The environment matches
  Phase 6's choice, and no keyring dependency is added.
- Issue #79 (`minimatch` in dev tooling), Dependabot PRs (#8, #31, #47, #78, and
  #85 open on 2026-11-03), and removing version 1 from the operator's `PATH`.
  Independent maintenance and the operator's housekeeping, outside every step.
- A package version bump. The version stays `2.0.0.dev0` until the release
  candidate in Phase 8; `/api/health` names the build, and the milestone tag
  marks the phase.

---

_This roadmap is the execution plan for Phase 7. Each step's `**Status:**` line
is flipped by that step's own PR (Status rule), so this file on `main` is the
phase's ledger — `grep -n '^\*\*Status:\*\*'` reports progress. After all steps
and verification pass, and every finding has a destination, Phase 7 is complete
— declared with the line "Phase 7 is complete. You can now move on to Phase 8."
and nothing after it — and Phase 8 (Release 2.0) inherits a daily-use
application: locations found by name and watched side by side, a phone channel
with its secrets kept out of every record, settings the page can edit and
history it can prune, the whole official picture on the map, charts, a replay
scrubber, and a shareable report, all of which its documentation describes, its
fresh-install smoke exercises with no key, topic, or corpus, and its readiness
scan clears._
