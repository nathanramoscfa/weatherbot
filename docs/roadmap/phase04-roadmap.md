# Phase 4 Roadmap — Monitoring and notifications

**Status:** In progress

## Overview

Phase 4 opens the gate between a decision and the operator. Weatherbot starts
running unattended on the operator's Windows machine: it fetches the official
products on NHC's own schedule, assesses every stored location, stores the
result, and tells the operator what changed through a Windows toast and an
in-app log, under a policy that never holds back an escalation. Task Scheduler
starts it at logon and checks on it every hour, and its health — a heartbeat per
source and per process, a staleness rule, and two alarms — shows in `status` and
`doctor`. It does not serve a page or push events to a browser (Phase 5, which
subscribes to this phase's cycle events), write a briefing (Phase 6), reach a
phone through ntfy or offer per-location notification preferences in a settings
page (Phase 7), or publish a release (Phase 8). The work is one phase because
the schedule, the policy, and the channels are one contract with the operator: a
notification is only as good as the cycle that found the change, and a cycle
that runs at 3 a.m. is only as good as the alarm that says when it stopped.

The phase lands in 7 layers:

1. **Snapshot storage that stays small** — Alembic revision `0004` stores each
   product geometry's content once, by its SHA-256, compressed like the response
   bodies, and each response's provenance once per snapshot;
   `SnapshotRepository` writes every new snapshot that way and reads snapshots
   stored before the revision as they are. A second cycle over unchanged answers
   grows the database by less than 128 KiB, where today it grows by 2.0 MiB.
2. **The monitor cycle, the heartbeat, and staleness** —
   `weatherbot.services.monitor.MonitorService.run_cycle`, the one path that
   fetches, stores, assesses, and records; a cycle lock shared by every process;
   revision `0005` with the `heartbeats` and `monitor_cycles` tables; the
   staleness rule and its banner in `status`; heartbeat lines in `doctor`;
   `weatherbot check --once`; `weatherbot config show` and `config path`.
3. **The notification policy and the notification log** — the pure policy in
   `weatherbot.services.policy`, which announces levels against the last
   announced level, sends escalations at once, holds a drop that may be an
   artifact until a second fetch confirms it, applies the cooldown and quiet
   hours to everything else, and groups one notification per location per cycle;
   revision `0006` with the notification, decision, and delivery tables; the
   in-app log channel and `weatherbot notify log`; and Irma's notification
   timelines at both landmarks, reviewed once by the operator and frozen under
   `tests/golden/notifications/`.
4. **The Windows toast channel** — the toast channel behind Step 3's `Channel`
   interface, over pywinrt's `winrt-Windows.UI.Notifications`; the application
   identity Windows needs for an unpackaged app, registered by `weatherbot
   notify setup`; an honest delivery result (delivered, failed, disabled, or
   unavailable); a no-op channel off Windows; and `weatherbot notify test`.
5. **The scheduler, `serve`, and `check`** — a small asyncio scheduler in
   `weatherbot.services.scheduler` that opens a fetch window after each of NHC's
   fixed UTC product times, watches the storm roster, polls NWS alerts only
   while a storm is relevant to a location, retries a failed cycle, and catches
   up after the machine sleeps; `weatherbot serve` and `weatherbot check`,
   single-instance; a rotating log file; the degraded-data alarm; and a
   simulated new advisory that raises a toast on the operator's machine within
   one scheduler interval.
6. **Task Scheduler and health** — `weatherbot install-task` and
   `uninstall-task` for a `serve` task at the operator's logon and an hourly
   `check --once --if-stale` fallback, both run as the operator with no stored
   credential and no console window; the stale-monitor alarm the fallback
   raises; and `doctor` reporting both tasks, the installation they run, and the
   heartbeat.
7. **QA + `verify_phase04.py`** — `scripts/verify_phase04.py` (`--fast`, `--py`,
   `--live`, `--security`, `--all`, `--post`), `docs/phase04-qa-findings.md`,
   and matrix entry `"04"` beside `"01"`, `"02"`, and `"03"` in
   `phase-verify.yml`; Phase 4 closed in this roadmap and the project roadmap;
   the `v2.0.0-phase-4` tag.

The ship test for Phase 4 is straightforward: a second monitoring cycle over
unchanged answers grows the database by less than 128 KiB and every snapshot
stored before revision `0004` still loads back equal; replaying Irma through the
monitor's policy equals the four operator-approved notification timelines (two
landmarks, under the defaults and under strict settings), every escalation of
the eight replays is sent even under a 24-hour cooldown with quiet hours all
day, and an event re-presented inside the cooldown is a repeat; the staleness
rule fires under a frozen clock and shows in `status`; `notify test` raises a
toast on the operator's machine and records its delivery; a simulated new
advisory during `serve` raises a toast within one scheduler interval, and its
notification row records the delivery; after `install-task`, Task Scheduler
shows both tasks, `doctor` reports them and a fresh heartbeat, and a forced task
run writes a new assessment; the degraded-data and stale-monitor alarms have
each been seen to fire; no notification text holds a coordinate, a distance, a
bearing, or a key; Phase 1's, Phase 2's, and Phase 3's verification still pass
unchanged; and `scripts/verify_phase04.py --fast` exits 0 on Ubuntu CI with
`phase-verify (01)`, `(02)`, `(03)`, and `(04)` green.

**Pre-requisite:** Phase 3 closed on 2026-10-20 (PR #38, `v2.0.0-phase-3`). Its
pure `assess` with calibrated thresholds, its typed change events from `diff`,
and its `AssessmentService`, which stores each assessment with its changes once
per snapshot, are what the monitor runs every cycle; its incomplete assessments
are what the staleness banner and the policy's held drops build on; and its
eight frozen golden replays are the timelines this phase's notification goldens
are derived from. Phase 2's snapshot service, persistence, conditional fetcher,
and commands are what the cycle composes, and Phase 1's gate, required checks,
socket guard, and working-directory guard are what every Phase 4 commit runs
under. The planning kit is roadmodel 0.2.88: PR #39 refreshed it on 2026-10-21,
before this roadmap, with the matching lock bump.

**Dependency:** Phase 5 does not start until Phase 4's V-checks are green. Its
FastAPI app runs inside the same `serve` process, subscribes to the monitor's
cycle events for its server-sent events, serves the heartbeat and the
notification log, and shows the staleness banner; Phase 6's change summary reads
the stored change events and decisions; and Phase 7 adds ntfy as a second
channel behind the same interface, per-location notification preferences over
the same policy, and retention over the storage this phase made small.

**Design rationale (decisions and clarifications of the brief and the project
roadmap).** Fifteen decisions, each made against recorded or measured evidence
while this roadmap was written (2026-10-21). The project roadmap records each
one that changes it, in this roadmap's own pull request. Step agents treat them
as settled spec unless the operator changes them.

- *A scheduled monitor must not grow the database by megabytes per cycle.*
  Measured on 2026-10-21 by running `status` four times over the recorded
  2026-10-12 answers (one active storm, two landmarks) in a temporary data
  directory, with a WAL checkpoint before each size: the first cycle added 3.1
  MiB and every later one 2.0 MiB, although every answer was byte-identical,
  because `product_geometries` stores all 608 geometry rows of every snapshot
  again. Per snapshot they hold 1.85 MiB: the three wind-speed probability
  products 1.2 MiB, the wind radii 196 KiB, and the static breakpoint catalogue
  333 KiB, of which 242 KiB is one response's provenance repeated on each of its
  549 points; the response bodies themselves are already stored once
  (`response_bodies`). Eight window cycles a day would add about 6 GB a year.
  Revision `0004` stores each geometry's content once by hash and each
  response's provenance once per snapshot, so an unchanged cycle adds link rows
  only. It is expand-only: nothing references `product_geometries`, its rows
  stay readable as they are, and moving them waits a release.
- *The monitor runs one kind of cycle, and never a snapshot of some sources
  only.* A cycle fetches every source, stores the snapshot, assesses every
  location through `AssessmentService`, and records the heartbeat; it is the
  only path that assesses. The scheduler's light polls (the roster and the cone
  layer, and NWS alerts while a storm is relevant) only decide when to run one.
  A snapshot that left a source out would lie: the engine names a *failed*
  source as an unavailable input, but a *skipped* one is not, so a level read
  from it would look complete when it was not. One cycle costs 41 + 4S + 3L
  requests for S active storms and L locations inside NWS coverage (48 and 2.4
  MB measured for one storm and one US location), most of them conditional.
