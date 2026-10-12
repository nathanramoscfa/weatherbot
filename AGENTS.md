<!-- AGENTS.md -->
# Weatherbot — operating instructions for AI coding agents

Weatherbot is a personal hurricane-threat monitor: a CLI and a local-only
web app that decide a five-level threat for named locations from official
National Hurricane Center (NHC) and National Weather Service (NWS)
products, notify on change, keep history, and use Claude to explain the
situation in plain language. Version 2 is a from-scratch rewrite planned
in October 2026. Version 1 is retired and readable only at the `v1.0.0`
tag: reference material and a source of recorded fixtures, never a base
to extend. `main` holds the version 2 scaffold (Python 3.13, uv), which
later phases fill in.

## Where the plan lives

- `docs/brief/weatherbot-v2-brief.md` — the product specification and the
  operator's recorded decisions (stack, scope, locations, model,
  visibility). Do not edit it to match an implementation; the roadmap
  records departures from it.
- `docs/roadmap/ROADMAP.md` — the project roadmap: phases, architecture,
  branch, security, release, and operations strategy. Read §5 before any
  work.
- `docs/roadmap/phaseNN-roadmap.md` — the executable plan for one phase,
  one step per agent session. Start from the step you were given with
  `/roadmap-step <phase> <step>`; never improvise a step.
- `planning/` — the roadmodel planning kit. When asked to recommend a
  model for a step, run `planning/model-selector.txt` yourself against
  `planning/user-context.md`; do not call an external API or MCP tool
  (`planning/HOW-TO-USE.md`, "you are the engine"). `planning/user-
  context.md` is personal and git-ignored. roadmodel lives in the
  `planning` dependency group in `.venv`. The roadmodel updater
  (`/roadmodel-upgrade`, run daily on the maintainer's machine) upgrades
  it there with pip and re-exports `planning/`, but `uv sync` and every
  `uv run` put `.venv` back on the release `uv.lock` pins. So a step that
  finds a kit refresh uncommitted commits it first, on its own, together
  with the matching lock bump (`uv lock --upgrade-package
  roadmodel==<release>`), as `chore(planning): refresh the roadmodel kit
  to <release>`, taking the release from the latest `[weatherbot] <old> ->
  <new>` line of `~/.config/roadmodel/update.log` rather than from a
  `roadmodel` on `PATH`, which is a separate install.

## Layers and commands

One package, `src/weatherbot/`, with five layers (brief §6). Each layer's
`__init__.py` states its rule; `import-linter` contracts in
`pyproject.toml` and `tests/test_architecture.py` enforce them.

- `sources/` — async HTTP clients, one per official feed. Sources fetch,
  validate, and return typed models with provenance; they never interpret.
- `engine/` — pure functions from a snapshot and a location to an
  assessment. The engine imports nothing from the other layers and no I/O
  library (HTTP, sockets, databases, web frameworks, the Anthropic SDK, or
  schedulers); it is deterministic and tested with recorded and replayed
  data.
- `services/` — time, state, and side effects: scheduling, change
  detection, notification, persistence, and the Claude integration.
- `cli/` — Typer commands over the services.
- `web/` — the FastAPI app over the same services.

Imports run downward only: `cli` and `web` may import `services`;
`services` may import `sources` and `engine`; `sources` and `engine` are
independent siblings and import neither each other nor anything above. The
typed domain models that sources and the engine share get their own
package, `weatherbot.models`, which Phase 2 creates and adds to the
contracts as the lowest layer.

```sh
uv sync                      # create .venv from the lock (dev and planning groups)
uv run weatherbot --version  # prints the version
uv run ruff check            # lint (select = ALL; every ignore states its reason)
uv run ruff format --check   # formatting
uv run pyright               # strict type checking
uv run lint-imports          # layer contracts
uv run pytest                # tests: loopback-only sockets, temporary working directory
```

Tests that call real services carry `@pytest.mark.live` and
`@pytest.mark.enable_socket` and run only with `pytest -m live`. Never run
anything from the repository root that writes through a relative path;
the test suite's working-directory guard exists because that is how
version 1's recorded responses were lost.

## Rules that apply to every step

- **Public repository.** No personal coordinates, API keys, tokens, or
  other secrets in code, fixtures, documentation, examples, or commits.
  The operator's locations and keys live only in local configuration and
  the environment. Documentation examples use public landmarks.
- **Official products decide; Claude narrates.** Alert levels, storm
  positions, watches and warnings, and times come only from fetched NHC
  and NWS products with recorded provenance. No model output is ever
  stored or shown as a fact, and the application must work with AI off.
- **Nothing season-specific in code.** No storm names, advisory slots,
  dates, or home-specific guidance in source or defaults. Locations are
  data.
- **CI runs on GitHub-hosted runners.** The repository is public; never
  point a workflow at a self-hosted runner.
- **One step, one session, one branch, one PR.** The roadmap on `main`
  is the ledger; a step's own PR flips its Status line. Conventional
  Commits on every commit.
- **Disclaimer on every assessment surface.** Weatherbot is informational
  only and never a substitute for official guidance; `DISCLAIMER.md` is
  the full text.
