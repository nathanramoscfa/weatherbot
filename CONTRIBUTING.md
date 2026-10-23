# Contributing to Weatherbot

Weatherbot is a personal hurricane-threat monitor and a public repository.
Version 2 is being built phase by phase from
[the project roadmap](docs/roadmap/ROADMAP.md); read
[AGENTS.md](AGENTS.md) for the rules that apply to every change, whether a
person or an AI coding agent makes it.

## Setup

Weatherbot uses [uv](https://docs.astral.sh/uv/) and Python 3.13.

```sh
git clone https://github.com/nathanramoscfa/weatherbot.git
cd weatherbot
uv sync                      # creates .venv from uv.lock (and installs Python 3.13 if needed)
uv run weatherbot --version  # prints 2.0.0.dev0
```

`uv sync` installs the `dev` and `planning` dependency groups by default.
The `planning` group holds roadmodel, the tool behind `docs/roadmap/`; it is
not an application dependency.

## The checks

The pre-commit hook runs these before every commit (see "Security gate"
below); CI runs them on Ubuntu and Windows and rolls them into the required
`gate` check.

```sh
uv run ruff check          # lint, every rule family selected
uv run ruff format --check # formatting (use `uv run ruff format` to fix)
uv run pyright             # strict type checking
uv run lint-imports        # layer contracts (see AGENTS.md)
uv run pytest              # tests: no network, each in a temporary directory
```

CI's `test` job runs the suite with a coverage floor: at least 90 percent
branch coverage of `weatherbot.engine` and of `weatherbot.services.policy` on
its own. Run the same locally with the coverage data file in a temporary
directory, never the checkout:

```sh
COVERAGE_FILE="$(mktemp -d)/.coverage" uv run pytest \
  --cov=weatherbot.engine --cov=weatherbot.services.policy \
  --cov-branch --cov-report=term-missing:skip-covered --cov-fail-under=90
```

In PowerShell, set `$env:COVERAGE_FILE = Join-Path $env:TEMP "weatherbot.coverage"`
first, then run the same `uv run pytest` command.

The engine's property tests use Hypothesis under one profile, `weatherbot`,
that `tests/conftest.py` registers and loads for the whole suite:
`derandomize=True` (every run tries the same examples, so a failure reproduces),
`database=None` (a run writes no example database), and `deadline=None` (a slow
runner never fails a correct test). Generate positions and shapes in a strategy,
or as offsets from the public landmarks, never as coordinate literals.

Phase 1's repeatable verification is `uv run python scripts/verify_phase01.py`:

- `--fast`: 50 numbered, independent checks, offline and standard-library only.
- `--py`: static checks, lint, formatting, types, import contracts, tests and a
  fresh installed-wheel smoke in a temporary environment.
- `--corpus`: static checks, fetch on missing pinned archives, checksum verification
  and full-cache reconversion tests.
- `--security`: static checks and the four-check security gate; install gitleaks
  locally for the history scan. CI requires it. No denylist value is printed.
- `--all`: the Python, corpus and security suites together.
- `--post`: the canonical 75-check pre-tag sweep, including GitHub readbacks,
  the local updater dry run and a live recording in a temporary directory.

No flag means static plus Python checks. The post sweep reports unavailable
evidence explicitly; phase closure requires every V-row to pass. The findings
and downstream owners are in [the QA ledger](docs/phase01-qa-findings.md).

Phase 2's is `uv run python scripts/verify_phase02.py`, with the same flag
shape and `--live` in place of `--corpus`:

- `--fast`: 47 numbered, independent checks, offline and standard-library only.
- `--py`: static checks, lint, formatting, types, import contracts, the offline
  tests, and the installed-wheel smoke, which also opens a new database at the
  Alembic head.
- `--live`: static checks and `pytest -m live` (landmarks only, in a temporary
  data directory).
- `--security`: static checks and the four-check security gate.
- `--all`: the Python, live and security suites together.
- `--post`: the canonical 73-check pre-tag sweep: the V1-V7 matrix, GitHub
  readbacks, Phase 1's own `--post`, `doctor` against your database (only the
  revision is printed), and a `doctor` alarm against a temporary database
  stamped with an unknown revision. Each V-row reads its own tests from one
  JUnit report of the pytest run. Findings are in
  [the Phase 2 QA ledger](docs/phase02-qa-findings.md).

