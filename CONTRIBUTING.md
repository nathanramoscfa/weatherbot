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

Run these before every commit; CI runs them on Ubuntu and Windows and rolls
them into the required `gate` check.

```sh
uv run ruff check          # lint, every rule family selected
uv run ruff format --check # formatting (use `uv run ruff format` to fix)
uv run pyright             # strict type checking
uv run lint-imports        # layer contracts (see AGENTS.md)
uv run pytest              # tests: no network, each in a temporary directory
```

The test suite blocks all network access except loopback, and every test
runs in a temporary working directory, so a test can never read or write the
repository through a relative path. A test that must reach a real service is
marked `live`, also carries `@pytest.mark.enable_socket`, and runs only on
request with `pytest -m live`.

A pre-commit hook with the project's security gate (secret scan, personal
data check, static analysis, dependency audit) arrives in Phase 1 Step 3.
Until then, run `gitleaks git --pre-commit --staged --redact` before each
commit. Never commit credentials, tokens, or anyone's real coordinates:
examples use public landmarks.

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
