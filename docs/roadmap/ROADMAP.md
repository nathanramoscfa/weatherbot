# Weatherbot — Roadmap to the Second Draft: a CLI and a Local Web App

> **Status:** Phase 1 Complete — 2026-10-15; PR #17; v2.0.0-phase-1. Phase 2 (Sources and persistence) is next.
> **Owner:** Nathan Ramos, sole maintainer and sole user
> **Audience:** Maintainer and the AI coding agents that write the phase
> roadmaps and execute their steps; public, because the repository is
> **Target environment:** Local (the operator's Windows 11 machine); the
> package is published to PyPI
> **Last updated:** October 2026

This roadmap takes Weatherbot from its first draft to its second. The
first draft is a Python command-line tool published to PyPI as 1.0.0 in
September 2025: it reads National Hurricane Center (NHC) forecast cones
and National Weather Service (NWS) alerts for one configured point, maps
them onto a five-level alert ladder, shows Windows toast notifications,
writes one-off HTML reports, and asks OpenAI models to interpret the
official outlook map. The second draft is a from-scratch rewrite: a
deterministic threat engine over official products, a CLI, a modern
local-only web app with pushed updates, history, historical replay, and
Claude as the explainer rather than the decider. Why now: the maintainer
reopened the project in October 2026, with seven weeks of the Atlantic
season left to record live data, and found the first draft's AI layer
stale, its data layer duplicated, and its correctness guarantees
inverted (§2).

The product specification is the brief at
[`docs/brief/weatherbot-v2-brief.md`](../brief/weatherbot-v2-brief.md),
agreed on 2026-10-11, with the operator's decisions D1–D10 recorded in
its §3. This roadmap executes it. Where the roadmap departs from the
brief, §2 "Changes from the brief" records the change and the reason. It
supersedes the "Future Roadmap" wishlist in v1's `CHANGELOG.md`, which
retires with v1.

---

## 1. Executive Summary

Weatherbot is today a working but fragile v1 CLI: about 9,000 lines of
Python 3.11 in which the monitoring cycle lives in the CLI module, four
NHC clients overlap, the AI picks the alert level and code clamps it
afterwards, a "web search" never searches the web, and season-specific
storm names, advisory slots, and a Nassau default area sit in source. It
now needs to become a local application with two front doors, a CLI and
a browser app served from localhost, around one pure threat engine that
decides a five-level threat for named locations from official NHC and
NWS products, keeps history, notifies on change, replays past storms,
and uses Claude Sonnet 5.5 to explain. It must satisfy these
constraints:

1. **Official products decide; the model narrates.** Levels, positions,
   watches, warnings, and times come only from fetched NHC and NWS
   products with recorded provenance. No model output is ever stored or
   shown as a fact, and everything but the briefing works with AI off.
2. **Nothing personal and nothing seasonal in a public package.** The
   repository and the PyPI package carry no coordinates, keys, storm
   names, or home-specific guidance. Locations are data; the operator's
   live only in local configuration.
3. **Testable without a storm.** The Atlantic season ends 30 November
   and most of this work happens after it. Recorded fixtures and
   historical replay come first and gate every later phase.
4. **Alive but light.** The browser receives a pushed event when
   something changed and never polls; the server idles at near-zero
   cost; the map uses raster tiles, not WebGL.
5. **Solo maintainer with AI agents.** Each phase is independently
   shippable; each step is one agent session on its own branch with
   its own PR; the same security gate runs before every commit.

The path: **freeze and record → fetch → decide → watch → show → explain
→ deepen → release**. Phases run strictly in order; none depends on a
cloud resource or spends money except the Claude layer's per-token
calls, which carry a cap.

### Scope by phase

| Phase | Adds                                                    | What becomes demonstrable                                              |
|-------|---------------------------------------------------------|------------------------------------------------------------------------|
| 1     | uv scaffold, strict gates, CI, source register, recorded fixtures, v1 tag | A green empty project whose tests replay real NOAA payloads   |
| 2     | Typed models, NHC and NWS clients, SQLite, read commands | `weatherbot storms` and `weatherbot alerts` print today's official picture |
| 3     | Pure threat engine, geodesy, replay harness, golden tests | Irma 2017 replayed against Miami-Dade reproduces the expected ladder  |
| 4     | Scheduler, change detection, Windows toast, Task Scheduler setup | A new advisory raises a toast within one interval, unattended |
| 5     | FastAPI API with server-sent events, the React SPA, packaging | `weatherbot serve` opens a live dashboard and map in the browser |
| 6     | Claude Sonnet 5.5 briefing, change summary, grounded chat, cost meter | The dashboard explains the situation in plain language, labeled |
| 7     | Charts, surge and radar layers, replay scrubber, multi-location UI, ntfy push, quiet hours, export | Nassau joins Miami-Dade; the phone buzzes; a past storm scrubs on the map |
| 8     | Documentation, PyPI 2.0.0, always-on guide, optional LAN mode | `pip install weatherbot` gives anyone the whole thing              |

---

## 2. Current State Assessment

### What works today

- `weatherbot run`, `run --once`, and `ai-analysis` fetch active cones
  from the NHC map service and the current-storms feed, fetch NWS alerts
  for the configured point, and print a five-level assessment.
- The five-level alert ladder with actions per level is defined in
  `src/weatherbot/alert_levels.py` and documented in `docs/alerts.md`.
- Point-in-polygon and polygon-intersection tests over NHC cone geometry
  (Shapely) work, including an optional county polygon.
- Windows toast notifications work through `win11toast`.
- An HTML report per run embeds the official outlook graphics.
- OpenAI GPT-4o reads the official outlook map and GPT-3.5 and GPT-4
  summarize text, when a key is configured.
- 366 tests pass with every network call mocked; CI runs on
  GitHub-hosted Windows runners for Python 3.11 and 3.12.
- The package is published to PyPI as `weatherbot` 1.0.0 and the
  repository is public under the MIT license with a `DISCLAIMER.md`.
- `reports/` (untracked) still holds six v1 reports from September and
  October 2025 that embed NHC's seven-day Atlantic outlook map of their
  dates. The 38 responses `cache/` held from those storms were deleted
  on 2026-10-11, when the v1 test suite ran from the repository root
  (two v1 tests clear the working-directory cache); see "Changes from
  the brief".

### Gaps blocking the second draft

| #  | Gap                                                                                                                        | Severity |
|----|----------------------------------------------------------------------------------------------------------------------------|----------|
| 1  | The AI decides the alert level and code overrides it afterwards; two modules ask GPT models to recall storm positions from memory, and one ships hardcoded invest positions from September 2025 as a fallback | Critical |
| 2  | Season-specific and personal content in source: storm names in prompts, advisory slots `AT1`–`AT5` in URLs, a Nassau default polygon, "evacuate to the mainland" guidance, a personal email placeholder in the User-Agent | Critical |
| 3  | No recorded real payloads, no golden tests; CI ignores a long list of ruff rules and disables most mypy error codes, so the gates are hollow | High     |
| 4  | Business logic lives in the CLI module; four NHC clients overlap, one scraping storm web pages; cooldown skips the whole analysis so state goes stale | High     |
| 5  | No web app; reports are static one-off files; no history, no timeline, no replay                                           | High     |
| 6  | OpenAI models (`gpt-4`, `gpt-3.5-turbo`, `gpt-4o`) through regex-parsed free text; no structured outputs, caching, or cost control | High     |
| 7  | Watches and warnings for non-US locations come from keyword matching on advisory text; NWS is queried by point only, missing county-zone alerts | Medium   |
| 8  | The evacuation-order input exists but nothing feeds it; the "global coverage" claim rests on the fake web search           | Medium   |
| 9  | Notifications are Windows toast only; nothing reaches a phone                                                               | Medium   |
| 10 | Heavy runtime dependencies (matplotlib, pandas, folium, a tkinter map widget, BeautifulSoup); setuptools and pip instead of uv; Python 3.11 | Medium   |
| 11 | No branch protection, no security gate, no dependency audit; the default branch is `master` while every planning command assumes `main` | Medium   |
| 12 | Documentation describes features that do not exist as described (global coverage, Home Assistant integration)              | Low      |

These gaps drive the phase ordering below.

### Changes from the brief

- **Scaffold before discovery.** The brief's Phase 1 (discovery and
  fixtures) and Phase 2 (scaffold and sources) are reordered and
  regrouped: Phase 1 scaffolds the uv project, the gates, and CI first,
  then records the data-source register and fixtures into it; Phase 2
  is sources and persistence. Reason: the fixture recorder, the replay
  corpus, and their tests need a home and a test runner, and v1's tree
  cannot host them without extending v1.
- **Default branch renamed to `main`.** The brief's D9 keeps `master`.
  Phase 1 Step 1 renamed it on 2026-10-12 so the step lifecycle and every
  `/roadmap-*` command, which name `main`, apply without translation.
  Before that rename, `master` was the ledger.
- **The v1 cache responses are lost.** The brief's §1 lists the 38
  responses in `cache/` as fixtures to harvest. They were deleted on
  2026-10-11, before any harvest, when the planning session ran the v1
  test suite from the repository root. Phase 1 harvests the outlook
  maps embedded in the surviving v1 reports and records every source's
  fixtures live instead (`phase01-roadmap.md`, "Design rationale").
- **The Eastern Pacific outlook graphics are `two_pac_*`.** The brief's
  §5 names them `two_epac_{2d0,7d0}.png`, which NHC answers with 404
  (checked 2026-10-11); the working names are `two_atl_*`, `two_pac_*`,
  and `two_cpac_*`.