Phase 3's is `uv run python scripts/verify_phase03.py`, with Phase 2's flags;
`--all` also runs the cached corpus:

- `--fast`: 52 numbered, independent checks, offline and standard-library only.
- `--py`: static checks, lint, formatting, types, import contracts, the offline
  tests with the engine's branch-coverage floor (the coverage data file goes to
  a temporary directory), and the installed-wheel smoke, which also imports the
  engine.
- `--live`: static checks and `pytest -m live` (landmarks only).
- `--security`: static checks and the four-check security gate.
- `--all`: the Python, live and security suites, and one `pytest -m corpus` run
  against the local cache (fetched and verified first).
- `--post`: the canonical 80-check pre-tag sweep: the V1-V7 matrix from one
  offline, one live, and one corpus run, GitHub readbacks, Phase 2's own
  `--post`, `doctor` against your database and its alarm proof, and the replay
  time budget, timed on the two landmarks in a temporary data directory (it
  never runs `status` or `replay` against your locations). Findings are in
  [the Phase 3 QA ledger](docs/phase03-qa-findings.md).

Both `gate` and `phase-verify` are required on protected `main`. The latter
aggregates the `phase-verify (01)`, `phase-verify (02)`, and `phase-verify (03)`
matrix jobs; later phases append their entries and retain the aggregate name. Both workflows run
on every pull request.

The test suite blocks all network access except loopback, and every test
runs in a temporary working directory, so a test can never read or write the
repository through a relative path. A test that must reach a real service is
marked `live`, also carries `@pytest.mark.enable_socket`, and runs only on
request with `pytest -m live`.

### The live suite

`uv run pytest -m live` calls the real services: it fetches the storm
roster, resolves every register layer name in both NHC tropical map services
(each `{slot}` layer for all fifteen slots), queries one outlook layer, and
records the roster into a temporary directory. It also fetches every active
storm's arrival-time KMZ pair and the archived Dorian pair, one TCP list,
the three TWO lists, one outlook map twice (the second request
conditional), the three GIS feeds, both overlay capabilities documents,
and the surge-risk catalog. A test that needs an active storm skips, and
says why, when none is active. The NWS and Nominatim tests send the two
public landmarks of `scripts/public_landmarks.toml` and no other
coordinate: the Miami-Dade point, its alerts, and its three zones; the
Nassau point, which is outside NWS coverage and makes no alert request;
and one reverse lookup per landmark. The command test adds both landmarks
through `locations add` in a temporary data directory, then runs `fetch`,
`storms --json`, `alerts --json` for each landmark, `status --json` (which
assesses and stores both landmarks in that temporary database, and a
`status --no-fetch` rerun that stores nothing new), and `doctor --json`,
validating each document against its committed schema. Run it before a
change that touches a source client or a command, and whenever a register
layer, field, or product may have changed (Source drift).

### The command tests and the JSON Schemas

`tests/cli/` runs every command through Typer's runner, offline: respx serves
every recorded answer, and the fetcher's pacing waits are recorded rather than
slept. Every `--json` document a test produces is validated against its schema
in `docs/schema/`.

Each command's document is a Pydantic model in `src/weatherbot/cli/documents.py`.
After you change one, regenerate the schemas and commit them with the change:

```sh
uv run python scripts/export_schemas.py           # writes docs/schema/*.schema.json
uv run python scripts/export_schemas.py --check   # exits 1 if a committed schema is stale
```

`tests/cli/test_documents.py` fails while a committed schema differs from a
fresh export. A schema holds no example value, and only `locations` has a
field for a coordinate. The disclaimer the commands print ships in the package as
`src/weatherbot/DISCLAIMER.md`; after editing the root `DISCLAIMER.md`, copy
it there byte for byte, or the same test file fails.

The same suite runs on GitHub's hosted runners when you dispatch
`.github/workflows/live-smoke.yml`, which has no other trigger:

```sh
gh workflow run live-smoke.yml --ref main
gh run list --workflow live-smoke.yml --limit 1
```

It is not part of `gate` or of branch protection, and it uses no secret.
Scheduled drift detection belongs to Phase 4.

### The replay corpus

