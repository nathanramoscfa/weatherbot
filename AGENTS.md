<!-- AGENTS.md -->
# Weatherbot — operating instructions for AI coding agents

Weatherbot is a personal hurricane-threat monitor: a CLI and a local-only
web app that decide a five-level threat for named locations from official
National Hurricane Center (NHC) and National Weather Service (NWS)
products, notify on change, keep history, and use Claude to explain the
situation in plain language. Version 2 is a from-scratch rewrite planned
in October 2026. Until the Phase 1 scaffold lands, the code on `main`
is version 1: reference material and a source of recorded fixtures, never
a base to extend.

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
  context.md` is personal and git-ignored. The roadmodel updater
  (`/roadmodel-upgrade`, run daily on the maintainer's machine) keeps the
  kit current. Until Phase 1 creates the project's own `.venv`, the
  updater upgrades roadmodel in the registered external environment named
  by the project's line in `~/.config/roadmodel/projects.txt`; Phase 1
  moves roadmodel into a `planning` dependency group in `.venv` and drops
  that override. A step that finds a kit refresh uncommitted commits it
  first, on its own, as `chore(planning): refresh the roadmodel kit to
  <version>`.

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
