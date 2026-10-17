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

Both `gate` and `phase-verify` are required on protected `main`. The latter
aggregates the `phase-verify (01)` matrix job; later phases append their entries
and retain the aggregate name. Both workflows run on every pull request.

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
and one reverse lookup per landmark. Run it before a change that touches a source client, and whenever
a register layer, field, or product may have changed (Source drift).

The same suite runs on GitHub's hosted runners when you dispatch
`.github/workflows/live-smoke.yml`, which has no other trigger:

```sh
gh workflow run live-smoke.yml --ref main
gh run list --workflow live-smoke.yml --limit 1
```

It is not part of `gate` or of branch protection, and it uses no secret.
Scheduled drift detection belongs to Phase 4.

## Local data

Weatherbot keeps its state outside the repository, in your user directories:

| What | Windows | Linux |
| --- | --- | --- |
| Configuration: `weatherbot.toml` (optional) | `%LOCALAPPDATA%\weatherbot\` | `${XDG_CONFIG_HOME:-~/.config}/weatherbot/` |
| Data: the database `weatherbot.sqlite3` and `backups/` | `%LOCALAPPDATA%\weatherbot\` | `${XDG_DATA_HOME:-~/.local/share}/weatherbot/` |

`WEATHERBOT_CONFIG_DIR` and `WEATHERBOT_DATA_DIR` override the two
directories. Each must be an absolute path. `weatherbot.toml` holds Phase 2's
two settings, and `WEATHERBOT_LOG_LEVEL` and `WEATHERBOT_HTTP_TIMEOUT_SECONDS`
override them (environment, then file, then default):

```toml
[logging]
level = "INFO"          # DEBUG, INFO, WARNING, ERROR, or CRITICAL

[http]
timeout_seconds = 30    # more than 0, at most 300
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

The tests never touch any of this. An autouse fixture in `tests/conftest.py`
points both directories into each test's temporary directory and clears
every other `WEATHERBOT_*` variable except the development tools'
`WEATHERBOT_DENYLIST` and `WEATHERBOT_CORPUS_CACHE`.

To start over, delete the data directory. Weatherbot creates a new database
the next time it opens one.

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