`tests/fixtures/replay/` holds four historical storms as the archive's
products, converted: every advisory's cone, track, points, and watches and
warnings, and each synoptic time's 5 km wind-speed probabilities clipped to
one degree on each side of each public landmark (read a windowed product only
inside its window). `corpus-manifest.json` pins every original by URL, size,
and SHA-256, and every committed file by its SHA-256.
`weatherbot.services.replay.ReplayCorpus` reads it: `ReplayCorpus.open(directory)`,
then `storms()` and `snapshots(atcf_id)`, one `Snapshot(origin="replay")` per
advisory, every file checked against the manifest before it is parsed. Replay
snapshots are never stored.

The originals live in the ignored cache (`.cache/replay-corpus/`, or
`WEATHERBOT_CORPUS_CACHE`). `pytest -m corpus` needs it:

```sh
uv run python scripts/fetch_replay_corpus.py fetch    # download the pinned originals
uv run python scripts/fetch_replay_corpus.py verify   # check every checksum
uv run pytest -m corpus                               # reconvert byte for byte; replay a full conversion
```

For your own locations, convert everything (every forecast product, every
probability product unclipped, and every arrival-time KMZ) into a directory
outside the checkout; the script refuses one inside it, so its 70 MiB can
never reach a commit:

```sh
uv run python scripts/fetch_replay_corpus.py convert --full --out ../weatherbot-replay
```

`ReplayCorpus.open` reads that directory like the committed subset. A change
to the conversion itself is committed with `convert --refresh-subset`, which
rewrites only the manifest's `subset` and `subset_rule` from the verified
cache: review the manifest diff in the pull request. The originals' checksums
never change except through a deliberate `manifest` re-recording.

### Calibrating and reviewing the ladder

`ReplayService(corpus).timeline(atcf_id, location, thresholds)` returns each
advisory's assessment and change events without storing anything. The development
tools build the same two public landmarks from `scripts/public_landmarks.toml`,
the verified recorded NWS answers, and the breakpoint catalogue.

```sh
uv run python scripts/calibrate_ladder.py          # docs/ladder-calibration.json
uv run python scripts/calibrate_ladder.py --check  # repeat all legal-value sweeps
uv run python scripts/build_goldens.py --review-only # eight transition tables and review digest
uv run python scripts/build_goldens.py --check     # frozen timelines and approvals
uv run python scripts/export_ladder.py --check     # the three canonical document tables
```

The operator must approve all eight timelines, with the calibration evidence,
in the PR that changes them. An agent cannot approve its own goldens. After that
explicit approval, record its date and the exact review digest:

```sh
uv run python scripts/build_goldens.py --approve-date YYYY-MM-DD --review-sha256 SHA
```

A first build writes candidates with null approvals. An existing frozen golden
is never silently regenerated: editing its timeline invalidates its approval
digest, and changing the manifest or ruleset invalidates its metadata check.
Any changed golden needs another operator approval recorded in that PR. Review
digests bind all eight candidates and their source/ruleset metadata; an approval
record binds each exact timeline. The approval date is never inferred from a
test run. `tests/engine/test_golden_mutations.py` guards every rule and threshold,
and records the exact adjacent swaps the reference cannot distinguish.

The full-products and arrival cross-checks share one session conversion of the
verified cache in a temporary directory. They run with `pytest -m corpus`; all
ordinary golden tests use only the committed subset and run offline on every PR.
The ordering/reversal exceptions the operator approved on 2026-10-20 are explicit
in [the written ladder](docs/ALERT-LADDER.md), beside the retained watch-lead target.
That document is the shared text the CLI, UI, and Claude prompts quote. After a
rule or threshold metadata change, run `scripts/export_ladder.py` and commit its
rendered tables with the change.

## Local data

Weatherbot keeps its state outside the repository, in your user directories:

