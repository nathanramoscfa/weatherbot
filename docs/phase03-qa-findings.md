# Phase 3 QA findings

Phase 3 threat engine, verified 2026-10-20. This is the disposition ledger for
[the phase roadmap](roadmap/phase03-roadmap.md), including the findings and
judgement calls in PRs #27 through #37 and Step 7's own. Official products
decide; Phase 3 reads them into a level with evidence, stores the live
assessments, and replays four historical storms at two public landmarks.

Each row names its class, destination and guard. A named later phase owns a
documented limitation; it is not an unfinished Phase 3 implementation.

## Phase roadmap — decisions

Sources: [PR #27](https://github.com/nathanramoscfa/weatherbot/pull/27) and
[PR #28](https://github.com/nathanramoscfa/weatherbot/pull/28).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Phase 2's check 31 forbids later phases' tables, so Phase 3's first assessments revision would turn `phase-verify (02)` red. | Downstream integration requirement | PR #27 recorded it in the project roadmap's Phase 3 entry; Step 1 made check 31 historical against `v2.0.0-phase-2`. | Static checks 6 and 7; V1.3. |
| **Issue #10 (county-zone alerts):** the measured rule is that an NWS alert covers a location when the point query found it or its UGC list names the location's forecast or county zone; a county alert outside them is context that never sets the level. | Architectural decision | Implemented in Step 3, [PR #34](https://github.com/nathanramoscfa/weatherbot/pull/34); [issue #10](https://github.com/nathanramoscfa/weatherbot/issues/10) closed with its decision comment. | Static checks 21 and 26 (four `issue-10-*` scenarios); V3.2; V3.3. |
| Watch-warning segments against the landmarks over 310 advisories: covering lines pass within 3.8 km, short-ending lines at 22.6 km or more, alongside lines at 58.2 km or more. | Measured design input | The segment rule (within the coastal reach and not at an end, or within the end tolerance), calibrated in Step 5. | Static checks 22 and 38; V5.3. |
| The WGS 84 to archive-sphere transform is a "ballpark" offset of zero in PROJ. | Measured design input | Points are placed unchanged and measured on each geometry's own figure; nothing is relabelled. | Static checks 2 and 3; the figure-mismatch refusals in `tests/engine/test_engine_geometry.py`; V1.2. |
| The full 5 km wind-probability products are 52.9 MiB; windows of one degree around each landmark are about 0.6 MiB. | Scope decision | Commit the landmark windows; the full products stay in the cache with a cached cross-check. | Static checks 13, 14, and 40; V2.3; V5.5. |
| The arrival isochrones are mostly open lines, so a planar face partition cannot read them. | Measured design input | Step 4 reads them along the path from the tau-0 center; 0 conflicts with a closed contour over 244 products at both landmarks. | Static check 31; V4.3. |

## Step 1 — Geodesy and geometry

Source: [PR #29](https://github.com/nathanramoscfa/weatherbot/pull/29).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| A sphere geometry measured on WGS 84 by accident would shift every distance. | Correctness rule | Every measuring function refuses a figure other than `figure_of(geometry.crs)`; a projected CRS is refused. | Figure-mismatch tests; static checks 2 and 3; V1.2. |
| A Hypothesis case found that a position given at +360° met an unwrapped ring only two turns away. | Implementation bug, fixed in-step | `covers` normalizes longitude to [-180, 180) before trying ±360°. | `tests/engine/test_engine_properties.py` under the derandomized profile; static check 8. |
| Shapely's repair note carries a bracketed location, which is a coordinate. | Security control | `repair` strips the location from its note. | Geometry tests; the personal-data gate. |
| Windows CI checks text out with CRLF, so check 31's "byte-identical" could not compare bytes. | CI portability, fixed in-step | Check 31 compares blob ids (`git hash-object` against the tagged blob). | Throwaway-repository tests in `tests/test_phase02_verification.py`; static checks 6 and 7. |
| Windows `Path.write_text` writes CRLF, and a Git Bash heredoc turns `\\n` into a newline. | Process lesson | Shared memory; edit scripts write bytes, and splice code through files. | None needed. |
| The repository-root `.coverage` is an ignored version 1 leftover. | Data safety | AGENTS.md: set `COVERAGE_FILE` to an absolute temporary path before any coverage run. | `ci.yml` (static check 5) and `verify_phase03.py --py` put the data file in a temporary directory. |

## Step 2 — Replay snapshots

Source: [PR #32](https://github.com/nathanramoscfa/weatherbot/pull/32).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Phase 1 recorded 39 one-vertex Dorian warning lines in 13 advisories; the originals hold 36 in 12 (057A has no watch-warning product). | Spec rot, fixed in-step | Register, `NOTICE.md`, the roadmap's Current State, and the Phase 1 ledger row (annotated). | `tests/replay/test_corpus_subset.py`. |
| 319 source bands are invalid and 259 records have no shape; 9 clipped bands self-touch. | Source fact / judgement call | Made valid before clipping (and again after, equal to the exact intersection); empty shapes omitted; each change named by `WindProbabilityBand.geometry_note`. | Converter tests; byte-for-byte reconversion; V2.3. |
| The 5 km grid runs west to -260°, past the model's ±180° bound. | Judgement call | `convert --full` adds 360° vertex by vertex, same sphere, and notes it. | `tests/replay/test_full_conversion.py` (corpus). |
| A replay snapshot could be stored as live history. | Correctness rule | `Snapshot.origin`; `SnapshotRepository.save` refuses `origin != "live"`. | Static check 17; V2.2. |
| A refresh of the committed subset must be reproducible. | Judgement call | `convert --refresh-subset`, which refuses a change in omitted advisories. | Static check 15; script tests. |
| Check 16 expects the engine in `replay-corpus.yml`'s filters, which Step 2 did not need. | Downstream note | Step 4 added `src/weatherbot/engine/**` and `tests/engine/**` to both filters. | Static check 16. |

## Step 3 — Ladder rules and evidence

Source: [PR #34](https://github.com/nathanramoscfa/weatherbot/pull/34).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| An NWS point query's provenance URL holds the location's coordinates, and Phase 6 quotes evidence. | Security control | Evidence cites a `Citation`, which drops the URL for `LOCATED_SOURCES`; a validator refuses one. | Static check 25 (no coordinate field on `Evidence`, `Assessment`, or `Citation`); privacy tests. |
| The span's rule needs the breakpoint catalogue's `objectid` and load date, which Phase 2 did not keep. | Upstream gap, fixed in-step | `Breakpoint.objectid` and `loaded_at`; the parser's `FIELDS_READ` and the register amended 2026-10-19. | Field-coverage contract; V3.2. |
| Step 2's carry-over called a failed breakpoint catalogue an unavailable input. | Spec rot, fixed in-step | The catalogue never decides the level, so it is not unavailable; the span falls back to the stored one. Step 3's context annotated. | Assessment tests. |
| Issue #10 auto-closed when roadmap PR #28 merged. | Process / ledger | Not reopened (as #11 and #12 in Phase 2); the decision comment says PR #34 earns the close. | V3.3 reads it closed with a comment. |
| Should a storm-surge or extreme-wind product move the ladder? | Open product question | [Issue #33](https://github.com/nathanramoscfa/weatherbot/issues/33), owned by the operator (Pre-ship items). | V3.3 reads it open or closed with its decision. |
| ruff's ERA001 reads a filepath comment holding "breakpoints" as code. | Process lesson | Shared memory; a justified `noqa`. | None needed. |

## Step 4 — Per-storm threats and change events

Source: [PR #35](https://github.com/nathanramoscfa/weatherbot/pull/35).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| A geodesic path misreads Ian 005 at Nassau, days early. | Measured design input | The reading uses the straight path in the lines' own longitude and latitude, which reproduces the roadmap's counts. | Dorian 036 anchors in `tests/engine/test_arrivals.py`; V4.2. |
| A path that leaves the outer contour and returns cannot be read (22 Ian readings, 3 of which would read "before" wrongly). | Correctness rule | Such a path reads `unresolved`, with its reason. | The frozen cache distribution (186 outside, 43 before, 228 between, 9 after, 22 unresolved); static check 31; V4.3. |
| The recorded Simon 038 pair is degenerate (a two-position outer contour and no isochrone). | Spec rot, fixed in-step | The roadmap's Step 4 task amended. | Arrival tests. |
| How `diff` identifies alerts, segments, and vanished storms. | Judgement calls | Alerts by id (a `references` successor is a change); segments by storm and code; a vanished storm is `cone_left` unless its source failed. Explained in the PR #35 body. | `tests/engine/test_changes.py`; static check 32; V4.2. |
| `model_copy(update=)` skips validation; pyright reads `set != frozenset` as no overlap. | Process lessons | Shared memory. | None needed. |

## Step 5 — Calibration, golden replays, and the written ladder

Source: [PR #36](https://github.com/nathanramoscfa/weatherbot/pull/36).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| The calibration criteria conflicted: Milton at Miami-Dade reaches level 3 at advisory 1 (54 h before its watch) and then level 2, so suppressing the first match loses the 48-hour lead. | Operator decision (2026-10-20) | Measured ordering and reversal exceptions are documented, never smoothed; the 48-hour target stays. Step 5 task and `docs/ALERT-LADDER.md`. | Static check 38; V5.3 (the exception list must equal a fresh measurement). |
| The eight timelines needed the operator's review before freezing. | Operator approval | "Approve these eight timelines", bound to the combined review SHA-256 5710ded5…5a05; each golden carries its approval date and timeline digest. | Static check 33; `build_goldens.py --check`; V5.2 and V5.4. |
| The defaults (25 km, 5 km, 120 h, 10%, 5%, 0%) were provisional. | Calibration | Each now has a measured interval and evidence in `weatherbot.models.ladder` and `docs/ALERT-LADDER.md`; the development floor is scenario-bound, since the archive holds no outlook. | Static check 38; V5.4. |
| Eight adjacent rule swaps are indistinguishable on the corpus and scenarios. | Documented limitation | Recorded as exact exceptions; `all_clear` is a non-matching fallback. | The mutation suite's exception test; V5.3. |
| Keeping every parsed full-product snapshot used about 4 GB. | Implementation bug, fixed in-step | Corpus consumers share one conversion and stream snapshots. | `tests/engine/test_golden_full_products.py`; V5.5. |
| An early coverage run started without `COVERAGE_FILE`; the ignored historical `.coverage` is now absent. | Process lesson | AGENTS.md now requires an absolute temporary `COVERAGE_FILE` before any coverage run. | `ci.yml` and `verify_phase03.py --py` set it. |

## Step 6 — Stored assessments and the commands

Source: [PR #37](https://github.com/nathanramoscfa/weatherbot/pull/37).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| An Alembic batch alteration rebuilds `locations`, and the dropped table's foreign keys cascade-delete every alert observation (0 of 1 kept, measured). | Data safety | Revision `0003` uses plain `op.add_column` and `op.drop_column`. | `test_0003_downgrades_to_0002_without_losing_a_location_or_its_observations`; static check 41; V6.2. |
| `status --no-fetch` after a toggle change returns the stored assessment of that snapshot, whose level did not read the toggle. | Judgement call | History is never rewritten (unique key: location, snapshot, ruleset); `status` warns and says to run a fetching `status`. PR #37 body. | `tests/cli/test_status.py`; V6.2. |
| A raw float bearing reads as a coordinate to the privacy scanners. | Security control | Documents round distances to 0.1 km, bearings to a degree, and leads to 0.1 h. | `tests/cli/test_cli_privacy.py`; static check 44; V6.2. |
| certifi PYSEC-2026-4320 failed the fail-closed dependency audit. | Dependency vulnerability, fixed in-step | Lock-only `fix(deps)` bump to certifi 2026.10.19. | `scripts/audit_deps.py`; V7.4. |
| The first Windows test job ran past its 15-minute bound. | CI capacity, fixed in-step | Replay tests outside the Irma golden check use Milton and store landmarks offline; the job allows 25 minutes. | `ci.yml` `test (windows-latest)`. |
| `tests/cli/test_replay.py` collided with `tests/services/test_replay.py`; an untracked new file escaped the pre-commit stash. | Process lessons | Shared memory; `tests/cli/test_replay_command.py`. | Static check 8 (unique test basenames). |

## Step 7 — Verification and closure

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Phase 3's V rows need a third suite: the cached corpus. | Verification design | One offline pytest run (with the engine coverage floor and its data file in a temporary directory), one live run, and one corpus run each write a JUnit report; each V row selects its tests, every selection must match, a failure fails, and a skip is not a pass. Each run's exit is a constituent of V1.2, V6.3, and V4.3 and V5.5, so no failure escapes `--post`. | `tests/test_phase03_verification.py`: selection, JUnit parsing, skip and failure rules, and exactly 28 rows. |
| The roadmap's V6.4 reads "at head `0003`", which Phase 4's first revision would turn red. | Downstream integration requirement, fixed in-step | V6.4 requires the operator's database at the head and that head to descend from `0003`. | `test_the_operator_database_head_must_descend_from_0003`. |
| The roadmap's V3.3 reads the storm-surge issue "open", which deciding #33 would turn red. | Downstream integration requirement, fixed in-step | V3.3 accepts #33 open, or closed with its decision comment; #10 must be closed with a comment. | `test_issue_10_must_be_decided_and_the_surge_issue_open_or_decided`. |
| Check 33 counts exactly eight files in `tests/golden/replay/`, and check 32 exactly seven change kinds. | Downstream integration requirement | Project roadmap, Phase 4 entry: notification-timeline goldens go in a directory of their own; staleness is not a change kind. A deliberate new kind converts check 32 to read `v2.0.0-phase-3` in the same PR. | Static checks 32 and 33. |
| A test name still called the calibrated thresholds "provisional". | Spec rot, fixed in-step | `test_the_engine_table_defaults_to_the_calibrated_thresholds`. | Static check 38 (no evidence text says provisional). |
| The installed wheel must carry the engine, not only the migrations. | Verification design | The wheel smoke imports `assess`, `RULES`, and `diff` from the installed package and opens a new database at the head. | `--py` package smoke. |
| A static check that silently passes proves nothing. | Verification integrity | Seven probes edit a deliverable in memory (geodesy, the manifest date, the corpus filters, a change kind, a threshold's evidence, a command, the README) and require exactly that check to turn red. | `test_a_changed_deliverable_turns_exactly_its_check_red`. |

## Source-drift observations

Every observation of a source differing from the register or the recorded
set during Phase 3, and where it went:

- **2026-10-19 (Step 2):** the Dorian singleton count is 36 in 12 advisories,
  not 39 in 13 (Step 2 row above).
- **2026-10-19 (Step 3):** the breakpoint catalogue's `objectid` and
  `idp_filedate` joined the register's "Fields v2 uses" (Step 3 row above).
- **2026-10-19 (Step 4):** the recorded Simon 038 arrival pair is degenerate
  (Step 4 row above).
- No live source drift was observed; the live-smoke runs below are green.

## Replay-corpus runs

`replay-corpus.yml` runs on relevant pull requests and pushes, on Mondays and
Thursdays, and on dispatch. Each run below is green:

- Step 1, branch: [39288580223](https://github.com/nathanramoscfa/weatherbot/actions/runs/39288580223); `main`: [39290034234](https://github.com/nathanramoscfa/weatherbot/actions/runs/39290034234).
- Step 2, branch: [39338668068](https://github.com/nathanramoscfa/weatherbot/actions/runs/39338668068) (cold cache), [39339065793](https://github.com/nathanramoscfa/weatherbot/actions/runs/39339065793) (cache hit); `main`: [39341332426](https://github.com/nathanramoscfa/weatherbot/actions/runs/39341332426).
- Step 3, branch: [39355089221](https://github.com/nathanramoscfa/weatherbot/actions/runs/39355089221); `main`: [39355805875](https://github.com/nathanramoscfa/weatherbot/actions/runs/39355805875).
- Step 4, branch: [39364153224](https://github.com/nathanramoscfa/weatherbot/actions/runs/39364153224); `main`: [39365213071](https://github.com/nathanramoscfa/weatherbot/actions/runs/39365213071).
- Step 5, branch: [39419846462](https://github.com/nathanramoscfa/weatherbot/actions/runs/39419846462); `main`: [39422219143](https://github.com/nathanramoscfa/weatherbot/actions/runs/39422219143) (5 passed, the full-products goldens included).
- Step 6, branch: [39533826888](https://github.com/nathanramoscfa/weatherbot/actions/runs/39533826888); `main`: [39535270684](https://github.com/nathanramoscfa/weatherbot/actions/runs/39535270684).

V2.4 reads the latest run on `main`. Failure signal: the run's status and
GitHub's failure email to the operator.

## Live smoke runs

`live-smoke.yml` is dispatch-only; each run below is green:

- Step 6, branch: [39528691201](https://github.com/nathanramoscfa/weatherbot/actions/runs/39528691201); `main` at 550a85b: [39535513115](https://github.com/nathanramoscfa/weatherbot/actions/runs/39535513115) (`status` for both landmarks).

V6.3 reads the live run of `--live` and `--post`. Scheduled monitoring
arrives in Phase 4.

## Pre-ship items

These are documented limitations and downstream owners, with no unassigned
finding:

| Item | Owner / destination | Required next action |
| --- | --- | --- |
| Run `assess` on a schedule; store each cycle through `AssessmentService`. | Phase 4 | The monitor calls the snapshot and assessment services per cycle. |
| Turn `diff`'s change events into notifications. | Phase 4 | The policy reads the stored `assessment_changes`; escalations always notify. |
| A staleness banner on incomplete assessments and stale sources. | Phase 4 | Build it on `Assessment.unavailable` and the heartbeat; staleness is not a change kind. |
| Notification-timeline goldens and change kinds (checks 32 and 33). | Phase 4 | Put new goldens outside `tests/golden/replay/`; a new change kind converts check 32 to read `v2.0.0-phase-3`. |
| An API serving the assessment models. | Phase 5 | Mirror the `status` and `replay` documents and their schemas. |
| Quote the written ladder and the evidence. | Phase 6 | Quote `docs/ALERT-LADDER.md` and stored evidence; never state a model output as a fact. |
| Replay in the UI, and how an installed package gets the corpus. | Phase 7 | Drive replay snapshots in the scrubber; decide whether the corpus ships, downloads, or stays a checkout path. |
| Whether a storm-surge watch or warning, or an extreme-wind warning, moves the ladder. | The operator, [issue #33](https://github.com/nathanramoscfa/weatherbot/issues/33) | Decide; a change to the ladder needs a fresh golden review and closes #33 with its decision comment. |
| The development-chance floor is calibrated on a recorded scenario only; the archive has no outlook. | Any phase that records an outlook during an active season (Source drift) | Re-run `calibrate_ladder.py` with recorded outlooks and review the interval. |
| The milestone tag is not a release; the package stays `2.0.0.dev0`. | Phase 8 | Release readiness and trusted publishing. |
| Dependency updates #8, #30, and #31. | Dependabot PRs | Independent maintenance; not folded into a phase step. |

Run `uv run python scripts/verify_phase03.py --post` for the canonical
52 static + 28 V-check sweep. `--fast` is offline and standard-library only;
`--py`, `--live`, `--security` and `--all` provide the same suites independently.
