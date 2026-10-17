# Phase 2 Roadmap — Sources and persistence

**Status:** In progress

## Overview

Phase 2 opens the gate between recorded payloads and a working application.
Every official source Weatherbot reads gets a typed, provenance-carrying client
in `weatherbot.sources`; every recorded fixture parses into the shared domain
models of a new `weatherbot.models` package; a local SQLite database with
Alembic migrations keeps locations, snapshots, and the raw responses behind
them; and the first CLI commands print today's storms and alerts from the live
services. It does not compute a level, rank a threat, or decide what an alert or
a watch-warning segment means for a location (Phase 3), run anything on a
schedule or send a notification (Phase 4), or serve a web page (Phase 5). The
work is one phase because the clients, the models, and the database are one
contract: a field the engine, the API, and the user interface will read is fixed
here, with a recorded payload behind it, and a wrong field costs three phases.

The phase lands in 7 layers:

1. **Domain models** — `src/weatherbot/models/`: frozen Pydantic v2 models with
   a `Provenance` on every record (source id, URL, fetched-at, status, SHA-256,
   product issuance, advisory): `Location`, `StormSummary`, `Advisory`,
   `ConeGeometry`, `TrackPoint`, `ForecastTrack`, `WatchWarningSegment`,
   `WindRadii`, `ArrivalTimeProduct`, `OutlookArea`, `WindProbabilityProduct`,
   `NwsAlert`, `NwsZone`, `GeocodeResult`, `Breakpoint`, `TextProduct`,
   `GisFeedItem`, `OutlookGraphic`, `MapCatalog`, `OverlayCatalog`,
   `DisplayLayer`, and `Snapshot`. Geometry is a GeoJSON-shaped value with an
   explicit CRS, checked by Shapely and never relabeled; instants are
   timezone-aware UTC, with NOAA's local text kept beside them; the decisions on
   issues #11 and #12 are encoded in the types; `weatherbot.models` joins the
   import contracts as the lowest layer; and checks 7, 9, and 12 of
   `scripts/verify_phase01.py` read Phase 1's version, skeleton, and dependency
   list from `v2.0.0-phase-1`.
2. **HTTP foundation and NHC map clients** — `weatherbot.sources.http`: the one
   `httpx.AsyncClient` a run uses, with the register's User-Agent as a package
   constant that the fixture recorder now imports, per-host pacing, retries with
   backoff, timeouts, a size cap, conditional requests, typed errors, and log
   lines that never carry a request coordinate above DEBUG; the
   `nhc-current-storms` client; a generic ArcGIS client (catalog, layer
   resolution by name and group path, the register's shared query parameters,
   paging, counts); clients for the tropical, summary, breakpoint, and
   peak-surge services; contract tests that parse every recorded capture and
   fail when a register field disappears; and `live-smoke.yml`, dispatched by
   hand.
3. **NHC products** — the arrival-time KMZ that the storm roster links, as the
   new register source `nhc-arrival-times`, with every labelled line resolved to
   an instant against the product's own time zone and publication time (issue
   #11); the TCP and TWO text products from the NWS API; the six outlook
   graphics with conditional requests; the three GIS RSS feeds; and the
   surge-risk and overlay catalogs, so every recorded NHC and display fixture
   has a client.
4. **NWS and geocoding clients** — `/points`, with the documented
   out-of-coverage answer as a typed non-US result; alerts at the point and for
   the county and forecast zones, merged into one list that keeps how each alert
   was found and its `affectedZones` and `geocode` lists (the inputs issue #10's
   rule needs); `/zones`; and the Nominatim reverse geocoder, called once per
   location.
5. **Persistence and configuration** — the configuration and data directories
   through `platformdirs` with `WEATHERBOT_*` overrides; `weatherbot.toml`;
   SQLAlchemy 2 tables for the data Phase 2 writes, created by an Alembic
   baseline that ships inside the package; an online-backup copy of the database
   before every migration; a raw-response cache that keeps conditional requests
   working between runs; and a test guard that keeps every test away from the
   operator's real directories.
6. **Services and the first CLI commands** — a snapshot service that fetches
   every source concurrently under the pacing rules, records each source's
   outcome, and stores the snapshot; a locations service;
   `locations add|list|remove`, `fetch`, `storms`, `alerts`, and `doctor`, each
   with `--json` output validated against a JSON Schema committed under
   `docs/schema/`; Rich tables; the disclaimer on first run; and the live smoke
   of every command for both public landmarks.
7. **QA + `verify_phase02.py`** — `scripts/verify_phase02.py` (`--fast`, `--py`,
   `--live`, `--security`, `--all`, `--post`), `docs/phase02-qa-findings.md`,
   and matrix entry `"02"` beside `"01"` in `phase-verify.yml`; Phase 2 closed
   in this roadmap and the project roadmap; the `v2.0.0-phase-2` tag.

The ship test for Phase 2 is straightforward: every recorded fixture of every
register source parses into the domain models, and a contract test fails when a
register "Fields v2 uses" field disappears from a recorded shape;
`uv run weatherbot storms` and `uv run weatherbot alerts` print the current
official picture for a configured landmark location against the live services,
and every `--json` document validates against its committed schema; unit tests
make no network call under the socket guard, and `live-smoke.yml`, dispatched on
`main`, runs the live suite green; `alembic upgrade head` succeeds on an empty
database and on a database at every earlier revision, and `doctor` reports the
head; Phase 1's verification still passes, with its version, skeleton, and
dependency assertions read from `v2.0.0-phase-1`; and
`scripts/verify_phase02.py --fast` exits 0 on Ubuntu CI with `phase-verify (01)`
and `phase-verify (02)` green.