| What | Windows | Linux |
| --- | --- | --- |
| Configuration: `weatherbot.toml` (optional) | `%LOCALAPPDATA%\weatherbot\` | `${XDG_CONFIG_HOME:-~/.config}/weatherbot/` |
| Data: the database `weatherbot.sqlite3` and `backups/` | `%LOCALAPPDATA%\weatherbot\` | `${XDG_DATA_HOME:-~/.local/share}/weatherbot/` |

`WEATHERBOT_CONFIG_DIR` and `WEATHERBOT_DATA_DIR` override the two
directories. Each must be an absolute path. `weatherbot.toml` holds the
settings below, and an environment variable overrides each one (environment,
then file, then default): `WEATHERBOT_LOG_LEVEL`,
`WEATHERBOT_HTTP_TIMEOUT_SECONDS`, `WEATHERBOT_ENGINE_<KEY>` for each key
of `[engine]`, such as `WEATHERBOT_ENGINE_COASTAL_REACH_KM`, and
`WEATHERBOT_MONITOR_CYCLE_LOCK_WAIT_SECONDS`. `weatherbot config show` prints
every effective value and where it came from; `weatherbot config path` prints
where the files live. The `[engine]`
values are the alert ladder's calibrated defaults; their outcome intervals and
evidence are in [the written ladder](docs/ALERT-LADDER.md).

```toml
[logging]
level = "INFO"          # DEBUG, INFO, WARNING, ERROR, or CRITICAL

[http]
timeout_seconds = 30    # more than 0, at most 300

[engine]
coastal_reach_km = 25               # 0 to 200
segment_end_tolerance_km = 5        # 0 to 50
cone_horizon_h = 120                # 1 to 120
hurricane_wind_floor_pct = 10       # a band lower bound: 0, 5, 10, 20, ..., 90
tropical_storm_wind_floor_pct = 5   # a band lower bound
development_chance_floor_pct = 0    # a band lower bound

[monitor]
cycle_lock_wait_seconds = 120       # 1 to 3600: how long a cycle waits for another
confirm_after_minutes = 5           # 1 to 60: delay before a held-drop confirmation cycle

