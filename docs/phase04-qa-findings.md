# Phase 4 QA findings

Phase 4 monitoring and notifications, verified 2026-10-24. This is the
disposition ledger for [the phase roadmap](roadmap/phase04-roadmap.md),
including the findings and judgement calls in PRs #39 through #51 and Step 7's
own. Phase 4 makes the monitor run unattended on NHC's UTC schedule, deduplicates
unchanged snapshot geometry in SQLite, decides notifications from stored change
events without suppressing escalations, delivers Windows toasts over `pywinrt`,
and registers the two Windows Task Scheduler entries (`\Weatherbot\serve` and
`\Weatherbot\check`).

Each row names its class, destination, and guard. A named later phase owns a
documented limitation; it is not an unfinished Phase 4 implementation.

## Phase roadmap — decisions

Sources: [PR #39](https://github.com/nathanramoscfa/weatherbot/pull/39) and
[PR #40](https://github.com/nathanramoscfa/weatherbot/pull/40).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Every unchanged cycle stored all 608 geometry rows again (2.0 MiB per cycle, measured 2026-10-21), which would grow SQLite by hundreds of megabytes per week under scheduled operation. | Measured design input | Step 1 deduplicates product content in `geometry_contents` and provenances in `snapshot_provenances` before adding the scheduler. | Static checks 1–5; `tests/cli/test_storage_growth.py`; V1.1–V1.4. |
| APScheduler 3.11.3 is untyped and has an unreleased fix for a loop-stopping exception bug, while 4.0 is an alpha. | Architectural decision | Step 5 implements a small deterministic `asyncio` scheduler (`weatherbot.services.scheduler.Scheduler`) using the standard library only. | Static checks 30 and 31; `tests/services/test_scheduler.py`; V5.1. |
| NHC's advisory schedule is fixed in UTC (routine advisories at 03, 09, 15, 21 UTC; intermediates and outlooks at 00, 06, 12, 18 UTC), and the roster can lead or trail the GIS cone layer by 2 to 68 minutes. | Measured design input | `ROADMAP.md` "Changes from the brief"; Step 5 opens windows at +15 minutes UTC with jitter and polls every 5 minutes until the roster and the cone layer agree on an advisory issued at or after the product hour (or +60 minutes). | Static checks 28 and 32; `tests/services/test_schedule.py`; V5.2. |
| A drop caused by a transient missing input or an unconfirmed intermediate state would send "fell" and then "rose" 5 minutes later. | Architectural decision | `ROADMAP.md` "Changes from the brief"; Step 3 announces levels against the last announced level, sends escalations immediately, and holds drops for a 5-minute confirming cycle (at most 3 holds). | Static checks 16–18; `tests/services/test_policy.py`; V3.1 and V3.2. |
| `virtualenv` CVE-2026-113722 failed `pip-audit --strict` during PR #40. | Security finding, fixed in-step | Lock-only `fix(deps)` bump of `virtualenv` from `21.14.7` to `21.14.12` in PR #40. | `scripts/audit_deps.py`; V7.4. |
| Phase 3's checks 32 (`CHANGE_KINDS`), 33 (`tests/golden/replay/`), and 38 (`Thresholds`) are exact. | Downstream integration requirement | `ROADMAP.md` Phase 4 note: staleness is a heartbeat/assessment flag, notification goldens live in `tests/golden/notifications/`, and Phase 4 settings live in `[monitor]` and `[notifications]`. | `verify_phase03.py` checks 32, 33, and 38; static checks 14, 19, and 20. |

## Step 1 — Snapshot storage that stays small

Source: [PR #41](https://github.com/nathanramoscfa/weatherbot/pull/41).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| The roadmap draft's link table (`snapshot_id` + 64-byte hex `content_sha256` + inline provenance per row) measured 144–152 KiB per unchanged cycle, exceeding the 128 KiB budget. | Spec rot, fixed in-step | Revision `0004` normalizes `snapshot_provenances` once per response and links `snapshot_geometries` by integer `provenance_id` and `content_id`, measuring 64 KiB across two unchanged cycles. Step 1 task block amended. | Static checks 1–5; `tests/cli/test_storage_growth.py`; V1.1–V1.4. |
| Steps 2 and 3 add per-cycle rows (`heartbeats`, `monitor_cycles`, `notification_decisions`) that count against the 128 KiB growth test. | Downstream note | Added carry-over notes in Steps 2 and 3 task blocks to re-measure `test_storage_growth.py` (stayed 64 KiB in both). | `tests/cli/test_storage_growth.py`; V1.3. |
| Pre-`0004` snapshots must still load equal after upgrading, and downgrading `0004 -> 0003` must not lose post-`0004` snapshots. | Correctness rule | `SnapshotRepository` reads from `snapshot_geometries` when `snapshot_provenances` rows exist for the snapshot and from `product_geometries` otherwise; `0004` downgrade copies linked rows back into `product_geometries` before dropping the new tables. | `tests/services/test_geometry_storage.py`; `tests/services/test_database.py`; V1.2 and V1.4. |

## Step 2 — The monitor cycle, the heartbeat, and staleness

Source: [PR #42](https://github.com/nathanramoscfa/weatherbot/pull/42).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Overlapping SQLite writers under default deferred transactions fail immediately with `database is locked` instead of waiting for `busy_timeout`. | Correctness rule | `writing_session` sets `BEGIN IMMEDIATE` via SQLAlchemy execution options and a 30,000 ms `busy_timeout`; `open_database` takes `migrate.lock` when behind the Alembic head. | Static checks 6 and 9; `tests/services/test_writing_transactions.py`; V2.1 and V2.2. |
| Manual CLI commands (`fetch`, `storms`, `alerts`, `status`, `check --once`) must not set `expected_every_s`, or a one-off run would become stale 6 hours later. | Correctness rule | `MonitorService.run_cycle` accepts `cadence_s: int | None = None`; manual runs pass `None`, which preserves any existing `expected_every_s` on the heartbeat row. | Static checks 8 and 10; `tests/services/test_monitor.py`; V2.2 and V2.3. |
| Cycle failures must record the exception class name on `monitor_cycles.error_kind`, never the raw exception message (which can contain a URL or coordinate). | Security control | `MonitorService.run_cycle` catches `BaseException`, records `type(exc).__name__`, commits the failed cycle row, and re-raises. | `tests/services/test_monitor.py`; V2.2 and V7.3. |
| The Windows CI test job reached 18m15s against its 25-minute timeout. | Process note | Step 4 shared the eight replay timelines in `tests/engine/ladder_data.py` (`replay_timelines()`), cutting 33 seconds from the suite. | `ci.yml` `test (windows-latest)`. |

## Step 3 — The notification policy and the notification log

Source: [PR #43](https://github.com/nathanramoscfa/weatherbot/pull/43).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| When a level drop was held while another trigger (`advisory_issued` or `alert_changed`) fired in the same cycle, using `assessment.level` in the notification title and quiet-hours check showed the unconfirmed lower level ("level 1, All Clear" during an active Hurricane Warning). | Implementation bug, fixed in-step | `decide` uses the effective announced level (`announced_level` while a drop is held) for the notification's `level`, title, and quiet-hours check. Step 3 task block and `docs/ALERT-LADDER.md` amended. | `tests/services/test_policy.py`; V3.1. |
| The Irma notification goldens (`AL112017-miami-dade.json` and `AL112017-nassau.json`) required explicit operator review and approval. | Operator approval (2026-10-22) | Approved by the operator at review SHA-256 `df7c5f869bcdca8b85a44b347012c5641625fade51f22780e5b11d34d93be717`; frozen in `tests/golden/notifications/`. | Static check 20; `scripts/build_notification_goldens.py --check`; V3.3. |
| Rerunning `NotificationService.decide_cycle` over an already-decided assessment must not emit duplicate decisions or notifications. | Correctness rule | `notification_decisions` is unique on `(assessment_id, trigger, change_position)` and skips assessments already recorded. | Static check 18; `tests/services/test_notification_replay.py`; V3.2. |
| An `advisory_issued` change-event detail from Phase 3 reads `"whose cone does not."` when the location is outside the cone. | Non-blocking wording defect | Tracked as [issue #44](https://github.com/nathanramoscfa/weatherbot/issues/44) (Pre-ship items). | Issue #44. |

## Step 4 — The Windows toast channel

Source: [PR #46](https://github.com/nathanramoscfa/weatherbot/pull/46).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| `pip-audit --strict` flagged six CVEs in `filelock 4.1.1` (a transitive dev dependency of `pre-commit` / `virtualenv`). | Security finding, fixed in-step | Separate `fix(deps)` commit in PR #46 upgrading `filelock` to `4.2.4` in `uv.lock`. | `scripts/audit_deps.py`; V7.4. |
| `winrt-*` wheels exist only for Windows (`sys_platform == 'win32'`), so importing them unconditionally or checking types only on Linux would either break Ubuntu or leave Windows-only code unchecked. | Cross-platform design | All five `winrt-*` packages carry `sys_platform == 'win32'` markers in `pyproject.toml`, `toast.py` imports `winreg` and `winrt` behind `if sys.platform == "win32":` (loading `winrt` lazily on first toast), and `.github/workflows/ci.yml` runs `typecheck` on both `ubuntu-latest` and `windows-latest`. | Static checks 22, 23, and 27; `tests/services/test_toast.py`; V4.1–V4.3. |
| Ordinary tests must never pop a real toast or touch `HKEY_CURRENT_USER`. | Test isolation rule | `tests/conftest.py` sets `WEATHERBOT_NOTIFICATIONS_TOAST=false`, `Runtime` provides `make_toast` and `identity` seams, and the real toast test (`tests/desktop/test_toast_desktop.py`) is marked `desktop` and deselected by default. | Static check 26; `tests/test_conftest_guards.py`; V4.2 and V4.3. |
| `NotificationService` default channels in service unit tests vs CLI commands. | Spec rot, fixed in-step | `NotificationService` defaults to `(LogChannel(),)` so service tests never touch `ToastChannel`; `cli/runtime.py` wires `(LogChannel(), toast_channel)` for every CLI command. Step 4 task block annotated ("As shipped (PR #46)"). | Static check 24; `tests/services/test_toast.py`; V4.1. |

## Step 5 — The scheduler, `serve`, and `check`

Source: [PR #49](https://github.com/nathanramoscfa/weatherbot/pull/49).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| `random.Random()` triggers Ruff `S311` and Bandit `B311` in `src/weatherbot/services/scheduler.py`. | Security gate compliance | `Scheduler` defaults to `secrets.SystemRandom()` while accepting any injected `Random` in deterministic tests. | `tests/services/test_scheduler.py`; Bandit gate; V5.1 and V7.4. |
| Under `pythonw.exe`, `sys.stdout` and `sys.stderr` are `None`, so any stream handler or library write to `sys.stderr` fails. | Windows background execution | `configure_logging` redirects `None` `sys.stdout`/`sys.stderr` to `os.devnull` (closed via `atexit`) and attaches only the rotating `weatherbot.log` file handler (`1_048_576` bytes, 5 backups, `UtcFormatter`, `RedactingFilter`). | Static check 34; `tests/services/test_log_file.py`; V5.3. |
| When a newer checkout upgrades `weatherbot.sqlite3` past the installed tool's Alembic head, the background monitor cannot open the database to log a notification. | Operational resilience | `open_monitor_session` in `cli/runtime.py` catches `DatabaseError` from `open_database`, logs it to `weatherbot.log`, sends a database-free toast via `deliver_database_refused_toast`, and exits `1`. | Static check 35; `tests/services/test_database_refused.py`; V5.3. |
| A cleanly stopped `serve` or `check` would look stale to `status` and `doctor` after twice its 5-minute cadence if `expected_every_s` remained set. | Correctness rule | `clear_runner_heartbeat_cadence` sets `expected_every_s = None` on the runner's `heartbeats` row in a `finally` block on clean stop. | `tests/cli/test_serve_command.py`; V5.3. |

## Step 6 — Task Scheduler and health

Sources: [PR #50](https://github.com/nathanramoscfa/weatherbot/pull/50) and
[PR #51](https://github.com/nathanramoscfa/weatherbot/pull/51).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Windows PowerShell 5.1 `Get-ScheduledTask` serializes `Principal.LogonType` and `Principal.RunLevel` as numeric enum values (`3` -> `Interactive`, `0` -> `Limited`), whereas Task Scheduler 1.2 XML spells them `InteractiveToken` and `LeastPrivilege`. | Windows platform quirk, fixed in PR #51 | `weatherbot.services.tasks.query` normalizes `Interactive` -> `InteractiveToken` and `Limited` -> `LeastPrivilege` so `doctor`'s `tasks` check and `InstallTaskData` see a single canonical vocabulary. | `tests/services/test_tasks.py`; `tests/desktop/test_tasks_desktop.py`; V6.1 and V6.4. |
| On 2026-10-24 (no active storms), NHC's live `nhc-map-tropical-summary` 50 kt wind-speed probability layer served a degenerate feature with `"percentage": "<5%"` and `"geometry": null`, which `parse_wind_probabilities` rejected as a `SchemaDriftError`. | Source drift, fixed in PR #51 | `parse_wind_probabilities` in `src/weatherbot/sources/nhc_map.py` skips features whose `geometry` is `None` after reading `percentage` and `idp_source`, matching `scripts/fetch_replay_corpus.py`'s `shapefile.NULL` handling. | `tests/sources/test_nhc_map.py`; `tests/live/test_monitor_live.py`; V6.3. |
| When a machine wakes from sleep and `\Weatherbot\check` fires immediately (`StartWhenAvailable`), `serve` may still be mid-cycle before its runner heartbeat updates. | Operational race condition | `run_fallback_check` (`check --once --if-stale`) polls up to `FALLBACK_WAIT_S = 180.0` seconds (every `5.0` seconds) while `monitor.lock` is held before declaring `serve` stale. | Static check 42; `tests/services/test_fallback.py`; V6.2. |
| Repeated hourly fallback runs during a prolonged `serve` outage must not spam `stale_monitor` toasts every hour. | Notification policy rule | `run_fallback_check` latches `STALE_MONITOR_NOTIFIED_KEY` (`"1"`) in `app_settings` after sending the first `stale_monitor` notification and clears it only when `serve` is seen fresh again (and `run_heartbeat_task` clears it whenever `serve` writes a fresh heartbeat). | `tests/services/test_fallback.py`; V6.2. |
| `doctor` in tests or scratch directories with `WEATHERBOT_DATA_DIR` set must not fail because the operator's machine-global tasks or `PATH` differ. | Test isolation rule | `doctor` skips the machine-global `tasks` and `path` checks (and the installed-`serve` requirement in `heartbeat_check`) when `WEATHERBOT_DATA_DIR` overrides the default data directory. | Static check 44; `tests/services/test_doctor_machine.py`; V6.3. |
| On the operator's machine, `weatherbot` on `PATH` resolves to retired v1.0.0 (`C:\Users\Admin\AppData\Local\Programs\Python\Python311\Scripts\weatherbot.exe`) ahead of `~/.local/bin\weatherbot.exe`. | Operator environment finding | Surfaced as designed by `doctor`'s new `path` check; recorded in Pre-ship items for the operator's `PATH` housekeeping, while `verify_phase04.py --post` V6.5 verifies the installed `~/.local/bin/weatherbot` directly (`settings`, `database`, `migrations`, `heartbeat`, `toast`, and `tasks` all `pass`). | `tests/services/test_doctor_machine.py`; V6.3 and V6.5. |

## Step 7 — Verification and closure

Source: [PR #52](https://github.com/nathanramoscfa/weatherbot/pull/52).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Phase 4's `--post` sweep spans three pytest suites (`offline` with engine and policy branch-coverage floors, `live`, and `desktop`) plus `scripts/simulate_advisory.py`, Phase 3's `--post`, the installed tool's `doctor --offline --json`, a synthetic stale-heartbeat alarm proof, and Task Scheduler readbacks. | Verification design | `scripts/verify_phase04.py` runs 51 static checks and the 29-row V1–V7 matrix (`(4, 5, 4, 3, 4, 5, 4)` = 80 total in `--post`). Every `Select` must match at least one test, any failed or skipped test prevents `PASS`, and `Select(..., without=...)` excludes only the two OS-permission-dependent skips (`a_link_out` and `refuses_world_accessible`). | Static checks 47–51; `tests/test_phase04_verification.py`. |
| Revision `0006_notifications.py` was not yet in `tests/services/test_database.py`'s `FROZEN` hash table. | Upstream gap, fixed in-step | Added `"0006_notifications.py": "88ad27ba143120845fb027270935cd617f8120f970c307fa85fb5d4b6400ee69"` to `FROZEN` in `tests/services/test_database.py`, enforced by static check 19. | Static check 19; `tests/services/test_database.py`. |
| Later phases (5–8) will add migrations, settings, JSON Schemas, and web server wiring in `serve`. | Downstream integration requirement | Checks 4, 14, 15, 19, 22, 29, 45, and 49 and V7.1 use inclusion (`<=`), and V2.5 checks `descends_from(head, "0006")`. The seven exact checks (8, 17, 20, 36, 40, 43, 46) are documented in `ROADMAP.md`'s Phase 5 section and in Pre-ship items below so any future step that deliberately widens them converts them to read `v2.0.0-phase-4` in the same PR. | `ROADMAP.md` Phase 5 note; `tests/test_phase04_verification.py`. |
| A static check that never turns red when its deliverable breaks proves nothing. | Verification integrity | `test_a_changed_deliverable_turns_exactly_its_check_red` in `tests/test_phase04_verification.py` mutates deliverables across Steps 1–6 in memory and requires only the targeted static check to fail. | `tests/test_phase04_verification.py`. |

## Source-drift observations

Every observation of a live NOAA or NWS source differing from the register or
recorded fixtures during Phase 4, and where it went:

- **2026-10-21 (Step 1 / Step 2 live runs):** Tropical Storm Josephine (`AL102026`)
  and Hurricane Vance (`EP222026`) were active; all live source clients and
  `MonitorService.run_cycle` parsed their advisories, cones, arrival KMZs, and
  wind-speed probabilities without drift warnings.
- **2026-10-24 (Step 6, PR #51):** With no active storms in the Atlantic,
  Eastern Pacific, or Central Pacific basins, NHC's live
  `nhc-map-tropical-summary` 50 kt cumulative wind-speed probability layer
  returned a single placeholder feature with `"percentage": "<5%"` and
  `"geometry": null`. Fixed in PR #51 (`parse_wind_probabilities` skips
  null-geometry band features after reading `percentage` and `idp_source`,
  matching the replay archive converter's `shapefile.NULL` handling) and
  guarded by `test_wind_probability_parser_skips_null_geometry_band_feature` in
  `tests/sources/test_nhc_map.py`.

## Live smoke runs

`pytest -m live` runs in `--live`, `--all`, and `--post` against the two public
landmarks in a temporary data directory:

- Step 2 (2026-10-22, PR #42): `tests/live/test_monitor_live.py` and
  `tests/live/test_cli_live.py` passed on `main` at `7bea5ca`.
- Step 3 (2026-10-22, PR #43): live `check --once` with both public landmarks
  in a temporary data directory stored 8 decisions, 1 notification, and 1
  `log`/`delivered` delivery.
- Step 6 (2026-10-24, PR #51): `uv run pytest -m live tests/live/test_monitor_live.py`
  passed (16.71 s), and full `uv run pytest -m live` runs inside `verify_phase04.py --post`
  (V2.4 and V6.3).

## Pre-ship items

These are documented limitations and downstream owners, with no unassigned
finding:

| Item | Owner / destination | Required next action |
| --- | --- | --- |
| On the operator's machine, `PATH` resolves `weatherbot` to retired v1.0.0 (`C:\Users\Admin\AppData\Local\Programs\Python\Python311\Scripts\weatherbot.exe`) ahead of `~/.local/bin\weatherbot.exe`. | The operator | Put `%USERPROFILE%\.local\bin` ahead of `Python311\Scripts` on the user `PATH`, or uninstall the retired `weatherbot 1.0.0` copy from Python 3.11, then confirm `weatherbot doctor --offline` reports `path: pass`. |
| `weatherbot serve` currently runs the scheduled monitor only; the FastAPI web app and SSE stream join `serve` in Phase 5. | Phase 5 (`phase05-roadmap.md`) | Host FastAPI + `/api/events` alongside `run_monitor` in `serve`, keeping `ProcessLock` and `run_monitor` in `cli/serve.py` (or converting `verify_phase04.py` check 36 to read `v2.0.0-phase-4` in that PR). |
| Seven `verify_phase04.py` checks are exact: check 8 (`CycleTrigger`), check 17 (`DECISION_KINDS`), check 20 (`IRMA_NOTIFICATION_GOLDENS`), check 36 (`cli/serve.py` calling `ProcessLock` and `run_monitor`), check 40 (`TASK_NAMES`), check 43 (`NOTIFICATION_KINDS`), and check 46 (`README.md` `## Status` naming Phase 4 complete and Phase 5 next). | Phase 5–8 (`ROADMAP.md` Phase 5 note) | When Phase 5 updates `README.md`'s `## Status`, convert check 46 in the same PR to read `v2.0.0-phase-4:README.md`; if any later step widens the other six constants, convert that check to read `v2.0.0-phase-4` in the same PR. |
| Claude Sonnet 5.5 briefing and change narration over stored assessments and change events. | Phase 6 | Read stored assessments, evidence, and change events; never let model output change a level or trigger a notification. |
| Phone push notifications (`ntfy`), UI quiet-hours and per-location notification settings, and `geometry_contents` retention cleanup. | Phase 7 | Implement the `ntfy` `Channel`, settings UI, and retention pruning of unreferenced `geometry_contents` rows. |
| Issue #44 (`advisory_issued` detail wording `"whose cone does not."` when outside the cone). | [Issue #44](https://github.com/nathanramoscfa/weatherbot/issues/44) | Fix on its own `fix/` branch in a dedicated session (with a fresh golden review if timeline text changes). |
| Whether a storm-surge watch or warning, or an extreme-wind warning, moves the ladder. | The operator, [issue #33](https://github.com/nathanramoscfa/weatherbot/issues/33) | Decide; a change to the ladder needs a fresh golden review and closes #33 with its decision comment. |
| The milestone tag `v2.0.0-phase-4` is not a PyPI release; the package version stays `2.0.0.dev0`. | Phase 8 | Release readiness gate and OIDC trusted publishing to TestPyPI and PyPI. |
| Dependency updates #8, #30, and #31. | Dependabot PRs | Independent maintenance; not folded into a phase step. |

Run `uv run python scripts/verify_phase04.py --post` for the canonical
51 static + 29 V-check sweep. `--fast` is offline and standard-library only;
`--py`, `--live`, `--security`, and `--all` provide the same suites independently.