- *Fetch windows follow NHC's fixed UTC schedule.* NWS Instruction 10-607
  (2026-08-17) fixes the routine advisories at 0300, 0900, 1500, and 2100 UTC
  and the intermediate advisories and the Tropical Weather Outlook at 0000,
  0600, 1200, and 1800 UTC, the same in UTC when daylight time ends (Sunday
  2026-11-01), and puts the wind-speed probabilities "no earlier than 15 minutes
  following the issuance deadlines". Measured at three advisories: the cone's
  file date was 8 minutes after the nominal time on 2026-10-12 (21:08:17 for
  21:00), and on 2026-10-21 4 minutes after (15:04:09, ingested 15:05:57, for
  Twenty-Two-E's 15:00 advisory 1) and 9 minutes after (21:08:41, ingested
  21:09:42, for Vance's 21:00 advisory 2, with the new Atlantic storm
  Josephine's advisory 1 filed at 21:08:40); `CurrentStorms.json` was rewritten
  24 minutes after the first two (21:24 and 15:24) but 8 minutes *before* the
  third (20:52), already naming both 21:00 advisories. The roster can lead the
  map service or trail it, so a window opens 15 minutes after each of the eight
  product times, plus a random delay of up to 2 minutes; every 5 minutes (the
  roster's `max-age` is 300 s, and a conditional request returns 304) it reads
  the roster and the summary service's cone layer (advisory numbers only, no
  geometry) until every listed storm has a public advisory issued at or after
  the product time and the cone layer shows that advisory, or until 60 minutes
  after the product time; and then runs one full cycle. With no storm it runs at
  once. Nothing in code names a season: the schedule is the same all year, and
  off-season windows simply find nothing new.
- *The light polls are cheap and polite.* The roster is polled every 15 minutes,
  every 5 while a storm is relevant, with conditional requests; a change in its
  storms or their advisories (a special advisory, a new system) runs a full
  cycle. NWS alerts are polled only while a storm is relevant — some US
  location's latest assessment is above All Clear — every 5 minutes, three
  requests per US location at the client's 1.2-second pacing; the NWS alerts
  documentation recommends no more than one request every 30 seconds (the API's
  own rate limit is not public), and on 2026-10-21 its alert endpoints answered
  a matching `If-None-Match` with 200 and the full body, so the poll compares
  alert ids and `sent` instants with the latest stored snapshot instead, and a
  difference runs a full cycle. The watches share one in-memory roster answer
  for 60 seconds, so no two of them fetch it within a minute, and a poll's
  answers are never stored: the full cycle fetches again.
- *A small asyncio scheduler, not APScheduler.* The project roadmap's section
  4.1 names APScheduler. Checked on 2026-10-21: APScheduler 3.11.3 (2026-06-28)
  ships no `py.typed` and has no stub package, so strict pyright rejects it; the
  fix for `AsyncIOScheduler` permanently stopping every job after one exception
  in its job loop (PR #1132) was merged on 2026-08-31 and is unreleased; a long
  wait can overshoot after the machine sleeps (issue #794, open), and the
  default misfire grace of one second then drops the run; and 4.0 is still the
  alpha 4.0.0a6, whose README says not to use it in production.
  `weatherbot.services.scheduler` is about 150 lines instead: it sleeps at most
  60 seconds at a time and compares due times with the UTC wall clock, so a
  sleep, a resume, or a clock change costs at most a minute; it runs one job at
  a time and skips a job still running; it isolates and logs every job's
  failure; it adds positive random delay; and it runs one coalesced catch-up
  cycle after a gap. A fake clock tests it deterministically. This PR amends the
  project roadmap's 4.1.
- *The policy announces levels, against the last announced level.* For each
  location the policy keeps the announced level — the level its last level
  decision settled — and the assessment that set it. A higher level is an
  escalation: sent at once, never held by the cooldown or quiet hours, even when
  the assessment is incomplete, because a floor that is higher is still higher.
  A lower level is a drop, sent under the cooldown and quiet-hours rules unless
  it may be an artifact of the fetch: when its assessment names an unavailable
  input that the announcing assessment did not name (a source failed this
  cycle), or when it came with no new advisory for any storm while no official
  product that covered the location in the announcing assessment has passed its
  own `expires`. Such a drop is *held*: not sent, and the monitor runs a
  confirmation cycle 5 minutes later. The next assessment settles a held drop.
  Back at the announced level or above, the drop is withdrawn. Still lower with
  no newly unavailable input, it is decided as a drop (the no-advisory test
  never holds the same drop twice). Still lower with an input still unavailable,
  it is held again, at most three times, and then announced as a floor ("fell to
  at least 3") while the degraded-data alarm says why. A fetch that fails, or a
  map layer caught mid-update, and recovers within those confirmations therefore
  never sends "fell to 3" and then "rose to 5". Measured on the eight replays
  under the same rule: no step is held, because every replay step is a new
  advisory with the same inputs, so replay notifications follow `diff`'s level
  events exactly.
- *The other triggers, and the rest of brief §9.* An advisory for a storm whose
  cone covers the location, a cone entered (which brief §9 does not name: the
  cone can arrive a cycle after its advisory, when no advisory event remains to
  carry it), and an official product that covers the location added or replaced
  each send a notification; a product removed and a cone left are recorded and
  shown, and a drop they cause is announced as a drop. The cooldown suppresses
  only a repeat of the same event — the same drop, the same advisory, the same
  cone, the same product — within 6 hours, one full advisory period; an NWS
  alert keeps its key across updates that keep its codes, so a same-code update
  inside the cooldown is a repeat, while a watch upgraded to a warning is not;
  measured, no identical non-escalation event repeats within 12 hours in any of
  the eight replays (Dorian at Nassau repeats "fell from 3 to 2" after 18), so
  the default suppresses nothing historical and absorbs live flapping. Quiet
  hours are off by default; when set, they hold back only non-escalations at
  levels 1 and 2. One notification per location per cycle carries every sent
  trigger. Measured with the defaults: Irma at Miami-Dade sends 38 notifications
  (4 escalations, 3 drops, 34 in-cone advisories, 1 cone entered, 3 official
  products), Irma at Nassau 25 (6 escalations, among them a second 2-to-3 twelve
  hours after the first, 3 drops, 20 advisories, 2 cones, 4 official products);
  all 29 escalations of the eight replays are still sent under a 24-hour
  cooldown with quiet hours all day. Quiet hours are implemented here because
  the policy is one rule; Phase 7 adds their settings page and per-location
  preferences and proves them through ntfy.
- *Notification text names; it never locates.* A notification names the
  location, its level and its label, the deciding rule's trigger, storm names,
  advisory numbers, and product codes, and carries the disclaimer's notice line,
  because a toast that shows a level is an assessment surface. It never holds a
  coordinate, a distance, a bearing, an arrival instant, or a key: a distance
  and a bearing from a public storm center locate the operator's home as surely
  as its coordinates do, and a toast shows on the lock screen.
  `ChangeEvent.detail` already holds names and codes only.
- *One maintained toast layer: pywinrt.* Checked on 2026-10-21:
  `winrt-Windows.UI.Notifications` 3.2.1 (MIT) ships typed stubs and CPython
  3.13 wheels, reads Windows' notification setting for the app (enabled, or
  disabled for the application, the user, group policy, or the manifest), and
  reports a failed toast with its HRESULT. desktop-notifier swallows failures
  and writes the registry on construction; Windows-Toasts has had no release
  since May 2025; winsdk is archived and has no 3.13 wheels; win11toast pulls in
  twelve WinRT namespaces; winotify starts PowerShell per toast. Its application
  identity lives under `HKEY_CURRENT_USER`, written only by
  `register_identity()`, which `notify setup` and `install-task` call explicitly
  and idempotently — never as a side effect of sending — with no administrator
  rights. The packages carry `sys_platform == 'win32'` markers like `tzdata`,
  and a no-op channel answers elsewhere.
- *Unattended on Windows, with no stored credential and no window.* The
  operator's account is an administrator under UAC whose shells run at medium
  integrity, on Windows 11 build 26200 (checked 2026-10-21). Two 2026 reports on
  Windows 11, one on that build, show `schtasks /Create /SC ONLOGON` refused
  without elevation, because it triggers on any user's logon, and a task whose
  `LogonTrigger` names the current user registering unelevated from task XML;
  Step 6's desktop test proves that on this machine before anything depends on
  it. Both tasks run as the operator with `InteractiveToken` and
  `LeastPrivilege` ("run only when the user is logged on"), so no password is
  stored and toasts reach the operator's desktop; they launch `pythonw.exe`, so
  no console window opens; `serve` has no time limit and ignores battery power.
  The task XML and the toast XML are written as escaped string templates,
  because Phase 2's check 20 forbids every standard-library XML module in the
  package, and task state is read as JSON from one PowerShell call, never from
  `schtasks`' localized text.
- *Health has a consumer.* The `heartbeats` table holds, per source and per
  monitor process, the last attempt, the last success, the run of consecutive
  failures, and the cadence its writer expects; a row is stale when its last
  success is older than twice that cadence. `status` shows a staleness banner
  and `doctor` a line per row. After a cycle in which a source the ladder reads
  failed, the scheduler retries 5, then 10, then 20 minutes later, one series
  per run of failures, so the degraded-data alarm — a toast and a log entry when
  such a source fails 3 times in a row, the project roadmap's TBD — fires about
  15 minutes into a failure, once, with a recovery entry when the source answers
  again. When the database is at a revision newer than the running code (a
  checkout migrated it past the installed copy), the monitor says so in a toast
  that needs no database, because both alarms store their notifications in it.
  The hourly fallback is the stale-monitor alarm's consumer: when no monitor
  holds its lock (which the operating system frees when the process dies), or
  the one that does has stopped writing its heartbeat, it says so in a toast and
  the log and runs the cycle itself; a monitor that just woke with the machine
  gets three minutes to write its heartbeat first, so a resume never raises the
  alarm.
- *Phase 3's checks stay green as written.* Check 32 reads exactly the seven
  change kinds, and this phase adds none: staleness, held drops, decisions, and
  deliveries are heartbeat, policy, and notification records, never change
  events. Check 33 reads exactly the eight files in `tests/golden/replay/`, so
  the notification goldens live in `tests/golden/notifications/`. The project
  roadmap's Phase 4 note says Phase 3's threshold checks read inclusion; check
  38 in fact requires `Thresholds` to hold exactly the six thresholds, so every
  Phase 4 setting lives in a new `Settings` table, and this PR corrects the
  note. Phase 2's check 31 already reads its tag, so the new tables are safe,
  and `doctor --offline` on a fresh database must still exit 0 for both alarm
  proofs: every new `doctor` check reads `skip`, never `fail`, until there is
  something to judge.
- *`check`, `check --once`, `serve`, and `config`.* `check --once` runs one
  cycle and exits with `status`'s exit code; it is the manual check on demand
  and, with `--if-stale`, the hourly fallback. `check` runs the scheduler in the
  terminal, and `serve` runs the same scheduler as the long-lived process Task
  Scheduler starts and Phase 5 adds its web server to; only one of them runs at
  a time. `config show` prints every setting's effective value and where it came
  from (default, file, or environment), and `config path` prints where the file
  and the data live; Phase 3 left the `config` command to this phase.
- *The operator's machine has two version 1 installations on `PATH`.* Found on
  2026-10-21: a retired virtual environment outside the checkout holds version
  1.0.0 and sits ninth on `PATH`, ahead of `~/.local/bin` (35th), and the system
  Python 3.11 holds another. Typing `weatherbot` after installing version 2
  would therefore run version 1. The tasks run an absolute interpreter path,
  never a name looked up on `PATH`, `doctor` says which installation a bare
  `weatherbot` resolves to, and Step 6 tells the operator how to remove the
  shadow; removing it is the operator's housekeeping, outside git.
- *The tasks run an installed copy; the version stays `2.0.0.dev0`.*
  `install-task` registers the interpreter it runs under. The operator installs
  a copy with `uv tool install --from <checkout> weatherbot` and reinstalls it
  after a merge that changes the monitor, because the checkout's `.venv` follows
  whatever branch is checked out. The package version stays `2.0.0.dev0` until
  the release candidate in Phase 8; the milestone tag marks the phase.

**Branch strategy.** Every step in this phase lands on its own short-lived
feature branch (`feature/phase04-step<M>-<slug>`), opens a pull request against
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
git checkout -b feature/phase04-step<M>-<slug>
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
feature/phase04-step<M>-<slug> <worktree-path> origin/main`, the worktree is
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
(injection, a subprocess built from a shell string, unsafe deserialization, a
path read outside the directory it names, a coordinate or a location's distance
and bearing in a log line above DEBUG or in a notification). The gate is wired
into the pre-commit hook and re-run in CI, so a security issue introduced while
implementing a step is caught during development — before it reaches the branch,
the PR, or `main`. See the project roadmap's "Security & privacy strategy" →
"Per-step security gate" for the canonical checks and tooling; each step's XML
`<task>` carries a `<security>` block restating them for the agent, and each
step's Acceptance Criteria ends with a security check. AI coding agents
executing a step MUST treat the security gate as part of the step's definition
of done, exactly like its tests. This phase sends the operator's situation off
the terminal for the first time: a toast shows on the lock screen, a log file
outlives the process, and a scheduled task runs with no one watching. So
notification text names and never locates, the log file holds no coordinate at
INFO or above, the scheduled tasks store no credential and run at the least
privilege, every subprocess is built from an argument list with an absolute
executable path, and no step reads, prints, or quotes the operator's
coordinates, an assessment of the operator's location, or a notification sent
about it.

**Deploy-and-verify rule.** Merged is not deployed, and deployed is not
released. Every step header carries a `**Deploys:**` line naming the surface and
environment the step's merge reaches — or `nothing beyond merge` — and when
going live needs a migration, a reinstalled copy, a registered task, or a tag,
the line says so and this step (or a named follow-on step) owns that event. For
a step whose Deploys line names a surface, Stage 4 of the lifecycle does not end
at the squash-merge: the step's acceptance criteria carry a **Deployed &
verified** bullet (`doctor` on the operator's machine reports the database at
the Alembic head and the heartbeat; a toast reached the operator's desktop and
its delivery row says so; Task Scheduler shows both tasks), and that bullet must
be green before the step is declared complete. This phase introduces no secret
and no required environment variable: every source stays keyless, and the new
`WEATHERBOT_MONITOR_*` and `WEATHERBOT_NOTIFICATIONS_*` overrides are optional.
Its new local surfaces are revisions `0004` to `0006`, the toast channel and its
application identity under `HKEY_CURRENT_USER`, the log file in the data
directory, and the two scheduled tasks. A step registers anything persistent on
the operator's machine — the application identity, a scheduled task, an
installed copy — only after the operator says yes to that exact action
(AskUserQuestion), and a toast on the operator's desktop is confirmed by the
operator. An agent verifies with the public landmarks in a temporary data
directory and reads the operator's database only through `doctor`. See the
project roadmap's "Release & deployment strategy" for the surfaces table,
promotion path, migrations, and rollback.

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
contract test in the same PR. A golden that changes is never "fixed" by
regenerating it: a policy change that moves a notification golden, like a rule
change that moves a replay golden, needs the operator's approval in the PR. A
step's PR contains the step plus blocking fixes only, and lists the issues it
opened. When a merged PR auto-closes an issue, the environment check is what
earns the close — reopen or follow up if a gap remains.
`docs/phase04-qa-findings.md` is the rollup: every finding, its class, and the
guard added so the class cannot recur.

**Status rule.** Every step carries a `**Status:**` line directly under its `##
Step N — …` heading, before the Goal, and this file on `main` is the ledger of
what is done — never a chat transcript, never a later conversation
reconstructing history from `git log`. The line reads `Not started` when this
roadmap is written and is flipped by the step's OWN pull request: at Stage 3,
right after `gh pr create` returns the PR number, the agent sets it to `Complete
— PR #<n> (<YYYY-MM-DD>)`, appends ` ✅` to the step's heading (`## Step 3 — The
notification policy and the notification log ✅`) so the completion shows in the
rendered preview, the outline, and the table of contents, sets the step's
Summary Table Status cell to `Complete — PR #<n>`, commits that edit on the step
branch, and pushes. The PR therefore carries its own completion mark, and the
roadmap on `main` says a step is complete exactly when that step's PR merges —
never before. This file's phase-level `**Status:**` line (under the title) and
the project roadmap are marked the same way, in the same commit: Step 1's PR
flips both from `Not started` to `In progress` (the project roadmap's `### Phase
4` line reads `In progress — phase04-roadmap.md`, and its row in the "Phase
Complexity Summary" table reads `In progress`), and the final step's PR flips
both to `Complete — …` (the project roadmap's with its row in the "Phase
Complexity Summary" table and the header `> **Status:**` line) and appends ` ✅`
to this file's `# ` title and to the project roadmap's `### Phase 4` heading, so
the project roadmap shows a finished phase the way this file shows a finished
step. There is no separate "update the roadmaps" chore: a step whose PR merged
without its Status line is a lifecycle violation, and the next step's Stage 1
(and `/roadmap-step`) refuses to start until the previous step reads `Complete`.
If a post-merge check fails — a Deployed & verified bullet, an alarm that never
fired — the step is NOT complete despite the merged line; say so, and the
`hotfix/` PR that completes it appends its own number to the line. `grep -n
'^\*\*Status:\*\*'` on this file is the phase's progress report, and the ✅
headings are the same report at a glance.

**Step lifecycle.** Every step in this phase follows the exact same six-stage
lifecycle, in order, with no exceptions. Each stage is a hard checkpoint — if a
stage is skipped, branch protection or the next step's Stage 1 will fail loudly,
and that is the safety net. AI coding agents MUST execute all six stages before
declaring a step complete.

1. **Create the branch.** Before any Read / Edit / Bash, run `git checkout -b
   feature/phase04-step<M>-<slug>` from a clean, up-to-date `main`. The exact
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
   branch (`docs: mark Phase 4 Step <M> complete`), and push — the PR now
   carries its own completion mark, so the roadmap on `main` will say the step
   is complete exactly when the PR merges (Status rule). On the phase's first
   step, the same commit sets this roadmap's phase-level `**Status:**` (under
   its title) and the project roadmap's Phase 4 `**Status:**` to `In progress`;
   on the final step, both to `Complete`, with ` ✅` appended to this roadmap's
   `# ` title and to the project roadmap's `### Phase 4` heading.

4. **Wait for green checks, then squash-merge.** Every required status check
   must report success: the aggregate `gate` check of `ci.yml` (lint, typecheck,
   the test matrix with the coverage floor, the package smoke, and the security
   scan) and the aggregate `phase-verify` check (`phase-verify (01)`,
   `phase-verify (02)`, `phase-verify (03)`, and `phase-verify (04)` from Step
   7). If the PR goes BEHIND main while waiting, refresh with `gh pr
   update-branch --rebase` — never merge `main` into the branch;
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
   for phase-boundary hygiene, the operator closes this Claude Code / Codex /
   Antigravity session and opens a fresh one before starting Step <M+1>; the new
   conversation begins again at Stage 1 of this lifecycle, with the next step's
   `**Branch:**` line driving the `git checkout -b` command. No work straddles
   two steps.

---

## Current State (as of Phase 3)

### Persistence surface

- The Alembic head is `0003`: the frozen `0001` baseline (17 tables),
  `0002_drift_warnings`, and `0003_assessments` (`assessments`,
  `assessment_evidence`, `assessment_changes`, and the plain `add_column` of
  `locations.evacuation_order_set_at`). `open_database(paths)` backs the
  database up with SQLite's online backup API before any upgrade
  (`data_dir/backups/weatherbot-<UTC stamp>-<revision>.sqlite3`), refuses an
  unknown revision, and runs DDL in a transaction. Every connection sets
  `foreign_keys=ON`, `journal_mode=WAL`, and `busy_timeout=5000`, and a `begin`
  event emits a plain deferred `BEGIN`; nothing in `src` holds a process lock,
  so two processes that write at once can meet `database is locked`.
- `SnapshotRepository.save(snapshot, responses, drift_warnings)` writes a
  snapshot in one transaction: its source outcomes, its observation rows, the
  raw responses (`raw_responses`, with each body stored once per SHA-256 in
  `response_bodies`), and every product geometry through `_product_row` into
  `product_geometries` (`snapshot_id`, `advisory_id`, `product_kind`,
  `position`, `crs`, `crs_datum`, and the encoded `geojson`, `properties`, and
  `provenance` of `services/persistence/codec.py`), all of it again for every
  snapshot; `load` reads it back through `_decoded`. Nothing references
  `product_geometries`. Measured on 2026-10-21 with the recorded answers: every
  unchanged cycle adds 1.85 MiB of geometry rows and 2.0 MiB to the file
  (Overview, "Design rationale").
- `AssessmentRepository(engine, now=)` saves an assessment with its changes once
  per location, snapshot, and ruleset, and `AssessmentService(engine,
  thresholds=, now=).assess(snapshot, locations)` runs, per location, the latest
  stored assessment at or before the snapshot's instant, `assess`, and `diff` in
  one transaction, returning `AssessedLocation(location, stored, created,
  toggle_changed)`; a rerun over the same snapshot returns the stored assessment
  with `created=False`. A replay snapshot is refused. `SettingsRepository` holds
  one key, `disclaimer_shown_at`. There is no retention or pruning
  (`docs/phase02-qa-findings.md` leaves raw-response retention to Phase 7).
- Phase 2's check 30 parses every tracked revision under `migrations/versions/`:
  each needs literal `revision` and `down_revision` values and an
  `op.create_table("name", …)` whose first argument is a string.
  `tests/services/test_tables.py` asserts the exact Phase 3 table set and
  forbids a table named for notifications or heartbeats;
  `tests/services/test_database.py` freezes `0001` and `0002` by SHA-256 and its
  `0003` test asserts the head is `0003` (Phase 3's V6.2 selects the tests named
  for `0003`).

### Services surface

- `SnapshotService(engine, network=, now=).fetch_snapshot(locations)` (async)
  fetches the roster first, then the summary service, the arrival KMZ, the
  breakpoint catalogue, peak surge, the TCPs and TWOs, the GIS feeds, the
  outlook graphics, and each US location's point, county-zone, and forecast-zone
  alerts concurrently; stores the snapshot; and returns
  `FetchedSnapshot(snapshot, drift_warnings)`. Its conditional fetcher reads
  validators from `RawResponseCache`, so the roster, KMZ, feeds, graphics, and
  ArcGIS queries can answer 304; the text products carry no validators. One
  failed alert query drops every location's alerts, and a failed source drops
  all of its records. `SourceOutcome` has `status` (`ok`, `not_modified`,
  `failed`, `skipped`), `error_kind`, and `reason`, but no instant; the
  database's `source_outcomes.fetched_at` is not loaded back.
- `weatherbot.engine.assess` names a *failed* source among the ladder's sources
  as an `UnavailableInput` (`kind`, `source_id`, `atcf_id`, `storm_name`,
  `threshold_kt`, `reason`), and NWS alerts missing for a US location as
  `nws_alerts`; a *skipped* source names nothing. `diff(previous, current)`
  emits the seven `CHANGE_KINDS` in a fixed order; it guards a vanished storm
  when the roster failed, but it emits `level_changed` and `official_removed`
  from an incomplete assessment like any other.
- `ReplayService(corpus).timeline(atcf_id, location, thresholds)` returns
  `ReplayStep(assessment, changes)` per advisory and stores nothing;
  `services.replay.without_evacuation_order(location)` turns the toggle off for
  a replay. Measured on 2026-10-21 over the eight storm-landmark pairs: every
  replay assessment lacks `arrival_times` and `outlook_areas`, and the
  Miami-Dade ones `nws_alerts`, the same at every step except Ian's last three
  advisories (36 to 38, at level 1, with no level change), which also lack wind
  probabilities.
- No scheduler, monitor, policy, or channel exists, and no process lock or
  signal handling. `src/weatherbot/services/__init__.py`'s docstring already
  gives the layer "the scheduler, change detection, notification policy and
  channels". An empty, untracked `src/weatherbot/notifiers/` directory is a
  leftover on disk; git tracks nothing in it, and Phase 1's check 10 fails if
  any path version 1 deleted is tracked again,
  `src/weatherbot/notifiers/toast.py` among them, so no step puts a file there.

### CLI surface

- The root Typer app in `cli/__init__.py` registers `locations` (with `add`,
  `list`, `remove`, `evacuation`), `fetch`, `storms`, `alerts`, `status`,
  `replay`, and `doctor`; Phase 2's check 36 and Phase 3's check 43 read those
  registrations as literal `app.command("…")` and `app.add_typer(locations.app)`
  lines, so new commands are added beside them in the same form. Each command
  builds its services directly inside `with open_session(context, output) as
  database:`, which opens and migrates the database and prints the disclaimer's
  essentials on first run; `status` exits 0 on a complete snapshot and 1 on a
  partial or failed one, and 2 on a usage error.
- `cli/documents.py` defines the `--json` documents and `DOCUMENTS` maps seven
  schemas (`locations`, `fetch`, `storms`, `alerts`, `doctor`, `status`,
  `replay`), committed under `docs/schema/` by `scripts/export_schemas.py`.
  `tests/cli/test_documents.py` asserts there are exactly seven and that no
  schema's text holds a decimal number, so a new document carries integer bounds
  and defaults only. `ChangeEntry.kind` repeats the seven change kinds as its
  own literal.
- The test seam is `CliRunner().invoke(app, args, obj=Runtime(make_fetcher=...,
  now=..., terminal=False))`; `tests/cli/cli_support.py` serves every recorded
  answer through respx (`recorded_services()`, `run()`, `parse()`, `urls()`,
  `add_landmark()`). Phase 2's V6.2 selects the whole `tests.cli` package, so a
  test under `tests/cli/` that skips on the operator's Windows account turns
  that row SKIP and Phase 2's nested `--post` red.

### Configuration and logging surface

- `AppPaths` has two directories, `WEATHERBOT_CONFIG_DIR` and
  `WEATHERBOT_DATA_DIR` or `platformdirs`' user directories; on Windows both are
  `%LOCALAPPDATA%\weatherbot`. `Settings` holds `[logging] level`, `[http]
  timeout_seconds`, and the six `[engine]` thresholds, each table a frozen
  `_Section`; `ENVIRONMENT_OVERRIDES` maps eight `(table, key)` pairs to
  `WEATHERBOT_*` names as literals, and a `ConfigError` names the key, never the
  value. Phase 3's check 24 reads that mapping as literals and requires exactly
  one class named `Settings` and one named `EngineSettings` under `services/`;
  its check 38 requires `Thresholds` to hold exactly the six thresholds.
- `configure_logging(level)` installs one standard-error handler with
  `RedactingFilter` and the format `%(levelname)s %(name)s: %(message)s`, with
  no timestamp and no file; httpx, httpcore, and alembic stay at WARNING unless
  the level is DEBUG. Under `pythonw.exe`, `sys.stderr` is `None`, so today's
  logging would write nowhere.
- `tests/conftest.py` clears every `WEATHERBOT_*` variable except
  `WEATHERBOT_DENYLIST` and `WEATHERBOT_CORPUS_CACHE` (Phase 2's check 32 reads
  that set exactly) and points both directories into the test's temporary
  directory, so new overrides need no conftest change.

### Windows integration surface

- No toast library, task registration, or application identity exists; neither
  pywinrt nor pywin32 is installed. Every uv environment has
  `Scripts\pythonw.exe` beside `python.exe` (the checkout's `.venv` does), and
  `python -m weatherbot` runs the CLI, so a task can start Weatherbot with no
  console window and no new entry point.
- The operator's account (checked 2026-10-21) is an administrator under UAC
  whose shells run at medium integrity, on Windows 11 build 26200. Reported on
  Windows 11 (one report on this build), not yet tried here: `schtasks /Create
  /SC ONLOGON` needs elevation, and a `LogonTrigger` that names the current user
  does not (Overview, "Design rationale"). `C:\Windows\System32\Tasks` grants
  Authenticated Users write and creates folders owned by their creator, so a
  `\Weatherbot\` task folder is expected to work unelevated; Step 6 proves it.
- `weatherbot` on the operator's `PATH` is version 1.0.0 from a retired virtual
  environment outside the checkout (ninth on `PATH`), with another version 1
  copy in the system Python 3.11; `~/.local/bin`, where `uv tool install` puts a
  launcher, is 35th. No uv tool is installed.

### Security & sensitive-data surface

- Data in play: notification text, which reaches the lock screen and the
  notification center; the log file, which outlives the process; the operator's
  assessments, which the monitor now writes unattended; and the scheduled tasks,
  which run as the operator. A distance, a bearing, or an arrival instant
  locates the operator's home as surely as its coordinates, so none appears in a
  notification or in a log line above DEBUG. Phase 4 adds no secret.
- Controls: the four-check gate in pre-commit and CI's `security` job (gitleaks;
  bandit over `src` and `scripts` at every severity, so a subprocess call needs
  a justified `# nosec` and an absolute executable path;
  `scripts/audit_deps.py`; `scripts/check_personal_data.py` R1 to R4, R2
  allowing only the two landmarks as coordinates); `RedactingFilter` on every
  handler; `repr=False` on located fields; `hide_input_in_errors` on every
  model; and `Citation`, which drops a located URL from evidence. Phase 2's
  check 16 forbids the text `verify=False` and `follow_redirects=True` in the
  package, its check 20 any standard-library XML module (`xml.sax.saxutils`
  included), and its check 28 any string literal holding `/points/` or `point=`
  outside `sources/nws.py` and `sources/http.py` (`checkpoint=`, `endpoint=`,
  and `breakpoint=` included).
- Patterns every step mirrors: tests use the two landmarks or values generated
  at run time, never a coordinate literal; a message names a rule, a key, or a
  source, never a value; subprocesses take argument lists; XML is written as an
  escaped template and read through `defusedxml` or not at all; the operator's
  database is read only through `doctor`; and every new dependency passes
  `pip-audit`.

### Operations & observability surface

- Nothing runs unattended yet. `doctor` is the local health signal and its exit
  status the alarm: `settings`, `database`, `migrations`, and `locations`
  checks, source probes and layer discovery online, and the drift warnings
  stored with the latest snapshot. Phase 2's and Phase 3's alarm proofs run
  `doctor --offline --json` on a fresh temporary database and require exit 0,
  then stamp an unknown revision and require exit 1. The GitHub surfaces are
  `ci.yml` and `phase-verify.yml` (both required), the twice-weekly
  `replay-corpus.yml`, and the dispatch-only `live-smoke.yml`, whose
  dispatch-only form Phase 2's check 15 requires.
- The project roadmap's "Operations & observability strategy" gives this phase
  two health signals — `serve`'s last successful fetch per source with a toast
  and log entry after N consecutive failures (N TBD here), and the scheduled
  check's heartbeat with a banner and toast when older than twice its cadence —
  and the rule that a surface is live only once its alarm has been seen to fire.

### Documentation surface

- `README.md`'s Status section still says Phase 3 is in progress and that
  nothing runs on a schedule or notifies yet; its `## Commands` section lists
  Phase 2's and Phase 3's commands, and Phase 2's check 41 and Phase 3's check
  47 read that heading and require `weatherbot status`, `weatherbot replay`, and
  `weatherbot locations evacuation` before the next `## ` heading.
  `CONTRIBUTING.md` documents the checks, the live suite, the command tests and
  schemas, local data, the replay corpus, and the security gate; `AGENTS.md`
  describes the layers; `CHANGELOG.md` has one `## [Unreleased]` section with a
  "Phase 3 — Threat engine" group (Phase 1's check 4 requires exactly one such
  heading); `docs/DATA_SOURCES.md`'s register states each source's cadence and
  caching, and says "v2 … polls alerts at the scheduler's cadence (Phase 4)".

### Verification surfaces

- `scripts/verify_phase03.py` is the structural template: 52 standard-library
  static checks, the modes `--fast`, `--py`, `--live`, `--security`, `--all`,
  and `--post`, and 28 V rows built from three JUnit runs (offline with the
  engine coverage floor, live, and corpus), in which every selection must match
  a test, a failure fails, and a skip is never a pass. Its `--post` nests Phase
  2's (73 checks), which nests Phase 1's (75); the canonical run on `main` took
  3,237 s, and its nested Phase 2 call has a 5,400-second timeout.
- `.github/workflows/phase-verify.yml` runs matrix entries `"01"`, `"02"`, and
  `"03"` (`--fast` and `--security` each, with full history and a
  checksum-verified gitleaks) under the required aggregate `phase-verify`. Step
  7 appends `"04"` to the flow list; the three entries stay.
- Checks of the earlier phases that this phase's growth could turn red, and how
  each stays green: Phase 3's checks 32 (the seven change kinds), 33 (the eight
  replay goldens), and 38 (the six thresholds) are exact, and no step adds a
  kind, a replay golden, or a threshold; Phase 3's check 8 and every test module
  need unique basenames (`test_config`, `test_status`, `test_snapshots`,
  `test_database`, `test_commands`, `test_replay`, `test_assessments`,
  `test_tables`, `test_documents`, `test_geometry`, `test_nws`, and `test_http`
  are taken); Phase 1's check 10 forbids re-adding version 1's deleted paths;
  Phase 1's checks 25 and 26 require every workflow's actions pinned to a full
  SHA with a version comment and a top-level `permissions:`; Phase 1's check 15
  requires every new ruff ignore on its own line with its reason; and the wheel
  smokes of all three phases import the CLI and the services on Ubuntu, so a
  Windows-only import must stay behind `sys.platform == "win32"`.

### Carry-over from Phase 3

Every item Phase 3 handed to this phase, and where it lands:

| Item | Source | Destination in Phase 4 |
| ---- | ------ | ---------------------- |
| Run `assess` on a schedule; store each cycle through `AssessmentService` | QA ledger, pre-ship items; project roadmap 4.2 | Step 2 (the cycle), Step 5 (the schedule) |
| Turn `diff`'s change events into notifications; escalations always notify | QA ledger, pre-ship items; brief §9 | Step 3 |
| A staleness banner on incomplete assessments and stale sources; staleness is not a change kind | QA ledger, pre-ship items; project roadmap 4.1 | Step 2 (heartbeat, rule, banner), Step 3 (held drops on incomplete assessments) |
| Notification goldens outside `tests/golden/replay/`; a new change kind converts check 32 | QA ledger, pre-ship items; project roadmap, Phase 4 | Step 3 (`tests/golden/notifications/`; no new kind) |
| The scheduler, `check --once`, Task Scheduler, the heartbeat, and a `config` command | Phase 3 roadmap, "Not in scope" | Steps 2, 5, and 6 |
| Quiet hours and the cooldown | Phase 3 roadmap, "Not in scope"; brief §9 | Step 3 (the rule and its settings); Phase 7 adds the settings page and proves it through ntfy |
| `README.md`'s Status section still says Phase 3 is in progress | Found writing this roadmap (Phase 3 Step 7's closure missed it) | Step 1 |
| The development-chance floor is calibrated on a recorded scenario only | QA ledger, pre-ship items | Any step that records an outlook during an active season (Source drift) |
| Whether a storm-surge or extreme-wind product moves the ladder | Issue #33, the operator | The operator; Phase 3's V3.3 accepts it open or closed with its decision |
| The Atlantic and Central Pacific rows of the register's per-basin table wait for an active storm there | Phase 2 QA ledger, pre-ship items | Any step that runs while a storm is active in one of those basins re-checks that row under Source drift, adding captures beside the 2026-10-12 set and never replacing it (on 2026-10-21 Subtropical Storm Josephine, AL102026, became active in the Atlantic at 21:00 UTC, beside Tropical Storm Vance, EP222026) |
| Dependabot PRs #8, #30, and #31 | QA ledger | Independent maintenance, outside every step |

---

## Execution Order

```
Step 1  (snapshot storage)                revision 0004: shared geometry
                                          content + per-snapshot provenance
                                          → implement
  ↓
Step 2  (cycle + heartbeat)               MonitorService.run_cycle + cycle
                                          lock + revision 0005 + staleness
                                          + check --once + config
                                          → implement
  ↓
Step 3  (policy + notification log)       services.policy + revision 0006
                                          + log channel + notify log
                                          + Irma notification goldens
                                          → implement
  ↓
Step 4  (Windows toast channel)           Channel + ToastChannel (pywinrt)
                                          + identity + notify test
                                          → implement
  ↓
Step 5  (scheduler + serve + check)       services.scheduler + windows
                                          + watches + retries + log file
                                          + degraded-data alarm
                                          → implement
  ↓
Step 6  (Task Scheduler + health)         install-task / uninstall-task
                                          + --if-stale fallback + doctor
                                          + the operator's installed copy
                                          → implement
  ↓
Step 7  (QA + verify_phase04.py)          scripts/verify_phase04.py
                                          + docs/phase04-qa-findings.md
                                          + phase-verify.yml entry "04"
                                          → create

--- post-implementation ---

V1  An unchanged cycle adds under 128 KiB; old snapshots
    load back equal; Phase 3's own post sweep passes.
V2  One cycle path under one lock; staleness holds under a
    frozen clock; doctor's alarm proof still fires.
V3  The policy equals the approved Irma timelines; every
    escalation is sent; repeats and held drops hold.
V4  The toast channel reports honest results; a real
    toast on the operator's machine reads delivered.
V5  The scheduler opens its windows and survives sleep;
    a simulated advisory raised a toast within one interval.
V6  A probe task registers unelevated; both tasks run as
    the operator; serve's heartbeat is fresh.
V7  verify_phase04.py --fast and --security exit 0 in
    phase-verify (04); the phase is closed.
```

Steps are sequential by dependency. Step 1 makes a stored snapshot small before
anything stores one on a schedule, and it touches only persistence, so the
monitor is written against the storage it will use; Step 2's cycle and heartbeat
are what Step 3's policy runs inside and what its decisions reference; Step 3's
notifications are what Step 4's toast delivers, and its in-app log is the
channel Step 4's interface generalizes; Step 5's scheduler runs Step 2's cycle
and needs Step 4's toast for the degraded-data alarm and the simulated advisory;
Step 6 registers Step 5's `serve` and Step 2's `check --once`; Step 7 verifies
every prior step. Steps 3 and 4 touch different modules, but Step 4's channel
interface delivers Step 3's notification records and both edit the notification
documents, `CHANGELOG.md`, and `CONTRIBUTING.md`, so this phase draws no steps
in parallel, and the Worktree rule permits no concurrent steps.

---

## Step 1 — Snapshot storage that stays small ✅

**Status:** Complete — PR #41 (2026-10-21)

> **Goal:** Make a stored snapshot cost what changed, before anything stores one
> on a schedule. Alembic revision `0004`
> (`migrations/versions/0004_shared_geometry.py`, after `0003`) creates
> `geometry_contents` (one row per distinct encoded geometry content, keyed by
> the SHA-256 of its canonical JSON and stored zlib-compressed, as
> `response_bodies` stores bodies), `snapshot_provenances` (one row per distinct
> provenance within a snapshot), and `snapshot_geometries` (each product's
> advisory, kind, and position, linked to its content and to its provenance,
> which names its snapshot); `SnapshotRepository.save` writes every new
> snapshot's products through them, and `load` reads a snapshot stored before
> the revision from `product_geometries` as it is, both giving an equal
> `Snapshot`; the downgrade writes the new rows back into `product_geometries`
> before dropping the tables, so no stored snapshot is lost either way; a
> measurement test proves that a second cycle over unchanged answers adds no
> content row and grows the database by less than 128 KiB, where it grew by 2.0
> MiB; and `README.md`'s Status section says where the project stands. This step
> lands the storage; Step 2's cycle and Step 5's schedule write through it.

**Branch:** `feature/phase04-step1-snapshot-storage`

**Deploys:** the operator's machine → the local SQLite database migrates to
revision `0004` at the first command after the merge, after its online backup;
`doctor` must report `0004` at head `0004` on the operator's database. GitHub
Actions → the first `ci.yml` and `phase-verify.yml` runs on `main` must be
green.

| Setting      | Cost                                    | Balanced                             | Quality                                    |
| ------------ | --------------------------------------- | ------------------------------------ | ------------------------------------------ |
| Model        | GPT-6.1 Sol                             | Gemini 4 Argon                       | Opus 5.5                                   |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | Opus 5.5 — Claude Code · Effort High | Gemini 4 Argon — Antigravity · Effort High |
| Platform     | Codex                                   | Antigravity                          | Claude Code                                |
| Effort       | Intelligence High                       | Effort High                          | Effort XHigh                               |
| Thinking     | —                                       | On                                   | —                                          |
| Conversation | **New**                                 | **New**                              | **New**                                    |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

> Ran 2026-10-21: Balanced column's Backup — Opus 5.5 · Effort High. The **Runs:** rule selected Balanced (its Antigravity pool read `headroom`); the operator opened the column's Backup on Claude Code.

**Model rationale:** Step 1 is coding with a long-context secondary category: a
persistence change that has to keep Phase 2's load-equality contract across two
storage forms while reading the repository, the codec, the migrations, and their
tests together, and that migrates the operator's live database. Its overall
complexity is High — content hashing over a canonical encoding, a provenance
split out of the hash, a data-preserving downgrade, and a size measurement that
must be stable on both runners — and it is not novel: content-addressed storage
is the `response_bodies` pattern already in the repository. The columns differ
in depth and maker: Balanced runs Gemini 4 Argon, S-tier in coding, on
Antigravity at Effort High with thinking on; Quality runs Opus 5.5, S-tier in
coding, on Claude Code at Effort XHigh for the closest audit of migration edge
cases (it always thinks, so its Thinking cell is `—`); Cost moves the step to
GPT-6.1 Sol on Codex at Intelligence High. Google AI Pro funds Antigravity, the
claude.ai Max subscription funds Claude Code, and ChatGPT Pro 5x funds Codex, so
each column costs nothing at the margin while its pool has headroom, and each
backup comes from another maker. Antigravity must be signed into the personal
account Google AI Pro is on (the user-context records a Workspace sign-in on
2026-10-10, which Antigravity refuses); when it cannot serve the step, the
Balanced column's Backup, Opus 5.5 on Claude Code at Effort High, runs instead.
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
       feature/phase04-step1-snapshot-storage`
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
       Phase 4 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 4`
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

    THIS STEP changes how every snapshot is stored and migrates
    the operator's database. The revision runs after
    `open_database`'s online backup, creates tables only, and
    moves no existing row; its downgrade copies rows back and
    drops nothing it has not copied. Content is canonical JSON
    compressed with `zlib` and read back through `json`, never
    `pickle`. Provenance keeps exactly the fields it has today, in
    the local database only: no log line, message, or test output
    prints a provenance, a URL, or a geometry. The measurement
    test writes to its own temporary data directory and prints
    sizes and row counts only. No test holds a coordinate other
    than a landmark's, and no dependency is added.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 4 (Monitoring and
    notifications). Step 1: Snapshot storage that stays small.

    Current state (as of Phase 3; no Phase 4 step has run):

    - `main` requires `gate` (`ci.yml`) and `phase-verify`
      (entries `"01"`, `"02"`, and `"03"`). The Alembic head is
      `0003`; every connection runs WAL with a 5-second busy
      timeout and transactional DDL.
    - `SnapshotRepository.save`
      (`services/persistence/repositories.py`) writes each product
      through `_product_row`, which calls
      `codec.encode_product(kind, record)` and stores `crs`,
      `crs_datum`, `geojson`, `properties`, and `provenance` in
      one `product_geometries` row per product per snapshot
      (`snapshot_id` cascades from `snapshots`; `advisory_id`
      references `advisories`). `_storms` and `_snapshot_products`
      read the rows back through `_decoded`
      (`codec.decode_product`) in `position` order. Nothing
      references `product_geometries`. `raw_cache.store_body` and
      `read_body` (one zlib body per SHA-256 in `response_bodies`)
      are the precedent for content stored once.
    - Measured on 2026-10-21 with a scratch harness over
      `tests/cli/cli_support.recorded_services()` (two landmarks;
      `status` four times, 15 minutes apart on the runtime clock;
      `PRAGMA wal_checkpoint(TRUNCATE)` before each size): the
      first cycle adds 3.1 MiB and every later one 2.0 MiB. Per
      snapshot, `product_geometries` holds 608 rows and 1.85 MiB:
      wind-speed probabilities 3 rows and 1.2 MiB; wind radii 24
      rows and 196 KiB; display layers 6 rows and 50 KiB; the
      breakpoint catalogue 549 rows with 26 KiB of GeoJSON, 65 KiB
      of properties, and 242 KiB of provenance; the cone 21 KiB;
      outlook areas 14 KiB. Everything else a cycle adds is about
      25 KiB (assessments 9.9 KiB for two locations, observation
      and outcome rows).
    - A `Provenance` carries `fetched_at`, `status`,
      `not_modified`, and the fetch's validators, so it differs on
      every cycle even when its product does not; records parsed
      from one response share one provenance.
    - Checks that read this code: Phase 2's check 30 parses every
      tracked revision (literal `revision` and `down_revision`, an
      `op.create_table` whose first argument is a string, one
      root, `0002` after `0001`); Phase 3's check 41 pins `0003`
      exactly; Phase 3's check 17 needs `SnapshotRepository` to
      keep one `def save` with `snapshot.origin != "live"`. Phase
      2's V5.2 selects the whole of
      `tests/services/test_database.py` and
      `tests/services/test_repositories.py`'s
      `test_a_recorded_snapshot_is_saved_and_loaded_back_equal`;
      Phase 3's V6.2 selects the `test_database.py` tests whose
      names contain `0003`.
    - `tests/services/test_tables.py`'s
      `test_the_tables_are_phase_3s_only` asserts the exact Phase
      3 table set (no V row selects it);
      `tests/services/test_database.py`'s `0003` test asserts
      `opened.revision == "0003"`, and its `FROZEN` pins `0001`
      and `0002` by SHA-256 with CRLF normalized.
    - `README.md`'s Status section still says Phase 3 is in
      progress and that nothing runs on a schedule or notifies
      yet.

    Files to read (every file before drafting):
    - docs/roadmap/phase04-roadmap.md (Overview and its design
      rationale, Current State, this step, and the goals of Steps
      2 and 5, which write through this storage).
    - docs/roadmap/ROADMAP.md (Phase 4; section 5, "Data and
      schema migrations").
    - src/weatherbot/services/persistence/repositories.py,
      codec.py, tables.py, raw_cache.py, and database.py.
    - src/weatherbot/services/persistence/migrations/: env.py and
      versions/0003_assessments.py.
    - tests/services/test_repositories.py, test_database.py,
      test_tables.py, and snapshot_support.py;
      tests/cli/cli_support.py.
    - docs/phase02-qa-findings.md (the persistence rows),
      CONTRIBUTING.md ("Local data"), README.md (Status), and
      CHANGELOG.md.
  </context>

  <goal>
    Ship revision `0004` and the repository change that stores
    each geometry content once and each provenance once per
    snapshot; keep every snapshot stored before the revision
    loading back equal, and every snapshot stored after it
    loadable at `0003` once downgraded; prove with tests that two
    snapshots of the same products share every content row and
    that a second `status` over unchanged recorded answers grows
    the database by less than 128 KiB; and update README's Status.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Revision `0004`
      (`migrations/versions/0004_shared_geometry.py`, `revision:
      str = "0004"`, `down_revision: str | None = "0003"`, plain
      SQLAlchemy types as in `0003`, each table created with
      `op.create_table("…", …)`):

      - `geometry_contents`: `id` (primary key); `sha256`
        (CHAR(64), unique); `product_kind` (checked against the
        eleven product kinds); `size` (the canonical JSON's length
        in bytes); `body` (BLOB: the zlib-compressed canonical
        JSON).
      - `snapshot_provenances`: `id` (primary key); `snapshot_id`
        (references `snapshots.id`, `ON DELETE CASCADE`);
        `position`; `provenance` (JSON); unique on `(snapshot_id,
        position)`.
      - `snapshot_geometries`: `id` (primary key); `provenance_id`
        (references `snapshot_provenances.id`, `ON DELETE
        CASCADE`: the link's snapshot is its provenance's);
        `advisory_id` (references `advisories.id`, nullable,
        indexed); `product_kind` (checked); `position`;
        `content_id` (references `geometry_contents.id`); an index
        — not a unique key — on `(provenance_id, product_kind,
        position)`, because positions restart for each storm, so
        two storms' cones, tracks, points, and radii share
        positions within one snapshot.
      - Amended in this step's PR (spec rot, measured): the first
        draft keyed `geometry_contents` by `sha256` alone and gave
        each link `snapshot_id` and `content_sha256` with an index
        on `(snapshot_id, product_kind, position)`. Built that way,
        a second unchanged cycle grew the file by 144 to 152 KiB
        (36 to 38 pages; the 32-character snapshot id and the
        64-character hash on each of 608 links, and a random-UUID
        index whose fill varied by run), over the 128 KiB budget.
        Integer links reached through the provenance grow it by
        64 KiB (16 pages) on every run, half the budget, leaving
        room for the rows Steps 2 and 3 add to every cycle.
      - The upgrade creates the three tables and touches no
        existing row. The downgrade first writes every
        `snapshot_geometries` row back as a `product_geometries`
        row (the content's `crs`, `crs_datum`, `geojson`, and
        `properties`, and the linked provenance, decompressed with
        `zlib` and read with `json`), then drops the three tables,
        newest first. Add `0003`'s SHA-256 to `FROZEN` in
        `tests/services/test_database.py`: it is merged and
        frozen.
    </requirement>

    <requirement>
      `SnapshotRepository` (in place; no second class of that
      name):

      - `save` writes every product of a new snapshot through the
        new tables, in its one transaction: the record is encoded
        with `codec.encode_product` as today; its content is the
        canonical JSON of `{"product_kind", "crs", "crs_datum",
        "geojson", "properties"}` (`json.dumps(…, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False)` encoded as
        UTF-8), whose SHA-256 keys `geometry_contents`, inserted
        only when absent (`INSERT … ON CONFLICT (sha256) DO
        NOTHING`, then the ids read back by hash); each distinct
        provenance of the snapshot is one `snapshot_provenances`
        row; and one `snapshot_geometries` row links the product
        to both by their ids. `product_geometries`
        receives no new row. The refusal of a replay snapshot
        (`snapshot.origin != "live"`) stays where it is.
      - `load`, `_storms`, and `_snapshot_products` read a
        snapshot's products from `snapshot_geometries` when it has
        provenance rows (written only with links) and from
        `product_geometries` otherwise (a snapshot never has
        both), decode each through
        `codec.decode_product`, and return the same `Snapshot`
        either way, in the same order.
      - A content row is never updated or deleted. Removing a
        snapshot cascades its provenance rows and, through them,
        its link rows; a content
        row no snapshot uses any more stays until Phase 7's
        retention, and the docstring says so.
      - No other table and no other repository changes;
        `RawResponseCache`, `response_bodies`, `raw_responses`,
        and the observation tables are untouched.
    </requirement>

    <requirement>
      Tests, every one offline and under a unique basename:

      - `tests/services/test_geometry_storage.py`: the recorded
        snapshot (`snapshot_support.recorded_snapshot()`) saved at
        `0004` loads back equal; a snapshot with two active storms
        (the recorded storm and a second built with
        `snapshot_support.dorian()` or
        `tests/engine/engine_support.synthetic_storm`) saves and
        loads back equal, each storm keeping its own products in
        order; two saves of the same products under two snapshot
        ids and two fetch instants add one set of content rows and
        two sets of link and provenance rows, and both load back
        equal; a provenance is stored once for all the records of
        one response (the breakpoint catalogue's 549 points share
        one row); a pre-`0004` snapshot — a database migrated to
        `0003`, a snapshot written into `product_geometries`
        through the codec as the old writer did, then the upgrade
        — loads back equal; and removing a location never touches
        content rows.
      - `tests/services/test_database.py` (tests named for
        `0004`): the upgrade from `0003` keeps every existing row;
        a snapshot saved at `0004` — the two-storm one too — still
        loads back equal after `alembic downgrade 0003`; a failed
        upgrade rolls back completely. The `0003` test compares
        `opened.revision` with `head_revision()` instead of the
        literal, and keeps its name.
      - `tests/cli/test_commands.py`'s
        `test_doctor_offline_reports_the_paths_the_head_and_the_locations`
        asserts `migrations  pass    at revision 0003, the head`:
        make it read the head from `head_revision()`, keeping its
        name and the column spacing (every later `doctor` check
        name stays at most 10 characters, the width of
        `migrations`, so that spacing never moves). Phase 2's V6.2
        selects the whole `tests.cli` package.
      - `tests/services/test_tables.py`: the table set is Phase
        3's plus the three new tables (rename the test for the new
        set; no V row selects it).
      - `tests/cli/test_storage_growth.py`: two `status` runs over
        `recorded_services()` with the two landmarks, the runtime
        clock 15 minutes apart, a WAL checkpoint (`TRUNCATE`)
        before each size: the second adds no `geometry_contents`
        row and grows the database file by less than 128 KiB. It
        never skips. (As shipped, the second run's fetches are 15
        minutes later too, through `cli_support.quiet_fetcher(…,
        now=)`, so its provenances differ as a real cycle's do.)
    </requirement>

    <requirement>
      Documents. `README.md`'s Status: Phases 1 to 3 are complete,
      Phase 4 (monitoring and notifications) is in progress, and
      nothing yet runs on a schedule or notifies.
      `CONTRIBUTING.md`'s "Local data": unchanged geometry is
      stored once and shared by the snapshots that use it.
      `CHANGELOG.md`: a "Phase 4 — Monitoring and notifications"
      group under `[Unreleased]`, above Phase 3's, with this
      step's entries (one `## [Unreleased]` heading only: Phase
      1's check 4).
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

- Revision `0004` follows `0003` and creates `geometry_contents`,
  `snapshot_provenances`, and `snapshot_geometries`; the upgrade keeps every
  existing row, the downgrade keeps every stored snapshot loadable at `0003`,
  and `0003` is pinned in `FROZEN`.
- Every snapshot saved at `0004` loads back equal, one with two active storms
  included, and a snapshot stored in `product_geometries` before `0004` loads
  back equal after the upgrade; `tests/services/test_repositories.py`'s
  round-trip test passes unchanged.
- Two snapshots of the same products share every content row; the breakpoint
  catalogue's 549 records share one provenance row; and a second `status` over
  unchanged recorded answers grows the database by less than 128 KiB (2.0 MiB
  before this step).
- `verify_phase01.py --fast`, `verify_phase02.py --fast`, and `verify_phase03.py
  --fast` still report 50, 47, and 52 checks, all PASS.
- `README.md`'s Status section names Phase 4 as in progress, and `CHANGELOG.md`
  has the Phase 4 group.
- **Deployed & verified:** after the merge, `uv run weatherbot doctor --offline
  --json` on the operator's machine, printing only the database fields, reports
  revision `0004` at head `0004` with `migrations` passing and the pre-migration
  backup in `backups/`; and the first `ci.yml` and `phase-verify.yml` runs on
  `main` at the merge commit are green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, SAST
  clean, dependency audit clean with no dependency added — and no test, log
  line, or message prints a provenance, a URL, or a geometry.

---

## Step 2 — The monitor cycle, the heartbeat, and staleness ✅

**Status:** Complete — PR #42 (2026-10-22)

> **Goal:** Give the monitor its one path and its pulse.
> `weatherbot.services.monitor.MonitorService.run_cycle(trigger)` fetches every
> source, stores the snapshot, assesses and stores every location through
> `AssessmentService`, records the heartbeat, and records the cycle, under a
> cross-process cycle lock (`weatherbot.services.locks.ProcessLock`, standard
> library only), with every writing transaction beginning `BEGIN IMMEDIATE`;
> revision `0005` (`migrations/versions/0005_monitor.py`) creates `heartbeats`
> (per source, per watch, and per monitor process: the last attempt, the last
> success, the run of consecutive failures, and the cadence its writer expects)
> and `monitor_cycles`; the pure staleness rule in `weatherbot.services.health`
> flags a row whose last success is older than twice its cadence, and `status`
> shows it in a banner and its `--json` document; `doctor` reports the
> heartbeat; `weatherbot check --once` runs one cycle on demand; `status`,
> `fetch`, `storms`, and `alerts` go through the same path; and `weatherbot
> config show` and `config path` print the effective settings with their origins
> and where the files live. This step lands the cycle; Step 3 decides
> notifications inside it, and Step 5 schedules it.

**Branch:** `feature/phase04-step2-monitor-cycle`

**Deploys:** the operator's machine → the local database migrates to revision
`0005` at the first command after the merge, after its online backup; `doctor`
must report `0005` at head `0005` and its heartbeat section. GitHub Actions →
the first `ci.yml` and `phase-verify.yml` runs on `main` must be green.

| Setting      | Cost                                    | Balanced                             | Quality                                    |
| ------------ | --------------------------------------- | ------------------------------------ | ------------------------------------------ |
| Model        | GPT-6.1 Sol                             | Gemini 4 Argon                       | Opus 5.5                                   |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | Opus 5.5 — Claude Code · Effort High | Gemini 4 Argon — Antigravity · Effort High |
| Platform     | Codex                                   | Antigravity                          | Claude Code                                |
| Effort       | Intelligence High                       | Effort High                          | Effort XHigh                               |
| Thinking     | —                                       | On                                   | —                                          |
| Conversation | **New**                                 | **New**                              | **New**                                    |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

> Ran 2026-10-22: Balanced column's Backup — Opus 5.5 · Effort High. The **Runs:** rule selected Balanced (its Antigravity pool read `headroom`); the operator opened the column's Backup on Claude Code.

**Model rationale:** Step 2 is coding with an agentic secondary category — a
service that composes the snapshot and assessment services under a lock shared
by processes, a revision, two commands, and a live run with the landmarks. Its
overall complexity is High: cross-process locking on two operating systems,
`BEGIN IMMEDIATE` threaded through the repositories' sessions, heartbeat
bookkeeping that must not mistake a skipped source for a failure, and `status`
rerouted through the cycle while Phase 3's tests and documents stay exactly as
they are. It is not novel; this roadmap fixes the decisions. The columns differ
in depth and maker: Balanced runs Gemini 4 Argon on Antigravity at Effort High
with thinking on; Quality runs Opus 5.5 on Claude Code at Effort XHigh (always
thinking, so `—`); Cost moves it to GPT-6.1 Sol on Codex at Intelligence High.
Google AI Pro, the claude.ai Max subscription, and ChatGPT Pro 5x fund the three
platforms, so each column costs nothing at the margin while its pool has
headroom; as in Step 1, when Antigravity cannot serve the personal account, the
Balanced Backup (Opus 5.5 on Claude Code at Effort High) runs. The conversation
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
       feature/phase04-step2-monitor-cycle`
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
       Phase 4 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 4`
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

    THIS STEP makes every fetching command write the heartbeat and
    the cycle record, and adds a lock file and two commands. The
    lock file holds the holder's process id and start instant for
    diagnostics only, inside the data directory, and is never
    trusted for exclusivity (the operating system's lock is). A
    cycle's log lines name the trigger, the cycle id, location
    names, levels, rules, and counts — never a coordinate, a
    distance, a bearing, an arrival instant, or a URL above DEBUG;
    a failure is recorded by its exception class and error kind,
    never its message. `config show` prints setting values and
    their origins (no secret exists in Phase 4; Phase 6's key is
    reported as present or absent, never printed) and `config
    path` prints the local paths to the operator's own terminal
    only; tests compare paths under their temporary directory and
    print none. The live test uses the two landmarks in a
    temporary data directory, never the operator's database. No
    dependency is added: the lock is `msvcrt.locking` on Windows
    and `fcntl.flock` elsewhere.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 4 (Monitoring and
    notifications). Step 2: The monitor cycle, the heartbeat, and
    staleness.

    Current state (as of Phase 4 Step 1):

    - The Alembic head is `0004` (shared geometry). Carry-over
      from Step 1 (PR body has the measurements): a stored
      product links to its content by `content_id` and to its
      snapshot through `snapshot_provenances` (no `snapshot_id` on
      `snapshot_geometries`); `tests/cli/test_storage_growth.py`
      measured a second unchanged `status` at 64 KiB (16 pages:
      links 4, their index 4, provenances 3, the advisory index 1,
      assessments 2, feed observations 2) against its 128 KiB
      bound. Once `status` runs through the cycle, that test
      counts this step's per-cycle rows (`monitor_cycles`, the
      heartbeat writes) too: keep them narrow, and re-measure
      before the PR.
      `SnapshotService(engine, network=,
      now=).fetch_snapshot(locations)` (async) fetches, stores,
      and returns `FetchedSnapshot(snapshot, drift_warnings)`;
      `AssessmentService(engine, thresholds=,
      now=).assess(snapshot, locations)` stores each location's
      assessment and changes in one transaction and returns
      `AssessedLocation(location, stored, created,
      toggle_changed)`. `cli/snapshots.read_snapshot` composes the
      first for `fetch`, `storms`, `alerts`, and `status`;
      `status` then runs the second.
    - `SourceOutcome.status` is `ok`, `not_modified`, `failed`, or
      `skipped` (a source not needed: no active storm, no arrival
      link, no US location); only a failed source among the
      ladder's sources becomes an `UnavailableInput`.
      `Snapshot.status` is `complete`, `partial`, or `failed` (the
      roster failed).
    - `open_database` sets WAL and `busy_timeout=5000`, and its
      `begin` event emits a plain deferred `BEGIN`, so a
      transaction that reads and then writes while another process
      commits can fail at once with `database is locked`. No
      process lock exists. `repositories._writing` and `_reading`
      join a caller's session or open their own.
    - `Settings` has `[logging]`, `[http]`, and `[engine]`;
      `ENVIRONMENT_OVERRIDES` is a literal mapping (Phase 3's
      check 24), and exactly one class named `Settings` and one
      named `EngineSettings` may exist under `services/`. On
      Windows `AppPaths.config_dir` and `data_dir` are both
      `%LOCALAPPDATA%\weatherbot`.
    - `doctor`'s local checks are `settings`, `database`,
      `migrations`, and `locations`. Phase 2's and Phase 3's alarm
      proofs require `doctor --offline --json` on a fresh
      temporary database to exit 0 and print one JSON document,
      and the operator-database rows read `database.at_head` and
      the `migrations` check.
    - `DOCUMENTS` holds seven schemas, and
      `tests/cli/test_documents.py` asserts the count (update it
      in place, keeping the test's name) and that no schema's text
      holds a decimal number. Phase 3's V6.2 selects
      `tests/cli/test_status.py` and `tests/cli/test_documents.py`
      whole, Phase 2's V6.2 the whole `tests.cli` package, and the
      live rows `tests/live/test_cli_live.py`; none of them may
      skip on the operator's Windows account. Test basenames must
      be unique: `test_config.py`, `test_status.py`,
      `test_snapshots.py`, and `test_commands.py` are taken.
    - Phase 2's check 36 and Phase 3's check 43 read the command
      registrations in `cli/__init__.py` as literal lines; new
      commands are added beside them in the same form. Phase 2's
      check 28 forbids a string literal holding `/points/` or
      `point=` (so `checkpoint=` and `endpoint=` too) outside
      `sources/nws.py` and `sources/http.py`.

    Files to read (every file before drafting):
    - docs/roadmap/phase04-roadmap.md (Overview and its design
      rationale, Current State, Step 1's acceptance criteria, this
      step, and Steps 3 and 5, which build on the cycle).
    - docs/roadmap/ROADMAP.md (Phase 4; section 5, "Operations &
      observability strategy").
    - src/weatherbot/services/snapshots.py, assessments.py,
      config.py, doctor.py, logs.py, network.py, and locations.py;
      src/weatherbot/services/persistence/database.py,
      repositories.py, and tables.py.
    - src/weatherbot/cli/__init__.py, runtime.py, snapshots.py,
      status.py, doctor.py, and documents.py;
      scripts/export_schemas.py.
    - tests/conftest.py, tests/cli/cli_support.py,
      tests/cli/test_status.py, tests/cli/test_documents.py,
      tests/services/test_database.py, and
      tests/live/test_cli_live.py.
    - README.md ("Commands"), CONTRIBUTING.md, AGENTS.md, and
      CHANGELOG.md.
  </context>

  <goal>
    Ship `MonitorService.run_cycle`, `ProcessLock`, revision
    `0005`, the staleness rule, and the `check --once`, `config
    show`, and `config path` commands; route `status` and `fetch`
    through the cycle without changing what they print; make every
    writing transaction begin `BEGIN IMMEDIATE`; and show the
    heartbeat in `status` and `doctor`.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Revision `0005` (`migrations/versions/0005_monitor.py`,
      `revision: str = "0005"`, `down_revision: str | None =
      "0004"`, each table created with `op.create_table("…", …)`):

      - `heartbeats`: `id`; `kind` (`source`, `watch`, or
        `runner`); `name` (a source id, a watch's name, or a
        process's name); `last_attempt_at`; `last_success_at`
        (nullable); `consecutive_failures` (integer, default 0);
        `last_error_kind` (nullable; an error kind or an exception
        class name, never a message); `expected_every_s` (nullable
        integer: the cadence the writer expects; `NULL` means none
        is promised); `updated_at`; unique on `(kind, name)`.
      - `monitor_cycles`: `id`; `runner` (`serve`, `check`,
        `check-once`, `fallback`, `status`, `fetch`, `storms`, or
        `alerts`); `trigger` (`manual`, `window`, `roster`,
        `alerts`, `confirm`, `retry`, `startup`, `resume`,
        `fallback`); `started_at`; `completed_at` (nullable);
        `snapshot_id` (references `snapshots.id`, `ON DELETE SET
        NULL`); `status` (`complete`, `partial`, `failed`,
        `skipped`, `error`); `detail` (nullable: a reason or an
        exception class name); indexed on `started_at`.
      - No CHECK constraint on a list of values a later phase may
        extend (`kind`, `runner`, `trigger`, `status`): the
        services validate them with literals, because changing a
        CHECK in SQLite needs a batch rebuild, which cascades
        (Phase 3's QA ledger, Step 6).
      - The downgrade drops both tables. A revision test (named
        for `0005`) upgrades from `0004` keeping every row and
        downgrades cleanly.
    </requirement>

    <requirement>
      `src/weatherbot/services/locks.py`: `ProcessLock(path, *,
      poll_s=0.5)` takes an exclusive operating-system lock on the
      first byte of a file used for nothing else
      (`msvcrt.locking(fd, LK_NBLCK, 1)` on Windows,
      `fcntl.flock(fd, LOCK_EX | LOCK_NB)` elsewhere, branched on
      `sys.platform` so strict pyright reads only the platform's
      branch). It opens the file with `os.open(path, os.O_RDWR |
      os.O_CREAT)`, never truncating it, because a Windows lock is
      mandatory and a second opener must not disturb the holder;
      the holder's process id and start instant go to a sidecar
      `<path>.info`, written only after the lock is taken, for
      diagnostics. `acquire(wait_s)` retries until `wait_s` has
      passed and then raises `LockBusyError` (a usage-level error
      the commands print as "another cycle is running; try
      again"); `acquire_async(wait_s)` waits with `await
      asyncio.sleep(poll_s)` between tries, so `serve`'s event
      loop, which Phase 5's web server will share, never blocks;
      `held(path)` reports whether another process holds it (a try
      without waiting, released at once). The operating system
      releases the lock when the process ends. The cycle lock is
      `data_dir/cycle.lock`, and `open_database` takes
      `data_dir/migrate.lock` around its backup and upgrade, so
      two processes that open a database behind the head migrate
      it once.
    </requirement>

    <requirement>
      Writing transactions. Every transaction that writes — every
      repository's `_writing` path and every service transaction
      that stores (snapshots, assessments, locations, settings,
      heartbeats, cycles) — begins with `BEGIN IMMEDIATE`, and
      read-only transactions stay deferred; `BUSY_TIMEOUT_MS`
      becomes 30,000. A test runs two processes (each
      `sys.executable` with a small script on the same temporary
      database) that write in overlapping transactions, and both
      succeed.
    </requirement>

    <requirement>
      `src/weatherbot/services/monitor.py`:

      - `CycleTrigger`, the literal of the nine triggers above;
        `CycleResult` (frozen): `cycle_id`, `trigger`, `runner`,
        `status`, `snapshot` (or `None` when skipped), `assessed`
        (the `AssessedLocation`s), `drift_warnings`, `started_at`,
        `completed_at`.
      - `MonitorService(engine, *, paths, settings, network, now,
        runner, listeners=())`. `async run_cycle(trigger, *,
        snapshot=None, assess=True) -> CycleResult`: take the
        cycle lock with `acquire_async` (`[monitor]
        cycle_lock_wait_seconds`, default 120; past it, record and
        return a `skipped` cycle whose detail says another cycle
        held the lock); record the cycle as started; fetch and
        store a snapshot through `SnapshotService` — or, when
        `snapshot` is given, use that stored snapshot (for `status
        --no-fetch`); with `assess` (the default), assess and
        store every location through `AssessmentService` (`fetch`,
        `storms`, and `alerts` pass `assess=False`: they fetch,
        store, and record, and decide nothing); record the
        heartbeat; record the cycle as complete, partial, or
        failed by the snapshot's status; call each listener with
        the result after the commit (Phase 5's server-sent events
        subscribe here; Phase 4 logs); and release the lock. Any
        other exception records the cycle as `error` with its
        class name, releases the lock, and propagates.
      - Heartbeat rules: each `source` row a fetching cycle
        touches records `last_attempt_at`; `ok` and `not_modified`
        set `last_success_at` and reset `consecutive_failures`;
        `failed` increments it and records the error kind;
        `skipped` changes nothing else and clears the row's
        cadence, so a source that is not needed is never stale and
        never failing. A cycle over a stored snapshot (`status
        --no-fetch`) records no source row. Only a scheduled
        runner sets a cadence (`expected_every_s`): Step 5's
        `serve` and `check` loops set 3 hours (10,800 s, NHC's
        product spacing) on the source rows their cycles touch and
        their own interval on their runner and watch rows, and
        Step 6's hourly fallback sets one hour on its own
        `fallback` row; every other writer leaves a row's cadence
        as it is, so a manual command never makes data look stale,
        and a clean stop of a loop clears its runner row's
        cadence. The `runner` row (the process's name:
        `check-once`, `status`, `fetch`, `storms`, or `alerts`
        here) records the cycle's completion as its success.
      - One path: `status` (fetching, and `--no-fetch` with the
        latest stored snapshot), `check --once`, and — with
        `assess=False` — `fetch`, `storms`, and `alerts` (each
        fetching unless `--no-fetch`) all go through
        `MonitorService`, under the one lock. What they print is
        unchanged, and so are their documents except for
        `status`'s new `staleness` field; a `skipped` cycle makes
        each print "another cycle is running; try again" and exit
        1.
    </requirement>

    <requirement>
      `src/weatherbot/services/health.py`: `Staleness` (frozen:
      `kind`, `name`, `last_success_at`, `expected_every_s`,
      `age_s`, `stale`) and the pure `staleness(rows, now) ->
      tuple[Staleness, ...]`: a row with an expected cadence is
      stale when it has no success or `now - last_success_at > 2 ×
      expected_every_s`; a row without one is reported and never
      stale. A `HeartbeatRepository` (in `repositories.py`, with
      `record(...)` and `rows()`) holds the reads and writes.
      `status` prints a yellow banner above the locations when any
      row is stale ("Stale data: <name> last succeeded <age> ago;
      expected every <cadence>.") and lists every row in its
      document's `staleness` (integer seconds, so the schema holds
      no decimal number). `doctor` adds a `heartbeat` check —
      `skip` when no row carries a cadence (a fresh install, or a
      machine where no scheduler has run, so both alarm proofs
      keep exiting 0) and when the database did not open, `pass`
      when none is stale, `fail` when one is — and lists the rows
      in its document. Every `doctor` check that reads the
      database, this one and the later ones, reads `skip` when the
      database did not open, so the stamped half of the alarm
      proofs still prints one JSON document whose only failure is
      the database.
    </requirement>

    <requirement>
      `src/weatherbot/cli/check.py`: `weatherbot check --once
      [--json]` runs one cycle with the trigger `manual` and the
      runner `check-once`, and prints, for each location, the
      level line, the changes, and (from Step 3) the
      notifications, then the cycle's status; its document is
      `check`. It exits 0 on a complete cycle, 1 on a partial,
      failed, or skipped one, and 2 on a usage error. Without
      `--once` it exits 2 saying the monitor loop arrives with the
      scheduler (Step 5 replaces that). Register it in
      `cli/__init__.py` as `app.command("check")(check.check)`,
      beside the existing lines.
    </requirement>

    <requirement>
      `src/weatherbot/cli/config.py` (a `config` group added with
      `app.add_typer(config.app)`): `config show [--json]` prints
      every setting's table, key, effective value, and origin
      (`default`, `file`, or `environment`, with the variable's
      name); `config path [--json]` prints the settings file, the
      data directory, the database, the backups, and the lock
      files. Their documents are `config` (each entry's table,
      key, value as a JSON value, origin, and variable name) and
      `config-path` (the paths), with integer bounds only.
      `[monitor] cycle_lock_wait_seconds` (default 120, 1 to
      3,600) joins `Settings` as `MonitorSettings` with its
      literal `("monitor", "cycle_lock_wait_seconds"):
      "WEATHERBOT_MONITOR_CYCLE_LOCK_WAIT_SECONDS"` override.
      `DOCUMENTS` gains `check`, `config`, and `config-path`
      (ten); `scripts/export_schemas.py` writes their schemas.
    </requirement>

    <requirement>
      Tests, every one offline unless marked live, under unique
      basenames, and none that skips on Windows:

      - `tests/services/test_monitor.py`: a cycle over
        `recorded_services()`'s answers stores one snapshot, one
        assessment per location, the source and runner heartbeats,
        and a `complete` cycle; a failed source increments its
        failures and a later success resets them; a skipped source
        is neither stale nor failing; a held cycle lock gives a
        `skipped` cycle; an exception records `error` and releases
        the lock; listeners see the committed result; `status`,
        `fetch`, `storms`, `alerts`, and `check --once` each
        record their runner; a cycle over a stored snapshot
        records no source row; no manual command sets a cadence.
      - `tests/services/test_locks.py`: a second holder in another
        process waits and then raises `LockBusyError`; a second
        process's probe neither truncates the lock file nor reads
        the holder's sidecar; `acquire_async` lets other tasks run
        while it waits; `held` sees another process's lock; the
        lock is released when the holding process exits; two
        processes opening a database behind the head migrate it
        once.
      - `tests/services/test_health.py`: under a frozen clock, a
        source row last successful 7 hours ago with a 3-hour
        cadence is stale, one 5 hours ago is not, a row with no
        cadence never is, and a row never successful is stale.
      - `tests/services/test_writing_transactions.py`: the
        two-process test above.
      - `tests/cli/test_status_staleness.py`: after a cycle
        recorded as a scheduled runner's (the test sets the rows'
        3-hour cadence as Step 5's loops will), `status
        --no-fetch` with the runtime clock 7 hours later prints
        the banner and lists the stale rows in its document, and
        after a manual cycle alone it prints none.
      - `tests/cli/test_check_command.py` and
        `tests/cli/test_config_command.py`: exit codes, documents
        against their committed schemas, origins (a file value, an
        environment value), and paths under the test's temporary
        directory.
      - `tests/live/test_monitor_live.py` (`live`): `check --once`
        against the live services with both landmarks in a
        temporary data directory stores a cycle with fresh
        heartbeats.
      - Update in place, keeping names: the `DOCUMENTS` count in
        `tests/cli/test_documents.py` (ten), and the table set in
        `tests/services/test_tables.py`, whose `LATER_PHASES`
        loses `heartbeat`.
    </requirement>

    <requirement>
      Documents. `README.md`'s "Commands": `weatherbot check
      --once` and `weatherbot config show` / `config path`, added
      after the existing lines with no new `## ` heading before
      `weatherbot locations evacuation` (Phase 3's check 47).
      `CONTRIBUTING.md`: the cycle, its lock, the heartbeat, and
      the staleness rule. `AGENTS.md`: the services own the one
      cycle path, and every fetching command goes through it.
      `CHANGELOG.md`: this step's entries in the Phase 4 group.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with its repo-relative path as a comment, as every
      existing one does.
    </requirement>
  </requirements>
</task>
```

### Step 2 acceptance criteria

- Revision `0005` follows `0004` and creates `heartbeats` and `monitor_cycles`;
  its revision test passes, and `doctor` reports the head.
- `MonitorService.run_cycle` stores the snapshot, every location's assessment,
  the heartbeat, and the cycle record under the cycle lock; `status` and `check
  --once` go through it, and `fetch`, `storms`, and `alerts` through its
  fetch-only form; and Phase 3's `status` tests and documents pass unchanged
  apart from the new `staleness` field.
- A second process waiting on the cycle lock gets a `skipped` cycle without
  blocking its event loop; two processes writing overlapping transactions both
  succeed; two processes opening a database behind the head migrate it once.
- Under a frozen clock the staleness rule flags a source row 7 hours after its
  last success on a 3-hour cadence, and `status` shows it in its banner and its
  document.
- A failed source increments its consecutive failures and a later success resets
  them; a skipped source is never stale or failing; no manual command sets a
  cadence, and a cycle over a stored snapshot records no source row.
- `check --once` exits 0, 1, and 2 as specified; `config show` names each
  value's origin and `config path` the local paths; `DOCUMENTS` holds ten
  schemas, each committed.
- `doctor --offline --json` on a fresh temporary database still exits 0 with the
  `heartbeat` check skipped, and Phase 2's and Phase 3's alarm proofs pass.
- **Deployed & verified:** after the merge, `doctor --offline --json` on the
  operator's machine, printing only the database fields and the heartbeat
  check's status, reports revision `0005` at head `0005`; a live `check --once`
  with the two landmarks in a temporary data directory stores a complete cycle
  with fresh heartbeats; and the first `ci.yml` and `phase-verify.yml` runs on
  `main` are green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, SAST
  clean, dependency audit clean with no dependency added — and no cycle log line
  or record carries a coordinate, a distance, a bearing, a URL above DEBUG, or
  an exception message.

---

## Step 3 — The notification policy and the notification log ✅

**Status:** Complete — PR #43 (2026-10-22)

> **Goal:** Decide, once per stored assessment, what to tell the operator, by a
> policy that cannot hold back an escalation. `weatherbot.services.policy` is
> pure: from a location's policy state (its announced level and the assessment
> that announced it, its pending held drop, and the instants its recent events
> were sent), the new assessment and its change events, the settings, and the
> cycle's instant, `decide` returns one decision per trigger — `escalation`,
> `sent`, `repeat`, `quiet_hours`, `held`, `withdrawn`, or `informational` — and
> at most one notification whose text names and never locates. Revision `0006`
> (`migrations/versions/0006_notifications.py`) creates `notifications`,
> `notification_decisions`, and `notification_deliveries`;
> `weatherbot.services.notifications.NotificationService` runs the policy inside
> every cycle after the assessments commit, stores the decisions and the
> notification once, and delivers it through the in-app log channel, the first
> `Channel`; a held drop asks for a confirmation cycle 5 minutes later;
> `weatherbot notify log` prints the log; and
> `scripts/build_notification_goldens.py` freezes Irma's notification timelines
> at both landmarks, under the defaults and under strict settings, after the
> operator reviews them, while invariant tests hold the policy over all eight
> replays. This step lands the decisions; Step 4 delivers them to the desktop,
> and Step 5 runs the confirmation cycle on schedule.

**Branch:** `feature/phase04-step3-notification-policy`

**Deploys:** the operator's machine → the local database migrates to revision
`0006` at the first command after the merge, after its online backup; `doctor`
must report `0006` at head `0006`. GitHub Actions → the first `ci.yml` and
`phase-verify.yml` runs on `main` must be green.

| Setting      | Cost                                       | Balanced                             | Quality                                    |
| ------------ | ------------------------------------------ | ------------------------------------ | ------------------------------------------ |
| Model        | Sonnet 5.5                                 | Gemini 4 Argon                       | Opus 5.5                                   |
| Backup       | Gemini 4 Argon — Antigravity · Effort High | Opus 5.5 — Claude Code · Effort High | Gemini 4 Argon — Antigravity · Effort High |
| Platform     | Claude Code                                | Antigravity                          | Claude Code                                |
| Effort       | Effort XHigh                               | Effort High                          | Effort XHigh                               |
| Thinking     | —                                          | On                                   | —                                          |
| Conversation | **New**                                    | **New**                              | **New**                                    |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

> Ran 2026-10-22: Balanced — Gemini 4 Argon · Effort High on Antigravity wrote the step and stopped before its first commit; the column's Backup — Opus 5.5 · Effort High on Claude Code reviewed it against this task block, fixed a held drop showing through another trigger's notification, and finished it.

**Model rationale:** Step 3 is coding with a planning secondary category: the
policy's rules are fixed by this roadmap, but turning them into a pure function
with persistent state — an announced level, held drops resolved by a later
cycle, cooldown keys, quiet hours in a time zone, idempotent decisions — and
freezing its output through one operator review is new problem-solving, and a
wrong rule here is the silent failure the project roadmap warns of. Its overall
complexity is High and it is novel, which is the ladder printed above. The
columns differ in depth and maker: Balanced runs Gemini 4 Argon on Antigravity
at Effort High with thinking on; Quality runs Opus 5.5 on Claude Code at Effort
XHigh (always thinking, so `—`) for the deepest search of the policy's edge
cases; Cost runs Sonnet 5.5 on Claude Code at Effort XHigh, the strongest
reasoning the cheaper Claude model offers. Google AI Pro funds Antigravity and
the claude.ai Max subscription funds Claude Code, so each column costs nothing
at the margin while its pool has headroom, and each backup comes from another
maker; as in Step 1, when Antigravity cannot serve the personal account, the
Balanced Backup (Opus 5.5 on Claude Code at Effort High) runs. The conversation
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
       feature/phase04-step3-notification-policy`
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
       Phase 4 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 4`
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

    THIS STEP writes the text that leaves the terminal. Every
    title and body line is built from the location's name, the
    level and its label, the deciding rule's trigger text
    (`services.assessments.RULE_TRIGGERS`), storm names, advisory
    numbers, product codes, and `ChangeEvent.detail` — never a
    coordinate, a distance, a bearing, an arrival instant, a URL,
    or a key — and a test over every notification of the eight
    replays proves it. The goldens and their review hold landmark
    names and public storm names only. Log lines name the
    location, the decision, and the trigger, never the text of a
    notification about the operator's location above DEBUG. The
    policy module is pure — no clock, file, environment, logging,
    network, or database — and a scan proves it, as the engine's
    does. No dependency is added.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 4 (Monitoring and
    notifications). Step 3: The notification policy and the
    notification log.

    Current state (as of Phase 4 Step 2):

    - The head is `0005`. `MonitorService.run_cycle(trigger)`
      (`services/monitor.py`) fetches, stores, assesses through
      `AssessmentService` (one transaction;
      `AssessedLocation.created` is false for an assessment stored
      before, whose changes are the stored ones), records the
      heartbeat and the cycle, and calls its listeners after the
      commit. `status`, `fetch`, and `check --once` go through it.
      `CycleTrigger` already holds `confirm`.
    - Carry-over from Step 1: `tests/cli/test_storage_growth.py`
      bounds a second unchanged `status` at 128 KiB (64 KiB
      measured at Step 1, before Step 2's rows). The decisions
      and notifications this step writes each cycle count against
      it: re-measure before the PR.
    - Carry-over from Step 2 (PR body has the details): Step 2's
      rows add no page (64 KiB again on three `dbstat` runs:
      heartbeats update in place, one `monitor_cycles` row a
      cycle). `MonitorService._locked` runs `fetch_snapshot`,
      then `AssessmentService.assess` (its own transaction), then
      one `writing_session` that records the source and runner
      heartbeats and `CycleRepository.finish`; `decide_cycle`
      belongs after the assessments commit and its own
      transaction must begin `IMMEDIATE` (`writing_session`;
      `tests/services/test_writing_transactions.py` scans
      `services/` for a plain `Session(...).begin()`). The cycle
      row reads `started` until it ends, a status outside the
      five final ones. Listeners are called for `skipped` cycles
      too, and one that raises is logged by class only. Every
      fetching command runs through `cli/snapshots.run_cycle`
      (`fetch`, `storms`, `alerts`, `status`, `check --once`), and
      `check --once` with no stored location still runs the
      cycle.
    - The seven change kinds and their fields
      (`models/assessment.py`): `level_changed` (`previous_level`,
      `level`, `direction` up, down, or initial, `rule`),
      `advisory_issued` (`atcf_id`, `storm_name`, `advisory`,
      `previous_advisory`, `in_cone`), `official_added`,
      `official_changed`, `official_removed` (`product`
      `nws_alert` with `alert_id`, `previous_alert_id`, and codes,
      or `watch_warning_segment` with `atcf_id`, `storm_name`,
      `advisory`, and codes), `cone_entered`, `cone_left`; every
      event's `detail` is a plain sentence with names and codes.
      `diff` emits them from any two consecutive assessments,
      complete or not. An `Assessment` carries `level`, `rule`,
      `official` (each `OfficialProduct` with `covers` and
      `expires_at`), `unavailable` (each `UnavailableInput`
      identified by `kind`, `source_id`, `atcf_id`, and
      `threshold_kt`), `as_of`, and `origin`.
    - Measured on 2026-10-21 by replaying the eight storm-landmark
      pairs through `ReplayService.timeline` with the default
      thresholds: every replay step carries a new advisory (an
      `advisory_issued` event at every step), and each pair's
      unavailable inputs are the same at every step except Ian's
      last three (at level 1, with no level change). A scratch
      simulation of this step's policy with the defaults sends 38
      notifications for Irma at Miami-Dade (4 escalations, 3
      drops, 34 in-cone advisories, 1 cone entered, 3 official
      products) and 25 for Irma at Nassau (6 escalations, the
      second 2-to-3 twelve hours after the first, 3 drops, 20
      advisories, 2 cones, 4 official products), and 36 and 23
      under the strict settings (a 24-hour cooldown and quiet
      hours all day), with every escalation still sent; all 29
      escalations of the eight replays are sent under both; no
      step is held; and no identical non-escalation event repeats
      within 12 hours.
    - Phase 3's check 32 reads exactly the seven `CHANGE_KINDS`,
      and this step adds none: a decision is a policy record, not
      a change event. Phase 3's check 33 reads exactly the eight
      files in `tests/golden/replay/`; this step's goldens go in
      `tests/golden/notifications/`. `scripts/build_goldens.py`
      (candidates written with null approvals, `--check`,
      `--review-only` with a combined review SHA-256, and
      `--approve-date YYYY-MM-DD --review-sha256 SHA` only after
      the operator's explicit approval) is the approval workflow
      to mirror, and `scripts/ladder_data.public_landmarks()`
      builds the two landmarks.
    - Phase 3's check 38 requires `Thresholds` to hold exactly the
      six thresholds, so the policy's settings live in a new
      `[notifications]` table. Phase 3's check 24 needs
      `ENVIRONMENT_OVERRIDES` literal and one class each named
      `Settings` and `EngineSettings`.

    Files to read (every file before drafting):
    - docs/roadmap/phase04-roadmap.md (Overview and its design
      rationale — the policy bullets above all — Current State,
      Steps 1 and 2, this step, and Steps 4 and 5, which deliver
      and schedule what this step decides).
    - docs/roadmap/ROADMAP.md (Phase 4, section 4.2) and
      docs/brief/weatherbot-v2-brief.md (section 9).
    - src/weatherbot/models/assessment.py,
      src/weatherbot/engine/changes.py,
      src/weatherbot/services/assessments.py, monitor.py,
      replay.py, config.py, disclaimer.py;
      src/weatherbot/services/persistence/repositories.py and
      tables.py.
    - scripts/build_goldens.py, scripts/ladder_data.py,
      tests/golden/replay/ (one file),
      tests/engine/test_golden_replays.py,
      tests/engine/scenarios.py, tests/test_architecture.py.
    - src/weatherbot/cli/check.py, documents.py;
      tests/cli/cli_support.py.
    - CONTRIBUTING.md, AGENTS.md, CHANGELOG.md,
      docs/ALERT-LADDER.md.
  </context>

  <goal>
    Ship the pure policy, revision `0006`, `NotificationService`
    with the in-app log channel, the confirmation request, `notify
    log`, the notification-golden builder with the two
    operator-approved Irma goldens, and the invariant, scenario,
    and privacy tests; wire the policy into every cycle so each
    stored assessment is decided exactly once.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `src/weatherbot/services/policy.py` (pure: it imports models
      and the standard library's `datetime`, `zoneinfo`,
      `dataclasses`, and `typing` only, and reads no clock):

      - `PolicyState` (frozen): `announced_level` (or `None`
        before the location's first decision);
        `announced_unavailable` (the identities — `kind`,
        `source_id`, `atcf_id`, `threshold_kt` — of the announcing
        assessment's unavailable inputs); `announced_expiries`
        (the `expires_at` of every official product that covered
        the location in the announcing assessment); `pending_held`
        (a held drop's level and how many times it has been held,
        or `None`); and `last_sent` (each event key's latest sent
        instant). `PolicySettings` (frozen): `cooldown` (a
        `timedelta`), `quiet_hours` (`None`, or a start and an end
        wall-clock time and a `tzinfo`), `confirm_after` (a
        `timedelta`), and `max_holds` (default 3).
      - `decide(state, assessment, changes, settings, now) ->
        Decided`, where `Decided` holds the decisions, the new
        state, the notification (or `None`), and the confirmation
        instant (or `None`). Each decision names its trigger —
        `level` for the level decision, `held` for the settlement
        of a pending drop, or the change event's kind — its
        position (the event's index in `changes`, or −1 for a
        `level` or `held` decision), its event key, the decision,
        and the announced level after it; one assessment never has
        two decisions with the same trigger and position.
      - The level. Let A be the announced level and L the
        assessment's, and say the assessment is *missing an input*
        when it names an unavailable input whose identity is not
        in `announced_unavailable` (a source failed this cycle
        that had answered before). No A: L of 2 or more is an
        `escalation`, L of 1 is `informational`; either sets A to
        L. L above A: `escalation`, and A becomes L. L below A
        with no pending held drop: the drop is `held` when the
        assessment is missing an input, or when it carries no
        `advisory_issued` event while no instant in
        `announced_expiries` is at or before `assessment.as_of`. L
        below A with a pending held drop: the drop is held again
        only while the assessment is still missing an input, at
        most `max_holds` holds in all — the no-advisory test never
        holds the same drop twice — and past that it is decided as
        a drop whose text says "at least". A drop that is not held
        is decided against its key `("level", A, L)`: `repeat`
        when that key was sent within the cooldown, `quiet_hours`
        when L is 1 or 2 and `now` falls in quiet hours, else
        `sent`; each of the three sets A to L. A held drop leaves
        A unchanged, records `pending_held`, and asks for a
        confirmation cycle at `now + confirm_after`. The first
        assessment that is not held settles a pending drop: a
        `held` decision of `withdrawn` when L is A or above (and
        an `escalation` beside it when L is above), otherwise the
        drop's own decision. Every `level_changed` event is the
        `level` decision's event when one exists, and otherwise
        `informational`. The rule is the same for replay
        assessments; measured, it holds none of them (every replay
        step carries a new advisory and keeps its inputs).
      - The other triggers, each decided against its key:
        `advisory_issued` with `in_cone` true (`("advisory",
        atcf_id, advisory)`), `cone_entered` (`("cone",
        atcf_id)`), and `official_added` and `official_changed`
        (`("official", "nws_alert", codes)` for an NWS alert, so
        an update that keeps its codes is the same event, and
        `("official", "watch_warning_segment", atcf_id, codes)`
        for NHC's segments). In a cycle with an escalation each is
        `sent` unless it is a `repeat`; otherwise it is `repeat`
        inside the cooldown, `quiet_hours` when L is 1 or 2 inside
        quiet hours, else `sent`. `official_removed`, `cone_left`,
        and `advisory_issued` without a covering cone are
        `informational`.
      - The notification: present exactly when a decision is
        `escalation` or `sent`; one per location per cycle;
        `title` is "<location>: level <A>, <label>", A being the
        announced level after the decisions — L, except while a
        drop is held, so a held drop never shows through another
        trigger's notification, and the other triggers' quiet
        hours read the same level (amended in Step 3: with L, a
        newly failed NWS source during a Hurricane Warning sent
        "level 1, All Clear" beside an in-cone advisory); when a
        `level` decision was sent, the body's first line says the
        level — "Level rose to L: <trigger>", "Level fell to L.",
        "Level fell to at least L.", or "Level L: <trigger>" for
        the first, where <trigger> is the deciding rule's text in
        `RULE_TRIGGERS`, which already ends in a period — and
        every line after it, or every line when no `level`
        decision was sent, is a sent trigger's
        `ChangeEvent.detail`, at most four lines in all;
        `escalation` is true when a decision is `escalation`.
      - Quiet hours: a start after the end spans midnight; a start
        of `00:00` with an end of `24:00` means all day; a start
        equal to the end is refused when the settings load. An
        instant is converted to the settings' zone before
        comparing.
    </requirement>

    <requirement>
      Revision `0006`
      (`migrations/versions/0006_notifications.py`, `revision: str
      = "0006"`, `down_revision: str | None = "0005"`, each table
      created with `op.create_table("…", …)`):

      - `notifications`: `id`; `location_id` (references
        `locations.id`, `ON DELETE CASCADE`, nullable for a
        notification about the monitor itself); `assessment_id`
        (references `assessments.id`, `ON DELETE CASCADE`,
        nullable); `cycle_id` (references `monitor_cycles.id`, `ON
        DELETE SET NULL`, nullable); `kind` (`location`,
        `degraded`, `recovered`, `stale_monitor`, `test`); `level`
        (nullable, 1 to 5, checked); `escalation`; `title`; `body`
        (the lines, as JSON); `created_at`.
      - `notification_decisions`: `id`; `location_id` and
        `assessment_id` (both cascading); `change_position` (not
        null: the event's position, or −1 for a level decision
        with no event, so the unique key below holds — SQLite
        treats nulls as distinct); `trigger` (`level`, `held`, or
        a change kind); `event_key`; `decision` (one of the
        seven); `level_after` (nullable); `notification_id`
        (references `notifications.id`, `ON DELETE SET NULL`,
        nullable); `decided_at`; unique on `(assessment_id,
        trigger, change_position)` so an assessment is decided
        once.
      - `notification_deliveries`: `id`; `notification_id`
        (cascading); `channel` (`log`, `toast`); `attempted_at`;
        `result` (`delivered`, `failed`, `disabled`,
        `unavailable`); `detail` (nullable: an error kind, an
        HRESULT, or a setting's name — never content).
      - No CHECK constraint on a list of values a later phase may
        extend (`kind`, `trigger`, `decision`, `channel`,
        `result`): the services validate them with literals,
        because changing a CHECK in SQLite needs a batch rebuild,
        which cascades (Phase 3's QA ledger, Step 6).
      - The downgrade drops the three tables, newest first. A
        revision test named for `0006` upgrades from `0005`
        keeping every row.
    </requirement>

    <requirement>
      `src/weatherbot/services/notifications.py`:

      - `Channel`, a protocol: `name` and `async
        deliver(notification) -> Delivery(result, detail)` (async,
        because Step 4's toast waits briefly for Windows' failure
        event and Phase 7's ntfy channel is network I/O).
        `LogChannel` is always present: storing the notification
        is its delivery, so it records `log`/`delivered`. Step 4
        adds the toast.
      - `NotificationService(engine, *, settings, now, channels)`:
        `async decide_cycle(cycle_id, assessed) ->
        tuple[StoredNotification, ...]` builds each location's
        `PolicyState` from its stored decisions (the latest
        `level_after`; the announcing assessment's unavailable
        inputs and the `expires_at` of the official products that
        covered the location in it; an unsettled `held` and its
        count; and the latest sent instant per event key), runs
        `decide` for every assessment with `created` true, stores
        the decisions and the notification in one transaction,
        then delivers through every channel and stores each
        delivery. An assessment already decided is never decided
        again.
      - `MonitorService.run_cycle` calls it after the assessments
        commit; `CycleResult` gains `notifications` and
        `confirm_at` (the earliest confirmation instant asked
        for). `check --once` prints each sent notification's title
        and body and, when one is due, when the confirmation cycle
        is.
      - `replay_notifications(steps, *, location, settings) ->
        tuple[NotificationStep, ...]` runs the same `decide` over
        `ReplayService.timeline`'s steps with the state kept in
        memory and `now` the step's `as_of`, and stores nothing:
        it is "Irma replayed through the monitor".
      - `[notifications]` (`NotificationSettings`):
        `cooldown_hours` (default 6, 0 to 48), `quiet_hours_start`
        and `quiet_hours_end` (`"HH:MM"`, the end up to `24:00`,
        unset by default), `quiet_hours_time_zone` (an IANA name,
        or `local`, the default, for the machine's zone, resolved
        by the service at every cycle, so a long-running `serve`
        follows a daylight-time change, and never by the policy);
        `[monitor] confirm_after_minutes` (default 5, 1 to 60);
        each with its literal `WEATHERBOT_NOTIFICATIONS_*` or
        `WEATHERBOT_MONITOR_*` override. No field joins
        `Thresholds`.
    </requirement>

    <requirement>
      `weatherbot notify log [--limit N] [--json]` (a `notify`
      group, `app.add_typer(notify.app)`, in
      `src/weatherbot/cli/notify.py`): the newest notifications
      first, each with its time (UTC and the location's zone),
      location, title, body, and every delivery's channel and
      result, and the decisions of the cycle that sent it with
      `--json`; its document is `notifications`, the eleventh in
      `DOCUMENTS` (update the count in
      `tests/cli/test_documents.py` in place).
    </requirement>

    <requirement>
      Notification goldens.
      `scripts/build_notification_goldens.py` writes
      `tests/golden/notifications/AL112017-miami-dade.json` and
      `AL112017-nassau.json` from `replay_notifications` over the
      committed corpus with `public_landmarks()`: each file holds
      the replay golden's manifest digest and ruleset, the policy
      settings it ran with, and two timelines — `defaults`, and
      `strict` (a 24-hour cooldown and quiet hours all day, 00:00
      to 24:00, which the builder sets in each landmark's NWS time
      zone, or UTC outside NWS coverage, rather than reading the
      settings file) — listing every step with a decision other
      than `informational` (advisory, issued instant, level, the
      decisions, and the notification's title and body), plus an
      `approval` with its date and the timelines' SHA-256. It
      mirrors `build_goldens.py`: candidates carry null approvals;
      `--review-only` renders the four timelines and the combined
      review SHA-256; `--approve-date YYYY-MM-DD --review-sha256
      SHA` runs only after the operator explicitly approves that
      digest in this step's session; `--check` passes only with
      matching digests; and it refuses a silent edit of an
      approved file. Before asking for approval, reconcile the
      counts with the measured ones above (38 and 25 notifications
      with the defaults, 36 and 23 strict); explain any difference
      in the review and the PR body.
    </requirement>

    <requirement>
      Tests, under unique basenames, none that skips on Windows:

      - `tests/services/test_policy.py`: every rule above on
        synthetic assessments built from
        `tests/engine/scenarios.py` — the first decision at levels
        1 and 3; an escalation from an incomplete assessment; a
        drop with a new advisory sent at once; a drop held by a
        newly failed NWS source, then withdrawn by a confirmation
        at the old level and, separately, sent by a confirmation
        still lower with the source back; a drop held three times
        while its source stays down, then sent as "at least"; a
        drop held for want of a new advisory and an expired alert,
        then sent by the next assessment even without a new
        advisory; a drop sent at once when a covering alert
        expired; an escalation and a withdrawal in one cycle
        stored as two decisions; an NWS update that keeps its
        codes a `repeat` inside the cooldown, and a watch upgraded
        to a warning `sent`; the cooldown suppressing a
        re-presented event and only inside its window; quiet hours
        across midnight in a named zone holding back only
        non-escalations at levels 1 and 2; one notification per
        location per cycle; the body's length and order.
      - `tests/services/test_notifications.py`: a cycle stores the
        decisions, the notification, and a `log` delivery; a rerun
        over the same snapshot decides nothing again; removing a
        location removes its notifications; `check --once` prints
        the sent notification.
      - `tests/services/test_notification_replay.py` (all eight
        replays): no step is held; with the defaults, the level
        decisions coincide with `diff`'s `level_changed` events;
        every escalation is sent under the defaults and the strict
        settings; at most one notification per step; and no
        notification text matches a decimal number, `km`, `deg`, a
        coordinate pair, or a time of day (a privacy scan of every
        title and body line).
      - `tests/services/test_notification_goldens.py`: the two
        goldens equal `replay_notifications` with matching
        approval digests, and `build_notification_goldens.py
        --check` passes and writes nothing.
      - `tests/test_architecture.py`: a determinism scan of
        `services/policy.py` (no clock, random, file, environment,
        logging, or I/O import or call), as the engine's, added as
        its own test so the engine's scan and its literal sets
        stay as Phase 3's checks read them.
      - Coverage: `ci.yml`'s `test` step adds
        `--cov=weatherbot.services.policy` beside
        `--cov=weatherbot.engine`, under the same `--cov-branch
        --cov-fail-under=90` (Phase 3's check 5 reads those flags
        by inclusion), and a following step runs `coverage report
        --include="*/services/policy.py" --fail-under=90` on the
        same `COVERAGE_FILE`, because the combined floor is the
        engine's to meet; the policy alone must reach 90 percent
        branch coverage.
      - `pyproject.toml`'s pytest `pythonpath` gains
        `tests/engine` (pyright's `extraPaths` already has it), so
        `tests/services/test_policy.py` imports `scenarios` in any
        collection order.
      - Update in place, keeping names:
        `tests/services/test_tables.py`'s table set gains the
        three tables and its `LATER_PHASES` loses `notification`.
      - `tests/cli/test_notify_log.py`: the log and its document
        against the committed schema.
    </requirement>

    <requirement>
      Documents. `docs/ALERT-LADDER.md` gains a "Notifications"
      section stating the policy in the words of this roadmap's
      design rationale (generated tables stay untouched).
      `CONTRIBUTING.md`: the policy, the goldens and their
      approval, and the in-app log. `README.md`'s "Commands":
      `weatherbot notify log`. `AGENTS.md`: the policy is pure and
      decides each stored assessment once. `CHANGELOG.md`: this
      step's entries.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, TOML, and
      JSON-writing script starts with its repo-relative path as a
      comment, as every existing one does.
    </requirement>
  </requirements>
</task>
```

### Step 3 acceptance criteria

- `weatherbot.services.policy.decide` implements the level, trigger, cooldown,
  quiet-hours, held, and notification rules above; the determinism scan proves
  the module pure; and `ci.yml`'s `test` job holds the policy alone to at least
  90 percent branch coverage.
- Revision `0006` follows `0005` and creates `notifications`,
  `notification_decisions`, and `notification_deliveries`; every stored
  assessment is decided exactly once, and a rerun decides nothing.
- Each cycle stores its decisions and at most one notification per location with
  a `log` delivery; `check --once` prints it, and `notify log` lists it with its
  deliveries.
- The two Irma notification goldens, defaults and strict at both landmarks, are
  approved by the operator and equal `replay_notifications`;
  `build_notification_goldens.py --check` passes.
- Across the eight replays no step is held, every escalation is sent under the
  defaults and under the strict settings, and no notification text holds a
  coordinate, a distance, a bearing, or an instant; a re-presented event inside
  the cooldown is a `repeat`.
- A drop caused by a newly failed source is held and then withdrawn or sent by
  its confirmation — or, held three times while the source stays down, sent as
  "at least" — so a fetch that recovers never shows as "fell" and "rose"; no
  drop is held twice for want of a new advisory.
- Phase 3's checks 32, 33, and 38 still pass, and no `ChangeEvent` kind or
  `Thresholds` field was added.
- **Deployed & verified:** after the merge, `doctor --offline --json` on the
  operator's machine, printing only the database fields, reports revision `0006`
  at head `0006`; a live `check --once` with the two landmarks in a temporary
  data directory stores its decisions; and the first `ci.yml` and
  `phase-verify.yml` runs on `main` are green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, SAST
  clean, dependency audit clean with no dependency added — and the privacy scan
  over every replay notification passes.

---

## Step 4 — The Windows toast channel ✅

**Status:** Complete — PR #46 (2026-10-23)

> **Goal:** Put a notification on the operator's desktop and say truthfully
> whether it got there. `weatherbot.services.toast` adds `ToastChannel`, the
> second `Channel`, over pywinrt's `winrt-Windows.UI.Notifications` 3.2.1 and
> its sibling namespaces (Windows-only dependencies, `sys_platform == 'win32'`),
> and `NullChannel`, which answers `unavailable` everywhere else; the toast
> shows the notification's title and its first two body lines (the in-app log
> keeps every line), with the disclaimer's notice as its attribution, under
> Weatherbot's own application identity, which `weatherbot notify setup`
> registers under `HKEY_CURRENT_USER` explicitly and idempotently and `notify
> setup --remove` removes; each delivery is `delivered`, `failed` (with its
> HRESULT), `disabled` (with the notification setting Windows reports), or
> `unavailable`; `weatherbot notify test` sends a test notification through
> every configured channel and records each result; `[notifications] toast`
> turns the channel off; and `doctor` judges the toast from the stored
> deliveries. A `desktop` test marker, deselected by default, holds the one test
> that shows a real toast. This step lands the desktop channel; Step 5's alarms
> and Step 6's tasks reach the operator through it.

**Branch:** `feature/phase04-step4-toast-channel`

**Deploys:** the operator's machine → with the operator's yes, `notify setup`
registers the application identity under
`HKEY_CURRENT_USER\Software\Classes\AppUserModelId\` (no administrator rights);
a `notify test` must reach the operator's desktop and record `delivered`. GitHub
Actions → the first `ci.yml` and `phase-verify.yml` runs on `main` must be
green, with the Windows-only packages absent on Ubuntu.

| Setting      | Cost                                    | Balanced                             | Quality                                    |
| ------------ | --------------------------------------- | ------------------------------------ | ------------------------------------------ |
| Model        | GPT-6.1 Sol                             | Gemini 4 Argon                       | Opus 5.5                                   |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | Opus 5.5 — Claude Code · Effort High | Gemini 4 Argon — Antigravity · Effort High |
| Platform     | Codex                                   | Antigravity                          | Claude Code                                |
| Effort       | Intelligence High                       | Effort High                          | Effort XHigh                               |
| Thinking     | —                                       | On                                   | —                                          |
| Conversation | **New**                                 | **New**                              | **New**                                    |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

> Ran 2026-10-23: Balanced column's Backup — Opus 5.5 · Effort High. The **Runs:** rule selected Balanced (its Antigravity pool read `headroom`); the operator opened the column's Backup on Claude Code.

**Model rationale:** Step 4 is coding with a knowledge secondary category: the
Windows notification platform for an unpackaged app — its application identity,
its notification setting, its failure event raised on another thread — and
Windows-only packages that must stay invisible to Ubuntu's tests, pyright, and
wheel smokes. Its overall complexity is High (platform branches through strict
typing, an honest delivery result with a bounded wait for an asynchronous
failure, a fake notifier for every test that runs on CI) and it is not novel:
the research and the measurements behind each choice are in this roadmap. The
columns differ in depth and maker: Balanced runs Gemini 4 Argon on Antigravity
at Effort High with thinking on; Quality runs Opus 5.5 on Claude Code at Effort
XHigh (always thinking, so `—`); Cost moves it to GPT-6.1 Sol on Codex at
Intelligence High. Google AI Pro, the claude.ai Max subscription, and ChatGPT
Pro 5x fund the three platforms, so each column costs nothing at the margin
while its pool has headroom; as in Step 1, when Antigravity cannot serve the
personal account, the Balanced Backup (Opus 5.5 on Claude Code at Effort High)
runs. The conversation is new per phase-boundary hygiene.

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
       feature/phase04-step4-toast-channel`
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
       Phase 4 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 4`
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

    THIS STEP adds Windows-only runtime dependencies, a registry
    write, and text on the lock screen. The five `winrt-*`
    packages (pinned `>=3.2.1`, each with `; sys_platform ==
    'win32'`) must pass `scripts/audit_deps.py`, and nothing else
    is added. The registry write is one key under
    `HKEY_CURRENT_USER\Software\Classes\AppUserModelId\` holding
    the identity's display name, written only by
    `register_identity()`, which `notify setup` and Step 6's
    `install-task` call — never as a side effect of sending — and
    removed by `notify setup --remove`; nothing under
    `HKEY_LOCAL_MACHINE` is touched. Toast XML is a template whose
    every inserted value passes `html.escape` (Phase 2's check 20
    forbids the standard library's XML modules, `xml.sax.saxutils`
    included), so a storm or location name cannot inject markup. A
    delivery's detail is an HRESULT, an error class, or a
    setting's name, never the notification's text. The test toast
    says it is a test and carries no location. The `desktop` test
    runs only when the operator says yes, on the operator's
    machine, and shows one test toast.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 4 (Monitoring and
    notifications). Step 4: The Windows toast channel.

    Current state (as of Phase 4 Step 3):

    - The head is `0006`. `services/notifications.py` defines the
      `Channel` protocol (`name`, `async deliver(notification) ->
      Delivery(result, detail)`), `LogChannel`, and
      `NotificationService`, which stores each cycle's decisions
      and notification and then delivers through every channel,
      storing each delivery (`notification_deliveries.result`:
      `delivered`, `failed`, `disabled`, `unavailable`). `notify
      log` lists notifications and deliveries; `[notifications]`
      holds the cooldown and quiet hours.
    - Carry-over from Step 3 (PR #43 body has the details):
      `Channel.deliver` receives a `StoredNotification` (`title`,
      `body` lines, `level`, `escalation`, `location_name`,
      `location_time_zone`). `NotificationService(engine, *,
      settings, now, channels)` and `MonitorService(...,
      channels=)` are the seams; `None` means `LogChannel` only,
      so the toast is passed beside it, never instead of it.
      Deliveries are stored in their own `writing_session` after
      the decisions commit, and `_deliver_one` does not catch: a
      channel that raises leaves the notification stored with no
      delivery rows and fails the cycle, so the toast returns
      `Delivery("failed", <error kind>)` instead of raising. A
      notification's level and title are the announced level,
      which stays the higher level while a drop is held.
      CI's `test (windows-latest)` took 21m24s at Step 3 (18m15s
      at Step 2) against its 25-minute `timeout-minutes`. Step 3's
      eight-replay test (29 s locally) and golden comparison
      (11 s) rebuild the timelines Phase 3's golden tests already
      build. Share them through a session-cached fixture, or trim
      other slow tests, before this step's tests land, rather than
      raising the timeout.
    - Researched on 2026-10-21: `winrt-Windows.UI.Notifications`
      3.2.1 (2025-06-06, MIT) has CPython 3.9 to 3.14 wheels for
      `win_amd64`, `win_arm64`, and (3.13, 3.14) `win32`, and
      complete typed stubs; it exposes
      `ToastNotificationManager.create_toast_notifier_with_id(aumid)`,
      `ToastNotifier.setting` (`NotificationSetting`: `ENABLED` 0,
      `DISABLED_FOR_APPLICATION` 1, `DISABLED_FOR_USER` 2,
      `DISABLED_BY_GROUP_POLICY` 3, `DISABLED_BY_MANIFEST` 4;
      reading it can raise `OSError` 0x80070490, which means
      "unknown"), `ToastNotifier.show`, and
      `ToastNotification.add_failed` (with the error code),
      `add_dismissed`, and `add_activated`, whose handlers run off
      the event loop's thread. The XML is loaded with
      `winrt.windows.data.xml.dom.XmlDocument().load_xml(text)`.
      The packages are `winrt-runtime`,
      `winrt-Windows.UI.Notifications`,
      `winrt-Windows.Data.Xml.Dom`, `winrt-Windows.Foundation`,
      and `winrt-Windows.Foundation.Collections`; none installs on
      Linux, and pyright does not analyse a `sys.platform ==
      "win32"` branch on Linux.
    - An unpackaged app shows toasts under an application user
      model ID registered as
      `Software\Classes\AppUserModelId\<id>` with a `DisplayName`;
      the libraries write it under `HKEY_CURRENT_USER`, which
      needs no administrator rights. Whether toasts persist in the
      notification center without a COM activator on build 26200
      is unconfirmed: this step's desktop test finds out and
      records it. With Do Not Disturb on, Windows 11 sends toasts
      straight to the notification center without a banner, and
      nothing tells the app.
    - Constraints: the wheel smokes of all three phases import the
      CLI and the services on Ubuntu, so every `winrt` import sits
      behind `if sys.platform == "win32":` inside the toast
      module; `filterwarnings = ["error"]` turns an import-time
      warning into a test failure; `--strict-markers` requires
      every marker registered; Phase 1's check 17 reads that the
      markers include `live:` and `corpus:` and the addopts
      `--allow-hosts` and `--strict-markers`; Phase 2's V6.2
      selects the whole `tests.cli` package, so a CLI test uses a
      fake toast and never skips; the `doctor` alarm proofs need
      `doctor --offline --json` on a fresh temporary database to
      exit 0.

    Files to read (every file before drafting):
    - docs/roadmap/phase04-roadmap.md (Overview and its design
      rationale, Current State, Step 3, this step, and Steps 5 and
      6, which send through this channel).
    - src/weatherbot/services/notifications.py, policy.py,
      disclaimer.py (`NOTICE`), config.py, doctor.py;
      src/weatherbot/cli/runtime.py, notify.py, doctor.py,
      documents.py.
    - pyproject.toml (dependencies, pytest markers and addopts),
      scripts/audit_deps.py, .github/workflows/ci.yml (the package
      job).
    - tests/cli/cli_support.py,
      tests/services/test_notifications.py,
      tests/test_architecture.py.
    - CONTRIBUTING.md, README.md ("Commands"), CHANGELOG.md.
  </context>

  <goal>
    Ship `ToastChannel` and `NullChannel`, the identity commands
    `notify setup` and `notify setup --remove`, `notify test`, the
    `[notifications] toast` switch, `doctor`'s toast check, and
    the `desktop` marker with its one real-toast test; keep
    Ubuntu's tests, pyright, and wheel smokes free of every
    Windows-only import.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Dependencies: `uv add "winrt-runtime>=3.2.1 ; sys_platform
      == 'win32'"` and the same for
      `winrt-Windows.UI.Notifications`,
      `winrt-Windows.Data.Xml.Dom`, `winrt-Windows.Foundation`,
      and `winrt-Windows.Foundation.Collections`; run `uv lock`;
      `scripts/audit_deps.py` must pass. Add nothing else.
    </requirement>

    <requirement>
      `src/weatherbot/services/toast.py`:

      - `APP_ID = "Weatherbot.Monitor"` and `DISPLAY_NAME =
        "Weatherbot"`: the application identity.
      - `toast_xml(notification) -> str`: a `ToastGeneric`
        template with the title and at most the first two body
        lines (the binding shows three text elements, the title
        and two lines; the attribution is separate), and the
        disclaimer's `NOTICE` as the attribution text, every value
        passed through `html.escape`.
      - `ToastChannel(notifier_factory=…, wait_s=2.0)`: `name =
        "toast"`; `async deliver(notification)` reads the
        notifier's `setting` (anything but `ENABLED` → `disabled`
        with the setting's name; `OSError` → carry on as unknown),
        builds the toast from `toast_xml`, subscribes to `Failed`
        (the handler hands its HRESULT to the loop with
        `loop.call_soon_threadsafe`), calls `show`, and waits up
        to `wait_s` for a failure: an exception from `show` or a
        `Failed` event is `failed` with the HRESULT in
        hexadecimal; otherwise `delivered`, meaning Windows
        accepted it. A missing identity is `unavailable` with the
        detail "run weatherbot notify setup".
      - `NullChannel`: `name = "toast"`, always `unavailable` with
        the platform's name. `toast_channel(settings) -> Channel`
        returns `ToastChannel` on Windows when `[notifications]
        toast` is on, and `NullChannel` otherwise.
      - `register_identity()`, `unregister_identity()`, and
        `identity_registered()` use `winreg` on
        `HKEY_CURRENT_USER` only, idempotently, and are the only
        code that writes the registry; off Windows they report
        "not needed" and touch nothing.
      - Every `winrt` and `winreg` import sits inside `if
        sys.platform == "win32":`, so the module imports cleanly
        on Ubuntu; the notifier factory is the seam the tests
        replace. As shipped (PR #46): the `winrt` packages load
        on the first toast, inside the Windows-only notifier, so
        importing the module loads no `winrt` module on either
        platform, and a broken install fails one toast, not every
        command.
    </requirement>

    <requirement>
      `[notifications] toast` (default `true`) with its literal
      `("notifications", "toast"):
      "WEATHERBOT_NOTIFICATIONS_TOAST"` override.
      `NotificationService` gets its channels from
      `toast_channel(settings)` beside `LogChannel`, and the CLI's
      `Runtime` gains a channel seam (as `make_fetcher` is the
      network's) so every command test runs with a fake toast.
      As shipped (PR #46): the services' default stays
      `LogChannel` alone, so no service test can show a toast,
      and the CLI's `Context.channels` passes `LogChannel` and
      `Runtime.make_toast(settings)` to every cycle and to
      `notify test`.
    </requirement>

    <requirement>
      Commands in the `notify` group: `notify setup [--remove]
      [--json]` registers or removes the identity and says which;
      `notify test [--json]` stores a `test` notification
      ("Weatherbot test notification", "If you can read this,
      toasts work.", no location), delivers it through every
      channel, prints each channel's result, and exits 1 when a
      channel's result is `failed` or `disabled`, or is
      `unavailable` on Windows with `[notifications] toast` on
      (the identity is missing); an `unavailable` toast off
      Windows exits 0. Documents `notify-setup` and `notify-test`
      join `DOCUMENTS`; update its count in place.
    </requirement>

    <requirement>
      `doctor` gains a `toast` check: `skip` off Windows or when
      no toast delivery is stored (a fresh database, so both alarm
      proofs keep exiting 0); `fail` when the latest stored toast
      delivery is `failed` or `disabled`, or — on Windows with
      `[notifications] toast` on — `unavailable`, or the identity
      is missing although a toast was delivered before; `skip` too
      when the database did not open; `pass` otherwise. Its detail
      names the setting or the HRESULT, never a notification's
      text. As shipped (PR #46): also `skip` while
      `[notifications] toast` is off, when the latest delivery is
      the expected `unavailable`.
    </requirement>

    <requirement>
      The `desktop` marker: register `"desktop: shows a real toast
      or touches the operator's Task Scheduler; run deliberately
      with -m desktop"` in `pyproject.toml` and add `and not
      desktop` to the addopts' `-m` expression. Every verifier's
      offline run uses the addopts, and its live and corpus runs
      pass `-m live` and `-m corpus`, so a desktop test never runs
      inside a verifier. `tests/desktop/test_toast_desktop.py`
      (`desktop`): with the identity registered, a real
      `ToastChannel` delivers a test notification and returns
      `delivered`; it records whether the toast stayed in the
      notification center (the operator says so) in the PR body.
    </requirement>

    <requirement>
      Tests, offline, under unique basenames, none that skips on
      Windows or Ubuntu:

      - `tests/services/test_toast.py`: `toast_xml` escapes `<`,
        `&`, and quotes in titles and lines and carries `NOTICE`;
        with a fake notifier, an enabled setting delivers, each
        disabled setting gives `disabled` with its name, an
        `OSError` on the setting still delivers, an exception from
        `show` and a `Failed` event raised from another thread
        each give `failed` with the HRESULT, and a missing
        identity gives `unavailable`; `NullChannel` is
        `unavailable`; `toast_channel` honours `[notifications]
        toast`; and importing `weatherbot.services.toast` on any
        platform imports no `winrt` module unless the platform is
        Windows (checked through `sys.modules`).
      - `tests/cli/test_notify_commands.py`: `notify test` and
        `notify setup` with a fake toast and a fake registry; exit
        codes; documents against their committed schemas.
      - `tests/services/test_doctor_toast.py`: the `toast` check's
        skip, pass, and fail.
      - `tests/services/test_notifications.py` gains: a
        notification delivered through the log and a fake toast
        stores both deliveries.
    </requirement>

    <requirement>
      No test shows a real toast unless it is marked `desktop`:
      `tests/conftest.py`'s autouse fixture sets
      `WEATHERBOT_NOTIFICATIONS_TOAST=false` after it clears the
      environment (Phase 2's check 32 reads only the kept set), so
      the live suite inside every phase's nested `--live` and
      `--post` stays silent, and the desktop tests turn it back
      on. `ci.yml`'s `typecheck` job runs on `windows-latest` as
      well as `ubuntu-latest`, so the Windows-only branches are
      type-checked in CI.
    </requirement>

    <requirement>
      Documents. `README.md`'s "Commands": `notify setup` and
      `notify test`, and the note that from this step `status` and
      `check --once` deliver their notifications through the toast
      as well as the log. `CONTRIBUTING.md`: the channel
      interface, the fake toast in tests, the `desktop` marker and
      when to run it, and the Do Not Disturb note.
      `docs/DATA_SOURCES.md` is untouched (a channel is not a
      source). `CHANGELOG.md`: this step's entries.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with its repo-relative path as a comment, as every
      existing one does.
    </requirement>
  </requirements>
</task>
```

### Step 4 acceptance criteria

- `ToastChannel` delivers through pywinrt under the `Weatherbot.Monitor`
  identity and returns `delivered`, `failed` with its HRESULT, `disabled` with
  Windows' setting, or `unavailable`; `NullChannel` answers off Windows;
  `[notifications] toast` switches the channel.
- `notify setup` registers and `notify setup --remove` removes the identity
  under `HKEY_CURRENT_USER` only; `register_identity()` is the only code that
  writes the registry, and sending never does.
- `notify test` stores a test notification with one delivery per channel and
  exits 1 on `failed` or `disabled`, and on `unavailable` on Windows with the
  toast on; no test shows a real toast unless it is marked `desktop`;
  `typecheck` runs on both runners.
- The five `winrt-*` packages carry the Windows marker; Ubuntu's tests, pyright,
  and the three phases' wheel smokes import nothing from them;
  `scripts/audit_deps.py` passes.
- `doctor --offline --json` on a fresh temporary database still exits 0 with the
  `toast` check skipped, and Phase 2's and Phase 3's alarm proofs pass.
- The `desktop` marker is registered and deselected by default;
  `verify_phase01.py --fast` still passes its marker check.
- **Deployed & verified:** with the operator's yes, `notify setup` registered
  the identity on the operator's machine; `notify test` in a temporary data
  directory raised a toast the operator confirms seeing, and its delivery row
  reads `delivered`; `pytest -m desktop tests/desktop/test_toast_desktop.py`
  passed there; and the first `ci.yml` and `phase-verify.yml` runs on `main` are
  green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, SAST
  clean, `pip-audit` clean with the five `winrt-*` packages added — and every
  inserted toast value is escaped, with nothing written outside
  `HKEY_CURRENT_USER`.

---

## Step 5 — The scheduler, `serve`, and `check` ✅

**Status:** Complete — PR #49 (2026-10-23)

> **Goal:** Run the cycle on NHC's schedule, watch for what the schedule cannot
> know, and keep running through failures and sleep.
> `weatherbot.services.scheduler.Scheduler` runs jobs on an injected clock,
> sleeping at most 60 seconds at a time against the UTC wall clock, one job at a
> time, with positive jitter, isolated failures, and one catch-up cycle after a
> gap; `weatherbot.services.schedule` defines the monitor's jobs — a fetch
> window 15 minutes after each of NHC's eight UTC product times that polls the
> roster until every active storm's advisory has moved, a roster watch every 15
> minutes (every 5 while a storm is relevant), an NWS alert watch every 5
> minutes only while a storm is relevant to a US location, a confirmation cycle
> when the policy holds a drop, retries 5, 10, and 20 minutes apart after a
> source the ladder reads fails, and a process heartbeat every 5 minutes on its
> own task; `weatherbot serve` and `weatherbot check` run the scheduler as the
> one monitor process (`data_dir/monitor.lock`), writing a rotating log file in
> the data directory; the degraded-data alarm sends a toast and a log entry when
> a source the ladder reads fails 3 times in a row, and a recovery entry when it
> answers again; and `scripts/simulate_advisory.py` proves on the operator's
> machine that a new advisory during `serve` raises a toast within one scheduler
> interval. This step lands the schedule; Step 6 registers `serve` and the
> fallback with Task Scheduler.

**Branch:** `feature/phase04-step5-scheduler`

**Deploys:** nothing beyond merge for the code — `serve` runs only when started,
and Step 6 registers it. On the operator's machine → with the operator's yes,
`scripts/simulate_advisory.py` raises one toast labelled as a simulation, from a
temporary data directory; it must record `delivered` within one scheduler
interval. GitHub Actions → the first `ci.yml` and `phase-verify.yml` runs on
`main` must be green.

| Setting      | Cost                                    | Balanced                             | Quality                                    |
| ------------ | --------------------------------------- | ------------------------------------ | ------------------------------------------ |
| Model        | GPT-6.1 Sol                             | Gemini 4 Argon                       | Opus 5.5                                   |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | Opus 5.5 — Claude Code · Effort High | Gemini 4 Argon — Antigravity · Effort High |
| Platform     | Codex                                   | Antigravity                          | Claude Code                                |
| Effort       | Intelligence High                       | Effort High                          | Effort XHigh                               |
| Thinking     | —                                       | On                                   | —                                          |
| Conversation | **New**                                 | **New**                              | **New**                                    |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

> Ran 2026-10-23: Balanced column — Gemini 4 Argon · Effort High · Thinking On on Antigravity. Selected by the **Runs:** rule (Google AI Pro pool reads headroom).

**Model rationale:** Step 5 is coding with an agentic secondary category: an
asyncio scheduler and the monitor's jobs, two long-running commands, and an
on-machine proof that drives a real toast. Its overall complexity is High — time
arithmetic in UTC, sleep and resume, a window that waits for the roster, two
watches that only trigger cycles, retries, the confirmation cycle,
single-instance locking, and an alarm with recovery — and it is not novel: this
roadmap fixes the schedule, its measured basis, and the reasons for writing the
scheduler instead of adopting APScheduler. The columns differ in depth and
maker: Balanced runs Gemini 4 Argon on Antigravity at Effort High with thinking
on; Quality runs Opus 5.5 on Claude Code at Effort XHigh (always thinking, so
`—`) for the closest audit of timing edge cases; Cost moves it to GPT-6.1 Sol on
Codex at Intelligence High. Google AI Pro, the claude.ai Max subscription, and
ChatGPT Pro 5x fund the three platforms, so each column costs nothing at the
margin while its pool has headroom; as in Step 1, when Antigravity cannot serve
the personal account, the Balanced Backup (Opus 5.5 on Claude Code at Effort
High) runs. The conversation is new per phase-boundary hygiene.

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
       feature/phase04-step5-scheduler`
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
       Phase 4 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 4`
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

    THIS STEP starts a process that runs unattended and writes a
    log file. The log file lives in the data directory
    (`logs/weatherbot.log`, rotating at 1 MiB, five files),
    carries `RedactingFilter`, and holds at INFO and above no
    coordinate, distance, bearing, arrival instant, URL query, or
    notification text about a location; at DEBUG it may hold
    redacted URLs, and `CONTRIBUTING.md` says so. The lock files
    hold a process id and an instant only. The watches send the
    roster request, one attribute-only query of the summary
    service's cone layer (a new source function with a declared
    field list), and each US location's three alert queries, at
    the client's pacing; they share one roster answer for 60
    seconds, so no two of them fetch the same URL within a minute
    (the NWS alerts documentation recommends no more than one
    request every 30 seconds; its API rate limit is not public);
    and they store no answer. `scripts/simulate_advisory.py`
    serves recorded answers through respx with every other request
    refused, in a temporary data directory, with the two public
    landmarks; its synthetic alert is built from the register's
    alert shape and carries only the landmark's public zone. The
    process ends on Ctrl+C or Task Scheduler's stop, leaving every
    transaction rolled back or committed. No dependency is added.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 4 (Monitoring and
    notifications). Step 5: The scheduler, `serve`, and `check`.

    Current state (as of Phase 4 Step 4):

    - Carry-over from Step 2: a scheduled runner builds
      `MonitorService(..., runner="serve" or "check",
      cadence_s=SCHEDULED_SOURCE_CADENCE_S)` (10,800 s), which
      promises that cadence on every source row its cycles touch;
      a skipped source still clears its own. The runner and watch
      rows' cadence is written through
      `HeartbeatRepository.record(kind, name, at=, result=,
      expected_every_s=)` (`result` is `success`, `failure`, or
      `attempt`; `expected_every_s=None` clears a cadence, the
      default `UNCHANGED` keeps it), which is also how a clean stop
      clears the runner row's cadence. `ProcessLock(path,
      poll_s=)` has `try_acquire()`, `acquire(wait_s)`,
      `acquire_async(wait_s)`, and `release()`; `held(path)` is a
      module function. `AppPaths` has `cycle_lock_path` and
      `migrate_lock_path`; add `monitor.lock` beside them.
    - Carry-over from Step 3: `CycleResult.confirm_at` is the
      earliest of the cycle's held drops' `decide_cycle` instant
      plus `[monitor] confirm_after_minutes`, or `None` when
      nothing is held; schedule one `confirm` cycle at it. The
      confirmation cycle fetches again, so it stores a new
      assessment and the policy settles the hold (withdrawn, held
      again while the input is still missing, or decided as a
      drop); a rerun over the same snapshot decides nothing.
    - Carry-over from Step 4 (PR #46 body has the details): the
      CLI's channels are `Context.channels`, `LogChannel` and
      `Runtime.make_toast(settings)` (the toast's seam, as
      `make_fetcher` is the network's); pass
      `channels=context.channels` to every `MonitorService` that
      `serve` and `check` build, as `cli/snapshots.run_cycle`
      does. The services' default stays `LogChannel` alone.
      `NotificationService.send(kind, title=, body=)` stores and
      delivers a notification that belongs to no location
      (`notify test` uses it); extend it for `degraded` and
      `recovered` rather than writing their rows by hand. The
      database-free toast has no row, so it calls
      `context.runtime.make_toast(settings).deliver(...)` with a
      `StoredNotification` whose `id` is 0 and logs the result's
      kind. A toast delivery waits up to 2 s for Windows'
      `Failed` event, inside the simulated advisory's interval.
      Command tests get a delivering `cli_support.FakeToast` and
      a registered `FakeRegistry` from `runtime(toast=,
      identity=)`; `tests/conftest.py` sets
      `WEATHERBOT_NOTIFICATIONS_TOAST=false`, so only a run
      outside pytest, such as `scripts/simulate_advisory.py`,
      shows a real toast. Never deliver through a default
      `ToastChannel()` in a test: the identity is registered on
      the operator's machine (2026-10-23), where it would show.
      Both test toasts stayed in the notification center there
      (build 26200, no COM activator). PR #46's body records the
      Windows test job's time against its 25-minute budget.
    - `MonitorService.run_cycle(trigger)` runs one cycle under
      `data_dir/cycle.lock` and returns `CycleResult` (with
      `status`, `notifications`, and `confirm_at`, the instant a
      held drop asks to be confirmed); `CycleTrigger` holds
      `window`, `roster`, `alerts`, `confirm`, `retry`, `startup`,
      and `resume`. `heartbeats` rows are `source`, `watch`, or
      `runner`, with `expected_every_s`; the staleness rule flags
      a row past twice its cadence. `check --once` runs one cycle;
      `check` without `--once` exits 2 until this step.
    - The CLI's cycles decide and deliver through `LogChannel`
      and the runtime's toast (`toast_channel(settings)` by
      default); `notifications.kind` already allows `degraded` and
      `recovered`; the policy's quiet hours hold back
      non-escalations at levels 1 and 2.
    - The roster and alert sources the watches use exist:
      `sources.nhc_current_storms` (the roster, conditional
      through the fetcher's validator store; each storm's
      `binNumber` names its map slot) and
      `sources.nws.fetch_alerts(fetcher, location)` (the point,
      county-zone, and forecast-zone queries, merged by id). The
      cone-layer query does not: `arcgis.query` always sends
      `QUERY_PARAMETERS` (`outFields=*`, the geometry), and the
      cone layer's features carry `binnumber` and `advisnum`.
      `services.network.Network.fetcher(validators)` opens one
      client; `sources.http.MemoryValidatorStore` keeps validators
      in memory. Phase 2's check 12 reads exactly one dict in
      `QUERY_PARAMETERS`; `COUNT_PARAMETERS` beside it is the
      precedent for another.
    - Measured and researched on 2026-10-21 (Overview, "Design
      rationale"): the product times are fixed in UTC (0300, 0900,
      1500, 2100 advisories; 0000, 0600, 1200, 1800 intermediates
      and outlooks); wind-speed probabilities appear no earlier
      than 15 minutes after a deadline; at three advisories the
      cone's file date came 4 to 9 minutes after the nominal time,
      while the roster was rewritten 24 minutes after (twice) or 8
      minutes before (once, naming both 21:00 advisories of
      Josephine and Vance); the roster's `max-age` is 300 s with
      304 honored, and each storm's `publicAdvisory.issuance` is
      the nominal time; the NWS alert endpoints ignore
      `If-None-Match`. One cycle costs 41 + 4S + 3L requests.
    - APScheduler is not used (Overview, "Design rationale"): its
      3.11.3 release is untyped and has an unreleased fix for a
      scheduler that stops every job after one exception, and 4.0
      is an alpha. `tests/test_architecture.py` still bans
      `apscheduler` from the engine and the models.
    - `configure_logging(level)` writes to standard error only,
      without a timestamp; under `pythonw.exe` `sys.stdout` and
      `sys.stderr` are `None`, so `print` does nothing and a
      stream handler writes nowhere.
    - `tests/cli/cli_support.py` serves every recorded answer and
      `register_alert` (in `tests/contract/fixture_support.py`)
      builds an alert from the register's description;
      `scripts/ladder_data.public_landmarks()` builds both
      landmarks, and development scripts may import shared test
      support through checkout paths (application code never reads
      tests).

    Files to read (every file before drafting):
    - docs/roadmap/phase04-roadmap.md (Overview and its design
      rationale, Current State, Steps 2 to 4, this step, and Step
      6, which registers what this step builds).
    - docs/roadmap/ROADMAP.md (Phase 4, sections 4.1 and 4.4;
      section 5, "Operations & observability strategy").
    - src/weatherbot/services/monitor.py, notifications.py,
      policy.py, toast.py, health.py, locks.py, logs.py,
      network.py, snapshots.py, config.py;
      src/weatherbot/sources/nhc_current_storms.py, nws.py,
      arcgis.py, nhc_map.py, fields.py, and http.py (the fetcher,
      its validators, `RedactingFilter`);
      tests/contract/test_field_coverage.py.
    - src/weatherbot/cli/__init__.py, runtime.py, check.py;
      tests/cli/cli_support.py; tests/contract/fixture_support.py
      (`register_alert`); scripts/ladder_data.py.
    - docs/DATA_SOURCES.md (the roster's and the alerts' rows and
      sections), CONTRIBUTING.md, README.md, CHANGELOG.md.
  </context>

  <goal>
    Ship the cone-layer attribute query, the scheduler, the
    monitor's jobs, `serve`, `check`, the log file, the
    single-instance lock, the degraded-data alarm with its
    recovery, the database-free toast for a database the code
    cannot open, and `scripts/simulate_advisory.py`; prove every
    timing rule on a fake clock and the whole chain once on the
    operator's machine.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `src/weatherbot/services/scheduler.py`: `Job` (a name, a
      function from the current instant and the job's state to its
      next due instant or `None`, an async run, and its jitter in
      seconds) and `Scheduler(jobs, *, clock, sleep, random,
      max_sleep_s=60)` with `async run(stop: asyncio.Event)`. Each
      due instant gets one positive random delay drawn once
      (`random.uniform(0, jitter)`); the loop sleeps
      `min(max_sleep_s, until the next due run)` and re-reads the
      clock on every wake; due jobs run one at a time, in due
      order, and a job still running is never started again; every
      job run is short — one poll, one watch, or one cycle — and a
      job that must wait reschedules itself instead of sleeping
      inside its run, so no job holds the queue longer than one
      cycle; a job's exception is logged with its class name and
      recorded on its heartbeat, and the loop goes on; when a wake
      comes more than 60 seconds after the instant its sleep was
      due to end (the machine slept; a long job is not a gap), the
      scheduler logs "resumed after N minutes" and runs one
      `resume` cycle before anything else. It reads no clock,
      sleep, or randomness but the injected ones.
    </requirement>

    <requirement>
      `src/weatherbot/services/schedule.py`, the monitor's jobs
      (all instants UTC):

      - `window`: due at each product time T (00, 03, 06, 09, 12,
        15, 18, 21 h) plus `[monitor] window_offset_minutes` (15),
        with up to `window_jitter_seconds` (120) of delay. Each
        run reads the roster (conditionally) and the summary
        service's cone layer (one query returning the storm ids
        and advisory numbers, no geometry) once; until every storm
        the roster lists has a public advisory issued at or after
        T and the cone layer shows that same advisory, it
        reschedules itself `roster_poll_minutes` (5) later, and
        once they agree, or at T plus `window_close_minutes` (60),
        it runs one `window` cycle. With no active storm it runs
        the cycle at once; at an hour with no new advisory it runs
        at T plus 60.
      - `roster`: every `roster_interval_minutes` (15), or
        `roster_interval_relevant_minutes` (5) while some
        location's latest assessment is above level 1, up to 30
        seconds of delay. A conditional fetch whose storms or
        advisories differ from the latest stored snapshot's runs a
        `roster` cycle; it records the `roster` watch heartbeat
        with its interval.
      - `alerts`: only while some location inside NWS coverage has
        a latest assessment above level 1, every
        `alert_interval_minutes` (5; at least 1), up to 30 seconds
        of delay: `fetch_alerts` for each such location, and an
        `alerts` cycle when any location's set of alert ids and
        `sent` instants differs from the latest stored snapshot's;
        it records the `alerts` watch heartbeat, with no expected
        cadence while idle.
      - `confirm` at a cycle's `confirm_at`; `retry` after a cycle
        in which a source the ladder reads (`nhc-current-storms`,
        `nhc-map-tropical-summary`, `nws-alerts-point`,
        `nws-alerts-zone`) failed, or an `error` cycle:
        `retry_base_minutes` (5) later, then twice and four times
        that after each further failure, at most `retry_count` (3)
        retries per run of failures, cleared by a cycle in which
        those sources answer (a failure of any other source, such
        as the graphics or the text products, retries nothing);
        and `startup` once when the process starts. The process
        heartbeat is not a queued job: its own asyncio task
        records the runner row every `heartbeat_minutes` (5), with
        `expected_every_s` set to that interval, while jobs run,
        so a slow cycle never makes the process look silent, and
        the staleness rule flags one silent for twice as long.
      - The watches keep validators in a `MemoryValidatorStore`
        for the process's life, share one in-memory roster answer
        for 60 seconds (the window and the roster watch never
        fetch it twice within a minute), store no answer, and
        share the client's pacing.
      - `sources/nhc_map.py` gains `fetch_cone_advisories(fetcher,
        catalog) -> SourceResult` over a new
        `arcgis.attributes(fetcher, service, layer, fields)` and
        its own parameters mapping (`where=1=1`, the named
        `outFields`, `returnGeometry=false`, `f=json`) beside
        `COUNT_PARAMETERS`, reading `binnumber` and `advisnum`
        through `Fields` with its `FIELDS_READ` declared; the
        register's "Fields v2 uses" for the cone layer and
        `tests/contract/test_field_coverage.py` stay equal to it,
        and a recorded cone-layer capture answers it in tests.
      - The degraded-data alarm: after every cycle and watch, a
        ladder source's row (`nhc-current-storms`,
        `nhc-map-tropical-summary`, `nws-alerts-point`,
        `nws-alerts-zone`) or a watch row whose consecutive
        failures reach `degraded_after_failures` (3) sends one
        `degraded` notification ("Weatherbot: <source> failed 3
        times in a row since <instant>; levels may read as
        floors."), through the log and the toast, once per run of
        failures; its success afterwards sends a `recovered` entry
        (a toast only if the degraded one reached the toast).
        Quiet hours hold either back only while every location's
        latest level is 1 or 2.
      - `[monitor]` gains every interval named above —
        `window_offset_minutes`, `window_jitter_seconds`,
        `window_close_minutes`, `roster_poll_minutes`,
        `roster_interval_minutes`,
        `roster_interval_relevant_minutes`,
        `alert_interval_minutes`, `retry_base_minutes`,
        `retry_count`, `degraded_after_failures`, and
        `heartbeat_minutes` — each an integer whose lower bound is
        at least 1, with its literal `WEATHERBOT_MONITOR_*`
        override, so `config show` lists them.
      - A database the code cannot open: when `open_database`
        refuses a revision newer than the running code (a checkout
        migrated it past the installed copy) or fails a migration,
        `serve`, `check`, and the fallback log it and send one
        toast straight through `ToastChannel`, with no database
        ("Weatherbot cannot open its database: <the reason's
        kind>; reinstall or restore it."), once per process start,
        and exit 1.
    </requirement>

    <requirement>
      Commands. `weatherbot serve` and `weatherbot check` (without
      `--once`) take `data_dir/monitor.lock` (`ProcessLock` with
      no wait; a second one exits 2 with "the monitor is already
      running", naming the holder's process id and start instant
      from the lock file), configure the log file, and run the
      scheduler until Ctrl+C (or the process is stopped) with the
      runner names `serve` and `check`; a clean stop clears the
      runner row's cadence, so a monitor stopped on purpose never
      reads as stale (one killed by Task Scheduler or a crash
      keeps it, and the fallback notices). `serve`'s docstring
      says Phase 5 adds the web server to the same process and
      loop. Register `app.command("serve")(serve.serve)` beside
      the existing lines; `check` keeps `--once`.
    </requirement>

    <requirement>
      Logging. `configure_logging(level, *, log_file=None)` adds,
      when given a file, a rotating handler (1 MiB, five files)
      with UTC ISO-8601 timestamps and `RedactingFilter`; with
      `sys.stderr` `None` (`pythonw.exe`) it installs only the
      file handler and points `sys.stdout` and `sys.stderr` at
      `os.devnull` so nothing raises. `serve` and `check` write
      `data_dir/logs/weatherbot.log`; `config path` lists it.
    </requirement>

    <requirement>
      `scripts/simulate_advisory.py` (a development tool, run from
      a checkout with the dev group): in a temporary data
      directory, with both landmarks stored and every request
      answered by the recorded fixtures through respx (all others
      refused), the roster watch at its 1-minute minimum, and the
      real toast channel, it starts the `serve` scheduler, waits
      for the startup cycle, then serves a roster whose storm has
      the next advisory together with a synthetic Hurricane
      Warning alert covering the Miami-Dade landmark's forecast
      zone (built with `register_alert`'s shape), and waits. It
      passes when a level-5 escalation notification for the
      landmark (named "simulated Miami-Dade") is stored within one
      scheduler interval of the switch — the roster watch's
      interval plus one minute for its jitter, the cycle, and the
      toast's wait — with a toast delivery reading `delivered`,
      prints the elapsed time and the delivery, and stops the
      scheduler.
    </requirement>

    <requirement>
      Tests, offline, under unique basenames, none that skips on
      Windows or Ubuntu:

      - `tests/services/test_scheduler.py` (a fake clock and
        sleep): sleeps never exceed 60 seconds; a job runs at its
        due instant plus its drawn delay; a running job is not
        started twice; a failing job is logged and the loop goes
        on; a wake 3 hours after its sleep was due to end runs
        exactly one `resume` cycle first, while a job that ran for
        5 minutes is not taken for a gap; the heartbeat task keeps
        writing while a slow cycle runs; the clock crossing the
        2026-11-01 daylight-time change changes nothing (all UTC).
      - `tests/services/test_schedule.py` (fake network answers
        and clock): each window opens at T + 15 minutes within its
        jitter; a window with an active storm polls until the
        roster and the cone layer agree on an advisory issued at
        or after T — whether the roster leads the cone layer or
        trails it — and runs once at T + 60 minutes when they
        never do; with no storm it runs at once; the roster watch
        runs a cycle only when the storms or advisories change and
        tightens to 5 minutes while a location is above level 1;
        the alert watch runs only while a US location is above
        level 1 and only on a change of ids or `sent`; retries
        come 5, 10, and 20 minutes apart after a ladder source
        fails, never after a graphics or text-product failure, at
        most three per run of failures, and stop after a cycle in
        which the ladder sources answer; a held drop's
        confirmation cycle runs at its `confirm_at`; the degraded
        alarm fires once after 3 failures and the recovery entry
        follows.
      - `tests/services/test_log_file.py`: rotation, timestamps in
        UTC, the redaction of a point query above DEBUG, and a
        `None` standard error that raises nothing.
      - `tests/sources/test_cone_advisories.py`: the attribute
        query's URL and parameters, and its parsing of a recorded
        cone-layer answer;
        `tests/services/test_database_refused.py`: a database at
        an unknown revision makes `serve` send the database-free
        toast once (a fake toast) and exit 1.
      - `tests/cli/test_serve_command.py`: `serve` and `check`
        exit 2 while another process holds the monitor lock; with
        the runtime's clock and a stop after the startup cycle,
        `serve` runs the startup cycle and writes the runner
        heartbeat.
      - `tests/scripts/test_simulate_advisory.py`: the script's
        switch logic on a fake toast and a fake clock (the real
        toast run is the Deployed & verified bullet).
    </requirement>

    <requirement>
      Documents. `README.md`'s "Commands": `weatherbot serve` and
      `weatherbot check`. `CONTRIBUTING.md`: the schedule, the
      watches and their etiquette, retries and confirmation, the
      alarm, the log file, and how to run
      `scripts/simulate_advisory.py`. `docs/DATA_SOURCES.md`: the
      roster's, the summary service's, and the alerts' rows say
      how the monitor polls them (the cone layer's attribute query
      among them), dated the step's date, with the NWS alerts
      documentation's 30-second recommendation cited.
      `CHANGELOG.md`: this step's entries.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with its repo-relative path as a comment, as every
      existing one does.
    </requirement>
  </requirements>
</task>
```

### Step 5 acceptance criteria

- The scheduler sleeps at most 60 seconds, runs each job at its due instant plus
  one drawn delay, never runs a job twice at once, survives a failing job, and
  runs one `resume` cycle after a gap, on a fake clock.
- The window opens 15 minutes after each UTC product time and waits, up to 60
  minutes, until the roster and the cone layer agree on an advisory issued at or
  after that time, each poll a short run that reschedules itself; the roster
  watch tightens while a location is above level 1; the alert watch runs only
  while a US location is above level 1; retries come 5, 10, and 20 minutes apart
  after a ladder source fails, at most three per run of failures; a held drop is
  confirmed on schedule; the heartbeat task writes while a slow cycle runs.
- The degraded-data alarm sends one notification after 3 consecutive failures of
  a ladder source or a watch, about 15 minutes into a failure, and a recovery
  entry after it answers; a database the code cannot open raises one
  database-free toast.
- `serve` and `check` refuse a second monitor process, write the rotating log
  file, and record their runner heartbeat; the log file holds no coordinate or
  notification text at INFO.
- The daylight-time change of 2026-11-01 changes no due instant.
- **Deployed & verified:** with the operator's yes,
  `scripts/simulate_advisory.py` on the operator's machine stored a level-5
  escalation within one roster interval of the simulated advisory, with a toast
  delivery reading `delivered`, and the operator confirms seeing the toast; and
  the first `ci.yml` and `phase-verify.yml` runs on `main` are green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, SAST
  clean, dependency audit clean with no dependency added — and the watches add
  only the cone layer's attribute query to what the snapshot service sends, and
  never fetch the same URL twice within a minute.

---

## Step 6 — Task Scheduler and health ✅

**Status:** Complete — PR #50, #51 (2026-10-24)

> **Goal:** Keep the monitor running when no one is watching, and say so when it
> stops. `weatherbot.services.tasks` writes two task definitions as escaped XML
> templates and registers them with `schtasks.exe` unelevated —
> `\Weatherbot\serve`, started at the operator's own logon, and
> `\Weatherbot\check`, every hour running `check --once --if-stale` — both run
> as the operator with `InteractiveToken` and `LeastPrivilege` (no stored
> password), through the installation's `pythonw.exe` (no console window), with
> `serve` unlimited in time and indifferent to battery power; it reads their
> state as JSON from one PowerShell call; `weatherbot install-task` and
> `uninstall-task` drive it; `check --once --if-stale` runs nothing while a
> monitor holds its lock and writes its heartbeat, and when none runs or the
> running one has gone silent, raises the stale-monitor alarm (a toast and a log
> entry) and runs the cycle itself; and `doctor` reports both tasks, the
> installation they run, which installation a bare `weatherbot` reaches on
> `PATH`, and the heartbeat. With the operator's yes, the step installs a copy
> with `uv tool install`, registers the tasks on the operator's machine, and
> verifies them in place. This step lands unattended operation; Step 7 verifies
> the phase.

**Branch:** `feature/phase04-step6-task-scheduler`

**Deploys:** the operator's machine → with the operator's yes, an installed copy
(`uv tool install --from <checkout> weatherbot`) and the two scheduled tasks
under `\Weatherbot\`, registered by `install-task`; Task Scheduler must show
both, `doctor` must report them and a fresh heartbeat, and a forced task run
must store a new assessment. GitHub Actions → the first `ci.yml` and
`phase-verify.yml` runs on `main` must be green.

| Setting      | Cost                                    | Balanced                             | Quality                                    |
| ------------ | --------------------------------------- | ------------------------------------ | ------------------------------------------ |
| Model        | GPT-6.1 Sol                             | Gemini 4 Argon                       | Opus 5.5                                   |
| Backup       | Sonnet 5.5 — Claude Code · Effort XHigh | Opus 5.5 — Claude Code · Effort High | Gemini 4 Argon — Antigravity · Effort High |
| Platform     | Codex                                   | Antigravity                          | Claude Code                                |
| Effort       | Intelligence High                       | Effort High                          | Effort XHigh                               |
| Thinking     | —                                       | On                                   | —                                          |
| Conversation | **New**                                 | **New**                              | **New**                                    |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

> Ran 2026-10-24: Balanced column — Gemini 4 Argon · Effort High · Thinking On on Antigravity. Selected by the **Runs:** rule (Google AI Pro pool reads headroom).

**Model rationale:** Step 6 is coding with an agentic secondary category:
Windows task definitions, a subprocess layer over `schtasks.exe` and PowerShell,
the fallback's staleness logic, and `doctor`'s machine checks — then an
on-machine deployment that installs a copy, registers the tasks, forces runs,
and reads the results. Its overall complexity is High: the task XML's principal,
triggers, and settings each change what happens at 3 a.m.; the subprocesses must
be built safely and silently under `pythonw.exe`; and the machine checks must
never reach the earlier phases' alarm proofs, which run `doctor` on a temporary
data directory. It is not novel: Task Scheduler's documented and reported
behaviour is in this roadmap, and the step's desktop test proves the one claim
that matters most — unelevated registration — before anything depends on it. The
columns differ in depth and maker: Balanced runs Gemini 4 Argon on Antigravity
at Effort High with thinking on; Quality runs Opus 5.5 on Claude Code at Effort
XHigh (always thinking, so `—`); Cost moves it to GPT-6.1 Sol on Codex at
Intelligence High. Google AI Pro, the claude.ai Max subscription, and ChatGPT
Pro 5x fund the three platforms, so each column costs nothing at the margin
while its pool has headroom; as in Step 1, when Antigravity cannot serve the
personal account, the Balanced Backup (Opus 5.5 on Claude Code at Effort High)
runs. The conversation is new per phase-boundary hygiene.

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
       feature/phase04-step6-task-scheduler`
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
       Phase 4 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 4`
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

    THIS STEP registers scheduled tasks that run as the operator
    and calls system tools. Both tasks use `InteractiveToken` with
    `LeastPrivilege`: no password is stored, nothing runs elevated
    or as another account, and nothing runs when the operator is
    logged off. Every subprocess — `schtasks.exe` and
    `powershell.exe`, by their absolute paths under
    `%SystemRoot%\System32` — is an argument list, never a shell
    string, with a justified `# nosec B603` (bandit) and
    `creationflags=CREATE_NO_WINDOW` (a module constant,
    `0x08000000`); the PowerShell script is a constant, and the
    only value it receives is the task folder's name. Task XML is
    a template whose every inserted value (the user id, the
    interpreter's path, the arguments, the working directory)
    passes `html.escape`; the XML file is written in the data
    directory and deleted after registration. The working
    directory is the data directory, never the checkout. Tests use
    the synthetic user `EXAMPLE\operator` and temporary paths; no
    committed file holds the operator's user name, profile path,
    or machine name. The deployment changes the operator's machine
    only after the operator says yes to the exact list of actions,
    and reads the operator's database only through `doctor`,
    printing check names, statuses, ages, and the database fields.
    No dependency is added.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 4 (Monitoring and
    notifications). Step 6: Task Scheduler and health.

    Current state (as of Phase 4 Step 5):

    - `weatherbot serve` and `weatherbot check` run the scheduler
      as the one monitor process (`data_dir/monitor.lock`), write
      `data_dir/logs/weatherbot.log`, and record a `runner`
      heartbeat every 5 minutes; `check --once` runs one cycle;
      `CycleTrigger` holds `fallback`; `notifications.kind` allows
      `stale_monitor`. `notify setup` registers the toast
      identity. `doctor` has `settings`, `database`, `migrations`,
      `locations`, `heartbeat`, and `toast` checks.
    - Carry-over from Step 2: `check --once` with no stored
      location still runs the cycle and exits on its status (a
      usage error is only a bad flag), so the fallback works on a
      machine with no locations. A cycle whose process died
      mid-cycle stays `started` in `monitor_cycles` (no
      `completed_at`); `CycleRepository.recent(limit)` reads the
      latest cycles. `doctor`'s `heartbeat` check is `skip` until a
      row promises a cadence and when the database did not open.
    - Carry-over from Step 4 (PR #46 body has the details):
      `install-task` registers the identity through the runtime's
      seam, `context.runtime.identity().register()` (the
      `Identity` that `register_identity()` wraps), so its command
      tests use `cli_support.FakeRegistry` and never the real
      registry. It returns `registered`, `unchanged`, or
      `not_needed`, and raises `OSError` when the registry refuses;
      `notify setup` then names the error's class and exits 1. The
      `desktop` marker already names Task Scheduler, so
      `tests/desktop/test_tasks_desktop.py` needs no new marker.
      `doctor`'s `toast` check is the pure
      `toast_check(latest, *, identity, toast_on,
      delivered_before)` beside `heartbeat_check`, fed by
      `diagnose(identity=, toast_on=)`; the `tasks` and `path`
      checks follow that pattern. The stale-monitor alarm sends
      through `NotificationService.send("stale_monitor", ...)`
      with `context.channels`.
    - Carry-over from Step 5: `serve`, `check`, and `check --once`
      open the database through `open_monitor_session(context,
      output)` (`weatherbot.cli.runtime`), which catches
      `UnknownRevisionError` and `MigrationFailedError`, logs the
      refusal, delivers the database-free toast once via
      `deliver_database_refused_toast` (`weatherbot.services.notifications`),
      and exits 1; keep `check --once --if-stale` on
      `open_monitor_session` so the fallback inherits the same
      behaviour. `clear_runner_heartbeat_cadence` clears the
      runner row's `expected_every_s` on a clean stop, so a
      monitor stopped on purpose never triggers the fallback's
      stale-monitor alarm.
    - Checked on 2026-10-21: this machine runs Windows 11 build
      26200, and the operator's account is an administrator under
      UAC whose shells run at medium integrity. Reported in two
      2026 issues on Windows 11, one on build 26200, and not yet
      tried here (the desktop test below proves it first):
      `schtasks /Create /SC ONLOGON` is refused without elevation
      (it triggers on any user's logon), while a task whose
      `LogonTrigger` names the current user's `UserId` registers
      unelevated from XML (`schtasks /Create /TN <name> /XML
      <file> /F`); `C:\Windows\System32\Tasks` grants
      Authenticated Users write and makes the creator owner of
      what it creates, so `\Weatherbot\` is expected to work
      unelevated (this step proves it). Researched:
      `InteractiveToken` runs only in the user's interactive
      session ("run only when user is logged on"), which is also
      where toasts show; `ExecutionTimeLimit` defaults to 72 hours
      (`PT0S` is unlimited); `DisallowStartIfOnBatteries` defaults
      to true, and the documentation contradicts itself on
      `StopIfGoingOnBatteries`, so both are written explicitly; a
      `TimeTrigger` whose `Repetition` has an `Interval` and no
      `Duration` repeats indefinitely; `StartWhenAvailable` runs a
      missed start late; `schtasks /Query /XML` returns
      console-code-page text that declares UTF-16, and `/FO CSV`
      is localized, so neither is parsed; `Get-ScheduledTask |
      Get-ScheduledTaskInfo` gives `State`, `LastRunTime`,
      `LastTaskResult` (0x41301 running, 0x41303 has not run), and
      `NextRunTime`, in about 4 to 6 seconds per call; a
      non-administrator can read, update, delete, and run only the
      tasks it created.
    - `pythonw.exe` sits beside `python.exe` in every uv
      environment; `python -m weatherbot` runs the CLI. Under
      `pythonw.exe` standard streams are `None` (Step 5's logging
      handles it) and a child process opens a console unless
      started with `CREATE_NO_WINDOW`.
    - On the operator's `PATH`, `weatherbot` is version 1.0.0 from
      a retired virtual environment outside the checkout (ninth on
      `PATH`), with another version 1 copy in the system Python
      3.11, both ahead of `~/.local/bin` (35th), where `uv tool
      install` puts its launcher; no uv tool is installed.
      `doctor` names the shadowing directory on the operator's own
      terminal only.
    - Phase 2's and Phase 3's alarm proofs run `doctor --offline
      --json` with `WEATHERBOT_DATA_DIR` set to a fresh temporary
      directory and require exit 0, then exit 1 after stamping an
      unknown revision; their operator-database rows read only the
      database fields of the operator's `doctor --json`. Phase 2's
      check 20 forbids the standard library's XML modules in the
      package; bandit runs over `src` and `scripts` at every
      severity.

    Files to read (every file before drafting):
    - docs/roadmap/phase04-roadmap.md (Overview and its design
      rationale, Current State, Steps 2, 4, and 5, this step, and
      Step 7).
    - docs/roadmap/ROADMAP.md (Phase 4, section 4.4; section 5,
      "Release & deployment strategy" and "Operations &
      observability strategy").
    - src/weatherbot/services/monitor.py, schedule.py,
      notifications.py, toast.py, health.py, doctor.py, config.py,
      logs.py; src/weatherbot/cli/__init__.py, check.py, serve.py,
      doctor.py, runtime.py, documents.py.
    - scripts/verify_phase02.py and scripts/verify_phase03.py (the
      `doctor_alarm` and operator-database rows),
      tests/cli/cli_support.py.
    - CONTRIBUTING.md, README.md, CHANGELOG.md.
  </context>

  <goal>
    Ship the task definitions and their registration, query, and
    removal; `install-task` and `uninstall-task`; `check --once
    --if-stale` with the stale-monitor alarm; and `doctor`'s
    `tasks` and `installation` checks; then, with the operator's
    yes, install a copy, register both tasks on the operator's
    machine, and verify them in place.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `src/weatherbot/services/tasks.py` (functions run only on
      Windows; the module imports cleanly everywhere):

      - `TASK_FOLDER = "\\Weatherbot\\"`; the tasks `serve`
        (arguments `-m weatherbot serve`) and `check` (arguments
        `-m weatherbot check --once --if-stale`).
      - `definition_xml(name, *, user_id, command, arguments,
        working_directory, trigger, enabled, time_limit,
        start_when_available) -> str` writes Task Scheduler schema
        1.2 XML from one template, and `task_xml(task, *, user_id,
        interpreter, working_directory, start)` uses it for the
        two tasks. `serve`: a `LogonTrigger` with that `UserId`.
        `check`: a `TimeTrigger` from `start` (the next hour at 25
        minutes past, local time, after the measured roster
        rewrites, so a fallback cycle sees that hour's advisories)
        with `Repetition` `Interval` `PT1H` and no `Duration`.
        Both: a `Principal` with that `UserId`, `LogonType`
        `InteractiveToken`, and `RunLevel` `LeastPrivilege`;
        `MultipleInstancesPolicy` `IgnoreNew`;
        `DisallowStartIfOnBatteries` and `StopIfGoingOnBatteries`
        false; `AllowStartOnDemand` and `Enabled` true;
        `WakeToRun` false; `Priority` 7; `ExecutionTimeLimit`
        `PT0S` for `serve` and `PT30M` for `check`;
        `StartWhenAvailable` true for `check`; an `Exec` action
        whose `Command` is the installation's `pythonw.exe`, with
        the arguments above and the data directory as its
        `WorkingDirectory`; and a description saying `weatherbot
        install-task` registered it. Every inserted value passes
        `html.escape`.
      - `install(paths, *, interpreter)`: writes each definition
        to the data directory as UTF-16 little-endian with a
        byte-order mark, runs `%SystemRoot%\System32\schtasks.exe
        /Create /TN \Weatherbot\<name> /XML <file> /F`, deletes
        the file, and returns each task's outcome. `uninstall()`
        first ends a running `\Weatherbot\serve` (`schtasks.exe
        /End`), so the monitor stops, then deletes both (`/Delete
        … /F`), treats an absent task as removed, and clears the
        `serve` runner row's cadence so it is never stale
        afterwards. `run(name)` runs `schtasks.exe /Run /TN
        \Weatherbot\<name>`.
      - `query()` runs one constant PowerShell script
        (`%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe
        -NoProfile -NonInteractive -Command …`), written for
        Windows PowerShell 5.1's habits: it sets
        `[Console]::OutputEncoding` to UTF-8, wraps its result in
        `@(…)` so a single task is still a list, casts each enum
        (the state, the logon type, the run level) to a string,
        formats `LastRunTime` and `NextRunTime` with
        `.ToString('o')`, and passes `-Depth 4` to
        `ConvertTo-Json`. It reports every task under
        `\Weatherbot\` — the name, state, whether it is enabled,
        the action's executable and arguments, the principal's
        logon type and run level, the two instants, and
        `LastTaskResult` — and Python parses it with `json`.
      - Every subprocess passes `creationflags=CREATE_NO_WINDOW`,
        a module constant `0x08000000`:
        `subprocess.CREATE_NO_WINDOW` exists only on Windows, and
        the tests and strict pyright run on Ubuntu too. A runner
        seam replaces the subprocess in tests.
      - The user id is the session's `USERDOMAIN` and `USERNAME`;
        the interpreter is
        `Path(sys.executable).with_name("pythonw.exe")`, which
        must exist.
    </requirement>

    <requirement>
      Commands (`src/weatherbot/cli/tasks.py`): `weatherbot
      install-task [--allow-checkout] [--json]` refuses with exit
      2 off Windows, and when the running interpreter belongs to a
      source checkout's environment (its environment's parent
      holds a `pyproject.toml` naming `weatherbot`) unless
      `--allow-checkout` is given, because a checkout's `.venv`
      follows whatever branch is checked out. It registers the
      toast identity through `register_identity()` if it is
      missing (as `notify setup` does), registers both tasks,
      reads them back through `query()`, and prints each task's
      state and next run. `weatherbot uninstall-task [--json]`
      ends a running `serve`, removes both tasks, and leaves the
      toast identity (`notify setup --remove` removes it).
      Register both with `app.command("install-task")(…)` and
      `app.command("uninstall-task")(…)` beside the existing
      lines; documents `install-task` and `uninstall-task` join
      `DOCUMENTS` (update its count in place).
    </requirement>

    <requirement>
      The fallback. `check --once --if-stale` first asks whether a
      monitor is running: Step 2's `ProcessLock.held(path)` tries
      `data_dir/monitor.lock` without waiting, and the operating
      system frees that lock the moment its holder dies. While a
      monitor holds it, the fallback waits up to 3 minutes for
      that monitor's runner row to be fresh by the staleness rule
      — after the machine resumes, the monitor's heartbeat task
      writes within a minute, so a laptop waking up never raises
      the alarm — and exits 0 without a cycle once it is. When no
      monitor holds the lock while the `serve` task is installed,
      or the holder stays silent, it sends one `stale_monitor`
      notification per stale period ("Weatherbot: the monitor is
      not running; a check ran instead." or "Weatherbot: the
      monitor is not responding; a check ran instead."), through
      the log and the toast (quiet hours hold it back only while
      every location's latest level is 1 or 2), asks Task
      Scheduler to start `serve` again (`run("serve")`) when no
      monitor holds the lock, then runs a cycle with the trigger
      `fallback` and the runner `fallback`, and exits as `check
      --once` does. The notification is not sent again until a
      monitor's row has been fresh in between. With no `serve`
      task installed and no monitor running, it runs the cycle
      without the alarm. Every fallback run writes the log file,
      because it runs under `pythonw.exe` too, and records its
      runner row `fallback` with a one-hour cadence. The running
      `serve` watches that row from its heartbeat task: while the
      `check` task is installed and the row is stale (no fallback
      run for two hours), `serve` sends one `stale_monitor`
      notification ("Weatherbot: the hourly check has not run
      since <instant>.") per stale period, which is the alarm the
      project roadmap's operations table gives the scheduled
      check's own heartbeat.
    </requirement>

    <requirement>
      `doctor` gains two machine checks, judged only when `doctor`
      reads the default data directory (no `WEATHERBOT_DATA_DIR`
      override), so the alarm proofs' temporary directories never
      meet the operator's tasks. Their names stay at most 10
      characters, the width of `migrations`, because Phase 2's
      command tests assert the plain-text table's spacing. `tasks`
      — `skip` off Windows, under an override, or when neither
      task is installed; `pass` when both are enabled, use
      `InteractiveToken` and `LeastPrivilege`, point at an
      interpreter that exists, and last returned 0, 0x41301
      (running), or 0x41303 (has not run); `fail` naming the task
      and the reason otherwise. `path` — `skip` under an override
      and when the running interpreter belongs to a source
      checkout's environment (a developer's run, where `uv run`
      puts the checkout's `.venv` first); `pass` when a bare
      `weatherbot` on `PATH` (`shutil.which`) belongs to the
      running installation; `fail` naming the other installation's
      directory and the fix (put `~/.local/bin` earlier on `PATH`,
      or remove the other copy) otherwise. On the default data
      directory only, the `heartbeat` check also fails when the
      `serve` task is installed and the `serve` runner row is
      stale or absent; under an override it stays as Step 2 has
      it, so a fresh temporary directory still skips. `doctor`'s
      document lists the tasks' states, last results, and next
      runs.
    </requirement>

    <requirement>
      Tests, offline, under unique basenames, none that skips on
      Windows or Ubuntu (the platform and the subprocess runner
      are seams):

      - `tests/services/test_tasks.py`: both definitions' triggers
        (the check task's start at 25 minutes past the hour),
        principal, settings, action, working directory, and
        escaping (a user id and a path holding `&` and `<`); the
        file is UTF-16 with a byte-order mark and is deleted after
        registration; `install`, `uninstall` (which ends `serve`
        first), `run`, and `query` build exactly the argument
        lists above with absolute executables and the
        `CREATE_NO_WINDOW` constant; the PowerShell script carries
        `@(`, `.ToString('o')`, `-Depth 4`, and the UTF-8 output
        encoding; `query` parses recorded JSON for one task, two
        tasks, a missing task, and a running one; `install-task`
        refuses a checkout's interpreter without
        `--allow-checkout`.
      - `tests/services/test_fallback.py`: a monitor holding the
        lock with a fresh row runs nothing; a held lock whose row
        turns fresh within the wait (a resume) raises no alarm; a
        free lock with the `serve` task installed sends one "not
        running" notification, asks Task Scheduler to start
        `serve`, and runs a `fallback` cycle; a held lock whose
        row stays stale sends "not responding"; a second stale run
        sends no second notification until a row was fresh in
        between; the fallback records its runner row, and
        `serve`'s heartbeat task sends one notification when that
        row goes stale while the `check` task is installed.
      - `tests/services/test_doctor_machine.py`: both machine
        checks and the heartbeat's task rule skip under a
        data-directory override, and pass and fail on recorded
        `query()` answers and a fake `which`; the `path` check
        skips for a checkout's interpreter; `doctor --offline
        --json` on a fresh temporary database still exits 0.
      - `tests/cli/test_task_commands.py`: `install-task` and
        `uninstall-task` with the fake runner; exit codes;
        documents against their committed schemas.
      - `tests/desktop/test_tasks_desktop.py` (`desktop`): with
        `definition_xml`, registers a disposable, disabled
        `\Weatherbot\probe` task (a `LogonTrigger` for the current
        user, `InteractiveToken`, `LeastPrivilege`, the action
        `%SystemRoot%\System32\cmd.exe /c exit 0`) unelevated,
        reads it back through `query()`, and deletes it.
    </requirement>

    <requirement>
      Documents. `README.md`: a `### Running unattended`
      subsection under `## Commands`, after the Phase 3 lines (so
      Phase 3's check 47 still finds them before the next `## `
      heading), for `uv tool install --from <checkout> weatherbot`
      — and `uv tool install --reinstall --from <checkout>
      weatherbot` after each merge that changes the monitor,
      because the version stays `2.0.0.dev0` and a plain install
      of the same version changes nothing — `install-task`,
      `uninstall-task`, the hourly fallback, the `PATH` note, and
      that a checkout command which migrates the database past the
      installed copy stops the monitor with a toast until the copy
      is reinstalled. `CONTRIBUTING.md`: the task definitions, the
      `desktop` tests, and how to remove the tasks.
      `CHANGELOG.md`: this step's entries.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with its repo-relative path as a comment, as every
      existing one does.
    </requirement>

    <requirement>
      Deployment (Stage 4, after the merge, on `main`). Ask the
      operator (AskUserQuestion) to approve exactly: install a
      copy with `uv tool install --from <checkout> weatherbot`
      (with `--reinstall` if one exists); register the two tasks
      with that copy's `install-task`; start `\Weatherbot\serve`
      now; force one `\Weatherbot\check` run; and run `pytest -m
      desktop tests/desktop/test_tasks_desktop.py`. With a yes:
      run them, calling the installed copy by its absolute path
      (the version 1 copies shadow it on `PATH`); run that copy's
      `doctor`, printing only the check names and statuses, the
      tasks' states and last results, the heartbeat's ages, and
      the database fields; and tell the operator how to remove the
      version 1 shadow (their housekeeping, which `doctor`'s
      `path` check reports until it is done). With a no, the step
      is not complete: say so.
    </requirement>
  </requirements>
</task>
```

### Step 6 acceptance criteria

- `task_xml` writes both definitions with the operator's own `LogonTrigger` or
  the hourly `TimeTrigger` at 25 minutes past, `InteractiveToken`,
  `LeastPrivilege`, `pythonw.exe`, the data directory as the working directory,
  `PT0S` and `PT30M` time limits, and battery power ignored, every value
  escaped.
- `install-task` registers both tasks unelevated and reads them back;
  `uninstall-task` ends `serve` and removes them; `install-task` refuses a
  checkout's interpreter without `--allow-checkout`; `query()` reads Windows
  PowerShell 5.1's output for one task and for several.
- `check --once --if-stale` runs nothing while a monitor holds its lock and
  writes its heartbeat, even right after the machine resumes; when no monitor
  runs while the `serve` task is installed, or the running one stays silent, it
  sends one `stale_monitor` notification, asks Task Scheduler to start `serve`,
  and runs a `fallback` cycle; `serve` reports an hourly check that stopped
  running.
- `doctor`'s `tasks` and `path` checks pass and fail as specified on the default
  data directory and skip under an override (and `path` for a checkout's
  interpreter); `doctor --offline --json` on a fresh temporary database still
  exits 0, and Phase 2's and Phase 3's alarm proofs pass.
- `pytest -m desktop tests/desktop/test_tasks_desktop.py` passed on the
  operator's machine (unelevated registration proven).
- **Deployed & verified:** with the operator's yes, the installed copy's
  `install-task` registered `\Weatherbot\serve` and `\Weatherbot\check`; Task
  Scheduler (`query()`) shows both enabled under `InteractiveToken` and
  `LeastPrivilege`; a forced `\Weatherbot\serve` run stored a `startup` cycle
  with new assessments and a fresh `serve` runner row, which the installed
  copy's `doctor` reports; a forced `\Weatherbot\check` run returned 0 without a
  cycle while `serve` was fresh; and the first `ci.yml` and `phase-verify.yml`
  runs on `main` are green.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret and personal-data scan clean, SAST
  clean with each subprocess's `# nosec` justified, dependency audit clean with
  no dependency added — and no stored credential, elevated run level, or
  committed user name exists.

---

## Step 7 — QA & Verification Script

**Status:** Not started

> **Goal:** Package the verification matrix into `scripts/verify_phase04.py`
> (with `--fast`, `--py`, `--live`, `--security`, `--all`, and `--post` modes),
> produce `docs/phase04-qa-findings.md`, add `"04"` to the `phase-verify.yml`
> matrix beside `"01"`, `"02"`, and `"03"`, and close the phase. The script
> reads every Step 1 through Step 6 deliverable with standard-library static
> checks, builds the V1–V7 matrix from one offline pytest run with the coverage
> floor over the engine and the policy, one live run, and — in `--post`, on the
> operator's machine — one desktop run, each with `--junitxml`, and in `--post`
> adds the GitHub readbacks, Phase 3's own `--post` sweep, `doctor` on the
> operator's database with the alarm proof, the operator's two scheduled tasks
> and heartbeat, and the simulated advisory; the closure marks Phase 4 complete
> in both roadmaps and tags `v2.0.0-phase-4`.

**Branch:** `feature/phase04-step7-verify`

**Deploys:** GitHub Actions → `phase-verify (04)` runs on every push and pull
request from the merge on, under the required aggregate `phase-verify`; its
first run on `main` must be green, and the annotated `v2.0.0-phase-4` tag must
peel to the merge commit.

| Setting      | Cost                                     | Balanced                             | Quality                                    |
| ------------ | ---------------------------------------- | ------------------------------------ | ------------------------------------------ |
| Model        | GPT-6.1 Sol                              | Gemini 4 Argon                       | Opus 5.5                                   |
| Backup       | Sonnet 5.5 — Claude Code · Effort Medium | Opus 5.5 — Claude Code · Effort High | Gemini 4 Argon — Antigravity · Effort High |
| Platform     | Codex                                    | Antigravity                          | Claude Code                                |
| Effort       | Intelligence Low                         | Effort High                          | Effort High                                |
| Thinking     | —                                        | On                                   | —                                          |
| Conversation | **New**                                  | **New**                              | **New**                                    |

**Runs:** Balanced — the user-context's Budget priority is `balanced`. If that column's usage pool reads `tight`, run its Backup when the Backup's pool has headroom, else the Cost column; if it reads `exhausted`, run its Backup.

**Model rationale:** Step 7 is coding with an agentic secondary category —
GitHub readbacks, on-machine sweeps, and the closure — at Medium complexity: it
translates this roadmap's acceptance criteria into numbered checks, a V-matrix,
a matrix entry, and a findings rollup, with `scripts/verify_phase03.py` as the
structural template, and it is not novel. The columns differ in depth and maker:
Balanced runs Gemini 4 Argon on Antigravity at Effort High with thinking on;
Quality runs Opus 5.5 on Claude Code at Effort High (always thinking, so `—`)
for a deeper audit of each check against its deliverable; Cost moves the step to
GPT-6.1 Sol on Codex at Intelligence Low, enough for enumerated checks whose
content this roadmap writes down. Google AI Pro, the claude.ai Max subscription,
and ChatGPT Pro 5x fund the three platforms, so each column costs nothing at the
margin while its pool has headroom; as in Step 1, when Antigravity cannot serve
the personal account, the Balanced Backup (Opus 5.5 on Claude Code at Effort
High) runs. The conversation is new per phase-boundary hygiene.

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
       feature/phase04-step7-verify`
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
       Phase 4 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 4`
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
       complete. Phase 4 is
       complete. You can now move
       on to Phase 5." That
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
       one before Phase 5.
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
    own diff must still pass the gate before commit. The verifier
    runs subprocesses from argument lists, never a shell; prints
    check ids, rule names, and exception types, never scanned
    content; reads GitHub settings read-only; reads the operator's
    database only through `doctor`, printing only its revision,
    head, and check statuses; reads the operator's scheduled tasks
    only through `services.tasks.query()`, printing their names,
    states, and last results; runs every build, live, desktop, and
    alarm probe in a temporary data directory; and never runs
    `status`, `check`, or `replay` against the operator's stored
    locations, nor prints a notification about them. The desktop
    run and the simulated advisory each show one test toast, and
    the desktop run registers and removes one disabled probe task;
    `--post` says so before it starts. It never reads or prints
    the personal-data denylist.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 4 (Monitoring and
    notifications). Step 7: QA + verification script.

    Steps 1 through 6 have been implemented. Now create the
    verification script, the QA findings, and the matrix entry,
    and close the phase.

    Reference scripts (pattern templates):
    - scripts/verify_phase03.py (the structural precedent: 52
      static checks, the six modes, V rows built from JUnit
      reports where every selection must match a test, a failure
      fails, and a skip is never a pass, `Select(...,
      without=...)`, the GitHub readbacks, the nested `--post`,
      the operations proof).
    - scripts/verify_phase02.py (the `doctor` alarm proof and the
      operator-database row).

    Phase 4 deliverables to verify (51 static checks: 46 across
    Steps 1 through 6, and 5 Step 7 self-checks):

    Step 1 (snapshot storage) — checks 1-6:
    1. Revision `0004` follows `0003` and creates
       `geometry_contents`, `snapshot_provenances`, and
       `snapshot_geometries` (AST).
    2. `SnapshotRepository` stays unique, keeps `snapshot.origin
       != "live"` in `save`, and no longer constructs a
       `ProductGeometryRow` (AST).
    3. The repository hashes content with `hashlib.sha256` and
       compresses it with `zlib`.
    4. `tests/services/test_database.py`'s `FROZEN` pins `0001`,
       `0002`, and `0003`.
    5. `tests/services/test_geometry_storage.py` and
       `tests/cli/test_storage_growth.py` are tracked, the latter
       with its 128 KiB bound.
    6. `tests/services/test_tables.py` names the three new tables.

    Step 2 (the cycle, the heartbeat, staleness) — checks 7-15:
    7. Revision `0005` follows `0004` and creates `heartbeats` and
       `monitor_cycles`.
    8. `services/monitor.py` defines `MonitorService` with
       `run_cycle`, `CycleResult`, and `CycleTrigger` with its
       nine triggers.
    9. `services/locks.py` defines `ProcessLock` and
       `LockBusyError` over `msvcrt` and `fcntl` only.
    10. `database.py` begins writing transactions with `BEGIN
        IMMEDIATE` and sets `BUSY_TIMEOUT_MS` to 30,000.
    11. `services/health.py` defines `Staleness` and `staleness`,
        doubling `expected_every_s`.
    12. `cli/__init__.py` registers `app.command("check")` and
        adds the `config` group with `show` and `path`.
    13. `docs/schema/status.schema.json` names `staleness`, and
        the `check` and `config` schemas are committed.
    14. `ENVIRONMENT_OVERRIDES` holds literal
        `WEATHERBOT_MONITOR_*` and `WEATHERBOT_NOTIFICATIONS_*`
        names for every key of `[monitor]` and `[notifications]`.
    15. The Step 2 tests are tracked, and
        `tests/live/test_monitor_live.py` is marked `live`.

    Step 3 (the policy and the log) — checks 16-24:
    16. Revision `0006` follows `0005` and creates
        `notifications`, `notification_decisions`, and
        `notification_deliveries`.
    17. `services/policy.py` defines `decide`, `PolicyState`, and
        `PolicySettings`, and its decisions are exactly
        `escalation`, `sent`, `repeat`, `quiet_hours`, `held`,
        `withdrawn`, and `informational`.
    18. `services/policy.py` imports only `weatherbot.models` and
        the standard modules the step allows, and calls no clock.
    19. `services/notifications.py` defines `Channel`,
        `LogChannel`, `NotificationService`, and
        `replay_notifications`.
    20. `tests/golden/notifications/` holds exactly
        `AL112017-miami-dade.json` and `AL112017-nassau.json`,
        each with `defaults`, `strict`, and `approval`.
    21. `scripts/build_notification_goldens.py` is tracked and
        offers `--check`, `--review-only`, `--approve-date`, and
        `--review-sha256`.
    22. `tests/services/test_notification_replay.py` and
        `test_notification_goldens.py` are tracked, the first with
        the privacy scan.
    23. The `notify` group registers `log`, and the
        `notifications` schema is committed.
    24. `docs/ALERT-LADDER.md` has a "Notifications" section, and
        `ci.yml`'s test job adds
        `--cov=weatherbot.services.policy` and a `coverage report
        --include` step holding the policy alone to 90 percent.

    Step 4 (the toast) — checks 25-31:
    25. `pyproject.toml` declares the five `winrt-*` dependencies,
        each with `sys_platform == 'win32'`.
    26. `services/toast.py` defines `ToastChannel`, `NullChannel`,
        `toast_channel`, `toast_xml`, `APP_ID`,
        `register_identity`, and `unregister_identity`, and
        imports `winrt` and `winreg` only inside `if sys.platform
        == "win32":` (AST).
    27. `toast_xml` calls `html.escape`.
    28. No package module names `HKEY_LOCAL_MACHINE`.
    29. The `notify` group registers `setup` and `test`, with
        their schemas committed.
    30. `pyproject.toml` registers the `desktop` marker and its
        addopts deselect it.
    31. The Step 4 tests are tracked, and
        `tests/desktop/test_toast_desktop.py` is marked `desktop`.

    Step 5 (the scheduler) — checks 32-39:
    32. `services/scheduler.py` defines `Scheduler` and `Job`,
        with `max_sleep_s` defaulting to 60.
    33. No dependency or import names `apscheduler`.
    34. `services/schedule.py` names the product hours `(0, 3, 6,
        9, 12, 15, 18, 21)` and the 15-minute window offset, and
        `sources/nhc_map.py` defines `fetch_cone_advisories` with
        its declared fields.
    35. `[monitor]` holds `window_offset_minutes`,
        `window_jitter_seconds`, `window_close_minutes`,
        `roster_poll_minutes`, `roster_interval_minutes`,
        `roster_interval_relevant_minutes`,
        `alert_interval_minutes`, `retry_base_minutes`,
        `retry_count`, `degraded_after_failures`, and
        `heartbeat_minutes`, each bounded below by at least 1.
    36. `cli/__init__.py` registers `app.command("serve")`, and
        `serve` and `check` take `monitor.lock`.
    37. `configure_logging` takes `log_file` and installs a
        `RotatingFileHandler`.
    38. `scripts/simulate_advisory.py` is tracked and answers
        through respx.
    39. The Step 5 tests are tracked.

    Step 6 (Task Scheduler) — checks 40-46:
    40. `services/tasks.py` defines `definition_xml`, `task_xml`,
        `install`, `uninstall`, `run`, and `query`; the XML
        `task_xml` writes for each task carries `LogonType`
        `InteractiveToken`, `RunLevel` `LeastPrivilege`, and the
        `PT0S` or `PT1H` values, and no other logon type or run
        level (read from a rendered sample, not the module's
        prose).
    41. Every subprocess in `services/tasks.py` names an absolute
        `System32` executable and the module's `CREATE_NO_WINDOW`
        constant, and no package module passes `shell=True` (AST).
    42. `cli/__init__.py` registers `app.command("install-task")`
        and `app.command("uninstall-task")`, with their schemas
        committed.
    43. `check` offers `--if-stale`, and
        `services/notifications.py`'s literal of notification
        kinds is exactly `location`, `degraded`, `recovered`,
        `stale_monitor`, and `test`.
    44. `doctor` defines the `tasks` and `path` checks (each name
        at most 10 characters) and skips them under
        `WEATHERBOT_DATA_DIR`.
    45. The Step 6 tests are tracked, and
        `tests/desktop/test_tasks_desktop.py` is marked `desktop`.
    46. `README.md`'s "Commands" names `serve`, `check --once`,
        `notify`, and `install-task` and holds a `### Running
        unattended` subsection, with Phase 3's three lines still
        before any later `## ` heading, and its Status section
        names Phase 4 complete.

    Step 7 self-checks — checks 47-51:
    47. `scripts/verify_phase04.py` is tracked.
    48. `docs/phase04-qa-findings.md` exists.
    49. `docs/roadmap/phase04-roadmap.md` exists (this doc).
    50. `.github/workflows/phase-verify.yml`'s matrix includes
        `"01"`, `"02"`, `"03"`, and `"04"`.
    51. The security gate is wired: the four hooks in
        `.pre-commit-config.yaml`, and `--security` in every phase
        entry.

    Files to read:
    - scripts/verify_phase03.py (primary structural template) and
      tests/test_phase03_verification.py.
    - scripts/verify_phase02.py (the alarm proof).
    - all Phase 4 implementation files from Steps 1 through 6, and
      docs/phase03-qa-findings.md (the ledger's shape).
    - docs/roadmap/phase04-roadmap.md (this step, every step's
      acceptance criteria, and Post-Implementation Verification)
      and docs/roadmap/ROADMAP.md (Phase 4 and Phase 5).
  </context>

  <goal>
    Create scripts/verify_phase04.py with 51 static checks (46 for
    Steps 1 through 6, and 5 Step 7 self-checks) plus the 29-row
    V1-V7 matrix (80 in `--post`); create
    docs/phase04-qa-findings.md; add `"04"` to the
    phase-verify.yml matrix; close Phase 4 in both roadmaps; and
    tag `v2.0.0-phase-4`.
  </goal>

  <requirements>
    <requirement>
      Read scripts/verify_phase03.py end-to-end for structure,
      flag parsing, output format, the PASS / FAIL / SKIP
      conventions, and the final summary. Mirror it so the Phase 4
      output is continuous with Phase 3's in CI logs.
    </requirement>

    <requirement>
      scripts/verify_phase04.py modes, mutually exclusive; no flag
      runs `--fast` and `--py`:

      - `--fast`: the 51 static checks only, standard library only
        and offline, CI-safe on Ubuntu, under 30 seconds; AST,
        `tomllib`, `json`, and `git ls-files` reads.
      - `--py`: static checks + ruff, ruff format, strict pyright,
        lint-imports, and one offline pytest run with
        `--cov=weatherbot.engine --cov=weatherbot.services.policy
        --cov-branch --cov-fail-under=90` and `--junitxml`, its
        `COVERAGE_FILE` in a temporary directory, then `coverage
        report --include="*/services/policy.py" --fail-under=90`
        on that file, plus the wheel smoke (which imports the
        monitor, the policy, and the toast module on the platform
        it runs on).
      - `--live`: static checks + one `pytest -m live` run with
        `--junitxml` (the landmarks only).
      - `--security`: the security gate over the phase's surface —
        gitleaks, bandit over `src` and `scripts`,
        `scripts/audit_deps.py`, and
        `scripts/check_personal_data.py --ci` in CI, or with the
        denylist locally. CI-safe on Ubuntu; non-zero on any
        finding.
      - `--all`: py + live + security.
      - `--post`: static checks + V1-V7 (adding one `pytest -m
        desktop` run with `--junitxml` and the simulated advisory,
        both announced first), and `gh pr checks` on a branch.

      At least one static check is security-oriented and confirms
      the gate is wired, not bypassed (check 51), and the checks
      continue after a failure without echoing content.
    </requirement>

    <requirement>
      Post-implementation V-checks (29 rows; JUnit evidence per
      row, every selection matching at least one test):

      V1 — Snapshot storage
      - V1.1 Static checks 1-6 all PASS.
      - V1.2 The geometry-storage, revision `0004`, and
        storage-growth tests pass (`--py`).
      - V1.3 The latest `phase-verify.yml` run on `main` is at
        HEAD with `phase-verify (01)`, `(02)`, and `(03)` green.
      - V1.4 `verify_phase03.py --post` reports all 80 checks PASS
        (Phase 2's 73 and Phase 1's 75 inside it), with a nested
        timeout of 9,000 seconds.

      V2 — The cycle, the heartbeat, and staleness
      - V2.1 Static checks 7-15 all PASS.
      - V2.2 The monitor, lock, health, and writing-transaction
        tests pass.
      - V2.3 The status-staleness, check, and config command tests
        pass, and every document validates against its schema.
      - V2.4 `check --once` runs against the live services for
        both landmarks (the live run).
      - V2.5 `doctor` reports the operator's database at the head,
        a head that descends from `0006` (only the revision and
        the head printed), and the alarm proof: a fresh temporary
        database gives `doctor --offline --json` exit 0 with the
        `heartbeat`, `toast`, `tasks`, and `path` checks skipped,
        and the same database stamped with an unknown revision
        exits 1 with the database failing.

      V3 — The notification policy and the log
      - V3.1 Static checks 16-24 all PASS.
      - V3.2 The policy tests pass, every rule and scenario
        included, and the policy alone reaches 90 percent branch
        coverage (the offline run and its `coverage report
        --include`).
      - V3.3 The notification replay invariants pass over all
        eight replays: no step held, every escalation sent under
        the defaults and the strict settings, at most one
        notification per step, and the privacy scan.
      - V3.4 The two Irma notification goldens equal the policy
        with matching approval digests, and
        `build_notification_goldens.py --check` passes.

      V4 — The Windows toast channel
      - V4.1 Static checks 25-31 all PASS.
      - V4.2 The toast, notify-command, and doctor-toast tests
        pass (fake notifier).
      - V4.3 The desktop toast test passes on the operator's
        machine: a real toast reads `delivered` (the desktop run).

      V5 — The scheduler, `serve`, and `check`
      - V5.1 Static checks 32-39 all PASS.
      - V5.2 The scheduler and schedule tests pass (windows,
        watches, retries, confirmation, resume, and the
        daylight-time change on a fake clock), the degraded-data
        alarm and its recovery included.
      - V5.3 The log-file, serve-command, and simulate-advisory
        tests pass.
      - V5.4 `scripts/simulate_advisory.py` passes on the
        operator's machine: a level-5 escalation stored within one
        roster interval with a toast delivery reading `delivered`.

      V6 — Task Scheduler and health
      - V6.1 Static checks 40-46 all PASS.
      - V6.2 The tasks, fallback (the stale-monitor alarm
        included), doctor-machine, and task-command tests pass.
      - V6.3 The desktop tasks test passes: a disabled probe task
        registers unelevated, reads back, and is removed (the
        desktop run).
      - V6.4 On the operator's machine `query()` shows
        `\Weatherbot\serve` and `\Weatherbot\check` enabled with
        `InteractiveToken` and `LeastPrivilege`, `serve` running
        or last returning 0; the installed copy's `doctor` passes
        its `tasks` check on the default data directory, and its
        `path` check passes or fails only on the `PATH` shadow the
        QA ledger records with its owner.
      - V6.5 The installed copy's `doctor` document shows the
        `serve` runner row fresh by the staleness rule on the
        default data directory.

      V7 — CI integration + security
      - V7.1 `verify_phase04.py --fast` exits 0 on Ubuntu CI.
      - V7.2 `phase-verify.yml`'s matrix includes `"01"`, `"02"`,
        `"03"`, and `"04"`.
      - V7.3 All 51 static checks pass.
      - V7.4 `verify_phase04.py --security` exits 0.

      The whole offline run's exit is a constituent of V1.2, the
      live run's of V2.4, and the desktop run's of V4.3, so no
      failure escapes `--post`. On `main`, a GitHub readback
      requires the latest run to be at HEAD; run the canonical
      `--post` on clean `main` only after `main`'s `phase-verify`
      run finishes. Before adding a selection, grep the local
      run's SKIPPED lines: a selection that skips on the
      operator's account reads SKIP.
    </requirement>

    <requirement>
      Create `tests/test_phase04_verification.py`, mirroring Phase
      3's: the roadmap and QA documents exist; `--fast` runs; the
      matrix includes `"04"`; checks continue after a failure
      without echoing content; there are exactly 51 static checks;
      skipped evidence cannot pass; the mode flags are exclusive;
      JUnit selections must match; the post matrix reports exactly
      29 rows; and editing a deliverable in memory turns exactly
      its check red.
    </requirement>

    <requirement>
      Update `.github/workflows/phase-verify.yml` to include
      `"04"` in the matrix — append it to the flow list
      `matrix.phase`. Preserve `"01"`, `"02"`, and `"03"`; this is
      an additive change.
    </requirement>

    <requirement>
      Create docs/phase04-qa-findings.md with rollup sections for
      this roadmap's PR and every Step 1 through Step 6 PR, a Step
      7 rollup, the source-drift observations, the live-smoke
      runs, and a "Pre-ship items" section noting documented
      limitations and downstream-phase follow-ups: Phase 5 runs
      its FastAPI app in the `serve` process, subscribes to the
      monitor's cycle listeners for server-sent events, and serves
      the heartbeat, the staleness banner, and the notification
      log; Phase 6's change summary reads the stored change events
      and decisions; Phase 7 adds ntfy behind `Channel`, the
      settings page and per-location preferences over the same
      policy, and retention over the shared geometry content
      (whose orphans this phase keeps); Phase 8 documents
      `install-task` for always-on use; and the operator's `PATH`
      shadow names its owner. Every finding has a destination.
    </requirement>

    <requirement>
      Name every Phase 4 check that a later phase's normal growth
      would turn red (as Phase 3 did for checks 32 and 33), and
      record its historical conversion or its growth-proof form in
      the project roadmap's Phase 5 entry and the QA ledger.
    </requirement>

    <requirement>
      Mark the phase complete in the parent project roadmap
      (docs/roadmap/ROADMAP.md, beside this file) in the SAME
      Stage-3 commit that marks this step (Status rule):

      - `### Phase 4` gets `**Status:** Complete — <YYYY-MM-DD>;
        PR #<n>; v2.0.0-phase-4; phase04-roadmap.md` directly
        under its heading, and the heading ends in ✅.
      - Its row in the "Phase Complexity Summary" table reads
        `Complete` (Step 1's PR set it to `In progress`).
      - The header `> **Status:**` line names Phase 4 as shipped
        and Phase 5 as next.
      - Consistency audit: the Phase 4 "Acceptance criteria" there
        match this roadmap's V1-V7 checks.

      And in THIS roadmap, same commit: its phase-level
      `**Status:**` line (under the title) reads `Complete —
      <YYYY-MM-DD>`, the title and every step heading end in ✅,
      and every step's Summary Table Status cell reads `Complete —
      PR #<n>`. And `README.md`'s Status section, same commit:
      Phase 4 complete and Phase 5 next — the update Phase 3's
      closure missed (check 46).
    </requirement>

    <requirement>
      After the merge, create the annotated tag `v2.0.0-phase-4`
      on the merge commit and push it; `git ls-remote --tags
      origin v2.0.0-phase-4` must show it peeling to the merge
      commit. The package version stays `2.0.0.dev0`.
    </requirement>

    <requirement>
      The script exits 0 on success and 1 on any failure, prints a
      clear PASS / FAIL / SKIP line per check, and mirrors
      `verify_phase03.py`'s output format, check numbering, and
      summary so CI log diffing across phases is frictionless.
      `--fast` must complete in under 30 seconds on Ubuntu CI and
      on the operator's Windows machine. `CHANGELOG.md` and
      `CONTRIBUTING.md` describe it.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative path
      as the first line.
    </requirement>
  </requirements>
</task>
```

### Step 7 acceptance criteria

- `scripts/verify_phase04.py` exists and passes on a clean tree after
  implementation; all six modes exist.
- The script has 51 static checks plus the V1–V7 post-implementation checks (80
  in total).
- `--fast` runs in under 30 seconds on Ubuntu CI and on the operator's Windows
  machine.
- `--post` runs cleanly on the operator's Windows machine with `gh` signed in,
  reporting V1.1 through V7.4 green, Phase 3's 80 checks among them.
- `docs/phase04-qa-findings.md` is complete, with every rollup section and a
  destination for every finding.
- `.github/workflows/phase-verify.yml` runs matrix entries `"01"`, `"02"`,
  `"03"`, and `"04"` on every pull request, under the required aggregate
  `phase-verify`.
- `--security` exits 0 (secret scan, SAST, dependency audit, and the
  personal-data check clean over the phase's surface); V7.4 is green.
- Branch protection still passes on the resulting PR.
- **Deployed & verified:** the first `phase-verify.yml` run on `main` after the
  merge is green with all four entries; `gh api
  repos/nathanramoscfa/weatherbot/branches/main/protection --jq
  .required_status_checks` still names `gate` and `phase-verify`; and `git
  ls-remote --tags origin v2.0.0-phase-4` shows the tag at the merge commit.
- **Operations:** every runtime surface this phase added has a health signal and
  an alarm that has been seen to fire: the heartbeat and its staleness banner (a
  frozen-clock test, V2.3); the degraded-data alarm after 3 consecutive
  failures, with its recovery (V5.2); the stale-monitor alarm the hourly
  fallback raises (V6.2); the toast's delivery results in `notify log` and
  `doctor`'s `toast` check (V4.2, V4.3); and `doctor`'s exit status, whose
  unknown-revision alarm `--post` injected and saw exit 1 (V2.5).
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff, and the `security` job and all four
  `phase-verify` entries are green.
- **Phase closed, nothing carried.** Every finding recorded in
  `docs/phase04-qa-findings.md` has a destination (fixed, an issue number, or a
  named phase that owns it), the "Not in scope" section below is current, and no
  untracked item remains. Every step of this roadmap, this one included, reads
  `**Status:** Complete — PR #…` on `main` under a ✅ heading, the Summary
  Table's Status column and this roadmap's phase-level Status line say
  `Complete` under a ✅ title, and the project roadmap's Phase 4 entry (under a ✅
  heading), its summary-table row, and its header status line say `Complete` —
  all landed in this step's PR. This step's final response ends with the line
  "Step 7 is complete. Phase 4 is complete. You can now move on to Phase 5." in
  place of the usual "Step 7 is complete. You can now move on to Step 8." — same
  Stage 6 rule: no "Follow-ups", no trailer.

---

## Post-Implementation Verification

Every V1–V7 check below runs **automatically in CI** on every push and pull
request, except these. The GitHub readbacks (V1.3), Phase 3's own `--post` sweep
(V1.4), `doctor` against the operator's database with the alarm proof (V2.5),
the desktop run (V4.3, V6.3), the simulated advisory (V5.4), and the operator's
scheduled tasks and heartbeat (V6.4, V6.5) run in `--post` on the operator's
Windows machine, because they need the operator's environment, an interactive
desktop session, or reads the workflow token lacks. The live suite (V2.4, and
every live test) runs in `--live` locally and in `live-smoke.yml`, which is
dispatched by hand.

| Mode         | Workflow                                              | Runner           | Coverage                                                                 |
| ------------ | ----------------------------------------------------- | ---------------- | ------------------------------------------------------------------------ |
| `--fast`     | `phase-verify.yml` (matrix entry `"04"`)              | Ubuntu           | Static checks 1–51: V1.1, V2.1, V3.1, V4.1, V5.1, V6.1, V7.1–V7.3          |
| `--py`       | `ci.yml` (`lint`, `typecheck`, `test` with the coverage floor over the engine and the policy, `package`) | Ubuntu + Windows | V1.2, V2.2, V2.3, V3.2, V3.3, V3.4, V4.2, V5.2, V5.3, V6.2              |
| `--security` | `ci.yml` `security` and `phase-verify.yml`            | Ubuntu           | V7.4 (secret scan + SAST + dependency audit + personal-data check)        |
| `--live`     | `live-smoke.yml` (`workflow_dispatch`)                | Ubuntu           | V2.4 and every live test                                                  |
| `--all`      | none (local)                                          | Windows          | `--py` + `--live` + `--security`                                          |
| `--post`     | local, on the operator's machine                      | Windows          | V1.3, V1.4, V2.5, V4.3, V5.4, V6.3, V6.4, V6.5 + the full V-check sweep  |

Local invocations remain available for ad-hoc runs and pre-release sweeps:

```bash
uv run python scripts/verify_phase04.py --post   # static + V1-V7 + post checks
```

`--post` is the canonical command to run before tagging `v2.0.0-phase-4`. It
shows two test toasts (the desktop test's and the simulated advisory's) and
registers and removes one disabled probe task, and says so before it starts.

Other modes:

```bash
uv run python scripts/verify_phase04.py --fast      # static only (CI-safe)
uv run python scripts/verify_phase04.py --py        # + lint, types, tests
uv run python scripts/verify_phase04.py --live      # + live, landmarks only
uv run python scripts/verify_phase04.py --security  # the four-check gate
uv run python scripts/verify_phase04.py --all       # py + live + security
```

The script reports each V-check by id (V1.1, V2.1, ...) so a failure in any
workflow above maps directly to the corresponding row below.

### V1 — Snapshot storage that stays small

> **Automated in CI.** `phase-verify.yml` → V1.1 and V1.3; `ci.yml` → V1.2;
> `--post` on the operator's machine → V1.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V1.1 | Static checks 1–6 all PASS (revision `0004`, the repository's new write path, hashing and compression, `FROZEN`, the storage tests, the table set). | `phase-verify.yml` runs `verify_phase04.py --fast` on every push/PR.       |
| V1.2 | The geometry-storage, revision `0004`, and storage-growth tests pass: an unchanged cycle adds no content row and under 128 KiB. | `ci.yml` `test` (`--py` locally).                                          |
| V1.3 | `phase-verify (01)`, `(02)`, and `(03)` pass at HEAD on `main`.                               | `phase-verify.yml`; `--post` reads the latest run on `main`.               |
| V1.4 | `verify_phase03.py --post` reports all 80 Phase 3 checks PASS, with Phase 2's 73 and Phase 1's 75 inside it. | `--post`, local only.                                                      |

### V2 — The monitor cycle, the heartbeat, and staleness

> **Automated in CI.** `phase-verify.yml` → V2.1; `ci.yml` → V2.2 and V2.3;
> `live-smoke.yml` and `--live` → V2.4; `--post` → V2.5.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V2.1 | Static checks 7–15 all PASS (revision `0005`, the monitor, the lock, `BEGIN IMMEDIATE`, the staleness rule, the commands, the schemas, the overrides, the tests). | `phase-verify.yml --fast`.                                                 |
| V2.2 | The monitor, lock, health, and writing-transaction tests pass.                                | `ci.yml` `test`.                                                           |
| V2.3 | The status-staleness, check, and config command tests pass, and every document validates against its committed schema. | `ci.yml` `test`.                                                           |
| V2.4 | `check --once` runs against the live services for both landmarks.                            | `live-smoke.yml` (dispatch) and `--live`.                                  |
| V2.5 | `doctor` reports the operator's database at a head that descends from `0006`, and a fresh temporary database gives `doctor --offline --json` exit 0 (`heartbeat`, `toast`, `tasks`, and `path` skipped) and exit 1 once stamped with an unknown revision. | `--post`, local only.                                                      |

### V3 — The notification policy and the notification log

> **Automated in CI.** `phase-verify.yml` → V3.1; `ci.yml` → V3.2 through V3.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V3.1 | Static checks 16–24 all PASS (revision `0006`, the policy and its seven decisions, its purity, the service, the two goldens, the builder, the tests, `notify log`, the ladder document and the coverage flag). | `phase-verify.yml --fast`.                                                 |
| V3.2 | The policy tests pass, every rule and scenario included, and the policy alone reaches 90 percent branch coverage. | `ci.yml` `test`.                                                           |
| V3.3 | Over all eight replays no step is held, every escalation is sent under the defaults and the strict settings, at most one notification goes out per step, and no notification text holds a coordinate, a distance, a bearing, or an instant. | `ci.yml` `test`.                                                           |
| V3.4 | The two Irma notification goldens equal the policy with matching approval digests, and `build_notification_goldens.py --check` passes. | `ci.yml` `test`.                                                           |

### V4 — The Windows toast channel

> **Automated in CI.** `phase-verify.yml` → V4.1; `ci.yml` → V4.2; `--post` (the
> desktop run) → V4.3.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V4.1 | Static checks 25–31 all PASS (the Windows-only dependencies, the channel and its platform guard, escaping, `HKEY_CURRENT_USER` only, the commands, the `desktop` marker, the tests). | `phase-verify.yml --fast`.                                                 |
| V4.2 | The toast, notify-command, and doctor-toast tests pass on a fake notifier, on both runners.   | `ci.yml` `test`.                                                           |
| V4.3 | A real toast on the operator's machine reads `delivered`.                                     | `--post` (`pytest -m desktop`), local only.                                |

### V5 — The scheduler, `serve`, and `check`

> **Automated in CI.** `phase-verify.yml` → V5.1; `ci.yml` → V5.2 and V5.3;
> `--post` → V5.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V5.1 | Static checks 32–39 all PASS (the scheduler and its 60-second cap, no APScheduler, the product hours and offset, the `[monitor]` keys, `serve` and the monitor lock, the log file, the simulation script, the tests). | `phase-verify.yml --fast`.                                                 |
| V5.2 | The scheduler and schedule tests pass on a fake clock — windows, watches, retries, confirmation, resume, and the daylight-time change — with the degraded-data alarm and its recovery. | `ci.yml` `test`.                                                           |
| V5.3 | The log-file, serve-command, and simulate-advisory tests pass.                                | `ci.yml` `test`.                                                           |
| V5.4 | A simulated new advisory during `serve` stores a level-5 escalation within one roster interval with a toast delivery reading `delivered`. | `--post` (`scripts/simulate_advisory.py`), local only.                     |

### V6 — Task Scheduler and health

> **Automated in CI.** `phase-verify.yml` → V6.1; `ci.yml` → V6.2; `--post` →
> V6.3 through V6.5.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V6.1 | Static checks 40–46 all PASS (the task definitions and their principal, absolute executables and no shell, the commands, `--if-stale` and the notification kinds, the machine checks, the tests, the README). | `phase-verify.yml --fast`.                                                 |
| V6.2 | The tasks, fallback, doctor-machine, and task-command tests pass, the stale-monitor alarm included. | `ci.yml` `test`.                                                           |
| V6.3 | A disabled probe task registers unelevated, reads back, and is removed.                       | `--post` (`pytest -m desktop`), local only.                                |
| V6.4 | Both scheduled tasks are enabled under `InteractiveToken` and `LeastPrivilege`, `serve` running or last returning 0, with the installed copy's `doctor` passing its `tasks` check. | `--post` (`services.tasks.query()` and `doctor`), local only.             |
| V6.5 | The `serve` runner row is fresh on the operator's machine.                                    | `--post` (the installed copy's `doctor`), local only.                      |

### V7 — CI integration + security

> **Automated in CI.** `phase-verify.yml` → V7.1 through V7.4 on every push/PR.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V7.1 | `verify_phase04.py --fast` exits 0 on Ubuntu CI.                                              | `phase-verify.yml` matrix entry `"04"`.                                    |
| V7.2 | `phase-verify.yml`'s matrix includes `"01"`, `"02"`, `"03"`, and `"04"`.                        | `phase-verify.yml --fast` static check 50.                                 |
| V7.3 | All 51 static checks in `verify_phase04.py` pass.                                             | `phase-verify.yml --fast` records a pass only when every static check passed. |
| V7.4 | `verify_phase04.py --security` exits 0 (secret scan + SAST + dependency audit + personal-data check). | `phase-verify.yml` `--security` and `ci.yml` `security` on every push/PR.  |

---

## Summary Table

| Step | Scope                         | Model                    | Platform     | Reasoning dial      | Thinking | Conv | Status      |
| ---- | ----------------------------- | ------------------------ | ------------ | ------------------- | -------- | ---- | ----------- |
| 1    | Snapshot storage              | Gemini 4 Argon           | Antigravity  | Effort High         | On       | New  | Complete — PR #41 |
| 2    | Cycle + heartbeat + staleness | Gemini 4 Argon           | Antigravity  | Effort High         | On       | New  | Complete — PR #42 |
| 3    | Policy + notification log     | Gemini 4 Argon           | Antigravity  | Effort High         | On       | New  | Complete — PR #43 |
| 4    | Windows toast channel         | Gemini 4 Argon           | Antigravity  | Effort High         | On       | New  | Complete — PR #46 |
| 5    | Scheduler + serve + check     | Gemini 4 Argon           | Antigravity  | Effort High         | On       | New  | Complete — PR #49 |
| 6    | Task Scheduler + health       | Gemini 4 Argon           | Antigravity  | Effort High         | On       | New  | Complete — PR #50, #51 |
| 7    | QA + verify_phase04.py        | Gemini 4 Argon           | Antigravity  | Effort High         | On       | New  | Not started |
| V1   | Snapshot storage              | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V2   | Cycle + heartbeat + staleness | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V3   | Policy + notification log     | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V4   | Windows toast channel         | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V5   | Scheduler + serve + check     | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V6   | Task Scheduler + health       | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V7   | CI integration                | CI: phase-verify.yml     | --           | --                  | --       | --   | --          |

Each step's row restates the Balanced column its **Runs:** line names; the Cost
and Quality columns, the backups, and the rule for a pool that reads `tight` or
`exhausted` live in the step's own Settings table.

---

## Model selection blocks

```text
PROMPT: Step 1 — Snapshot storage that stays small
MODEL: Gemini 4 Argon
BACKUP: Opus 5.5
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a long-context secondary — content-addressed geometry, a split provenance, a data-preserving downgrade, and a size measurement, High complexity. PICK: Gemini 4 Argon is S-tier in coding (Terminal-Bench 4.0 57.1), the ladder's Balanced pick. EFFORT: High fits an established storage pattern with migration edge cases; the deepest audit is the Quality column's Opus 5.5 at Extra High.

PROMPT: Step 2 — The monitor cycle, the heartbeat, and staleness
MODEL: Gemini 4 Argon
BACKUP: Opus 5.5
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — one cycle path under a cross-process lock, BEGIN IMMEDIATE, a revision, staleness, two commands, and a live run, High complexity. PICK: Gemini 4 Argon is S-tier in coding and agentic work (Terminal-Bench 4.0 57.1), the ladder's Balanced pick. EFFORT: High fits a cross-cutting change whose decisions this roadmap fixes.

PROMPT: Step 3 — The notification policy and the notification log
MODEL: Gemini 4 Argon
BACKUP: Opus 5.5
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a planning secondary — a pure policy with persistent state, held drops, cooldown keys, quiet hours, idempotent decisions, and goldens frozen by one operator review, High complexity and novel. PICK: Gemini 4 Argon is S-tier in coding and planning (AA Intelligence Index 52.6), the ladder's Balanced pick. EFFORT: High fits rules this roadmap states exactly; the widest edge-case search is the Quality column's Opus 5.5 at Extra High.

PROMPT: Step 4 — The Windows toast channel
MODEL: Gemini 4 Argon
BACKUP: Opus 5.5
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a knowledge secondary — the Windows notification platform for an unpackaged app, an honest delivery result, and Windows-only packages kept out of Ubuntu's runs, High complexity. PICK: Gemini 4 Argon is S-tier in coding and knowledge (HLE 57.1%), the ladder's Balanced pick. EFFORT: High fits a platform integration whose library and identity this roadmap chose.

PROMPT: Step 5 — The scheduler, serve, and check
MODEL: Gemini 4 Argon
BACKUP: Opus 5.5
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — an asyncio scheduler on a fake clock, the windows and watches, retries, confirmation, the alarm, two long-running commands, and an on-machine proof, High complexity. PICK: Gemini 4 Argon is S-tier in coding and agentic work (Terminal-Bench 4.0 57.1), the ladder's Balanced pick. EFFORT: High fits timing rules with a measured basis; Opus 5.5 at Extra High is the Quality column's.

PROMPT: Step 6 — Task Scheduler and health
MODEL: Gemini 4 Argon
BACKUP: Opus 5.5
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with an agentic secondary — task definitions, a silent subprocess layer, the fallback, machine checks fenced from the alarm proofs, and an on-machine deployment, High complexity. PICK: Gemini 4 Argon is S-tier in coding and agentic work (Terminal-Bench 4.0 57.1), the ladder's Balanced pick. EFFORT: High fits measured Task Scheduler behaviour turned into code and a deployment.

PROMPT: Step 7 — QA + verify_phase04.py
MODEL: Gemini 4 Argon
BACKUP: Opus 5.5
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: mechanical translation of this roadmap's acceptance criteria into a verification script, a matrix entry, and a findings rollup. PICK: known pattern, no novel reasoning — Gemini 4 Argon, S-tier in coding (Terminal-Bench 4.0 57.1), the ladder's Balanced pick. EFFORT: High is the level the ladder prints for this column; enumerated checks whose content this roadmap already writes down need no more.
```

---

## Not in scope (from product roadmap)

The project roadmap's Phase 4 section carries no "Not in scope" list; these
items follow from its phase boundaries and its §6 "Out of Scope":

- The FastAPI API, server-sent events, the frontend, and browser notifications.
  Phase 5 runs its web server in the `serve` process and subscribes to the
  monitor's cycle listeners.
- Claude, the briefing, the change summary, and the grounded chat. Phase 6 reads
  the stored change events and decisions, and can never set a level or send a
  notification of its own.
- ntfy push, the settings page with per-location notification preferences and
  quiet-hours controls, history views, and retention (of history, raw responses,
  and the geometry content no snapshot uses any more). Phase 7, which proves
  quiet hours end to end through ntfy.
- The PyPI release and the always-on setup guide. Phase 8 documents
  `install-task` for anyone who installs the package.
- Mobile apps, SMS, email, Slack, or Discord, and automated evacuation-order
  ingestion (§6). The operator's toggle stands in for the orders.

Additionally not in scope for this phase:

- Toast buttons, the `urgent` scenario that breaks through Do Not Disturb, and a
  COM activator that persists toasts in the notification center. Step 4 records
  how the notification center treats Weatherbot's toasts; Phase 7 decides
  whether any of these is worth adding.
- Moving the `product_geometries` rows stored before revision `0004` into the
  shared tables. Contraction waits a release, per the project roadmap's
  expand-first rule.
- Running the monitor while the operator is logged off (S4U or a stored
  password). Refused on purpose: no credential is stored, and a toast needs the
  interactive session.
- A service manager on Linux or macOS (systemd, launchd). `serve` and `check`
  run in any terminal; `install-task` is Windows-only, for the operator's
  machine.
- A new change kind. Staleness, held drops, decisions, and deliveries are
  heartbeat, policy, and notification records; Phase 3's check 32 stays exact.
- APScheduler, and any other scheduler library. The Overview's design rationale
  gives the reasons; revisit only if the small scheduler proves wrong in use.
- Storm-surge watches and warnings, and extreme-wind warnings, moving the
  ladder. Issue #33 is the operator's call.
- Recalibrating the development-chance floor. Any phase that records an outlook
  during an active season does it under Source drift.
- Removing the version 1 copies from the operator's `PATH`. The operator's
  housekeeping; `doctor` names it.
- A package version bump. The version stays `2.0.0.dev0` until the release
  candidate in Phase 8; the milestone tag marks the phase.
- Dependabot PRs (#8, #30, and #31 open on 2026-10-21). They are independent
  maintenance, outside every step.

---

_This roadmap is the execution plan for Phase 4. Each step's `**Status:**` line
is flipped by that step's own PR (Status rule), so this file on `main` is the
phase's ledger — `grep -n '^\*\*Status:\*\*'` reports progress. After all steps
and verification pass, and every finding has a destination, Phase 4 is complete
— declared with the line "Phase 4 is complete. You can now move on to Phase 5."
and nothing after it — and Phase 5 (Web app MVP) inherits a `serve` process with
a scheduler and cycle listeners its web server and server-sent events join,
stored cycles, heartbeats, and notifications with their deliveries for its API
and its staleness banner, one policy and one channel interface its browser
notifications reuse, and snapshot storage that stays small under a schedule._