[notifications]
cooldown_hours = 6                  # 0 to 48: repeat window per event key
# quiet_hours_start = "22:00"       # HH:MM (00:00 to 23:59), set with quiet_hours_end
# quiet_hours_end = "07:00"         # HH:MM (up to 24:00); start != end
quiet_hours_time_zone = "local"     # "local" or an IANA zone name
```

An unknown key or a bad value stops the program with a message that names the
key and never repeats the value. No setting holds a secret, a location, or a
coordinate. Your locations live in the database.

The database is SQLite in WAL mode. Its schema is the Alembic head of the
migrations in `src/weatherbot/services/persistence/migrations/`, which ship
in the wheel. Opening a database that is behind the head first copies it,
through SQLite's online backup API, to
`backups/weatherbot-<UTC stamp>-<revision>.sqlite3`, then upgrades it. That
copy is the rollback. A database written by a newer Weatherbot refuses to
open, and nothing ever downgrades it.

Revision `0003` adds the assessments `weatherbot status` stores, three tables
written in one transaction per run:

- `assessments`: one row per location, snapshot, and ruleset (the thresholds'
  fingerprint with the rule order). It holds the level, the deciding rule,
  whether every input was available, the thresholds, and the whole assessment
  as JSON, which loads back equal.
- `assessment_evidence`: one row per evidence record of the deciding rule and
  per official product considered, with its kind, rule, source, code or event,
  and distance, for queries.
- `assessment_changes`: the change events from the location's previous stored
  assessment, in order.

Rerunning `status` over the same snapshot and ruleset stores nothing new; a
replay is never stored. An assessment's distances, bearings, and arrival
instants locate the location as surely as its coordinates do, so they stay in
this database and on your terminal, and no log line above DEBUG holds one.
`weatherbot locations remove NAME` removes the location with its alert
observations and its assessments, their evidence and changes included, in the
same transaction: the database cascades every row from the location's.
`weatherbot locations evacuation NAME on|off` sets the operator's toggle and
records when (`locations.evacuation_order_set_at`); a `status` that fetches a
new snapshot assesses with it.

Revision `0004` stores unchanged geometry once, shared by the snapshots that
use it. A product's content (its kind, CRS, GeoJSON, and other fields: all
but its provenance, which carries the fetch's instant) is stored once,
compressed, in `geometry_contents`, keyed by the SHA-256 of its canonical
JSON. Each response's provenance is stored once per snapshot in
`snapshot_provenances`, and `snapshot_geometries` links each product of a
snapshot to its content and its provenance. A second `status` over unchanged
answers therefore adds links and provenances, not products: well under
128 KiB, where every cycle used to add 2.0 MiB
(`tests/cli/test_storage_growth.py`). Snapshots stored before the revision
keep their products in `product_geometries` and load back as they were.
Removing a snapshot removes its links and provenances; a content row is never
changed or removed, and one that no snapshot uses any more stays until
retention arrives (Phase 7).

### The monitor cycle, its lock, and the heartbeat

`weatherbot.services.monitor.MonitorService.run_cycle(trigger)` is the one path
that fetches, stores, assesses, and records. It takes the cycle lock, records
the cycle as started (`monitor_cycles`, revision `0005`), fetches and stores a
snapshot (or uses a stored one, for `status --no-fetch`), assesses and stores
every location (`fetch`, `storms`, and `alerts` skip this), records the
heartbeats and the cycle's end in one transaction, calls its listeners, and
gives the lock back. Every command that fetches goes through it. An exception
records the cycle as `error` with its class name, never its message.

The cycle lock is `cycle.lock` in the data directory, and opening a database
behind the head takes `migrate.lock` there, so two processes migrate it once.
Both are `weatherbot.services.locks.ProcessLock`: the operating system's lock on
the file's first byte (`msvcrt.locking` on Windows, `fcntl.flock` elsewhere),
which the operating system frees when the holding process ends. The holder
writes its process id and start instant to `<lock>.info` for whoever reads the
directory; nothing decides anything from that sidecar. A cycle that waits past
`[monitor] cycle_lock_wait_seconds` is recorded as `skipped`, and the command
says "another cycle is running; try again" and exits 1. Every transaction that
writes begins `BEGIN IMMEDIATE` (`writing_session`), so two processes that write
at once wait for each other (up to the 30-second busy timeout) instead of one
failing with `database is locked`; reads stay deferred.

`heartbeats` holds one row per source, watch, and monitor process: the last
attempt, the last success, the run of consecutive failures with the last error
kind, and the cadence its writer expects. A source that answered (or answered
304) succeeds; one that failed adds a failure; one the cycle did not need (no
active storm, no location inside NWS coverage) records the attempt and clears
its cadence, so it is never stale and never failing. Only a scheduled runner
promises a cadence (three hours per source, NHC's product spacing); a manual
command leaves each row's cadence as it is. The staleness rule
(`weatherbot.services.health.staleness`) calls a row stale when it promises a
cadence and has never succeeded or last succeeded more than twice that cadence
ago. `status` shows a yellow banner for each stale row and lists every row in
its document's `staleness`; `doctor`'s `heartbeat` check is skipped while no row
promises a cadence (so a fresh install exits 0), passes when none is stale, and
fails when one is. Log lines name the runner, the trigger, the cycle, the
status, and counts, never a coordinate, a distance, a bearing, or a URL above
DEBUG.

### The notification policy, goldens, and in-app log

`weatherbot.services.policy.decide` is the pure notification policy: it imports
only `weatherbot.models` and standard-library value types, reads no clock or
I/O, and is scanned by `tests/test_architecture.py` and held to at least 90
percent branch coverage on its own in CI. `NotificationService.decide_cycle`
reconstructs each location's `PolicyState` from `notification_decisions`
(revision `0006`, with `notifications` and `notification_deliveries`), decides
each newly created assessment once in a `BEGIN IMMEDIATE` transaction, and
delivers through the configured channels (starting with `LogChannel`, which
records `log`/`delivered` in SQLite). `weatherbot notify log [--limit N]
[--json]` inspects the in-app log and its `notifications` document.

`scripts/build_notification_goldens.py` freezes the Irma (`AL112017`)
notification timelines at both public landmarks under `defaults` and `strict`
(24-hour cooldown and 00:00–24:00 quiet hours in the landmark's zone) in
`tests/golden/notifications/`:

```sh
uv run python scripts/build_notification_goldens.py --review-only
uv run python scripts/build_notification_goldens.py --check
uv run python scripts/build_notification_goldens.py --approve-date YYYY-MM-DD --review-sha256 SHA
```

As with the engine goldens, an agent never approves notification goldens on its
own; `--approve-date` is run only after the operator explicitly approves the
displayed review digest in the session.

The tests never touch any of this. An autouse fixture in `tests/conftest.py`
points both directories into each test's temporary directory and clears
every other `WEATHERBOT_*` variable except the development tools'
`WEATHERBOT_DENYLIST` and `WEATHERBOT_CORPUS_CACHE`.

To start over, delete the data directory. Weatherbot creates a new database
the next time it opens one. `uv run weatherbot doctor --offline` shows both
directories, the database file, and its revision against the head.

## Security gate

Every commit passes the project's fail-closed security gate
([the roadmap](docs/roadmap/ROADMAP.md), "Per-step security gate"). The
pre-commit hook runs it before each commit, and CI's `security` job runs it
again inside the required `gate` check, so a skipped hook cannot land a
finding on `main`. Any finding blocks the commit.

| Check | What it catches | Before each commit (pre-commit) | In CI (`security` job) |
| --- | --- | --- | --- |
| Secret scan | Credentials, keys, tokens | gitleaks on the staged changes | gitleaks over the pull request's or the push's commits, redacted |
| Personal-data check | Your own values from the denylist, any coordinate that is not a public landmark, a tracked `.env` file | `scripts/check_personal_data.py` on the staged files, with your denylist | `check_personal_data.py --all --ci` and `--self-test --ci` (CI has no denylist) |
| SAST | Injection, unsafe deserialization, weak crypto, path traversal | bandit over `src` and `scripts` | The same |
| Dependency audit | Known-vulnerable or yanked packages | `scripts/audit_deps.py` (pip-audit `--strict` over `uv.lock`) when `uv.lock` or `pyproject.toml` changes | On every run |

The hook also runs ruff, ruff format, pyright, the import contracts, and
hygiene checks: trailing whitespace, final newlines, LF line endings, YAML and TOML syntax,
merge-conflict markers, private keys, files over 5 MB, and no commit on
`main`.

### Set up once per clone

```sh
uv run pre-commit install                                          # run the gate before every commit
uv run python scripts/check_personal_data.py --init-from-env .env  # create your denylist; prints a count only
uv run python scripts/check_personal_data.py --self-test           # prove every rule fires
uv run pre-commit run --all-files                                  # run the whole gate by hand
```

The personal-data check reads a denylist of your own values (your
coordinates, and anything else you add) kept outside the repository, so every
worktree shares it and no commit can carry it:
`%APPDATA%\weatherbot\personal-denylist.txt` on Windows,
`${XDG_CONFIG_HOME:-~/.config}/weatherbot/personal-denylist.txt` elsewhere, or
the path in `WEATHERBOT_DENYLIST`. `--init-from-env` reads `HOME_LAT` and
`HOME_LON` from a dotenv file and writes the pair at two to six decimals in
both orders, plus the values as written; `--add` appends one more value read
from standard input without echoing it. Without a denylist the hook fails
closed and prints these instructions. Never paste a denylist value into an
issue, a pull request, or an AI conversation.

Standalone decimal coordinate entries match whole numeric values, including
equivalent trailing zeros. A prefix of a different, more precise number does not
match; other strings and coordinate pairs still use literal substring matching.

Coordinates in tracked files, requests, fixtures, and examples must be the
public landmarks in `scripts/public_landmarks.toml` (Miami-Dade County Hall
and Parliament Square, Nassau). Any other coordinate fails the check. The
NOAA payload trees, `tests/fixtures/recorded/` and `tests/fixtures/replay/`,
are exempt from the general coordinate rule because storm geometry is full
of coordinates, but the denylist still covers them and every recorded
request URL must use a landmark. The checker's output names the file, the
line, and the rule, never the matched text.

Hook repositories are pinned to full commit SHAs. Refresh them with
`uv run pre-commit autoupdate --freeze` (Dependabot proposes the same
updates weekly), and keep gitleaks at the version CI downloads (see the
comment in `.pre-commit-config.yaml`).

### Bypassing the hook

`git commit --no-verify` skips the hook. Use it only in a genuine emergency,
and record every use in the pull request body with its justification. CI
re-runs the gate regardless, so a bypassed finding still blocks the merge.

## One step, one branch, one pull request

Work follows the phase roadmaps in `docs/roadmap/`:

1. Cut a branch from an up-to-date `main`: `feature/phase01-step2-uv-scaffold`
   names the step it implements.
2. Commit with [Conventional Commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, ...).
3. Open a pull request against `main`. `main` is protected: it takes
   squash merges only, through a pull request, once the required checks pass.
4. One step per pull request; never bundle two.

## Reporting issues

Include your Python version, operating system, the steps to reproduce, and
the expected and actual behavior. Do not include real locations or API keys.
