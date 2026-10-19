# Phase 2 QA findings

Phase 2 sources and persistence, verified 2026-10-18. This is the disposition
ledger for [the phase roadmap](roadmap/phase02-roadmap.md), including the
findings and judgement calls in PRs #19 through #25 and Step 7's own. Official
products decide; Phase 2 fetches, validates, stores, and prints them, and makes
no assessment yet.

Each row names its class, destination and guard. A named later phase owns a
documented limitation; it is not an unfinished Phase 2 implementation.

## Phase roadmap — decisions

Source: [PR #19](https://github.com/nathanramoscfa/weatherbot/pull/19).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| **Issue #11 (arrival times):** the map layers' labels carry no date or zone, and on 2026-10-12 the `EP5` cone was intermediate advisory 22A while the arrival lines were full advisory 22, so option (a) fails. The arrival-time KMZ the roster links carries `timezone`, `advisoryNum`, and `pubAdvTime`. | Architectural decision | Option (b), the KMZ as register source `nhc-arrival-times`, with the map layers as a label-only fallback (c). Implemented and verified in Step 3, [PR #22](https://github.com/nathanramoscfa/weatherbot/pull/22); [issue #11](https://github.com/nathanramoscfa/weatherbot/issues/11) closed with its decision comment. | Static checks 6, 18, 19, 23; V3.3 (archived pair's checksums and label instants); V3.4 reads the issue closed. |
| **Issue #12 (wind-speed probabilities):** no official field attributes a band to a storm; one product exists per synoptic time. | Architectural decision | Held by the snapshot (`Snapshot.wind_probabilities`); no per-storm field. Verified in Step 2, [PR #21](https://github.com/nathanramoscfa/weatherbot/pull/21) (three products, 34/50/64 kt, `synoptic_at` 2026-10-12 18:00 UTC); [issue #12](https://github.com/nathanramoscfa/weatherbot/issues/12) closed with its decision comment. Project roadmap "Changes from the brief". | Static check 5 (no `storm` or `atcf` field); V3.4. |
| PR #19's merge closed issues #11 and #12 before any parser existed. | Process / ledger | Steps 2 and 3 earned each close with a decision comment, and Step 3's task said to reopen #11 on a failed criterion. | V3.4 reads both closed after the implementing PRs merged. |
| The project roadmap said "coordinates in WGS84"; the replay corpus keeps native D_Sphere. | Spec rot | Geometry carries an explicit CRS: live `EPSG:4326`, replay `native` with its WKT. Project roadmap 2.1 amended. | `Geometry` refuses a missing CRS; no function relabels or transforms. |
| The project roadmap's 2.4 table list included later phases' tables. | Scope decision | Tables arrive with their writers; the list is narrowed in the project roadmap. | Static check 31: no revision creates an assessment, evidence, notification, heartbeat, briefing, or ledger table. |

## Step 1 — Domain models

Source: [PR #20](https://github.com/nathanramoscfa/weatherbot/pull/20).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| NHC's status-file reference gives `movementSpeed` in mph while the shapefiles give speeds in kt and radii in nmi; the task's unit-free names would hide the difference. | Spec rot / judgement call | Unit-bearing names (`movement_speed_mph`, `speed_kt`, `*_extent_nmi`), with sources, in the register (2026-10-16). | Model tests; the register's units section. |
| A pydantic error on a `Location` or `Geometry` would print the operator's coordinates. | Security control | `hide_input_in_errors=True` on the base model; `repr=False` on points, polygons, and URLs. | `tests/models/test_privacy.py` with `synthetic_coordinates()`; V4.3. |
| `ArrivalTimeProduct` could not represent a KMZ that disagrees with its roster. | Judgement call | `withheld_reason` added; every line stays unresolved with the reason. | The validator recomputes each line by the same rule; Step 3's disagreement tests. |
| **Source drift:** the recorded `FLC086` and `FLZ173` alert captures (01:09 UTC on 2026-10-13) are empty; the register's Coastal Flood Statement had expired, and Step 4's criteria depended on it. | Spec rot, fixed in-step | Roadmap Current State, Step 1 context, Step 4 task, criteria, and V4.2 now prove the merge on an alert built from the register's description. | Step 4 recorded a live alert under Source drift (below). |
| Phase 1's exact scaffold, version, and Typer-only checks would turn red as the package grew. | Downstream integration requirement, fixed in-step | `verify_phase01.py` checks 7, 9, and 12 read `v2.0.0-phase-1`. | Static check 8; throwaway-repository tests in `tests/test_phase01_verification.py`; V1.3 and V1.4. |
| In this Windows shell, `lint-imports > /dev/null` returns 1 even when every contract is kept. | Process lesson | Shared memory; read the exit code through a pipe or file. | None needed in CI (no redirect there). |

## Step 2 — HTTP foundation and NHC map clients

Source: [PR #21](https://github.com/nathanramoscfa/weatherbot/pull/21).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| The roster dates an advisory while `Advisory.issued_at` had to equal its local text; both rules could not hold. | Spec rot / judgement call | `Advisory.issued_at_source` (`local_text` or `roster`); a gap over an hour from `advdate` is a Source-drift warning. | Model and map-client tests. |
| `OutlookArea.issued_at` and `ForecastTrack` need fields the register did not list. | Register amendment | Register (2026-10-16): `idp_filedate` on the outlook rows, `advdate` on Forecast Track, the roster's product objects. | Field-coverage contract (`FIELDS_READ` equals the register; 307 cases); static check 17; V2.3. |
| A `Retry-After` over 60 s, ArcGIS paging, and a feature naming another storm in its slot. | Judgement calls | Fail the source rather than wait less; restart paging ordered by `objectid`; skip a mismatched feature with a drift warning. | HTTP-layer and map tests; V2.2. |
| The pre-commit hook runs pyright with unstaged edits stashed, so a partial commit of interdependent changes fails. | Process lesson | Shared memory; one feature commit. | Hook on every commit. |
| Coordinates in URLs at INFO. | Security control | `RedactingFilter` and `redact_url` for `/points/`, `point`, `lat`, `lon`, `latitude`, `longitude`. | `tests/sources/test_http.py`; V4.3. |

## Step 3 — NHC products

Source: [PR #22](https://github.com/nathanramoscfa/weatherbot/pull/22).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| A KMZ is an untrusted zip with untrusted XML. | Security control | At most 64 members, no absolute or `..` names, 8 MiB uncompressed, ratio ≤100:1; `defusedxml` with `forbid_dtd=True` through `sources/markup.py`. | Hardening tests; static check 20; bandit clean without suppression; V3.2. |
| A roster link outside the pattern could send a request anywhere. | Security control | `ARRIVAL_KMZ_URL` anchored on `https://www.nhc.noaa.gov/storm_graphics/api/`; a mismatch raises and is never fetched. | Static check 23; route-not-called test. |
| Personal-data R1 did not look inside zip captures. | Security control, fixed in-step | R1 scans every zip member under the client's bounds and fails closed on an unreadable archive. | Synthetic regression in `tests/scripts/test_check_personal_data.py`. |
| A KMZ `timezone` that differs from the zone in `pubAdvTime` would shift every instant. | Judgement call | Withhold every line with the reason and log Source drift. | Disagreement tests. |
| Step 7's check 24 named a file Step 3 did not create, and check 23 would have missed the escaped regex. | Spec rot, fixed in-step | Step 7's task corrected in PR #22. | Static checks 23 and 24 as now written. |
| The register's RSS field list could not be parsed. | Spec rot | Written as paths (`nhc:Cyclone.atcf`); text products gained field bullets. | `fixture_support.register_section_fields`; contract tests. |

## Step 4 — NWS and geocoding clients

Source: [PR #23](https://github.com/nathanramoscfa/weatherbot/pull/23).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| The NWS documentation does not state the point precision; the API answered five decimals with 301 `AdjustPointPrecision`, and the clients refuse redirects. | Spec rot / source fact | `format_point` writes four decimals, half to even, never `-0`; the register records the API's answer with its date. | AST test: `format_point` is the only writer of a coordinate into a URL; static check 28. |
| Issue #10's county-zone semantics remain open. | Architectural question | [Issue #10](https://github.com/nathanramoscfa/weatherbot/issues/10) stays open for Phase 3; its [kept-inputs comment](https://github.com/nathanramoscfa/weatherbot/issues/10#issuecomment-6237126505). | Every alert keeps `found_by`, `affected_zone_ids`, `geocode_same`, `geocode_ugc`; static check 26; nothing is filtered by zone. |
| Optional `VTEC` and `NWSheadline`; copies of one alert that disagree; three queries in sequence. | Judgement calls | Optional fields read when present; the first copy kept with a drift warning; sequential queries so a documented problem propagates as itself. | Contract deletion tests; merge tests; V4.2. |
| GitHub declined a push exposing the private author email. | Process / repository configuration | Repository-local git `user.email` is the noreply address (operator-approved). One amend used `--no-verify` on a byte-identical tree; every hook then passed on the pushed commit. | Disclosed in PR #23; no hook bypass reached `main`. |

## Step 5 — Persistence and configuration

Source: [PR #24](https://github.com/nathanramoscfa/weatherbot/pull/24).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Loading a snapshot back equal needs four tables beyond the task's list. | Spec rot, fixed in-step | `storm_observations`, `text_product_observations`, `feed_item_observations`, `outcome_responses` in the baseline; Step 5 requirement and Step 7 check 30 amended. | Static check 30; the recorded-snapshot round trip; V5.2. |
| pysqlite runs DDL outside a transaction, so a failed upgrade could leave half a schema. | Implementation bug, fixed in-step | SQLAlchemy's documented recipe: the engine emits `BEGIN`; `transactional_ddl=True`. | Failed-upgrade rollback test. |
| A raw file copy misses rows that live only in the WAL. | Data safety | Backups use SQLite's online backup API; a name collision is refused. | WAL-only row proof in `tests/services/test_database.py`; V5.2. |
| A relative `WEATHERBOT_DATA_DIR` resolves against the working directory, which can be the checkout. | Data safety | Overrides must be absolute (`ConfigError`); the autouse fixture isolates both directories. | Static check 32; `platformdirs`-patched isolation test. |
| The baseline must not change when `tables.py` does. | Judgement call | The baseline names plain SQLAlchemy types. | `alembic check` finds no difference. |

## Step 6 — Services and the first CLI commands

Source: [PR #25](https://github.com/nathanramoscfa/weatherbot/pull/25).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| `doctor` must list stored drift warnings, which no Step 5 table holds. | Scope decision | Alembic revision `0002` adds `drift_warnings`; the baseline stays frozen. | Static check 30; every-revision upgrade test. |
| Step 5's `_migrate` test helper only upgraded, so "upgrade from every revision" was vacuous for `0001`. | Latent test bug, fixed in-step | It downgrades to the earlier target; the probe revision is named `probe`. | `tests/services/test_database.py`; V5.2. |
| Check 28's substring read flagged `Location(point=...)`, which is not a URL. | Spec rot, fixed in-step | Step 7's check 28 is an AST read of string literals; checks 30, 31, 39, 42 amended. | Static checks as now written. |
| Windows runners check text out as CRLF; Rich draws a heavy header on Linux. | CI portability bugs, fixed in-step | Commit 466c768: text compared with text; box-agnostic assertions. | Ubuntu and Windows `test` jobs. |
| httpx logs full request URLs at INFO. | Security control | httpx, httpcore, and Alembic stay at WARNING unless DEBUG; one handler carries `RedactingFilter`. | `tests/cli/test_cli_privacy.py`: no coordinate above DEBUG or outside `locations list`; V4.3. |
| A failed source must not be filled from an earlier snapshot. | Correctness rule | A failed source drops all its records; alerts kept only when both alert sources answered. | Partial-snapshot test (exit 1); V6.2. |
| respx clears its call log when its `with` block exits and merges identical routes; test basenames collide under prepend import. | Process lessons | Shared memory (`cli_support.urls()` reads inside the block; overrides after `serve()`; unique basenames). | The command tests as written. |
| The register is not in the wheel, but `doctor` needs its layer names. | Judgement call | `weatherbot.services.register`. | `tests/contract/test_doctor_register.py` keeps it equal to the register. |

## Step 7 — Verification and closure

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| The project roadmap's Phase Complexity Summary still read Phase 2 `Not started`; Step 1's PR set the Phase 2 Status line but not the table row. | Ledger miss, fixed in-step | This step's closure commit sets the row, the Status line, the heading, and the header line to Complete. | Phase closure criteria read all four. |
| V rows built from separate pytest runs would rerun the suite many times, and a row reading the whole suite's exit says nothing about its own evidence. | Verification design | One offline pytest run (and one live run) writes a JUnit report; each V row selects its modules or tests, every selection must match a test, a failure fails, and a skip is not a pass. The whole run's exit is a constituent of V1.2 (offline) and V6.3 (live), so no failure escapes `--post`. | `tests/test_phase02_verification.py`: selection, JUnit parsing, skip and failure rules, and exactly 26 rows. |
| Step 7's check 10 asks for "no User-Agent literal" in the recorder, which names the `User-Agent` header. | Judgement call | Read as no User-Agent value literal (`weatherbot/<version>` or `(+https://`); the header name stays. | Static check 10. |
| The roadmap's `--post` runs `weatherbot doctor --json` on the operator's machine, which also probes every source. | Judgement call | V5.4 judges the database (at head, migrations pass) and prints only the revision; a source outage is not a database failure. The operations proof runs `doctor --offline` against a temporary database stamped `unknown-revision` and requires exit 1 with a FAIL database row. | V5.4; the doctor test `test_doctor_fails_on_a_database_at_an_unknown_revision`. |
| Check 31 forbids later phases' tables, so Phase 3's first assessments revision would turn `phase-verify (02)` red. | Downstream integration requirement | Project roadmap, Phase 3 entry (PR #27): check 31 becomes historical against `v2.0.0-phase-2`; the other checks stay live; keep entries `"01"` and `"02"`. | The Phase 3 roadmap's first step adapts it, with throwaway-repository tests as in `tests/test_phase01_verification.py`. |
| A static check that silently passes proves nothing. | Verification integrity | Probes edit a deliverable in memory (live smoke trigger and permission, `format_point`, the database ignore rule) and require exactly one check to turn red. | `test_a_changed_deliverable_turns_its_check_red`. |

## Source-drift observations

Every observation of a live source differing from the register or the recorded
set during Phase 2, and where it went:

- **2026-10-13 (Step 1):** the recorded `FLC086` and `FLZ173` alert answers are
  empty; the Coastal Flood Statement the register described had expired. The
  roadmap was corrected (Step 1 row above).
- **2026-10-16 (Step 2):** the roster's product objects, the outlook rows'
  `idp_filedate`, and Forecast Track's `advdate` joined the register's "Fields
  v2 uses". Advisory dating by the roster logs drift when `advdate` is more than
  an hour away.
- **2026-10-17 (Step 3, 04:10–04:17 UTC):** Trudy (EP212026) is issued in `CST`
  and its KMZ products resolve; Simon (EP202026, post-tropical) carries only the
  outer contour. No Atlantic or Central Pacific storm was active, so those basin
  rows stayed at 2026-10-12. `nhc-arrival-times` was the only source
  re-recorded (Dorian 036 archived pair, Trudy 015, Simon 038).
- **2026-10-17 (Step 4):** the NWS API answered a five-decimal point with 301
  `AdjustPointPrecision` (recorded in the register); a live Rip Current
  Statement was returned by the point, `FLC086`, and `FLZ173` and recorded
  beside the 2026-10-12 set (`nws-alerts-{point,zone}/2026-10-17/`); the Nassau
  point answered 400 again; no API key was required.
- **2026-10-17 (Step 6):** the recorded roster links Simon's advisory 22 KMZ,
  which was never recorded, so the advisory 38 pair stands in for the command
  tests and produces the drift warnings they expect. The operator-machine
  `doctor` found every source reachable and 594 of 594 register layers.

## Live smoke runs

`live-smoke.yml` is dispatch-only; each run below is green:

- Step 2, `main` at 9f9d238: [39000150630](https://github.com/nathanramoscfa/weatherbot/actions/runs/39000150630) (5 passed).
- Step 3, branch: [39037032244](https://github.com/nathanramoscfa/weatherbot/actions/runs/39037032244) (12 passed).
- Step 4, branch: [39051642432](https://github.com/nathanramoscfa/weatherbot/actions/runs/39051642432) (15 passed).
- Step 6, branch: [39073754335](https://github.com/nathanramoscfa/weatherbot/actions/runs/39073754335); `main` at 287c4bb: [39077360530](https://github.com/nathanramoscfa/weatherbot/actions/runs/39077360530) (16 passed locally in the session).

V2.4 reads the latest run on `main`. Failure signal: the run's status and
GitHub's failure email to the operator; scheduled monitoring arrives in Phase 4.

## Pre-ship items

These are documented limitations and downstream owners, with no unassigned
finding:

| Item | Owner / destination | Required next action |
| --- | --- | --- |
| County-zone alerts outside the location's forecast zone. | Phase 3, [issue #10](https://github.com/nathanramoscfa/weatherbot/issues/10) | Decide the rule with tests over the kept `found_by`, `affected_zone_ids`, and geocodes. |
| A location's breakpoint span (`breakpoint_span`). | Phase 3 | Fill it from the breakpoints the snapshot holds. |
| The evacuation-order setter. | Phase 3 | Add the command that sets the toggle. |
| Geodesy over the replay corpus's native sphere. | Phase 3 | Honor the native D_Sphere CRS before any distance or containment; never relabel. |
| Wind probabilities at the location level. | Phase 3 | Read the snapshot's products (issue #12's decision); no per-storm field. |
| Arrival instants. | Phase 3 | Use instants only where a line resolved; a label-only or withheld line stays unresolved. |
| A scheduler over the snapshot service; scheduled drift detection; the heartbeat; a `config` command. | Phase 4 | Call `SnapshotService.fetch_snapshot` on a schedule; watch staleness and drift; alarm on failure. |
| An API serving these models and geometry. | Phase 5 | Mirror the CLI documents; this phase's JSON Schemas describe CLI output only. |
| Display layers; peak-surge fields once a capture has features; retention of raw responses. | Phase 7 | Render the stored display layers; re-record peak surge under Source drift when it has features; add retention. |
| Atlantic and Central Pacific active-storm rows of the per-basin table remain open (no active storm there on 2026-10-12 or 2026-10-17). | The phase in progress when a storm is active there (Source drift) | Re-run the recorder for that basin and update the register's dated row and contracts. |
| NWS may require an API key. | Any phase, through Step 4's stop rule; Phase 4's heartbeat surfaces it in operation | Open an issue before adding a key; the key lives only in the environment. |
| The milestone tag is not a release; the package stays `2.0.0.dev0`. | Phase 8 | Release readiness and trusted publishing. |
| Dependency updates #8 and #9. | Dependabot PRs #8/#9 | Independent maintenance; not folded into a phase step. |

Run `uv run python scripts/verify_phase02.py --post` for the canonical
47 static + 26 V-check sweep. `--fast` is offline and standard-library only;
`--py`, `--live`, `--security` and `--all` provide the same suites independently.
