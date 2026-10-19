# Phase 3 Roadmap — Threat engine

**Status:** In progress

## Overview

Phase 3 opens the gate between the official picture and a decision. A pure,
deterministic engine in `weatherbot.engine` turns one snapshot and one location
into an assessment: one of the five levels of the brief's §7 ladder, the
evidence behind it, a threat record for each active storm, and the typed
changes since the previous assessment. Golden replays of four historical storms
against the two public landmarks prove it, and `weatherbot status` and
`weatherbot replay` print it. It does not run anything on a schedule, send a
notification, or judge staleness (Phase 4), serve a page (Phase 5), or explain
a level in prose of its own (Phase 6, which quotes `docs/ALERT-LADDER.md` and
the evidence). The work is one phase because the rules, the geometry they
test, and the replays that calibrate them are one contract: a threshold is only
as good as the historical timelines that bound it, and every later phase shows,
notifies on, or narrates the level this phase decides.

The phase lands in 7 layers:

1. **Geodesy and geometry** — `weatherbot.engine.geodesy` and
   `weatherbot.engine.geometry`: the figure of each geometry's CRS (the WGS 84
   ellipsoid for live geometry, the archive's 6,371,200 m sphere for replay
   geometry) through `pyproj.Geod`; geodesic distance and initial bearing;
   antimeridian-safe containment and intersection; cone repair with a recorded
   reason; the nearest point of a line, and whether it is the line's end; and a
   forecast track's closest approach to a location in time and distance.
   Hypothesis property tests, an engine coverage floor of 90 percent in CI, a
   determinism guard, and `verify_phase02.py` check 31 read as a historical
   check against `v2.0.0-phase-2`.
2. **Replay snapshots** — a replayed advisory becomes a `Snapshot` whose
   origin is `replay`: its storms carry no roster record, its records cite the
   GIS archive, and nothing a replay product does not state is invented. The
   parser `weatherbot.sources.nhc_gis_archive` reads the converted archive
   collections through a declared field list that the register lists; the
   reader `weatherbot.services.replay` verifies every file's SHA-256 against
   the corpus manifest before parsing and yields one snapshot per advisory in
   order. The committed subset gains each storm's wind-speed probabilities
   clipped to a window around each public landmark, about 0.6 MiB, so every
   pull request replays every product the ladder reads.
3. **Ladder rules and evidence** — `weatherbot.models.ladder` and
   `weatherbot.models.assessment`; the eleven ordered rules of
   `weatherbot.engine.rules`; `assess(snapshot, location, thresholds)`; issue
   #10's rule for NWS alerts; the coverage rule for NHC's watch-warning
   segments; a location's breakpoint span; the location's wind-speed
   probability bands; the seven-day development regions; the evacuation-order
   toggle; the `[engine]` thresholds in `weatherbot.toml`; and an assessment
   that names every input it lacked.
4. **Per-storm threats and change events** — a `StormThreat` per active storm
   (category, in-cone, distance and bearing from the current center, the
   forecast track's closest approach, and the earliest and most-likely arrival
   of tropical-storm-force winds read from the arrival-time products, with the
   closest approach as the labelled fallback) and `diff(previous, current)`,
   the typed change events Phase 4's notification policy consumes.
5. **Calibration, golden replays, and the written ladder** —
   `scripts/calibrate_ladder.py` sets each threshold's default from the replay
   corpus and records the interval the corpus allows; eight golden timelines
   (four storms against two landmarks) under `tests/golden/replay/`, reviewed
   once by the operator and then frozen; a mutation suite in which every rule
   and every threshold breaks at least one golden; and `docs/ALERT-LADDER.md`,
   whose levels, rules, and thresholds tables a test renders from code and
   compares.
6. **Stored assessments and the commands** — Alembic revision `0003` with the
   assessment and evidence tables and their writer; `weatherbot status`, which
   assesses every location against a fresh or stored snapshot and stores the
   result with its changes; `weatherbot replay`; `weatherbot locations
   evacuation`; the breakpoint span filled and shown; and `weatherbot alerts`
   saying which official products cover the location.
7. **QA + `verify_phase03.py`** — `scripts/verify_phase03.py` (`--fast`,
   `--py`, `--live`, `--security`, `--all`, `--post`),
   `docs/phase03-qa-findings.md`, and matrix entry `"03"` beside `"01"` and
   `"02"` in `phase-verify.yml`; Phase 3 closed in this roadmap and the
   project roadmap; the `v2.0.0-phase-3` tag.

The ship test for Phase 3 is straightforward: the eight golden replays equal the
engine's timelines on every pull request, from the committed corpus alone;
removing any rule, swapping two adjacent rules the corpus can tell apart, or
moving any threshold past a finite end of its recorded calibration interval
breaks at least one golden; the import contracts and the architecture scan
prove that `weatherbot.engine` imports no I/O library and reads no clock, and
its branch coverage is at least 90 percent in CI; `weatherbot replay` runs
each storm against each landmark in under 10 seconds on the operator's
machine; `docs/ALERT-LADDER.md` equals the tables rendered
from code; `weatherbot status` stores and prints an assessment for each
landmark against the live services, and `doctor` reports revision `0003` at
the head on the operator's database; issue #10 is closed by a rule with a
golden scenario built from the recorded zone-alert capture; Phase 1's and Phase
2's verification still pass, with check 31 read from `v2.0.0-phase-2`; and
`scripts/verify_phase03.py --fast` exits 0 on Ubuntu CI with `phase-verify
(01)`, `(02)`, and `(03)` green.