**Pre-requisite:** Phase 1 closed on 2026-10-15 (PR #17, `v2.0.0-phase-1`). Its
register fixes the source ids, endpoints, query parameters, and User-Agent the
clients implement; its recorded fixtures are what every contract test parses;
its replay corpus is the second consumer of the arrival-time parser; and its
gate, required checks, socket guard, and working-directory guard are what every
Phase 2 commit runs under. The planning kit moved to roadmodel 0.2.86 on
2026-10-16 (PR #18), before this roadmap was written.

**Dependency:** Phase 3 does not start until Phase 2's V-checks are green. The
engine is a pure function of `weatherbot.models` values: it reads the `Snapshot`
and `Location` this phase defines, alerts that carry the inputs issue #10's rule
needs, arrival times with resolved instants, and wind probabilities that belong
to the snapshot, and its golden replays load the corpus into the same models.
Phase 4's scheduler calls the snapshot service and reads the stored snapshots,
and Phase 5's API serves the same models.

**Design rationale (decisions and changes from the project roadmap and the
brief).** Seven decisions, each reflected in the project roadmap by this
roadmap's own pull request where it changes that document:

- *Arrival times come from the arrival-time KMZ the roster links (issue #11,
  option b).* The map layers label each line only `Tue 8 am`, with no date and
  no zone. Option (a), dating labels from the slot's `advdate`, fails on the
  recorded fixtures themselves: on 2026-10-12 the `EP5` cone was intermediate
  advisory 22A (`500 PM MST`), while the arrival lines belonged to full advisory
  22 (2:00 PM MST), because arrival products come only with full advisories. The
  KMZ at the roster's `earliestArrivalTimeTSWindsGIS.kmzFile` and
  `mostLikelyTimeTSWindsGIS.kmzFile` carries `timezone`, `advisoryNum`, and
  `pubAdvTime` in its `ExtendedData` (seen in EP202026 advisory 22 on 2026-10-12
  and in the archived Dorian advisory 036), and the replay corpus holds the same
  KMZ for Dorian, Ian, and Milton, so one parser serves live data and replay.
  Each label resolves to the first instant at or after `pubAdvTime` whose local
  weekday and clock time match it in the product's zone, within the product's
  120-hour horizon; an unknown zone abbreviation or a label that does not
  resolve leaves the line without an instant, never with a guess. The map-layer
  lines remain a label-only fallback (option c) for display when the KMZ is
  unavailable. The register gains `nhc-arrival-times`, and its "Not used" row on
  per-storm KMZ narrows.
- *Wind-speed probabilities belong to the snapshot (issue #12).* The
  `Probabilistic Winds` layers carry a band and a synoptic time and no storm,
  NHC publishes one combined product per synoptic time, and no official field
  attributes a band to a storm. `WindProbabilityProduct` is therefore one
  product per threshold and synoptic time, held by the `Snapshot`, with no storm
  field, and the per-storm threat record that Phase 3 builds carries no
  wind-probability field. The ladder's probability triggers (brief §7, levels 2
  and 3) read the location's band from the snapshot's product, and evidence
  cites its synoptic time. This changes the brief's §7 outputs, which list wind
  probabilities per storm; the project roadmap records the change.
- *Geometry keeps its CRS.* Live map queries ask for `outSR=4326` and NWS
  GeoJSON is WGS 84, so live geometry is labelled `EPSG:4326`; the replay corpus
  keeps the archive's native geographic D_Sphere (radius 6,371,200 m) with its
  exact WKT, as the operator approved on 2026-10-15. The project roadmap's 2.1
  said "coordinates in WGS84"; it now says every geometry carries an explicit
  CRS. No model relabels or transforms coordinates, and Phase 3 decides how its
  geodesy treats the sphere.
- *Tables arrive with their writers.* The Phase 2 baseline migration creates the
  tables Phase 2 code writes and reads: locations, snapshots, per-source
  outcomes, raw responses, storms, advisories, product geometries, text
  products, feed items, alerts and their observations, and settings. Assessments
  and evidence (Phase 3), notifications and the heartbeat (Phase 4), and
  briefings and the Claude ledger (Phase 6) arrive as Alembic revisions with the
  code that writes them, so no column is guessed before its producer exists. The
  project roadmap's 2.4 list is narrowed accordingly.
- *Unknown official codes are kept, never dropped.* A watch-warning `tcww` code,
  a storm classification, or an outlook risk outside the known set parses with
  its raw value and `recognized` false, and `doctor` reports it as a
  Source-drift warning. Dropping an official warning because its code is new is
  worse than showing it unrecognized.
- *The package version stays `2.0.0.dev0`.* The milestone tag marks the phase,
  as in Phase 1; the User-Agent follows the package version (the register), so a
  bump would change the agent of every recording for no user-visible gain.
- *The live smoke is manual.* `live-smoke.yml` runs on `workflow_dispatch` only,
  as the project roadmap's acceptance criteria say; detecting source drift on a
  schedule belongs to Phase 4's heartbeat and staleness rules.

**Branch strategy.** Every step in this phase lands on its own short-lived
feature branch (`feature/phase02-step<M>-<slug>`), opens a pull request against
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
git checkout -b feature/phase02-step<M>-<slug>
```

This is non-negotiable. `main` is protected with `enforce_admins: true`, so a
commit on `main` cannot be pushed and must be rewound or rebased onto the
feature branch before the PR can open — an avoidable round-trip. If you discover
mid-step that you started on `main`, recover by running the same
`git checkout -b` command immediately (uncommitted changes carry over to the new
branch), then continue. AI coding agents executing a step from this roadmap must
treat the branch checkout as Step 0 of every step.

**Worktree rule.** One working tree, one step in flight — the lifecycle below
assumes the primary checkout. A second working tree is created only with
`git worktree add`, and only for the three cases the project roadmap's "Worktree
strategy" sanctions: a `hotfix/` branch interrupting this step (cut from
`origin/main` in its own worktree so this step's tree is untouched); steps the
Execution Order below explicitly draws in parallel (this phase draws none); and
worktree-isolated subagents inside a step (throwaway trees that merge back into
the step branch locally and are removed before the PR opens). In those cases
Stage 1 becomes `git fetch origin && git worktree add -b
feature/phase02-step<M>-<slug> <worktree-path> origin/main`, the worktree is
bootstrapped before any test or build (`uv sync` in the worktree — a worktree
has none of the primary tree's untracked state, and it must never borrow the
primary tree's `.venv`), the Stage 4 merge runs from the primary tree, and Stage
5 removes the worktree BEFORE pruning the branch. Undeclared parallelism is a
lifecycle violation, not a shortcut. Worktree location for this project:
git-ignored `.worktrees/<branch-slug>/` inside the repository, matching the
project roadmap.

**Security-first execution rule.** Security is not a phase — it is a gate on
every commit of every step. Before each `git commit`, the step's work must pass
the local, fail-closed security gate: secret/personal-data scan clean, SAST
clean, dependency audit clean, and a diff review confirming no sensitive data
(the operator's coordinates, credentials, tokens) and no new insecure pattern
(injection, unsafe XML or archive parsing, a redirect or link followed without
an allowlist, over-broad scope, a coordinate in a log line above DEBUG). The
gate is wired into the pre-commit hook and re-run in CI, so a security issue
introduced while implementing a step is caught during development — before it
reaches the branch, the PR, or `main`. See the project roadmap's "Security &
privacy strategy" → "Per-step security gate" for the canonical checks and
tooling; each step's XML `<task>` carries a `<security>` block restating them
for the agent, and each step's Acceptance Criteria ends with a security check.
AI coding agents executing a step MUST treat the security gate as part of the
step's definition of done, exactly like its tests. This matters more in this
phase than in the last: for the first time the code handles the operator's
location coordinates, which reach two public services in request URLs, live in a
local database, and must never reach the repository, a fixture, a log line above
DEBUG, or a conversation.

**Deploy-and-verify rule.** Merged is not deployed, and deployed is not
released. Every step header carries a `**Deploys:**` line naming the surface and
environment the step's merge reaches — or `nothing beyond merge` — and when
going live needs a migration, a workflow run, or a tag, the line says so and
this step (or a named follow-on step) owns that event. For a step whose Deploys
line names a surface, Stage 4 of the lifecycle does not end at the squash-merge:
the step's acceptance criteria carry a **Deployed & verified** bullet (the
workflow's first run on `main` is green, or `doctor` on the operator's machine
reports the database at the Alembic head), and that bullet must be green before
the step is declared complete. This phase introduces no secret and no required
environment variable: every source is keyless, and the `WEATHERBOT_*` overrides
are optional paths and settings. Its new local surfaces are the CLI and the
SQLite database in the operator's data directory (Step 6). The operator's own
location enters only through `locations add`, which the operator runs
themselves; an agent verifies with the public landmarks and never asks for,
reads, or prints the operator's coordinates. See the project roadmap's "Release
& deployment strategy" for the surfaces table, promotion path, migrations, and
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
contract test in the same PR. A step's PR contains the step plus blocking fixes
only, and lists the issues it opened. When a merged PR auto-closes an issue, the
environment check is what earns the close — reopen or follow up if a gap
remains. `docs/phase02-qa-findings.md` is the rollup: every finding, its class,
and the guard added so the class cannot recur.

**Status rule.** Every step carries a `**Status:**` line directly under its
`## Step N — …` heading, before the Goal, and this file on `main` is the ledger
of what is done — never a chat transcript, never a later conversation
reconstructing history from `git log`. The line reads `Not started` when this
roadmap is written and is flipped by the step's OWN pull request: at Stage 3,
right after `gh pr create` returns the PR number, the agent sets it to
`Complete — PR #<n> (<YYYY-MM-DD>)`, appends ` ✅` to the step's heading
(`## Step 3 — NHC products ✅`) so the completion shows in the rendered preview,
the outline, and the table of contents, sets the step's Summary Table Status
cell to `Complete — PR #<n>`, commits that edit on the step branch, and pushes.
The PR therefore carries its own completion mark, and the roadmap on `main` says
a step is complete exactly when that step's PR merges — never before. This
file's phase-level `**Status:**` line (under the title) and the project roadmap
are marked the same way, in the same commit: Step 1's PR flips both from
`Not started` to `In progress` (the project roadmap's `### Phase 2` line reads
`In progress — phase02-roadmap.md`), and the final step's PR flips both to
`Complete — …` (the project roadmap's with its row in the "Phase Complexity
Summary" table and the header `> **Status:**` line) and appends ` ✅` to this
file's `# ` title and to the project roadmap's `### Phase 2` heading, so the
project roadmap shows a finished phase the way this file shows a finished step.
There is no separate "update the roadmaps" chore: a step whose PR merged without
its Status line is a lifecycle violation, and the next step's Stage 1 (and
`/roadmap-step`) refuses to start until the previous step reads `Complete`. If a
post-merge check fails — a Deployed & verified bullet, a live smoke that never
ran green — the step is NOT complete despite the merged line; say so, and the
`hotfix/` PR that completes it appends its own number to the line.
`grep -n '^\*\*Status:\*\*'` on this file is the phase's progress report, and
the ✅ headings are the same report at a glance.

**Step lifecycle.** Every step in this phase follows the exact same six-stage
lifecycle, in order, with no exceptions. Each stage is a hard checkpoint — if a
stage is skipped, branch protection or the next step's Stage 1 will fail loudly,
and that is the safety net. AI coding agents MUST execute all six stages before
declaring a step complete.

1. **Create the branch.** Before any Read / Edit / Bash, run `git checkout -b
   feature/phase02-step<M>-<slug>` from a clean, up-to-date `main`. The exact
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
   `**Status:**` line (directly under its heading) to
   `Complete — PR #<n> (<YYYY-MM-DD>)`, append ` ✅` to the step's `## Step`
   heading, set its Summary Table Status cell to `Complete — PR #<n>`, commit
   that edit on the step branch (`docs: mark Phase 2 Step <M> complete`), and
   push — the PR now carries its own completion mark, so the roadmap on `main`
   will say the step is complete exactly when the PR merges (Status rule). On
   the phase's first step, the same commit sets this roadmap's phase-level
   `**Status:**` (under its title) and the project roadmap's Phase 2
   `**Status:**` to `In progress`; on the final step, both to `Complete`, with
   ` ✅` appended to this roadmap's `# ` title and to the project roadmap's
   `### Phase 2` heading.

4. **Wait for green checks, then squash-merge.** Every required status check
   must report success: the aggregate `gate` check of `ci.yml` (lint, typecheck,
   the test matrix, the package smoke, and the security scan) and the aggregate
   `phase-verify` check (`phase-verify (01)`, and `phase-verify (02)` from Step
   7). If the PR goes BEHIND main while waiting, refresh with
   `gh pr update-branch --rebase` — never merge `main` into the branch;
   `required_linear_history: true` enforces rebase. Once every check is green:

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
   for phase-boundary hygiene, the operator closes this Claude Code / Codex
   session and opens a fresh one before starting Step <M+1>; the new
   conversation begins again at Stage 1 of this lifecycle, with the next step's
   `**Branch:**` line driving the `git checkout -b` command. No work straddles
   two steps.

---

## Current State (as of Phase 1)

### Package and layer surface

- `src/weatherbot/` holds exactly the eight files Phase 1 Step 2 created:
  `__init__.py` (the version from package metadata), `__main__.py`, `py.typed`,
  and one `__init__.py` per layer (`cli`, `engine`, `services`, `sources`,
  `web`), each stating its layer's rule. The CLI is a Typer `app` with an eager
  `--version` and nothing else. `typer` is the only runtime dependency; `httpx`,
  `respx`, `pyshp`, and `shapely` sit in the `dev` group because only the
  development scripts and tests use them so far. The package version is
  `2.0.0.dev0`.
- `pyproject.toml` declares two import-linter contracts: the engine imports no
  other layer, and layers import downward only (`cli | web` over `services` over
  `sources | engine`). `tests/test_architecture.py` runs both and bans thirteen
  I/O roots (`httpx`, `sqlalchemy`, `alembic`, `sqlite3`, `socket`, `anthropic`,
  and others) from `src/weatherbot/engine`. `AGENTS.md` says the shared models
  get their own package, `weatherbot.models`, which Phase 2 creates and adds to
  the contracts as the lowest layer.
- Strict tooling applies to every new file: ruff `select = ["ALL"]` with
  reasoned ignores only, pyright strict over `src`, `tests`, and `scripts`,
  `filterwarnings = ["error"]`, pytest-socket's `--allow-hosts=127.0.0.1,::1`,
  the `live` and `corpus` markers, and an autouse fixture that runs every test
  in its own temporary working directory. Every new Python, YAML, and TOML file
  starts with a `# <repo-relative path>` comment.

### Source register and fixture surface

- `docs/DATA_SOURCES.md` was verified live on 2026-10-12. It lists 18 source
  ids, 16 of them with fixture class `required`; the shared ArcGIS query
  parameters (`where=1=1`, `outFields=*`, `outSR=4326`, `f=geojson`,
  `geometryPrecision=5`) and paging on `exceededTransferLimit`; the User-Agent
  `weatherbot/2.0.0.dev0 (+https://github.com/nathanramoscfa/weatherbot)`, which
  "Step 5's recorder and Phase 2's clients share"; the fields each layer carries
  and the fields v2 uses; the per-basin answer on arrival-time,
  probabilistic-wind, and surge layers (answered for the Eastern Pacific, open
  for the Atlantic and the Central Pacific); the decision to read text products
  from the NWS API; and the sources v2 does not use. A field appears there only
  if a live response contained it, and the register states no field's unit: not
  the roster's `intensity`, `pressure`, or `movementSpeed`, nor the forecast
  points' winds and pressure, nor the wind-radii quadrant extents.
- `scripts/record_fixtures.py` is the synchronous precedent the clients
  generalize: `USER_AGENT`, `HOST_INTERVALS` (1.2 s for `api.weather.gov`, 1.5 s
  for Nominatim, 0.5 s otherwise), `REQUEST_TIMEOUT`, retries with backoff,
  `QUERY_PARAMETERS`, `MAP_SERVICES`, `resolve_layer`, `check_query_result`, the
  header allowlist, and `SOURCES`. It is a development script; nothing in it is
  package code.
- `tests/fixtures/recorded/` holds a capture of every `required` source from
  2026-10-12, about 8 MiB of its 25 MiB budget: one active storm, `EP202026`
  Simon in slot `EP5`, whose cone, points, and watch-warning lines were
  intermediate advisory 22A while its arrival-time lines belonged to full
  advisory 22, beside the wind-speed probabilities of the 2026-10-12 18:00 UTC
  synoptic time; Atlantic and Pacific outlook areas; the Miami-Dade landmark's
  NWS point, zone alerts, and zones (the `FLC086` and `FLZ173` alert captures,
  taken at 01:09 UTC on 2026-10-13, hold no features: the Coastal Flood
  Statement the register saw on `FLC086` at verification had expired, so no
  recorded alert exists yet); the Nassau landmark's documented 404 and 400
  answers; and the six 2025 outlook maps harvested from v1 reports.
  `tests/contract/fixture_support.py` holds the shared readers
  (`capture_directories`, `latest_live`, `register_rows`, `register_layers`,
  `register_user_agent`).
- This capture set is the only one with an active storm's products. Re-recording
  every source on a later, quieter date would delete the storm-layer captures
  that the contract tests need, so Phase 2 adds captures for new sources and
  keeps the 2026-10-12 set.
- `tests/fixtures/replay/` holds the replay corpus: every advisory of Irma,
  Dorian, Ian, and Milton as GeoJSON-shaped collections in the archive's native
  D_Sphere, each with `source_crs`, under a 10 MiB budget, and
  `corpus-manifest.json` pins 1,199 archive files by SHA-256. The arrival-time
  KMZ and wind-speed-probability files live only in the git-ignored cache
  (`.cache/replay-corpus/`, or `WEATHERBOT_CORPUS_CACHE`).

### Persistence and configuration surface

- Nothing exists: no SQLAlchemy, Alembic, or `platformdirs` dependency, no
  configuration file, and no database. v1's `.env` (ignored) still holds the
  operator's coordinates and is only the source of the personal-data denylist.
  The ignore rules `/cache/`, `/reports/`, `/logs/`, and `/state/` are anchored
  to the repository root, so a fixture directory of the same name deeper in the
  tree stays tracked.

### CLI surface

- `weatherbot --version` and `--help` are the whole interface.
  `tests/test_cli.py` strips ANSI escapes, because GitHub's runners force color
  in Typer's help.

### Security & sensitive-data surface

- Data in play: the operator's location coordinates enter the system for the
  first time. They arrive only through `locations add` (Step 6), live in the
  local database in the operator's data directory, and are sent to
  `api.weather.gov` (`/points/{lat},{lon}`, `point=`) and to Nominatim (`lat`,
  `lon`) in request URLs. They never enter the repository, a fixture, a test, a
  log line above DEBUG, an exception message, or a conversation. Phase 2
  introduces no secret: every source is keyless.
- Controls: the four-check gate in pre-commit and in CI's `security` job
  (gitleaks, bandit over `src` and `scripts`, pip-audit over `uv.lock` through
  `scripts/audit_deps.py`, and `scripts/check_personal_data.py` with rules R1 to
  R4); the two public landmarks in `scripts/public_landmarks.toml` (Miami-Dade
  County Hall and Parliament Square, Nassau); `synthetic_coordinates()` for
  tests that need a non-landmark coordinate; the denylist outside the
  repository; and `request_coordinates()`, which finds coordinates in `/points/`
  paths, `point=`, and `lat`/`lon` parameters.
- Patterns every step mirrors: tests and documentation use the landmarks or
  coordinates generated at run time, never a literal; a check's output names a
  rule and a path, never a value; network XML is parsed with `defusedxml`, never
  the standard library's parsers; a zip is read in memory with member-count,
  size, and path checks, as `scripts/fetch_replay_corpus.py` does; a URL taken
  from a payload is followed only when it matches an allowlisted pattern; and
  redirects are refused, as the recorder refuses them.

### Operations & observability surface

- Phase 2 adds no scheduled or unattended surface. Its runtime surfaces are
  local and on demand: the CLI and the SQLite database, whose health `doctor`
  reports (reachability, layer discovery, and the Alembic head). The GitHub
  surfaces are `ci.yml` and `phase-verify.yml` (both required), the twice-weekly
  `replay-corpus.yml`, Dependabot, and, from Step 2, `live-smoke.yml`. That
  workflow runs only when dispatched; its signal is the run status, and a failed
  run reaches the operator through GitHub's failure email. Detecting source
  drift without a human is Phase 4's heartbeat and staleness work.

### Documentation surface

- `README.md` is a v2 status page with the disclaimer and a development
  quickstart; `CONTRIBUTING.md` documents the checks and the security gate;
  `AGENTS.md` documents the layers and commands; `SECURITY.md` names private
  vulnerability reporting; `CHANGELOG.md` has an `[Unreleased]` section with
  Phase 1's entries. No document describes a user-facing command yet; Phase 2
  adds a short "Commands" section to the README and the JSON Schemas under
  `docs/schema/`, and Phase 8 writes the user guide.

### Verification surfaces

- `scripts/verify_phase01.py` is the structural template: 50 numbered static
  checks that read the repository only, the modes `--fast`, `--py`, `--corpus`,
  `--security`, `--all`, and `--post`, and a 25-row V-matrix (75 checks in
  `--post`). `.github/workflows/phase-verify.yml` runs matrix entry `"01"`
  (`--fast` and `--security`), and its aggregate `phase-verify` check is
  required on `main` beside `gate`. `tests/test_phase01_verification.py` runs
  `--fast` in CI.
- Checks 7, 9, and 12 pin Phase 1's version (`2.0.0.dev0`), its exact eight-file
  skeleton, and `typer` as the only runtime dependency. The first module or
  runtime dependency Phase 2 adds turns entry `"01"` red unless those checks
  read their facts from `v2.0.0-phase-1`; Step 1 makes that change. Entry `"01"`
  and its 50 numbered checks stay in the matrix, and Step 7 adds `"02"`.

### Carry-over from Phase 1

Every item Phase 1 handed to this phase, and where it lands:

| Item | Source | Destination in Phase 2 |
| ---- | ------ | ---------------------- |
| Phase 1's exact version, skeleton, and Typer-only checks become historical checks against `v2.0.0-phase-1`; live security, provenance, and fixture checks stay live; entry `"01"` stays | Project roadmap, Phase 2; `docs/phase01-qa-findings.md`, Step 7 | Step 1 |
| Shared domain models in `weatherbot.models`, the lowest layer of the contracts | Phase 1 Not in scope; `AGENTS.md` | Step 1 |
| Arrival-time lines need a date and a time zone | Issue #11 | Step 1 (model and rule), Step 3 (client, register row, contract test; closes #11) |
| Wind-speed probabilities: snapshot or storm | Issue #12 | Step 1 (model), Step 2 (client and contract test; closes #12) |
| County-zone alerts outside the location's forecast zone | Issue #10 | Step 4 keeps `found_by`, `affectedZones`, and `geocode` on every alert; the rule stays with Phase 3 |
| A manually triggered live-smoke CI job for the clients | Phase 1 Not in scope | Step 2 (workflow); Steps 3, 4, and 6 (live tests) |
| Clients reuse the register's query parameters, User-Agent, source ids, and fixtures | QA ledger, pre-ship items | Steps 2 to 4 |
| Off-season roster and slot shapes have synthetic coverage only | QA ledger, Step 5 | Step 2 (empty roster), Step 3 (RSS placeholder item); a live off-season capture is re-recorded under Source drift when observed |
| Atlantic and Central Pacific per-basin rows open; peak-surge fields unknown | Register; QA ledger | Any step that runs while a storm is active in an open basin re-checks that row live and records it with its date (Step 3 owns the register amendment); the peak-surge client keeps raw features until a capture with features fixes the schema |
| NWS may replace its User-Agent rule with an API key | QA ledger, Step 4 | Step 4 stops and opens an issue if a key is required; no key handling in Phase 2 |
| Dependabot PRs #8 and #9 | QA ledger | Independent maintenance, outside every step |

---

## Execution Order

```
Step 1  (domain models)                   weatherbot.models + models layer
                                          + Phase 1 historical checks
                                          → implement
  ↓
Step 2  (HTTP + NHC map clients)          sources.http + roster + ArcGIS
                                          + map clients + live-smoke.yml
                                          → implement
  ↓
Step 3  (NHC products)                    arrival-time KMZ (#11) + text,
                                          graphics, RSS, catalogs
                                          → implement
  ↓
Step 4  (NWS + geocoding)                 points, merged alerts (#10
                                          inputs), zones, Nominatim
                                          → implement
  ↓
Step 5  (persistence + configuration)     platformdirs paths + SQLite +
                                          Alembic baseline + backup + cache
                                          → implement
  ↓
Step 6  (services + CLI)                  snapshot service + locations,
                                          fetch, storms, alerts, doctor
                                          → implement
  ↓
Step 7  (QA + verify_phase02.py)          scripts/verify_phase02.py
                                          + docs/phase02-qa-findings.md
                                          + phase-verify.yml entry "02"
                                          → create

--- post-implementation ---

V1  The models round-trip, encode #11 and #12, sit at the
    bottom of the layers; Phase 1's checks are historical.
V2  The HTTP layer paces, retries, and redacts; every roster
    and map capture parses; live-smoke.yml runs green.
V3  The arrival KMZ resolves labels to instants; text,
    graphics, RSS, and catalog captures parse.
V4  NWS alerts merge with found_by and zones kept; the non-US
    path is typed; Nominatim runs once per location.
V5  Migrations upgrade from empty and from every revision,
    back up first, and ship in the wheel.
V6  storms, alerts, fetch, locations, and doctor run live;
    every --json validates against its committed schema.
V7  verify_phase02.py --fast and --security exit 0 in
    phase-verify (02); the phase is closed.
```

Steps are sequential by dependency. Step 1's models are the return types of
every client in Steps 2 to 4, and its historical checks must land before any of
them, or the first new module turns `phase-verify (01)` red; Step 2's HTTP
layer, User-Agent constant, and ArcGIS client carry every later client, and its
`live-smoke.yml` is where Steps 3, 4, and 6 add their live tests; Step 3
completes the NHC products and amends the register; Step 4 adds the sources that
take a location's coordinates, after the redaction Step 2 builds; Step 5 stores
the models and raw responses the clients produce and gives the HTTP layer its
persistent validator store; Step 6 composes every client and the database into
the commands; Step 7 verifies every prior step. Steps 3 and 4 touch disjoint
sources, but both edit the register, the shared contract tests, and
`CHANGELOG.md`, so this phase draws no steps in parallel, and the Worktree rule
permits no concurrent steps.

---

## Step 1 — Domain models ✅

**Status:** Complete — PR #20 (2026-10-16)

> **Goal:** Create `weatherbot.models`, the typed vocabulary every later layer
> shares, and keep Phase 1's verification green while the package grows. Frozen,
> strict Pydantic v2 models in `src/weatherbot/models/` give every record a
> `Provenance`; geometry is a GeoJSON-shaped value with an explicit `crs`,
> checked by Shapely and never relabeled; instants are timezone-aware UTC, with
> NOAA's local text kept beside them and parsed only by the tested functions of
> `weatherbot.models.times`; a unit is part of a field name only where an
> official statement names it; unknown official codes keep their raw value;
> `ArrivalTimeProduct` and `WindProbabilityProduct` encode the decisions on
> issues #11 and #12; `weatherbot.models` becomes the lowest layer of the import
> contracts, with the engine's I/O ban extended to it; `pydantic` and `shapely`
> join the runtime dependencies; and checks 7, 9, and 12 of
> `scripts/verify_phase01.py` read Phase 1's version, skeleton, and dependency
> list from `v2.0.0-phase-1`. This step lands the vocabulary; Steps 2–4 parse
> recorded payloads into it, Step 5 stores it, and Step 6 prints it.

**Branch:** `feature/phase02-step1-domain-models`

**Deploys:** GitHub Actions → `phase-verify (01)` runs the historical checks
from the merge on; its first run on `main` must be green.

| Setting      | Cost                                    | Balanced                                 | Quality                                  |
| ------------ | --------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Model        | GPT-6.1 Sol                             | Opus 5.5                                 | Opus 5.5                                 |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh |
| Platform     | Codex                                   | Claude Code                              | Claude Code                              |
| Effort       | Intelligence High                       | Effort High                              | Effort XHigh                             |
| Thinking     | —                                       | On                                       | On                                       |
| Conversation | **New**                                 | **New**                                  | **New**                                  |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

> Ran 2026-10-16: Balanced — Opus 5.5 · Effort High. The **Runs:** column; the Claude weekly pool's `tight` row had passed its reset (Tue 2026-10-13 20:00 EDT), so it read `headroom`.

**Model rationale:** Step 1 is coding — models, their tests, and a verifier
change — with planning as its secondary category, because its field choices fix
what three later phases read. Its overall complexity is High: many interacting
concerns (CRS provenance, NOAA's time formats, units, unknown codes, two issue
decisions) across a cross-cutting scope; it is not novel, because this roadmap
writes each decision down. The columns differ in depth: Balanced runs Opus 5.5,
S-tier in coding and planning, on Claude Code at Effort High, one rung above its
documented `medium` default, with thinking on; Quality runs the same model at
Extra High for the closest audit of every field against the register; Cost moves
the step to GPT-6.1 Sol on Codex at Intelligence High, S-tier in agentic work
and A-tier in coding. The claude.ai Max subscription funds Claude Code and
ChatGPT Pro 5x funds Codex, so each column costs nothing at the margin while its
pool has headroom, and each backup comes from the other maker. The conversation
is new per phase-boundary hygiene.

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
       feature/phase02-step1-domain-models`
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
       Phase 2 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 2`
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

    THIS STEP adds `pydantic` and `shapely` to the runtime set,
    so `scripts/audit_deps.py` must pass on the new lock. The
    models will hold the operator's coordinates at run time:
    `Location.point`, `Location.polygon`, and `Provenance.url`
    stay out of `repr`, and a test proves it with coordinates
    from `synthetic_coordinates()`. Tests and docstrings hold no
    coordinate literal other than a landmark (rule R2 scans
    tests). The verifier change reads Git history only and
    prints no file content.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 2 (Sources and
    persistence). Step 1: Domain models.

    Current state (as of Phase 1; no Phase 2 step has run):

    - `main` is protected and requires `gate` (`ci.yml`) and
      `phase-verify` (`phase-verify.yml`, matrix entry `"01"`).
      `src/weatherbot/` holds the eight-file skeleton; `typer`
      is the only runtime dependency, and `shapely` sits in the
      `dev` group for the replay tests.
    - `docs/DATA_SOURCES.md` lists, per layer and endpoint, the
      fields present and the fields v2 uses. Fields the models
      need are exactly the "Fields v2 uses" columns, plus the
      roster's product objects Step 2 adds to that list; a field
      never observed live is not modelled. The register states
      no unit for any field.
    - Recorded facts the models must represent
      (`tests/fixtures/recorded/`, 2026-10-12): the `EP5` cone,
      points, and watch-warning lines carry `advisnum` `22A` and
      `advdate` `500 PM MST Mon Oct 12 2026`; the forecast
      points carry `validtime` `12/2100` (UTC) and `timezone`
      `MST`; the arrival-time lines carry labels such as
      `Mon 8 pm` and `Tue 8 am` from advisory 22
      (`EP202026_022adv_earliest_reasonable_toa_34`), one with a
      blank label; the probabilistic-wind bands read `<5%`,
      `5-10%`, `10-20%` with `idp_source`
      `2026101218_wsp34knt120hr_5km` and no storm field; the
      outlook areas carry `prob2day` `20%` and `risk2day` `Low`;
      the roster carries `intensity` `"85"`, `pressure` `"969"`,
      `movementSpeed` 3, and `publicAdvisory.advNum` `022a`; the
      register describes a county alert with `affectedZones`
      URLs and `geocode` `SAME` and `UGC` lists, but the
      recorded zone-alert captures hold no features.
    - The replay subset (`tests/fixtures/replay/`) keeps the
      archive's native D_Sphere with the WKT in each
      collection's `source_crs`, and Dorian 056–062A keeps 39
      one-vertex watch-warning records as Points with
      `source_geometry` and `geometry_note`.
    - `scripts/verify_phase01.py` checks 7, 9, and 12 compare
      the working tree with Phase 1's exact version, the
      `SKELETON` set, and a Typer-only dependency list; the
      first module this step adds turns entry `"01"` red unless
      they change. CI's `test` job and `phase-verify.yml` check
      out with `fetch-depth: 0`, so tags are present.

    Files to read (every file before drafting):
    - docs/roadmap/phase02-roadmap.md (Overview and its design
      rationale, Current State, this step, and the goals of
      Steps 2–6, which consume these models).
    - docs/roadmap/ROADMAP.md (Phase 2; Phase 3 sections 3.2 and
      3.3, for what the engine reads).
    - docs/brief/weatherbot-v2-brief.md (§6 architecture, §7 the
      ladder's inputs and outputs).
    - docs/DATA_SOURCES.md (whole: the fields each model
      carries).
    - Issues #11 and #12 (`gh issue view 11`,
      `gh issue view 12`).
    - AGENTS.md, pyproject.toml, tests/test_architecture.py,
      tests/conftest.py.
    - scripts/verify_phase01.py,
      tests/test_phase01_verification.py,
      docs/phase01-qa-findings.md.
    - tests/fixtures/replay/NOTICE.md and the `source_crs` of
      one replay collection.
    - The `*.shp.xml` field metadata in one archived `_5day_`
      and one `_fcst_` package in `.cache/replay-corpus/` (run
      `uv run python scripts/fetch_replay_corpus.py fetch` if
      the cache is absent), read in memory, and NHC's
      description of `CurrentStorms.json`, for the units.
  </context>

  <goal>
    Ship `weatherbot.models` with every public model below,
    frozen and strict, round-tripping through JSON and producing
    JSON Schemas; the time, geometry, and code-value rules as
    tested functions; `weatherbot.models` as the lowest import
    layer under the I/O ban; and Phase 1's version, skeleton,
    and dependency checks reading `v2.0.0-phase-1`, so both
    phase-verify entries stay green.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Dependencies. Add `pydantic` (2.x) and `shapely` to
      `[project] dependencies` and remove `shapely` from the
      `dev` group, since the models check geometry at run time.
      Run `uv lock`; `scripts/audit_deps.py` must pass. Add
      nothing else at run time in this step: `httpx` moves in
      Step 2, `defusedxml` arrives in Step 3, and the database
      libraries in Step 5.
    </requirement>

    <requirement>
      Layout. `src/weatherbot/models/__init__.py` states the
      layer's rule in its docstring (the lowest layer: no I/O
      library and no other `weatherbot` layer) and lists every
      public name in `__all__`. Modules by topic:
      `provenance.py`, `geometry.py`, `times.py`, `location.py`,
      `storms.py`, `outlook.py`, `alerts.py`, `products.py`,
      `snapshot.py`. Module boundaries may move; the public
      names below may not.
    </requirement>

    <requirement>
      Conventions for every model:
      - One base class with `ConfigDict(frozen=True,
        extra="forbid", strict=True)`. JSON enters through
        `model_validate_json`, where strict mode still accepts
        ISO 8601 instants (a test proves it); a field turns lax
        only with a comment saying why.
      - Field names are snake_case. A unit is part of a name
        only where an official statement names it: NHC's
        description of `CurrentStorms.json`, or the field
        metadata (`*.shp.xml`) inside the archived forecast
        packages in the replay cache. Record each unit adopted,
        with its source, in the matching section of
        `docs/DATA_SOURCES.md`, dated with this step's date. A
        field whose unit no official statement gives keeps a
        unit-free name (`movement_speed`, `ne_extent`). The
        names below (`intensity_kt`, `pressure_mb`,
        `max_wind_kt`, `gust_kt`, `mslp_mb`) assume the
        statement exists; without it, they lose the suffix.
      - A value from a closed official vocabulary is a coded
        value: the raw string, the matching enum member, and
        `recognized`. Storm classification, watch-warning `tcww`
        (at least `HWA`, `HWR`, `TWA`, `TWR`), outlook risk
        (`Low`, `Medium`, `High`), and the CAP fields of an
        alert are coded. An unknown code parses with
        `recognized` false and its raw value; it is never
        dropped.
      - No model holds an operator's value by default, and no
        model name, default, or docstring names a storm, a
        season, or a place beyond the public landmarks.
    </requirement>

    <requirement>
      `Provenance`: `source_id` (a `SourceId` literal of the
      register's ids; a test keeps the literal equal to the
      register's Source id column), `url` (excluded from `repr`,
      because an NWS or Nominatim URL holds a location's
      coordinates), `status`, `fetched_at`, `sha256` (of the
      bytes as received), `issued_at` (the product's own
      issuance, when it states one), `advisory`
      (`AdvisoryNumber` or `None`), `etag`, `last_modified`, and
      `not_modified` (a 304 reused the stored body). Records
      parsed from one response share its provenance.
    </requirement>

    <requirement>
      Time (`times.py`). Instants are aware `datetime` values in
      UTC; a validator rejects naive values and normalizes aware
      ones to UTC. NOAA's local text stays beside an instant in
      a `*_local_text` field and is parsed only by these
      functions, each tested on recorded examples:
      - `parse_nhc_local_time(text)`:
        `500 PM MST Mon Oct 12 2026`,
        `500 AM EDT Mon Sep 02 2019`, through one explicit table
        of the abbreviations NHC uses in the three basins — AST
        −4, EDT −4, EST −5, CDT −5, CST −6, MDT −6, MST −7, PDT
        −7, PST −8, HST −10 — plus `UTC` and `GMT`. An
        abbreviation outside the table yields no instant, never
        a guess.
      - `resolve_track_valid_time(text, anchor)`: `validtime`
        `DD/HHMM` (UTC) becomes the one instant with that day
        and time in [anchor − 1 day, anchor + 8 days], where the
        anchor is the advisory's UTC issuance; none or two is an
        error.
      - `parse_synoptic_time(text)`: `YYYYMMDDHH` (UTC), and the
        leading stamp of an `idp_source` such as
        `2026101218_wsp34knt120hr_5km`.
      - `from_epoch_ms(value)`: `idp_filedate` and
        `idp_ingestdate`.
      - `resolve_arrival_label(label, published_at, zone)`, the
        issue #11 rule: parse `Ddd H am|pm` and
        `Ddd H:MM am|pm`, ignoring case; return the first
        instant at or after `published_at` whose local weekday
        and clock time in `zone` match, provided it lies within
        120 hours of `published_at`. A label that does not
        parse, an unknown zone, or an instant beyond the horizon
        resolves to `None` with a reason.
    </requirement>

    <requirement>
      Geometry (`geometry.py`). `Geometry` holds `type`
      (`Point`, `MultiPoint`, `LineString`, `MultiLineString`,
      `Polygon`, `MultiPolygon`), `coordinates`, and `crs`:
      `EPSG:4326` for live map queries (they ask for
      `outSR=4326`), NWS GeoJSON (RFC 7946), and KML (WGS 84 by
      its specification); or `native` with the replay
      collection's `source_crs` WKT, verbatim. Validation checks
      structure, finite numbers, closed rings, and longitude and
      latitude ranges for a geographic CRS; Shapely builds the
      shape, and the model records `is_valid` and Shapely's
      reason without changing a coordinate (repair is Phase 3's,
      project roadmap 3.1). Provide `from_geojson(mapping, crs)`
      and `to_shapely()`. No function relabels a CRS or
      transforms a coordinate.
    </requirement>

    <requirement>
      `Location`: `name` (1–64 printable characters), `point`
      (latitude and longitude, WGS 84), `polygon` (`Geometry` or
      `None`: an NWS zone's shape when the operator asks for
      one), `country_code` (ISO 3166-1 alpha-2 from geocoding,
      or `None`), `display_name`, `nws` (`NwsCoverage`: forecast
      zone, county zone, office `cwa`, IANA `time_zone`, and
      `relativeLocation`'s city and state — the register's
      "Fields v2 uses" for `/points`; `None` when `/points`
      answers `InvalidPoint`), `breakpoint_span` (`None`; Phase
      3 defines and fills it), `evacuation_order_in_effect`
      (`False`; the brief's §4 toggle, which Phase 3's level-4
      rule reads), and the geocoding provenance. `point` and
      `polygon` are excluded from `repr`.
    </requirement>

    <requirement>
      Storms (`storms.py`):
      - `StormSummary` from the roster: `atcf_id` (upper case,
        `^(AL|EP|CP)\d{6}$`, from the roster's lower-case `id`),
        `slot` (`AT1`–`AT5`, `EP1`–`EP5`, `CP1`–`CP5`, from
        `binNumber`), `name`, coded `classification`,
        `intensity_kt` and `pressure_mb` (the roster's strings
        as integers), the center's `latitude` and `longitude`,
        `movement_dir_deg`, `movement_speed`, `last_update`, the
        public advisory's number and issuance, the track cone's
        advisory and issuance, the arrival-time KMZ links with
        their advisory and issuance, the wind-speed-probability
        issuance, and one flag per surge product (whether the
        roster's object is non-null).
      - `AdvisoryNumber`: an integer and an optional letter,
        parsed from `22A`, `022a`, `22`, and `022`, ordered
        (`22 < 22A < 22B < 23`), printed as NHC prints it
        (`22A`).
      - `Advisory` (`atcf_id`, `number`, `issued_at`,
        `local_text`); `ConeGeometry` (`forecast_period_h` from
        `fcstprd`, Polygon or MultiPolygon); `TrackPoint`
        (`tau_h`, `valid_at`, position, `max_wind_kt`,
        `gust_kt`, `mslp_mb`, `direction_deg`, `speed` — each
        `None` where NHC writes `9999` — `development`,
        `storm_type`, `saffir_simpson`, `label`);
        `ForecastTrack` (LineString); `WatchWarningSegment`
        (coded `tcww`, LineString, or Point with the replay
        corpus's `geometry_note`); `WindRadii` (`threshold_kt`
        34, 50, or 64 from `radii`, `tau_h`, `valid_at`,
        `synoptic_at`, unit-free `ne_extent`, `se_extent`,
        `sw_extent`, `nw_extent`, `is_advisory_field`). Each
        carries `atcf_id`, its advisory, and provenance.
    </requirement>

    <requirement>
      Arrival times (issue #11). `ArrivalTimeProduct`:
      `atcf_id`, `advisory` (a full advisory), `kind`
      (`earliest_reasonable` or `most_likely`), `time_zone` (the
      abbreviation, or `None`), `published_at` and
      `published_local_text` (from `pubAdvTime`, or `None`),
      `origin` (`kmz` or `map_layer`), and `lines`, each an
      `ArrivalTimeLine`: `label` (or `None`), `is_outer_contour`
      (the "Wind Speed Probability 5% contour", which has no
      time), `valid_at` (or `None`), `unresolved_reason`, and a
      LineString or MultiLineString. A `map_layer` product never
      carries a zone or an instant. A `kmz` product resolves
      every labelled line through `resolve_arrival_label`. The
      class docstring cites issue #11 and the evidence in this
      roadmap's design rationale.
    </requirement>

    <requirement>
      Outlook and wind probabilities (issue #12). `OutlookArea`:
      `kind` (`two_day_location`, `seven_day_location`,
      `development_region`, `development_motion`), `basin` (the
      layer's text, such as `Atlantic` or `Pacific`),
      `chance_2day_pct` and `chance_7day_pct` (from `20%`),
      coded `risk_2day` and `risk_7day`, `outlook_stamp`
      (`idp_source`), `issued_at` (from `idp_filedate`), and
      geometry. `WindProbabilityProduct`: `threshold_kt` (34,
      50, or 64), `synoptic_at`, `horizon_h` (120), `resolution`
      (`5km`), and `bands`, each a `WindProbabilityBand`
      (`lower_pct`, `upper_pct` — `<5%` is [0, 5), `5-10%` is
      [5, 10), `>90%` is [90, 100] — `label`, and a Polygon or
      MultiPolygon). It has no storm field; its docstring cites
      issue #12. An unknown band label is a schema error.
    </requirement>

    <requirement>
      `NwsAlert` (`alerts.py`): the register's "Fields v2 uses"
      — `id`, `event`, `headline`, coded `severity`,
      `certainty`, `urgency`, `status`, `message_type`, and
      `category`, the instants `sent`, `effective`, `onset`,
      `expires`, and `ends` (`ends` and `onset` may be `None`),
      `area_desc`, `sender_name`, `references` (alert ids),
      `vtec`, `nws_headline`, `description`, `instruction` —
      plus `affected_zone_ids` (the last path segment of each
      `affectedZones` URL), `geocode_same`, `geocode_ugc`,
      `geometry` (`None` when the alert has none), and
      `found_by`: a non-empty tuple of `AlertQuery` values
      (`point`, or `zone` with its id). The last four are issue
      #10's inputs; Phase 3 decides what they mean. Beside it:
      `NwsZone` (`id`, `type`, `name`, `state`, `cwa`,
      `time_zone`, `effective_date`, and the zone's Polygon or
      MultiPolygon) and `GeocodeResult` (`display_name`, `name`,
      `country_code`, `country`, `licence`, `osm_type`,
      `osm_id`), the register's "Fields v2 uses" for `nws-zones`
      and `geocode-nominatim`.
    </requirement>

    <requirement>
      Products and catalogs (`products.py`): `TextProduct`
      (`product_id`, `code` TCP or TWO, `location` slot or basin
      code, `wmo_collective_id`, `issuing_office`, `issued_at`,
      `text`, and the `atcf_id` and `advisory` a TCP's header
      names, `None` for a TWO); `GisFeedItem` (`feed`, `guid`,
      `title`, `link`, `published_at` or `None`,
      `is_placeholder` for "There are no tropical cyclones at
      this time.", `atcf_id`, `slot`); `OutlookGraphic` (`basin`
      `atl`, `pac`, or `cpac`, `horizon` `2d0` or `7d0`,
      `width_px`, `height_px`); `Breakpoint` (`name`, `state`,
      `country`, and a Point built from the layer's `lat` and
      `lon` fields, since its features' geometry is null);
      `MapCatalog` (service, read time, and per layer its id,
      name, type, geometry type, and group path — ids valid for
      that read only); `OverlayCatalog` (service, layer names,
      each layer's `time` default); and `DisplayLayer` (layer
      name, the raw FeatureCollection as received, provenance)
      for layers v2 shows but does not interpret: past points
      and track, the wind swath, and peak surge until a capture
      with features fixes its fields.
    </requirement>

    <requirement>
      `Snapshot` (`snapshot.py`): `snapshot_id` (UUID),
      `started_at`, `completed_at`, `storms`, each storm's
      advisory products (cone, track points, track,
      watch-warning segments, wind radii, arrival-time
      products), `outlook_areas`, `wind_probabilities` (one
      product per threshold, held by the snapshot),
      `text_products`, `gis_feed_items`, `outlook_graphics`,
      `breakpoints`, `display_layers`, `alerts` keyed by
      location name, and `source_outcomes`: one `SourceOutcome`
      per source the snapshot asked for (`ok`, `not_modified`,
      `failed` with an error kind, or `skipped` with a reason).
      A derived `status` reads `complete`, `partial`, or
      `failed` (the roster failed). Nothing in a snapshot stands
      in for a source it did not fetch.
    </requirement>

    <requirement>
      Every public model round-trips
      (`model_validate_json(m.model_dump_json()) == m`) and
      produces a JSON Schema through `model_json_schema()`; Step
      6 publishes schemas built from them.
    </requirement>

    <requirement>
      Tests in `tests/models/`:
      - construction from minimal data for every public model;
        rejection of naive instants, extra fields, out-of-range
        coordinates in a geographic CRS, and mutation; coded
        values with an unknown code;
      - `repr` of `Location` and `Provenance` contains no
        coordinate digits, with coordinates from
        `synthetic_coordinates()` in
        `scripts/check_personal_data.py`, never a literal;
      - `times.py` on recorded examples: the recorded labels
        `Mon 8 pm` and `Tue 8 am` resolve against
        `200 PM MST Mon Oct 12 2026` to the instants the test
        lists; a label 120 hours or more after publication and
        an unknown zone stay unresolved; a `Sat 11 pm`
        publication resolves `Mon 2 am` across the week
        boundary; `validtime` `01/1800` after an issuance on the
        31st lands in the next month; the recorded `idp_source`
        stamps and epoch milliseconds parse;
      - `AdvisoryNumber` parsing and ordering; band parsing for
        every recorded label;
      - JSON round trip and schema generation for every public
        model.
    </requirement>

    <requirement>
      Architecture. Add `"weatherbot.models"` as the lowest
      entry of the "Layers import downward only" contract, and
      extend `tests/test_architecture.py` so the I/O ban also
      scans `src/weatherbot/models/`. Prove both with throwaway
      probes — `import weatherbot.sources` in a model module
      fails `lint-imports`, and `import httpx` there fails the
      AST test — then revert them and record both in the PR
      body. Update `AGENTS.md`: `weatherbot.models` exists and
      is the lowest layer.
    </requirement>

    <requirement>
      Phase 1's checks become historical. In
      `scripts/verify_phase01.py`, keep the numbering and the
      count of 50, and change:
      - check 7: live — name `weatherbot`,
        `requires-python >=3.13`, build backend `uv_build`;
        historical — `git show v2.0.0-phase-1:pyproject.toml`
        has version `2.0.0.dev0`;
      - check 9: historical — `git ls-tree -r --name-only
        v2.0.0-phase-1 -- src/weatherbot` equals the eight-file
        skeleton; live — every skeleton file is still tracked;
      - check 12: historical — at the tag,
        `[project] dependencies` is one `typer` entry; live —
        `[project.scripts] weatherbot` is `weatherbot.cli:app`
        and a `typer` dependency remains.
      A missing tag or a failed `git` call is a FAIL, never a
      PASS; each description names the tag. `--fast` stays
      standard-library-only and under 30 seconds, and `--post`
      still reports 75 checks. Parameterize the helpers by
      repository root, and add tests to
      `tests/test_phase01_verification.py` that build a
      throwaway repository in `tmp_path` with `git init`, commit
      a skeleton, tag it `v2.0.0-phase-1`, and prove each
      historical check passes on a grown tree and fails when the
      tagged tree differs. Set this PR as the destination of the
      Step 7 row in `docs/phase01-qa-findings.md` that names
      this obligation.
    </requirement>

    <requirement>
      `CHANGELOG.md` `[Unreleased]`: an `Added` entry for
      `weatherbot.models` and a `Changed` entry for the
      historical Phase 1 checks. The PR body references issues
      #11 and #12 without a closing keyword: Step 3 closes #11
      and Step 2 closes #12, each once a recorded capture parses
      into these models.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with a `# <repo-relative path>` comment; Markdown
      files follow their siblings in `docs/`, which carry none.
    </requirement>
  </requirements>
</task>
```

### Step 1 acceptance criteria

- `weatherbot.models` exports every public name this step's task lists; every
  model is frozen, forbids unknown fields, round-trips through JSON, and
  produces a JSON Schema, and `tests/models/` passes on both runners.
- `resolve_arrival_label` resolves the recorded labels against
  `200 PM MST Mon Oct 12 2026` to the instants the test lists and leaves an
  unknown zone or an out-of-horizon label unresolved; `ArrivalTimeProduct`
  carries `time_zone`, `published_at`, `origin`, and a `valid_at` per line.
- `WindProbabilityProduct` has no storm field and lives in
  `Snapshot.wind_probabilities`; every `Geometry` carries a `crs`, and no
  function relabels a CRS or transforms a coordinate.
- `lint-imports` places `weatherbot.models` at the bottom of the layers and the
  I/O ban scans it; the two throwaway probes failed and were reverted, as the PR
  body records.
- `uv run python scripts/verify_phase01.py --fast` passes with checks 7, 9, and
  12 reading `v2.0.0-phase-1`; the throwaway-repository tests prove each fails
  when the tagged tree differs; `--post` still counts 75 checks.
- **Deployed & verified:** the first `phase-verify.yml` and `ci.yml` runs on
  `main` after the merge are green (`gh run list --workflow phase-verify.yml
  --branch main --limit 1`, and the same for `ci.yml`).
- **Security gate clean** (always the final criterion): the hook passed on every
  commit; pip-audit is clean with `pydantic` and `shapely` at run time; a test
  proves no `repr` of a `Location` or `Provenance` exposes a coordinate; and no
  test or docstring holds a coordinate literal other than a landmark.

---

## Step 2 — HTTP foundation and NHC map clients ✅

**Status:** Complete — PR #21 (2026-10-16)

> **Goal:** Build the network layer once, then the storm roster and map-service
> clients on it. `weatherbot.sources.http` holds the one `httpx.AsyncClient` a
> run uses: the register's User-Agent as the package constant
> `weatherbot.sources.USER_AGENT` (the fixture recorder imports it, with the
> shared query parameters and host intervals, instead of defining its own),
> per-host pacing, bounded retries with backoff and `Retry-After`, timeouts, a
> response size cap, refused redirects, conditional requests through a validator
> store (in memory here; Step 5 persists it), typed errors, and log lines that
> never carry a request coordinate above DEBUG.
> `weatherbot.sources.nhc_current_storms` parses the roster into `StormSummary`
> values; `weatherbot.sources.arcgis` reads a service catalog, resolves layers
> by exact name or group path, queries with the shared parameters, pages on
> `exceededTransferLimit`, and counts; `weatherbot.sources.nhc_map` parses every
> register layer of the tropical, summary, breakpoint, and peak-surge services
> into the Step 1 models, including the snapshot-level wind probabilities that
> close issue #12; a field-coverage contract keeps the parsers and the
> register's "Fields v2 uses" columns equal and fails when a recorded shape
> loses a field; and `.github/workflows/live-smoke.yml` runs the live suite when
> dispatched.

**Branch:** `feature/phase02-step2-nhc-map-clients`

**Deploys:** GitHub Actions → `live-smoke.yml` becomes dispatchable on merge
(`workflow_dispatch` only); a dispatch on `main` after the merge must run green.

| Setting      | Cost                                    | Balanced                                 | Quality                                  |
| ------------ | --------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Model        | GPT-6.1 Sol                             | Opus 5.5                                 | Opus 5.5                                 |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh |
| Platform     | Codex                                   | Claude Code                              | Claude Code                              |
| Effort       | Intelligence High                       | Effort High                              | Effort XHigh                             |
| Thinking     | —                                       | On                                       | On                                       |
| Conversation | **New**                                 | **New**                                  | **New**                                  |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

> Ran 2026-10-16: Balanced — Opus 5.5 · Effort High. The **Runs:** column; the Claude weekly pool's `tight` row had passed its reset (Tue 2026-10-13 20:00 EDT), so it read `headroom`.

**Model rationale:** Step 2 is coding with an agentic secondary — live probes
and a new workflow — at High complexity: pacing, retries, conditional requests,
paging, ten kinds of layer, and a contract that ties every parser to the
register interact, and every later client inherits the layer. It is not novel,
because the Phase 1 recorder already proves each request pattern synchronously.
The columns differ in model and depth: Balanced runs Opus 5.5 on Claude Code at
Effort High, one rung above its `medium` default, with thinking on; Quality runs
it at Extra High for the closest reading of the register against each parser;
Cost hands the step to GPT-6.1 Sol on Codex at Intelligence High, whose S-tier
agentic rating suits the live probing. The claude.ai Max subscription funds
Claude Code and ChatGPT Pro 5x funds Codex, and each column's backup comes from
the other maker. The conversation is new per phase-boundary hygiene.

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
       feature/phase02-step2-nhc-map-clients`
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
       Phase 2 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 2`
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

    THIS STEP builds the network layer every later client uses,
    so its defaults are the controls: TLS verification on,
    redirects refused, a response size cap, bounded retries, the
    register's pacing, and no coordinate in a log line above
    DEBUG or in any error message (tests prove it with
    `synthetic_coordinates()`). `httpx` moves to the runtime set
    and must pass pip-audit. The new workflow is a
    security-relevant diff: SHA-pinned actions,
    `contents: read`, no secret, dispatch only. This step's live
    tests send no coordinate at all.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 2 (Sources and
    persistence). Step 2: HTTP foundation and NHC map clients.

    Current state (as of Phase 2, post-Step 1):

    - `weatherbot.models` holds every model this step returns
      (`StormSummary`, `Advisory`, `ConeGeometry`, `TrackPoint`,
      `ForecastTrack`, `WatchWarningSegment`, `WindRadii`,
      `ArrivalTimeProduct`, `OutlookArea`,
      `WindProbabilityProduct`, `Breakpoint`, `MapCatalog`,
      `DisplayLayer`, `Provenance`), the time functions in
      `weatherbot.models.times`, and the lowest layer of the
      import contracts. Checks 7, 9, and 12 of
      `verify_phase01.py` are historical, so new modules and
      dependencies keep `phase-verify (01)` green.
    - Carry-over from Step 1 (2026-10-16). Field names follow
      the unit statements the register now records: the
      roster's `movementSpeed` is miles per hour
      (`StormSummary.movement_speed_mph`), while the forecast
      points' `tcspd` is knots (`TrackPoint.speed_kt`); wind
      radii extents are nautical miles (`ne_extent_nmi` ...
      `nw_extent_nmi`). The models are strict: a parser passes
      tuples, not lists (`Geometry.from_geojson(mapping, crs)`
      converts parsed GeoJSON), builds coded values with
      `.parse(raw)`, `AdvisoryNumber.parse`, and upper-cases
      the roster's ATCF id. `WindRadii.advisory` is an
      `AdvisoryNumber`, because the radii layers carry no
      `advdate`. The recorded forecast points' taus count from
      the synoptic time (tau 0 is the 21:00 position; tau 12
      is 06:00 the next day). Map-layer arrival lines are built
      with `ArrivalTimeLine.resolve(label, geometry,
      origin="map_layer")`, which turns the blank label into
      the outer contour. Validation errors never repeat their
      input (`hide_input_in_errors`).
    - `scripts/record_fixtures.py` is the synchronous precedent:
      `USER_AGENT`, `HOST_INTERVALS` (1.2 s for
      `api.weather.gov`, 1.5 s for Nominatim, 0.5 s otherwise),
      `REQUEST_TIMEOUT`, four attempts with backoff, the header
      allowlist, `QUERY_PARAMETERS`, `COUNT_PARAMETERS`,
      `resolve_layer`, and `check_query_result`, which refuses
      an ArcGIS error object and a truncated response.
    - The register's map-service facts (2026-10-12): ArcGIS
      11.3, `maxRecordCount` 2000; ids shift between reads, so
      layers resolve by exact name (group path for
      `StormSurgeRisk`); the tropical service's `/layers`
      document is 2.3 MB; an empty layer returns a 42-byte empty
      FeatureCollection; queries answer
      `max-age=0,must-revalidate` with an `ETag`; the summary
      service serves every slot product across storms, split by
      `binnumber`, byte-identical to the slot service for one
      storm; field order differs between slots, and
      `AT1 Advisory Wind Field` lacks `idp_source`;
      `Watch_Warning_Breakpoints` features have null geometry
      with the position in `lat` and `lon`; the peak-surge
      layers were empty. The roster answers `max-age=300` with
      `ETag` and `Last-Modified`, and a conditional request
      returned 304.
    - The recorded `EP5` storm products are advisory 22A (cone,
      points, track, watch-warning) and advisory 22
      (arrival-time layers); the probabilistic winds carry
      `idp_source` `2026101218_wsp34knt120hr_5km`, and the
      roster lists `windSpeedProbabilitiesGIS.issuance`
      `2026-10-12T18:00:00.000Z` under the storm.

    Files to read (every file before drafting):
    - docs/roadmap/phase02-roadmap.md (Overview, Current State,
      Step 1's requirements, this step, and Steps 3–6, which
      build on this layer).
    - docs/DATA_SOURCES.md (the roster, the map services, the
      shared query parameters, the per-basin section).
    - src/weatherbot/models/ (every module) and
      src/weatherbot/sources/__init__.py.
    - scripts/record_fixtures.py and
      tests/scripts/test_record_fixtures.py (constants to move,
      request patterns to generalize).
    - tests/contract/fixture_support.py,
      tests/contract/test_register.py,
      tests/contract/test_recorded_fixtures.py.
    - scripts/check_personal_data.py (`request_coordinates` and
      `synthetic_coordinates`).
    - pyproject.toml, .github/workflows/ci.yml (pinning and
      permission conventions), issue #12.
  </context>

  <goal>
    Ship the HTTP layer with its controls and tests, the roster,
    ArcGIS, and NHC map-service clients returning Step 1 models,
    a field-coverage contract over every recorded roster and map
    capture, the recorder reusing the package's constants, and a
    dispatch-only `live-smoke.yml` that runs green on `main`;
    close issue #12.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Dependencies. Move `httpx` from the `dev` group to
      `[project] dependencies`; `respx` stays in `dev`. Run
      `uv lock`; `scripts/audit_deps.py` must pass.
    </requirement>

    <requirement>
      One definition of each register constant.
      `weatherbot/sources/__init__.py` defines `USER_AGENT =
      f"weatherbot/{__version__}
      (+https://github.com/nathanramoscfa/weatherbot)"`, which
      equals the register's string while the version is
      `2.0.0.dev0`; `tests/contract/test_register.py` asserts
      the equality. `HOST_INTERVALS` moves to
      `weatherbot.sources.http`, and `QUERY_PARAMETERS` and
      `COUNT_PARAMETERS` to `weatherbot.sources.arcgis`.
      `scripts/record_fixtures.py` imports all four from the
      package and its tests still pass.
    </requirement>

    <requirement>
      The HTTP layer, `weatherbot/sources/http.py`:
      - `open_client()`: an async context manager yielding one
        `httpx.AsyncClient` with the User-Agent header,
        `follow_redirects=False`, TLS verification on (never
        `verify=False`), and a timeout of 30 seconds with a
        10-second connect timeout.
      - `Fetcher.get(url, *, source_id, accept=(200,),
        problems=(), max_bytes=...)` returns a `FetchResult`:
        URL, status, body, the recorder's allowlisted headers,
        fetched-at, SHA-256 of the body as received, and
        `not_modified`.
      - Pacing: one async pacer per host with `HOST_INTERVALS`;
        concurrent requests to one host leave in order at the
        host's interval; requests to different hosts do not wait
        for each other. Clock and sleep are injectable.
      - Retries: at most four attempts on transport errors, 5xx,
        and 429, with exponential backoff (1, 2, 4 seconds) and
        full jitter from an injectable random source; a
        `Retry-After` in seconds or as an HTTP date is honored
        up to 60 seconds; no other status is retried.
      - Size: the body streams into memory up to `max_bytes`
        (default 8 MiB) and raises `ResponseTooLarge` beyond it.
      - Conditional requests: a `ValidatorStore` protocol stores
        the ETag, the Last-Modified, and the last body per URL,
        with an in-memory implementation here. When the store
        holds validators, the request sends `If-None-Match` and
        `If-Modified-Since`, and a 304 returns the stored body
        with `not_modified=True` and its stored hash.
      - Errors (`weatherbot/sources/errors.py`): `SourceError`
        with `source_id` and `kind`, and `SourceUnavailable`
        (attempts exhausted), `SourceHttpError` (an undeclared
        status), `DocumentedProblem` (an
        `application/problem+json` answer whose status the
        caller declared, with its `type` and `title`),
        `SourceSchemaError` (a payload that breaks the
        register's shape), `ResponseTooLarge`, and
        `RedirectRefused` (naming only the target host). No
        message carries a query string or a path with
        coordinates.
      - Logging: logger `weatherbot.sources`. Records at INFO
        and above name the source id, the host, the path with
        coordinates redacted (`/points/<redacted>`, and the
        values of `point`, `lat`, and `lon` — every form
        `request_coordinates()` recognizes), the status, the
        byte count, and the elapsed time. Only DEBUG records may
        carry the full URL.
    </requirement>

    <requirement>
      Roster client, `weatherbot/sources/nhc_current_storms.py`:
      `fetch_current_storms(fetcher)` and the pure
      `parse_current_storms(body, provenance)`, returning
      `StormSummary` values. `{"activeStorms": []}` (off-season)
      parses to an empty tuple. Amend the roster's "Fields v2
      uses" in the register, with this step's date, to add the
      product objects the clients read: `trackCone.advNum` and
      `issuance`, `windSpeedProbabilitiesGIS.issuance`, and both
      arrival-time objects' `advNum`, `issuance`, and `kmzFile`.
    </requirement>

    <requirement>
      ArcGIS client, `weatherbot/sources/arcgis.py`:
      - `fetch_catalog(fetcher, service)` reads
        `<service>/MapServer?f=json` into a `MapCatalog`, once
        per service per run. `/layers?f=json` (2.3 MB) is read
        only by `doctor` and the tests, never per fetch.
      - `resolve(catalog, name)`: exactly one layer with that
        exact name, or, for a name containing ` / `, the group
        path from the service root; none or several raise
        `SourceSchemaError` naming the layer. An id is used
        within its run only.
      - `query(fetcher, service, layer_id)` sends the shared
        parameters; a 200 whose body is an ArcGIS
        `{"error": ...}` raises `SourceHttpError`; a
        FeatureCollection with `exceededTransferLimit: true`
        pages with `resultOffset`, `resultRecordCount` (the
        catalog's `maxRecordCount`), and
        `orderByFields=objectid` until a page arrives without
        the flag. `count(...)` sends `COUNT_PARAMETERS`.
    </requirement>

    <requirement>
      Map clients, `weatherbot/sources/nhc_map.py` (pure parsers
      plus fetch functions):
      - Storm products from `nhc-map-tropical-summary`, split by
        `binnumber` and joined to the roster's slots:
        `Forecast Cone` → `ConeGeometry`; `Forecast Points` →
        `TrackPoint` values, timed by `resolve_track_valid_time`
        against the advisory's issuance; `Forecast Track` →
        `ForecastTrack`; `Watch-Warning` → `WatchWarningSegment`
        values; `Forecast Wind Radii` and `Advisory Wind Field`
        → `WindRadii`; the two arrival-time layers → label-only
        `ArrivalTimeProduct` values (`origin` `map_layer`, issue
        #11's fallback); `Past Points`, `Past Track`, and
        `Past Cumulative Wind Swath` → `DisplayLayer` values.
        The inundation boundaries and footprint counts are read
        by `doctor` only.
      - The same parsers accept the slot service's `{slot} …`
        layers, so both services' recorded captures parse. The
        snapshot (Step 6) queries the summary service, one query
        per layer for every storm; the slot service serves
        `doctor`'s discovery.
      - An `Advisory` takes its number from `advisnum`, its
        local text from `advdate`, and its `issued_at` from the
        roster's issuance for that product (`trackCone.issuance`
        for the cone's advisory). If
        `parse_nhc_local_time(advdate)` differs from it by more
        than an hour, keep the roster's value and log a
        Source-drift warning.
      - The outlook layers of either service → `OutlookArea`
        values.
      - `Probabilistic Winds 34 kts`, `50 kts`, and `64 kts` →
        one `WindProbabilityProduct` per threshold, with
        `synoptic_at` from `idp_source`, held by the snapshot.
        When a roster storm lists
        `windSpeedProbabilitiesGIS.issuance`, it must equal
        `synoptic_at`; a mismatch is a Source-drift warning.
      - `nhc-map-breakpoints`: `Watch_Warning_Breakpoints` →
        `Breakpoint` values, positioned from the `lat` and `lon`
        fields; `StormSurge_Communication_Points` is not parsed
        (the register: not used in 2.0).
      - `nhc-map-peak-surge`: `Points`, `Lines`, and `Polygons`
        → `DisplayLayer` values, empty or not.
      - Every parser reads fields by name, never by position,
        accepts the missing `idp_source` of
        `AT1 Advisory Wind Field`, and reads `9999` as missing
        where the register says so.
    </requirement>

    <requirement>
      Field-coverage contract,
      `tests/contract/test_field_coverage.py`: each parser
      declares the fields it reads per layer (`FIELDS_READ`).
      For a typed layer the test asserts that set equals the
      layer's "Fields v2 uses" in the register (read through
      `fixture_support.register_layers`), and, for every
      recorded capture with features and every field read,
      deletes that field from one feature of a copy and asserts
      `SourceSchemaError`. For a display layer it asserts each
      "Fields v2 uses" field is present in every recorded
      feature, because the map will read them. An empty recorded
      layer checks its catalog schema instead. The roster gets
      the same two checks against its amended list.
    </requirement>

    <requirement>
      Tests without network (respx, with recorded captures as
      response bodies): the User-Agent on every request; pacing
      per host under a fake clock (two concurrent requests to
      one host leave one interval apart; another host does not
      wait); a retry on 503 and on 429 with `Retry-After`, none
      on 404, backoff under a seeded jitter; the size cap; a
      refused redirect; 304 reuse through the in-memory store;
      layer resolution that survives shifted ids, and group
      paths; paging over a synthetic three-page layer; the
      ArcGIS error object; an empty roster; every recorded
      `nhc-current-storms`, `nhc-map-tropical-weather`,
      `nhc-map-tropical-summary`, `nhc-map-breakpoints`, and
      `nhc-map-peak-surge` capture parsing; and no record at
      INFO or above, and no error message, containing a
      coordinate from `synthetic_coordinates()`. Async tests run
      through anyio's pytest plugin (anyio ships with httpx) or
      `asyncio.run`; add no test dependency unless it removes
      code. Under `filterwarnings = ["error"]`, every test
      closes its client.
    </requirement>

    <requirement>
      Live tests in `tests/live/` (each `@pytest.mark.live` and
      `@pytest.mark.enable_socket`): fetch the roster; read the
      summary service's catalog and resolve every register layer
      name; read the tropical service's catalog and resolve
      every `{slot}` name for all fifteen slots; query one
      outlook layer. Run `uv run pytest -m live` in the session.
    </requirement>

    <requirement>
      `.github/workflows/live-smoke.yml`:
      `on: workflow_dispatch` only — no schedule, push, or
      pull-request trigger; top-level
      `permissions: contents: read`; one ubuntu-latest job with
      `timeout-minutes: 20`, checkout with
      `persist-credentials: false`, the SHA-pinned
      `astral-sh/setup-uv` that `ci.yml` uses,
      `uv sync --locked`, and `uv run pytest -m live`; no
      secret. A header comment says the repository is public, so
      the job runs on GitHub-hosted runners only, and that the
      workflow is manual by design (Phase 4 owns scheduled drift
      detection). It joins neither `gate` nor branch protection.
      After the merge, dispatch it on `main` (`gh workflow run
      live-smoke.yml --ref main`), wait for the run, and add its
      URL to the PR body through the REST API.
    </requirement>

    <requirement>
      Documentation and issues. The register's "User-Agent"
      section names `weatherbot.sources.USER_AGENT` as the one
      constant. `CONTRIBUTING.md` explains the live suite
      (`uv run pytest -m live`) and how to dispatch
      `live-smoke.yml`. `CHANGELOG.md` `[Unreleased]` gains
      `Added` entries for the HTTP layer, the roster and map
      clients, and the live smoke. The PR body says "Closes #12"
      once the recorded probabilistic winds parse into
      `WindProbabilityProduct`, and a comment on the issue
      summarizes the decision and links this roadmap's design
      rationale.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with a `# <repo-relative path>` comment.
    </requirement>
  </requirements>
</task>
```

### Step 2 acceptance criteria

- `weatherbot.sources.USER_AGENT` equals the register's User-Agent (a contract
  test), and `scripts/record_fixtures.py` imports it, `HOST_INTERVALS`,
  `QUERY_PARAMETERS`, and `COUNT_PARAMETERS` from the package; `tests/contract/`
  and `tests/scripts/` pass on both runners.
- The HTTP layer's tests pass: the User-Agent on every request, pacing per host,
  bounded retries with `Retry-After`, the size cap, a refused redirect, 304
  reuse, and no coordinate in a record at INFO or above or in an error message.
- Every recorded `nhc-current-storms`, `nhc-map-tropical-weather`,
  `nhc-map-tropical-summary`, `nhc-map-breakpoints`, and `nhc-map-peak-surge`
  capture parses into Step 1 models; the field-coverage test matches the
  register, including the amended roster list, and deleting any field read fails
  the parse.
- The recorded probabilistic winds parse into three `WindProbabilityProduct`
  values with `synoptic_at` 2026-10-12 18:00 UTC and no storm; this PR closed
  issue #12 with a comment that states the decision.
- `uv run pytest -m live` passed in the session.
- **Deployed & verified:** `live-smoke.yml`, dispatched on `main` after the
  merge, ran green, and its run URL is in the PR body.
- **Security gate clean** (always the final criterion): the hook passed on every
  commit; pip-audit is clean with `httpx` at run time; bandit is clean over
  `src`; no source module disables TLS verification or follows a redirect; and
  the new workflow is SHA-pinned, `contents: read`, secret-free, and
  dispatch-only.

---

## Step 3 — NHC products

**Status:** Not started

> **Goal:** Give every remaining NHC product and display catalog a client, and
> settle issue #11. The new register source `nhc-arrival-times` reads the
> arrival-time KMZ that the roster links
> (`earliestArrivalTimeTSWindsGIS.kmzFile` and
> `mostLikelyTimeTSWindsGIS.kmzFile`): `weatherbot.sources.nhc_arrival_times`
> opens it in memory under member, size, ratio, and path limits, parses its KML
> with `defusedxml`, reads `timezone`, `advisoryNum`, and `pubAdvTime`, and
> resolves every labelled line to a UTC instant by the Step 1 rule; the register
> gains the row and a section, the recorder records a fixed archived pair whose
> checksums the replay corpus manifest pins, and a contract test proves the pair
> parses. `nhc-text-products` reads the TCP by slot and the TWO by basin from
> the NWS API and matches a TCP to its storm by the ATCF id in its header;
> `nhc-outlook-graphics` fetches the six maps with conditional requests;
> `nhc-gis-rss` parses the three feeds and recognizes the no-storm placeholder;
> and the surge-risk catalog and the two nowCOAST WMS capabilities parse into
> the catalogs `doctor` checks. After this step every `required` source except
> the NWS and geocoding rows has a client.

**Branch:** `feature/phase02-step3-nhc-products`

**Deploys:** nothing beyond merge.

| Setting      | Cost                                    | Balanced                                 | Quality                                  |
| ------------ | --------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Model        | GPT-6.1 Sol                             | Opus 5.5                                 | Opus 5.5                                 |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh |
| Platform     | Codex                                   | Claude Code                              | Claude Code                              |
| Effort       | Intelligence High                       | Effort High                              | Effort XHigh                             |
| Thinking     | —                                       | On                                       | On                                       |
| Conversation | **New**                                 | **New**                                  | **New**                                  |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

**Model rationale:** Step 3 is coding with a knowledge secondary — the register
amendment is grounded, live-verified research — at High complexity: hardened
archive and XML parsing, the time-resolution rule of issue #11 on real products,
a new register source with its recorder and contract, and four more clients. It
is not novel; the rule, the hardening, and every endpoint are specified here and
in the register. Balanced runs Opus 5.5, S-tier in coding and knowledge, on
Claude Code at Effort High, one rung above its `medium` default, with thinking
on; Quality runs it at Extra High for the most careful pass over the parsing
limits and the resolution edge cases; Cost runs GPT-6.1 Sol on Codex at
Intelligence High. The claude.ai Max subscription funds Claude Code, ChatGPT Pro
5x funds Codex, and each backup comes from the other maker. The conversation is
new per phase-boundary hygiene.

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
       feature/phase02-step3-nhc-products`
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
       Phase 2 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 2`
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

    THIS STEP parses archives and XML from the network:
    `defusedxml` only (never `xml.etree`, `xml.dom`, `xml.sax`,
    or `lxml` on network input); zip members read in memory
    under member-count, size, ratio, and path checks; and a URL
    taken from the roster followed only when it matches the
    arrival-time KMZ pattern on `www.nhc.noaa.gov` over HTTPS.
    `defusedxml` passes pip-audit. No request in this step
    carries a coordinate.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 2 (Sources and
    persistence). Step 3: NHC products.

    Current state (as of Phase 2, post-Step 2):

    - `weatherbot.sources` has the HTTP layer (pacing, retries,
      size cap, refused redirects, conditional requests,
      redacted logging, typed errors), `USER_AGENT`, the roster
      client, the ArcGIS client, and the map clients; the
      recorder imports the package's constants;
      `tests/contract/test_field_coverage.py` ties every parser
      to the register; `live-smoke.yml` runs `pytest -m live` on
      dispatch. Issue #12 is closed.
    - Carry-over from Step 1 (2026-10-16): build each KMZ line
      with `ArrivalTimeLine.resolve(label, geometry,
      origin="kmz", published_at=..., time_zone=...)`; the
      `ArrivalTimeProduct` validator recomputes every line by
      the same rule and rejects any other instant. When the
      KMZ disagrees with the roster (advisory, ATCF id, or
      issuance), set the product's `withheld_reason` and pass
      it to every line: they stay unresolved with that reason.
      `published_at` must be the instant `parse_nhc_local_time`
      reads from `published_local_text`.
    - Carry-over from Step 2 (2026-10-16). Issues #11 and #12
      were closed on 2026-10-16 by PR #19's merge, before any
      parser existed and with no decision comment; Step 2's PR
      commented on #12. Step 3 earns #11's close: post the
      decision comment, and reopen #11 if a criterion below
      fails. The client API: `Fetcher.get(url, *, source_id,
      accept, problems, max_bytes)` returns a `FetchResult`
      (`.provenance()` builds the record's `Provenance`); every
      fetch function returns `SourceResult(records,
      responses)`; `arcgis.fetch_catalog(fetcher, service)`
      returns a `SourceResult[MapCatalog]`, read once per run
      and passed to every fetch function; `arcgis.query`
      takes the resolved `MapLayer`, not a bare id, so its
      errors name the layer. Parsers read fields through
      `weatherbot.sources.fields.Fields` and a declared
      `FIELDS_READ`, and raise `SourceSchemaError` on a missing
      or mistyped field; `weatherbot.sources.drift.warn_drift`
      logs a Source-drift warning. A map-layer arrival product's
      `Advisory` has `issued_at_source` `roster` (the roster's
      arrival-time `issuance`) and no `local_text`; a KMZ
      product's `Advisory` takes the default `local_text`
      source from `pubAdvTime`. A `Retry-After` over 60 seconds
      fails the source without a retry.
    - The map layers' arrival-time lines parse into label-only
      `ArrivalTimeProduct` values (`origin` `map_layer`). The
      roster names each storm's arrival-time KMZ: on 2026-10-12,
      `https://www.nhc.noaa.gov/storm_graphics/api/EP202026_022adv_earliest_reasonable_toa_34.kmz`
      and its `most_likely` twin, with `advNum` `022` and
      `issuance` `2026-10-12T21:00:00.000Z`.
    - The replay cache holds the same product for Dorian, Ian,
      and Milton, pinned by
      `tests/fixtures/replay/corpus-manifest.json`.
      `AL052019_036adv_earliest_reasonable_toa_34.kmz` (37,795
      bytes) holds one KML file and label images; the KML uses
      namespace `http://earth.google.com/kml/2.2`; its Document
      `ExtendedData` holds `timezone` `EDT`, `storm`, `atcfid`,
      `advisoryNum` `36`, and `pubAdvTime`
      `500 AM EDT Mon Sep 02 2019`; twelve Placemarks each hold
      a LineString and a `description` whose single HTML table
      cell is the label (`Mon 8 am` … `Fri 8 am`, and
      `Wind Speed Probability 5% contour`).
    - The register's facts for the other sources (2026-10-12):
      TCP lists by slot and TWO lists by basin (`AT`, `EP`,
      `CP`; `SAT`, `SEP`, `SCP` are Spanish) from
      `api.weather.gov/products`, a TCP header naming the ATCF
      id because slots are reused, `issuanceTime` matching the
      WMO line; the six graphics
      `two_{atl,pac,cpac}_{2d0,7d0}.png` with `ETag`,
      `Last-Modified`, 304 honored, and dimensions that change;
      RSS 2.0 feeds with the `nhc` namespace, item `guid`s, the
      `nhc:Cyclone` `atcf` and `wallet`, and a placeholder item
      whose `pubDate` lies in the future; `StormSurgeRisk`
      layers named by group path; nowCOAST WMS 1.3.0
      capabilities with the radar and satellite layers and a
      `time` dimension.
    - The 2026-10-12 capture set is the only one with an active
      storm's products: record only the new source and keep
      every other capture.

    Files to read (every file before drafting):
    - docs/roadmap/phase02-roadmap.md (Overview and the issue
      #11 rationale, Current State, Step 1's arrival-time
      requirements, Step 2, this step, and Step 6's snapshot
      rule).
    - docs/DATA_SOURCES.md (the roster's product objects, text
      products, outlook graphics, GIS RSS, GIS archive,
      overlays, "Not used").
    - src/weatherbot/models/times.py and storms.py;
      src/weatherbot/sources/ (every module).
    - scripts/record_fixtures.py, tests/contract/ (every
      module), tests/fixtures/replay/corpus-manifest.json (the
      Dorian 036 entries).
    - scripts/fetch_replay_corpus.py (its bounded in-memory zip
      reading).
    - Issue #11 (`gh issue view 11`).
  </context>

  <goal>
    Amend the register with `nhc-arrival-times` and record its
    fixed archived pair; ship the arrival-time, text-product,
    outlook-graphic, GIS RSS, surge-risk catalog, and overlay
    catalog clients with contract and hardening tests; resolve
    every labelled arrival line to an instant or record why not;
    close issue #11.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Dependencies. Add `defusedxml` to
      `[project] dependencies`. Run `uv lock`;
      `scripts/audit_deps.py` must pass.
    </requirement>

    <requirement>
      Register amendment, verified live on the step's date.
      Fetch the roster; for every active storm with arrival-time
      links, fetch both KMZ files; fetch the fixed archived pair
      (Dorian `AL052019`, advisory 036, both kinds, with the
      URLs the corpus manifest lists). Record status, content
      type, size, the zip's members, and the `ExtendedData`
      keys. Then:
      - add the row `nhc-arrival-times`: Brief §5 source
        `CurrentStorms.json`; Endpoint
        `https://www.nhc.noaa.gov/storm_graphics/api/{ID}_{adv}adv_{earliest_reasonable,most_likely}_toa_34.kmz`;
        Format KMZ (KML 2.2 in a zip); Fixture `required`;
        Cadence per full advisory; Terms public domain (NWS
        disclaimer); Verified, the step's date — no `|` inside a
        cell;
      - add a section "Arrival-time KMZ": the structure above,
        why v2 reads it (issue #11: the map layers' labels carry
        no date or zone, and the slot's `advdate` belongs to the
        latest, possibly intermediate, advisory), the resolution
        rule of `resolve_arrival_label`, and the map-layer
        fallback;
      - narrow the "Not used" row on live per-storm shapefiles
        and KMZ so it excludes the arrival-time KMZ, with the
        reason;
      - note the amendment and its date under the register's
        "Verified" line, which keeps 2026-10-12 for every other
        statement;
      - add `nhc-arrival-times` to the `SourceId` literal in
        `weatherbot.models`, which Step 1's test keeps equal to
        the register's ids.
    </requirement>

    <requirement>
      Recorder. Add `nhc-arrival-times` to `SOURCES` in
      `scripts/record_fixtures.py`. It always records the fixed
      archived pair, and also every active storm's roster-linked
      pair. Before any fetch, a URL must match
      `^https://www\.nhc\.noaa\.gov/storm_graphics/api/(AL|EP|CP)\d{6}_\d{3}adv_(earliest_reasonable|most_likely)_toa_34\.kmz$`.
      Run `uv run python scripts/record_fixtures.py record
      --source nhc-arrival-times` only; no other source is
      re-recorded. `tests/contract/test_register.py` passes with
      the new id; `tests/contract/test_recorded_fixtures.py`'s
      format check learns `.kmz` (a zip whose single KML
      parses); and a new contract test proves the archived
      pair's SHA-256 values equal the corpus manifest's entries
      for the same URLs.
    </requirement>

    <requirement>
      The personal-data check sees inside a KMZ. Rule R1 of
      `scripts/check_personal_data.py` already scans gzip
      captures decompressed; extend it to the members of a
      `.kmz` (or any zip) capture, bounded as the client bounds
      them and failing closed on an unreadable archive, with a
      synthetic regression in
      `tests/scripts/test_check_personal_data.py` that hides a
      generated value inside a zip member. No denylist value is
      printed or changed.
    </requirement>

    <requirement>
      Arrival-time client,
      `weatherbot/sources/nhc_arrival_times.py`:
      - URLs come only from a roster storm's two arrival-time
        objects and must match the pattern above; anything else
        raises `SourceSchemaError` and is never fetched.
      - `parse_arrival_kmz(body, provenance)` opens the zip in
        memory and refuses more than 64 members, an absolute
        member name or one containing `..`, a total uncompressed
        size over 8 MiB, or a member compressed more than 100 to
        1. It reads exactly one `.kml` member and ignores the
        label images, parses it with `defusedxml.ElementTree`
        under either KML namespace
        (`http://earth.google.com/kml/2.2` or
        `http://www.opengis.net/kml/2.2`), and reads
        `ExtendedData` `timezone`, `advisoryNum`, `atcfid`, and
        `pubAdvTime`, each Placemark's label from the single
        table cell of its `description` (through the standard
        library's `html.parser`), and its LineString or
        MultiGeometry coordinates (`lon,lat[,alt]`, WGS 84).
      - `published_at` is `parse_nhc_local_time(pubAdvTime)`.
        When the roster gives the product's `issuance`, the two
        must agree within an hour, `advisoryNum` must equal the
        roster's `advNum` and the URL's advisory, and `atcfid`
        must equal the storm's; otherwise every line stays
        unresolved with the reason, and the client logs a
        Source-drift warning.
      - Each labelled line resolves through
        `resolve_arrival_label`; the "Wind Speed Probability 5%
        contour" line is the outer contour, without a time.
      - The snapshot rule, which Step 6 applies: a `kmz` product
        supersedes the `map_layer` product of the same storm,
        advisory, and kind.
    </requirement>

    <requirement>
      Text products, `weatherbot/sources/nhc_text_products.py`:
      the TCP list `/products/types/TCP/locations/{slot}` for
      each active slot and the TWO list
      `/products/types/TWO/locations/{AT,EP,CP}` (English
      editions only); the newest product id, checked against the
      recorder's id pattern, then `/products/{id}`; a
      `TextProduct` from `issuanceTime`, `wmoCollectiveId`,
      `issuingOffice`, and `productText`. A TCP whose header
      names another ATCF id than the slot's storm (a reused
      slot) is not attributed to the storm and is logged, not
      raised. The advisory number read from the TCP text
      ("ADVISORY NUMBER 22A", "INTERMEDIATE ADVISORY NUMBER
      22A") is compared with the roster's
      `publicAdvisory.advNum`, and an older product keeps its
      own number. Requests share `api.weather.gov`'s 1.2-second
      pacing with the NWS client of Step 4.
    </requirement>

    <requirement>
      Outlook graphics,
      `weatherbot/sources/nhc_outlook_graphics.py`: the six URLs
      `two_{atl,pac,cpac}_{2d0,7d0}.png` (never `two_epac_*`),
      fetched with conditional requests; a 304 reuses the stored
      body. The PNG signature and IHDR dimensions are checked
      and returned in an `OutlookGraphic`; the bytes travel in
      the `FetchResult` for the raw-response cache of Step 5.
      The recorded 2026-10-12 maps and the six harvested 2025
      maps all parse.
    </requirement>

    <requirement>
      GIS RSS, `weatherbot/sources/nhc_gis_rss.py`: the three
      feeds, parsed with `defusedxml`, into `GisFeedItem`
      values: `guid`, `title`, `link`, and `pubDate` in UTC (RFC
      2822), plus `atcf_id` and `slot` from `nhc:Cyclone`'s
      `atcf` and `wallet`. The "There are no tropical cyclones
      at this time." item parses with `is_placeholder` true and
      no `published_at`, because its `pubDate` is not a time.
      The channel `pubDate` is not read: NHC rewrites it without
      changing an item.
    </requirement>

    <requirement>
      Catalogs. `nhc-map-surge-risk` → `MapCatalog` through the
      Step 2 ArcGIS client, resolving `Atlantic / US East and
      Gulf Coast / Category {n} / Image` for each category 1 to
      5 by group path. `overlay-radar` and `overlay-satellite` →
      `OverlayCatalog` from WMS 1.3.0 `GetCapabilities`, parsed
      with `defusedxml`, confirming
      `conus_base_reflectivity_mosaic`, `goes_longwave_imagery`,
      and `goes_visible_imagery` and their `time` defaults.
      `doctor` (Step 6) uses both; no tile or image is fetched.
    </requirement>

    <requirement>
      Contract tests for every recorded capture of
      `nhc-arrival-times`, `nhc-text-products`,
      `nhc-outlook-graphics`, `nhc-gis-rss`,
      `nhc-map-surge-risk`, `overlay-radar`, and
      `overlay-satellite`, with Step 2's field-coverage rule
      wherever the register lists fields read (text-product
      keys, RSS item fields, `ExtendedData` keys).
    </requirement>

    <requirement>
      Tests without network (respx, recorded bodies): every
      hardening limit (a high-ratio member, too many members, a
      `../` member name, a KML with an internal entity
      declaration, which `defusedxml` refuses, and a roster link
      outside the pattern, which is never fetched); the archived
      pair's lines resolving against
      `500 AM EDT Mon Sep 02 2019` to the instants the test
      lists, with the outer contour flagged; a roster issuance
      an hour and a half from `pubAdvTime` leaving every line
      unresolved; a TCP from a reused slot; the RSS placeholder;
      a 304 on a graphic.
    </requirement>

    <requirement>
      Live tests in `tests/live/`: each active storm's
      arrival-time pair, skipped with the reason when no storm
      is active; the archived pair; one TCP list when a slot is
      active; the three TWO lists; one graphic with a
      conditional request; the three feeds; both WMS
      capabilities. Run `uv run pytest -m live` in the session,
      then dispatch `live-smoke.yml` on the branch before
      merging (`gh workflow run live-smoke.yml --ref
      feature/phase02-step3-nhc-products`) and add the run's URL
      to the PR body.
    </requirement>

    <requirement>
      Open basins. If a storm is active in the Atlantic or the
      Central Pacific when this step runs, re-check that basin's
      row in "Arrival-time, probabilistic-wind, and surge layers
      by basin" live — layer counts for both arrival-time
      layers, the probabilistic winds, peak surge, and
      inundation — and record the answer with its date (Source
      drift). The 2026-10-12 captures stay as they are.
    </requirement>

    <requirement>
      `CHANGELOG.md` `[Unreleased]` gains `Added` entries for
      the five clients and the new register source. The PR body
      says "Closes #11" once the archived pair parses with
      resolved instants, and a comment on the issue summarizes
      the decision (option b, with option c as the fallback) and
      links this roadmap's design rationale.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with a `# <repo-relative path>` comment.
    </requirement>
  </requirements>
</task>
```

### Step 3 acceptance criteria

- `docs/DATA_SOURCES.md` has the `nhc-arrival-times` row, the "Arrival-time KMZ"
  section, and the narrowed "Not used" row; `tests/contract/test_register.py`
  passes with the new id; and the recorded archived pair's SHA-256 values equal
  the corpus manifest's.
- Every recorded capture of `nhc-arrival-times`, `nhc-text-products`,
  `nhc-outlook-graphics`, `nhc-gis-rss`, `nhc-map-surge-risk`, `overlay-radar`,
  and `overlay-satellite` parses, and the field-coverage rule holds for them.
- The archived pair's labelled lines resolve to the instants the test lists, the
  outer contour carries no time, and a roster mismatch, an unknown zone, or an
  out-of-horizon label leaves a line unresolved with its reason.
- Every hardening test passes, and bandit is clean over `src` with no new
  suppression on an XML or zip path.
- `uv run pytest -m live` passed in the session, and `live-smoke.yml` dispatched
  on the branch ran green (its URL is in the PR body).
- This PR closed issue #11 with a comment that states the decision.
- **Security gate clean** (always the final criterion): the hook passed on every
  commit; pip-audit is clean with `defusedxml`; no module parses network XML
  with a standard-library parser; and a roster link is followed only when it
  matches the arrival-time pattern over HTTPS.

---

## Step 4 — NWS and geocoding clients

**Status:** Not started

> **Goal:** Give the location-specific sources their clients.
> `weatherbot.sources.nws` resolves a point through `/points` to its forecast
> zone, county, office, and time zone, and turns the documented `InvalidPoint`
> 404 into a typed result for a location outside NWS coverage; it fetches alerts
> at the point and for the county and forecast zones and merges them into one
> `NwsAlert` list keyed by alert id, each alert keeping `found_by` (the queries
> that returned it), `affected_zone_ids`, and its `geocode` lists — the inputs
> issue #10's rule needs in Phase 3; and it fetches a zone's metadata and shape
> for a location's optional polygon. `weatherbot.sources.nominatim`
> reverse-geocodes a location once, at setup, for its display name and country.
> Coordinates appear only in these requests' URLs, formatted to four decimals by
> one function, at the register's pacing, and never in a log line above DEBUG,
> an error message, or a `repr`.

**Branch:** `feature/phase02-step4-nws-geocoding-clients`

**Deploys:** nothing beyond merge.

| Setting      | Cost                                     | Balanced                                | Quality                                 |
| ------------ | ---------------------------------------- | --------------------------------------- | --------------------------------------- |
| Model        | GPT-6.1 Sol                              | Opus 5.5                                | Opus 5.5                                |
| Backup       | Sonnet 5.5 — Claude Code · Effort Medium | GPT-6.1 Sol — Codex · Intelligence High | GPT-6.1 Sol — Codex · Intelligence High |
| Platform     | Codex                                    | Claude Code                             | Claude Code                             |
| Effort       | Intelligence Low                         | Effort Medium                           | Effort High                             |
| Thinking     | —                                        | On                                      | On                                      |
| Conversation | **New**                                  | **New**                                 | **New**                                 |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

**Model rationale:** Step 4 is coding at Medium complexity: bounded clients over
five endpoints whose answers, including the documented errors and the
point-and-county split, are already recorded, with the merge rule and the
coordinate hygiene written down here; nothing in it is novel, and issue #10's
judgement stays with Phase 3. Balanced runs Opus 5.5 on Claude Code at Effort
Medium — Claude Code's default model at its documented default effort, so the
session runs as opened — with thinking on; Quality raises it to Effort High for
a second look at the coordinate paths; Cost runs GPT-6.1 Sol on Codex at
Intelligence Low, enough for well-specified parsing against recorded answers.
The claude.ai Max subscription funds Claude Code and ChatGPT Pro 5x funds Codex,
and each backup comes from the other maker. The conversation is new per
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
       feature/phase02-step4-nws-geocoding-clients`
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
       Phase 2 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 2`
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

    THIS STEP sends a location's coordinates to
    `api.weather.gov` and Nominatim for the first time, so it
    proves the hygiene: coordinates appear only in request URLs,
    rendered by one function; no record at INFO or above, no
    error message, and no `repr` carries them (tests with
    `synthetic_coordinates()`); tests and live probes use the
    two landmarks only; and Nominatim gets one request per
    location at setup, never per fetch, as its usage policy
    requires. No dependency is added.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 2 (Sources and
    persistence). Step 4: NWS and geocoding clients.

    Current state (as of Phase 2, post-Step 3):

    - Every NHC and display source has a client; the HTTP layer
      paces `api.weather.gov` at 1.2 seconds (shared with the
      text-product client) and Nominatim at 1.5 seconds, redacts
      `/points/` paths and `point`, `lat`, and `lon` values
      above DEBUG, and types `application/problem+json` answers
      the caller declares as `DocumentedProblem`. Issues #11 and
      #12 are closed; issue #10 is open for Phase 3.
    - Carry-over from Step 2 (2026-10-16): declare the
      documented error statuses with `problems=(404,)` (and
      `(400,)` for an out-of-bounds alerts point); a
      `DocumentedProblem` keeps the problem's `type` and
      `title` and drops its `detail`, which repeats the
      coordinates. `redact_url` and `RedactingFilter` in
      `weatherbot.sources.http` also cover `latitude` and
      `longitude`, and `tests/sources/test_http.py` shows the
      `synthetic_coordinates()` pattern for the privacy tests.
    - Carry-over from Step 3 (2026-10-17): the 1.2-second
      `api.weather.gov` pacing is shared only when every client
      uses the run's one `Fetcher`, whose `HostPacer` keys by
      host; `tests/sources/test_nhc_text_products.py` asserts
      the spacing on the pacer's fake clock. Any XML goes
      through `weatherbot.sources.markup.parse_xml`
      (`defusedxml`, no DTD). Bandit runs at every severity, so
      no module under `src/` or `scripts/` imports `xml.etree`,
      even for a type: use `markup.XmlElement`.
    - `weatherbot.models` defines `NwsAlert` (with `found_by`,
      `affected_zone_ids`, `geocode_same`, `geocode_ugc`),
      `AlertQuery`, `NwsCoverage`, `NwsZone`, `GeocodeResult`,
      and `Location`. Carry-over from Step 1 (2026-10-16): each
      `AlertQuery` holds the `Provenance` of the response that
      returned the alert, so a merged alert keeps one per
      query; `NwsZone.cwa` and `time_zone` are tuples, because
      the zone answers list them; `Location.country_code` is
      upper case, while `GeocodeResult.country_code` keeps
      Nominatim's lower case; the models' validation errors
      never repeat their input.
    - The register's NWS facts (2026-10-12): the Miami-Dade
      landmark's `/points` answer (200, `max-age=86400`) names
      `forecastZone` `FLZ173`, `county` `FLC086`,
      `fireWeatherZone` `FLZ173`, `cwa` `MFL`, and `timeZone`
      `America/New_York`; the Nassau landmark's answer is 404
      `application/problem+json` with `type`
      `https://api.weather.gov/problems/InvalidPoint`; alerts at
      the Miami-Dade point returned an empty FeatureCollection,
      and at the Nassau point 400 `InvalidParameter` ("out of
      bounds"); at verification `FLC086` returned one Coastal
      Flood Statement (`affectedZones` `FLZ069`, `FLZ075`,
      `FLZ174`; `geocode.SAME` including `012086`; `geometry`
      null) that the point query missed, and `FLZ173` returned
      none. That alert had expired by the recording: both
      recorded zone-alert captures (01:09 UTC on 2026-10-13)
      hold no features, and no recorded alert exists (found
      by Step 1, 2026-10-16). Zones
      are MultiPolygons of up to 784,207 bytes with `max-age` of
      weeks. The API requires an identifying User-Agent, keeps
      its rate limit private, and says a key will replace the
      User-Agent "in the future".
    - The register's Nominatim facts: `reverse?format=jsonv2`,
      at most one request per second, an identifying User-Agent,
      results cached for good, ODbL attribution; the fields v2
      uses are `display_name`, `name`, `address.country_code`,
      `address.country`, `licence`, `osm_type`, and `osm_id`.

    Files to read (every file before drafting):
    - docs/roadmap/phase02-roadmap.md (Current State, Step 1's
      location and alert models, Step 2's HTTP layer, this step,
      and Step 6's locations service).
    - docs/DATA_SOURCES.md ("NWS API", "OpenStreetMap: basemap
      and geocoding").
    - src/weatherbot/models/ (location.py, alerts.py,
      provenance.py) and src/weatherbot/sources/ (http.py,
      errors.py, nhc_text_products.py).
    - scripts/check_personal_data.py (`request_coordinates`,
      `synthetic_coordinates`, `load_landmarks`) and
      scripts/public_landmarks.toml.
    - tests/contract/ (fixture_support.py and
      test_field_coverage.py), issue #10 (`gh issue view 10`).
  </context>

  <goal>
    Ship the NWS client (points, merged alerts, zones) and the
    Nominatim client returning Step 1 models, with every
    recorded capture of the five sources parsing, the alert
    merge keeping issue #10's inputs, the non-US path typed, and
    coordinate hygiene proven by tests.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      `weatherbot/sources/nws.py`:
      - `format_point(lat, lon)` renders a point with four
        decimals, the precision the API documents; it is the
        only function that writes a location's coordinates into
        a URL. Confirm the documentation's statement and record
        it, with its link and the step's date, in the register's
        NWS section.
      - `lookup_point(fetcher, lat, lon)` returns an
        `NwsCoverage` (the last path segment of `forecastZone`
        and `county`; `cwa`; `timeZone`; `relativeLocation`'s
        city and state — exactly the register's "Fields v2
        uses") or `OutsideNwsCoverage` for the documented 404
        `InvalidPoint` problem; any other problem raises
        `SourceHttpError`.
      - `fetch_alerts(fetcher, location)` sends the point query
        and one zone query each for the county and the forecast
        zone, and merges the answers by alert `id` into one
        tuple of `NwsAlert` values, each with `found_by` listing
        every query that returned it, in a stable order. Nothing
        is filtered by zone: whether a county alert outside the
        location's forecast zone counts is issue #10's rule,
        which Phase 3 decides. A location outside NWS coverage
        makes no alert request. The documented 400 for an
        out-of-bounds point is a `DocumentedProblem`.
      - `fetch_zone(fetcher, kind, zone_id)` returns an
        `NwsZone`; zone answers change rarely, so the request is
        conditional.
    </requirement>

    <requirement>
      `weatherbot/sources/nominatim.py`:
      `reverse_geocode(fetcher, lat, lon)` sends
      `reverse?format=jsonv2` at the register's pacing and
      returns a `GeocodeResult` that keeps the licence text for
      the attribution the display shows. Its docstring states
      the rule Step 6 enforces: one request per location, at
      setup, never per fetch.
    </requirement>

    <requirement>
      Coordinate hygiene. A location's coordinates appear only
      in the request URL. The Step 2 filter redacts them above
      DEBUG; error messages carry no path or query; results that
      hold coordinates keep them out of `repr`. Tests use the
      landmarks from `scripts/public_landmarks.toml` through
      `load_landmarks()`, or coordinates from
      `synthetic_coordinates()`, never a literal.
    </requirement>

    <requirement>
      Contract tests over every recorded capture: the Miami-Dade
      point; the Nassau 404 as `OutsideNwsCoverage`; the
      Miami-Dade point alerts (none); the Nassau 400 as a
      `DocumentedProblem`; the empty `FLC086` and `FLZ173`
      answers parsed to no alert; the three zones; the two
      reverse lookups. The merge is proved on an alert built in
      the test from the register's `FLC086` description, never a
      fabricated fixture: returned by `zone FLC086` and absent
      from the point and `FLZ173` answers, it merges into one
      alert found by `zone FLC086`, with affected zones
      `FLZ069`, `FLZ075`, and `FLZ174` and `012086` among its
      SAME codes. When a live capture holds an alert, it is
      recorded beside the 2026-10-12 set under Source drift and
      a contract test parses it. The
      field-coverage rule of Step 2 holds against the register's
      "Fields v2 uses" for all five sources, including deletion
      tests.
    </requirement>

    <requirement>
      Tests without network (respx): an alert both queries
      return is kept once with both queries in `found_by`;
      four-decimal formatting, including rounding; a 429 with
      `Retry-After` on `api.weather.gov`; pacing shared between
      this client and the text-product client on the same host;
      Nominatim's 1.5-second pacing; no coordinate from
      `synthetic_coordinates()` in any record at INFO or above,
      any error message, or any `repr`.
    </requirement>

    <requirement>
      Live tests in `tests/live/`, landmarks only: the
      Miami-Dade point, its point alerts, its county and
      forecast-zone alerts, and its three zones; the Nassau
      point (404) with no alert request; and one reverse lookup
      per landmark (two Nominatim requests in all). Run
      `uv run pytest -m live` in the session, then dispatch
      `live-smoke.yml` on the branch (`gh workflow run
      live-smoke.yml --ref
      feature/phase02-step4-nws-geocoding-clients`) and add the
      run's URL to the PR body.
    </requirement>

    <requirement>
      If the NWS API requires a key when this step runs, stop:
      open an issue (architectural question, owner the operator)
      citing the register's keyless rule, record it in the
      register's NWS section, and report. Phase 2 adds no key
      handling.
    </requirement>

    <requirement>
      `CHANGELOG.md` `[Unreleased]` gains `Added` entries for
      both clients. Comment on issue #10: the client keeps
      `found_by`, `affected_zone_ids`, and both geocode lists on
      every alert, with the register's `FLC086` example; the issue
      stays open for Phase 3's rule.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with a `# <repo-relative path>` comment.
    </requirement>
  </requirements>
</task>
```

### Step 4 acceptance criteria

- Every recorded capture of `nws-points`, `nws-alerts-point`, `nws-alerts-zone`,
  `nws-zones`, and `geocode-nominatim` parses, and the field-coverage rule holds
  for all five.
- The recorded (empty) `FLC086` and `FLZ173` answers parse; an alert built from
  the register's `FLC086` description merges into one alert found by
  `zone FLC086` with its affected zones and SAME codes; and the Nassau landmark
  yields `OutsideNwsCoverage` with no alert request.
- `format_point` is the only writer of coordinates into a URL, renders four
  decimals, and its precision is recorded in the register with its source; the
  coordinate-hygiene tests pass.
- `uv run pytest -m live` passed in the session, and `live-smoke.yml` dispatched
  on the branch ran green (its URL is in the PR body).
- Issue #10 carries the comment on the kept inputs and stays open for Phase 3.
- **Security gate clean** (always the final criterion): the hook passed on every
  commit; no test, fixture, or document holds a coordinate other than a
  landmark; no record at INFO or above, error message, or `repr` exposes a
  coordinate (tests); and Nominatim is called only by `reverse_geocode`.

---

## Step 5 — Persistence and configuration

**Status:** Not started

> **Goal:** Give the application its local state. `weatherbot.services.config`
> resolves the configuration and data directories through `platformdirs`
> (`WEATHERBOT_CONFIG_DIR` and `WEATHERBOT_DATA_DIR` override them) and reads
> and validates `weatherbot.toml` under `WEATHERBOT_*` environment overrides.
> `weatherbot.services.persistence` defines SQLAlchemy 2 tables for the data
> Phase 2 writes — locations, snapshots, source outcomes, raw responses and
> their deduplicated bodies, storms, advisories, product geometries, text
> products, feed items, alerts and their observations, and settings — and
> repositories that store and load the Step 1 models; an Alembic baseline that
> ships inside the package creates them; opening the database copies it with
> SQLite's online backup API before any pending migration, refuses a revision
> the code does not know, and never downgrades; the raw-response cache
> implements Step 2's validator store, so conditional requests work across runs;
> and an autouse test fixture pins both directories to `tmp_path`, so no test
> can touch the operator's real database or configuration.

**Branch:** `feature/phase02-step5-persistence`

**Deploys:** GitHub Actions → `ci.yml`'s `package` job gains a migration smoke
against the installed wheel on merge. The operator's database is created by the
first command that opens it, which Step 6 adds; Step 6 owns that surface's
Deployed & verified check.

| Setting      | Cost                                    | Balanced                                 | Quality                                  |
| ------------ | --------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Model        | GPT-6.1 Sol                             | Opus 5.5                                 | Opus 5.5                                 |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh |
| Platform     | Codex                                   | Claude Code                              | Claude Code                              |
| Effort       | Intelligence High                       | Effort High                              | Effort XHigh                             |
| Thinking     | —                                       | On                                       | On                                       |
| Conversation | **New**                                 | **New**                                  | **New**                                  |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

**Model rationale:** Step 5 is coding at High complexity: a schema that must
hold every Step 1 model and give it back unchanged, a migration path with a
consistent backup, a refusal rule, and an isolation guard, and a configuration
layer with a fixed precedence, all of which every later phase inherits. It is
not novel — SQLAlchemy 2 with Alembic is a known pattern, and the project
roadmap's "Data and schema migrations" rules fix the behavior. Balanced runs
Opus 5.5 on Claude Code at Effort High, one rung above its `medium` default,
with thinking on; Quality runs it at Extra High for the migration and backup
edge cases; Cost runs GPT-6.1 Sol on Codex at Intelligence High. The claude.ai
Max subscription funds Claude Code, ChatGPT Pro 5x funds Codex, and each backup
comes from the other maker. The conversation is new per phase-boundary hygiene.

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
       feature/phase02-step5-persistence`
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
       Phase 2 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 2`
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

    THIS STEP creates the store that will hold the operator's
    locations and the request URLs that carry their coordinates.
    It lives in the user data directory, outside the repository
    (`.gitignore` also ignores `*.sqlite3` there); it holds no
    secret; the raw-response cache keeps allowlisted response
    headers only and never a request header; every statement
    goes through SQLAlchemy constructs, never string-built SQL
    (bandit and ruff's S608 stay clean); and tests are pinned to
    `tmp_path`, so none can read or write the operator's
    database. `sqlalchemy`, `alembic`, and `platformdirs` pass
    pip-audit.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 2 (Sources and
    persistence). Step 5: Persistence and configuration.

    Current state (as of Phase 2, post-Step 4):

    - Every `required` register source has a client returning
      Step 1 models; the HTTP layer's `ValidatorStore` protocol
      has an in-memory implementation only, so conditional
      requests do not survive a run; `FetchResult` carries the
      body, its SHA-256, and the allowlisted headers.
    - Carry-over from Step 2 (2026-10-16): the protocol is
      `ValidatorStore.load(url) -> StoredResponse | None` and
      `save(url, StoredResponse(etag, last_modified, body,
      sha256, headers))`; only a 200 with an `ETag` or a
      `Last-Modified` is saved, and a 304 returns the stored
      body with `not_modified` and the stored hash. Two model
      fields arrived in Step 2 for the tables to hold:
      `Advisory.issued_at_source` (`local_text` or `roster`,
      with `local_text` nullable for the map-layer arrival
      products) and `MapCatalog.max_record_count`.
    - Carry-over from Step 3 (2026-10-17): the raw-response
      cache holds binary bodies too, such as the outlook PNGs
      and the arrival-time KMZ files. The persisted
      `ValidatorStore` must return the stored body on a 304:
      `nhc_outlook_graphics` relies on it
      (`tests/sources/test_nhc_outlook_graphics.py`,
      `test_a_304_reuses_the_stored_body`, shows the contract).
      An arrival product carries `withheld_reason`, and each
      line its `unresolved_reason`. A post-tropical storm's
      KMZ can hold only the outer contour (`EP202026` advisory
      038 on 2026-10-17).
    - The project roadmap fixes the rules (§5, "Data and schema
      migrations" and "Rollback"): migrations run at application
      start after the application copies the database aside, the
      copy is the rollback, migrations are expand-first, and
      `doctor` reports the head. Phase 2 creates only the tables
      its own code writes; assessments and evidence (Phase 3),
      notifications and the heartbeat (Phase 4), and briefings
      and the Claude ledger (Phase 6) arrive with their writers.
    - No database or configuration code exists, and
      `platformdirs`, SQLAlchemy, and Alembic are not installed.
      Tests already run in a temporary working directory;
      nothing yet keeps them out of the user's real directories.
      On Windows, `platformdirs` resolves
      `user_data_dir("weatherbot", appauthor=False)` under
      `%LOCALAPPDATA%`; the personal-data denylist lives
      elsewhere (`%APPDATA%\weatherbot\`), belongs to the
      checker, and is never read by the application.
    - `uv_build` packages every file under `src/weatherbot/`, so
      migrations placed there ship in the wheel; `ci.yml`'s
      `package` job installs the wheel into a fresh environment
      on both runners.

    Files to read (every file before drafting):
    - docs/roadmap/phase02-roadmap.md (Overview and its "tables
      arrive with their writers" decision, Current State, this
      step, and Step 6, which opens the database).
    - docs/roadmap/ROADMAP.md (§5 "Release & deployment
      strategy": data and schema migrations, rollback,
      runbooks).
    - src/weatherbot/models/ (every module) and
      src/weatherbot/sources/http.py.
    - tests/conftest.py, tests/test_architecture.py,
      pyproject.toml, .gitignore, .github/workflows/ci.yml,
      CONTRIBUTING.md.
  </context>

  <goal>
    Ship the configuration layer, the Phase 2 tables with an
    Alembic baseline inside the package, a database opener that
    backs up before migrating and refuses unknown revisions,
    repositories that round-trip the models, the persistent
    validator store, a test-isolation guard, and a migration
    smoke against the installed wheel.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Dependencies. Add `sqlalchemy` (2.x), `alembic`, and
      `platformdirs` to `[project] dependencies`. Run `uv lock`;
      `scripts/audit_deps.py` must pass.
    </requirement>

    <requirement>
      Configuration, `weatherbot/services/config.py`:
      - `AppPaths`: `config_dir` from `WEATHERBOT_CONFIG_DIR`,
        else `platformdirs.user_config_dir("weatherbot",
        appauthor=False)`; `data_dir` from
        `WEATHERBOT_DATA_DIR`, else
        `platformdirs.user_data_dir("weatherbot",
        appauthor=False)`; `database_path` is
        `data_dir / "weatherbot.sqlite3"` and `backup_dir` is
        `data_dir / "backups"`. Directories are created on first
        use, owner-only (0o700) on POSIX.
      - `Settings`, from the optional
        `config_dir / "weatherbot.toml"` read with `tomllib` and
        validated by Pydantic, with Phase 2's keys only:
        `[logging] level` (default `INFO`) and
        `[http] timeout_seconds` (default 30).
        `WEATHERBOT_LOG_LEVEL` and
        `WEATHERBOT_HTTP_TIMEOUT_SECONDS` override the file; the
        precedence is environment, then file, then default. An
        unknown key or a bad value fails with a message that
        names the key and never echoes the value.
      - No secret, location, or coordinate is a setting;
        locations live in the database. The configuration never
        reads the personal-data denylist or `.env`.
    </requirement>

    <requirement>
      Tables, `weatherbot/services/persistence/tables.py`, with
      SQLAlchemy 2 typed declarative mapping (`Mapped[...]`):
      - `locations`: unique name; latitude and longitude; the
        polygon's GeoJSON and CRS; country code; display name;
        the NWS coverage columns; `breakpoint_span` (JSON,
        null); `evacuation_order_in_effect` (false); the
        geocoding provenance (JSON); created and updated times.
      - `snapshots` (UUID, started and completed times, status)
        and `source_outcomes` (snapshot, source id, status,
        error kind, fetched-at, raw response).
      - `raw_responses` (source id, product key, issued-at, URL,
        status, fetched-at, SHA-256, allowlisted headers, ETag,
        Last-Modified), unique on source id, product key,
        issued-at, and SHA-256, with bodies in
        `response_bodies`, keyed and deduplicated by SHA-256 and
        stored zlib-compressed.
      - `storms` (ATCF id, name, basin, first and last seen) and
        `advisories` (storm, number, issued-at, local text;
        unique on storm and number).
      - `product_geometries` (snapshot, advisory or none,
        product kind, CRS as an EPSG code or the verbatim WKT,
        GeoJSON, properties JSON, provenance JSON).
      - `text_products` (unique product id, code, location,
        issued-at, ATCF id, advisory, text) and `feed_items`
        (unique guid, feed, title, link, published-at,
        placeholder flag, ATCF id, slot, first and last seen).
      - `alerts` (unique alert id, sent, effective, expires,
        ends, event, the full `NwsAlert` JSON, first and last
        seen) and `alert_observations` (snapshot, location,
        alert, `found_by` JSON).
      - `settings` (key, JSON value, updated-at): application
        state such as the first-run disclaimer time, not the
        TOML settings.
      Instants go in and come out as aware UTC values (a test
      proves it). A naming convention gives every constraint a
      stable name, so SQLite batch migrations can alter it. No
      table for assessments, evidence, notifications, the
      heartbeat, briefings, or the Claude ledger is created
      here.
    </requirement>

    <requirement>
      Alembic inside the package:
      `weatherbot/services/persistence/migrations/` with
      `env.py`, `script.py.mako`, and
      `versions/0001_baseline.py`, configured in code so the
      runtime needs no `alembic.ini` (a development
      `alembic.ini`, if added, points at the same directory),
      with `render_as_batch=True` for SQLite. The baseline
      creates exactly the tables above.
    </requirement>

    <requirement>
      Opening the database, `open_database(paths)`:
      - every connection sets `foreign_keys=ON`,
        `journal_mode=WAL`, and a `busy_timeout`;
      - a new database is created at head, without a backup;
      - an existing database behind head is first copied through
        SQLite's online backup API (`sqlite3.Connection.backup`,
        consistent under WAL; never a raw file copy) to
        `backups/weatherbot-<UTC stamp>-<revision>.sqlite3`,
        then upgraded; a failed upgrade keeps the copy and
        raises a typed error that names the backup's path,
        matching the project roadmap's runbook "Migration failed
        at start-up";
      - a database at a revision the code does not know (a newer
        package wrote it) refuses to open, telling the operator
        to upgrade the package or restore a backup; the code
        never downgrades on its own.
    </requirement>

    <requirement>
      Raw-response cache,
      `weatherbot/services/persistence/raw_cache.py`: implements
      Step 2's `ValidatorStore` on `raw_responses` and
      `response_bodies`, so ETags and Last-Modified values
      survive between runs, and `save_fetch(result, source_id,
      product_key, issued_at)` records a `FetchResult`. It
      stores allowlisted response headers only, never a request
      header. A URL may hold a location's coordinates: it stays
      in the local database, and no record above DEBUG prints
      it.
    </requirement>

    <requirement>
      Repositories,
      `weatherbot/services/persistence/repositories.py`:
      `LocationRepository` (add, list, get by name, remove —
      removing a location deletes its alert observations and
      nothing else), `SnapshotRepository` (save a `Snapshot`
      with its outcomes, raw responses, storms, advisories,
      geometries, text products, feed items, alerts, and
      observations in one transaction; `latest()`;
      `load(snapshot_id)` back into an equal `Snapshot`), and
      `SettingsRepository`.
    </requirement>

    <requirement>
      Test isolation. `tests/conftest.py` gains an autouse
      fixture that sets `WEATHERBOT_CONFIG_DIR` and
      `WEATHERBOT_DATA_DIR` to directories under `tmp_path` and
      clears every other `WEATHERBOT_*` variable. A guard test
      proves `AppPaths` never reaches `platformdirs`' real
      directories during a test (patch `platformdirs` to fail if
      called with the overrides set). No test opens the
      operator's database.
    </requirement>

    <requirement>
      Tests: `upgrade head` on an empty database;
      `downgrade base`, then `upgrade head`; an upgrade from
      every revision in the history to head, parameterized over
      the script directory so later phases' revisions join
      automatically; `alembic check` (tables and migrations
      agree); the backup before an upgrade from a behind
      revision, made through the online backup API and readable;
      refusal of an unknown revision; a failed upgrade that
      keeps its backup; a `Snapshot` built from the recorded
      fixtures through the Step 2–4 parsers, saved, and loaded
      back equal; raw-body deduplication and a 304 across two
      runs through the persistent store; configuration
      precedence, and an unknown key's message without its
      value.
    </requirement>

    <requirement>
      Package smoke. In `ci.yml`'s `package` job, after
      installing the wheel into the fresh environment, run a
      short Python check with `WEATHERBOT_DATA_DIR` set to a
      temporary directory: open a new database through the
      installed package and assert it reads at head. This proves
      the migrations ship in the wheel on both runners.
    </requirement>

    <requirement>
      Contracts. Set `include_external_packages = true` in
      `[tool.importlinter]` and add a forbidden contract with
      `allow_indirect_imports = true` (the CLI reaches the
      database through `services`, an indirect import the
      contract must allow): `weatherbot.models`,
      `weatherbot.sources`, `weatherbot.engine`,
      `weatherbot.cli`, and `weatherbot.web` may not import
      `sqlalchemy` or `alembic` directly; only
      `weatherbot.services` touches the database. Prove it with
      a throwaway `import sqlalchemy` in a source module,
      reverted and recorded in the PR body.
    </requirement>

    <requirement>
      `.gitignore` gains `*.sqlite3` and `*.sqlite3-*` (the WAL
      and shared-memory files), a guard in case a data-directory
      override points into the checkout.
    </requirement>

    <requirement>
      Documentation. `CONTRIBUTING.md` gains "Local data": where
      the database and `weatherbot.toml` live on Windows and
      Linux, the overrides, that tests never touch them, and how
      to start over (delete the data directory). `README.md`
      names the data location in one sentence. `CHANGELOG.md`
      `[Unreleased]` gains an `Added` entry.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with a `# <repo-relative path>` comment.
    </requirement>
  </requirements>
</task>
```

### Step 5 acceptance criteria

- `upgrade head` succeeds on an empty database and from every revision in the
  history, `downgrade base` followed by `upgrade head` succeeds, and
  `alembic check` finds no difference between the tables and the migrations.
- An upgrade from a behind revision writes a readable backup first, through the
  online backup API; a failed upgrade keeps it and names it; an unknown revision
  refuses to open.
- A `Snapshot` built from the recorded fixtures is saved and loaded back equal,
  and a 304 is served from the persistent store across two runs.
- The isolation guard proves no test resolves the operator's real directories,
  and configuration precedence and the unknown-key message (without its value)
  are tested.
- `lint-imports` keeps `sqlalchemy` and `alembic` inside `weatherbot.services`;
  the throwaway probe failed and was reverted, as the PR body records.
- **Deployed & verified:** the first `ci.yml` run on `main` after the merge is
  green, including the `package` job's migration smoke against the installed
  wheel on Ubuntu and Windows.
- **Security gate clean** (always the final criterion): the hook passed on every
  commit; pip-audit is clean with `sqlalchemy`, `alembic`, and `platformdirs`;
  bandit and ruff's S608 are clean (no string-built SQL); the cache stores no
  request header; and `.gitignore` ignores `*.sqlite3`.

---

## Step 6 — Services and the first CLI commands

**Status:** Not started

> **Goal:** Put the clients and the database behind the first commands.
> `weatherbot.services.snapshots` fetches one snapshot — the roster, the summary
> service's storm, outlook, and wind-probability layers, the peak-surge layers,
> each active storm's arrival-time KMZ and TCP, the three TWO lists and GIS RSS
> feeds, the six outlook graphics, the breakpoints, and every US location's
> alerts — concurrently under the per-host pacing, records every source's
> outcome, lets a KMZ arrival product supersede its map-layer fallback, and
> stores the snapshot with its raw responses. `weatherbot.services.locations`
> adds a location (checked point, NWS coverage, optional zone polygon, one
> Nominatim lookup), lists, and removes. The CLI gains
> `locations add|list|remove`, `fetch`, `storms`, `alerts`, and `doctor` (paths,
> the Alembic head, reachability, and layer discovery for every register layer
> and catalog), each with `--json` output whose JSON Schema is committed under
> `docs/schema/` and validated in tests; Rich tables; the disclaimer on first
> run and a one-line notice on every read command; and live tests of every
> command for both landmarks. This step makes Phase 2 demonstrable.

**Branch:** `feature/phase02-step6-cli-read-commands`

**Deploys:** the operator's machine → the local SQLite database, created in the
user data directory and migrated to head by the first command that opens it, and
the new commands; GitHub Actions → `live-smoke.yml` runs the command tests
through the live suite.

| Setting      | Cost                                    | Balanced                                 | Quality                                  |
| ------------ | --------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Model        | GPT-6.1 Sol                             | Opus 5.5                                 | Opus 5.5                                 |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh |
| Platform     | Codex                                   | Claude Code                              | Claude Code                              |
| Effort       | Intelligence High                       | Effort High                              | Effort XHigh                             |
| Thinking     | —                                       | On                                       | On                                       |
| Conversation | **New**                                 | **New**                                  | **New**                                  |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

**Model rationale:** Step 6 is coding with an agentic secondary — live runs of
every command and a check on the operator's machine — at High complexity: it
composes every client and the database under concurrency and pacing, defines
partial snapshots, fixes five JSON contracts that Phase 5's API will mirror, and
touches the operator's real data directory for the first time. It is not novel;
each part exists, and this step assembles them by rules written here. Balanced
runs Opus 5.5 on Claude Code at Effort High, one rung above its `medium`
default, with thinking on; Quality runs it at Extra High for the integration and
privacy paths; Cost runs GPT-6.1 Sol on Codex at Intelligence High, S-tier at
agentic work. The claude.ai Max subscription funds Claude Code, ChatGPT Pro 5x
funds Codex, and each backup comes from the other maker. The conversation is new
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
       feature/phase02-step6-cli-read-commands`
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
       Phase 2 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 2`
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

    THIS STEP puts the operator's coordinates behind commands
    for the first time. They enter only through `locations add`,
    which the operator runs; they leave the machine only for
    `api.weather.gov` (on every fetch) and Nominatim (once, at
    setup); and they appear in `locations list` and nowhere else
    — not in a log line above DEBUG and not in any other
    `--json` document. The agent verifies with the landmarks in
    a temporary data directory and never reads the operator's
    database or asks for a coordinate. The committed schemas
    carry no example coordinate. `rich`, `tzdata`, and
    `jsonschema` pass pip-audit.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 2 (Sources and
    persistence). Step 6: Services and the first CLI commands.

    Current state (as of Phase 2, post-Step 5):

    - Every `required` register source has a client returning
      Step 1 models; the HTTP layer paces per host, redacts
      coordinates above DEBUG, and makes requests conditional
      through a validator store that Step 5 persists;
      `weatherbot.services.config` resolves `AppPaths` and
      `Settings`; `weatherbot.services.persistence` opens the
      database (backup before migrating, refusal of unknown
      revisions) and stores and loads `Snapshot` and `Location`
      values; tests run in `tmp_path` with both directories
      pinned there.
    - Carry-over from Step 2 (2026-10-16): Source-drift
      warnings are WARNING records on the `weatherbot.sources`
      logger with `extra={"source_drift": <source id>}`
      (`weatherbot.sources.drift.DRIFT_ATTRIBUTE`), so the
      snapshot service collects a run's warnings with a
      handler; "the Step 2 redaction filter" is
      `weatherbot.sources.http.RedactingFilter`. The map fetch
      functions are `nhc_map.fetch_storm_products`,
      `fetch_storm_display_layers`, `fetch_wind_probabilities`
      (each with the catalog and the roster's storms; the
      storm ones send no request when there is no storm, the
      `skipped` outcome), `fetch_outlook`, `fetch_breakpoints`,
      and `fetch_peak_surge`; `nhc_current_storms.
      fetch_current_storms` reads the roster.
    - Carry-over from Step 3 (2026-10-17): the product fetch
      functions are `nhc_arrival_times.fetch_arrival_times(
      fetcher, storms)`, which checks every link before the
      first request and sends none without a storm;
      `nhc_text_products.fetch_tcps(fetcher, storms)` and
      `fetch_twos(fetcher)`;
      `nhc_outlook_graphics.fetch_outlook_graphics(fetcher)`;
      `nhc_gis_rss.fetch_gis_feeds(fetcher)`; and, for `doctor`,
      `catalogs.fetch_overlay_catalogs(fetcher)` and
      `catalogs.fetch_surge_risk_catalog(fetcher)`
      (`catalogs.surge_risk_images` resolves the five images).
      The KMZ supersession rule is the pure function
      `nhc_arrival_times.prefer_kmz(products)`: pass it the
      map-layer and KMZ products together. A reused slot's TCP
      and an older TCP are Source-drift warnings, never errors.
    - The CLI is a Typer `app` with `--version` only; Typer
      brings Rich, and `tests/test_cli.py` strips ANSI escapes
      because GitHub's runners force color.
    - Rules this step applies: a KMZ arrival product supersedes
      the map-layer product of the same storm, advisory, and
      kind (issue #11); wind probabilities belong to the
      snapshot (issue #12); alerts keep `found_by`,
      `affected_zone_ids`, and both geocode lists, and nothing
      filters them by zone (issue #10 is Phase 3's); a location
      outside NWS coverage makes no NWS request; Nominatim runs
      once per location at setup.
    - The brief's §11 lists the read commands with `--json`; §12
      puts the disclaimer on first run; `DISCLAIMER.md` sits at
      the repository root and is not in the wheel.

    Files to read (every file before drafting):
    - docs/roadmap/phase02-roadmap.md (Overview, Current State,
      Steps 1–5, this step, and Step 7's checks on it).
    - docs/roadmap/ROADMAP.md (Phase 2 section 2.5 and its
      acceptance criteria; §5 "Operations & observability
      strategy").
    - docs/brief/weatherbot-v2-brief.md (§11 CLI, §12 quality,
      security, privacy).
    - DISCLAIMER.md, README.md, AGENTS.md, CONTRIBUTING.md.
    - src/weatherbot/ (every module) and tests/conftest.py,
      tests/test_cli.py.
    - docs/DATA_SOURCES.md (every source's etiquette, for
      `doctor`'s probes).
  </context>

  <goal>
    Ship the snapshot and locations services and the commands
    `locations add|list|remove`, `fetch`, `storms`, `alerts`,
    and `doctor`, with Rich output, `--json` documents validated
    against committed schemas, the disclaimer on first run,
    tests offline and live, and `doctor` run on the operator's
    machine with the database at head.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Dependencies. Add `rich` to `[project] dependencies`,
      since the CLI imports it directly; add `tzdata` with the
      marker `sys_platform == 'win32'` if the CLI renders times
      in a location's IANA zone through `zoneinfo` (Windows has
      no system zone database); add `jsonschema` to the `dev`
      group for the schema tests. Run `uv lock`;
      `scripts/audit_deps.py` must pass.
    </requirement>

    <requirement>
      Logging. The CLI configures logging once: the level from
      `Settings`, `--verbose` for DEBUG, and the Step 2
      redaction filter on the handler, so every logger is
      covered.
    </requirement>

    <requirement>
      Snapshot service, `weatherbot/services/snapshots.py`:
      `fetch_snapshot(locations)` runs inside one
      `open_client()`:
      - the roster first, since it names the active slots and
        storms; then, concurrently under the per-host pacing (an
        `asyncio.TaskGroup`): the summary service's storm,
        outlook, and probabilistic-wind layers; the peak-surge
        layers; each active storm's arrival-time KMZ pair and
        TCP; the three TWO lists; the three GIS RSS feeds; the
        six outlook graphics; the breakpoints; and, for each US
        location, its point and zone alerts. A location outside
        NWS coverage gets no NWS request. The surge-risk and
        overlay catalogs are read by `doctor` only.
      - Every source records a `SourceOutcome`: `ok`;
        `not_modified` (a 304 served from the store); `failed`
        with the error kind; or `skipped` with the reason (no
        active storm, a location outside NWS coverage). A failed
        source leaves its part of the snapshot empty and marked;
        nothing from an earlier snapshot fills it.
      - A `kmz` arrival product supersedes the `map_layer`
        product of the same storm, advisory, and kind; the
        `map_layer` product stays only when the KMZ failed.
      - The snapshot and its raw responses are saved through the
        Step 5 repositories in one transaction, and the
        persistent validator store makes repeated fetches
        conditional.
      - Records at INFO name sources, counts, and outcomes,
        never a coordinate or a URL with one.
    </requirement>

    <requirement>
      Locations service, `weatherbot/services/locations.py`:
      `add(name, lat, lon, polygon=None)` checks the name (1–64
      printable characters, unique) and the coordinates (finite
      and in range); `lookup_point` decides NWS coverage;
      `polygon` `county` or `forecast` (US locations only)
      fetches that zone's shape through `fetch_zone`;
      `reverse_geocode` runs once and its result is stored; the
      location is saved. `list()` and `remove(name)` complete
      it. Nothing re-geocodes a stored location.
    </requirement>

    <requirement>
      Commands, in `weatherbot/cli/`. Rich tables in a terminal
      and plain text otherwise; `--json` prints exactly one JSON
      document to standard output; exit codes 0 (complete), 1 (a
      partial or failed snapshot, or a failed check), 2 (a usage
      error):
      - `weatherbot locations add NAME --lat LAT --lon LON
        [--polygon county|forecast]`,
        `weatherbot locations list [--json]`,
        `weatherbot locations remove NAME`.
      - `weatherbot fetch [--json]`: fetch and store a snapshot,
        then print each source's outcome.
      - `weatherbot storms [--json] [--no-fetch]`: fetch (or,
        with `--no-fetch`, read the latest stored snapshot and
        print its age), then print the active storms — ATCF id,
        name, classification, intensity, pressure, movement, the
        latest advisory's number and time, and which products
        the snapshot holds (cone, track, watch-warning, arrival
        times with their origin, wind radii) — then the outlook
        areas per basin with their two- and seven-day chances,
        and the synoptic time of the wind-probability products.
        With no active storm, it says so and still prints the
        outlook.
      - `weatherbot alerts [--location NAME] [--json]
        [--no-fetch]`: for a location inside NWS coverage, its
        alerts — event, severity, urgency, headline, effective
        and expires in UTC and in the location's time zone,
        `found_by`, and the affected zones. For a location
        outside NWS coverage, it says NWS does not cover it and
        lists the active storms' official watch-warning segments
        verbatim (storm, code, advisory), stating that matching
        a segment to a location is Phase 3's work. With one
        location, `--location` is optional; with none, the
        command says how to add one.
      - `weatherbot doctor [--json] [--offline]`: the
        configuration and data paths, the database file, the
        Alembic revision against head, and the number of
        locations, never a coordinate; then, unless `--offline`,
        one light, coordinate-free probe per register source —
        the map services' catalogs, the roster, one TWO list
        (for `api.weather.gov`), the outlook graphics
        (conditional), the feeds, and the WMS capabilities — and
        layer discovery: every register layer name resolved,
        `{slot}` over all fifteen slots, the `StormSurgeRisk`
        group paths, and the overlay layers. Nominatim is not
        probed, because of its usage policy, and the output says
        so; the basemap tiles and the GIS archive are
        display-only or replay-only, and the output says so.
        `doctor` also lists the Source-drift warnings stored
        with the latest snapshot (an unrecognized code, an
        issuance mismatch) and exits 1 when a check fails.
    </requirement>

    <requirement>
      Disclaimer. When `settings` has no `disclaimer_shown_at`,
      a command prints the disclaimer's essentials before its
      output (to standard error under `--json`) and records the
      time. Every read command ends with a one-line notice —
      informational only, never a substitute for official
      guidance, see `DISCLAIMER.md` — and every `--json`
      document carries a `disclaimer` field. The text ships in
      the package, and a test compares it with `DISCLAIMER.md`
      so the two cannot drift.
    </requirement>

    <requirement>
      JSON documents and schemas. Pydantic models in
      `weatherbot/cli/documents.py` define each command's
      document: `schema_version`, `command`, `generated_at`,
      `disclaimer`, the snapshot's id, time, status, and source
      outcomes where it applies, and `data`, built from Step 1
      models without geometry (Phase 5's API serves geometry). A
      new development script, `scripts/export_schemas.py`,
      writes `docs/schema/locations.schema.json`,
      `fetch.schema.json`, `storms.schema.json`,
      `alerts.schema.json`, and `doctor.schema.json` (JSON
      Schema 2020-12); a test proves the committed files equal a
      fresh export. `locations list --json` is the only document
      that carries a location's coordinates.
    </requirement>

    <requirement>
      Tests without network (respx with recorded bodies; the
      Step 5 isolation fixture): every command through Typer's
      `CliRunner`, with ANSI stripped; every `--json` document
      validated against its committed schema with `jsonschema`;
      the first-run disclaimer and its recorded time; the non-US
      path of `alerts`; a partial snapshot (one source answering
      503) with its outcome table and exit code 1; `--no-fetch`
      with no stored snapshot; `storms` with an empty roster;
      `doctor --offline`; the arrival-time supersession; and no
      coordinate from `synthetic_coordinates()` in any record at
      INFO or above during a command, or in any output other
      than `locations list`.
    </requirement>

    <requirement>
      Live tests, `tests/live/test_cli_live.py`, in a temporary
      data directory with both landmarks added through
      `locations add` (values from `load_landmarks()`): `fetch`,
      `storms --json`, `alerts --json` for each landmark, and
      `doctor --json`, each document validated against its
      schema. Run `uv run pytest -m live` in the session,
      dispatch `live-smoke.yml` on the branch (`gh workflow run
      live-smoke.yml --ref
      feature/phase02-step6-cli-read-commands`), and add the
      run's URL to the PR body; after the merge, dispatch it on
      `main` and add that URL too.
    </requirement>

    <requirement>
      The operator's machine, at Stage 4. From the primary
      checkout with no `WEATHERBOT_*` override, run
      `uv run weatherbot doctor`: it creates the operator's
      database in the real data directory and migrates it to
      head. Record the output in the PR body with the paths
      shortened to `<config dir>` and `<data dir>`. The agent
      never adds a location there, never reads the operator's
      database, and never asks for coordinates: the PR body
      hands the operator `uv run weatherbot locations add <name>
      --lat <latitude> --lon <longitude>` to run themselves,
      followed by `uv run weatherbot alerts`.
    </requirement>

    <requirement>
      Documentation. `README.md` gains "Commands": every
      command, with examples that use the landmarks only.
      `AGENTS.md` lists `uv run weatherbot doctor` among the
      commands. `CONTRIBUTING.md` explains
      `scripts/export_schemas.py`. `CHANGELOG.md` `[Unreleased]`
      gains `Added` entries.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with a `# <repo-relative path>` comment; the JSON
      Schemas, which cannot carry a comment, carry `$id`
      instead.
    </requirement>
  </requirements>
</task>
```

### Step 6 acceptance criteria

- `locations add|list|remove`, `fetch`, `storms`, `alerts`, and `doctor` exist
  with `--json`; the committed schemas under `docs/schema/` equal a fresh
  export, and every document the tests produce validates against its schema.
- `storms` and `alerts` printed the current official picture for both landmarks
  against the live services, in the session and in `live-smoke.yml` on the
  branch; both run URLs are in the PR body.
- A partial snapshot is marked per source and exits 1, nothing from an earlier
  snapshot fills a failed source, and a KMZ arrival product supersedes the
  map-layer one.
- The first-run disclaimer appears once and its time is recorded; every read
  command ends with the notice; every document carries `disclaimer`; the
  packaged text matches `DISCLAIMER.md`.
- **Deployed & verified:** on the operator's machine, `uv run weatherbot doctor`
  created the database in the user data directory at the Alembic head and
  reported every source reachable and every register layer discovered (its
  output, paths shortened, is in the PR body); and `live-smoke.yml` dispatched
  on `main` after the merge ran green.
- **Security gate clean** (always the final criterion): the hook passed on every
  commit; pip-audit is clean with `rich`, `tzdata`, and `jsonschema`; no command
  logs a coordinate above DEBUG or prints one outside `locations list` (tests);
  the committed schemas hold no coordinate; and the agent used the landmarks
  only and never read the operator's database.

---

## Step 7 — QA & Verification Script

**Status:** Not started

> **Goal:** Package the verification matrix into `scripts/verify_phase02.py`
> (with `--fast`, `--py`, `--live`, `--security`, `--all`, and `--post` modes),
> produce `docs/phase02-qa-findings.md`, and add matrix entry `"02"` beside
> `"01"` in `.github/workflows/phase-verify.yml`. The script's 47 numbered
> static checks cover every Step 1 through Step 6 deliverable plus four
> self-checks; `--py` runs the lint, type, contract, model, and command suites
> and the package smoke with its migration check; `--live` runs `pytest -m live`
> against the live services with the landmarks in a temporary data directory;
> `--security` runs the four-check gate; and `--post` reports the V1–V7 matrix,
> including GitHub readbacks, Phase 1's own `--post` sweep, and `doctor` on the
> operator's machine. The same step closes Phase 2 in this roadmap and the
> project roadmap, and tags `v2.0.0-phase-2`.

**Branch:** `feature/phase02-step7-verify`

**Deploys:** GitHub Actions → `phase-verify (02)` runs on every push and pull
request from the merge on, under the aggregate `phase-verify` check that `main`
already requires; GitHub repository → the `v2.0.0-phase-2` tag, pushed after the
merge.

| Setting      | Cost                                     | Balanced                                | Quality                                 |
| ------------ | ---------------------------------------- | --------------------------------------- | --------------------------------------- |
| Model        | GPT-6.1 Sol                              | Opus 5.5                                | Opus 5.5                                |
| Backup       | Sonnet 5.5 — Claude Code · Effort Medium | GPT-6.1 Sol — Codex · Intelligence High | GPT-6.1 Sol — Codex · Intelligence High |
| Platform     | Codex                                    | Claude Code                             | Claude Code                             |
| Effort       | Intelligence Low                         | Effort Medium                           | Effort High                             |
| Thinking     | —                                        | On                                      | On                                      |
| Conversation | **New**                                  | **New**                                 | **New**                                 |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

**Model rationale:** Step 7 is coding with an agentic secondary — GitHub
readbacks and the closure — at Medium complexity: it translates this roadmap's
acceptance criteria into numbered checks, a V-matrix, a matrix entry, and a
findings rollup, with `scripts/verify_phase01.py` as the structural template,
and every check's content is written below; nothing is novel. Balanced runs Opus
5.5 on Claude Code at Effort Medium, Claude Code's default model at its
documented default effort, so the session runs as opened, with thinking on;
Quality raises it to Effort High for the findings rollup; Cost runs GPT-6.1 Sol
on Codex at Intelligence Low, enough for enumerated, independent checks. The
claude.ai Max subscription funds Claude Code, ChatGPT Pro 5x funds Codex, and
each backup comes from the other maker. The conversation is new per
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
       feature/phase02-step7-verify`
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
       Phase 2 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 2`
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
       complete. Phase 2 is
       complete. You can now move
       on to Phase 3." That
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
       one before Phase 3.
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
    reads the repository and runs the gate's tools; it never
    prints a denylist value or a coordinate; `--post` reads
    GitHub through `gh` without writing, and runs `doctor`
    against the operator's database, printing PASS or FAIL and
    shortened paths only. The workflow change keeps SHA pins,
    `contents: read`, and no secret.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 2 (Sources and
    persistence). Step 7: QA + verification script.

    Steps 1 through 6 have been implemented. Now create the
    verification script, the QA findings document, and the
    matrix entry, then close the phase.

    Reference script (pattern template):
    `scripts/verify_phase01.py` — numbered, independent static
    checks that read the repository only, standard library only
    in `--fast`, the exception type and never its text on a
    failure, a Git index read once per run, a V-matrix whose
    aggregate rows never turn a SKIP into a PASS, and the
    summary table. `verify_phase02.py` mirrors its output
    format, flag parsing, and conventions so the two read alike
    in CI logs.

    Phase 2 deliverables to verify (43 static checks across
    Steps 1 through 6, plus 4 Step 7 self-checks):

    Step 1 (domain models) — checks 1-8:
    1. `src/weatherbot/models/__init__.py` is tracked, and its
       `__all__` names `Provenance`, `Geometry`, `Location`,
       `StormSummary`, `Advisory`, `AdvisoryNumber`,
       `ConeGeometry`, `TrackPoint`, `ForecastTrack`,
       `WatchWarningSegment`, `WindRadii`, `ArrivalTimeProduct`,
       `OutlookArea`, `WindProbabilityProduct`, `NwsAlert`,
       `NwsZone`, `GeocodeResult`, `Breakpoint`, `TextProduct`,
       `GisFeedItem`, `OutlookGraphic`, `MapCatalog`,
       `OverlayCatalog`, `DisplayLayer`, and `Snapshot`.
    2. `[project] dependencies` include `pydantic` and
       `shapely`, and the `dev` group no longer lists `shapely`.
    3. The "Layers import downward only" contract ends with
       `weatherbot.models`.
    4. `tests/test_architecture.py` applies the I/O ban to
       `src/weatherbot/models`.
    5. An AST read of `WindProbabilityProduct` finds no field
       whose name contains `storm` or `atcf`.
    6. An AST read finds `time_zone`, `published_at`, and
       `origin` on `ArrivalTimeProduct` and `valid_at` on
       `ArrivalTimeLine`.
    7. `src/weatherbot/models/times.py` defines
       `parse_nhc_local_time`, `resolve_track_valid_time`,
       `parse_synoptic_time`, `from_epoch_ms`, and
       `resolve_arrival_label`.
    8. `scripts/verify_phase01.py` reads `v2.0.0-phase-1` for
       checks 7, 9, and 12 (the tag and `ls-tree` appear in the
       file).

    Step 2 (HTTP and NHC map clients) — checks 9-17:
    9. `src/weatherbot/sources/http.py` and `errors.py` are
       tracked; `http.py` defines `HOST_INTERVALS`,
       `ValidatorStore`, and `Fetcher` and passes
       `follow_redirects=False`.
    10. `src/weatherbot/sources/__init__.py` defines
        `USER_AGENT` from the package version, and
        `scripts/record_fixtures.py` imports it and holds no
        User-Agent literal.
    11. `httpx` is a runtime dependency.
    12. `src/weatherbot/sources/arcgis.py` defines
        `QUERY_PARAMETERS` with `outSR` `4326` and
        `geometryPrecision` `5`, and the recorder imports it.
    13. `nhc_current_storms.py` and `nhc_map.py` are tracked
        under `src/weatherbot/sources/`.
    14. `tests/contract/test_field_coverage.py` is tracked.
    15. `.github/workflows/live-smoke.yml` triggers on
        `workflow_dispatch` alone, declares
        `permissions: contents: read`, and runs
        `pytest -m live`.
    16. No module under `src/weatherbot/` contains
        `verify=False` or `follow_redirects=True`.
    17. The register's roster section lists `trackCone`,
        `windSpeedProbabilitiesGIS`, and both arrival-time
        objects among the fields v2 uses.

    Step 3 (NHC products) — checks 18-24:
    18. The register has an `nhc-arrival-times` row with Fixture
        `required` and an ISO `Verified` date, and an
        "Arrival-time KMZ" section.
    19. `tests/fixtures/recorded/nhc-arrival-times/` holds a
        manifest whose captures include the archived Dorian 036
        pair.
    20. `defusedxml` is a runtime dependency, and no module
        under `src/weatherbot/` imports `xml.etree`, `xml.dom`,
        `xml.sax`, or `lxml`.
    21. `nhc_arrival_times.py`, `nhc_text_products.py`,
        `nhc_outlook_graphics.py`, `nhc_gis_rss.py`,
        `catalogs.py`, and `markup.py` are tracked under
        `src/weatherbot/sources/`.
    22. The recorder's `SOURCES` includes `nhc-arrival-times`.
    23. `nhc_arrival_times.py` holds the KMZ URL pattern
        (`ARRIVAL_KMZ_URL`) anchored on
        `https://www.nhc.noaa.gov/storm_graphics/api/`; the
        source writes it as a regular expression,
        `^https://www\.nhc\.noaa\.gov/storm_graphics/api/`, so
        the check matches the escaped form.
    24. The contract tests for the Step 3 sources are tracked,
        `tests/contract/test_product_captures.py` (every capture
        of the seven sources, the field-coverage rule, and the
        archived pair's corpus checksums) among them.
        (Corrected 2026-10-17 by Step 3, which named its file
        `test_product_captures.py`.)

    Step 4 (NWS and geocoding clients) — checks 25-28:
    25. `nws.py` and `nominatim.py` are tracked under
        `src/weatherbot/sources/`, and `nws.py` defines
        `format_point`.
    26. `NwsAlert` declares `found_by`, `affected_zone_ids`,
        `geocode_same`, and `geocode_ugc`.
    27. The contract tests for `nws-points`, `nws-alerts-point`,
        `nws-alerts-zone`, `nws-zones`, and `geocode-nominatim`
        are tracked.
    28. Under `src/weatherbot/`, only `sources/nws.py` and the
        redaction in `sources/http.py` contain `/points/` or
        `point=`.

    Step 5 (persistence and configuration) — checks 29-35:
    29. `sqlalchemy`, `alembic`, and `platformdirs` are runtime
        dependencies.
    30. `src/weatherbot/services/persistence/migrations/versions/`
        holds the baseline revision, which creates `locations`,
        `snapshots`, `source_outcomes`, `raw_responses`,
        `response_bodies`, `storms`, `advisories`,
        `product_geometries`, `text_products`, `feed_items`,
        `alerts`, `alert_observations`, and `settings`.
    31. The baseline creates no table for assessments, evidence,
        notifications, heartbeats, briefings, or a ledger.
    32. `tests/conftest.py` sets `WEATHERBOT_CONFIG_DIR` and
        `WEATHERBOT_DATA_DIR` in an autouse fixture.
    33. `[tool.importlinter]` sets
        `include_external_packages = true`, and a forbidden
        contract keeps `sqlalchemy` and `alembic` out of
        `weatherbot.models`, `sources`, `engine`, `cli`, and
        `web`.
    34. `.gitignore` ignores `*.sqlite3` and `*.sqlite3-*`.
    35. `ci.yml`'s `package` job runs the migration smoke
        against the installed wheel (`WEATHERBOT_DATA_DIR`
        appears in that job).

    Step 6 (services and the first CLI commands) — checks 36-43:
    36. The CLI registers `locations` (with `add`, `list`, and
        `remove`), `fetch`, `storms`, `alerts`, and `doctor`.
    37. `docs/schema/` holds the `locations`, `fetch`, `storms`,
        `alerts`, and `doctor` schemas, each valid JSON
        declaring JSON Schema 2020-12.
    38. `scripts/export_schemas.py` is tracked.
    39. The packaged disclaimer text exists, and a test compares
        it with `DISCLAIMER.md`.
    40. `src/weatherbot/services/snapshots.py` and
        `locations.py` are tracked.
    41. `README.md` has a "Commands" section.
    42. `tests/live/` holds the command tests under the `live`
        marker.
    43. The gate is still wired: `.pre-commit-config.yaml` runs
        gitleaks, bandit, pip-audit, and the personal-data
        check, and `phase-verify.yml` runs `--security` for
        every matrix entry.

    Step 7 self-checks — checks 44-47:
    44. `scripts/verify_phase02.py` is tracked and defines all
        six mode flags.
    45. `docs/phase02-qa-findings.md` exists.
    46. `docs/roadmap/phase02-roadmap.md` exists (this
        document).
    47. `.github/workflows/phase-verify.yml`'s matrix includes
        `"01"` and `"02"`.

    Files to read (every file before drafting):
    - docs/roadmap/phase02-roadmap.md (every step's acceptance
      criteria; Post-Implementation Verification).
    - scripts/verify_phase01.py and
      tests/test_phase01_verification.py (structure,
      conventions).
    - every Phase 2 implementation file from Steps 1 through 6,
      and every Phase 2 PR body (`gh pr view <n>`), for the
      findings rollup.
    - docs/phase01-qa-findings.md (the rollup's format).
  </context>

  <goal>
    Create `scripts/verify_phase02.py` with 47 static checks and
    the V1-V7 matrix (73 checks in `--post`); create
    `docs/phase02-qa-findings.md`; add matrix entry `"02"` to
    `phase-verify.yml`; close Phase 2 in both roadmaps; tag
    `v2.0.0-phase-2`.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes, `scripts/verify_phase01.py` end to end: mirror
      its output format, flag parsing, PASS and FAIL
      conventions, and summary table.
    </requirement>

    <requirement>
      `scripts/verify_phase02.py` modes:
      - `--fast`: the 47 static checks only; standard library
        only (pathlib, re, json, tomllib, ast, the Git index);
        no network; under 30 seconds on Ubuntu and on the
        operator's Windows machine.
      - `--py`: static checks, then `ruff check`,
        `ruff format --check`, `pyright`, `lint-imports`,
        `pytest` (unit, model, contract, replay-subset, and
        command suites), and the package smoke (`uv build`, the
        wheel installed into a temporary `uv venv`, its
        `weatherbot --version` compared with the project
        version, and a new database opened at head through the
        installed package).
      - `--live`: static checks, then `uv run pytest -m live`
        (every client and command against the live services,
        landmarks only, in a temporary data directory).
      - `--security`: static checks, then gitleaks over history
        (`gitleaks git --redact`, never `gitleaks dir .`),
        bandit, `scripts/audit_deps.py`, and
        `scripts/check_personal_data.py --all` (with `--ci` when
        `CI` is set) and `--self-test`.
      - `--all`: static, py, live, and security.
      - `--post`: static checks and the V1-V7 matrix: the suites
        above; `gh` readbacks when `gh` is signed in (`main`'s
        protection requires `gate` and `phase-verify`; the
        latest `phase-verify.yml` run on `main` is green with
        both entries; the latest `live-smoke.yml` run on `main`
        is green; issues #11 and #12 are closed); `uv run python
        scripts/verify_phase01.py --post` (Phase 1's 75 checks
        still PASS); `weatherbot doctor --json` against the
        operator's database (the head reported, nothing else
        printed); and the operations proof: `doctor` against a
        temporary database stamped with an unknown revision
        exits 1 with a FAIL row.
      Each static check reads the repository only, prints one
      PASS or FAIL line with its number, and is independent of
      the others. `--fast` exits 0 only when all 47 pass, every
      mode exits 1 on any failure, and no aggregate row turns a
      SKIP into a PASS.
    </requirement>

    <requirement>
      The V-matrix (26 rows, 73 checks in `--post` with the 47
      static):
      - V1 domain models: V1.1 static checks 1-8; V1.2
        `tests/models/` passes; V1.3 `phase-verify (01)` passes
        with checks 7, 9, and 12 historical; V1.4
        `verify_phase01.py --post` reports 75 PASS.
      - V2 HTTP and map clients: V2.1 static checks 9-17; V2.2
        the HTTP-layer and map contract tests pass; V2.3 the
        field-coverage contract passes; V2.4 the latest
        `live-smoke.yml` run on `main` is green.
      - V3 NHC products: V3.1 static checks 18-24; V3.2 the Step
        3 contract and hardening tests pass; V3.3 the archived
        pair matches the corpus manifest's checksums and its
        labels resolve; V3.4 issues #11 and #12 are closed.
      - V4 NWS and geocoding: V4.1 static checks 25-28; V4.2 the
        location-source contract tests pass, the `FLC086`-shaped
        merge included; V4.3 the coordinate-hygiene tests pass.
      - V5 persistence: V5.1 static checks 29-35; V5.2 the
        migration, backup, refusal, and round-trip tests pass;
        V5.3 the installed wheel opens a new database at head;
        V5.4 `doctor` on the operator's machine reports the
        database at head.
      - V6 commands: V6.1 static checks 36-43; V6.2 the command
        and schema tests pass; V6.3 the live command tests pass
        for both landmarks.
      - V7 CI integration and security: V7.1
        `verify_phase02.py --fast` exits 0 on Ubuntu CI; V7.2
        `phase-verify.yml`'s matrix includes `"01"` and `"02"`;
        V7.3 all 47 static checks pass; V7.4
        `verify_phase02.py --security` exits 0.
    </requirement>

    <requirement>
      `tests/test_phase02_verification.py`:
      - `test_roadmap_doc_exists`.
      - `test_qa_findings_doc_exists`.
      - `test_verify_script_runs_fast` (a subprocess run of
        `--fast` exits 0 within 30 seconds, with `cwd` set to
        the repository root, since `tests/conftest.py` moves
        every test into `tmp_path`).
      - `test_phase_verify_matrix_includes_02`.
      - a synthetic failing check that proves later checks still
        run and its sample value never reaches the output.
    </requirement>

    <requirement>
      `.github/workflows/phase-verify.yml`: append `"02"` to
      `matrix.phase`, keeping `"01"`; nothing else changes. The
      aggregate `phase-verify` job, already required on `main`,
      then needs both entries; no protection change is needed,
      which `--post` confirms by readback.
    </requirement>

    <requirement>
      `docs/phase02-qa-findings.md`: a rollup per step (finding,
      class, destination, guard) from every Phase 2 PR body, in
      `docs/phase01-qa-findings.md`'s format, including at least
      the decisions on issues #11 and #12 and where they were
      verified, the live-smoke run URLs, and every Source-drift
      observation; then a "Pre-ship items" section with each
      documented limitation and the phase that owns it: Phase 3
      (issue #10's rule, `breakpoint_span`, the evacuation-order
      setter, geodesy over the native sphere, wind probabilities
      at the location level, arrival instants only where
      resolved); Phase 4 (the scheduler over the snapshot
      service, scheduled drift detection, the heartbeat, a
      `config` command); Phase 5 (the API serving these models
      and geometry); Phase 7 (display layers, the peak-surge
      fields once a capture has features, retention of raw
      responses); any basin row still open; and the NWS key
      risk.
    </requirement>

    <requirement>
      Mark the phase complete in the parent project roadmap
      (docs/roadmap/ROADMAP.md, beside this file) in the SAME
      Stage-3 commit that marks this step (Status rule):
      - `### Phase 2` gets `**Status:** Complete — <YYYY-MM-DD>;
        PR #<n>; v2.0.0-phase-2; phase02-roadmap.md` directly
        under its heading, and the heading ends in ✅.
      - Its row in the "Phase Complexity Summary" table reads
        `Complete` (Step 1's PR set it to `In progress`).
      - The header `> **Status:**` line names Phase 2 as shipped
        and Phase 3 as next.
      - Consistency audit: the Phase 2 "Acceptance criteria"
        there match this roadmap's V1-V7 checks.
      And in THIS roadmap, same commit: its phase-level
      `**Status:**` line (under the title) reads
      `Complete — <YYYY-MM-DD>`, the title and every step
      heading end in ✅, and every step's Summary Table Status
      cell reads `Complete — PR #<n>`.
    </requirement>

    <requirement>
      After the merge, run `uv run python
      scripts/verify_phase02.py --post` on clean `main` and
      record its totals in the PR body through the REST API
      (`gh pr edit` fails on this machine's token), then tag the
      merge commit: `git tag -a v2.0.0-phase-2 <merge commit> -m
      "Phase 2: sources and persistence"`, then
      `git push origin v2.0.0-phase-2`. The package version
      stays `2.0.0.dev0`.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative
      path as the first line (Python and YAML `#` comments;
      Markdown follows its siblings, which carry none).
    </requirement>
  </requirements>
</task>
```

### Step 7 acceptance criteria

- `scripts/verify_phase02.py` exists and passes on a clean tree after
  implementation; all six modes exist.
- The script has 47 static checks plus the V1–V7 post-implementation checks (73
  in total).
- `--fast` runs in under 30 seconds on Ubuntu CI and on the operator's Windows
  machine.
- `--post` runs cleanly on the operator's Windows machine with `gh` signed in,
  reporting V1.1 through V7.4 green, Phase 1's 75 checks among them.
- `docs/phase02-qa-findings.md` is complete, with every rollup section and a
  destination for every finding.
- `.github/workflows/phase-verify.yml` runs matrix entries `"01"` and `"02"` on
  every pull request, under the required aggregate `phase-verify`.
- `--security` exits 0 (secret scan, SAST, dependency audit, and the
  personal-data check clean over the phase's surface); V7.4 is green.
- Branch protection still passes on the resulting PR.
- **Deployed & verified:** the first `phase-verify.yml` run on `main` after the
  merge is green with both entries; `gh api
  repos/nathanramoscfa/weatherbot/branches/main/protection --jq
  .required_status_checks` still names `gate` and `phase-verify`; and `git
  ls-remote --tags origin v2.0.0-phase-2` shows the tag at the merge commit.
- **Operations:** the phase's local runtime surfaces — the CLI and the database
  — have `doctor` as their health signal and its exit status as their alarm;
  `--post` injected a failure (a temporary database stamped with an unknown
  revision) and saw `doctor` report FAIL and exit 1. `live-smoke.yml` reports
  through its run status and GitHub's failure email; scheduled monitoring
  arrives in Phase 4.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff, and the `security` job and both
  `phase-verify` entries are green.
- **Phase closed, nothing carried.** Every finding recorded in
  `docs/phase02-qa-findings.md` has a destination (fixed, an issue number, or a
  named phase that owns it), the "Not in scope" section below is current, and no
  untracked item remains. Every step of this roadmap, this one included, reads
  `**Status:** Complete — PR #…` on `main` under a ✅ heading, the Summary
  Table's Status column and this roadmap's phase-level Status line say
  `Complete` under a ✅ title, and the project roadmap's Phase 2 entry (under a ✅
  heading), its summary-table row, and its header status line say `Complete` —
  all landed in this step's PR. This step's final response ends with the line
  "Step 7 is complete. Phase 2 is complete. You can now move on to Phase 3." in
  place of the usual "Step 7 is complete. You can now move on to Step 8." — same
  Stage 6 rule: no "Follow-ups", no trailer.

---

## Post-Implementation Verification

Every V1–V7 check below runs **automatically in CI** on every push and pull
request, except these. The GitHub readbacks (V1.3 on `main`, V2.4, V3.4), Phase
1's own `--post` sweep (V1.4), and `doctor` against the operator's database
(V5.4) run in `--post` on the operator's Windows machine, because they need the
operator's environment, the network, or reads the workflow token lacks. The live
suites (V6.3, and every client's live tests) run in `--live` locally and in
`live-smoke.yml`, which is dispatched by hand rather than run on every pull
request, because they call the live services.

| Mode         | Workflow                                              | Runner           | Coverage                                                                 |
| ------------ | ----------------------------------------------------- | ---------------- | ------------------------------------------------------------------------ |
| `--fast`     | `phase-verify.yml` (matrix entry `"02"`)              | Ubuntu           | Static checks 1–47: V1.1, V2.1, V3.1, V4.1, V5.1, V6.1, V7.1–V7.3          |
| `--py`       | `ci.yml` (`lint`, `typecheck`, `test`, `package`)     | Ubuntu + Windows | V1.2, V2.2, V2.3, V3.2, V3.3, V4.2, V4.3, V5.2, V5.3, V6.2                |
| `--security` | `ci.yml` `security` and `phase-verify.yml`            | Ubuntu           | V7.4 (secret scan + SAST + dependency audit + personal-data check)        |
| `--live`     | `live-smoke.yml` (`workflow_dispatch`)                | Ubuntu           | V6.3 and every client's live tests                                        |
| `--post`     | local, on the operator's machine                      | Windows          | V1.3, V1.4, V2.4, V3.4, V5.4 + the full V-check sweep                      |

Local invocations remain available for ad-hoc runs and pre-release sweeps:

```bash
uv run python scripts/verify_phase02.py --post   # static + V1-V7 + post checks
```

`--post` is the canonical command to run before tagging `v2.0.0-phase-2`.

Other modes:

```bash
uv run python scripts/verify_phase02.py --fast      # static only (CI-safe)
uv run python scripts/verify_phase02.py --py        # + lint, types, tests, wheel
uv run python scripts/verify_phase02.py --live      # + live services, landmarks only
uv run python scripts/verify_phase02.py --security  # the four-check gate
uv run python scripts/verify_phase02.py --all       # py + live + security
```

The script reports each V-check by id (V1.1, V2.1, ...) so a failure in any
workflow above maps directly to the corresponding row below.

### V1 — Domain models

> **Automated in CI.** `phase-verify.yml` → V1.1 and V1.3; `ci.yml` → V1.2;
> `--post` on the operator's machine → V1.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V1.1 | Static checks 1–8 all PASS (public models, runtime dependencies, models layer, I/O ban, #11 and #12 shapes, time functions, historical Phase 1 checks). | `phase-verify.yml` runs `verify_phase02.py --fast` on every push/PR.       |
| V1.2 | `tests/models/` passes: strict and frozen models, JSON round trips, schemas, the time rules on recorded examples. | `ci.yml` `test` (`--py` locally).                                          |
| V1.3 | `phase-verify (01)` passes with checks 7, 9, and 12 reading `v2.0.0-phase-1`.                  | `phase-verify.yml` matrix entry `"01"`; `--post` reads the latest run on `main`. |
| V1.4 | `verify_phase01.py --post` reports all 75 Phase 1 checks PASS.                                 | `--post`, local only.                                                      |

### V2 — HTTP foundation and NHC map clients

> **Automated in CI.** `phase-verify.yml` → V2.1; `ci.yml` → V2.2 and V2.3;
> `--post` → V2.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V2.1 | Static checks 9–17 all PASS (HTTP layer, one User-Agent, ArcGIS parameters, map clients, coverage contract, dispatch-only workflow, no TLS bypass or redirect, amended roster fields). | `phase-verify.yml --fast`.                                                 |
| V2.2 | The HTTP-layer tests and the roster and map contract tests pass, redaction included.          | `ci.yml` `test`.                                                           |
| V2.3 | The field-coverage contract matches the register and fails on every deleted field.            | `ci.yml` `test`.                                                           |
| V2.4 | The latest `live-smoke.yml` run on `main` is green.                                           | `--post` (`gh run list`).                                                  |

### V3 — NHC products

> **Automated in CI.** `phase-verify.yml` → V3.1; `ci.yml` → V3.2 and V3.3;
> `--post` → V3.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V3.1 | Static checks 18–24 all PASS (register row and section, recorded pair, `defusedxml` only, clients, recorder source, URL pattern, contract tests). | `phase-verify.yml --fast`.                                                 |
| V3.2 | The Step 3 contract and hardening tests pass (zip limits, entity refusal, link pattern).      | `ci.yml` `test`.                                                           |
| V3.3 | The archived pair matches the corpus manifest's checksums, and its labels resolve to the listed instants. | `ci.yml` `test`.                                                           |
| V3.4 | Issues #11 and #12 are closed.                                                                | `--post` (`gh issue view`).                                                |

### V4 — NWS and geocoding clients

> **Automated in CI.** `phase-verify.yml` → V4.1; `ci.yml` → V4.2 and V4.3.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V4.1 | Static checks 25–28 all PASS (clients, the alert's issue #10 inputs, contract tests, coordinates confined to the NWS client). | `phase-verify.yml --fast`.                                                 |
| V4.2 | The five location sources' contract tests pass, the `FLC086`-shaped merge and the non-US path included. | `ci.yml` `test`.                                                           |
| V4.3 | No record at INFO or above, error message, or `repr` exposes a coordinate.                    | `ci.yml` `test`.                                                           |

### V5 — Persistence and configuration

> **Automated in CI.** `phase-verify.yml` → V5.1; `ci.yml` → V5.2 and V5.3;
> `--post` → V5.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V5.1 | Static checks 29–35 all PASS (dependencies, baseline tables and no later-phase table, isolation fixture, database contract, ignore rules, wheel smoke). | `phase-verify.yml --fast`.                                                 |
| V5.2 | Migrations upgrade from empty and from every revision, back up first, refuse unknown revisions, and round-trip a `Snapshot`. | `ci.yml` `test`.                                                           |
| V5.3 | The installed wheel opens a new database at head on Ubuntu and Windows.                       | `ci.yml` `package` (`--py` locally).                                       |
| V5.4 | `doctor` reports the operator's database at the Alembic head.                                 | `--post`, local only.                                                      |

### V6 — Services and the first CLI commands

> **Automated in CI.** `phase-verify.yml` → V6.1; `ci.yml` → V6.2;
> `live-smoke.yml` and `--live` → V6.3.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V6.1 | Static checks 36–43 all PASS (commands, schemas, exporter, disclaimer, services, README, live tests, the gate still wired). | `phase-verify.yml --fast`.                                                 |
| V6.2 | Every command's tests pass and every `--json` document validates against its committed schema. | `ci.yml` `test`.                                                           |
| V6.3 | `fetch`, `storms`, `alerts`, and `doctor` run against the live services for both landmarks.   | `live-smoke.yml` (dispatch) and `--live`.                                  |

### V7 — CI integration + security

> **Automated in CI.** `phase-verify.yml` → V7.1 through V7.4 on every push/PR.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V7.1 | `verify_phase02.py --fast` exits 0 on Ubuntu CI.                                              | `phase-verify.yml` matrix entry `"02"`.                                    |
| V7.2 | `phase-verify.yml`'s matrix includes `"01"` and `"02"`.                                        | `phase-verify.yml --fast` static check 47.                                 |
| V7.3 | All 47 static checks in `verify_phase02.py` pass.                                             | `phase-verify.yml --fast` records a pass only when every static check passed. |
| V7.4 | `verify_phase02.py --security` exits 0 (secret scan + SAST + dependency audit + personal-data check). | `phase-verify.yml` `--security` and `ci.yml` `security` on every push/PR.  |

---

## Summary Table

| Step | Scope                    | Model                    | Platform     | Reasoning dial      | Thinking | Conv | Status      |
| ---- | ------------------------ | ------------------------ | ------------ | ------------------- | -------- | ---- | ----------- |
| 1    | Domain models            | Opus 5.5                 | Claude Code  | Effort High         | On       | New  | Complete — PR #20 |
| 2    | HTTP + NHC map clients   | Opus 5.5                 | Claude Code  | Effort High         | On       | New  | Complete — PR #21 |
| 3    | NHC products             | Opus 5.5                 | Claude Code  | Effort High         | On       | New  | Not started |
| 4    | NWS + geocoding clients  | Opus 5.5                 | Claude Code  | Effort Medium       | On       | New  | Not started |
| 5    | Persistence + config     | Opus 5.5                 | Claude Code  | Effort High         | On       | New  | Not started |
| 6    | Services + CLI commands  | Opus 5.5                 | Claude Code  | Effort High         | On       | New  | Not started |
| 7    | QA + verify_phase02.py   | Opus 5.5                 | Claude Code  | Effort Medium       | On       | New  | Not started |
| V1   | Domain models            | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V2   | HTTP + NHC map clients   | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V3   | NHC products             | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V4   | NWS + geocoding clients  | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V5   | Persistence + config     | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V6   | Services + CLI commands  | CI: live-smoke.yml       | --           | --                  | --       | --   | --          |
| V7   | CI integration           | CI: phase-verify.yml     | --           | --                  | --       | --   | --          |

Each step's row restates the Balanced column its **Runs:** line names; the Cost
and Quality columns, and the rule for a pool that reads `tight` or `exhausted`,
live in the step's own Settings table.

---

## Model selection blocks

```text
PROMPT: Step 1 — Domain models
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a planning secondary — the shared domain models every later phase reads, High complexity by cross-cutting scope. PICK: Opus 5.5 is S-tier in coding and planning (AA Intelligence Index 57.6), the ladder's Balanced pick. EFFORT: High, one rung above Opus 5.5's medium default, fits a fully specified but cross-cutting design; Extra High is the Quality column's.

PROMPT: Step 2 — HTTP foundation and NHC map clients
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — the network layer, the roster and map clients, and a field-coverage contract, High complexity. PICK: Opus 5.5 is S-tier in coding and agentic work (AA Intelligence Index 57.6), the ladder's Balanced pick. EFFORT: High fits many interacting but known request patterns that the Phase 1 recorder already proves.

PROMPT: Step 3 — NHC products
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a knowledge secondary — hardened KMZ and XML parsing, issue #11's time rule, and a live-verified register amendment, High complexity. PICK: Opus 5.5 is S-tier in coding and knowledge (HLE 61.4%), the ladder's Balanced pick. EFFORT: High fits specified rules applied to real products; no novel reasoning earns more.

PROMPT: Step 4 — NWS and geocoding clients
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: Medium
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding — bounded clients over five endpoints with recorded answers and written hygiene rules, Medium complexity. PICK: Opus 5.5 is Claude Code's default model and S-tier in coding (AA Intelligence Index 57.6). EFFORT: Medium is its documented default, so the session runs as opened.

PROMPT: Step 5 — Persistence and configuration
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding — tables, an in-package Alembic baseline, backup-before-migrate, configuration precedence, and test isolation, High complexity. PICK: Opus 5.5 is S-tier in coding (AA Intelligence Index 57.6), the ladder's Balanced pick. EFFORT: High fits a known pattern whose edge cases every later phase inherits.

PROMPT: Step 6 — Services and the first CLI commands
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — the snapshot service and five commands across every layer, with live and on-machine checks, High complexity. PICK: Opus 5.5 is S-tier in coding and agentic work (AA Intelligence Index 57.6), the ladder's Balanced pick. EFFORT: High fits an integration of specified parts under concurrency and privacy rules.

PROMPT: Step 7 — QA + verify_phase02.py
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: Medium
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: mechanical translation of this roadmap's acceptance criteria into a verification script, a matrix entry, and a findings rollup. PICK: known pattern, no novel reasoning — Opus 5.5, Claude Code's default model, S-tier in coding (AA Intelligence Index 57.6). EFFORT: Medium, its documented default, fits enumerated checks whose content this roadmap already writes down.
```

---

## Not in scope (from product roadmap)

The project roadmap's Phase 2 section carries no "Not in scope" list; these
items follow from its phase boundaries and its §6 "Out of Scope":

- The engine: levels, rules, evidence, assessments, thresholds, geodesy over the
  native sphere, mapping a location to its breakpoint span, issue #10's rule,
  and the command that sets the evacuation-order toggle. Phase 3 builds them on
  this phase's models.
- The scheduler, change detection, notifications, the heartbeat and staleness
  rules, `check --once`, `status`, Task Scheduler registration, and a `config`
  command. Phase 4.
- The FastAPI API, server-sent events, the frontend, and the OpenAPI schema.
  Phase 5; this phase's JSON Schemas describe CLI documents only.
- Claude, briefings, the change summary, and the Claude ledger. Phase 6.
- Map display of radar, satellite, surge rasters, past track, the wind swath,
  and peak surge; the multi-location user interface and custom location
  polygons; retention of history and raw responses. Phase 7.
- A PyPI release, trusted publishing, and LAN mode. Phase 8.

Additionally not in scope for this phase:

- A scheduled live smoke or drift detection. `live-smoke.yml` is manual by
  design; Phase 4's heartbeat and staleness rules watch the live sources.
- Re-recording the 2026-10-12 capture set. It is the only set with an active
  storm's products; a re-record happens under Source drift, and an open basin's
  row is re-checked only while a storm is active there.
- Live per-storm shapefiles and KMZ other than the arrival-time KMZ, gridded
  GRIB products, and probabilistic storm surge. They stay on the register's "Not
  used" list.
- API keys and their handling. Every Phase 2 source is keyless; if NWS adds a
  key, Step 4's stop rule opens an issue first.
- A package version bump. The version stays `2.0.0.dev0` until the release
  candidate in Phase 8; the milestone tag marks the phase.
- Dependabot PRs #8 and #9. They are independent maintenance, outside every
  step.

---

_This roadmap is the execution plan for Phase 2. Each step's `**Status:**` line
is flipped by that step's own PR (Status rule), so this file on `main` is the
phase's ledger — `grep -n '^\*\*Status:\*\*'` reports progress. After all steps
and verification pass, and every finding has a destination, Phase 2 is complete
— declared with the line "Phase 2 is complete. You can now move on to Phase 3."
and nothing after it — and Phase 3 (Threat engine) inherits the shared domain
models in `weatherbot.models`, a typed client with a recorded contract for every
register source, alerts that carry issue #10's inputs, arrival times resolved
from their own products, wind probabilities held by the snapshot, geometry with
explicit CRS provenance, stored snapshots with their raw responses, and the
`doctor`, `fetch`, `storms`, and `alerts` commands it extends._