- **Text products come from the NWS API.** The brief's §5 reads the TCP
  and TWO through NHC's `text/refresh/…` pages. Phase 1 Step 4 compared
  one live product of each on 2026-10-12. The NWS API's `/products` JSON
  carries the same text, line for line, with a structured issuance time,
  so v2 reads it there and scrapes no HTML (`docs/DATA_SOURCES.md`, "Text
  products").
- **Arrival times come from the arrival-time KMZ.** The brief's §5 names
  the map layers as the arrival-time source. Their labels (`Tue 8 am`)
  carry no date or zone, and the slot's `advdate` can belong to a later,
  intermediate advisory, so v2 reads the KMZ the roster links, which
  states its own time zone and publication time, and keeps the layers as
  a label-only fallback (issue #11; `phase02-roadmap.md`, "Design
  rationale").
- **Wind-speed probabilities belong to the snapshot.** The brief's §7
  lists wind probabilities among the per-storm threat outputs. NHC
  publishes one combined product per synoptic time, and no official
  field attributes a band to a storm, so v2 holds the product per
  snapshot, the per-storm threat record carries no wind-probability
  field, and the ladder's probability triggers read the location's band
  (issue #12; `phase02-roadmap.md`, "Design rationale").

Everything else in the brief applies unchanged: the decisions D1–D10,
the data sources (with the graphic names, the text-product path, and
the arrival-time KMZ above), the ladder semantics, the AI role and
model, the notification policy, and the success criteria.

---

## 3. Target Architecture

```
 Operator's machine (Windows 11). The only trust boundary is loopback.
 ┌──────────────────────────────────────────────────────────────────────┐
 │  Browser ──HTTP + SSE──▶ 127.0.0.1:8765  FastAPI  (weatherbot.web)   │
 │  Terminal ────────────▶  Typer CLI       (weatherbot.cli)            │
 │                 │                              │  serves built SPA   │
 │                 ▼                              ▼                     │
 │        ┌────────────────── weatherbot.services ──────────────────┐   │
 │        │ scheduler · change detection · notification policy      │   │
 │        │ persistence (SQLAlchemy + Alembic) · claude · ledger    │   │
 │        └──────┬───────────────────┬───────────────────┬──────────┘   │
 │               ▼                   ▼                   ▼              │
 │     ┌──────────────────┐  ┌────────────────┐  ┌──────────────────┐   │
 │     │ weatherbot.engine│  │ weatherbot.    │  │ SQLite file in   │   │
 │     │ pure rules, no   │  │ sources (httpx)│  │ the user data dir│   │
 │     │ I/O imports      │  └───────┬────────┘  └──────────────────┘   │
 │     └──────────────────┘          │                                  │
 │  Windows toast ◀── notifications  │   ntfy push (Phase 7) ──────┐    │
 └───────────────────────────────────┼───────────────────────────┼────┘
             HTTPS, keyless, project │ User-Agent      HTTPS, API key from env
             ▼                       ▼                    ▼               ▼
   NHC map services, CurrentStorms,  NWS api.weather.gov  Anthropic API   ntfy
   GIS archive, text products                             (Sonnet 5.5)    server
```

Everything runs on the operator's machine. The web app binds to
127.0.0.1 and serves the built single-page app and a JSON API with a
server-sent events stream; the CLI uses the same services and the same
SQLite database, so both front doors show the same assessment. Outbound
traffic is HTTPS to public NOAA services with a project User-Agent, to
the Anthropic API with a key read from the environment, and, from Phase
7, to an ntfy server with a topic token. There is no public ingress; an
optional LAN mode in Phase 8 is the only widening, and it is gated.

---

## 4. Phased Roadmap

### Phase 1 — Foundation and discovery ✅

**Status:** Complete — 2026-10-15; PR #17; v2.0.0-phase-1; phase01-roadmap.md

**Goal:** Replace v1 with a green, strictly gated uv project on Python
3.13 whose tests already replay real NOAA payloads, with v1 preserved
under a tag and the data sources registered as verified facts.

**Complexity:** Medium · **Risk:** Medium · **Cloud cost:** $0 ·
**Handles sensitive data:** Yes — fixture redaction, the personal-data
gate, and the public repository's history

**Phase roadmap settings** — the session that writes
`phase01-roadmap.md` (`/roadmap-phase 1`):

| Setting      | Value                                  |
|--------------|----------------------------------------|
| Model        | Opus 5.5                               |
| Backup       | GPT-6 Astra — Codex · Intelligence Max |
| Platform     | Claude Code                            |
| Effort       | Max                                    |
| Thinking     | On                                     |
| Conversation | **New**                                |

This roadmap must get the foundations right once: the package layout
every later phase builds on, the fail-closed gate, the fixture format,
and the removal of v1 without losing its recorded payloads. Opus 5.5
leads `roadmodel score --category planning --complexity high --budget
best` (S for planning), at `Max` because the project roadmap fixes
every step after it; Claude Code is funded by the claude.ai Max
subscription, with GPT-6 Astra on Codex (ChatGPT Pro) as the backup if
the weekly Claude pool reads exhausted when the session opens.

#### 1.1 Freeze v1 and clean the tree
- Tag the last v1 commit `v1.0.0` and note in `CHANGELOG.md` that v1 is
  retired and remains installable from PyPI.
- The 21 generated report files v1 tracked under `reports/` were
  removed in PR #1, and no build artifact is tracked; `LICENSE`,
  `DISCLAIMER.md`, and the git history stay.
- Rename the default branch to `main` (local, remote, GitHub default),
  enable branch protection (required checks, linear history, no force
  push), and `delete_branch_on_merge`.

#### 1.2 Scaffold the uv project
- `pyproject.toml` for `weatherbot` 2.0.0.dev0: `src/` layout, Python
  3.13, uv-managed `.venv` with pip (carried by the `planning` group so
  `uv sync` keeps it), dependency groups `dev` and `planning`
  (roadmodel), committed `uv.lock`, `.python-version` 3.13 tracked.
- Package skeleton `weatherbot/{sources,engine,services,cli,web}` with
  an `import-linter` contract that forbids `engine` from importing the
  other layers; `weatherbot --version` prints the version.
- ruff in strict configuration with no blanket ignores; pyright in
  strict mode; pytest with `respx` for HTTP fixtures and no network in
  unit tests; `pre-commit` with the four-check security gate from §5
  (gitleaks, bandit, pip-audit, the personal-data check script) plus
  ruff and pyright.
- CI on GitHub-hosted `ubuntu-latest` and `windows-latest`, Python
  3.13, every action pinned to a commit SHA, minimal `permissions:`,
  the same gate re-run, Dependabot for uv and GitHub Actions (npm joins
  with `frontend/` in Phase 5, since an ecosystem with no manifest fails
  every run).
- Delete v1's code, tests, docs, scripts, and packaging in the scaffold
  itself: the v2 package and v1 cannot share `src/weatherbot` and one
  `pyproject.toml`, and v1 stays readable at the `v1.0.0` tag.
- Switch the roadmodel kit's environment: add roadmodel to the
  `planning` group, verify `.venv\Scripts\python -m pip` works for the
  updater, and replace the project's line in
  `~/.config/roadmodel/projects.txt` with the bare path (an operator
  step named in the step prompt, outside git).
- Rewrite `README.md` as a short v2 status page with the disclaimer and
  a pointer to the `v1.0.0` tag; move `AGENTS.md` to the v2 layout.

#### 1.3 Data-source register and fixture recorder
- `docs/DATA_SOURCES.md`: one row per endpoint in the brief's §5 with
  the layer names discovered by name (never by numeric id), the fields
  used, the cadence, and the verification date. Record what the
  arrival-time, probabilistic-wind, and surge layers actually return
  for each active storm in each basin, which closes the brief's open
  question.
- `scripts/record_fixtures.py`: fetches every source with the project
  User-Agent, redacts nothing personal because requests carry only
  public landmark coordinates, and writes
  `tests/fixtures/recorded/<source>/<yyyy-mm-dd>/` with a manifest
  (URL, fetched-at, SHA-256, HTTP headers that matter).
- Harvest the seven-day outlook maps embedded in the six surviving v1
  reports into the same layout, plus any of the lost `cache/` responses
  the operator restores from a backup (see "Changes from the brief").

#### 1.4 Replay corpus
- `scripts/fetch_replay_corpus.py`: downloads the per-advisory forecast
  shapefiles and KMZ for Irma 2017 (AL112017), Dorian 2019 (AL052019),
  Ian 2022 (AL092022), and Milton 2024 (AL142024) from the NHC GIS
  archive into a git-ignored cache with checksums, and converts each
  advisory to GeoJSON.
- Commit a size-budgeted subset (10 MiB, set in `phase01-roadmap.md`)
  for golden tests; CI restores the rest from a cache keyed by checksum.

**Acceptance criteria**
- `uv sync` on a fresh clone, then `uv run weatherbot --version`, prints
  `2.0.0.dev0` on Windows and Ubuntu.
- CI is green on both runners; a planted fake secret and a planted
  coordinate pattern are each blocked by the pre-commit gate and by CI.
- `git tag` lists `v1.0.0`; `git ls-files src/weatherbot` lists only v2
  skeleton files; the default branch is `main` with protection enabled.
- `tests/fixtures/recorded/` contains at least one manifest-verified
  capture of every source `docs/DATA_SOURCES.md` marks as needing one,
  including the outlook maps harvested from the v1 reports, and a
  contract test loads each one.
- The replay corpus script fetches all four storms with matching
  checksums, and the committed subset is under its size budget.
- `planning/` is current and the roadmodel updater's dry run shows this
  project with no environment override.
- The canonical Phase 1 `--post` sweep reports all 50 static checks and
  V1.1 through V7.4 PASS (see `phase01-roadmap.md`). Both `gate` and
  `phase-verify` are required on protected `main`; the first main phase
  workflow run is green, and annotated `v2.0.0-phase-1` peels to the
  closure merge commit. The QA ledger assigns every finding a destination.
- **Security:** the §5 security gate ran clean on this phase's work —
  gitleaks, bandit, and pip-audit green in pre-commit and CI; the
  personal-data check passes over the whole tree and the recorded
  fixtures; no `.env` or coordinate of the operator's appears in any
  committed file.

---

### Phase 2 — Sources and persistence

**Status:** In progress — phase02-roadmap.md

**Goal:** Typed, provenance-carrying clients for every official source,
a SQLite schema with migrations, and CLI commands that print today's
storms and alerts from them.

**Complexity:** Medium · **Risk:** Low · **Cloud cost:** $0 ·
**Handles sensitive data:** Yes — location coordinates in the local
database and configuration

**Phase roadmap settings** — the session that writes
`phase02-roadmap.md` (`/roadmap-phase 2`):

| Setting      | Value                                  |
|--------------|----------------------------------------|
| Model        | Opus 5.5                               |
| Backup       | GPT-6 Astra — Codex · Intelligence Max |
| Platform     | Claude Code                            |
| Effort       | Max                                    |
| Thinking     | On                                     |
| Conversation | **New**                                |

This roadmap fixes the domain model that the engine, the API, and the
UI all consume, so a wrong field here costs three phases. Opus 5.5 is
the `roadmodel score` PRIMARY for planning at `Max`, funded by the
claude.ai Max subscription; GPT-6 Astra on Codex is the funded backup.

Phase 2 also adapts Phase 1 verification when it expands the scaffold: exact
version, eight-file skeleton, and Typer-only assertions become historical checks
against `v2.0.0-phase-1`; live security, provenance, and fixture guards stay live.
Keep the `"01"` matrix entry and its numbered checks rather than dropping Phase 1
from required verification.

#### 2.1 Domain models
- Pydantic models with provenance on every record: `Location` (name,
  point, optional polygon, country, NWS zone and county ids, and a
  breakpoint span that Phase 3 fills), `StormSummary`, `Advisory`,
  `ConeGeometry`, `TrackPoint`, `WindRadii`, `WatchWarningSegment`,
  `OutlookArea`, `WindProbability` (one product per synoptic time,
  held by the snapshot, issue #12), `ArrivalTime` (resolved against
  the arrival-time KMZ's own time zone and publication time, issue
  #11), `NwsAlert`, and `Snapshot` (the set fetched at one instant).
- Geometry carried as GeoJSON-shaped values validated by Shapely, each
  with an explicit CRS: WGS 84 for live map queries (`outSR=4326`) and
  NWS GeoJSON, and the archive's native D_Sphere for the replay corpus.
  Nothing is relabeled or transformed (`phase02-roadmap.md`, "Design
  rationale").

#### 2.2 NHC clients
- Current storms, map-service layer discovery by name per storm slot
  and for the outlook group, the summary service for probabilistic
  winds, breakpoints, peak surge, text products, outlook graphics, the
  GIS RSS feed, and the arrival-time KMZ the roster links (a new
  register source, `nhc-arrival-times`).
- One `httpx.AsyncClient` with retries and backoff, conditional
  requests where the service honors them, timeouts, and the project
  User-Agent; every response shape covered by a recorded fixture.

#### 2.3 NWS client
- `/points`, `/alerts/active?point=`, `/alerts/active/zone/{county}`,
  and `/zones` with the required User-Agent and the polite interval the
  API documentation asks for; both point and county queries feed one
  alert list.

#### 2.4 Persistence
- SQLAlchemy 2 models and an Alembic baseline for the tables Phase 2
  writes: locations, snapshots, per-source outcomes, storms, advisories,
  geometries, text products, feed items, alerts, settings, and a
  raw-response cache keyed by source, product, and issuance time.
  Assessments and evidence (Phase 3), notifications and the heartbeat
  (Phase 4), and briefings and the Claude ledger (Phase 6) arrive as
  revisions with the code that writes them.
- Database and configuration in the user data directory (`platformdirs`),
  a `weatherbot.toml`, and `WEATHERBOT_*` environment overrides; the
  app backs the database up before applying a migration.

#### 2.5 First CLI commands
- `locations add|list|remove`, `fetch`, `storms`, `alerts`, `doctor`
  (endpoint reachability, layer discovery, database head), each with
  `--json`; Rich tables in the terminal; the disclaimer on first run.

**Acceptance criteria**
- Every recorded fixture from Phase 1 parses into the domain models,
  and a contract test fails when a recorded shape loses a field.
- `uv run weatherbot storms` and `uv run weatherbot alerts` print the
  current official picture for a configured location against the live
  services, and `--json` output validates against the published
  schema.
- Unit tests make no network calls (enforced by a socket guard);
  an optional, manually triggered CI job runs the live smoke.
- `alembic upgrade head` on an empty database and on a Phase 2
  database both succeed; `doctor` reports the head.
- **Security:** gate green; the raw-response cache and logs contain no
  key material; coordinates appear in logs only at DEBUG; the
  User-Agent carries the repository URL and no personal address.

---

### Phase 3 — Threat engine

**Status:** Not started

**Goal:** A pure, deterministic engine that turns a snapshot and a
location into a level with evidence, verified by golden replays of four
historical storms against two locations.

**Complexity:** High · **Risk:** Medium · **Cloud cost:** $0 ·
**Handles sensitive data:** No — pure computation over public data;
tests use public landmark coordinates

**Phase roadmap settings** — the session that writes
`phase03-roadmap.md` (`/roadmap-phase 3`):

| Setting      | Value                                  |
|--------------|----------------------------------------|
| Model        | Opus 5.5                               |
| Backup       | GPT-6 Astra — Codex · Intelligence Max |
| Platform     | Claude Code                            |
| Effort       | Max                                    |
| Thinking     | On                                     |
| Conversation | **New**                                |

This is the phase where correctness lives: rule order, evidence, and
the replay harness decide whether the product can be trusted. Opus 5.5
at `Max` on Claude Code (Max subscription), GPT-6 Astra on Codex as the
funded backup, per the `roadmodel score` PRIMARY and BACKUP lines.

#### 3.1 Geodesy and geometry
- Point-in-polygon and polygon-intersection tests, geodesic distance
  and bearing (`pyproj.Geod`), antimeridian-safe handling for the
  Central Pacific, cone validity repair, nearest point on a track.

#### 3.2 Rules and evidence
- The ladder from the brief's §7 as ordered rules that stop at the
  first match; each match emits an `Evidence` record naming the
  product, issuance time, advisory number, geometry test, distance,
  and time estimate.
- Thresholds (wind-probability floors, cone horizon, development-area
  chance) as configuration with defaults chosen in this phase from
  replay calibration; the brief fixes none, and this roadmap marks
  them TBD until then.
- Per-storm threats: category, in-cone, distance, bearing, earliest and
  most-likely arrival from the arrival-time layers, with a track-based
  fallback when a layer is absent.
- Non-US watches and warnings: map a location to its coastal breakpoint
  span and read the storm's watch-warning segments against it.
- The diff between consecutive assessments as typed change events
  (level up or down, new advisory, new or changed alert, cone entered
  or left).

#### 3.3 Replay harness and golden tests
- Honor the replay FeatureCollections' `source_crs` and the manifest's
  original WKT. Phase 1 preserves geographic D_Sphere (radius 6,371,200 m)
  with operator approval on 2026-10-15; it performs no WGS84 transformation.
  Geometry/geodesy must account for this CRS before comparing locations.
- Load the Phase 1 replay corpus as a sequence of snapshots and run the
  engine over time; `weatherbot replay <storm> --location <name>`
  prints the ladder timeline.
- Golden expectation files for Irma, Dorian, Ian, and Milton against a
  Miami-Dade landmark and a Nassau landmark, reviewed by the operator
  once and then frozen.
- Property tests on geometry helpers; mutation-style tests that flip a
  single rule and expect a golden failure.

#### 3.4 The written ladder
- `docs/ALERT-LADDER.md`: the levels, triggers, priority order,
  thresholds with their calibration evidence, and the actions text,
  as the single source the UI, the CLI, and the Claude prompts quote.

**Acceptance criteria**
- All golden replays pass; changing any threshold or rule order breaks
  at least one golden test.
- The import-linter contract proves `weatherbot.engine` imports no
  I/O layer; engine coverage is at least 90 percent.
- `replay` runs each of the four storms end to end in under a time
  budget set in the phase roadmap (TBD) on the operator's machine.
- `docs/ALERT-LADDER.md` matches the implemented rules (a test renders
  the rules table from code and diffs it against the document).
- **Security:** gate green; no fixture or golden file contains a
  coordinate of the operator's; the personal-data check covers the new
  test data.

---

### Phase 4 — Monitoring and notifications

**Status:** Not started

**Goal:** Unattended operation on the operator's machine: a scheduler
aligned to NHC's cadence, change detection, a notification policy that
never suppresses an escalation, Windows toast delivery, and Task
Scheduler registration.

**Complexity:** Medium · **Risk:** Medium · **Cloud cost:** $0 ·
**Handles sensitive data:** Yes — notification text names locations;
scheduler state and logs live in the user data directory

**Phase roadmap settings** — the session that writes
`phase04-roadmap.md` (`/roadmap-phase 4`):

| Setting      | Value                                  |
|--------------|----------------------------------------|
| Model        | Opus 5.5                               |
| Backup       | GPT-6 Astra — Codex · Intelligence Max |
| Platform     | Claude Code                            |
| Effort       | Max                                    |
| Thinking     | On                                     |
| Conversation | **New**                                |

The notification policy and the scheduler are what make the tool
useful at 3 a.m. during a warning, and a wrong cooldown rule is a
silent failure. Opus 5.5 at `Max` on Claude Code, GPT-6 Astra on Codex
as backup, per the `roadmodel score` PRIMARY and BACKUP.

#### 4.1 Scheduler
- APScheduler inside the `serve` process and a one-shot `check --once`:
  fetch windows after each scheduled NHC product time with jitter, an
  adaptive NWS interval that tightens only while a storm is relevant
  to any location, and a manual `check` on demand.
- A heartbeat table with the last successful fetch per source; a
  staleness rule flags data older than twice its cadence.

#### 4.2 Change detection and notification policy
- Each cycle stores a snapshot, runs the engine per location, stores
  the assessment, and emits change events.
- Policy: notify on level change in either direction, on a new
  advisory for a storm whose cone contains the location, and on a new
  or changed official alert; cooldown suppresses repeats of the same
  event only; escalations always notify; quiet hours apply to levels 1
  and 2 only.
- Every notification is stored with its trigger, channel, and delivery
  result.

#### 4.3 Channels
- A channel interface with Windows toast (one maintained library behind
  it, a no-op fallback elsewhere) and the in-app log; `notify test`
  exercises each configured channel.

#### 4.4 Windows integration and health
- `weatherbot install-task` registers Task Scheduler entries for
  `serve` at logon and an hourly `check --once` fallback;
  `uninstall-task` removes them; `doctor` verifies both and the
  heartbeat.
- After a configurable number of consecutive fetch failures (default
  TBD), a toast and a log entry report degraded data.

**Acceptance criteria**
- Replaying Irma through the monitor service produces the expected
  notification timeline, with cooldown applied to repeats and never to
  escalations.
- A simulated new advisory during `serve` raises a toast on the
  operator's machine within one scheduler interval, and the
  notification row records delivery.
- **Deployed & verified:** after `install-task`, Task Scheduler shows
  both tasks, `doctor` reports them and a fresh heartbeat, and a forced
  task run writes a new assessment.
- The staleness rule fires in a test with a frozen clock and shows in
  `status`.
- **Security:** gate green; notification text contains location names
  only, never coordinates or keys; Task Scheduler entries run as the
  operator with no stored credentials.

---

### Phase 5 — Web app MVP

**Status:** Not started

**Goal:** A local web app that looks and feels like a modern website:
a FastAPI API with a server-sent events stream and a React single-page
app with dashboard, map, storms, alerts, timeline, and settings, packaged
into the wheel.

**Complexity:** High · **Risk:** Medium · **Cloud cost:** $0 ·
**Handles sensitive data:** Yes — a local HTTP surface without
authentication, bound to loopback; coordinates in API responses

**Phase roadmap settings** — the session that writes
`phase05-roadmap.md` (`/roadmap-phase 5`):

| Setting      | Value                                  |
|--------------|----------------------------------------|
| Model        | Opus 5.5                               |
| Backup       | GPT-6 Astra — Codex · Intelligence Max |
| Platform     | Claude Code                            |
| Effort       | Max                                    |
| Thinking     | On                                     |
| Conversation | **New**                                |

This roadmap sets the API contract, the frontend architecture, and the
packaging path that every later UI step extends. Opus 5.5 at `Max` on
Claude Code (Max subscription); GPT-6 Astra on Codex as the funded
backup, per `roadmodel score`.

#### 5.1 API
- FastAPI routes: `/api/health` (version, scheduler state, heartbeat,
  database head), `/api/locations`, `/api/storms`, `/api/assessments`,
  `/api/alerts`, `/api/timeline`, `/api/settings`, and `/api/events`
  (server-sent events emitted when a snapshot, assessment, alert, or
  notification is stored); OpenAPI schema committed and diffed in CI.
- Bound to 127.0.0.1 on a configurable port (default 8765); CORS
  limited to the served origin; a content-security policy on the SPA.

#### 5.2 Frontend
- `frontend/` with Vite, React 19, TypeScript, Tailwind, TanStack Query,
  react-leaflet, Radix primitives, and lucide icons; dark and light
  themes; responsive to phone width; a generated API client from the
  OpenAPI schema.
- Pages: Dashboard (level card with evidence, storms, alerts, next
  product time, staleness banner), Map (cones, tracks, points, watch
  and warning lines, outlook areas, locations), Storms, Alerts,
  Timeline (assessment history and the change feed), Settings
  (first-run location setup, notification preferences).
- The page subscribes to `/api/events` and invalidates only the queries
  an event names; no interval polling anywhere.

#### 5.3 Packaging and developer loop
- The Vite build is copied into `src/weatherbot/web/static` by a build
  step that CI and the release workflow run; the wheel includes it;
  `weatherbot serve` opens the browser; development runs the Vite dev
  server proxied to FastAPI.
- Frontend tests with Vitest and Testing Library; a Playwright smoke
  that loads the dashboard against replay data.
- Dependabot gains the `npm` ecosystem for `frontend/` (Phase 1 left it
  out until a manifest exists).

**Acceptance criteria**
- On a machine without Node, `pip install` of the built wheel then
  `weatherbot serve` opens a dashboard that shows the current
  assessment, and a stored change appears in the browser without a
  reload (observed through the SSE stream in the Playwright smoke).
- The map renders the replay corpus's cones and tracks for a selected
  advisory with the location marker.
- Idle CPU of the server and the browser tab stays near zero between
  events (measured, numbers recorded in the phase's QA findings).
- `npm audit --audit-level=high` and `eslint-plugin-security` are clean
  and run in the gate; the server refuses non-loopback binds unless the
  Phase 8 LAN mode is explicitly enabled.
- **Deployed & verified:** `/api/health` on the operator's running
  service reports this phase's version after upgrade.
- **Security:** gate green; CSP and CORS headers verified by a test;
  no secrets reach the client bundle; coordinates never appear in
  browser console logs.

---

### Phase 6 — Claude layer

**Status:** Not started

**Goal:** Claude Sonnet 5.5 explains the situation: a briefing per
location, a change summary per advisory, a grounded chat over the stored
snapshot, and an optional narration of the official outlook graphic,
all labeled, metered, and capped, and none of it able to touch a level.

**Complexity:** High · **Risk:** Medium · **Cloud cost:** pay-per-token
(see §5 cost projection) · **Handles sensitive data:** Yes — the
Anthropic API key; location names in prompts

**Phase roadmap settings** — the session that writes
`phase06-roadmap.md` (`/roadmap-phase 6`):

| Setting      | Value                                  |
|--------------|----------------------------------------|
| Model        | Opus 5.5                               |
| Backup       | GPT-6 Astra — Codex · Intelligence Max |
| Platform     | Claude Code                            |
| Effort       | Max                                    |
| Thinking     | On                                     |
| Conversation | **New**                                |

This roadmap must design prompts, tools, and guardrails so the model
can never become a source of fact, and must size the cost cap from
measured tokens. Opus 5.5 at `Max` on Claude Code (Max subscription),
GPT-6 Astra on Codex as the funded backup, per `roadmodel score`.

#### 6.1 Client and guardrails
- The official `anthropic` SDK with `claude-sonnet-5-5` as the default
  model (configurable; Haiku 5.5 selectable for micro-summaries),
  adaptive thinking, structured outputs through `client.messages.parse`,
  prompt caching on the frozen system prompt and ladder text, streaming
  to the UI, typed error handling, and the `refusal` stop reason
  handled as "AI unavailable".
- A per-call ledger (model, tokens, cache hits, cost at list price) and
  a daily cap with a kill switch; the key read from `ANTHROPIC_API_KEY`
  or an `ant auth login` profile, never logged, never sent to the
  browser.
- Fetched NOAA text is passed as data inside delimited blocks, tools are
  read-only over local tables, and no tool fetches a URL.

#### 6.2 Briefing and change summary
- A briefing per location from the assessment, evidence, storms, and
  advisory text, in a fixed schema (situation, what it means here,
  timeline, actions by level, sources); a change summary from the
  diff events.
- A small eval set of stored snapshots with checks: the briefing never
  states a level other than the engine's, names its sources, and keeps
  the required sections.

#### 6.3 Grounded chat and optional narration
- A chat panel whose tools read storms, assessments, evidence, alerts,
  and the ladder; streaming replies labeled as AI; a setting to attach
  the current outlook graphic for narration.
- CLI `brief` and `ask`, sharing the same code path.

**Acceptance criteria**
- With a key configured, the dashboard streams a labeled briefing and
  answers a question grounded on the stored snapshot; without a key,
  every other feature is unchanged (a test runs the full suite with
  the client disabled).
- A test proves no code path from the Claude service writes to the
  assessment, storm, or alert tables.
- The daily cap stops calls and the UI says so; the ledger totals match
  the SDK's reported usage on recorded calls.
- The eval set passes; a briefing that contradicts the engine's level
  fails it.
- **Security:** gate green; the key never appears in logs, the
  database, the client bundle, or a test fixture; prompt-injection
  cases in the eval (hostile text inside a fetched advisory) do not
  change tool behaviour.

---

### Phase 7 — Depth

**Status:** Not started

**Goal:** The features that turn a correct monitor into a daily-use
tool: charts, surge and radar layers, a replay scrubber, the
multi-location UI with Nassau, ntfy push, quiet hours, history views,
and an on-demand report export.

**Complexity:** Medium · **Risk:** Low · **Cloud cost:** $0 (ntfy free
tier or self-hosted) · **Handles sensitive data:** Yes — the ntfy topic
token is a secret

**Phase roadmap settings** — the session that writes
`phase07-roadmap.md` (`/roadmap-phase 7`):

| Setting      | Value                                  |
|--------------|----------------------------------------|
| Model        | Opus 5.5                               |
| Backup       | GPT-6 Astra — Codex · Intelligence Max |
| Platform     | Claude Code                            |
| Effort       | Max                                    |
| Thinking     | On                                     |
| Conversation | **New**                                |

A broad phase with many independent features; its roadmap must cut
them into steps that each ship alone. Opus 5.5 at `Max` on Claude Code
(Max subscription), GPT-6 Astra on Codex as the funded backup, per
`roadmodel score`.

#### 7.1 Charts and layers
- Wind-probability charts per location over the forecast period,
  arrival-time display, a level-history sparkline; map layers for
  probabilistic winds, wind radii, past track, peak surge, and radar
  and satellite overlays from the NOAA or Iowa Environmental Mesonet
  services confirmed in Phase 1; a time slider over advisories.

#### 7.2 Replay in the UI
- Pick a storm from the corpus, scrub through advisories, and watch the
  level, evidence, and map change; the same engine and the same
  components as live mode.

#### 7.3 Locations and channels
- Multi-location management in Settings, per-location notification
  preferences, and the Nassau profile exercising the breakpoint path;
  an ntfy channel (topic token in configuration), quiet hours, and
  retention settings for history.

#### 7.4 Export
- An on-demand static report (HTML, optionally PDF) of the current
  dashboard for sharing, with the disclaimer and the AI labels intact.

**Acceptance criteria**
- Dorian 2019 replayed against Nassau shows the watch-and-warning
  ladder from breakpoint segments, in the test suite and in the
  scrubber.
- A test notification reaches a phone through ntfy, and quiet hours
  suppress a level-2 repeat while an escalation still arrives.
- Charts and layers render from recorded fixtures without network, and
  the overlay services are documented with their terms.
- The exported report opens offline and carries the disclaimer.
- **Security:** gate green; the ntfy token is stored like the API key
  and redacted from logs and exports; `npm audit` and `pip-audit`
  clean after the new dependencies.

---

### Phase 8 — Release 2.0

**Status:** Not started

**Goal:** Weatherbot 2.0.0 on PyPI with complete documentation, a
verified fresh-install experience on Windows and Ubuntu, an always-on
setup guide, and an optional, gated LAN mode.

**Complexity:** Medium · **Risk:** Medium · **Cloud cost:** $0 ·
**Handles sensitive data:** Yes — PyPI publishing through OIDC trusted
publishing; the LAN mode token

**Phase roadmap settings** — the session that writes
`phase08-roadmap.md` (`/roadmap-phase 8`):

| Setting      | Value                                  |
|--------------|----------------------------------------|
| Model        | Opus 5.5                               |
| Backup       | GPT-6 Astra — Codex · Intelligence Max |
| Platform     | Claude Code                            |
| Effort       | Max                                    |
| Thinking     | On                                     |
| Conversation | **New**                                |

The release phase owns the irreversible cutovers (a public 2.0.0 and
the first non-loopback bind) and their readiness gates. Opus 5.5 at
`Max` on Claude Code (Max subscription), GPT-6 Astra on Codex as the
funded backup, per `roadmodel score`.

#### 8.1 Documentation
- User guide, configuration reference, `docs/DATA_SOURCES.md` and
  `docs/ALERT-LADDER.md` finalized, AI features and costs, always-on
  setup, troubleshooting, a v1 to v2 migration note, and `CHANGELOG.md`
  for 2.0.0.

#### 8.2 Release pipeline
- A tag-triggered workflow builds the SPA and the wheel, publishes to
  TestPyPI for `2.0.0rc1` and to PyPI for `2.0.0` through trusted
  publishing from a protected environment, then runs a fresh-install
  smoke on Windows and Ubuntu (`uv tool install`, `--version`,
  `doctor`, `serve --check`).

#### 8.3 Readiness gate and optional LAN mode
- A release readiness checklist: repository scan for personal data,
  disclaimer surfaces, dependency audits, rollback rehearsed (yank and
  patch), documentation complete.
- LAN mode behind an explicit setting with a bearer token, rate
  limiting, and a startup warning; its own readiness sub-step before it
  is documented as supported.

**Acceptance criteria**
- `pip install weatherbot==2.0.0` on a clean Windows and a clean Ubuntu
  machine installs; `weatherbot serve` opens the dashboard with no Node
  and no key.
- **Deployed & verified:** the PyPI release page shows 2.0.0, the
  fresh-install smoke job passed on both runners after publication,
  and the operator's own installation reports 2.0.0 at `/api/health`.
- The readiness checklist is complete and linked from the PR that
  tagged the release; `v2.0.0` is tagged on `main`.
- LAN mode refuses to start without a token, and a request without the
  token is rejected (test).
- **Security:** gate green; publishing uses OIDC with no long-lived
  token; the release workflow has minimal permissions and SHA-pinned
  actions; the repository scan for personal data is clean.

---

## 5. Cross-Cutting Concerns

### Cost projection (monthly, USD, personal scale)

Every figure except the list prices is an estimate from stated
assumptions; Phase 6 replaces the token assumptions with measured
usage.

| Service                                                      | Estimate            |
|--------------------------------------------------------------|---------------------|
| NOAA services (NHC, NWS), OpenStreetMap tiles, GIS archive   | $0 (public, keyless, within usage policies) |
| GitHub Actions, Dependabot, PyPI, TestPyPI                   | $0 (public repository) |
| ntfy (public server free tier or self-hosted)                | $0                  |
| Claude Sonnet 5.5 at list price ($2 input, $10 output, $0.20 cache read per million tokens): assume a briefing of 8k input (3k cached) and 1.5k output, so about $0.03; an active-storm day of 4 briefings, 4 change summaries, and 10 chat turns about $0.50; a quiet month near $0 | $0–15 (peak month) |
| **Total**                                                    | **$0–15**           |

The Claude ledger (§5 "Operations & observability strategy") records
the real figure per call, and the daily cap bounds the worst case.

### Sequencing & dependencies

```
Phase 1 ──▶ Phase 2 ──▶ Phase 3 ──▶ Phase 4 ──▶ Phase 5 ──▶ Phase 6
                                                              │
                                                              ▼
                                                   Phase 7 ──▶ Phase 8
```

- Strictly serial. Each phase consumes the previous phase's artifacts:
  fixtures (1) feed clients (2), clients feed the engine (3), the
  engine feeds the monitor (4), the monitor feeds the API and UI (5),
  the stored assessments feed Claude (6), and 7 and 8 extend all of it.
- Every phase runs locally with zero spend; only Phase 6 introduces a
  metered dependency, and it is capped.
- The irreversible cutovers are both in Phase 8: the public 2.0.0
  release and the first non-loopback bind. Each has its own
  readiness-gate sub-step (§4 Phase 8.3).
- No phases run in parallel, so the "Worktree strategy" below permits
  no declared-parallel steps; the only second worktree is a hotfix.

### Branch management strategy

#### Branching model

`main` is the single source of truth (renamed from `master` in Phase 1
Step 1 on 2026-10-12). All work happens on short-lived branches (≤ 1 week)
that merge into `main` via pull request. `main` must always be:

- Green on CI.
- Installable: `uv sync` and `uv run weatherbot --version` succeed on a
  fresh clone.
- Tagged with semver on every published release.

#### Branch naming convention

| Prefix     | Purpose                          | Example                          |
|------------|----------------------------------|----------------------------------|
| `feature/` | Phase work or new feature        | `feature/phase-3-replay-harness` |
| `fix/`     | Non-urgent bug fix               | `fix/nws-zone-parsing`           |
| `hotfix/`  | Urgent fix from `main`           | `hotfix/cone-layer-rename`       |
| `chore/`   | Tooling, deps, housekeeping      | `chore/roadmap-refresh-2026-10-11` |
| `docs/`    | Documentation-only changes       | `docs/alert-ladder`              |
| `perf/`    | Performance work                 | `perf/sse-fanout`                |
| `release/` | Pre-release stabilisation        | `release/v2.0.0`                 |

#### Pull request rules
1. **Scope discipline.** One PR per phase step.
2. **PR template.** Roadmap reference, summary, test plan, screenshots
   for UI, breaking-change notes, rollback plan.
3. **CI green required.** Lint, type-check, tests, the frontend build,
   and the security scans (secret scan, SAST, dependency audit) all
   pass before merge. CI re-runs the same security gate the pre-commit
   hook ran locally — defense in depth, so a bypassed or skipped local
   hook still cannot land an issue on `main`.
4. **No force-push to `main`.** Allowed on personal branches only
   before review opens.
5. **Squash-merge** to `main` so each step reads as one clean commit.
6. **Conventional Commits** on the squash message.

#### Step lifecycle

Every step / sub-section of every phase follows the same six-stage
lifecycle, in order, with no exceptions. Each stage is a hard
checkpoint — if any stage is skipped, branch protection or the next
step's Stage 1 will fail loudly, and that is the safety net. AI coding
agents executing a step MUST complete all six stages before declaring
the step done.

1. **Create the branch.** Before any Read / Edit / Bash, run
   `git checkout -b <prefix>/<slug>` from a clean, up-to-date `main`
   (e.g. `feature/phase-2-nws-client`). The branch name comes from the
   roadmap step's `**Branch:**` line, or from the naming convention
   above for ad-hoc work. When the step runs in its own working tree
   (one of the three cases in "Worktree strategy" below), the
   equivalent is `git fetch origin && git worktree add -b
   <prefix>/<slug> <worktree-path> origin/main`, followed by that
   worktree's bootstrap.

2. **Work on the branch, and pass the security gate before every
   commit.** All commits land here. Never push to `main` directly —
   branch protection rejects it. Before each `git commit`, the local
   security gate (see §5 "Security & privacy strategy" → "Per-step
   security gate") must run and pass: secret scan clean, SAST clean,
   dependency audit clean, and no sensitive data (coordinates,
   credentials, tokens) in the diff. The gate is wired into the
   pre-commit hook and is fail-closed — a finding blocks the commit, so
   a security issue introduced while implementing this step is caught
   here, before it ever reaches the branch, the PR, or `main`.

3. **Open the PR, then mark the step.** `gh pr create --base main
   --head <branch>` with a Conventional Commits title and a body
   referencing the roadmap step and its acceptance criteria. One PR per
   step. Then, with the PR number in hand, set the step's `**Status:**`
   line in its phase roadmap to `Complete — PR #<n> (<YYYY-MM-DD>)`,
   commit that edit on the step branch (`docs: mark Phase N Step M
   complete`), and push. The PR carries its own completion mark, so the
   roadmap on `main` says the step is complete exactly when the PR
   merges — never before, and never by a later conversation
   reconstructing history from `git log`. The same commit marks the
   phase here: on a phase's first step its `**Status:**` line becomes
   `In progress — <phase roadmap file>`; on its final step, `Complete
   — …` with ` ✅` appended to its `### Phase` heading, together with
   its §8 summary row and the header `> **Status:**` line. A roadmap
   that is git-excluded needs the edit only.

4. **Wait for green checks, then squash-merge.** Every required status
   check must report success. If the PR goes BEHIND main, refresh with
   `gh pr update-branch --rebase` — never merge `main` into the branch
   when the repo enforces linear history. Once green:

   ```sh
   gh pr merge <PR_NUMBER> --squash --delete-branch
   ```

   Merged is not done for a step that touches a deployed surface:
   complete the post-deploy verification named in the step's
   acceptance criteria (see "Release & deployment strategy") before
   Stage 6.

5. **Retire the branch (remote + local).** The `--delete-branch` flag
   and the repo's `delete_branch_on_merge: true` setting retire the
   remote automatically. Sync local state and prune the merged branch
   plus any other `[gone]` labels:

   ```sh
   git switch main
   git pull --ff-only origin main
   git fetch --prune origin
   git branch -vv | grep ': gone]' | awk '{print $1}' \
     | xargs -r git branch -D
   ```

   If the step ran in its own working tree, remove that worktree FIRST
   — `git worktree remove <worktree-path>`, then `git worktree prune` —
   because `git branch -D` refuses to delete a branch that is still
   checked out in a worktree. Between steps, `git worktree list` shows
   only the primary tree.

6. **Dispose of every finding, declare completion, then new
   conversation.** Before declaring anything, send every finding the
   step surfaced to its destination per "Defect handling & triage"
   below — a note for a later step is edited into that step's prompt
   now, a bug is fixed or is an issue number, a judgement call in the
   diff is explained in the PR body. A finding that is only described
   is not disposed of, and counts as an unmet acceptance criterion.
   Only once the PR is merged — and `main` therefore carries the step's
   `Complete` Status line — every acceptance criterion is affirmatively
   met, and every finding has a destination, end the final response
   with the verbatim line "Step N is complete. You can now move on to
   Step N+1." (or, on the phase's last step, "Phase N is complete. You
   can now move on to Phase N+1."). That line is the LAST line of the
   response. Nothing follows it — no "Follow-ups (non-blocking)",
   "Notes", "Next", or suggested improvements. If any criterion is
   unmet or any finding has no destination, say plainly that the step
   is NOT complete, name what is outstanding, and withhold the line.
   "Done" means done. Then, for phase-boundary hygiene, the operator
   closes the current Claude Code / Cursor / Codex session and opens a
   fresh one before starting the next step. The new conversation
   begins again at Stage 1 with the next step's `**Branch:**` line
   driving the `git checkout -b` command. No work straddles two steps.

#### Worktree strategy

The default is one working tree — the primary checkout — and one step
in flight at a time; the six-stage lifecycle assumes it. A second
working tree is created only with `git worktree add` (never a second
clone, which would not share branches, hooks, or config), and only in
these cases:

| Case                         | Rule                                                                 |
|------------------------------|----------------------------------------------------------------------|
| Hotfix interrupting a step   | A Critical/High finding (see "Vulnerability handling") gets its `hotfix/` branch in a worktree cut from `origin/main`. The in-flight step's tree is left untouched — nothing stashed, nothing half-committed. |
| Declared-independent steps   | Only steps the "Sequencing & dependencies" diagram (or a phase roadmap's Execution Order) draws in parallel. This roadmap declares none. Each would get its own worktree AND its own conversation; each branches from the same `origin/main` and rebases before merge. Undeclared parallelism is a lifecycle violation, not a shortcut. |
| Subagent isolation in a step | Multi-agent runs inside one step (an agent harness's worktree-isolated subagents) work in throwaway worktrees. Results merge back into the step branch locally; only the step branch opens a PR, and every subagent worktree is removed before Stage 3. |

Rules that apply to every worktree:

1. **Location.** Worktrees live in one recorded place per project: a
   sibling directory (`../<repo>--<branch-slug>`) or a git-ignored
   `.worktrees/<branch-slug>/` inside the repo. Agent tooling that
   creates its own worktrees keeps its own location. Never nest a
   worktree under a tracked path. This project uses: `.worktrees/`.
2. **Bootstrap before use.** A new worktree has NONE of the primary
   tree's untracked state: `.venv`, `frontend/node_modules`, local
   configuration, build output. Run `uv sync` and `npm ci` in the
   worktree before any test or build. Never point a worktree at the
   primary tree's `.venv`: tests in the worktree would silently import
   the primary tree's source.
3. **Hooks and config carry over.** `core.hooksPath` and the rest of
   the repo config are per-repository, so the pre-commit security gate
   and branch guard run in every worktree without setup. Confirm once
   per worktree with `git config core.hooksPath`.
4. **One conversation, one worktree.** Stage 6 still holds: each step
   (and each hotfix) is its own conversation, and a conversation never
   touches more than one worktree. Parallel steps run as parallel
   conversations, never as one conversation switching trees.
5. **Merge from the primary tree.** Run the Stage 4 merge command from
   the primary checkout. Inside a linked worktree, `--delete-branch`
   tries to check out `main` locally and fails (it is checked out in
   the primary tree); the merge itself still lands, but the local
   cleanup is left to Stage 5.
6. **Retire with the branch.** No worktree outlives its PR. Stage 5
   removes it (`git worktree remove <path>`, then `git worktree
   prune`) BEFORE the branch prune, because `git branch -D` refuses a
   branch that is still checked out in a worktree. Between steps,
   `git worktree list` shows only the primary tree.

#### Release & tagging

| Milestone tag        | Marker                                                        |
|----------------------|---------------------------------------------------------------|
| `v1.0.0`             | The last v1 commit, tagged in Phase 1 before v1 code is removed |
| `v2.0.0-phase-1`     | uv scaffold, gates, CI, source register, recorded fixtures    |
| `v2.0.0-phase-2`     | Sources and persistence; `storms` and `alerts` commands       |
| `v2.0.0-phase-3`     | Threat engine with golden replays                             |
| `v2.0.0-phase-4`     | Unattended monitoring and Windows notifications               |
| `v2.0.0-phase-5`     | Web app MVP packaged in the wheel                             |
| `v2.0.0-phase-6`     | Claude briefing, change summary, grounded chat                |
| `v2.0.0-phase-7`     | Depth: charts, layers, replay UI, Nassau, ntfy                |
| `v2.0.0rc1`          | Release candidate on TestPyPI                                 |
| `v2.0.0`             | Public release on PyPI                                        |

Package versions on `main` between phases read `2.0.0.devN`; only the
release candidate and the release are published.

### Release & deployment strategy

**Merged is not deployed, and deployed is not released.** Three
distinct events with three distinct triggers. The surfaces this project
ships are listed below so no step can mistake "the PR merged" for "the
change is live".

#### Deployable surfaces

| Surface                                   | Environments                | Deploy trigger                                              | "Released" means                                  | Verify with                                                        |
|-------------------------------------------|-----------------------------|-------------------------------------------------------------|---------------------------------------------------|--------------------------------------------------------------------|
| PyPI package (CLI and the built web app)  | TestPyPI, PyPI              | Tag-triggered release workflow with trusted publishing      | The version installs from the registry            | Fresh-install smoke on Windows and Ubuntu: `uv tool install weatherbot==X`, `weatherbot --version`, `weatherbot doctor` |
| Operator's local service (`serve` under Task Scheduler) | The operator's machine | The operator upgrades the installed package and restarts the task | `/api/health` reports the new version       | `curl http://127.0.0.1:8765/api/health`; `weatherbot doctor`       |
| Local SQLite database                     | The operator's machine      | Alembic migrations run at application start after a backup  | Schema head matches the code's head               | `weatherbot doctor` shows the Alembic head                         |
| Scheduled tasks (`serve` at logon, hourly `check --once`) | The operator's machine | `weatherbot install-task`                            | The next scheduled run writes a fresh heartbeat   | `weatherbot status`; Task Scheduler history                        |
| GitHub Actions workflows                  | GitHub                      | Merge to `main`                                             | The next run is green                             | Actions tab; required checks on the next PR                        |

A change that lands in a surface whose deploy trigger is not "merge to
`main`" needs its own roadmap step or an explicit sub-step for the
release — never assume it happened.

#### Promotion path and cutovers

- Changes move from a step branch to `main`, then to the operator's
  machine by an explicit upgrade, and to PyPI by an explicit tag.
  Promotion to PyPI is gated on CI green and the readiness checklist.
- **Staged rollout.** When a step spans layers (schema → services →
  API → frontend), each layer lands and is verified before the next is
  started; a migration ships with its backup and its downgrade.
- **Readiness gate before an irreversible cutover.** The public 2.0.0
  release and the first non-loopback bind each get their own
  readiness-gate sub-step (Phase 8.3) with a checklist: personal-data
  scan, disclaimer surfaces, audits, rollback rehearsed, documentation
  complete. Going live is a decision, not a side effect of a merge.

#### Configuration and secrets provisioning

- A step that introduces a required environment variable or secret
  (`ANTHROPIC_API_KEY` in Phase 6, the ntfy token in Phase 7, the LAN
  token in Phase 8) verifies at step kickoff — before writing code
  that fails closed without it — that the operator has a place to set
  it (the environment or the OS credential store) and that `doctor`
  reports its presence without printing it.
- A shared secret is proven by an authenticated round-trip: a real
  Anthropic call, a real ntfy delivery, a real request with the LAN
  token. Listing a variable name proves nothing.
- Sensitive values never transit chat or a PR. Hand the operator a
  command to run, never a value to paste back.

#### Data and schema migrations

- Alembic migrations run at application start, after the application
  copies the database file aside; the copy is the rollback. Migrations
  are expand-first: new columns and tables land before code reads
  them, and contraction waits a release.
- A merged migration that the operator's installation has not applied
  is a tracked gap until `doctor` reports the new head.

#### Post-deploy verification

A step that touches a deployed surface is not done at merge. Its
acceptance criteria include a check in the target environment, and
Stage 4 of the step lifecycle runs it:

- `/api/health` on the operator's running service, or the fresh-install
  smoke for a release, reports the expected version, and
- the changed behaviour is exercised end to end with a hands-off recipe
  the step names (a forced task run, a replayed advisory through the
  live service, an authenticated test notification), not an ad-hoc
  click-through.

Where a PR that references an issue auto-closes it on merge,
verification is what earns the close: if a gap remains after the
environment check, reopen the issue or open a follow-up.

#### Rollback

| Surface                 | Rollback                                                        | Time to execute |
|-------------------------|-----------------------------------------------------------------|-----------------|
| PyPI package            | Yank the release, publish a patch; consumers pin the previous version | Under an hour (TBD once rehearsed) |
| Operator's local service| `uv tool install weatherbot==<previous>` and restart the task   | Minutes         |
| Local SQLite database   | Restore the pre-migration copy the application made             | Minutes         |
| Scheduled tasks         | `weatherbot uninstall-task`, reinstall the previous version's tasks | Minutes      |
| GitHub Actions workflows| Revert the workflow commit                                      | Minutes         |

Every deploy has a named rollback the operator can run in minutes; the
PR body's "rollback plan" field (PR rule 2) names which one. The LAN
mode ships behind a setting, so turning it off is a configuration
change, not a redeploy.

#### Versioning

Releases are tagged per the "Release & tagging" table above. The
package follows semver with PEP 440 spellings (`2.0.0rc1`, `2.0.0`);
the database schema version is the Alembic head and is reported by
`doctor` and `/api/health`.

### Security & privacy strategy

#### Data classification

| Data class                            | Present? | Handling requirement                                                                 |
|---------------------------------------|----------|--------------------------------------------------------------------------------------|
| Operator location coordinates         | Yes      | Local configuration and database only; never in the repository, fixtures, examples, or logs above DEBUG; redacted from exports and bug reports. |
| Anthropic API key                     | Yes (Phase 6) | Environment variable or OS credential store only; never in source, config files under version control, logs, the database, or the client bundle. |
| ntfy topic token, LAN bearer token    | Yes (Phases 7–8) | Same handling as the API key; the LAN token is required for any non-loopback bind. |
| Client / user PII                     | No       | Single operator; no accounts, no third-party users.                                 |
| Payment / financial data              | No       | None.                                                                               |
| Health / regulated data               | No       | None.                                                                               |

#### Threat model (one-paragraph)

The assets are the operator's location coordinates, the API and push
tokens, and the integrity of the level the application shows. The trust
boundaries are the loopback interface between browser and server, the
HTTPS edges to NOAA and Anthropic, and the supply chain through GitHub
Actions, PyPI, and npm. Realistic adversaries are an accidental commit
or a leaked agent transcript that publishes personal data from a public
repository, a compromised dependency or unpinned action, a device on
the same network if the server is ever bound wider, hostile text inside
a fetched advisory aimed at the model's tools, and a silent change in a
NOAA service that would make stale or wrong data look current. The
design must resist five abuse cases: personal data or a secret reaching
the public repository; model output being treated as a fact; the API
being reachable without a token off loopback; a supply-chain compromise
landing through CI; and stale data presented as live.

#### Per-step security gate

This is the core control. Every step of every phase runs the SAME
local, fail-closed security gate before any commit, so a security issue
introduced while implementing a step is caught in development — before
it reaches the branch, the PR, or `main`. A coding agent handed a phase
step must treat this gate as part of the step's definition of done,
exactly like tests.

The gate is wired into the repo's `pre-commit` configuration so it runs
automatically, and it is re-run in CI so a bypassed hook cannot land an
issue on `main`. It has four checks; all must be clean:

| Check                | What it catches                                   | Tooling in this project                                        |
|----------------------|---------------------------------------------------|----------------------------------------------------------------|
| Secret / personal-data scan | Committed credentials, tokens, keys, the operator's coordinates | `gitleaks`; `scripts/check_personal_data.py`, which reads a local denylist of the operator's values kept outside the repository and, in CI, a generic pattern set |
| SAST (static analysis) | Injection, unsafe deserialization, weak crypto, path traversal | `bandit` for Python; `eslint-plugin-security` for TypeScript from Phase 5 |
| Dependency audit     | Known-vulnerable, yanked, or typo-squatted deps   | `pip-audit` over `uv.lock`; `npm audit --audit-level=high` from Phase 5; Dependabot weekly |
| Sensitive-data review| Coordinates in logs, secrets in the client bundle, over-broad binds, missing redaction | Diff review against the data-classification table above       |

Rules for the gate:

1. **Fail-closed.** Any finding blocks the commit. The bypass is for
   genuine emergencies only and every use is recorded in the PR body
   with a justification.
2. **Runs per commit, not per phase.** Because it is a pre-commit
   hook, the developer/agent cannot defer security to "the end" — the
   smallest unit of work is already gated.
3. **Mirrored in CI.** The same four checks run as required status
   checks so the merge is blocked even if the local hook was skipped
   (PR rule 3).
4. **Owned by acceptance criteria.** Every phase's Acceptance criteria
   names the concrete security check for its surface; the phase is not
   "done" until the gate is green on its work.
5. **The pipeline is a trust boundary.** Pin third-party actions to a
   commit SHA, grant each workflow the minimum `permissions:`, never
   expose secrets to workflows triggered by untrusted pull requests,
   put the publish job behind a protected environment, and use OIDC
   trusted publishing instead of a stored PyPI token. A change to a
   workflow file is a security-relevant diff and gets the
   sensitive-data review.

#### Security controls by layer

| Layer               | Control                                                                                     |
|---------------------|---------------------------------------------------------------------------------------------|
| Identity / auth     | None on loopback by design; LAN mode (Phase 8) requires a bearer token, rate limiting, and a startup warning |
| Transport           | HTTPS to every external service with certificate verification on; plain HTTP only on 127.0.0.1 |
| Data at rest        | SQLite and configuration in the user data directory under the OS account's permissions; database backup before migrations |
| Secrets             | Environment or OS credential store; `doctor` reports presence, never values; redaction filter on logging |
| Network / edge      | Bind 127.0.0.1 by default; refuse other binds without the LAN setting and token; CORS limited to the served origin; CSP on the SPA |
| Dependencies        | `uv.lock` and `package-lock.json` committed; `pip-audit` and `npm audit` in the gate; Dependabot weekly |
| CI/CD pipeline      | SHA-pinned actions; least-privilege permissions; OIDC publish from a protected environment; no secrets on pull-request triggers |
| Model integration   | Read-only tools over local tables; fetched text passed as delimited data; no URL-fetching tool; structured outputs; daily cap and kill switch |
| Logging / audit     | Structured logs; no keys; coordinates only at DEBUG; notification and Claude ledgers in the database |
| Incident response   | Rotation runbook for the API and push tokens; yank-and-patch runbook for PyPI; the operator is the on-call owner |

#### Vulnerability handling

Security findings — from the gate, CI, a scanner, Dependabot, or a
report — follow the same discover → triage → track → fix → verify loop
as any other defect, but jump the queue by severity: Critical/High are
fixed on a `hotfix/` or `fix/` branch before new feature work
continues; Medium/Low are tracked as issues with an owner and a due
date. Never silence a finding without a recorded justification.

### Defect handling & triage

Executing a step surfaces findings that are not the step: a failing
adjacent test, a wrong assumption in the step's own spec, a gap an
earlier step left, a product question, a lesson about the process.
Every finding is classified before it is acted on, and each class has
exactly one destination. Never conflate classes in a single fix.

| Class                  | Definition                                                                                   | Destination                                                                                                            |
|------------------------|----------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| Spec rot               | The step's own prompt or spec was wrong (wrong API, wrong threshold, a prerequisite claimed but never done) | Edit the step's `<task>` block in the phase roadmap now, before the next conversation.                                  |
| Upstream gap           | An earlier step missed something that belonged to it                                         | Patch the earlier step's prompt so a re-run does not repeat it; add it to the phase's carry-over checklist.             |
| Implementation bug     | The code is wrong                                                                            | If it blocks this step's acceptance criteria, fix it in this step. Otherwise open an issue; fix on its own branch in a fresh conversation. |
| Architectural question | A broader product or design decision was exposed                                             | Open an issue for a future phase. Never fold it into the immediate fix.                                                |
| Process improvement    | A lesson about how the work is done                                                          | Record it where the next conversation will read it (this roadmap, `AGENTS.md`). If it is a rule, make it a check.      |
| Security finding       | Any of the four gate checks, or a threat-model abuse case                                    | Jumps the queue by severity — see "Vulnerability handling".                                                            |
| Source drift           | A NOAA layer, field, or product changed shape or disappeared                                 | Re-record the fixture, update `docs/DATA_SOURCES.md` with the date, and add a contract test for the new shape in the same PR. |

Rules:

1. **Scope discipline.** A step's PR contains the step plus only the
   blocking fixes from the table. Everything else is tracked, not
   smuggled in. The PR body lists the issues it opened.
2. **Track before you defer.** A deferred finding exists as an issue
   with a class label, an owner, and the phase or step that will
   absorb it, before the current step is declared complete. "We'll
   remember" is not tracking.
3. **Verify the close.** A PR that references an issue with a closing
   keyword closes it on merge — the first such PR wins, even if it
   fixed only part. Verification in the target environment is what
   earns the close; reopen or open a follow-up if a gap remains.
4. **Prevent the class, not the instance.** Every defect that escaped
   a gate gets a guard in the same or the next step — a test, a lint
   rule, a CI check, a contract test — so the class cannot recur. The
   phase's QA findings doc records the finding and its guard together.
5. **Dispose before you declare.** The table above is the only place a
   finding may go. A step is not declared complete while any finding
   is merely described — in the chat, in a "follow-ups" note, in a
   "worth a glance" aside — rather than sitting at its destination.
   The completion line (Stage 6) is the last line of the response; a
   finding that would need to follow it means the step is not done
   yet.

### Operations & observability strategy

Every runtime surface is observable before it is considered live, and
every signal has an owner and a response. The owner is the operator in
every row.

#### Health signals

| Surface                          | Signal                                                                 | Checked by                                        | Alerts                                              |
|----------------------------------|------------------------------------------------------------------------|---------------------------------------------------|-----------------------------------------------------|
| `weatherbot serve`               | `/api/health`: version, scheduler state, last successful fetch per source, Alembic head | `doctor`; the dashboard's staleness banner; the post-upgrade check | Toast and log entry after N consecutive fetch failures (N configurable, default TBD in Phase 4) |
| Scheduled `check --once` task    | Last successful run time in the heartbeat table                        | `status`, `doctor`, Task Scheduler history        | Dashboard banner and toast when older than twice the cadence |
| Claude usage (metered)           | Per-call ledger versus the daily cap                                   | Settings page; `brief --cost`                     | The kill switch disables AI calls at the cap and the UI says so |
| Notification delivery            | Delivery result per notification row                                   | Notification log page; `notify test`              | A failed channel is shown in the log and in `doctor` |
| CI and release workflows         | Workflow status on `main` and on tags                                  | GitHub Actions; the fresh-install smoke job       | GitHub's failure email to the operator              |

#### Rules

1. **Version + health on every deployed surface.** `/api/health`
   reports the running version and the schema head; post-upgrade
   verification reads it, and so does `doctor`.
2. **Scheduled automation has a heartbeat.** The scheduler and the
   Task Scheduler fallback each write a heartbeat; staleness beyond
   twice the cadence is an alarm that the dashboard and a toast
   surface. Detection without a consumer is not health.
3. **Metered dependencies have a ledger and a cap.** The Claude service
   records per-call cost to the ledger table, enforces the daily cap
   with a kill switch, and the cost projection above shows the
   worst-case arithmetic.
4. **Logs are safe by construction.** No keys; coordinates only at
   DEBUG; structured fields so an incident can be queried, not grepped.
5. **Every alert has a runbook.** An alert with no owner or no runbook
   is noise; delete it or complete it.

#### Runbooks

| Scenario                                  | Runbook                                                                                              |
|-------------------------------------------|------------------------------------------------------------------------------------------------------|
| NOAA service renamed a layer or is down   | `doctor` names the failing source; the dashboard shows stale data with its age; re-record the fixture and ship a `fix/` under "Source drift"; levels are never computed from stale data without the banner |
| Toast does not appear                     | `notify test`; check the Windows notification settings for the Python executable; the channel's fallback logs the text |
| Scheduled task silent                     | `doctor`; Task Scheduler history; `install-task` again; the hourly fallback covers a crashed `serve` |
| API or push token leaked                  | Rotate at the provider, set the new value, prove it with an authenticated round-trip (`brief`, `notify test`); search logs and the database for the old value |
| Release regressed                         | Yank on PyPI, pin the previous version locally, publish a patch; record in `CHANGELOG.md`           |
| Migration failed at start-up              | Restore the pre-migration database copy, downgrade the package, open a `fix/`                        |
| Claude cap reached during a storm         | The UI says AI is paused; levels and notifications are unaffected; raise the cap deliberately in Settings if wanted |

**Acceptance.** A phase that adds a runtime surface is not done until
the surface's health signal and its alarm exist and have been seen to
fire once (or a synthetic failure was injected to prove they do). Phases
4, 5, 6, and 7 carry that in their acceptance criteria.

### Risks & mitigations

| Risk                                                                 | Mitigation                                                                                         |
|----------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| NOAA renames layers, changes fields, or retires a service             | Discovery by name, contract tests on recorded fixtures, the "Source drift" triage class, a staleness banner |
| Most development happens off-season with no live storms             | Fixtures and the replay corpus in Phase 1; golden replays gate the engine; replay mode in the UI   |
| NWS and Nominatim etiquette (User-Agent, polite intervals)          | A project User-Agent, cadence-aligned scheduling, one geocode per location cached forever           |
| Windows toast libraries churn                                        | One channel interface with a tested fallback; the library is a one-line swap                       |
| Claude cost spikes during an active storm                            | Sonnet 5.5, prompt caching, a daily cap with a kill switch, the ledger in the UI                    |
| Personal data leaks into the public repository                      | The personal-data check in the gate and CI, public-landmark coordinates in every example and test  |
| The claude.ai Max weekly pool is exhausted when a session opens     | Every Settings table names a funded backup from another provider (GPT on Codex for a Claude pick, Claude on Claude Code for a GPT pick); sessions switch rather than wait |
| Scope creep in Phase 7                                               | Each feature is its own step with its own PR; anything new goes to an issue for a later version    |
| The frontend build becomes a maintenance burden                      | A single lock file, Dependabot, the build in CI on every PR, no server-side rendering               |
| Replay corpus size strains the repository                            | A size budget set in Phase 1, a checksum-verified download script, CI cache for the rest           |

---

## 6. Out of Scope

The following are deliberately deferred to a future version:

- Public hosting, multi-user accounts, or any authentication beyond the
  optional LAN token.
- Coverage outside the Atlantic, Eastern Pacific, and Central Pacific
  basins, and model-driven web search of any kind.
- Mobile applications, SMS, email, Slack, or Discord channels.
- Machine-learning track or intensity prediction; any forecast of
  Weatherbot's own.
- Automated ingestion of county evacuation orders (a manual toggle per
  location stands in).
- Commercial API, enterprise features, and multi-hazard monitoring.

---

## 7. Glossary

| Term            | Meaning                                                                                   |
|-----------------|-------------------------------------------------------------------------------------------|
| NHC             | National Hurricane Center, the NOAA office that issues tropical cyclone forecasts and watches and warnings for the three basins |
| NWS             | National Weather Service; `api.weather.gov` serves its alerts for US locations           |
| Cone            | The NHC forecast cone: the probable track area of a storm's center over the forecast period |
| Breakpoint      | A named coastal point between which NHC watches and warnings are issued, including non-US coasts |
| TWO             | Tropical Weather Outlook: NHC's two- and seven-day formation outlook, as text, graphics, and map layers |
| TCP             | Tropical Cyclone Public Advisory, the text product issued with each advisory              |
| ATCF            | Automated Tropical Cyclone Forecasting system; its files carry invest positions           |
| Invest          | A disturbance NHC is investigating, numbered before it becomes a depression or storm      |
| Wind speed probabilities | NHC's 34, 50, and 64 knot cumulative probability products, served as map layers  |
| Advisory        | A numbered NHC forecast package issued at a scheduled time for one storm                  |
| Snapshot        | Everything Weatherbot fetched at one instant, with provenance                             |
| Assessment      | The engine's output for one location from one snapshot: level, evidence, threats, diff    |
| Evidence        | A record naming the product, time, advisory, geometry test, and estimate behind a level   |
| Golden test     | A frozen expected output (here, a ladder timeline) the engine must reproduce exactly      |
| Replay          | Running archived advisories through the engine and the UI as if live                      |
| SSE             | Server-sent events: a one-way stream from the server that lets the browser avoid polling  |
| SPA             | Single-page application, the React frontend served by FastAPI                             |
| uv              | The Python project and environment manager used from Phase 1                              |
| Alembic         | The migration tool for the SQLite schema                                                  |
| ntfy            | A simple publish-subscribe push service used for phone notifications                      |
| roadmodel       | The planning kit in `planning/` that picks the model for each roadmap session and step    |

---

## 8. Phase Complexity Summary

| Phase | Description                                   | Complexity | Status      |
|-------|-----------------------------------------------|------------|-------------|
| 1     | Foundation and discovery                      | Medium     | Complete |
| 2     | Sources and persistence                       | Medium     | Not started |
| 3     | Threat engine                                 | High       | Not started |
| 4     | Monitoring and notifications                  | Medium     | Not started |
| 5     | Web app MVP                                   | High       | Not started |
| 6     | Claude layer                                  | High       | Not started |
| 7     | Depth                                         | Medium     | Not started |
| 8     | Release 2.0                                   | Medium     | Not started |