**Pre-requisite:** Phase 2 closed on 2026-10-18 (PR #26, `v2.0.0-phase-2`). Its
models are the engine's whole input vocabulary: snapshots with one outcome per
source, alerts that keep issue #10's inputs, arrival products whose lines carry
resolved instants (issue #11), wind probabilities held by the snapshot (issue
#12), and geometry with an explicit CRS. Its snapshot service, persistence, and
commands are what `status` composes. Phase 1's replay corpus is what the golden
replays read, and its gate, required checks, socket guard, and working-directory
guard are what every Phase 3 commit runs under. The planning kit stays at
roadmodel 0.2.86: the export run on 2026-10-18 before this roadmap changed no
tracked file.

**Dependency:** Phase 4 does not start until Phase 3's V-checks are green. Its
monitor runs `assess` on every scheduled snapshot, stores the result through
this phase's repository, and turns `diff`'s change events into notifications;
its staleness rule extends `status`. Phase 5's API serves the assessment,
evidence, and threat models; Phase 6's briefing quotes `docs/ALERT-LADDER.md`
and the evidence and can never change a level; and Phase 7's replay scrubber
drives the same replay snapshots and engine.

**Design rationale (decisions and clarifications of the brief and the project
roadmap).** Twelve decisions, each made against recorded evidence while this
roadmap was written. The project roadmap records each one that changes it, in
this roadmap's own pull request. Step agents treat them as settled spec unless
the operator changes them.

- *The engine is a pure function, and its clock is the snapshot's.*
  `assess(snapshot, location, thresholds)` reads the snapshot's instant (a live
  snapshot's `completed_at`, a replay snapshot's advisory issuance) and never
  the wall clock, a file, the environment, or the network; `diff(previous,
  current)` reads two assessments. The services own time, storage, and the
  previous assessment. A test scans the engine for clock, random, filesystem,
  and environment use.
- *Geodesy follows each geometry's CRS, and nothing is relabeled.* Live
  geometry is `EPSG:4326`, so its distances use the WGS 84 ellipsoid; replay
  geometry keeps the archive's native geographic `D_Sphere` (radius
  6,371,200 m, the operator's decision of 2026-10-15), so its distances use
  that sphere; both go through `pyproj.Geod`. A location's WGS 84 point is
  placed into a native-sphere geometry's coordinates unchanged, because PROJ
  itself offers no other transformation: checked on 2026-10-18 with pyproj
  3.8.0 and PROJ 9.8.1, the only transformation from WGS 84 to the archive's
  WKT is a "ballpark geographic offset" of unknown accuracy, and it returned
  both landmarks with zero change. Step 1 proves that in a test, and evidence
  names the CRS of the geometry it tested. The two figures differ by about
  0.13 percent: the landmarks are 297.53 km apart on WGS 84 and 297.14 km apart
  on the archive sphere.
- *Issue #10: an NWS alert sets a level only when it covers the location.* It
  covers the location when the point query returned it, or when its UGC list
  (`affected_zone_ids`, `geocode_ugc`) names the location's forecast zone or
  county zone. A county-query alert whose list names neither is context
  evidence, shown with the zones it does cover, and never sets the level: a
  warning for one end of a county does not raise the whole county, and an
  official alert in the county is never hidden. Only alerts with status
  `Actual`, a message type other than `Cancel`, and an `expires` after the
  snapshot's instant count. The two recorded cases fix the rule's sides: the
  register's `FLC086` Coastal Flood Statement of 2026-10-12 (zones `FLZ069`,
  `FLZ075`, `FLZ174`; the landmark's zone is `FLZ173`) is context, and the Rip
  Current Statement recorded on 2026-10-17 (found by the point, `FLC086`, and
  `FLZ173`) covers the location.
- *Watches and warnings come from both official sources for every location.*
  An NWS alert counts by the rule above; an NHC watch-warning segment counts
  when the geodesic distance from the location to the segment is at most
  `coastal_reach_km` and the segment's nearest point lies inside the segment,
  or within `segment_end_tolerance_km` of its end. Replay holds no NWS alerts,
  so this is also what makes the Miami-Dade golden replay an official ladder.
  The corpus separates the cases with wide margins (all 310 advisories against
  both landmarks, measured 2026-10-18): every covering segment passes 1.1 km
  from the Miami-Dade landmark or 3.8 km from the Nassau landmark, with its
  nearest point inside the segment; the closest segment that ends short of a
  landmark ends 22.6 km away (a Dorian tropical-storm watch that stopped north
  of Miami-Dade); and the closest non-covering segment that runs alongside a
  landmark is 58.2 km away (Andros Island, from Nassau).
- *The breakpoint span names a location's coast; it does not decide coverage.*
  NHC's catalogue (`Watch_Warning_Breakpoints`, 549 points, loaded 2026-04-30)
  follows the coast in `objectid` order and represents the Bahamas as six
  regions. The span is the catalogue pair that brackets the location's coast —
  Ocean Reef to the Miami-Dade/Broward County Line for the Miami-Dade landmark —
  or the region that holds it — `Bahamas (NW)` for the Nassau landmark. It
  cannot decide coverage: the archive's segments name no breakpoint, historical
  breakpoints differ from today's catalogue, and the Bahamas segment that covers
  Nassau is a two-vertex line 3.8 km from the landmark but 18 km from the
  region's catalogue point. The engine computes the span from a snapshot's
  catalogue, the locations service stores it, and evidence quotes it.
- *The triggers of brief §7, made exact.* Level 5: a Hurricane Warning (NWS
  event `Hurricane Warning`, NHC code `HWR`) covers the location. Level 4: a
  Tropical Storm Warning (`TWR`) or a Hurricane Watch (`HWA`) covers it, or the
  operator's evacuation-order toggle is on. Level 3: a Tropical Storm Watch
  (`TWA`) covers it; or the location is inside the cone of a storm that is a
  hurricane (64 kt or more) at the advisory or at any forecast point up to its
  closest approach, and that closest approach falls within `cone_horizon_h`;
  or the location's 64-kt wind-speed probability band starts at or above
  `hurricane_wind_floor_pct`. Level 2: the location is inside the cone of any
  other active storm; or inside a seven-day potential development region whose
  seven-day chance is at least `development_chance_floor_pct`; or its 34-kt
  band starts at or above `tropical_storm_wind_floor_pct`. Level 1: none of
  these. The brief's level 2 names "a tropical storm or depression"; it now
  covers every cone that does not reach level 3, so a hurricane's cone beyond
  the horizon is never All Clear. The brief's "arrival inside the forecast
  window" is read from the forecast track, which every advisory carries, live
  or replayed; the arrival-time products exist only for full advisories, and
  only since 2018, so Irma has none.
- *Rules stop at the first match, and the order is fixed.* `hurricane_warning`,
  `tropical_storm_warning`, `hurricane_watch`, `evacuation_order`,
  `tropical_storm_watch`, `hurricane_cone`, `hurricane_wind_probability`,
  `storm_cone`, `development_region`, `tropical_storm_wind_probability`,
  `all_clear`. Each rule reads every official source it names and records
  every match as evidence. Within a level, official products precede the
  operator's toggle, and both precede geometry and probability, as the brief's
  priority order says.
- *Thresholds are configuration with calibrated defaults.* The six thresholds
  above live in `weatherbot.models.ladder.Thresholds`, are set in the
  `[engine]` table of `weatherbot.toml` or by `WEATHERBOT_ENGINE_*` overrides,
  and are recorded in every assessment. Steps 3 and 4 use provisional defaults
  inside the corpus margins (coastal reach 25 km, end tolerance 5 km, cone
  horizon 120 h, hurricane wind floor 10 percent, tropical-storm wind floor
  5 percent, development chance floor 0 percent). Step 5 sets the final
  defaults from replay calibration (TBD until then) and records each one's
  interval and evidence in `docs/ALERT-LADDER.md`. The corpus holds no
  outlook, so the development floor is bound by recorded scenarios instead,
  and the document says so.
- *Every pull request replays every product the ladder reads.* Wind-speed
  probabilities for the four storms would take 52.9 MiB in full, and 12.1 MiB
  even as only the unmodified bands that contain a landmark; clipped to a box
  of one degree on each side of each public landmark they take about 0.6 MiB,
  inside the replay subset's remaining 3.3 MiB. The committed subset gains
  those windows, each product records the area it covers, and the engine
  reads a windowed product only at a point inside it. The full products, the
  arrival-time KMZ (8.3 MiB), and the wind radii (22 MiB) stay in the cache;
  `fetch_replay_corpus.py convert --full` writes a complete local conversion
  for the operator's own locations.
- *An assessment says what it could not check.* A missing or failed input —
  NWS alerts outside a replay or from a failed source, an absent wind-speed
  probability product, a cone that could not be repaired — is named in the
  assessment, and its level reads as a floor: "All Clear from the products
  fetched; NWS alerts were not checked". Phase 4's staleness banner builds on
  this.
- *Assessments are stored by the code that writes them.* Revision `0003`
  creates the assessment and evidence tables with `weatherbot status`, their
  writer (tables arrive with their writers, as Phase 2 decided); replay
  assessments are never stored; removing a location removes its assessments.
  `verify_phase02.py` check 31, which forbids those tables, reads the
  revisions at `v2.0.0-phase-2` from Step 1 on (PR #27), as Phase 2 Step 1 did
  for Phase 1's checks 7, 9, and 12.
- *Storm-surge and extreme-wind products do not move the ladder.* Brief §7
  names hurricane and tropical-storm watches and warnings only. An NWS Storm
  Surge Warning or Watch, or an Extreme Wind Warning, that covers the location
  is shown as official context evidence. Whether one should move the ladder is
  the operator's call; Step 3 opens an issue for it. The package version stays
  `2.0.0.dev0`, and the milestone tag marks the phase.

**Branch strategy.** Every step in this phase lands on its own short-lived
feature branch (`feature/phase03-step<M>-<slug>`), opens a pull request against
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
git checkout -b feature/phase03-step<M>-<slug>
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
feature/phase03-step<M>-<slug> <worktree-path> origin/main`, the worktree is
bootstrapped before any test or build (`uv sync` in the worktree — a worktree
has none of the primary tree's untracked state, such as `.venv` or the replay
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
(injection, unsafe deserialization or archive parsing, a path read outside the
directory it names, a coordinate or a location's distance and bearing in a log
line above DEBUG). The gate is wired into the pre-commit hook and re-run in CI,
so a security issue introduced while implementing a step is caught during
development — before it reaches the branch, the PR, or `main`. See the project
roadmap's "Security & privacy strategy" → "Per-step security gate" for the
canonical checks and tooling; each step's XML `<task>` carries a `<security>`
block restating them for the agent, and each step's Acceptance Criteria ends
with a security check. AI coding agents executing a step MUST treat the
security gate as part of the step's definition of done, exactly like its tests.
This phase computes on the operator's coordinates for the first time: a
distance and a bearing from a storm's public center locate the operator's home
as surely as its coordinates do, so evidence stays in the local database and the
terminal, every test and golden uses the public landmarks or points derived at
run time from public products, and no assessment of the operator's location
reaches a fixture, a log line above DEBUG, or a conversation.

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
environment variable: every source stays keyless, and the `WEATHERBOT_ENGINE_*`
overrides are optional. Its new local surfaces are the assessment tables (Step
6) and the `status` and `replay` commands. The operator's own location is
assessed only when the operator runs `status`; an agent verifies with the public
landmarks and never asks for, reads, or prints the operator's coordinates or an
assessment of the operator's location. See the project roadmap's "Release &
deployment strategy" for the surfaces table, promotion path, migrations, and
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
contract test in the same PR. A golden replay that changes is never "fixed" by
regenerating it: a rule or threshold change that moves a golden needs the
operator's approval in the PR (Step 5). A step's PR contains the step plus
blocking fixes only, and lists the issues it opened. When a merged PR
auto-closes an issue, the environment check is what earns the close — reopen or
follow up if a gap remains. `docs/phase03-qa-findings.md` is the rollup: every
finding, its class, and the guard added so the class cannot recur.

**Status rule.** Every step carries a `**Status:**` line directly under its
`## Step N — …` heading, before the Goal, and this file on `main` is the ledger
of what is done — never a chat transcript, never a later conversation
reconstructing history from `git log`. The line reads `Not started` when this
roadmap is written and is flipped by the step's OWN pull request: at Stage 3,
right after `gh pr create` returns the PR number, the agent sets it to
`Complete — PR #<n> (<YYYY-MM-DD>)`, appends ` ✅` to the step's heading
(`## Step 3 — Ladder rules and evidence ✅`) so the completion shows in the
rendered preview, the outline, and the table of contents, sets the step's
Summary Table Status cell to `Complete — PR #<n>`, commits that edit on the step
branch, and pushes. The PR therefore carries its own completion mark, and the
roadmap on `main` says a step is complete exactly when that step's PR merges —
never before. This file's phase-level `**Status:**` line (under the title) and
the project roadmap are marked the same way, in the same commit: Step 1's PR
flips both from `Not started` to `In progress` (the project roadmap's
`### Phase 3` line reads `In progress — phase03-roadmap.md`, and its row in the
"Phase Complexity Summary" table reads `In progress`), and the final step's PR
flips both to `Complete — …` (the project roadmap's with its row in the "Phase
Complexity Summary" table and the header `> **Status:**` line) and appends ` ✅`
to this file's `# ` title and to the project roadmap's `### Phase 3` heading, so
the project roadmap shows a finished phase the way this file shows a finished
step. There is no separate "update the roadmaps" chore: a step whose PR merged
without its Status line is a lifecycle violation, and the next step's Stage 1
(and `/roadmap-step`) refuses to start until the previous step reads `Complete`.
If a post-merge check fails — a Deployed & verified bullet, a replay-corpus run
that never went green — the step is NOT complete despite the merged line; say
so, and the `hotfix/` PR that completes it appends its own number to the line.
`grep -n '^\*\*Status:\*\*'` on this file is the phase's progress report, and
the ✅ headings are the same report at a glance.

**Step lifecycle.** Every step in this phase follows the exact same six-stage
lifecycle, in order, with no exceptions. Each stage is a hard checkpoint — if a
stage is skipped, branch protection or the next step's Stage 1 will fail loudly,
and that is the safety net. AI coding agents MUST execute all six stages before
declaring a step complete.

1. **Create the branch.** Before any Read / Edit / Bash, run `git checkout -b
   feature/phase03-step<M>-<slug>` from a clean, up-to-date `main`. The exact
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
   that edit on the step branch (`docs: mark Phase 3 Step <M> complete`), and
   push — the PR now carries its own completion mark, so the roadmap on `main`
   will say the step is complete exactly when the PR merges (Status rule). On
   the phase's first step, the same commit sets this roadmap's phase-level
   `**Status:**` (under its title) and the project roadmap's Phase 3
   `**Status:**` to `In progress`; on the final step, both to `Complete`, with
   ` ✅` appended to this roadmap's `# ` title and to the project roadmap's
   `### Phase 3` heading.

4. **Wait for green checks, then squash-merge.** Every required status check
   must report success: the aggregate `gate` check of `ci.yml` (lint, typecheck,
   the test matrix with the engine coverage floor from Step 1, the package
   smoke, and the security scan) and the aggregate `phase-verify` check
   (`phase-verify (01)`, `phase-verify (02)`, and `phase-verify (03)` from Step
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

## Current State (as of Phase 2)

### Engine and models surface

- `src/weatherbot/engine/` holds one file, `__init__.py`, whose docstring states
  the layer's rule. Three import-linter contracts bind it (the engine imports no
  other layer; layers import downward only, over `weatherbot.models`; only the
  services touch the database libraries), and `tests/test_architecture.py` bans
  thirteen I/O roots (`alembic`, `anthropic`, `apscheduler`, `fastapi`,
  `httpx`, `requests`, `socket`, `sqlalchemy`, `sqlite3`, `starlette`,
  `urllib`, `urllib3`, `uvicorn`) from both the engine and the models. No test
  scans for clock or random use yet. `shapely` is a runtime dependency (the
  models build shapes to record their validity); `pyproj`, Hypothesis, and
  `pytest-cov` are not dependencies at all.
- `weatherbot.models` is the engine's whole input vocabulary, frozen and strict
  (`DomainModel`: `extra="forbid"`, `strict=True`, `hide_input_in_errors=True`).
  `Snapshot` holds one `SourceOutcome` per source it asked for, always the
  roster's (`nhc-current-storms`), and refuses a record whose source did not
  answer; its `storms` are `StormProducts`, each keyed by the roster's
  `StormSummary` (required; it carries the slot, the roster classification, and
  `movement_speed_mph`, a unit only the roster states); `wind_probabilities` is
  one `WindProbabilityProduct` per threshold (34, 50, 64 kt), held by the
  snapshot with no storm field (issue #12); `alerts` maps a location name to its
  merged `NwsAlert` list; and `breakpoints` holds the coastal catalogue.
- `Location` keeps its WGS 84 `point` and optional `polygon` out of `repr`,
  carries `nws: NwsCoverage | None` (forecast zone, county zone, office, time
  zone; `None` outside NWS coverage), `evacuation_order_in_effect: bool`, and
  `breakpoint_span: None`, whose description reads "Phase 3 defines and fills
  it". `Geometry` records its `Crs` (`EPSG:4326`, or `native` with the source
  WKT and datum) and Shapely's verdict, and repairs nothing ("repair is Phase
  3's"). `TrackPoint` carries `tau_h`, `valid_at` (UTC), `position`,
  `max_wind_kt`, `storm_type`, `development`, and `saffir_simpson`;
  `WatchWarningSegment` carries a coded `tcww` (`HWA`, `HWR`, `TWA`, `TWR`, and
  an unknown code kept with `recognized` false) and a line, or a Point with its
  `geometry_note`; `ArrivalTimeProduct` lines carry a resolved `valid_at` or an
  `unresolved_reason`, with an unlabelled outer contour; `NwsAlert` keeps
  `found_by`, `affected_zone_ids`, `geocode_same`, and `geocode_ugc`, the inputs
  issue #10's rule needs. The functions in `weatherbot.models.times` are the
  only parsers of NOAA's time text.

### Sources and snapshot surface

- `SnapshotService.fetch_snapshot(locations)` (`services/snapshots.py`) fetches
  the roster first, then concurrently the summary service's storm, display,
  outlook, and probabilistic-wind layers; peak surge; each storm's arrival-time
  KMZ pair; the TCPs and TWOs; the GIS RSS feeds; the outlook graphics; the
  549-point breakpoint catalogue; and every US location's point, county-zone,
  and forecast-zone alerts, merged by id. A failed source drops all of its
  records, and alerts are kept only when both alert sources answered. Live
  geometry is `EPSG:4326` (`outSR=4326`, five decimals).
- Every parser reads properties only through `sources.fields.Fields` and a
  declared `FIELDS_READ`, which `tests/contract/test_field_coverage.py` keeps
  equal to the register's "Fields v2 uses" lists. The live layers spell their
  fields in lower case (`advisnum`, `tcww`); the archive's shapefiles spell the
  same fields in upper case (`ADVISNUM`, `TCWW`), and no parser reads them yet.
- `sources.nhc_arrival_times.parse_arrival_kmz(body, provenance, storm=None)`
  already parses an archived KMZ, checked against its URL alone: all 244 cached
  arrival KMZ of Dorian, Ian, and Milton parse, and every labelled line
  resolves (checked 2026-10-18). Their contours are mostly open isochrones;
  only the first contour and the outer 5 percent contour close.
- Nothing in the sources or the commands decides what a product means for a
  place: `cli/snapshots.py` prints a non-US location's segments verbatim with
  `PHASE_3_NOTE`.

### Replay corpus surface

- `tests/fixtures/replay/` holds every advisory of Irma (AL112017, 84),
  Dorian (AL052019, 117), Ian (AL092022, 68), and Milton (AL142024, 41) — 310
  in all — as `cone`, `track`, `points`, and `watch-warning` FeatureCollections
  (`.geojson.gz`, 1,201 files, 5.18 MiB; 6.68 MiB with the manifest and
  notice, under the 10 MiB cap `MAX_SUBSET_BYTES` sets in
  `scripts/fetch_replay_corpus.py`). Each collection keeps the archive's
  attributes in upper case and its native `D_Sphere` CRS in `source_crs`;
  Dorian 056–062A keeps 36 one-vertex segments, in 12 advisories, as Points
  with their `geometry_note` (corrected in Step 2: Phase 1's notes said 39 in
  13; 057A has no watch-warning product).
- `corpus-manifest.json` pins the 1,199 originals by URL, size, and SHA-256,
  with each file's advisories, each storm's synoptic times, the advisories that
  lack arrival or radii products, and one `subset` entry per committed file.
  The originals live in the ignored cache (`.cache/replay-corpus/`, or
  `WEATHERBOT_CORPUS_CACHE`, 111.7 MiB): the forecast and radii zips, the 5 km
  wind-speed-probability polygons and half-degree points for 169 synoptic
  times, and the arrival KMZ pairs of every full advisory of Dorian, Ian, and
  Milton. Irma has no arrival product; the archive begins in 2018.
- Constraints a corpus change must keep: Phase 1's static check "tracked replay
  pipeline with all commands" reads the literal `choices=("fetch", "verify",
  "convert", "manifest")`; `tests/replay/test_corpus_subset.py` reads `ADVISNUM`
  on every feature of every subset file; Phase 1's V6.4 reads the latest
  `replay-corpus.yml` run on `main`; `tests/contract/test_fixture_budget.py`
  caps `recorded/` and `replay/` together at 25 MiB (14.85 MiB used) and any
  file at 5 MiB; the personal-data rule R2 exempts both payload trees, while R1
  scans everything.
- `replay-corpus.yml` restores the cache keyed on the manifest's hash, fetches
  on a miss, verifies every original, and runs `pytest -m corpus` (the
  byte-for-byte reconversion) on path-filtered pull requests and pushes, on
  Mondays and Thursdays, and on dispatch. It is not a required check.

### Persistence and configuration surface

- The Alembic head is `0002`: the frozen `0001` baseline (17 tables) and
  `0002_drift_warnings`, applied in package after an online backup, with
  transactional DDL. The `locations` table already has a JSON
  `breakpoint_span` column (null) and a boolean `evacuation_order_in_effect`
  column (default false), so filling the span and setting the toggle need no
  new column; `LocationRepository` has `add`, `list`, `get`, and `remove`, and
  no update.
- `Settings` has two tables, `[logging] level` and `[http] timeout_seconds`;
  `ENVIRONMENT_OVERRIDES` maps each `WEATHERBOT_*` variable to its key, and an
  error names the key, never the value. `SnapshotRepository` saves a snapshot
  with its raw responses and loads it back equal.
- `verify_phase02.py` check 30 (the baseline and revision `0002`) stays live.
  Check 31 forbids any revision that creates an assessment, evidence,
  notification, heartbeat, briefing, or ledger table; the first revision this
  phase adds turns `phase-verify (02)` red unless check 31 reads the revisions
  at `v2.0.0-phase-2` first (PR #27 recorded the obligation).

### CLI surface

- `locations add|list|remove`, `fetch`, `storms`, `alerts`, and `doctor`, each
  with `--json` documents defined in `cli/documents.py` and committed as JSON
  Schemas under `docs/schema/` by `scripts/export_schemas.py` (`--check` in
  tests). The `Runtime` seam (`CliRunner().invoke(app, args,
  obj=Runtime(make_fetcher=..., now=..., terminal=False))`) and
  `tests/cli/cli_support.py` (`recorded_services()`, `run()`, `parse()`,
  `urls()`) run every command against recorded answers. Exit codes are 0, 1
  (partial or failed snapshot), and 2 (usage).
- No command assesses, replays, or sets a toggle. `alerts` for a location
  outside NWS coverage lists every segment with `PHASE_3_NOTE`, and
  `tests/cli/test_commands.py` asserts that note.

### Security & sensitive-data surface

- Data in play: for the first time the operator's coordinates feed computation.
  The derived values — the distance and bearing from a storm's public center,
  and the closest approach — locate the operator's home as precisely as its
  coordinates, so they are handled like coordinates: stored in the local
  database, printed in the terminal, and never written to a log line above
  DEBUG, a fixture, a golden file, an exception message, or a conversation.
  Phase 3 adds no secret.
- Controls: the four-check gate in pre-commit and in CI's `security` job
  (gitleaks; bandit over `src` and `scripts` at every severity; pip-audit over
  `uv.lock` through `scripts/audit_deps.py`; `scripts/check_personal_data.py`
  rules R1 to R4); the two public landmarks in `scripts/public_landmarks.toml`
  (Miami-Dade County Hall and Parliament Square, Nassau);
  `synthetic_coordinates()` for a non-landmark test point; `configure_logging`
  and `RedactingFilter`; `repr=False` on location coordinates and
  `hide_input_in_errors` on every model.
- Patterns every step mirrors: tests and goldens use the landmarks, or points
  derived at run time from public products, never a coordinate literal; a
  message names a rule or a key, never a value; a replay file is parsed only
  after its SHA-256 matches the manifest; a path read stays inside the corpus
  directory it was given; KMZ goes through the hardened arrival parser and JSON
  through `json`, never `pickle`. The new dependencies — `pyproj` at run time,
  Hypothesis and `pytest-cov` in the dev group — pass `pip-audit`.

### Operations & observability surface

- Phase 3 adds no scheduled or unattended surface. Its local runtime surfaces
  are `status`, which writes assessments from Step 6, and `replay`, which only
  reads; `doctor` reports the database head (`0003` after Step 6) and is their
  health signal, with its exit status as the alarm, as in Phase 2. The GitHub
  surfaces are `ci.yml` and `phase-verify.yml` (both required), the
  twice-weekly `replay-corpus.yml`, whose failure reaches the operator through
  GitHub's email, Dependabot, and the dispatch-only `live-smoke.yml`. The
  heartbeat and the staleness alarm are Phase 4's.

### Documentation surface

- `README.md`'s Status section says matching products to places is Phase 3's
  work, and its Commands section lists Phase 2's commands. `CONTRIBUTING.md`
  documents the checks, the live suite, the command tests and schemas, local
  data, and the security gate; `AGENTS.md` describes the engine layer;
  `docs/DATA_SOURCES.md`'s "GIS archive" section describes the products and the
  corpus recorded 2026-10-15 but lists no field of the archive collections;
  `CHANGELOG.md` has an `[Unreleased]` section. No `docs/ALERT-LADDER.md`
  exists.

### Verification surfaces

- `scripts/verify_phase02.py` is the structural template: 47 numbered static
  checks, mostly AST reads; the modes `--fast` (standard library only),
  `--py`, `--live`, `--security`, `--all`, and `--post`; and 26 V rows built
  from one offline pytest run and one live run, each with `--junitxml`, where
  every selection must match a test, a failure fails, and a skip is never a
  pass. `scripts/verify_phase01.py`'s `tagged()` and `tagged_tree()` helpers,
  and the throwaway-repository tests in `tests/test_phase01_verification.py`,
  are the precedent for reading a check's facts from a tag.
- `.github/workflows/phase-verify.yml` runs matrix entries `"01"` and `"02"`
  (`--fast` and `--security` each, with full history and a checksum-verified
  gitleaks), and its aggregate `phase-verify` check is required on `main` beside
  `gate`. Step 7 adds `"03"`; entries `"01"` and `"02"` stay.

### Carry-over from Phase 2

Every item Phase 2 handed to this phase, and where it lands:

| Item | Source | Destination in Phase 3 |
| ---- | ------ | ---------------------- |
| `verify_phase02.py` check 31 becomes historical against `v2.0.0-phase-2`; the other Phase 2 checks stay live; entries `"01"` and `"02"` stay | Project roadmap, Phase 3 (PR #27); `docs/phase02-qa-findings.md`, Step 7 | Step 1 |
| County-zone alerts outside the location's forecast zone | Issue #10; QA ledger, pre-ship items | Step 3 (the rule and its golden scenario; closes #10) |
| A location's breakpoint span (`breakpoint_span`) | QA ledger, pre-ship items; `Location` | Step 3 (the type and the engine function), Step 6 (filled, stored, shown) |
| The evacuation-order setter | QA ledger, pre-ship items | Step 6 (`locations evacuation`); Step 3 reads the toggle |
| Geodesy over the native sphere; repair is Phase 3's | QA ledger, pre-ship items; project roadmap 3.3; `models/geometry.py` | Step 1 |
| Wind probabilities at the location level, never per storm | QA ledger, pre-ship items; issue #12 | Step 3 (the location's bands), Step 4 (no field on `StormThreat`) |
| Arrival instants only where a line resolved | QA ledger, pre-ship items; issue #11 | Step 4 |
| `alerts` prints `PHASE_3_NOTE` for a non-US location | `cli/snapshots.py` | Step 6 |
| Atlantic and Central Pacific per-basin rows of the register are open | QA ledger, pre-ship items | Any step that runs while a storm is active in an open basin re-checks that row live under Source drift |
| NWS may require an API key | QA ledger, pre-ship items | Any step: open an issue before adding a key |
| Dependabot PRs #8 and #9 | QA ledger | Independent maintenance, outside every step |

---

## Execution Order

```
Step 1  (geodesy + geometry)              engine.geodesy + engine.geometry
                                          + coverage floor + check 31
                                          historical
                                          → implement
  ↓
Step 2  (replay snapshots)                replay Snapshot + nhc_gis_archive
                                          + services.replay + landmark
                                          wind-probability windows
                                          → implement
  ↓
Step 3  (ladder rules + evidence)         eleven rules + assess() + #10
                                          + segment coverage + span
                                          + [engine] thresholds
                                          → implement
  ↓
Step 4  (storm threats + changes)         StormThreat + arrival reading
                                          + diff() change events
                                          → implement
  ↓
Step 5  (calibration + golden replays)    calibrated defaults + 8 goldens
                                          + mutation suite
                                          + docs/ALERT-LADDER.md
                                          → implement
  ↓
Step 6  (assessments + commands)          revision 0003 + status + replay
                                          + locations evacuation + span
                                          → implement
  ↓
Step 7  (QA + verify_phase03.py)          scripts/verify_phase03.py
                                          + docs/phase03-qa-findings.md
                                          + phase-verify.yml entry "03"
                                          → create

--- post-implementation ---

V1  Geodesy follows each CRS; antimeridian, repair, and
    nearest-point helpers hold; coverage >= 90%; check 31
    is historical.
V2  Replay advisories load as replay snapshots from verified
    files; the landmark windows rebuild byte for byte.
V3  The eleven rules decide in order with evidence; issue #10
    and the segment rule hold on recorded scenarios.
V4  Every storm gets a threat record; arrival reading and
    diff() hold on recorded and cached products.
V5  Eight approved goldens equal the engine; every mutation
    breaks one; ALERT-LADDER.md equals the code.
V6  status stores assessments at revision 0003; replay meets
    its budget; the commands run live for both landmarks.
V7  verify_phase03.py --fast and --security exit 0 in
    phase-verify (03); the phase is closed.
```

Steps are sequential by dependency. Step 1's geodesy and geometry are what every
rule measures with, and its historical check 31 must land before Step 6's
revision `0003`, or `phase-verify (02)` turns red; Step 2's replay snapshots
settle the model changes the engine reads from its first rule on, so Step 3 is
never written against live-only shapes; Step 3's rules and `Assessment` are what
Step 4's threats extend and its `diff` compares; Step 5 calibrates and freezes
what Steps 3 and 4 built, so it follows them; Step 6 stores and prints a frozen
engine; Step 7 verifies every prior step. Steps 1 and 2 touch disjoint modules,
but both edit `CHANGELOG.md` and `CONTRIBUTING.md`, and Step 2's model changes
are the input Step 3's first rule reads, so this phase draws no steps in
parallel, and the Worktree rule permits no concurrent steps.

---

## Step 1 — Geodesy and geometry ✅

**Status:** Complete — PR #29 (2026-10-19)

> **Goal:** Land the engine's measuring tools and the gates that keep the engine
> honest. `src/weatherbot/engine/geodesy.py` gives every geometry the figure its
> CRS implies — the WGS 84 ellipsoid for `EPSG:4326`, and for a native
> geographic CRS the spheroid its WKT names, which for the replay corpus is the
> 6,371,200 m sphere — and measures geodesic distance and initial bearing
> through `pyproj.Geod`; `src/weatherbot/engine/geometry.py` places a location's
> point in a geometry's coordinates, tests containment and intersection without
> breaking at the antimeridian, repairs an invalid areal geometry with a
> recorded reason, finds a line's nearest point and whether that point is the
> line's end, and finds a forecast track's closest approach to a location in
> time and distance; Hypothesis property tests, a branch-coverage floor of 90
> percent over `weatherbot.engine` in `ci.yml`, and an architecture scan that
> forbids clock, random, filesystem, environment, and logging use in the engine
> land with them; and check 31 of `scripts/verify_phase02.py` reads the
> migration revisions at `v2.0.0-phase-2`, so Step 6's revision `0003` leaves
> `phase-verify (02)` green. This step lands the tools; Step 3's rules and Step
> 4's threats measure with them.

**Branch:** `feature/phase03-step1-geodesy`

**Deploys:** GitHub Actions → from the merge on, `ci.yml`'s `test` job enforces
the engine coverage floor and `phase-verify (02)` runs check 31 as a historical
check; the first run of each on `main` must be green.

| Setting      | Cost                                    | Balanced                                 | Quality                                  |
| ------------ | --------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Model        | GPT-6.1 Sol                             | Opus 5.5                                 | Opus 5.5                                 |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh |
| Platform     | Codex                                   | Claude Code                              | Claude Code                              |
| Effort       | Intelligence High                       | Effort High                              | Effort XHigh                             |
| Thinking     | —                                       | On                                       | On                                       |
| Conversation | **New**                                 | **New**                                  | **New**                                  |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

> Ran 2026-10-19: Balanced — Opus 5.5 · Effort High. The **Runs:** column; the Claude weekly pool's `tight` row had passed its reset (Tue 2026-10-13 20:00 EDT), so it read `headroom`.

**Model rationale:** Step 1 is coding with knowledge as its secondary category:
geodesy, coordinate reference systems, and computational geometry, where a wrong
figure or a longitude that wraps silently corrupts every later level. Its
overall complexity is High — many interacting numeric concerns (two figures,
antimeridian unwrapping, repair, end detection, time interpolation) and three
gates across `ci.yml`, the architecture test, and a Phase 2 verifier check — and
it is not novel: every algorithm is established, and this roadmap fixes the
decisions. The columns differ in depth: Balanced runs Opus 5.5, S-tier in coding
and knowledge, on Claude Code at Effort High, one rung above its documented
`medium` default, with thinking on; Quality runs the same model at Extra High
for the closest audit of numeric edge cases; Cost moves the step to GPT-6.1 Sol
on Codex at Intelligence High, S-tier in agentic work and A-tier in coding. The
claude.ai Max subscription funds Claude Code and ChatGPT Pro 5x funds Codex, so
each column costs nothing at the margin while its pool has headroom, and each
backup comes from the other maker. The conversation is new per phase-boundary
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
       feature/phase03-step1-geodesy`
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
       Phase 3 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 3`
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

    THIS STEP adds `pyproj` to the runtime set and Hypothesis
    and `pytest-cov` to the dev group, so
    `scripts/audit_deps.py` must pass on the new lock. The
    engine uses `pyproj.Geod` alone: no `Transformer`, no PROJ
    database lookup, and no network (PROJ's network grids stay
    off); the architecture scan proves it, and pyproj's
    `Transformer` appears only in the one test that proves the
    identity placement. Tests use the two public landmarks and
    points generated at run time (Hypothesis strategies,
    `synthetic_coordinates()`), never a coordinate literal,
    because R2 scans tests; no property test reads a stored
    location. A failed check or a refused WKT names the rule,
    never a coordinate. The coverage data file goes to a
    temporary directory, never the checkout. The verifier
    change reads Git history only and prints no file content.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 3 (Threat engine).
    Step 1: Geodesy and geometry.

    Current state (as of Phase 2; no Phase 3 step has run):

    - `main` requires `gate` (`ci.yml`) and `phase-verify`
      (entries `"01"` and `"02"`). `src/weatherbot/engine/`
      holds only `__init__.py`. `shapely` is a runtime
      dependency; `pyproj`, Hypothesis, and `pytest-cov` are
      not dependencies.
    - `weatherbot.models.Geometry` carries a `Crs`
      (`EPSG:4326`, or `native` with the source WKT and datum)
      and Shapely's validity verdict, and repairs nothing.
      Live geometry is `EPSG:4326`; every replay collection's
      `source_crs` holds the archive's
      `GEOGCS["GCS_Sphere",DATUM["D_Sphere",
      SPHEROID["Sphere",6371200.0,0.0]],...]`. A
      `Location.point` is a WGS 84 `LatLon`.
    - PROJ evidence, 2026-10-18, pyproj 3.8.0 with PROJ 9.8.1:
      `Transformer.from_crs("EPSG:4326", <corpus WKT>,
      always_xy=True)` describes itself as "Ballpark geographic
      offset from WGS 84 to Unknown datum based upon the
      Authalic Sphere", reports accuracy -1, and returns both
      landmarks unchanged; `CRS.from_wkt(<corpus WKT>)
      .get_geod()` has a = b = 6,371,200 m. The landmarks are
      297.53 km apart on WGS 84 and 297.14 km apart on the
      sphere.
    - Replay anchors on the archive sphere (measured
      2026-10-18; the Miami-Dade and Nassau landmarks from
      `scripts/public_landmarks.toml`): the Miami-Dade landmark
      lies inside every Irma cone from advisory 022 to 039A (34
      in a row; 021A and 040 miss it), and the Nassau landmark
      inside 20 Irma cones, the first at 019 and the last at
      031A, not in a row;
      Dorian advisory 030's Hurricane Warning segment is a
      two-vertex line 3.8 km from the Nassau landmark with its
      nearest point inside the line; Dorian's Tropical Storm
      Watch at advisories 032–040A ends 22.6 km from the
      Miami-Dade landmark, its nearest point the line's end;
      Irma advisory 036's forecast points, joined by geodesics,
      pass 38.9 km from the Miami-Dade landmark between the
      48-hour and 72-hour points.
    - The Central Pacific: NHC splits a track at 180 degrees
      into a MultiLineString (`ForecastTrack` allows one). No
      corpus storm crosses the antimeridian, so that handling
      is proven on synthetic geometry.
    - Forecast points: `TrackPoint.valid_at` is the UTC instant
      of each point. Tau 0 is the advisory's own time, three
      hours after the synoptic time the other taus count from,
      so interpolation runs on `valid_at`, never on `tau_h`.
    - Tests: basenames must be unique under pytest's prepend
      import mode, and `tests/models/test_geometry.py` exists,
      so the engine's modules are `tests/engine/test_geodesy.py`,
      `test_engine_geometry.py`, `test_tracks.py`, and
      `test_engine_properties.py`. `filterwarnings = ["error"]`
      turns any warning into a failure; every test runs in its
      own temporary working directory.
    - Check 31 (`no_later_tables`) reads the revisions in the
      working tree. `scripts/verify_phase01.py`'s `tagged()` and
      `tagged_tree()` (`git show` and `git ls-tree` at a tag)
      and `tests/test_phase01_verification.py`'s throwaway
      repository are the precedent. CI's `test` job and
      `phase-verify.yml` check out with `fetch-depth: 0`, so the
      tags are present.

    Files to read (every file before drafting):
    - docs/roadmap/phase03-roadmap.md (Overview and its design
      rationale, Current State, this step, and the goals of
      Steps 3 and 4, which call these functions).
    - docs/roadmap/ROADMAP.md (Phase 3, sections 3.1 and 3.3).
    - src/weatherbot/engine/__init__.py,
      src/weatherbot/models/geometry.py,
      src/weatherbot/models/storms.py (TrackPoint,
      ForecastTrack, ConeGeometry, WatchWarningSegment),
      src/weatherbot/models/location.py.
    - tests/test_architecture.py, tests/conftest.py,
      pyproject.toml, .github/workflows/ci.yml, .gitignore.
    - scripts/verify_phase02.py (check 31 and the revision
      reader), scripts/verify_phase01.py (`tagged`,
      `tagged_tree`), tests/test_phase02_verification.py,
      tests/test_phase01_verification.py.
    - tests/fixtures/replay/NOTICE.md and the `source_crs` of
      one replay collection.
    - AGENTS.md, CONTRIBUTING.md ("The checks"), CHANGELOG.md.
  </context>

  <goal>
    Ship `weatherbot.engine.geodesy` and
    `weatherbot.engine.geometry` with the functions below,
    tested by example on recorded and replay geometry and by
    property on generated geometry; enforce at least 90
    percent branch coverage of `weatherbot.engine` in CI; scan
    the engine for clock, random, filesystem, environment, and
    logging use; and make check 31 read `v2.0.0-phase-2`, so
    both phase-verify entries stay green when Step 6 adds
    revision `0003`.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Dependencies. `uv add pyproj` (runtime) and `uv add --dev
      hypothesis pytest-cov`; run `uv lock`;
      `scripts/audit_deps.py` must pass. Add nothing else.
    </requirement>

    <requirement>
      `src/weatherbot/engine/geodesy.py`:
      - `Figure`, frozen: the figure's name, semi-major axis in
        metres, inverse flattening (0 for a sphere), and its
        `pyproj.Geod`. `figure_of(crs: Crs) -> Figure`:
        `EPSG:4326` is WGS 84; a `native` CRS is read from its
        WKT by a strict parser of the top-level `GEOGCS` or
        `GEOGCRS` and its one `SPHEROID` or `ELLIPSOID` (name,
        semi-major axis, inverse flattening). The parser
        refuses a projected CRS (`PROJCS`, `PROJCRS`), a
        missing or repeated spheroid, an angular unit other
        than the degree, or a prime meridian other than
        Greenwich, with a `ValueError` that names the rule.
        Figures are cached by CRS.
      - `distance_km(a, b, figure) -> float` and
        `initial_bearing_deg(a, b, figure) -> float` (from `a`
        toward `b`, 0 to under 360), through `Geod.inv`; a
        position is `(longitude, latitude)` in the figure's
        coordinates.
      - Use `pyproj.Geod` only. No `Transformer`, CRS database,
        or network in any engine module.
    </requirement>

    <requirement>
      `src/weatherbot/engine/geometry.py`:
      - `place(point: LatLon, crs: Crs) -> tuple[float,
        float]`: the location's position in a geometry's
        coordinates. For both geographic CRSs it is the same
        longitude and latitude, unchanged; a projected CRS is
        refused. Its docstring records the PROJ evidence above,
        and every caller's evidence names the geometry's CRS.
      - `covers(geometry, position) -> bool` (a position on the
        boundary counts as inside, and the docstring says so)
        and `intersects(a, b) -> bool`, antimeridian-safe: a
        geographic ring with consecutive vertices more than 180
        degrees of longitude apart is unwrapped into one
        continuous longitude range before testing, and the
        position is tested at its longitude and at plus and
        minus 360 degrees; parts already split at 180 degrees
        test as they are.
      - `repair(geometry) -> Repaired`: a valid geometry comes
        back unchanged with no note; an invalid areal geometry
        goes through `shapely.make_valid`, keeps its polygonal
        parts, and carries a note naming the original
        `validity_reason`; a repair that leaves no area returns
        no shape with its note, and the caller treats the
        product as unusable. Repair is idempotent and never
        changes a valid geometry.
      - `nearest_on_line(position, line, figure) -> Nearest`:
        the geodesic distance in kilometres from the position
        to the nearest point of a LineString, MultiLineString,
        or Point segment; that point's fraction along its part;
        and `at_end`, true only when the nearest point is the
        first or last vertex of an open part (first vertex
        different from the last). Each edge is a geodesic; the
        reported distance is within 50 m of a brute-force dense
        sampling of the edge.
      - `closest_approach(points, position, figure) ->
        Approach`: the forecast track's closest approach. The
        points are taken in `valid_at` order; between
        consecutive points the center moves along the geodesic
        at a constant rate in time. `Approach` holds the
        minimum geodesic distance in kilometres, its
        interpolated instant (UTC), and the hours from the
        first point to it; a tie goes to the earliest instant;
        one point is its own approach; no points is an error.
      - Nothing logs, reads the clock, or opens a file.
    </requirement>

    <requirement>
      Tests, every one offline:
      - `tests/engine/test_geodesy.py`: both figures; every
        distinct WKT in `tests/fixtures/replay/corpus-manifest.json`
        parses to the 6,371,200 m sphere and equals
        `pyproj.CRS.from_wkt(...).get_geod()`; refused WKTs
        (projected, no spheroid, two spheroids, gradians, a
        Paris meridian); the landmarks are 297.53 km apart on
        WGS 84 and 297.14 km apart on the sphere, within
        0.01 km; bearings in range, with the back azimuth
        reciprocal on the sphere; the PROJ ballpark test above
        for both landmarks.
      - `tests/engine/test_engine_geometry.py`: on the replay
        corpus, through the same parsing the models do
        (`Geometry.from_geojson` with `Crs.native(source_crs)`):
        the Miami-Dade landmark inside every Irma cone from 022
        to 039A and outside 021A and 040; the Nassau landmark
        inside exactly 20 Irma cones, the first 019 and the last
        031A; Dorian 030's Hurricane Warning segment at
        3.8 km from the Nassau landmark (within 0.1 km), not at
        its end; Dorian 032's Tropical Storm Watch at 22.6 km
        from the Miami-Dade landmark, at its end. On synthetic
        geometry: a Central Pacific cone crossing 180 degrees
        covers positions just east and just west of the
        antimeridian and not the longitude opposite them; an
        invalid bow-tie cone is repaired with its reason; a
        Point segment's distance.
      - `tests/engine/test_tracks.py`: Irma 036's closest
        approach to the Miami-Dade landmark is 38.9 km (within
        0.5 km), between its 48-hour and 72-hour points;
        synthetic tracks: a straight pass, a stationary storm, a
        track moving away (approach at the first point), a
        track split at 180 degrees measured continuously.
      - `tests/engine/test_engine_properties.py` (Hypothesis,
        under a profile registered for the suite with
        `derandomize=True`, `database=None`, and
        `deadline=None`, so runs are reproducible and write
        nothing): distance symmetric and zero only for equal
        positions; the triangle inequality within 1 m;
        `covers` unchanged when a ring crossing 180 degrees is
        shifted by 360 degrees; `repair` idempotent and the
        identity on valid input; `nearest_on_line` no greater
        than the distance to any vertex; `closest_approach` no
        greater than the distance at any point.
    </requirement>

    <requirement>
      Determinism scan. Extend `tests/test_architecture.py`
      with an engine-only scan (the models' I/O ban is
      unchanged): no import of `os`, `pathlib`, `io`, `time`,
      `random`, `secrets`, `tempfile`, `shutil`, `subprocess`,
      or `logging`; no call of `datetime.now`, `utcnow`,
      `today`, `uuid1`, `uuid4`, `open`, `input`, or `print`;
      and `pyproj` imported only as `from pyproj import Geod`.
      Probe it: an engine module that imports `time`, and one
      that calls `datetime.now()`, each turn the scan red;
      revert both.
    </requirement>

    <requirement>
      Coverage floor. `ci.yml`'s `test` job runs `uv run pytest
      --cov=weatherbot.engine --cov-branch
      --cov-report=term-missing:skip-covered
      --cov-fail-under=90`, with `COVERAGE_FILE` set to a path
      under the runner's `runner.temp` directory, on both
      runners. `.gitignore`
      gains `.coverage` and `.coverage.*` for local runs, and
      `CONTRIBUTING.md` gives the local command with
      `COVERAGE_FILE` in a temporary directory. The floor holds
      from this step on, for every engine module a later step
      adds.
    </requirement>

    <requirement>
      Check 31 becomes historical. In
      `scripts/verify_phase02.py`, add `PHASE_2_TAG =
      "v2.0.0-phase-2"`; `no_later_tables` reads the revisions
      at the tag (`git ls-tree` of the versions directory and
      `git show` of each file, with the same AST reading) and
      passes only when none of them creates a table matching
      `LATER_TABLES` and each is byte-identical in the working
      tree (Phase 2's revisions are frozen). Check 30 and every
      other check stay live; the count stays 47, and the
      check's label says it reads the tag. A missing tag or
      path fails the check. Add throwaway-repository tests to
      `tests/test_phase02_verification.py`, modelled on
      Phase 1's: the check passes on a grown tree where a new
      revision creates `assessments` after the tag; fails when
      a tagged revision creates a later table; fails when a
      tagged revision changed after the tag; fails without the
      tag.
    </requirement>

    <requirement>
      Documents. `AGENTS.md`: the engine's geodesy follows
      each geometry's CRS, uses `pyproj.Geod` only, and reads
      no clock. `CONTRIBUTING.md`: the coverage command and the
      Hypothesis profile. `CHANGELOG.md`: a "Phase 3 — Threat
      engine" group under `[Unreleased]` with this step's
      entries.
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

- `weatherbot.engine.geodesy` and `weatherbot.engine.geometry` define `Figure`,
  `figure_of`, `distance_km`, `initial_bearing_deg`, `place`, `covers`,
  `intersects`, `repair`, `nearest_on_line`, and `closest_approach`; `pyproj` is
  a runtime dependency, and Hypothesis and `pytest-cov` are dev dependencies.
- The landmarks are 297.53 km apart on WGS 84 and 297.14 km apart on the archive
  sphere (within 0.01 km); every distinct corpus WKT parses to the sphere and
  agrees with pyproj's own reading; a projected or ambiguous WKT is refused by
  name.
- The PROJ test shows the ballpark transformation returning both landmarks
  unchanged, and `place` returns them unchanged.
- The replay anchors hold: every Irma cone from 022 to 039A covers the
  Miami-Dade landmark and 021A and 040 do not; exactly 20 Irma cones cover the
  Nassau landmark; Dorian 030's Hurricane Warning segment is
  3.8 km from the Nassau landmark, not at its end; Dorian 032's Tropical Storm
  Watch is 22.6 km from the Miami-Dade landmark, at its end; Irma 036's closest
  approach to the Miami-Dade landmark is 38.9 km.
- The antimeridian, repair, track, and Hypothesis property tests pass under the
  deterministic profile.
- `ci.yml`'s `test` job fails below 90 percent branch coverage of
  `weatherbot.engine`, and the suite meets the floor.
- The architecture scan forbids clock, random, filesystem, environment, and
  logging use in the engine and allows `pyproj` only as `Geod`; both probes
  turned it red and were reverted.
- Check 31 reads `v2.0.0-phase-2`, keeps Phase 2's revisions frozen, and its
  throwaway-repository tests pass; `verify_phase02.py --fast` still reports 47
  checks, all PASS.
- **Deployed & verified:** the first `ci.yml` run and the first
  `phase-verify.yml` run on `main` at the merge commit are green, with the
  coverage floor met on both runners and `phase-verify (02)` green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, SAST
  clean, `pip-audit` clean with `pyproj`, Hypothesis, and `pytest-cov` added —
  and no test, docstring, or message holds a coordinate other than a landmark.

---

## Step 2 — Replay snapshots

**Status:** Not started

> **Goal:** Make a replayed advisory an honest `Snapshot`, and give every pull
> request every product the ladder reads. `weatherbot.models` gains a snapshot
> origin, `live` or `replay`: a replay snapshot's outcomes name the archive
> sources it read instead of the roster, each of its storms carries an
> `ArchiveStorm` record (the ATCF id, and the name and type as the archive
> spells them) in place of the roster's `StormSummary`, and a
> wind-speed-probability product may be an extract that records the area it
> covers; `src/weatherbot/sources/nhc_gis_archive.py` parses the converted
> archive collections — cone, track, points, watch-warning, and wind-speed
> probabilities — through a declared field list that the register now lists;
> `src/weatherbot/services/replay.py` opens a corpus directory, checks every
> file against the manifest's SHA-256 before parsing it, and yields one replay
> snapshot per advisory in order, with the probabilities of the advisory's
> synoptic time and, where the corpus holds them, the arrival products of the
> latest full advisory; `scripts/fetch_replay_corpus.py convert` adds each
> storm's 5 km wind-speed probabilities, clipped to a window one degree on each
> side of each public landmark, to the committed subset (about 0.6 MiB, under
> the 10 MiB cap), and with `--full --out DIR` writes a complete conversion
> outside the checkout for the operator's own locations; and `replay-corpus.yml`
> rebuilds the extended subset byte for byte. This step lands the replay input;
> Step 3's rules read it, Step 5's goldens replay it, and Step 6's `replay`
> command prints it.

**Branch:** `feature/phase03-step2-replay-snapshots`

**Deploys:** GitHub Actions → `replay-corpus.yml` reconverts the extended subset
from the pinned originals on the merge push; its first run on `main` must be
green, because Phase 1's V6.4 reads it.

| Setting      | Cost                                    | Balanced                                 | Quality                                  |
| ------------ | --------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Model        | GPT-6.1 Sol                             | Opus 5.5                                 | Opus 5.5                                 |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh |
| Platform     | Codex                                   | Claude Code                              | Claude Code                              |
| Effort       | Intelligence High                       | Effort High                              | Effort XHigh                             |
| Thinking     | —                                       | On                                       | On                                       |
| Conversation | **New**                                 | **New**                                  | **New**                                  |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

**Model rationale:** Step 2 is coding with knowledge as its secondary category:
a model change that every layer reads, a parser over the archive's own field
vocabulary, a verifying reader, and a deliberate refresh of a pinned corpus
under three budgets and Phase 1's guards. Its overall complexity is High by
scope — models, sources, services, a development script, a manifest, a
workflow, and the Phase 1 checks that must stay green — and it is not novel:
this roadmap fixes the model shape, the windows, and the corpus discipline. The
columns differ in depth: Balanced runs Opus 5.5, S-tier in coding and
knowledge, on Claude Code at Effort High, one rung above its documented `medium`
default, with thinking on; Quality runs the same model at Extra High for the
closest audit of the manifest and the model change; Cost moves the step to
GPT-6.1 Sol on Codex at Intelligence High, S-tier in agentic work and A-tier in
coding. The claude.ai Max subscription funds Claude Code and ChatGPT Pro 5x
funds Codex, so each column costs nothing at the margin while its pool has
headroom, and each backup comes from the other maker. The conversation is new
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
       feature/phase03-step2-replay-snapshots`
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
       Phase 3 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 3`
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

    THIS STEP reads an untrusted public archive. A corpus file
    is parsed only after its SHA-256 matches the manifest; JSON
    is read with `json` under a size bound, never `pickle`; KMZ
    goes through `parse_arrival_kmz`'s hardened reader; and
    every path stays inside the corpus directory it was given
    (no `..`, no absolute member, no link followed out). `convert
    --full` refuses an output directory inside the checkout, so
    its 66 MiB of output can never reach a commit. The windows
    come only from `scripts/public_landmarks.toml`, the
    personal-data check R1 must stay clean over every new file,
    and no file, log line, or message names the operator's
    location. The manifest refresh follows Phase 1's rule: the
    checksums of the originals never change; only `subset`,
    `subset_rule`, and the recording date are refreshed,
    deliberately, with the diff reviewed in the PR.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 3 (Threat engine).
    Step 2: Replay snapshots.

    Current state (as of Phase 3 Step 1):

    - `Snapshot` requires the roster's outcome and refuses a
      record whose source did not answer; `StormProducts`
      requires the roster's `StormSummary`, which holds a slot,
      a roster classification, and `movement_speed_mph` — values
      the archive never states (it has no slot, spells types as
      `HU`, `MH`, `TS`, `TD`, and gives speeds in knots). Code
      reads `storm.summary` at 23 sites: `cli/snapshots.py`
      (13), `services/snapshots.py` (6), `models/snapshot.py`
      (2), and the persistence repositories (2). `SourceId`
      already includes `nhc-gis-archive` and `nhc-arrival-times`.
    - The converted collections (`tests/fixtures/replay/<storm>/
      <advisory>/{cone,track,points,watch-warning}.geojson.gz`)
      carry the members `type`, `features`, `source_crs`,
      `storm`, `advisory`, and `source`, and upper-case
      attributes: cone and track `ADVDATE`, `ADVISNUM`, `BASIN`,
      `FCSTPRD`, `STORMNAME`, `STORMNUM`, `STORMTYPE`; points
      those plus `TAU`, `VALIDTIME`, `FLDATELBL`, `DATELBL`,
      `TIMEZONE`, `MAXWIND`, `GUST`, `MSLP`, `TCDIR`, `TCSPD`,
      `TCDVLP`, `SSNUM`, `DVLBL`, `STORMSRC`, `LAT`, `LON`;
      watch-warning those of the cone plus `TCWW`. The archive's
      5 km wind-speed-probability shapefiles
      (`<YYYYMMDDHH>_wsp{34,50,64}knt120hr_5km`) carry one
      field, `PERCENTAGE`, with the same eleven band labels the
      live layers use.
    - `corpus-manifest.json`: `files` (each original's URL,
      SHA-256, bytes, `prj`, product, storm, advisories, and
      synoptic time — the WSP-to-advisory association taken
      from the radii packages' `SYNOPTIME`), `storms` (each
      storm's advisories, `missing_arrival`, `missing_fcst`,
      `synoptic_times`), `subset` (each committed file's name,
      bytes, SHA-256, source archive, and member), `subset_rule`,
      `float_decimals` (7), `coordinate_policy`, `user_agent`,
      and `schema`. It records no recording date; the originals
      were fetched on 2026-10-15 (PR #15).
    - Sizes measured 2026-10-18: the four storms' 5 km
      probabilities would take 52.9 MiB as GeoJSON in full, and
      12.1 MiB as only the unmodified bands containing a
      landmark; clipped to a box one degree on each side of each
      public landmark, about 0.6 MiB. The subset holds 6.68 MiB
      of its 10 MiB cap; `recorded/` and `replay/` together hold
      14.85 MiB of their 25 MiB budget. The arrival KMZ (8.3 MiB)
      and the wind radii (22 MiB) stay in the cache.
    - Phase 1 guards: the literal `choices=("fetch", "verify",
      "convert", "manifest")` must stay in the script (Phase 1's
      check); `tests/replay/test_corpus_subset.py` reads
      `ADVISNUM` on every feature of every subset file; Phase 1's
      V6.4 reads the latest `replay-corpus.yml` run on `main`;
      `verify_phase01.py --corpus` runs `fetch`, `verify`, and
      `pytest -m corpus`.
    - `parse_arrival_kmz(body, provenance, storm=None)` parses an
      archived KMZ checked against its URL; every cached KMZ
      parses and resolves (2026-10-18).
    - Carry-over from Step 1: `tests/engine/engine_support.py`
      builds `TrackPoint`s from a replay `points` collection
      (`replay_track`), with an `nhc-gis-archive` provenance
      that cites the original zip's URL and SHA-256, and reads
      collections through `Geometry.from_geojson` with
      `Crs.native(source_crs)` (`features`). The archive parser
      this step writes supersedes those helpers: have them call
      it, so the engine tests read replay data exactly as
      snapshots do. `weatherbot.engine.geodesy.figure_of` refuses
      any WKT that is not one geographic spheroid in degrees from
      Greenwich, by rule name. On Windows, Python's
      `Path.write_text` writes CRLF: an edit script writes bytes,
      and `git ls-files --eol` (not `grep $'\r'` in Git Bash)
      reads a file's line endings.

    Files to read (every file before drafting):
    - docs/roadmap/phase03-roadmap.md (Overview and its design
      rationale, Current State, this step, and the goals of
      Steps 3, 5, and 6).
    - src/weatherbot/models/snapshot.py, storms.py, outlook.py,
      provenance.py, geometry.py, and __init__.py.
    - src/weatherbot/sources/fields.py, nhc_map.py (the live
      parsers and their FIELDS_READ), nhc_arrival_times.py.
    - src/weatherbot/services/snapshots.py,
      services/persistence/repositories.py,
      src/weatherbot/cli/snapshots.py and documents.py.
    - scripts/fetch_replay_corpus.py, tests/replay/,
      tests/scripts/test_fetch_replay_corpus.py,
      tests/fixtures/replay/NOTICE.md, the manifest's header
      and one entry of each list.
    - tests/contract/test_field_coverage.py,
      tests/contract/fixture_support.py (the register readers),
      tests/contract/test_fixture_budget.py.
    - docs/DATA_SOURCES.md ("GIS archive" and "Replay corpus
      recorded 2026-10-15"), .github/workflows/replay-corpus.yml,
      scripts/verify_phase01.py (its corpus checks).
  </context>

  <goal>
    Ship the replay origin in the models; a parser for every
    converted archive collection with a register-backed field
    contract; a verifying corpus reader that yields one replay
    snapshot per advisory; the landmark wind-probability windows
    in the committed subset; `convert --full` for complete local
    conversions; and a green `replay-corpus.yml`, with every
    Phase 1 and Phase 2 guard still green.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Models. Under these constraints the step chooses the
      field shapes:
      - `Snapshot.origin: Literal["live", "replay"]`, default
        `live`. A live snapshot keeps every Phase 2 rule. A
        replay snapshot requires an `nhc-gis-archive` outcome,
        carries no roster outcome, and holds only records whose
        provenance source is the archive or
        `nhc-arrival-times`.
      - A new `ArchiveStorm` (the ATCF id, `name` and
        `storm_type` as the archive spells them, and the
        provenance of the collection they came from).
        `StormProducts` holds exactly one of `summary`
        (`StormSummary`) or `archived` (`ArchiveStorm`), the one
        its snapshot's origin requires, and exposes `atcf_id`
        and `name` that read whichever is present. Nothing in
        a replay storm is invented: no slot, no roster time, no
        speed in miles per hour.
      - `WindProbabilityProduct.coverage: Geometry | None`:
        `None` for a full product; for an extract, the areal
        geometry it covers, in the product's CRS, with every
        band inside it.
      - Every consumer of `storm.summary` keeps its behavior on
        live snapshots and passes strict pyright; the Phase 2
        tests keep their meaning. `SnapshotRepository.save`
        refuses a replay snapshot: history is live only. If a
        committed JSON Schema changes, re-export it with
        `scripts/export_schemas.py`.
    </requirement>

    <requirement>
      `src/weatherbot/sources/nhc_gis_archive.py`: parsers from
      a converted collection's bytes and its manifest entries to
      `ConeGeometry`, `ForecastTrack`, `TrackPoint`,
      `WatchWarningSegment`, `WindProbabilityProduct`, and
      `ArchiveStorm`, reading attributes only through
      `sources.fields.Fields` with a declared `FIELDS_READ`
      per collection kind (upper-case names), as the live
      parsers do. A record's `Provenance` names
      `nhc-gis-archive`, the original archive's URL and
      SHA-256 from the manifest (the bytes NHC served), the
      corpus's recording date as `fetched_at` (the manifest
      gains `recorded_on: "2026-10-15"`; a replay `fetched_at`
      is that day at 00:00 UTC, documented as day precision),
      the advisory's issuance as `issued_at`, and the advisory
      number. `ADVDATE` becomes the `Advisory` through
      `parse_nhc_local_time`; `VALIDTIME` resolves against it
      through `resolve_track_valid_time`; 9999 maps to `None`;
      a one-vertex segment stays a Point with its
      `geometry_note`; geometry is built with
      `Crs.native(source_crs)`, never relabeled. A WSP extract
      reads its synoptic time from its member name through
      `parse_synoptic_time` and its bands from `PERCENTAGE`.
    </requirement>

    <requirement>
      `src/weatherbot/services/replay.py`: `ReplayCorpus.open(
      directory)` reads `corpus-manifest.json`; `storms()` lists
      each storm's ATCF id, archive name, advisory count, and
      first and last issuance; `snapshots(atcf_id)` yields one
      `Snapshot(origin="replay")` per advisory in the manifest's
      order, each stamped with the advisory's issuance as both
      `started_at` and `completed_at` and a deterministic
      `snapshot_id` (a UUID 5 of the storm and advisory). Each
      snapshot holds the storm's products of that advisory; the
      three probability products of the synoptic time the
      manifest associates with that advisory, when there is
      one; and, when the directory holds arrival KMZ, the pair
      of the latest full advisory at or before it, parsed with
      `parse_arrival_kmz` (outcome `nhc-arrival-times` `ok`), or
      else an `nhc-arrival-times` outcome `skipped` with the
      reason "the corpus holds no arrival-time products". A
      file whose SHA-256 differs from the manifest, a missing
      file, a path that leaves the directory, or an unknown
      storm raises `ReplayError` naming the file and the rule.
    </requirement>

    <requirement>
      The landmark windows. `convert` adds, for every 5 km WSP
      original in the manifest, one collection per threshold at
      `<storm>/wsp/<YYYYMMDDHH>/wsp-<34|50|64>kt.geojson.gz`:
      each band clipped (`shapely.clip_by_rect`) to the two
      boxes reaching one degree of latitude and longitude on
      each side of each landmark in
      `scripts/public_landmarks.toml`, normalized, with floats
      fixed to seven decimals, sorted keys, and gzip `mtime`
      zero, like every subset file; empty clips dropped but the
      file always written; a band Shapely finds invalid is made
      valid before clipping, and its feature records the
      original reason in `geometry_note`. Each collection
      records `source_crs`, `storm`, `synoptic_time`, `source`,
      `threshold_kt`, and a `window` member naming both
      landmarks, the one-degree half-width, and the covered
      MultiPolygon. The manifest's `subset` lists every new file
      and `subset_rule` names the windows; the subset stays
      under 10 MiB and the fixture budget under 25 MiB.
      `NOTICE.md` documents that a windowed product is read only
      at a point inside its window. Keep the `choices` literal:
      `--full` is an option of `convert`.
    </requirement>

    <requirement>
      `convert --full --out DIR` writes a complete conversion —
      every forecast product, every WSP product unclipped, and
      every arrival KMZ copied byte for byte — with its own
      manifest whose `subset` lists every output with its
      SHA-256, so `ReplayCorpus.open(DIR)` reads it like the
      committed subset. It refuses a `DIR` inside the
      repository. `CONTRIBUTING.md` documents it.
    </requirement>

    <requirement>
      The register. `docs/DATA_SOURCES.md`'s "GIS archive"
      section gains a "Fields v2 uses" bullet for each converted
      collection kind and for the WSP extract (backticked field
      names only, as `fixture_support.register_section_fields`
      parses them), a paragraph on the landmark windows and
      their size, and an amended date. A contract test keeps
      each kind's `FIELDS_READ` equal to its register list and
      deletes each read field from a committed collection to
      prove a `SourceSchemaError`.
    </requirement>

    <requirement>
      Tests:
      - `tests/models/`: the origin rules (a live snapshot
        without a roster outcome, a replay snapshot with a
        roster outcome, a storm with both or neither header,
        and a band outside its product's coverage are each
        refused).
      - `tests/sources/test_nhc_gis_archive.py`: each kind
        parses from committed files; the Dorian singleton
        Points; `9999` handling; a WSP extract's bands and
        coverage.
      - `tests/services/test_replay.py`: the committed corpus
        yields 84, 117, 68, and 41 snapshots in advisory order
        with non-decreasing issuance; each snapshot's
        probabilities are the manifest's association; the
        committed subset's arrival outcome is `skipped` with its
        reason; a copied corpus with one flipped byte, a missing
        file, and an escaping path are each refused before
        parsing; the repository refuses a replay snapshot.
      - `tests/replay/` and `tests/scripts/`: the subset checks
        read `ADVISNUM` on forecast products only and check the
        windows (labels, coverage, synoptic times, sizes);
        `--full` refuses a checkout path; reconversion is
        deterministic.
      - `@pytest.mark.corpus`: the full-cache reconversion
        covers the windows byte for byte; a `--full` conversion
        into a temporary directory opens with `ReplayCorpus`,
        and every snapshot of every storm parses, with arrival
        products for Dorian, Ian, and Milton and none for Irma.
    </requirement>

    <requirement>
      `replay-corpus.yml`: add `src/weatherbot/models/**`,
      `src/weatherbot/sources/nhc_gis_archive.py`, and
      `src/weatherbot/services/replay.py` to both path filters;
      keep the cache keyed on the manifest's hash.
      `CHANGELOG.md` and `CONTRIBUTING.md` describe the replay
      snapshots and `--full`.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with its repo-relative path as a comment.
    </requirement>
  </requirements>
</task>
```

### Step 2 acceptance criteria

- A replay `Snapshot` has origin `replay`, an `nhc-gis-archive` outcome and no
  roster outcome, and storms that carry an `ArchiveStorm`; every Phase 2 test
  still passes with its meaning unchanged, and strict pyright is clean.
- `nhc_gis_archive` parses every committed collection kind through a
  `FIELDS_READ` equal to the register's lists, and deleting any read field from
  a committed collection raises a `SourceSchemaError`.
- `ReplayCorpus` yields 84, 117, 68, and 41 replay snapshots for Irma, Dorian,
  Ian, and Milton, in advisory order, with each advisory's associated
  probabilities, and refuses a tampered, missing, or escaping file before
  parsing it.
- The subset holds a windowed 34-, 50-, and 64-kt product for every synoptic
  time of every storm; it stays under 10 MiB, the fixtures under 25 MiB, and
  every file under 5 MiB; `NOTICE.md` and the register describe the windows.
- `convert --full` writes a complete conversion outside the checkout, refuses
  one inside it, and its output opens with `ReplayCorpus`.
- `verify_phase01.py --fast` and `verify_phase02.py --fast` pass; the
  `pytest -m corpus` suite passes locally with the cache.
- **Deployed & verified:** the first `replay-corpus.yml` run on `main` at the
  merge commit is green — verification of every original and byte-for-byte
  reconversion of the extended subset — and its URL is in the PR body.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff; R1 is clean over every new subset file; no
  corpus file is parsed before its checksum matches; and `--full` cannot write
  inside the checkout.

---

## Step 3 — Ladder rules and evidence

**Status:** Not started

> **Goal:** Decide the level. `weatherbot.models.ladder` defines the five levels
> with the brief's names and actions, the eleven rule ids, and `Thresholds` (the
> six thresholds, at the provisional defaults); `weatherbot.models.assessment`
> defines `Assessment`, `Evidence`, `OfficialProduct`,
> `LocationWindProbability`, `UnavailableInput`, and `BreakpointSpan`, the type
> `Location.breakpoint_span` now carries; `src/weatherbot/engine/rules.py` holds
> `RULES` in the order the design rationale fixes, and `assess(snapshot,
> location, thresholds)` in `src/weatherbot/engine/assess.py` evaluates them and
> stops at the first match, recording every match of the deciding rule as
> evidence and every official product it considered — covering or not — with the
> reason; `engine/official.py` applies issue #10's rule to NWS alerts and the
> coverage rule to NHC segments; `engine/breakpoints.py` computes a location's
> breakpoint span from a snapshot's catalogue; `engine/probabilities.py` reads
> the location's band of each wind-speed-probability product, never a storm's
> and never outside an extract's coverage; `engine/outlook.py` reads the
> seven-day development regions; `services/config.py` reads the `[engine]`
> table; an assessment names every input it lacked, and its level then reads as
> a floor; scenarios built from recorded fixtures and the replay corpus prove
> each rule; issue #10 closes with its decision comment; and an issue records
> the operator's open question on storm-surge products. This step decides the
> level; Step 4 adds the storm threats and the diff, and Step 5 calibrates the
> thresholds.

**Branch:** `feature/phase03-step3-ladder-rules`

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

**Model rationale:** Step 3 is coding with planning as its secondary category:
it encodes the ladder that every later phase shows, notifies on, and narrates,
including issue #10's rule and the honest-floor rule for missing inputs. Its
overall complexity is High — eleven ordered rules over five product families
and two official sources, with evidence, configuration, and a cross-cutting
model — and it is not novel, because this roadmap's design rationale states
every trigger, the order, and the coverage rules with their evidence. The
columns differ in depth: Balanced runs Opus 5.5, S-tier in coding and planning,
on Claude Code at Effort High, one rung above its documented `medium` default,
with thinking on; Quality runs the same model at Extra High for the closest
audit of each trigger against the brief; Cost moves the step to GPT-6.1 Sol on
Codex at Intelligence High, S-tier in agentic work and A-tier in coding. The
claude.ai Max subscription funds Claude Code and ChatGPT Pro 5x funds Codex, so
each column costs nothing at the margin while its pool has headroom, and each
backup comes from the other maker. The conversation is new per phase-boundary
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
       feature/phase03-step3-ladder-rules`
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
       Phase 3 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 3`
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

    THIS STEP produces the first values derived from the
    operator's location: distances to segments and the breakpoint
    span. Evidence holds distances, names, codes, and instants,
    and no coordinate field; its `detail` text never repeats a
    coordinate, and a test renders the evidence of an assessment
    of a `synthetic_coordinates()` location and finds none of its
    digits. The engine logs nothing. Scenario tests use the two
    landmarks, or points derived at run time from recorded
    public products (a development region's representative
    point), never a literal. A `ConfigError` from the `[engine]`
    table names the key, never its value.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 3 (Threat engine).
    Step 3: Ladder rules and evidence.

    Current state (as of Phase 3 Step 2):

    - `weatherbot.engine.geodesy` and `weatherbot.engine.geometry`
      (Step 1): `figure_of`, `distance_km`,
      `initial_bearing_deg`, `place`, `covers`, `intersects`,
      `repair`, `nearest_on_line` (with `at_end`), and
      `closest_approach`. The engine coverage floor (90 percent,
      branch) runs in CI.
    - Replay snapshots (Step 2): `Snapshot.origin`,
      `StormProducts.atcf_id`/`name` over a `summary` or an
      `archived` header, `WindProbabilityProduct.coverage`, and
      `ReplayCorpus` over `tests/fixtures/replay/`, with the
      landmark windows. A replay snapshot holds no NWS alerts, no
      outlook areas, and no breakpoint catalogue.
    - The brief's §7 ladder, made exact in this roadmap's design
      rationale: the triggers, the rule order
      (`hurricane_warning`, `tropical_storm_warning`,
      `hurricane_watch`, `evacuation_order`,
      `tropical_storm_watch`, `hurricane_cone`,
      `hurricane_wind_probability`, `storm_cone`,
      `development_region`, `tropical_storm_wind_probability`,
      `all_clear`), issue #10's rule, the segment coverage rule,
      and the provisional thresholds (`coastal_reach_km` 25,
      `segment_end_tolerance_km` 5, `cone_horizon_h` 120,
      `hurricane_wind_floor_pct` 10,
      `tropical_storm_wind_floor_pct` 5,
      `development_chance_floor_pct` 0). A floor is compared
      with a band's lower bound, which is the probability the
      band guarantees.
    - The levels' names and actions are the brief's §7 columns:
      5 Hurricane Warning ("Shelter if not evacuated; expect
      outages; follow local orders"); 4 Warning / Watch /
      Evacuation ("Evacuate vulnerable areas; secure transport;
      assume routes close"); 3 Watch / Hurricane Threat ("Stock
      supplies; pack; set an exit plan"); 2 Tropical Storm Threat
      ("Monitor daily; review plans"); 1 All Clear ("Normal
      activities"). Nothing home-specific: v1's guidance named
      South Florida.
    - Recorded inputs: the 2026-10-12 capture (Simon EP202026 in
      `EP5`; the 34/50/64-kt products of 2026-10-12 18 UTC; an
      Atlantic seven-day development region at 20 percent and a
      Pacific one at 100 percent; the 549-point breakpoint
      catalogue, whose `objectid` order follows the coast, with
      the Bahamas as six regions); the register's `FLC086`
      Coastal Flood Statement, built in
      `tests/contract/test_nws_captures.py` (zones `FLZ069`,
      `FLZ075`, `FLZ174`); and the 2026-10-17 Rip Current
      Statement (`nws-alerts-{point,zone}/2026-10-17/`, found by
      the point, `FLC086`, and `FLZ173`).
      `tests/services/snapshot_support.py` builds a `Snapshot`
      from the recorded fixtures.
    - Breakpoint facts (2026-10-12 catalogue): the Miami-Dade
      landmark's nearest breakpoints are the Miami-Dade/Broward
      County Line (24.0 km, `objectid` 57) and Ocean Reef
      (50.0 km, 56); the Nassau landmark's nearest is the region
      `Bahamas (NW)` (25.7 km).
    - Replay facts (Step 1's anchors): at Irma advisory 036 a
      Hurricane Warning segment passes 1.1 km from the Miami-Dade
      landmark, inside the segment; at Irma 034 a Hurricane Watch
      does; Irma's cones cover that landmark from 022 to 039A; at
      Dorian 030 a Hurricane Warning segment passes 3.8 km from
      the Nassau landmark; at Dorian 032 a Tropical Storm Watch
      ends 22.6 km from the Miami-Dade landmark.
    - `Location.breakpoint_span: None` and the `locations`
      table's JSON `breakpoint_span` column (always null so far);
      `Settings` has `[logging]` and `[http]`, and
      `ENVIRONMENT_OVERRIDES` maps each variable to its key.
    - Issue #10 is open with its kept-inputs comment; its body
      asks for a golden test built from the recorded zone-alert
      capture.
    - Carry-over from Step 1 (the shapes the rules read):
      `nearest_on_line(position, line, figure)` returns
      `Nearest(distance_km, part, fraction, at_end)`; `at_end` is
      false for a Point segment (its one vertex is first and
      last) and for two parts that meet at 180 degrees, so a
      Point segment covers within `coastal_reach_km`. Every
      measuring function refuses a figure other than its
      geometry's own CRS's (`figure_of(geometry.crs)`), and
      `place(location.point, geometry.crs)` gives the position to
      pass. `repair(cone)` returns `Repaired(shape, note)`:
      `shape` is the cone itself when valid, `None` when no area
      remained (the product is unusable: an `UnavailableInput`);
      the note names the reason without its location. `covers`
      counts the boundary as inside. The engine's tests share
      `tests/engine/engine_support.py` (`landmark`, `manifest`,
      `advisories`, `cone`, `segments`, `replay_track`,
      `synthetic_track`, `square`, `wrapped_polygon`; Step 2
      replaced `features` with the archive parser's records);
      `tests/engine/scenarios.py` imports from it as
      `tests/models/` imports `model_samples`. Branch coverage of
      the engine stood at 98 percent after Steps 1 and 2.
    - Carry-over from Step 2 (the replay input the rules read):
      a replay `Snapshot` has `origin="replay"`, outcomes
      `nhc-gis-archive` `ok` and `nhc-arrival-times` (`skipped`
      in the committed subset: "the corpus holds no arrival-time
      products"), and no NWS alerts, outlook areas, or
      breakpoint catalogue: each an input the assessment names
      as missing. Its storms carry `archived: ArchiveStorm`
      (`storm_type` as the archive spells it: `HU`, `TS`, `TD`,
      `PTC` at the cone) with `summary=None`; read
      `storm.atcf_id` and `storm.name`. A committed probability
      product is a window extract: `coverage` is the two
      landmark boxes in the product's native CRS, and 142 of
      the 507 extracts hold no band at all, which inside the
      coverage means no band reaches the point and outside it
      means nothing. A band's `geometry_note` says when its
      shape was made valid. A `convert --full` product has
      `coverage=None`, keeps invalid source bands as published
      (`is_valid` false: read them through `repair`), and has its
      longitudes brought into [-180, 180], so a band that crosses
      the antimeridian steps more than 180 degrees, which
      `covers` unwraps. Ian 036 to 038 have no probability
      product. `ReplayCorpus.open(directory).snapshots(atcf_id)`
      (`weatherbot.services.replay`) yields whole snapshots for
      the scenarios.

    Files to read (every file before drafting):
    - docs/roadmap/phase03-roadmap.md (Overview and its design
      rationale, this step, and the goals of Steps 4 to 6).
    - docs/brief/weatherbot-v2-brief.md (§7, the ladder).
    - Issue #10 (`gh issue view 10 --comments`).
    - src/weatherbot/engine/ (Step 1), src/weatherbot/models/
      (alerts.py, location.py, outlook.py, products.py,
      snapshot.py, storms.py), src/weatherbot/services/config.py,
      services/persistence/repositories.py (the location
      mapping).
    - tests/services/snapshot_support.py,
      tests/contract/test_nws_captures.py, the recorded
      `nws-alerts-*` and breakpoint captures,
      tests/services/test_replay.py (Step 2).
  </context>

  <goal>
    Ship the ladder's models, the eleven ordered rules, and
    `assess(snapshot, location, thresholds) -> Assessment`, with
    issue #10's rule, the segment coverage rule, the breakpoint
    span, the location's wind-probability bands, the development
    regions, the toggle, the `[engine]` table, and honest
    floors, proven on recorded and replayed scenarios; close
    issue #10; open the storm-surge question.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      `weatherbot.models.ladder`: `AlertLevel` (an `IntEnum` 1 to
      5) with each level's name and actions text from the brief;
      `RuleId` (the eleven ids); and `Thresholds`, a frozen model
      with the six fields, their units in their names, their
      provisional defaults, and ranges (a reach of 0 to 200 km,
      an end tolerance of 0 to 50 km, a horizon of 1 to 120 h;
      each floor one of the band lower bounds 0, 5, 10, 20, ...,
      90). `Thresholds.fingerprint()` is the SHA-256 of their
      canonical JSON with `RULES`' order, recorded in every
      assessment. Nothing in it is season- or home-specific.
    </requirement>

    <requirement>
      `weatherbot.models.assessment` (shapes the step chooses,
      with this content): `BreakpointSpan` (one or two catalogue
      names with their country, the catalogue's load date, and
      whether it names a region); `Evidence` (the rule, the
      product kind, the source id and the product's
      `Provenance`, the storm's ATCF id and name when there is
      one, the advisory number and issuance, the test that fired
      — point query, zone list, segment distance, point in
      polygon, band, toggle — the distance in kilometres and
      `at_end` where measured, the CRS name of the geometry
      tested, a closest-approach instant and lead in hours where
      measured, the coast's breakpoint names when known, and a
      plain `detail` sentence); `OfficialProduct` (every NWS
      alert and covering NHC segment the engine considered, with
      `covers` and the reason); `LocationWindProbability` (per
      threshold: the band at the location, "below every band",
      or "outside the extract's coverage", with the synoptic
      time); `UnavailableInput` (what was missing and why); and
      `Assessment` (`location_name`, `snapshot_id`, `origin`,
      `as_of`, `level`, `rule`, `evidence`, `official`,
      `wind_probabilities`, `breakpoint_span`, `unavailable`,
      `thresholds`, `ruleset`, and `complete`, false whenever
      `unavailable` is not empty). `Location.breakpoint_span`
      becomes `BreakpointSpan | None`, and the location
      repository reads and writes the JSON column (null stays
      `None`). Export the new public names from
      `weatherbot.models`.
    </requirement>

    <requirement>
      `engine/official.py`:
      - NWS alerts (issue #10): an alert counts only with status
        `Actual`, a message type other than `Cancel`, and
        `expires` after `as_of`. It covers the location when a
        point query found it, or when `affected_zone_ids` or
        `geocode_ugc` names the location's forecast zone or
        county zone. A county query's alert that names neither
        is listed with `covers` false and the reason
        "county-zone alert outside this location's zones", with
        the zones it covers, and never sets a level. The four
        ladder events are matched by exact NWS event name:
        `Hurricane Warning`, `Hurricane Watch`, `Tropical Storm
        Warning`, `Tropical Storm Watch`. A covering alert of any
        other event (a Storm Surge Warning, an Extreme Wind
        Warning, a Rip Current Statement) is listed with
        `covers` true and sets no level.
      - NHC segments: a segment covers the location when
        `nearest_on_line` gives at most `coastal_reach_km` and
        the point is not at the segment's end, or at most
        `segment_end_tolerance_km` when it is; the distance is
        measured on the segment's own figure. A segment with an
        unknown `tcww` code that covers the location is listed
        with the reason and sets no level. When the snapshot
        holds the catalogue, each covering segment's ends are
        named by their nearest catalogue breakpoints within
        10 km.
    </requirement>

    <requirement>
      `engine/breakpoints.py`: `breakpoint_span(position,
      breakpoints) -> BreakpointSpan | None`. The nearest
      catalogue breakpoint within 100 km; when it is a region (a
      Bahamas-style `country (region)` entry), the span is that
      region; otherwise it is that breakpoint and the
      `objectid` neighbour in the same country between which the
      location's projection falls, ordered by `objectid`; `None`
      beyond 100 km. On the 2026-10-12 catalogue the Miami-Dade
      landmark's span is Ocean Reef to the Miami-Dade/Broward
      County Line, and the Nassau landmark's is `Bahamas (NW)`.
    </requirement>

    <requirement>
      `engine/probabilities.py` and `engine/outlook.py`: for each
      `WindProbabilityProduct` in `snapshot.wind_probabilities`
      (never a storm attribute, issue #12), the band whose
      geometry covers the location (bands are disjoint; a
      boundary point takes the higher band), or "below every
      band"; an extract whose `coverage` does not cover the
      location yields "outside the extract's coverage" and an
      `UnavailableInput`. For each `development_region`
      `OutlookArea`, whether it covers the location and its
      seven-day chance.
    </requirement>

    <requirement>
      `engine/rules.py` and `engine/assess.py`: `RULES` in the
      fixed order; `assess(snapshot, location, thresholds) ->
      Assessment` with `as_of` from the snapshot (`completed_at`;
      a replay snapshot's issuance); each rule reads every source
      it names and returns its matches; the first rule with a
      match decides `level` and `rule`, and its matches are the
      `evidence`; `all_clear` decides when none does. The cone
      rules repair a cone first (an unusable cone is an
      `UnavailableInput`); `hurricane_cone` requires a forecast
      point with `max_wind_kt` of 64 or more at or before the
      closest approach, and the closest approach no more than
      `cone_horizon_h` after `as_of` (an approach already past
      counts as now). Inputs the rules lack become
      `UnavailableInput`: NWS alerts for a location inside NWS
      coverage when the snapshot holds no alert list for it
      (every replay snapshot, a failed alert source, a location
      added later); a failed roster or map source; a storm
      without a cone; a missing probability product; outlook
      areas absent (every replay snapshot). Export `assess` and
      `RULES` from `weatherbot.engine`.
    </requirement>

    <requirement>
      Configuration. `Settings.engine` is the `[engine]` table
      with the six thresholds, the same ranges, and
      `WEATHERBOT_ENGINE_<NAME>` overrides in
      `ENVIRONMENT_OVERRIDES`; a service builds `Thresholds` from
      it. `CONTRIBUTING.md` and the `doctor` text stay unchanged
      except where they list the settings.
    </requirement>

    <requirement>
      Scenarios. `tests/engine/scenarios.py` registers named
      scenarios — a snapshot, a location, and the expected level
      and rule — that this step's tests and Step 5's mutation
      suite share:
      - recorded 2026-10-12 at the Miami-Dade landmark:
        `all_clear`, with every Phase 2 input present;
      - a location at the representative point of the recorded
        Atlantic development region (20 percent):
        `development_region`;
      - issue #10's sides: the Rip Current Statement covers the
        Miami-Dade landmark and sets no level; the `FLC086`
        Coastal Flood Statement is listed as a county-zone alert
        outside its zones; copies of each with the event set to
        `Hurricane Warning` (built in the test, named as built
        from the recorded alert) give `hurricane_warning` and
        `all_clear` respectively;
      - the evacuation toggle on: `evacuation_order`;
      - replay: Irma 036 at the Miami-Dade landmark,
        `hurricane_warning`; Irma 034, `hurricane_watch`; Irma
        022, `hurricane_cone`; Dorian 030 at the Nassau landmark,
        `hurricane_warning`; at Dorian 032 the Tropical Storm
        Watch does not cover the Miami-Dade landmark;
      - partial: the recorded snapshot with both alert sources
        failed lists NWS alerts as unavailable, and its
        assessment is not complete.
      Expected values use the provisional thresholds; Step 5
      moves them to the calibrated ones.
    </requirement>

    <requirement>
      Tests: `tests/engine/test_rules.py`,
      `test_official.py`, `test_breakpoints.py`,
      `test_probabilities.py`, `test_outlook.py`, and
      `test_assess.py` — every rule matching and not matching;
      the order (two matching rules, the earlier decides); alert
      status, cancel, and expiry; a boundary point on a band;
      the extract coverage; repair; the fingerprint stable and
      changing with any threshold; `Thresholds` ranges; the
      `[engine]` table and its overrides (`tests/services/
      test_config.py`); the privacy test from the security
      block. The engine coverage floor still holds.
    </requirement>

    <requirement>
      Issues. Close issue #10 through this PR ("Closes #10")
      after posting a decision comment that states the rule, the
      two recorded cases, and the scenario tests. Open an issue,
      class architectural question, owner the operator: "Should
      a storm-surge watch or warning, or an extreme-wind warning,
      move the ladder?" — listing what this step does with them
      (official context, no level), and name it in the PR body.
    </requirement>

    <requirement>
      Documents: `AGENTS.md` (the engine's public API:
      `assess`, `RULES`), `CHANGELOG.md`. Filepath comment on
      every new file.
    </requirement>
  </requirements>
</task>
```

### Step 3 acceptance criteria

- `weatherbot.models.ladder` and `weatherbot.models.assessment` define the
  levels, the rule ids, `Thresholds` with its fingerprint, `Assessment`,
  `Evidence`, `OfficialProduct`, `LocationWindProbability`, `UnavailableInput`,
  and `BreakpointSpan`; `Location.breakpoint_span` round-trips through the
  repository.
- `RULES` holds the eleven rules in the documented order, and `assess` stops at
  the first match with that rule's matches as evidence.
- Issue #10's rule holds on both recorded cases and their `Hurricane Warning`
  copies; storm-surge, extreme-wind, and other covering alerts set no level and
  are listed.
- The segment coverage rule decides the replay scenarios: Irma 036 and 034 at
  the Miami-Dade landmark, Dorian 030 at the Nassau landmark, and the
  non-covering Dorian 032 watch.
- The breakpoint spans of both landmarks equal the recorded expectations.
- Wind probabilities are read from the snapshot only, at the location's band,
  and never outside an extract's coverage.
- Every scenario in `tests/engine/scenarios.py` gives its expected level and
  rule; the partial scenario lists NWS alerts as unavailable and is not
  complete.
- The `[engine]` table and its overrides set the thresholds, and a bad value
  names its key only.
- Issue #10 is closed with its decision comment; the storm-surge issue is open
  and named in the PR body.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff; no evidence field or `detail` text carries a
  coordinate (the synthetic-location test), and the engine logs nothing.

---

## Step 4 — Per-storm threats and change events

**Status:** Not started

> **Goal:** Say what each storm means for the location, and what changed.
> `weatherbot.models.assessment` gains `StormThreat` — the storm's ATCF id and
> name, its category at the advisory, whether its cone covers the location, the
> distance and initial bearing from its current center to the location, the
> forecast track's closest approach (instant, distance, and lead), whether it is
> forecast to be a hurricane by then, and the earliest-reasonable and
> most-likely arrival of tropical-storm-force winds — with `ArrivalReading`, and
> `ChangeEvent`; `Assessment` gains `threats`.
> `src/weatherbot/engine/threats.py` builds one threat per storm;
> `src/weatherbot/engine/arrivals.py` reads an arrival product at a location
> from the labelled isochrones that the path from the storm's current center to
> the location crosses, using only resolved instants (issue #11), and falls back
> to the closest approach, labelled as such, when no product exists; and
> `src/weatherbot/engine/changes.py`'s `diff(previous, current)` returns the
> typed change events — level changed, advisory issued, an official product
> added, changed, or removed, and a cone entered or left — that Phase 4's
> notification policy consumes. No threat carries a wind-speed probability
> (issue #12). This step completes the engine's output; Step 5 freezes it.

**Branch:** `feature/phase03-step4-storm-threats`

**Deploys:** GitHub Actions → `replay-corpus.yml` gains the engine's paths and
runs the cached arrival-product test; its first run on `main` must be green.

| Setting      | Cost                                     | Balanced                                 | Quality                                  |
| ------------ | ---------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Model        | Sonnet 5.5                               | Opus 5.5                                 | Opus 5.5                                 |
| Backup       | GPT-6.1 Sol — Codex · Intelligence XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh |
| Platform     | Claude Code                              | Claude Code                              | Claude Code                              |
| Effort       | Effort XHigh                             | Effort High                              | Effort XHigh                             |
| Thinking     | On                                       | On                                       | On                                       |
| Conversation | **New**                                  | **New**                                  | **New**                                  |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

**Model rationale:** Step 4 is coding with knowledge as its secondary category,
and it is the phase's first novel algorithm: NHC's arrival-time contours are
mostly open isochrones that never close against the 5 percent contour, so a
planar partition fails, and this roadmap settles on reading the isochrones the
path from the storm's center crosses — an approach measured on 2026-10-18
against every cached product, with no conflict against the closed contours, but
one whose edge cases the step must still prove. Its overall complexity is High —
threats, arrival reading, and a diff over every official source — and novel. The
columns differ in depth: Balanced runs Opus 5.5, S-tier in coding and knowledge,
on Claude Code at Effort High, one rung above its documented `medium` default,
with thinking on; Quality runs the same model at Extra High for the deepest
search of the reading's edge cases; Cost runs Sonnet 5.5, S-tier in coding, on
Claude Code at Extra High, the extra rung covering the novelty. The claude.ai
Max subscription funds Claude Code and ChatGPT Pro 5x funds the GPT-6.1 Sol
backup on Codex, so each column costs nothing at the margin while its pool has
headroom, and every backup comes from the other maker. The conversation is new
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
       feature/phase03-step4-storm-threats`
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
       Phase 3 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 3`
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

    THIS STEP derives the most precise values the engine
    computes about the operator's location: the distance and
    bearing from each storm's public center, the closest
    approach, and arrival times. They are kept in the assessment
    and printed only by Step 6's commands; nothing here logs,
    and no message, `repr`, or exception text carries them. Tests
    use the landmarks and points derived at run time from
    recorded products; the corpus-marked test reads only the
    pinned cache through Step 2's verifying reader.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 3 (Threat engine).
    Step 4: Per-storm threats and change events.

    Current state (as of Phase 3 Step 3):

    - `assess(snapshot, location, thresholds) -> Assessment`
      (Step 3) with `level`, `rule`, `evidence`, `official`,
      `wind_probabilities`, `breakpoint_span`, `unavailable`,
      `thresholds`, `ruleset`, and `complete`;
      `tests/engine/scenarios.py` holds the shared scenarios.
    - Step 1's `closest_approach`, `distance_km`,
      `initial_bearing_deg`, `covers`, `repair`, and `place`;
      Step 2's `ReplayCorpus`, whose `--full` conversion carries
      the arrival KMZ of every full advisory of Dorian, Ian, and
      Milton (Irma has none; intermediates have none).
    - `ArrivalTimeProduct` (issue #11): `kind`
      (`earliest_reasonable`, `most_likely`), `origin` (`kmz`,
      `map_layer`), `withheld_reason`, and `lines`, each with a
      label and a resolved `valid_at` or an `unresolved_reason`;
      the outer contour (`Wind Speed Probability 5% contour`) is
      unlabelled. In the cached products most isochrones are
      open lines; only the first contour and the outer contour
      close, so the outer contour's interior is not partitioned
      by the isochrones.
    - The reading this roadmap fixes, measured 2026-10-18 on all
      244 cached products at both landmarks: the path from the
      storm's current center (the advisory's tau-0 point) to the
      location; the latest labelled instant whose line that path
      crosses starts the interval, and the next labelled instant
      ends it. Of 488 readings, 186 lay outside the outer
      contour, 46 crossed no line (before the first), 11 had no
      later line (after the last, inside the outer contour), 245
      had both, and none contradicted a closed contour (a
      location inside a closed contour of instant T read no
      later than T). Anchors, Dorian advisory 036: the Nassau
      landmark's earliest-reasonable arrival is before 12:00 UTC
      2 September 2019 and its most-likely arrival between 18:00
      UTC 2 September and 00:00 UTC 3 September; the Miami-Dade
      landmark's are between 12:00 and 18:00 UTC 2 September and
      between 00:00 and 12:00 UTC 3 September.
    - The committed corpus holds the archived Dorian 036 pair
      only under `tests/fixtures/recorded/nhc-arrival-times/`
      (with the 2026 Trudy 015 and Simon 038 pairs); the replay
      subset holds none.
    - The brief's notification policy, which Phase 4 applies to
      these events: notify on a level change in either direction,
      on a new advisory for a storm whose cone contains the
      location, and on a new or changed official alert.
    - Carry-over from Step 1: `closest_approach(points:
      Sequence[TrackPoint], position, figure)` returns
      `Approach(distance_km, instant, lead_h)`; it sorts the
      points by `valid_at`, so `lead_h` counts from the earliest
      point (tau 0, the advisory's own position), and a tie goes
      to the earliest instant. `initial_bearing_deg` is in [0,
      360). Pass `figure_of(point.position.crs)`: a mismatched
      figure is refused.
    - Carry-over from Step 2: a replay snapshot holds arrival
      products only when its corpus directory holds the KMZ (a
      `convert --full` directory, never the committed subset):
      the earliest-reasonable and most-likely pair of the latest
      full advisory at or before the snapshot's advisory, parsed
      by `parse_arrival_kmz` against the archive URL (none is
      withheld). Otherwise `nhc-arrival-times` is `skipped`,
      "the corpus holds no arrival-time products", or "... for
      <ATCF id> advisory <n>" (Irma; Ian 036 to 038). A replay
      storm has no roster classification: its category comes
      from the track points (`saffir_simpson`, `max_wind_kt`).
      The recorded Dorian 036 pair stands in for the archive's
      in `tests/services/test_replay.py` (same bytes).

    Files to read (every file before drafting):
    - docs/roadmap/phase03-roadmap.md (Overview and its design
      rationale, this step, Step 5, and Step 6's `status`).
    - docs/roadmap/ROADMAP.md (Phase 3, 3.2; Phase 4, 4.2).
    - src/weatherbot/engine/ and src/weatherbot/models/
      (assessment.py, ladder.py, arrivals.py, storms.py).
    - src/weatherbot/sources/nhc_arrival_times.py (how lines are
      resolved and withheld).
    - tests/engine/ (Step 3), tests/services/test_replay.py,
      the recorded arrival-time captures and their manifest.
    - .github/workflows/replay-corpus.yml.
  </context>

  <goal>
    Ship `StormThreat`, `ArrivalReading`, `ChangeEvent`, and
    `Assessment.threats`; one threat per storm from `assess`;
    the arrival reading with its track fallback; and `diff`,
    proven on recorded products, the replay corpus, and every
    cached arrival product.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Models. `StormThreat`: ATCF id, name, category (the
      Saffir-Simpson category of the advisory's tau-0 point, or
      its `development` text below hurricane strength),
      `in_cone`, `distance_km` and `bearing_deg` from the current
      center to the location (on the geometry's figure, with its
      CRS named), the closest approach (instant, distance,
      lead in hours from `as_of`), `hurricane_by_approach`, and
      `earliest_arrival` and `most_likely_arrival` as
      `ArrivalReading`. `ArrivalReading`: the product's kind and
      origin (`kmz`, or `track` for the fallback) and exactly one
      of — `before` an instant; `between` two instants; `after`
      an instant, inside the 5 percent contour; `outside` the
      5 percent contour (no arrival at that probability within
      the product's 120 hours); `unresolved` with the reason;
      or, for the fallback, the closest approach's instant,
      labelled "track closest approach, not a wind arrival".
      `ChangeEvent`: `level_changed` (from, to, direction up,
      down, or initial), `advisory_issued` (storm, previous and
      current advisory, `in_cone`), `official_added`,
      `official_changed`, `official_removed` (a covering NWS
      alert by id, an alert whose `references` names a covering
      predecessor being `official_changed`; a covering NHC
      segment by storm and code), `cone_entered`, `cone_left`.
      No field of `StormThreat` holds a wind-speed probability.
    </requirement>

    <requirement>
      `engine/threats.py`: `threats_for(snapshot, location,
      as_of) -> tuple[StormThreat, ...]`, one per storm in
      snapshot order, from the storm's own advisory products
      (the tau-0 point for the center and category, the repaired
      cone, the forecast points for the approach). A storm
      without points or cone gets a threat with the missing
      parts unresolved and an `UnavailableInput` on the
      assessment. `assess` fills `Assessment.threats`; the
      level's rules do not change.
    </requirement>

    <requirement>
      `engine/arrivals.py`: `read_arrival(product, center,
      position, figure) -> ArrivalReading`. A `map_layer`
      product, a product with a `withheld_reason`, or lines
      without instants give `unresolved` with the product's own
      reason: no label is ever parsed here and no instant
      guessed. A position outside every closed part of the outer
      contour is `outside`. Otherwise, take the path from the
      center to the position (antimeridian-safe as in Step 1);
      the latest instant among labelled lines the path crosses
      starts the interval (`before` the earliest instant when it
      crosses none), and the next later labelled instant ends it
      (`after` when there is none). A position inside a closed
      labelled contour of instant T must never read later than
      T; when it would, the reading is `unresolved` with that
      reason. When the storm has no product of a kind, the
      reading is the track fallback, and the assessment lists
      the missing product as unavailable.
    </requirement>

    <requirement>
      `engine/changes.py`: `diff(previous: Assessment | None,
      current: Assessment) -> tuple[ChangeEvent, ...]`, pure and
      deterministic, in a fixed order (level, advisories,
      official products, cones). Two assessments of different
      locations, or a `current` older than `previous`, are an
      error. With no previous assessment, `diff` returns the
      initial events: `level_changed` with direction `initial`,
      `official_added` for each covering product, `cone_entered`
      for each cone covering the location, and `advisory_issued`
      for each storm. Only products that cover the location make
      official events. Export `diff` from `weatherbot.engine`.
    </requirement>

    <requirement>
      Tests:
      - `tests/engine/test_threats.py`: the threats of Irma 036
        and Dorian 030 at both landmarks (in-cone as Step 1's
        anchors, the 38.9 km closest approach of Irma 036 at the
        Miami-Dade landmark); a storm without points.
      - `tests/engine/test_arrivals.py`: the archived Dorian 036
        pair at both landmarks reads the anchors above; the
        Trudy 015 and Simon 038 pairs at a point derived at run
        time inside each outer contour read a determinate
        interval; a withheld product, a map-layer product, and
        an unresolved line give `unresolved` with their reasons;
        synthetic isochrones cover `before`, `between`, `after`,
        `outside`, and a path across 180 degrees; Irma (no
        product) reads the fallback.
      - `tests/engine/test_changes.py`: every event kind,
        including an NWS alert replaced through `references`, a
        segment's code moving from `HWA` to `HWR`, the initial
        events, and the refusals; replaying Irma at the
        Miami-Dade landmark advisory by advisory gives exactly
        one `cone_entered` (at 022) and one `cone_left` (at 040).
      - `@pytest.mark.corpus` in
        `tests/engine/test_cached_arrivals.py`: through a
        `--full` conversion in a temporary directory, every
        cached arrival product reads at both landmarks without
        an error, never contradicts a closed contour, and gives
        an interval whose start precedes its end.
    </requirement>

    <requirement>
      `replay-corpus.yml`: add `src/weatherbot/engine/**` and
      `tests/engine/**` to both path filters, so a change to the
      engine reruns the cached tests. The engine coverage floor
      still holds. `CHANGELOG.md`: this step's entries.
      Filepath comment on every new file.
    </requirement>
  </requirements>
</task>
```

### Step 4 acceptance criteria

- `StormThreat`, `ArrivalReading`, and `ChangeEvent` exist, `Assessment.threats`
  holds one threat per storm, and no threat field holds a wind-speed
  probability.
- The archived Dorian 036 pair reads the four anchors at the two landmarks, and
  Irma reads the labelled track fallback.
- Withheld, map-layer, and unresolved products read `unresolved` with their own
  reasons; no label is parsed in the engine.
- `diff` emits every event kind, the initial events, and exactly one
  `cone_entered` and one `cone_left` across Irma's replay at the Miami-Dade
  landmark, and refuses mismatched or reversed assessments.
- The cached arrival test passes locally with the cache: every product reads at
  both landmarks with no contradiction of a closed contour.
- **Deployed & verified:** the first `replay-corpus.yml` run on `main` at the
  merge commit is green, including the cached arrival test, and its URL is in
  the PR body.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff; no threat value reaches a log, message, or
  `repr`, and the tests use only landmarks and points derived from recorded
  products.

---

## Step 5 — Calibration, golden replays, and the written ladder

**Status:** Not started

> **Goal:** Freeze the engine against history. `ReplayService.timeline(atcf_id,
> location, thresholds)` in `src/weatherbot/services/replay.py` returns each
> advisory's assessment with its change events; `scripts/calibrate_ladder.py`
> replays the committed corpus at both landmarks with the shared scenarios,
> sweeps every threshold across its legal range, and reports each threshold's
> calibration interval — the values that leave every golden outcome unchanged —
> and each level's lead over the official watches and warnings; the step sets
> every default by the criteria below and records its interval and evidence in
> `weatherbot.models.ladder`; `scripts/build_goldens.py` writes the eight golden
> timelines under `tests/golden/replay/`, which the operator reviews once and
> approves, after which they are frozen; `tests/engine/test_golden_replays.py`
> requires the engine to reproduce them, and
> `tests/engine/test_golden_mutations.py` requires every removed or reordered
> rule, and every threshold moved past a finite end of its interval, to change
> at least one golden; `docs/ALERT-LADDER.md` gives the levels, triggers,
> priority order, thresholds with their calibration evidence, and actions, with
> three tables that `scripts/export_ladder.py` renders from code and a test
> compares; and a cached cross-check proves that the landmark windows change no
> outcome against the full probability products. This step freezes what Steps 3
> and 4 built; Step 6 stores and prints it.

**Branch:** `feature/phase03-step5-golden-replays`

**Deploys:** GitHub Actions → `replay-corpus.yml` runs the full-products
cross-check of the goldens; its first run on `main` must be green.

| Setting      | Cost                                    | Balanced                                 | Quality                                  |
| ------------ | --------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Model        | Sonnet 5.5                              | Opus 5.5                                 | Opus 5.5                                 |
| Backup       | GPT-6.1 Sol — Codex · Intelligence High | GPT-6.1 Sol — Codex · Intelligence XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh |
| Platform     | Claude Code                             | Claude Code                              | Claude Code                              |
| Effort       | Effort XHigh                            | Effort High                              | Effort XHigh                             |
| Thinking     | On                                      | On                                       | On                                       |
| Conversation | **New**                                 | **New**                                  | **New**                                  |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

**Model rationale:** Step 5 is planning with coding as its secondary category:
its hard part is judgment — choosing six defaults from historical evidence,
deciding what a sensible ladder looks like across four storms, and presenting
eight timelines the operator can approve in one review — and its code (a
calibration sweep, a golden builder, a mutation suite, a renderer) serves that
judgment. Its overall complexity is High, and it is novel: no prior phase
calibrated anything, and the criteria below must be applied, not looked up. The
columns differ in depth: Balanced runs Opus 5.5, S-tier in planning and coding,
on Claude Code at Effort High, one rung above its documented `medium` default,
with thinking on; Quality runs the same model at Extra High for the most
careful weighing of the evidence; Cost runs Sonnet 5.5, S-tier in planning and
the cheapest model the catalog rates S for planning, on Claude Code at Extra
High. The claude.ai Max subscription funds Claude Code and ChatGPT Pro 5x funds
the GPT-6.1 Sol backup on Codex, so each column costs nothing at the margin
while its pool has headroom, and every backup comes from the other maker. The
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
       feature/phase03-step5-golden-replays`
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
       Phase 3 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 3`
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

    THIS STEP writes the first committed engine outputs. Golden
    files and the ladder document hold levels, rule ids,
    advisory numbers, instants, codes, and distances at the two
    public landmarks only; no golden or scenario uses the
    operator's location, and the personal-data check (R1 and
    R2) covers `tests/golden/` and `docs/ALERT-LADDER.md`, which
    lie outside the payload trees. The calibration and golden
    scripts read the committed corpus through `ReplayCorpus`,
    write only under `tests/golden/` and `docs/`, and refuse to
    run with a relative path that leaves the repository.
    Approving the goldens is the operator's decision: an agent
    never approves its own goldens.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 3 (Threat engine).
    Step 5: Calibration, golden replays, and the written ladder.

    Current state (as of Phase 3 Step 4):

    - The engine is complete: `assess` (eleven rules, evidence,
      official products, wind-probability bands, the breakpoint
      span, unavailable inputs, threats) and `diff`. Thresholds
      are provisional: `coastal_reach_km` 25,
      `segment_end_tolerance_km` 5, `cone_horizon_h` 120,
      `hurricane_wind_floor_pct` 10,
      `tropical_storm_wind_floor_pct` 5,
      `development_chance_floor_pct` 0.
      `tests/engine/scenarios.py` holds the shared scenarios.
    - `ReplayCorpus` yields every advisory of the four storms as
      replay snapshots, with the landmark windows; a `--full`
      conversion adds the full probability products and the
      arrival KMZ.
    - Evidence for the separation thresholds (measured
      2026-10-18, all 310 advisories at both landmarks): covering
      segments pass at most 3.8 km away, with the nearest point
      inside the segment; the nearest non-covering segment that
      ends short of a landmark ends 22.6 km away; the nearest
      non-covering segment alongside a landmark is 58.2 km away.
    - The corpus holds no outlook areas, so only the recorded
      scenarios bind `development_chance_floor_pct`: the
      recorded Atlantic region's seven-day chance is 20 percent.
    - Carry-over from Step 2: `ReplayCorpus.storms()` gives
      `ReplayStorm` (`atcf_id`, `name` (the last advisory's
      `STORMNAME`), `advisories`, `first_issued_at`,
      `last_issued_at`); snapshot ids are
      `replay.snapshot_id(atcf_id, advisory)`, a UUID 5. The
      committed subset replays in 1 to 3 s per storm on the
      operator's machine. The cached cross-check converts with
      `fetch_replay_corpus.convert_full(load_manifest(), cache,
      tmp_path)` (about 45 s; replaying all four storms from it
      took about 5 minutes on Windows) and runs under
      `@pytest.mark.corpus` beside
      `tests/replay/test_full_conversion.py`. When it lands, add
      `src/weatherbot/engine/**` to both `replay-corpus.yml` path
      filters: Step 2 added the models, the archive parser, and
      the replay reader, and Step 7's check 16 also expects the
      engine.
    - The project roadmap's acceptance: all golden replays pass;
      changing any threshold or rule order breaks at least one
      golden; `docs/ALERT-LADDER.md` matches the implemented
      rules through a test that renders the rules from code. A
      threshold side that the corpus cannot bind (a minimum of
      zero, the 120-hour maximum of the cone) cannot break a
      golden; this roadmap reads the criterion as every finite
      end of every calibration interval being guarded, with each
      open end recorded and explained.

    Files to read (every file before drafting):
    - docs/roadmap/phase03-roadmap.md (Overview and its design
      rationale, this step, and Step 6).
    - docs/roadmap/ROADMAP.md (Phase 3: 3.2 to 3.4 and the
      acceptance criteria).
    - docs/brief/weatherbot-v2-brief.md (§7, the ladder and its
      actions).
    - src/weatherbot/engine/, src/weatherbot/models/ladder.py
      and assessment.py, src/weatherbot/services/replay.py.
    - tests/engine/ (the scenarios and every engine test).
    - scripts/export_schemas.py (the render-and-check pattern),
      DISCLAIMER.md, README.md ("Documents").
  </context>

  <goal>
    Ship `ReplayService.timeline`; the calibration script and
    calibrated defaults with their intervals and evidence; eight
    operator-approved, frozen golden timelines; the mutation
    suite; `docs/ALERT-LADDER.md` with its rendered tables and
    their test; and the cached full-products cross-check.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      `ReplayService.timeline(atcf_id, location, thresholds) ->
      tuple[ReplayStep, ...]`: for each replay snapshot in
      order, the `Assessment` and `diff` against the previous
      step's. Nothing is stored. The golden landmarks are built
      by one helper from `scripts/public_landmarks.toml`, the
      recorded `nws-points` answers (the Miami-Dade landmark's
      `FLZ173`, `FLC086`, `MFL`; the Nassau landmark outside NWS
      coverage), and their breakpoint spans from the recorded
      catalogue.
    </requirement>

    <requirement>
      `scripts/calibrate_ladder.py` (with `--check`): replays the
      eight storm-landmark pairs and the scenarios; for each
      threshold, with the others at their defaults, sweeps its
      legal values and reports the calibration interval (the
      contiguous values around the default that leave every
      golden outcome — level and rule at every step — unchanged)
      with the outcome that changes just past each end; and
      reports, per pair, the advisory and instant at which each
      level first appears, the first covering Tropical Storm or
      Hurricane Watch and Warning, the number of level reversals,
      and the closest approach. `--check` verifies that the
      intervals recorded in `weatherbot.models.ladder` equal a
      fresh sweep.
    </requirement>

    <requirement>
      Defaults. Set each default by these criteria, and present
      the evidence with the goldens:
      - `coastal_reach_km` and `segment_end_tolerance_km`: inside
        the corpus gap with at least a factor of two to spare on
        each side (a reach from 7.6 to 29.1 km; an end tolerance
        no more than 11.3 km), at a round value.
      - `cone_horizon_h` and `hurricane_wind_floor_pct`: level 3
        begins at least 48 hours before the first covering
        official watch at every landmark that gets one, with no
        more level reversals than the official products
        themselves make, at a round value (a multiple of 12 h; a
        band lower bound).
      - `tropical_storm_wind_floor_pct`: level 2 begins before
        level 3 wherever both occur, with no more reversals than
        the official products make, at a band lower bound.
      - `development_chance_floor_pct`: the brief's literal
        reading — any seven-day region — unless the evidence
        argues otherwise; bound by the recorded Atlantic
        scenario, and documented as uncalibrated by the corpus.
      Record in `weatherbot.models.ladder`, for each threshold,
      its default, its calibration interval with each open end
      named and explained, and a one-line evidence statement.
      Move the shared scenarios' expectations to the calibrated
      defaults.
    </requirement>

    <requirement>
      Goldens. `scripts/build_goldens.py` (with `--check`) writes
      `tests/golden/replay/<atcf_id>-<landmark>.json` for Irma,
      Dorian, Ian, and Milton at the Miami-Dade and Nassau
      landmarks: the storm, its archive name, the landmark id,
      the corpus manifest's SHA-256, the ruleset fingerprint, and
      one entry per advisory (number, issuance in UTC, level,
      rule, the change kinds, and the codes of covering official
      products), plus an `approval` record (the date and the
      SHA-256 of the timeline it approves). No golden holds a
      coordinate. Render the eight timelines as transitions (the
      advisories where the level or rule changes, with the
      watches and warnings in effect) in the PR body, and ask the
      operator to approve them with the calibration evidence;
      record the approval date in each file only after the
      operator says yes in this session. If the operator asks
      for a change, change the rule, threshold, or criterion
      they name, rebuild, and ask again.
    </requirement>

    <requirement>
      Frozen goldens. `tests/engine/test_golden_replays.py`: each
      engine timeline equals its golden; each golden's ruleset
      fingerprint equals the code's, and its approval digest
      equals its timeline (an edited timeline without a new
      approval fails, naming the file); `build_goldens.py
      --check` passes. A golden changes only with the operator's
      approval recorded in that PR, and `CONTRIBUTING.md` says
      so.
    </requirement>

    <requirement>
      `tests/engine/test_golden_mutations.py`: with the goldens
      and the scenarios as the reference, (a) removing each rule
      but `all_clear`, (b) swapping each adjacent pair of rules,
      and (c) moving each threshold one step past each finite end
      of its recorded interval, each change at least one
      reference outcome. A pair whose swap the corpus cannot
      distinguish (both rules never match together) is listed by
      name in `weatherbot.models.ladder` with that reason, and
      the test checks that the list is exactly the
      indistinguishable pairs. A meta-test proves that every rule
      and every threshold is covered, so a new one cannot escape.
    </requirement>

    <requirement>
      `docs/ALERT-LADDER.md`: what the ladder is and that
      official products decide; the disclaimer and its link; how
      a level is decided (the snapshot's instant, the first
      match, the official sources and their coverage rules,
      issue #10, the breakpoint span); the levels table (number,
      name, actions); the rules table (order, rule id, level,
      trigger, products read); the thresholds table (name,
      default, unit, interval, evidence); what an incomplete
      assessment says; the storm threats and the arrival
      reading; the change events; what does not move the ladder
      (the storm-surge issue linked); and the calibration (the
      corpus, the criteria, a lead-time table per pair, the
      date). The three tables sit between `<!-- ladder:levels -->`
      style markers and are rendered by `scripts/export_ladder.py`
      (with `--check`) from `weatherbot.models.ladder` and
      `weatherbot.engine.rules`; `tests/engine/test_ladder_document.py`
      fails when a block differs. It is the single text the CLI,
      the UI, and the Claude prompts quote. Link it from
      `README.md`'s "Documents".
    </requirement>

    <requirement>
      `@pytest.mark.corpus` in
      `tests/engine/test_golden_full_products.py`: through a
      `--full` conversion in a temporary directory, every
      storm-landmark timeline built from the full probability
      products equals its golden's levels and rules.
    </requirement>

    <requirement>
      `CHANGELOG.md` and `CONTRIBUTING.md` (calibration, goldens,
      approval, the ladder document). The engine coverage floor
      still holds. Filepath comment on every new file.
    </requirement>
  </requirements>
</task>
```

### Step 5 acceptance criteria

- `ReplayService.timeline` replays any corpus storm at any location without
  storing anything.
- Every threshold has a calibrated default chosen by the stated criteria, a
  recorded calibration interval with every open end explained, and an evidence
  line; `calibrate_ladder.py --check` passes.
- Eight golden timelines exist under `tests/golden/replay/`, carry the
  operator's approval date and their timeline digest, hold no coordinate, and
  equal the engine's output; `build_goldens.py --check` passes.
- The mutation suite changes at least one reference outcome for every removed
  rule, every distinguishable adjacent swap, and every threshold moved past a
  finite end of its interval; the indistinguishable pairs are listed exactly,
  and the meta-test covers every rule and threshold.
- `docs/ALERT-LADDER.md` is complete, its three tables equal the code's
  rendering, `export_ladder.py --check` passes, and the README links it.
- The cached cross-check passes locally with the cache.
- **Deployed & verified:** the first `replay-corpus.yml` run on `main` at the
  merge commit is green, including the full-products cross-check, and its URL is
  in the PR body with the operator's approval.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff; R1 and R2 are clean over `tests/golden/` and
  `docs/ALERT-LADDER.md`, and no golden or scenario uses a location other than
  a landmark or a point derived from a public product.

---

## Step 6 — Stored assessments and the commands

**Status:** Not started

> **Goal:** Store and print the level. Alembic revision `0003` creates
> `assessments` (one row per location, snapshot, and ruleset: the level, rule,
> fingerprint, thresholds, completeness, and the whole `Assessment` as validated
> JSON, so it loads back equal), `assessment_evidence` (one row per evidence
> record and official product, for queries), and `assessment_changes` (the
> change events against the previous stored assessment), and adds
> `evacuation_order_set_at` to `locations`; `AssessmentRepository` and
> `AssessmentService` assess every stored location against a snapshot, diff
> against the latest stored assessment, fill the breakpoint span from the
> snapshot's catalogue, and store it all in one transaction; `weatherbot status`
> prints each location's level, deciding evidence, actions, official products,
> wind-speed probabilities, storm threats, and changes, saying "at least" when
> an input was missing; `weatherbot replay ATCF_ID --location NAME --corpus DIR`
> prints the ladder timeline within its time budget; `weatherbot locations
> evacuation NAME on|off` sets the toggle; `locations list` shows the toggle and
> the span; `weatherbot alerts` says which official products cover the location;
> every new or changed `--json` document has its committed schema; and the live
> smoke runs `status` for both landmarks. This step makes the engine usable;
> Step 7 verifies the phase.

**Branch:** `feature/phase03-step6-assessments-status`

**Deploys:** the operator's machine → the local SQLite database migrates to
revision `0003`, after its automatic backup, on the first command after the
merge; `doctor` must report `0003` at the head. GitHub Actions →
`live-smoke.yml`, dispatched on `main`, runs `status` for both landmarks and
must be green.

| Setting      | Cost                                    | Balanced                                 | Quality                                  |
| ------------ | --------------------------------------- | ---------------------------------------- | ---------------------------------------- |
| Model        | GPT-6.1 Sol                             | Opus 5.5                                 | Opus 5.5                                 |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh | GPT-6.1 Sol — Codex · Intelligence XHigh |
| Platform     | Codex                                   | Claude Code                              | Claude Code                              |
| Effort       | Intelligence High                       | Effort High                              | Effort XHigh                             |
| Thinking     | —                                       | On                                       | On                                       |
| Conversation | **New**                                 | **New**                                  | **New**                                  |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

**Model rationale:** Step 6 is coding with an agentic secondary category: a
migration, a repository, a service, four command changes, schemas, and live
and on-machine verification, all on patterns Phase 2's Steps 5 and 6 set. Its
overall complexity is High by scope — every layer from the database to the
terminal, and the privacy of the first stored values about the operator's
location — and it is not novel. The columns differ in depth: Balanced runs Opus
5.5, S-tier in coding and agentic work, on Claude Code at Effort High, one rung
above its documented `medium` default, with thinking on; Quality runs the same
model at Extra High for the closest audit of the migration and the privacy
rules; Cost moves the step to GPT-6.1 Sol on Codex at Intelligence High, S-tier
in agentic work and A-tier in coding. The claude.ai Max subscription funds
Claude Code and ChatGPT Pro 5x funds Codex, so each column costs nothing at the
margin while its pool has headroom, and each backup comes from the other maker.
The conversation is new per phase-boundary hygiene.

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
       feature/phase03-step6-assessments-status`
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
       Phase 3 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 3`
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

    THIS STEP stores the first values derived from the
    operator's location — levels, distances, bearings, closest
    approaches, arrival times — in the local database, under the
    data directory's permissions, beside the coordinates Phase 2
    already keeps there. They are printed only by `status` and
    `replay` on the operator's own terminal, and never written to
    a log line above DEBUG: a test runs `status` over a
    `synthetic_coordinates()` location and finds none of its
    digits, nor its distances, in any log record at INFO or
    above. An agent never runs `status` or `replay` against the
    operator's stored locations: it verifies with the landmarks
    in a temporary database and with `doctor` on the operator's
    machine, which prints only the revision and the head, and
    the operator runs `status` themselves. `replay --corpus`
    reads only inside the directory named. The migration is
    expand-only and runs after the online backup.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 3 (Threat engine).
    Step 6: Stored assessments and the commands.

    Current state (as of Phase 3 Step 5):

    - The engine is frozen: `assess`, `diff`, `RULES`, the
      calibrated `Thresholds` with their intervals, eight
      approved goldens, the mutation suite, and
      `docs/ALERT-LADDER.md`. `ReplayService.timeline` replays a
      corpus storm at a location. `Settings.engine` holds the
      `[engine]` table.
    - Persistence (Phase 2): head `0002`; migrations frozen and
      in package, applied after an online backup, with
      transactional DDL; `UtcDateTime` in tables, plain
      `sa.DateTime()` and `sa.JSON()` in revisions;
      `SnapshotRepository` loads a snapshot back equal;
      `LocationRepository` has `add`, `list`, `get`, `remove`;
      the `locations` table has `breakpoint_span` (JSON, null)
      and `evacuation_order_in_effect` (default false). Check 31
      reads the revisions at `v2.0.0-phase-2` (Step 1), so a
      revision creating these tables keeps `phase-verify (02)`
      green; check 30 checks the baseline and `0002` only.
    - Commands (Phase 2): `locations add|list|remove`, `fetch`,
      `storms`, `alerts`, `doctor`; `cli/runtime.py`
      (`Runtime`, `Output`, `open_session`, exit codes 0, 1, 2);
      `cli/documents.py` and `scripts/export_schemas.py`;
      `tests/cli/cli_support.py`; `alerts` prints `PHASE_3_NOTE`
      for a location outside NWS coverage, and
      `tests/cli/test_commands.py` asserts it; `storms` and
      `alerts` fetch unless `--no-fetch`, and exit 1 on a
      partial or failed snapshot.
    - Traps recorded in Phase 2: respx clears its call log when
      its block exits and merges identical routes; two snapshots
      stamped with one fixed clock make `latest()` ambiguous
      (advance the runtime clock); test basenames must be
      unique; Alembic autogenerate writes package types into
      revisions (replace them); a `/abs` path is not absolute on
      Windows (use `tmp_path`).
    - Carry-over from Step 2: `replay --corpus DIR` opens
      `ReplayCorpus.open(DIR)`; the committed subset lives under
      `tests/fixtures/replay/` and is not in the wheel, so the
      command names its directory. `ReplayError` (`file`,
      `rule`) is the corpus's refusal: a tampered, missing, or
      escaping file, an unreadable manifest, or an unknown storm.
      `ReplayCorpus.storms()` lists the storms a replay can name.
      `SnapshotRepository.save` refuses a replay snapshot
      ("history is live only"), and `cli/snapshots.py`'s
      `storm_entries` describes roster storms only, so a replay
      storm needs its own entry in the `replay` document.

    Files to read (every file before drafting):
    - docs/roadmap/phase03-roadmap.md (Overview and its design
      rationale, this step, and Step 7's checks 41 to 47).
    - docs/ALERT-LADDER.md, src/weatherbot/engine/,
      src/weatherbot/models/ (assessment.py, ladder.py,
      location.py).
    - src/weatherbot/services/ (snapshots.py, locations.py,
      config.py, replay.py, doctor.py) and
      services/persistence/ (tables.py, repositories.py,
      database.py, migrations/versions/).
    - src/weatherbot/cli/ (every module), tests/cli/,
      tests/live/test_cli_live.py, .github/workflows/live-smoke.yml.
    - scripts/export_schemas.py, docs/schema/, README.md
      ("Commands"), CONTRIBUTING.md ("Local data").
  </context>

  <goal>
    Ship revision `0003` with its repository and service;
    `status`, `replay`, and `locations evacuation`; the span and
    toggle in `locations list`; covering products in `alerts`;
    the schemas; the live smoke of `status`; and the operator's
    database at head `0003`.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Revision `0003` (`down_revision` `0002`): `assessments`
      (location, snapshot, ruleset fingerprint, `as_of`, level,
      rule, complete, thresholds JSON, the `Assessment` JSON;
      unique on location, snapshot, and fingerprint; indexed for
      the latest per location), `assessment_evidence` (one row
      per evidence record and per official product, with kind,
      rule, source, code or event, and distance), and
      `assessment_changes` (one row per change event, in order);
      `locations.evacuation_order_set_at` (nullable). Removing a
      location removes its assessments in the same transaction.
      Upgrade from empty and from every earlier revision, and
      downgrade, are tested; `0001` and `0002` stay
      byte-identical.
    </requirement>

    <requirement>
      `AssessmentRepository` (`save(assessment, changes)`,
      `latest(location_name)`, `history(location_name, limit)`,
      `load(id)`; a stored assessment loads back equal) and
      `LocationRepository.set_evacuation_order(name, on, at)` and
      `set_breakpoint_span(name, span)`. `Location` gains
      `evacuation_order_set_at`, and the toggle's evidence names
      that instant. `AssessmentService.assess(snapshot,
      locations)`: per location, the previous stored assessment,
      `assess` with the configured thresholds, `diff`, and the
      breakpoint span from the snapshot's catalogue when it holds
      one and the stored span is absent or differs; one
      transaction per run; an assessment already stored for that
      snapshot, location, and ruleset is returned, not stored
      again. Replay snapshots are refused.
    </requirement>

    <requirement>
      `weatherbot status [--location NAME] [--json]
      [--no-fetch]`: fetch a snapshot (or read the latest stored
      one and print its age), assess and store every location,
      and print, per location (or the one named): the level's
      number and name from `weatherbot.models.ladder`; the
      deciding rule and each evidence record (product,
      issuance, the test, the distance); the actions text; "at
      least" with the missing inputs when the assessment is not
      complete; the official products that cover the location
      and the county-zone alerts outside its zones; the
      wind-speed probabilities at the location; each storm's
      threat (category, in cone, distance and bearing from the
      center, closest approach, both arrivals); the changes since
      the previous stored assessment; the breakpoint span; the
      toggle; and the disclaimer. Instants print in UTC and in
      the location's NWS time zone when it has one. Exit 1 on a
      partial or failed snapshot, as `storms` and `alerts` do.
    </requirement>

    <requirement>
      `weatherbot replay ATCF_ID --location NAME --corpus DIR
      [--json] [--every]`: open the corpus with `ReplayCorpus`
      (a directory without a corpus manifest is a usage error),
      replay the storm at a stored location with the configured
      thresholds, and print the transitions (each advisory where
      the level or rule changes, with its issuance, the rule, the
      covering watches and warnings, and the change kinds), or
      every advisory with `--every`. When the corpus's
      probability products are landmark windows that do not
      cover the location, say so once and name `convert --full`.
      The replay assesses the location with its evacuation
      toggle off, because the toggle is a present-day input, and
      says so when the stored toggle is on. Storm names come from
      the corpus, never from code. Nothing is stored. Budget:
      each storm at each landmark finishes in
      under 10 seconds on the operator's machine (Step 7's
      `--post` measures all eight); a test bounds it at 60
      seconds on CI runners.
    </requirement>

    <requirement>
      `weatherbot locations evacuation NAME on|off` sets the
      toggle and its instant and prints the location's state and
      that the toggle holds the location at level 4 or above
      until it is turned off. `locations list` (and its
      document) shows the toggle with its instant and the
      breakpoint span. `alerts`: for a US location, each alert
      says whether it covers the location or is a county-zone
      alert outside its zones (issue #10); for a location outside
      NWS coverage, the segments that cover it come first, with
      their distance, and the note that matching is Phase 3's
      work is gone (update `tests/cli/test_commands.py`).
    </requirement>

    <requirement>
      Documents and schemas: `StatusDocument` and
      `ReplayDocument` in `cli/documents.py`, and the changed
      `locations` and `alerts` documents, exported to
      `docs/schema/` by `scripts/export_schemas.py`; every
      `--json` test validates against the committed schema first,
      as `cli_support.parse` does.
    </requirement>

    <requirement>
      Tests: `tests/services/test_assessments.py` (the service
      over recorded snapshots, the span fill, the idempotent
      rerun, history, location removal), migration tests in
      `tests/services/test_database.py`, command tests in
      `tests/cli/` for `status`, `replay` (Irma at both
      landmarks over the committed corpus equals the goldens'
      transitions), `locations evacuation`, `locations list`,
      and `alerts`; the privacy test from the security block;
      `tests/live/test_cli_live.py` runs `status` for both
      landmarks against the live services into a temporary
      database. Dispatch `live-smoke.yml` on the branch.
    </requirement>

    <requirement>
      Documents: `README.md` ("Commands": `status`, `replay`,
      `locations evacuation`), `CONTRIBUTING.md` ("Local data":
      the assessment tables and how a location's removal removes
      them), `CHANGELOG.md`. Filepath comment on every new file.
    </requirement>
  </requirements>
</task>
```

### Step 6 acceptance criteria

- Revision `0003` creates the three assessment tables and the
  `evacuation_order_set_at` column; upgrades from empty and from every earlier
  revision, and its downgrade, pass; `0001` and `0002` are unchanged.
- A stored assessment loads back equal; rerunning `status --no-fetch` stores
  nothing new; removing a location removes its assessments.
- `status` prints every listed part for both landmarks over recorded snapshots,
  says "at least" with the missing inputs for an incomplete assessment, and
  exits 1 on a partial snapshot.
- `replay` prints Irma's transitions at both landmarks equal to the goldens and
  stays within its CI bound; `locations evacuation` sets and clears the toggle;
  `locations list` shows the toggle and the span; `alerts` marks coverage and no
  longer prints the Phase 3 note.
- Every new and changed `--json` document validates against its committed
  schema, and `export_schemas.py --check` passes.
- **Deployed & verified:** on the operator's machine the first command after the
  merge backed the database up and migrated it, and `uv run weatherbot doctor`
  reports revision `0003` at the head (only the revision and the head are
  printed in the PR body); `live-smoke.yml` dispatched on `main` is green with
  `status` for both landmarks, and its URL is in the PR body; the operator was
  asked to run `uv run weatherbot status` for their own location themselves.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff; no coordinate, distance, or bearing of an
  assessed location reaches a log record at INFO or above (the
  synthetic-location test), and no agent ran `status` or `replay` against the
  operator's stored locations.

---

## Step 7 — QA & Verification Script

**Status:** Not started

> **Goal:** Package the verification matrix into `scripts/verify_phase03.py`
> (with `--fast`, `--py`, `--live`, `--security`, `--all`, and `--post` modes),
> produce `docs/phase03-qa-findings.md`, add `"03"` to the `phase-verify.yml`
> matrix beside `"01"` and `"02"`, and close the phase. The script reads every
> Step 1 through Step 6 deliverable with standard-library static checks, builds
> the V1–V7 matrix from one offline pytest run with the engine coverage floor,
> one live run, and one cached-corpus run, each with `--junitxml`, and in
> `--post` adds the GitHub readbacks, Phase 2's own `--post` sweep, `doctor` on
> the operator's database, the operations alarm proof, and the replay time
> budget; the closure marks Phase 3 complete in both roadmaps and tags
> `v2.0.0-phase-3`.

**Branch:** `feature/phase03-step7-verify`

**Deploys:** GitHub Actions → `phase-verify (03)` runs on every push and pull
request from the merge on, under the required aggregate `phase-verify`; its
first run on `main` must be green, and the annotated `v2.0.0-phase-3` tag must
peel to the merge commit.

| Setting      | Cost                                     | Balanced                                | Quality                                 |
| ------------ | ---------------------------------------- | --------------------------------------- | --------------------------------------- |
| Model        | GPT-6.1 Sol                              | Opus 5.5                                | Opus 5.5                                |
| Backup       | Sonnet 5.5 — Claude Code · Effort Medium | GPT-6.1 Sol — Codex · Intelligence High | GPT-6.1 Sol — Codex · Intelligence High |
| Platform     | Codex                                    | Claude Code                             | Claude Code                             |
| Effort       | Intelligence Low                         | Effort Medium                           | Effort High                             |
| Thinking     | —                                        | On                                      | On                                      |
| Conversation | **New**                                  | **New**                                 | **New**                                 |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

**Model rationale:** Step 7 is coding with an agentic secondary category —
GitHub readbacks, on-machine sweeps, and the closure — at Medium complexity: it
translates this roadmap's acceptance criteria into numbered checks, a V-matrix,
a matrix entry, and a findings rollup, with `scripts/verify_phase02.py` as the
structural template, and it is not novel. The columns differ in depth: Balanced
runs Opus 5.5, Claude Code's default model and S-tier in coding, at Effort
Medium, its documented default, with thinking on; Quality runs it at Effort
High for a deeper audit of each check against its deliverable; Cost moves the
step to GPT-6.1 Sol on Codex at Intelligence Low, enough for enumerated checks
whose content this roadmap writes down. The claude.ai Max subscription funds
Claude Code and ChatGPT Pro 5x funds Codex, so each column costs nothing at the
margin while its pool has headroom, and each backup comes from the other maker.
The conversation is new per phase-boundary hygiene.

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
       feature/phase03-step7-verify`
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
       Phase 3 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 3`
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
       complete. Phase 3 is
       complete. You can now move
       on to Phase 4." That
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
       one before Phase 4.
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
    own diff must still pass the gate before commit. The
    verifier runs subprocesses from argument lists, never a
    shell; prints check ids, rule names, and exception types,
    never scanned content; reads GitHub settings read-only;
    reads the operator's database only through `doctor`,
    printing only its revision and head; runs every build, live,
    corpus, and alarm probe in a temporary directory; and never
    runs `status` or `replay` against the operator's stored
    locations — the replay budget is timed on the two landmarks
    in a temporary data directory. It never reads or prints the
    personal-data denylist.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 3 (Threat engine).
    Step 7: QA + verification script.

    Steps 1 through 6 have been implemented. Now create the
    verification script, the QA findings, and the matrix entry,
    and close the phase.

    Reference scripts (pattern templates):
    - scripts/verify_phase02.py (the structural precedent: 47
      static checks, the six modes, V rows built from JUnit
      reports where every selection must match a test, a
      failure fails, and a skip is never a pass; the GitHub
      readbacks; the operations proof).
    - scripts/verify_phase01.py (the historical helpers and the
      `--corpus` suite).

    Phase 3 deliverables to verify (52 static checks across
    Steps 1 through 6 plus 5 Step 7 self-checks):

    Step 1 (geodesy and geometry) — checks 1-8:
    1.  `pyproj` at run time; `hypothesis` and `pytest-cov` in
        the dev group.
    2.  `engine/geodesy.py` and `engine/geometry.py` define
        `figure_of`, `distance_km`, `initial_bearing_deg`,
        `place`, `covers`, `intersects`, `repair`,
        `nearest_on_line`, and `closest_approach` (AST).
    3.  No engine module imports from `pyproj` anything but
        `Geod` (AST).
    4.  `tests/test_architecture.py` scans the engine for the
        clock, random, filesystem, environment, and logging
        bans.
    5.  `ci.yml`'s `test` job runs `--cov=weatherbot.engine`,
        `--cov-branch`, and `--cov-fail-under=90`, with
        `COVERAGE_FILE` under `runner.temp`.
    6.  `verify_phase02.py`'s check 31 reads `v2.0.0-phase-2`.
    7.  `tests/test_phase02_verification.py` holds check 31's
        throwaway-repository tests.
    8.  The engine tests are tracked under unique basenames, with
        the deterministic Hypothesis profile.

    Step 2 (replay snapshots) — checks 9-17:
    9.  `Snapshot` declares `origin`; `StormProducts` declares
        `summary` and `archived`; `ArchiveStorm` is exported.
    10. `WindProbabilityProduct` declares `coverage`.
    11. `sources/nhc_gis_archive.py` declares `FIELDS_READ`, and
        the archive field contract test is tracked.
    12. `services/replay.py` defines `ReplayCorpus` and
        `ReplayError` and checks SHA-256 before parsing.
    13. The manifest's `subset` lists windowed 34-, 50-, and
        64-kt products for every synoptic time of the four
        storms, and `recorded_on` is set.
    14. The subset stays under 10 MiB, and `NOTICE.md` documents
        the windows.
    15. `scripts/fetch_replay_corpus.py` keeps the `choices`
        literal and offers `--full`.
    16. `replay-corpus.yml`'s path filters include the models,
        the archive parser, the replay reader, and the engine,
        and its cache is keyed on the manifest's hash.
    17. `SnapshotRepository.save` refuses a replay snapshot.

    Step 3 (ladder rules and evidence) — checks 18-26:
    18. `models/ladder.py` defines `AlertLevel`, `RuleId`, and
        `Thresholds` with its six fields; `models/assessment.py`
        defines `Assessment`, `Evidence`, `OfficialProduct`,
        `LocationWindProbability`, `UnavailableInput`, and
        `BreakpointSpan`.
    19. `RULES` lists the eleven rule ids in the documented
        order.
    20. `Location.breakpoint_span` is typed `BreakpointSpan |
        None`.
    21. `engine/official.py` names the four ladder events and
        reads `found_by`, `affected_zone_ids`, and `geocode_ugc`
        (issue #10).
    22. `engine/official.py` reads `coastal_reach_km`,
        `segment_end_tolerance_km`, and `at_end`.
    23. `engine/probabilities.py` reads the snapshot's
        `wind_probabilities` and each product's `coverage`.
    24. `Settings` has an `[engine]` table with the six
        thresholds and their `WEATHERBOT_ENGINE_*` overrides.
    25. `Evidence` and `Assessment` declare no coordinate field
        (`latitude`, `longitude`, `point`, `position`,
        `coordinates`).
    26. `tests/engine/scenarios.py` is tracked and registers
        issue #10's two recorded cases.

    Step 4 (threats and change events) — checks 27-32:
    27. `StormThreat`, `ArrivalReading`, and `ChangeEvent` are
        defined, and `Assessment` declares `threats`.
    28. `threats_for`, `read_arrival`, and `diff` are defined,
        and `weatherbot.engine` exports `assess`, `RULES`, and
        `diff`.
    29. `StormThreat` declares no wind-probability field (issue
        #12).
    30. No engine module calls `resolve_arrival_label` or
        `parse_nhc_local_time` (issue #11).
    31. `tests/engine/test_cached_arrivals.py` is tracked and
        marked `corpus`.
    32. `ChangeEvent`'s kinds are exactly the seven documented.

    Step 5 (calibration, goldens, and the written ladder) —
    checks 33-40:
    33. `tests/golden/replay/` holds exactly the eight goldens,
        each with `approval`, `ruleset`, and `timeline`.
    34. `scripts/calibrate_ladder.py` and
        `scripts/build_goldens.py` are tracked and offer
        `--check`.
    35. `tests/engine/test_golden_replays.py` and
        `test_golden_mutations.py` are tracked.
    36. `docs/ALERT-LADDER.md` holds the three generated blocks
        and the disclaimer link.
    37. `scripts/export_ladder.py` offers `--check`, and
        `tests/engine/test_ladder_document.py` is tracked.
    38. Every threshold records a calibration interval and
        evidence, and none is provisional.
    39. No golden holds a coordinate key.
    40. `tests/engine/test_golden_full_products.py` is tracked
        and marked `corpus`.

    Step 6 (stored assessments and the commands) — checks 41-47:
    41. Revision `0003` follows `0002` and creates
        `assessments`, `assessment_evidence`, and
        `assessment_changes`.
    42. `AssessmentRepository` and `AssessmentService` are
        defined.
    43. The root app registers `status` and `replay`, and the
        `locations` group registers `evacuation`.
    44. `docs/schema/status.schema.json` and
        `replay.schema.json` are committed beside the five Phase
        2 schemas.
    45. `PHASE_3_NOTE` is gone from `cli/snapshots.py`.
    46. `tests/live/test_cli_live.py` runs `status`.
    47. `README.md`'s "Commands" names `status`, `replay`, and
        `locations evacuation`.

    Step 7 self-checks — checks 48-52:
    48. `scripts/verify_phase03.py` is tracked.
    49. `docs/phase03-qa-findings.md` exists.
    50. `docs/roadmap/phase03-roadmap.md` exists (this doc).
    51. `.github/workflows/phase-verify.yml`'s matrix includes
        `"01"`, `"02"`, and `"03"`.
    52. The security gate is wired: the four hooks in
        `.pre-commit-config.yaml`, and `--security` in every
        phase entry.

    Carry-over from Step 1 (what checks 1-8 read): `ci.yml`'s
    `test` step sets `COVERAGE_FILE` to `.coverage` under
    `runner.temp` in its `env` and runs a folded (`>-`) command
    whose lines
    carry `--cov=weatherbot.engine`, `--cov-branch`, and
    `--cov-fail-under=90`; `tests/conftest.py` registers and
    loads `HYPOTHESIS_PROFILE = "weatherbot"` with
    `derandomize=True`, `database=None`, `deadline=None`;
    `tests/test_architecture.py` defines
    `DETERMINISM_BANNED_IMPORTS`, `DETERMINISM_BANNED_CALLS`,
    `PYPROJ_ALLOWED`, and `nondeterminism()`; and
    `verify_phase02.py` defines `PHASE_2_TAG`, and check 31's
    label names it. Check 31 compares blob ids (`git
    hash-object` against the tagged blob), because Windows CI
    checks text out with CRLF. The engine test modules are
    `tests/engine/test_geodesy.py`, `test_engine_geometry.py`,
    `test_tracks.py`, and `test_engine_properties.py`, with
    `engine_support.py` beside them.

    Carry-over from Step 2 (what checks 9-17 read):
    `Snapshot.origin`, `StormProducts.summary` and `archived`,
    and `ArchiveStorm` in `weatherbot.models.__all__`;
    `WindProbabilityProduct.coverage` (and the new
    `WindProbabilityBand.geometry_note`);
    `nhc_gis_archive.FIELDS_READ` and
    `tests/contract/test_archive_field_coverage.py`;
    `services/replay.py`'s `ReplayCorpus` and `ReplayError`,
    with `hashlib.sha256` checked in `_read` before any parser
    runs; the manifest's 507 `wsp-<34|50|64>kt` subset entries
    at `<storm>/wsp/<yyyymmddhh>/` and `recorded_on`
    (`2026-10-15`); `convert --full` and `--refresh-subset`
    beside the `choices` literal; `SnapshotRepository.save`
    refusing `origin != "live"`. The engine path joins
    `replay-corpus.yml`'s filters in Step 5 (check 16). The
    V2 tests are `tests/models/test_origin.py`,
    `tests/sources/test_nhc_gis_archive.py`,
    `tests/services/test_replay.py`, the window tests in
    `tests/replay/test_corpus_subset.py`, and, under the
    `corpus` marker, `tests/replay/test_full_conversion.py`
    (about 6 minutes with the byte-for-byte reconversion).

    Files to read:
    - scripts/verify_phase02.py (primary structural template)
      and tests/test_phase02_verification.py.
    - scripts/verify_phase01.py (the `--corpus` suite).
    - all Phase 3 implementation files from Steps 1 through 6,
      and docs/phase02-qa-findings.md (the ledger's shape).
    - docs/roadmap/phase03-roadmap.md (this step, every step's
      acceptance criteria, and Post-Implementation
      Verification) and docs/roadmap/ROADMAP.md (Phase 3 and
      Phase 4).
  </context>

  <goal>
    Create scripts/verify_phase03.py with 52 static checks
    (Steps 1 through 6, and 5 Step 7 self-checks) plus the
    28-row V1-V7 matrix (80 in `--post`); create
    docs/phase03-qa-findings.md; add `"03"` to the
    phase-verify.yml matrix; close Phase 3 in both roadmaps; and
    tag `v2.0.0-phase-3`.
  </goal>

  <requirements>
    <requirement>
      Read scripts/verify_phase02.py end-to-end for structure,
      flag parsing, output format, the PASS / FAIL / SKIP
      conventions, and the final summary. Mirror it so the Phase
      3 output is continuous with Phase 2's in CI logs.
    </requirement>

    <requirement>
      scripts/verify_phase03.py modes, mutually exclusive; no
      flag runs `--fast` and `--py`:
      - `--fast`: the 52 static checks only, standard library
        only and offline, CI-safe on Ubuntu, under 30 seconds;
        AST, `tomllib`, `json`, and `git ls-files` reads.
      - `--py`: static checks + ruff, ruff format, strict
        pyright, lint-imports, and one offline pytest run with
        `--cov=weatherbot.engine --cov-branch
        --cov-fail-under=90` and `--junitxml` in a temporary
        directory, plus the wheel smoke.
      - `--live`: static checks + one `pytest -m live` run with
        `--junitxml` (the landmarks only).
      - `--security`: the security gate over the phase's
        surface — gitleaks, bandit over `src` and `scripts`,
        `scripts/audit_deps.py`, and
        `scripts/check_personal_data.py --ci` in CI, or with the
        denylist locally. CI-safe on Ubuntu; non-zero on any
        finding.
      - `--all`: py + live + security, and one `pytest -m
        corpus` run against the local cache.
      - `--post`: static checks + V1-V7, and `gh pr checks` on
        a branch.

      At least one static check is security-oriented and
      confirms the gate is wired, not bypassed (check 52), and
      the checks continue after a failure without echoing
      content.
    </requirement>

    <requirement>
      Post-implementation V-checks (28 rows; JUnit evidence per
      row, every selection matching at least one test):

      V1 — Geodesy and geometry
      - V1.1 Static checks 1-8 all PASS.
      - V1.2 The engine geodesy, geometry, track, and property
        tests pass, and the engine's branch coverage is at least
        90 percent (`--py`).
      - V1.3 The latest `phase-verify.yml` run on `main` is at
        HEAD with `phase-verify (02)` green (check 31 reads
        `v2.0.0-phase-2`).
      - V1.4 `verify_phase02.py --post` reports all 73 checks
        PASS (Phase 1's 75 inside it).

      V2 — Replay snapshots
      - V2.1 Static checks 9-17 all PASS.
      - V2.2 The archive parser, field contract, and
        `ReplayCorpus` tests pass.
      - V2.3 The subset, window, and budget tests pass.
      - V2.4 The latest `replay-corpus.yml` run on `main` is
        green.

      V3 — Ladder rules and evidence
      - V3.1 Static checks 18-26 all PASS.
      - V3.2 The rule, official, breakpoint, probability,
        outlook, and assessment tests pass, scenarios included.
      - V3.3 Issue #10 is closed with its decision comment, and
        the storm-surge issue is open (`gh issue view`).

      V4 — Per-storm threats and change events
      - V4.1 Static checks 27-32 all PASS.
      - V4.2 The threat, arrival, and change tests pass.
      - V4.3 The cached arrival test passes (the corpus run).

      V5 — Calibration, golden replays, and the written ladder
      - V5.1 Static checks 33-40 all PASS.
      - V5.2 The eight golden replays equal the engine, with
        their fingerprints and approval digests.
      - V5.3 The mutation suite passes.
      - V5.4 The ladder document test passes, and
        `export_ladder.py`, `calibrate_ladder.py`, and
        `build_goldens.py` pass `--check`.
      - V5.5 The cached full-products cross-check passes (the
        corpus run).

      V6 — Stored assessments and the commands
      - V6.1 Static checks 41-47 all PASS.
      - V6.2 The assessment service, migration, and command
        tests pass, and every document validates against its
        schema.
      - V6.3 `status` runs against the live services for both
        landmarks (the live run).
      - V6.4 `doctor` reports the operator's database at head
        `0003` (only the revision and the head printed), and the
        alarm proof: a temporary database stamped with an
        unknown revision makes `doctor --offline --json` exit 1
        with the database failing.
      - V6.5 Each of the eight storm-landmark replays over the
        committed corpus finishes in under 10 seconds, timed on
        the two landmarks in a temporary data directory.

      V7 — CI integration + security
      - V7.1 `verify_phase03.py --fast` exits 0 on Ubuntu CI.
      - V7.2 `phase-verify.yml`'s matrix includes `"01"`,
        `"02"`, and `"03"`.
      - V7.3 All 52 static checks pass.
      - V7.4 `verify_phase03.py --security` exits 0.

      The whole offline run's exit is a constituent of V1.2,
      the live run's of V6.3, and the corpus run's of V4.3, so
      no failure escapes `--post`. On `main`, a GitHub readback
      requires the latest run to be at HEAD; run the canonical
      `--post` on clean `main` only after `main`'s
      `phase-verify` run finishes.
    </requirement>

    <requirement>
      Create `tests/test_phase03_verification.py`, mirroring
      Phase 2's: the roadmap and QA documents exist; `--fast`
      runs; the matrix includes `"03"`; checks continue after a
      failure without echoing content; there are exactly 52
      static checks; skipped evidence cannot pass; the mode
      flags are exclusive; JUnit selections must match; the post
      matrix reports exactly 28 rows; and editing a deliverable
      in memory turns exactly its check red.
    </requirement>

    <requirement>
      Update `.github/workflows/phase-verify.yml` to include
      `"03"` in the matrix — append it to `matrix.phase`.
      Preserve `"01"` and `"02"`; this is an additive change.
    </requirement>

    <requirement>
      Create docs/phase03-qa-findings.md with rollup sections for
      this roadmap's PR and every Step 1 through Step 6 PR, a
      Step 7 rollup, the source-drift observations, the
      replay-corpus runs, and a "Pre-ship items" section noting
      documented limitations and downstream-phase follow-ups:
      Phase 4 runs `assess` on a schedule, turns `diff`'s events
      into notifications, and builds its staleness banner on
      incomplete assessments; Phase 5 serves the assessment
      models; Phase 6 quotes `docs/ALERT-LADDER.md` and the
      evidence; Phase 7 drives the replay snapshots in its
      scrubber and decides how an installed package gets the
      corpus; and the storm-surge issue names its owner. Every
      finding has a destination.
    </requirement>

    <requirement>
      Name every Phase 3 check that a later phase's normal
      growth would turn red (as check 31 was for Phase 2), and
      record its historical conversion in the project roadmap's
      Phase 4 entry and the QA ledger, as PR #27 did.
    </requirement>

    <requirement>
      Mark the phase complete in the parent project roadmap
      (docs/roadmap/ROADMAP.md, beside this file) in the SAME
      Stage-3 commit that marks this step (Status rule):
      - `### Phase 3` gets `**Status:** Complete — <YYYY-MM-DD>;
        PR #<n>; v2.0.0-phase-3; phase03-roadmap.md` directly
        under its heading, and the heading ends in ✅.
      - Its row in the "Phase Complexity Summary" table reads
        `Complete` (Step 1's PR set it to `In progress`).
      - The header `> **Status:**` line names Phase 3 as shipped
        and Phase 4 as next.
      - Consistency audit: the Phase 3 "Acceptance criteria"
        there match this roadmap's V1-V7 checks.
      And in THIS roadmap, same commit: its phase-level
      `**Status:**` line (under the title) reads `Complete —
      <YYYY-MM-DD>`, the title and every step heading end in ✅,
      and every step's Summary Table Status cell reads
      `Complete — PR #<n>`.
    </requirement>

    <requirement>
      After the merge, create the annotated tag `v2.0.0-phase-3`
      on the merge commit and push it; `git ls-remote --tags
      origin v2.0.0-phase-3` must show it peeling to the merge
      commit. The package version stays `2.0.0.dev0`.
    </requirement>

    <requirement>
      The script exits 0 on success and 1 on any failure, prints
      a clear PASS / FAIL / SKIP line per check, and mirrors
      `verify_phase02.py`'s output format, check numbering, and
      summary so CI log diffing across phases is frictionless.
      `--fast` must complete in under 30 seconds on Ubuntu CI and
      on the operator's Windows machine. `CHANGELOG.md` and
      `CONTRIBUTING.md` describe it.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative
      path as the first line.
    </requirement>
  </requirements>
</task>
```

### Step 7 acceptance criteria

- `scripts/verify_phase03.py` exists and passes on a clean tree after
  implementation; all six modes exist.
- The script has 52 static checks plus the V1–V7 post-implementation checks (80
  in total).
- `--fast` runs in under 30 seconds on Ubuntu CI and on the operator's Windows
  machine.
- `--post` runs cleanly on the operator's Windows machine with `gh` signed in,
  reporting V1.1 through V7.4 green, Phase 2's 73 checks among them.
- `docs/phase03-qa-findings.md` is complete, with every rollup section and a
  destination for every finding.
- `.github/workflows/phase-verify.yml` runs matrix entries `"01"`, `"02"`, and
  `"03"` on every pull request, under the required aggregate `phase-verify`.
- `--security` exits 0 (secret scan, SAST, dependency audit, and the
  personal-data check clean over the phase's surface); V7.4 is green.
- Branch protection still passes on the resulting PR.
- **Deployed & verified:** the first `phase-verify.yml` run on `main` after the
  merge is green with all three entries; `gh api
  repos/nathanramoscfa/weatherbot/branches/main/protection --jq
  .required_status_checks` still names `gate` and `phase-verify`; and `git
  ls-remote --tags origin v2.0.0-phase-3` shows the tag at the merge commit.
- **Operations:** the phase's local runtime surfaces — `status`, `replay`, and
  the assessment tables — have `doctor` as their health signal and its exit
  status as their alarm, and `--post` injected a failure (a temporary database
  stamped with an unknown revision) and saw `doctor` report FAIL and exit 1;
  `status` exits 1 on a partial snapshot (tested); `replay-corpus.yml` reports
  through its run status and GitHub's failure email. Scheduled monitoring
  arrives in Phase 4.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff, and the `security` job and all three
  `phase-verify` entries are green.
- **Phase closed, nothing carried.** Every finding recorded in
  `docs/phase03-qa-findings.md` has a destination (fixed, an issue number, or a
  named phase that owns it), the "Not in scope" section below is current, and no
  untracked item remains. Every step of this roadmap, this one included, reads
  `**Status:** Complete — PR #…` on `main` under a ✅ heading, the Summary
  Table's Status column and this roadmap's phase-level Status line say
  `Complete` under a ✅ title, and the project roadmap's Phase 3 entry (under a ✅
  heading), its summary-table row, and its header status line say `Complete` —
  all landed in this step's PR. This step's final response ends with the line
  "Step 7 is complete. Phase 3 is complete. You can now move on to Phase 4." in
  place of the usual "Step 7 is complete. You can now move on to Step 8." — same
  Stage 6 rule: no "Follow-ups", no trailer.

---

## Post-Implementation Verification

Every V1–V7 check below runs **automatically in CI** on every push and pull
request, except these. The GitHub readbacks (V1.3, V2.4, V3.3), Phase 2's own
`--post` sweep (V1.4), `doctor` against the operator's database with the alarm
proof (V6.4), and the replay time budget on the operator's machine (V6.5) run in
`--post` on the operator's Windows machine, because they need the operator's
environment, the network, or reads the workflow token lacks. The live suite
(V6.3, and every live test) runs in `--live` locally and in `live-smoke.yml`,
which is dispatched by hand. The cached-corpus suite (V4.3, V5.5) runs in
`replay-corpus.yml` on relevant pull requests and pushes, on Mondays and
Thursdays, and on dispatch, and in `--all` and `--post` against the local
cache.

| Mode         | Workflow                                              | Runner           | Coverage                                                                 |
| ------------ | ----------------------------------------------------- | ---------------- | ------------------------------------------------------------------------ |
| `--fast`     | `phase-verify.yml` (matrix entry `"03"`)              | Ubuntu           | Static checks 1–52: V1.1, V2.1, V3.1, V4.1, V5.1, V6.1, V7.1–V7.3          |
| `--py`       | `ci.yml` (`lint`, `typecheck`, `test` with the engine coverage floor, `package`) | Ubuntu + Windows | V1.2, V2.2, V2.3, V3.2, V4.2, V5.2, V5.3, V5.4, V6.2                      |
| `--security` | `ci.yml` `security` and `phase-verify.yml`            | Ubuntu           | V7.4 (secret scan + SAST + dependency audit + personal-data check)        |
| `--live`     | `live-smoke.yml` (`workflow_dispatch`)                | Ubuntu           | V6.3 and every live test                                                  |
| `--all`      | `replay-corpus.yml` for its corpus part               | Ubuntu           | `--py` + `--live` + `--security` + V4.3 and V5.5 (the cached corpus)      |
| `--post`     | local, on the operator's machine                      | Windows          | V1.3, V1.4, V2.4, V3.3, V6.4, V6.5 + the full V-check sweep              |

Local invocations remain available for ad-hoc runs and pre-release sweeps:

```bash
uv run python scripts/verify_phase03.py --post   # static + V1-V7 + post checks
```

`--post` is the canonical command to run before tagging `v2.0.0-phase-3`.

Other modes:

```bash
uv run python scripts/verify_phase03.py --fast      # static only (CI-safe)
uv run python scripts/verify_phase03.py --py        # + lint, types, tests, coverage, wheel
uv run python scripts/verify_phase03.py --live      # + live services, landmarks only
uv run python scripts/verify_phase03.py --security  # the four-check gate
uv run python scripts/verify_phase03.py --all       # py + live + security + cached corpus
```

The script reports each V-check by id (V1.1, V2.1, ...) so a failure in any
workflow above maps directly to the corresponding row below.

### V1 — Geodesy and geometry

> **Automated in CI.** `phase-verify.yml` → V1.1 and V1.3; `ci.yml` → V1.2;
> `--post` on the operator's machine → V1.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V1.1 | Static checks 1–8 all PASS (dependencies, the geodesy and geometry functions, `Geod` only, the determinism scan, the coverage floor, check 31 historical and its tests, the property profile). | `phase-verify.yml` runs `verify_phase03.py --fast` on every push/PR.       |
| V1.2 | The engine geodesy, geometry, track, and property tests pass, and the engine's branch coverage is at least 90 percent. | `ci.yml` `test` (`--py` locally).                                          |
| V1.3 | `phase-verify (02)` passes with check 31 reading `v2.0.0-phase-2`.                            | `phase-verify.yml` matrix entry `"02"`; `--post` reads the latest run on `main`. |
| V1.4 | `verify_phase02.py --post` reports all 73 Phase 2 checks PASS, with Phase 1's 75 inside it.    | `--post`, local only.                                                      |

### V2 — Replay snapshots

> **Automated in CI.** `phase-verify.yml` → V2.1; `ci.yml` → V2.2 and V2.3;
> `replay-corpus.yml`, read back by `--post` → V2.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V2.1 | Static checks 9–17 all PASS (the replay origin, coverage, the archive parser and reader, the windows in the manifest, the cap, the `choices` literal and `--full`, the workflow paths, the repository refusal). | `phase-verify.yml --fast`.                                                 |
| V2.2 | The archive parser, its field contract, and the `ReplayCorpus` tests pass, tampering refused.  | `ci.yml` `test`.                                                           |
| V2.3 | The subset, window, and budget tests pass.                                                    | `ci.yml` `test`.                                                           |
| V2.4 | The latest `replay-corpus.yml` run on `main` is green.                                         | `--post` (`gh run list`).                                                  |

### V3 — Ladder rules and evidence

> **Automated in CI.** `phase-verify.yml` → V3.1; `ci.yml` → V3.2; `--post` →
> V3.3.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V3.1 | Static checks 18–26 all PASS (the ladder and assessment models, the rule order, the span type, issue #10's inputs, the segment thresholds, the probability reading, the `[engine]` table, no coordinate field, the scenarios). | `phase-verify.yml --fast`.                                                 |
| V3.2 | The rule, official, breakpoint, probability, outlook, and assessment tests pass, every shared scenario included. | `ci.yml` `test`.                                                           |
| V3.3 | Issue #10 is closed with its decision comment, and the storm-surge issue is open.             | `--post` (`gh issue view`).                                                |

### V4 — Per-storm threats and change events

> **Automated in CI.** `phase-verify.yml` → V4.1; `ci.yml` → V4.2;
> `replay-corpus.yml` and the corpus run of `--all` and `--post` → V4.3.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V4.1 | Static checks 27–32 all PASS (the threat models, the functions and exports, no probability on a threat, no label parsing, the cached test, the event kinds). | `phase-verify.yml --fast`.                                                 |
| V4.2 | The threat, arrival, and change tests pass, the Dorian 036 anchors included.                  | `ci.yml` `test`.                                                           |
| V4.3 | Every cached arrival product reads at both landmarks without contradicting a closed contour.  | `replay-corpus.yml` (`pytest -m corpus`); the corpus run locally.          |

### V5 — Calibration, golden replays, and the written ladder

> **Automated in CI.** `phase-verify.yml` → V5.1; `ci.yml` → V5.2 through V5.4;
> `replay-corpus.yml` and the corpus run → V5.5.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V5.1 | Static checks 33–40 all PASS (the eight goldens, the scripts, the tests, the ladder document and its renderer, calibrated thresholds, no coordinate key, the cached cross-check). | `phase-verify.yml --fast`.                                                 |
| V5.2 | The eight golden replays equal the engine, with matching fingerprints and approval digests.   | `ci.yml` `test`.                                                           |
| V5.3 | The mutation suite passes: every removed rule, distinguishable swap, and threshold moved past a finite interval end changes a reference outcome. | `ci.yml` `test`.                                                           |
| V5.4 | `docs/ALERT-LADDER.md` equals the code's tables; `export_ladder.py`, `calibrate_ladder.py`, and `build_goldens.py` pass `--check`. | `ci.yml` `test`.                                                           |
| V5.5 | The goldens hold with the full probability products in place of the landmark windows.         | `replay-corpus.yml` (`pytest -m corpus`); the corpus run locally.          |

### V6 — Stored assessments and the commands

> **Automated in CI.** `phase-verify.yml` → V6.1; `ci.yml` → V6.2;
> `live-smoke.yml` and `--live` → V6.3; `--post` → V6.4 and V6.5.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V6.1 | Static checks 41–47 all PASS (revision `0003`, the repository and service, the commands, the schemas, the note gone, the live test, the README). | `phase-verify.yml --fast`.                                                 |
| V6.2 | The assessment service, migration, and command tests pass, and every document validates against its committed schema. | `ci.yml` `test`.                                                           |
| V6.3 | `status` runs against the live services for both landmarks.                                  | `live-smoke.yml` (dispatch) and `--live`.                                  |
| V6.4 | `doctor` reports the operator's database at head `0003`, and a database stamped with an unknown revision makes `doctor --offline --json` exit 1. | `--post`, local only.                                                      |
| V6.5 | Each of the eight storm-landmark replays over the committed corpus finishes in under 10 seconds. | `--post`, local only (timed on the landmarks in a temporary data directory). |

### V7 — CI integration + security

> **Automated in CI.** `phase-verify.yml` → V7.1 through V7.4 on every push/PR.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V7.1 | `verify_phase03.py --fast` exits 0 on Ubuntu CI.                                              | `phase-verify.yml` matrix entry `"03"`.                                    |
| V7.2 | `phase-verify.yml`'s matrix includes `"01"`, `"02"`, and `"03"`.                                | `phase-verify.yml --fast` static check 51.                                 |
| V7.3 | All 52 static checks in `verify_phase03.py` pass.                                             | `phase-verify.yml --fast` records a pass only when every static check passed. |
| V7.4 | `verify_phase03.py --security` exits 0 (secret scan + SAST + dependency audit + personal-data check). | `phase-verify.yml` `--security` and `ci.yml` `security` on every push/PR.  |

---

## Summary Table

| Step | Scope                         | Model                    | Platform     | Reasoning dial      | Thinking | Conv | Status      |
| ---- | ----------------------------- | ------------------------ | ------------ | ------------------- | -------- | ---- | ----------- |
| 1    | Geodesy + geometry            | Opus 5.5                 | Claude Code  | Effort High         | On       | New  | Complete — PR #29 |
| 2    | Replay snapshots              | Opus 5.5                 | Claude Code  | Effort High         | On       | New  | Not started |
| 3    | Ladder rules + evidence       | Opus 5.5                 | Claude Code  | Effort High         | On       | New  | Not started |
| 4    | Storm threats + changes       | Opus 5.5                 | Claude Code  | Effort High         | On       | New  | Not started |
| 5    | Calibration + golden replays  | Opus 5.5                 | Claude Code  | Effort High         | On       | New  | Not started |
| 6    | Assessments + commands        | Opus 5.5                 | Claude Code  | Effort High         | On       | New  | Not started |
| 7    | QA + verify_phase03.py        | Opus 5.5                 | Claude Code  | Effort Medium       | On       | New  | Not started |
| V1   | Geodesy + geometry            | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V2   | Replay snapshots              | CI: replay-corpus.yml    | --           | --                  | --       | --   | --          |
| V3   | Ladder rules + evidence       | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V4   | Storm threats + changes       | CI: replay-corpus.yml    | --           | --                  | --       | --   | --          |
| V5   | Calibration + golden replays  | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V6   | Assessments + commands        | CI: live-smoke.yml       | --           | --                  | --       | --   | --          |
| V7   | CI integration                | CI: phase-verify.yml     | --           | --                  | --       | --   | --          |

Each step's row restates the Balanced column its **Runs:** line names; the Cost
and Quality columns, and the rule for a pool that reads `tight` or `exhausted`,
live in the step's own Settings table.

---

## Model selection blocks

```text
PROMPT: Step 1 — Geodesy and geometry
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a knowledge secondary — geodesy on two figures, antimeridian-safe geometry, repair, closest approach, and three CI gates, High complexity. PICK: Opus 5.5 is S-tier in coding and knowledge (AA Intelligence Index 57.6), the ladder's Balanced pick. EFFORT: High, one rung above Opus 5.5's medium default, fits established algorithms with many numeric edge cases; Extra High is the Quality column's.

PROMPT: Step 2 — Replay snapshots
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a knowledge secondary — the replay origin across the models, an archive parser with a field contract, a verifying reader, and a pinned-corpus refresh, High complexity. PICK: Opus 5.5 is S-tier in coding and knowledge (AA Intelligence Index 57.6), the ladder's Balanced pick. EFFORT: High fits a cross-cutting change whose shape this roadmap fixes.

PROMPT: Step 3 — Ladder rules and evidence
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a planning secondary — eleven ordered rules over two official sources, issue #10's rule, the segment rule, and honest floors, High complexity. PICK: Opus 5.5 is S-tier in coding and planning (AA Intelligence Index 57.6), the ladder's Balanced pick. EFFORT: High fits specified rules with many interacting inputs; no novel reasoning earns more.

PROMPT: Step 4 — Per-storm threats and change events
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a knowledge secondary — storm threats, a novel arrival reading over open isochrones, and the typed diff, High complexity and novel. PICK: Opus 5.5 is S-tier in coding and knowledge (HLE 61.4%), the ladder's Balanced pick. EFFORT: High fits a measured approach with known anchors; the deepest edge-case search is the Quality column's Extra High.

PROMPT: Step 5 — Calibration, golden replays, and the written ladder
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: planning with a coding secondary — six defaults calibrated from four storms, eight goldens for one operator review, a mutation suite, and the written ladder, High complexity and novel. PICK: Opus 5.5 is S-tier in planning and coding (AA Intelligence Index 57.6), the ladder's Balanced pick. EFFORT: High fits judgment bounded by stated criteria and measured evidence.

PROMPT: Step 6 — Stored assessments and the commands
MODEL: Opus 5.5
BACKUP: GPT-6.1 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — a migration, a repository, a service, four commands, schemas, and live and on-machine verification, High complexity. PICK: Opus 5.5 is S-tier in coding and agentic work (AA Intelligence Index 57.6), the ladder's Balanced pick. EFFORT: High fits Phase 2's established patterns at full-stack scope.

PROMPT: Step 7 — QA + verify_phase03.py
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

The project roadmap's Phase 3 section carries no "Not in scope" list; these
items follow from its phase boundaries and its §6 "Out of Scope":

- The scheduler, `check --once`, notifications and their policy (cooldown,
  quiet hours, escalations), the heartbeat and staleness rules, Task Scheduler,
  and a `config` command. Phase 4 runs `assess`, stores through this phase's
  repository, and turns `diff`'s events into notifications.
- The FastAPI API, server-sent events, and the frontend. Phase 5 serves the
  assessment, evidence, and threat models.
- Claude, the briefing, the change summary, and the grounded chat. Phase 6
  quotes `docs/ALERT-LADDER.md` and the evidence, and can never set a level.
- The replay scrubber, the map's layers (wind radii, surge, radar, satellite),
  the multi-location UI with Nassau, ntfy, quiet hours, history views, and
  export. Phase 7, which also decides how an installed package obtains the
  replay corpus.
- A PyPI release and LAN mode. Phase 8.
- Automated ingestion of evacuation orders (§6). The operator's toggle stands
  in.

Additionally not in scope for this phase:

- Storm-surge watches and warnings, and extreme-wind warnings, moving the
  ladder. They are official context; the issue Step 3 opens records the
  operator's call.
- County-zone alerts outside a location's zones setting a level. Issue #10's
  decision keeps them as context.
- Wind radii and the arrival-time products in the level's rules. The radii stay
  in the cache for Phase 7's display; the arrival products feed the storm
  threats only.
- Inundation and peak-surge products in the engine. They are outside the replay
  corpus; Phase 7 displays them.
- Concurrent storms in a replay. Each replay is one storm's archive; another
  storm active at the time is absent, except inside the combined probability
  products, and `docs/ALERT-LADDER.md` says so.
- Storing replay assessments. History is live only.
- Re-recording the 2026-10-12 capture set or the replay originals. Both stay
  pinned; a change goes through Source drift or a deliberate manifest refresh.
- A package version bump. The version stays `2.0.0.dev0` until the release
  candidate in Phase 8; the milestone tag marks the phase.
- Dependabot PRs #8 and #9. They are independent maintenance, outside every
  step.

---

_This roadmap is the execution plan for Phase 3. Each step's `**Status:**` line
is flipped by that step's own PR (Status rule), so this file on `main` is the
phase's ledger — `grep -n '^\*\*Status:\*\*'` reports progress. After all steps
and verification pass, and every finding has a destination, Phase 3 is complete
— declared with the line "Phase 3 is complete. You can now move on to Phase 4."
and nothing after it — and Phase 4 (Monitoring and notifications) inherits a
pure `assess` with calibrated, documented thresholds, typed change events from
`diff`, stored assessments with their repository and the `status` command it
extends, incomplete assessments its staleness banner builds on, and eight frozen
golden replays that guard every later change to the ladder._
