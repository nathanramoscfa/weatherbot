# Phase 1 Roadmap — Foundation and discovery

**Status:** In progress

## Overview

Phase 1 opens the gate every later phase stands on: a version 2 project
that installs, tests, and gates itself, with real NOAA payloads already
recorded for its tests to replay. It freezes version 1 under the `v1.0.0`
tag, moves the repository to a protected `main`, replaces v1's tree with a
strictly gated uv project on Python 3.13, wires the fail-closed security
gate into pre-commit and CI, writes the data-source register, records a
fixture of every source, and builds the historical replay corpus. It does
not parse a payload into a domain model, store anything in a database, or
compute a level (Phases 2 and 3), and nothing in it runs unattended on the
operator's machine (Phase 4). The work is one phase because each piece is
useless alone: a gate with nothing to guard, fixtures with no test runner,
a register with no recorder.

The phase lands in 7 layers:

1. **Freeze v1 and move to `main`** — prove that PyPI's `weatherbot`
   1.0.0 matches commit `5de67aa` by comparing the published sdist
   against `git archive` (the approved `setup.cfg` formatting exception
   is recorded in Step 1), tag that commit `v1.0.0`, and record v1's
   retirement in `CHANGELOG.md`; rename `master` to `main` on GitHub and
   locally; make merges squash-only with `delete_branch_on_merge`; and
   protect `main` (pull request required, linear history, no force pushes
   or deletions, admins included).
2. **uv scaffold** — replace v1 with `weatherbot` 2.0.0.dev0: a `uv_build`
   `pyproject.toml`, `uv.lock`, `.python-version` 3.13, the five-layer
   package `src/weatherbot/{sources,engine,services,cli,web}` with
   `weatherbot --version`, import-linter contracts and an engine I/O ban,
   strict ruff and pyright, pytest with respx, a socket guard, and a
   working-directory guard; a v2 `ci.yml` on ubuntu-latest and
   windows-latest whose aggregate `gate` becomes the required check; v1's
   code, tests, docs, and packaging deleted; roadmodel moved into a
   `planning` dependency group in `.venv`.
3. **Security gate** — `.pre-commit-config.yaml` with the four-check gate
   (gitleaks, bandit, pip-audit over `uv.lock`, and
   `scripts/check_personal_data.py`) plus ruff, pyright, and import
   contracts; the personal-data checker with a denylist outside the
   repository, a CI pattern set, a public-landmark allowlist, and redacted
   output; a `security` job in CI inside `gate`; Dependabot, alerts,
   private vulnerability reporting, and `SECURITY.md`; a planted fake
   secret and a planted coordinate each shown blocked by the hook and by
   CI.
4. **Data-source register** — `docs/DATA_SOURCES.md`, verified live: one
   row per source id with endpoint, format, fixture class, cadence, terms,
   and verification date; every ArcGIS layer named, never numbered; the
   query parameters the recorder and Phase 2's clients share; the
   per-basin answer to the brief's open question on arrival-time,
   probabilistic-wind, and surge layers; overlays, etiquette, and the
   sources v2 does not use.
5. **Fixture recorder and harvest** — `scripts/record_fixtures.py`
   writing `tests/fixtures/recorded/<source-id>/<yyyy-mm-dd>/` with a
   checksummed `manifest.json`; a capture of every register source; the
   six NHC outlook maps harvested from the surviving v1 reports; contract
   tests that verify every capture and keep the register, the recorder,
   and the recorded service catalogs in agreement; the fixture budget
   enforced by a test.
6. **Replay corpus** — `scripts/fetch_replay_corpus.py` fetching Irma
   (AL112017), Dorian (AL052019), Ian (AL092022), and Milton (AL142024)
   from the NHC GIS archive into a git-ignored cache verified against a
   committed checksum manifest; every advisory's forecast products
   committed as deterministic, compressed GeoJSON under a 10 MiB budget;
   `replay-corpus.yml` restoring the cache in CI and running twice a
   week.
7. **QA + `verify_phase01.py`** — `scripts/verify_phase01.py` (`--fast`,
   `--py`, `--corpus`, `--security`, `--all`, `--post`),
   `docs/phase01-qa-findings.md`, and `.github/workflows/phase-verify.yml`
   with matrix entry `"01"`, whose aggregate `phase-verify` check becomes
   required on `main`; Phase 1 closed in this roadmap and the project
   roadmap; the `v2.0.0-phase-1` tag.

The ship test for Phase 1 is straightforward: `v1.0.0` tags the commit
PyPI's 1.0.0 was built from and `main` is the protected, squash-only
default branch; `uv sync` then `uv run weatherbot --version` prints
`2.0.0.dev0` on Windows and Ubuntu and `git ls-files src/weatherbot` lists
only the v2 skeleton; strict ruff, pyright, import contracts, and pytest
pass in CI on both runners behind the required `gate` check; a planted
fake secret and a planted coordinate are each blocked by the pre-commit
gate and by CI; `docs/DATA_SOURCES.md` covers every source in the brief's
§5 with a verification date; `tests/fixtures/recorded/` holds a
manifest-verified capture of every required register source, including the
six harvested outlook maps, within its budget; the replay corpus script
fetches all four storms with matching checksums and the committed subset
is within its budget; the roadmodel updater's dry run shows this project
on `.venv` with no environment override; and
`scripts/verify_phase01.py --fast` exits 0 on Ubuntu CI with the
`phase-verify (01)` check green.

**Pre-requisite:** None among the phases; Phase 1 is first. It builds on
the v2 planning merge (PR #1, `f071577`), which put the brief, the project
roadmap, the roadmodel planning kit, `AGENTS.md`, and `CLAUDE.md` on the
default branch; this roadmap expands the project roadmap's Phase 1
section.

**Dependency:** Phase 2 does not start until Phase 1's V-checks are green.
Its domain models and source clients are written against the recorded
fixtures (a contract test per source), reuse the register's source ids,
query parameters, and User-Agent, and land under the gate and the required
checks this phase builds; Phase 3's replay harness and golden tests load
the corpus Step 6 commits and caches.

**Design rationale (changes from the project roadmap and the brief).**
Eight changes, each reflected in the project roadmap by this roadmap's own
pull request:

- *The 38 v1 cache responses are gone.* The planning session listed 38
  files in `cache/` at 18:10 EDT on 2026-10-11 (29 NHC responses keyed by
  hash and 9 `atcf_*` invest files from September–October 2025). At
  19:31 EDT the same session ran the v1 test suite from the repository
  root to check CI tool drift, and two v1 tests call `api_cache.clear()`
  on v1's module-level cache, whose directory is the relative path
  `cache/`. Their contents were never copied, `Path.unlink` bypasses the
  Recycle Bin, and a search of the operator's code and profile
  directories found no other copy. The harvest therefore covers the six
  seven-day outlook maps embedded in the surviving v1 reports, and every
  source's fixtures come from live recording. If the operator restores
  the 38 files from a backup taken before 19:31 EDT that day, Step 5
  harvests the ones that belong to a register source.
- *v1 is deleted by the scaffold, not after the recorder.* The v2 package
  and v1 cannot share `src/weatherbot` and one `pyproject.toml` (v2's
  `cli/` package would shadow v1's `cli.py`). v1 stays readable at the
  `v1.0.0` tag; the v1 artifacts worth harvesting are untracked data under
  ignored directories, which no deletion touches.
- *The tracked reports are already removed.* PR #1 deleted the 21 report
  files v1 tracked, and no build artifact is tracked, so Step 1 has only
  the tag, the changelog, the branch, and its protection left.
- *Required checks follow the checks.* Protection lands in Step 1 without
  required status checks, because a required check that no workflow
  produces blocks every pull request; Step 2 requires `gate` once its CI
  reports it, and Step 7 adds `phase-verify`.
- *Dependabot starts with uv and GitHub Actions.* An npm entry with no
  manifest fails every run, so npm joins when `frontend/` lands in Phase 5.
- *Verification is a Python script.* `scripts/verify_phase01.py`, not the
  template's shell script, so it runs natively on the operator's Windows
  machine, falls under ruff and pyright, and matches the maintainer's
  judge-metrics project (`scripts/verify_phaseNN.py`, `phase-verify (NN)`).
- *The Eastern Pacific outlook graphics are `two_pac_*`.* The brief's §5
  names them `two_epac_{2d0,7d0}.png`, which NHC answers with 404 (checked
  2026-10-11); `two_atl_*`, `two_pac_*`, and `two_cpac_*` all return 200.
  The register and the recorder use the working names.
- *Two details move.* The personal-data denylist lives in the user
  configuration directory instead of a git-ignored file in the tree, so
  every worktree shares it and no commit can carry it; and `.venv` gets
  pip from the `planning` dependency group instead of from seeding, so
  `uv sync` keeps it.

**Branch strategy.** Every step in this phase lands on its own short-lived
feature branch (`feature/phase01-step<M>-<slug>`), opens a pull request
against `main`, waits for the project's CI workflow to go green, and
squash-merges with a Conventional Commits subject line. Direct pushes to
`main` are blocked by branch protection from Step 1 on. See the project
roadmap's "Branch management strategy" for the canonical naming
convention, PR rules, and release tagging — this paragraph confirms those
rules apply unchanged within this phase. Per-step branches are listed on
each step header below as `**Branch:**` so reviewers can map commits 1:1
to the step they implement.

**Branch-first execution rule.** The very first action of every step —
before reading any files, before running any tool, before drafting any
change — is to check out the branch named in that step's `**Branch:**`
line:

```sh
git checkout -b feature/phase01-step<M>-<slug>
```

This is non-negotiable. From Step 1 on, `main` is protected with
`enforce_admins: true`, so a commit on `main` cannot be pushed and must be
rewound or rebased onto the feature branch before the PR can open — an
avoidable round-trip. Step 1 alone starts from `master`, because `main`
does not exist until that step renames it. If you discover mid-step that
you started on `main`, recover by running the same `git checkout -b`
command immediately (uncommitted changes carry over to the new branch),
then continue. AI coding agents executing a step from this roadmap must
treat the branch checkout as Step 0 of every step.

**Worktree rule.** One working tree, one step in flight — the lifecycle
below assumes the primary checkout. A second working tree is created only
with `git worktree add`, and only for the three cases the project
roadmap's "Worktree strategy" sanctions: a `hotfix/` branch interrupting
this step (cut from `origin/main` in its own worktree so this step's tree
is untouched); steps the Execution Order below explicitly draws in
parallel (this phase draws none); and worktree-isolated subagents inside a
step (throwaway trees that merge back into the step branch locally and are
removed before the PR opens). In those cases Stage 1 becomes `git fetch
origin && git worktree add -b feature/phase01-step<M>-<slug>
<worktree-path> origin/main`, the worktree is bootstrapped before any test
or build (`uv sync` in the worktree — a worktree has none of the primary
tree's untracked state, and it must never borrow the primary tree's
`.venv`), the Stage 4 merge runs from the primary tree, and Stage 5
removes the worktree BEFORE pruning the branch. Undeclared parallelism is
a lifecycle violation, not a shortcut. Worktree location for this project:
git-ignored `.worktrees/<branch-slug>/` inside the repository, matching
the project roadmap (Step 2 adds the ignore rule).

**Security-first execution rule.** Security is not a phase — it is a gate
on every commit of every step. Before each `git commit`, the step's work
must pass the local, fail-closed security gate: secret/personal-data scan
clean, SAST clean, dependency audit clean, and a diff review confirming no
sensitive data (the operator's coordinates, credentials, tokens) and no
new insecure pattern (injection, unsafe archive extraction, over-broad
scope, secret in a log line or a fixture). From Step 3 on, this gate is
wired into the pre-commit hook and re-run in CI, so a security issue
introduced while implementing a step is caught during development —
before it reaches the branch, the PR, or `main`; Steps 1 and 2 run the
same checks by hand, as their `<security>` blocks say. See the project
roadmap's "Security & privacy strategy" → "Per-step security gate" for
the canonical checks and tooling; each step's XML `<task>` carries a
`<security>` block restating them for the agent, and each step's
Acceptance Criteria ends with a security check. AI coding agents
executing a step MUST treat the security gate as part of the step's
definition of done, exactly like its tests. This matters most here: the
repository is public, so a coordinate or a key that reaches a commit is
published permanently.

**Deploy-and-verify rule.** Merged is not deployed, and deployed is not
released. Every step header carries a `**Deploys:**` line naming the
surface and environment the step's merge reaches — or `nothing beyond
merge` — and when going live needs a repository-settings change, a tag,
or a workflow run, the line says so and this step (or a named follow-on
step) owns that event. For a step whose Deploys line names a surface,
Stage 4 of the lifecycle does not end at the squash-merge: the step's
acceptance criteria carry a **Deployed & verified** bullet (the GitHub
setting reads back as specified, or the workflow's first run on `main`
is green), and that bullet must be green before the step is declared
complete. This phase introduces no required environment variable and no
shared secret (Steps 3 and 6 add optional path overrides only); Step 2
retires the one secret v1 used. See the project roadmap's
"Release & deployment strategy" for the surfaces table, promotion path,
and rollback.

**Triage rule.** Findings surfaced while executing a step are classified
before they are acted on, per the project roadmap's "Defect handling &
triage": spec rot → edit this roadmap's affected `<task>` block now;
upstream gap → patch the earlier step's prompt and add it to the
carry-over checklist; implementation bug → fix in-step only if it blocks
this step's acceptance criteria, otherwise an issue and its own branch in
a fresh conversation; architectural question → an issue for a future
phase; process improvement → recorded where the next conversation will
read it; security finding → jumps the queue by severity; source drift (a
NOAA layer, field, or product changed or vanished) → re-record, update
`docs/DATA_SOURCES.md` with the date, and add a contract test in the same
PR. A step's PR contains the step plus blocking fixes only, and lists the
issues it opened. When a merged PR auto-closes an issue, the environment
check is what earns the close — reopen or follow up if a gap remains.
`docs/phase01-qa-findings.md` is the rollup: every finding, its class,
and the guard added so the class cannot recur.

**Status rule.** Every step carries a `**Status:**` line directly under
its `## Step N — …` heading, before the Goal, and this file on `main` is
the ledger of what is done — never a chat transcript, never a later
conversation reconstructing history from `git log`. The line reads `Not
started` when this roadmap is written and is flipped by the step's OWN
pull request: at Stage 3, right after `gh pr create` returns the PR
number, the agent sets it to `Complete — PR #<n> (<YYYY-MM-DD>)`, appends
` ✅` to the step's heading (`## Step 3 — Security gate ✅`) so the
completion shows in the rendered preview, the outline, and the table of
contents, sets the step's Summary Table Status cell to `Complete — PR
#<n>`, commits that edit on the step branch, and pushes. The PR therefore
carries its own completion mark, and the roadmap on `main` says a step is
complete exactly when that step's PR merges — never before. This file's
phase-level `**Status:**` line (under the title) and the project roadmap
are marked the same way, in the same commit: Step 1's PR flips both from
`Not started` to `In progress` (the project roadmap's `### Phase 1` line
reads `In progress — phase01-roadmap.md`), and the final step's PR flips
both to `Complete — …` (the project roadmap's with its row in the "Phase
Complexity Summary" table and the header `> **Status:**` line) and
appends ` ✅` to this file's `# ` title and to the project roadmap's `###
Phase 1` heading, so the project roadmap shows a finished phase the way
this file shows a finished step. There is no separate "update the
roadmaps" chore: a step whose PR merged without its Status line is a
lifecycle violation, and the next step's Stage 1 (and `/roadmap-step`)
refuses to start until the previous step reads `Complete`. If a
post-merge check fails — a Deployed & verified bullet, an alarm that never
fired — the step is NOT complete despite the merged line; say so, and the
`hotfix/` PR that completes it appends its own number to the line.
`grep -n '^\*\*Status:\*\*'` on this file is the phase's progress report,
and the ✅ headings are the same report at a glance.

**Step lifecycle.** Every step in this phase follows the exact same
six-stage lifecycle, in order, with no exceptions. Each stage is a hard
checkpoint — if a stage is skipped, branch protection or the next step's
Stage 1 will fail loudly, and that is the safety net. AI coding agents
MUST execute all six stages before declaring a step complete.

1. **Create the branch.** Before any Read / Edit / Bash, run `git checkout
   -b feature/phase01-step<M>-<slug>` from a clean, up-to-date `main`
   (Step 1: from `master`). The exact branch name comes from this step's
   `**Branch:**` line. When the Worktree rule applies, the equivalent is
   `git fetch origin && git worktree add -b <branch> <worktree-path>
   origin/main`, followed by the worktree's bootstrap.

2. **Work on the branch, passing the security gate before every
   commit.** All commits land here. Never push to `main` directly —
   branch protection (`enforce_admins: true`) rejects it. Before each
   `git commit`, run the local security gate (secret/personal-data scan,
   SAST, dependency audit, sensitive-data diff review — see the step's
   `<security>` block and the project roadmap's "Per-step security
   gate"). It is fail-closed: a finding blocks the commit, so a security
   issue in this step's work is caught here, before the PR and before
   `main`.

3. **Open the PR, then mark the step.** `gh pr create --base main --head
   <branch>` with a Conventional Commits title and a body that references
   this roadmap step and its acceptance criteria. One PR per step; never
   bundle two steps into one PR. Then, with the PR number in hand, set
   this step's `**Status:**` line (directly under its heading) to
   `Complete — PR #<n> (<YYYY-MM-DD>)`, append ` ✅` to the step's `##
   Step` heading, set its Summary Table Status cell to `Complete — PR
   #<n>`, commit that edit on the step branch (`docs: mark Phase 1 Step
   <M> complete`), and push — the PR now carries its own completion mark,
   so the roadmap on `main` will say the step is complete exactly when the
   PR merges (Status rule). On the phase's first step, the same commit
   sets this roadmap's phase-level `**Status:**` (under its title) and the
   project roadmap's Phase 1 `**Status:**` to `In progress`; on the final
   step, both to `Complete`, with ` ✅` appended to this roadmap's `# `
   title and to the project roadmap's `### Phase 1` heading.

4. **Wait for green checks, then squash-merge.** Every required status
   check must report success: the aggregate `gate` check of `ci.yml`
   (lint, typecheck, the test matrix, the package smoke, and from Step 3
   the security scan) from Step 2 on, and `phase-verify` from Step 7 on;
   before Step 2, v1's CI must still be green. If the PR goes BEHIND
   main while waiting, refresh with `gh pr update-branch --rebase` — never
   merge `main` into the branch; `required_linear_history: true` enforces
   rebase. Once every check is green:

   ```sh
   gh pr merge <PR_NUMBER> --squash --delete-branch
   ```

   If this step's `**Deploys:**` line names a surface, the merge is not
   the finish line: run the Deployed & verified check from the acceptance
   criteria against the target environment now (see the Deploy-and-verify
   rule) before declaring the step complete.

5. **Retire the branch (remote + local).** The `--delete-branch` flag
   plus the repo's `delete_branch_on_merge: true` setting (from Step 1)
   retire the remote automatically. Sync local state and prune the merged
   branch plus any other `[gone]` labels left over from prior PRs:

   ```sh
   git switch main
   git pull --ff-only origin main
   git fetch --prune origin
   git branch -vv | grep ': gone]' | awk '{print $1}' \
     | xargs -r git branch -D
   ```

   If this step ran in its own worktree, remove it FIRST — `git worktree
   remove <worktree-path>`, then `git worktree prune` — because `git
   branch -D` refuses a branch still checked out in a worktree. Confirm
   with `git branch -vv` that only `main` and any intentional long-lived
   branches remain locally, and with `git worktree list` that only the
   primary tree remains.

6. **Dispose of every finding, declare completion, then new
   conversation.** Before you declare anything, walk the findings this
   step surfaced and send each to its destination per the Triage rule
   above — a note that a later step needs is edited into that step's
   `<task>` block now; a wrong claim in this step's spec is fixed in this
   roadmap now; an implementation bug is fixed in-step or exists as an
   issue with a number; a judgement call you made in the diff is explained
   in the PR body; a process lesson is written where the next conversation
   reads it. A finding you can only *describe* has not been disposed of,
   and an undisposed finding is an unmet acceptance criterion. Only once
   the PR is merged — and `main` therefore carries this step's `Complete`
   Status line — every acceptance criterion is affirmatively met, and
   every finding has a destination, say so plainly: end your final
   response with an explicit, unhedged completion line — verbatim shape
   "Step <M> is complete. You can now move on to Step <M+1>." — so the
   operator has a clean stopping point at which to close this
   conversation. That line is the LAST line of the response. Nothing
   follows it: no "Follow-ups (non-blocking)", no "Notes", no "Next", no
   "worth a glance", no suggested improvements. If you want to show your
   work, a short ledger may PRECEDE the line, one entry per finding naming
   its destination (an issue number, a file you edited, the PR body) —
   never an open item. If any acceptance criterion is NOT met, or any
   finding has no destination yet, do the opposite — state plainly that
   the step is NOT complete, name what is outstanding, and do not emit the
   completion line. "Done" means done, not "done, but here is what you
   still have to do". Then, for phase-boundary hygiene, the operator
   closes this Claude Code / Codex session and opens a fresh one before
   starting Step <M+1>; the new conversation begins again at Stage 1 of
   this lifecycle, with the next step's `**Branch:**` line driving the
   `git checkout -b` command. No work straddles two steps.

---

## Current State (before Phase 1)

### Repository and branch surface

- The default branch is `master` at `f071577` (PR #1, the v2 planning
  merge of 2026-10-11) in a public repository with no branch protection,
  no rulesets, and no tags. Squash, merge-commit, and rebase merges are
  all allowed and `delete_branch_on_merge` is off, so PRs merge with `gh
  pr merge --squash --delete-branch`. Secret scanning and push protection
  are on; Dependabot security updates are off; the one Actions secret,
  `SAFETY_API_KEY`, serves only v1's Safety scan.
- The last v1 commit is `45623a1` (2025-09-29 13:31 EDT). PyPI's
  `weatherbot` 1.0.0 wheel and sdist were uploaded 23 minutes later
  (17:54 UTC), which makes `45623a1` the presumptive source of the
  release; Step 1 proves it by diffing the published sdist before tagging.
  `CHANGELOG.md` dates 1.0.0 as 2024-01-15, which PyPI's upload record
  contradicts.
- `master` is named in `AGENTS.md` (the code on `master`, the roadmap on
  `master`), in the project roadmap (§2's gap table, "Changes from the
  brief", and §5's "Branching model"), in `pyproject.toml`'s project URLs,
  and in v1 CI's triggers (`[master, main, develop]`, so v1 CI also runs
  on pull requests to `main`).
- The machine's GitHub token lacks `read:org`, so `gh pr edit` fails;
  `gh pr create`, `gh pr merge`, and `gh api` work, and a PR body is
  edited with `gh api -X PATCH repos/nathanramoscfa/weatherbot/pulls/<n>
  -F body=@<file>`.

### v1 code and packaging surface

- About 9,000 lines of Python 3.11 in 25 modules under `src/weatherbot/`
  (`cli.py` alone is 1,570 lines), 18 test files with 366 tests, a
  setuptools `pyproject.toml` (version 1.0.0, `requires-python >=3.11`,
  sixteen runtime dependencies including matplotlib, pandas, folium,
  tkintermapview, openai, and beautifulsoup4), `setup.cfg`,
  `MANIFEST.in`, `Makefile`, `pyrightconfig.json`, `.safety-project.ini`,
  `env.example`, four PowerShell scripts under `scripts/`, twelve v1
  documents under `docs/`, `.vscode/settings.json`, `logs/.gitkeep`, and
  `state/.gitkeep`. A v1 pre-commit file exists but is named
  `pre-commit-config.yaml` without the leading dot, so no hook ever ran.
- v1 is reference material only (`AGENTS.md`): readable forever at
  `v1.0.0` once Step 1 tags it, never imported or extended. The one text
  the brief carries forward, the ladder wording in
  `src/weatherbot/alert_levels.py` and `docs/alerts.md`, is read from the
  tag by Phase 3's `docs/ALERT-LADDER.md`.
- Hazard: v1 creates a module-level `APICache()` whose directory is the
  relative path `cache/`, and `tests/test_atcf_client_comprehensive.py`
  and `tests/test_nhc_comprehensive.py` call `api_cache.clear()` on it.
  Running the v1 suite from the repository root deletes every file in
  `cache/`. No step in this phase runs v1 code or tests.

### v1 artifacts surface

- `cache/` held 38 recorded responses at 18:10 EDT on 2026-10-11 and was
  cleared at 19:31 EDT by the v1 test run described in the Overview; one
  78-byte test entry is left. The 38 responses are lost unless the
  operator holds a backup taken before that time.
- `reports/` (ignored, untracked) holds six v1 reports dated 2025-09-30,
  10-03, 10-04, 10-06, 10-22, and 10-23. They embed ten official NOAA
  graphics as base64 PNG: one NHC seven-day Atlantic outlook map per
  report (`alt="NOAA 7-Day Atlantic Tropical Weather Outlook"`, 900×665,
  from `xgtwo/two_atl_7d0.png`) and four forecast-cone graphics (897×736:
  Humberto, Imelda, and Melissa twice). A scan found no coordinate pair in
  any report. A seventh report, written by the 2026-10-11 test run, holds
  no image.
- `.env` (ignored, 2025-09-27) is v1's configuration and holds the
  operator's `HOME_LAT` and `HOME_LON` and an OpenAI key slot. It is the
  source of the personal-data denylist Step 3 creates; no step prints,
  copies, or commits its values.

### CI and tooling surface

- v1's `.github/workflows/ci.yml` runs one Windows job on Python 3.11 and
  3.12 with actions pinned by tag (`actions/checkout@v4`,
  `actions/setup-python@v5`, `codecov/codecov-action@v4`), ruff with 25
  ignored rules, mypy, bandit and Safety both made non-failing, pytest,
  and a Codecov upload. It went green on PR #1.
- On the operator's Windows machine: uv 0.12.15, gitleaks 8.30.1, GitHub
  CLI 2.76.2, Node, and Python 3.11 only — Python 3.13 comes from `uv
  python install 3.13`. pre-commit exists only in the external
  environment the roadmodel registry points at.
- The maintainer's public judge-metrics project
  (`https://github.com/nathanramoscfa/judge-metrics`) runs this stack and
  is the working precedent: `uv_build`, a `planning` dependency group
  with `[tool.uv] default-groups`, local `uv run` pre-commit hooks,
  `scripts/audit_deps.py` for pip-audit over `uv.lock`, SHA-pinned actions
  (`actions/checkout`, `astral-sh/setup-uv`), and `scripts/verify_phaseNN.py`
  with a `phase-verify.yml` matrix. Steps 2, 3, and 7 mirror it.

### Planning kit surface

- `planning/` is roadmodel 0.2.80's export (re-exported, unchanged, when
  this roadmap was written) and `planning/user-context.md` is ignored. The
  project's line in `~/.config/roadmodel/projects.txt` carries a `venv:`
  override to an external environment; Step 2 moves roadmodel into the
  project's `.venv` through a `planning` dependency group and drops the
  override. Personal agent context (`.roadmodel/`, `.agents/`,
  `AGENTS.override.md`, `CLAUDE.local.md`) is excluded through
  `.git/info/exclude` and stays that way.

### Security & sensitive-data surface

- Data in play: the operator's coordinates (in `.env`, and possibly in
  v1's ignored `logs/` and `state/`), the public repository's permanent
  history, and NOAA payloads, which are in the public domain. Phase 1
  introduces no secret: every NOAA source is keyless, and the only
  credential, `SAFETY_API_KEY`, is retired in Step 2.
- Controls today: GitHub secret scanning with push protection, and
  `.gitignore` entries for `.env`, `cache/*.json`, `reports/*.html`, and
  `planning/user-context.md`. Missing: a pre-commit gate, a personal-data
  check, a dependency audit that can fail, SHA-pinned actions,
  least-privilege workflow permissions, and branch protection.
- The pattern every step mirrors: only public-landmark coordinates (one
  in Miami-Dade, one in Nassau, listed with their public sources in
  `scripts/public_landmarks.toml` from Step 3) appear in tracked files,
  requests, or fixtures; the operator's values live only in a local
  denylist outside the repository, which no command prints and CI never
  sees; a check's output names a file, a line, and a rule, never the
  matched text.

### Operations & observability surface

- Phase 1 adds no service and nothing that runs unattended on the
  operator's machine. Its operating surfaces are GitHub's: CI on every
  push and pull request, Dependabot's weekly runs, and a replay-corpus
  workflow (Step 6) that runs twice a week, which keeps the corpus cache
  ahead of GitHub's seven-day cache eviction and detects archive drift.
  Each reports by run status, and a failure reaches the operator through
  GitHub's failure email (project roadmap §5, "Health signals"). Step 6
  dispatches a deliberate failure once to see that alarm fire.

### Documentation surface

- `README.md` still describes v1, including the "global coverage" the
  brief retracted; `CONTRIBUTING.md` describes v1's setup; `DISCLAIMER.md`
  and `LICENSE` carry forward unchanged; `CHANGELOG.md` holds v1 history.
  The brief and the project roadmap live in `docs/brief/` and
  `docs/roadmap/`; `AGENTS.md` (imported by `CLAUDE.md`) still describes
  the pre-scaffold state.

### Verification surfaces

- No verification script and no `.github/workflows/phase-verify.yml`
  exist. Step 7 writes the first, `scripts/verify_phase01.py`, and the
  workflow with matrix entry `"01"`; later phases of this project mirror
  them. The structural precedent is the newest `scripts/verify_phaseNN.py`
  on judge-metrics' `main` (`verify_phase04.py` on 2026-10-11): numbered,
  independent static checks, modes from `--fast` to `--post`, and a
  V-matrix report.

---

## Execution Order

```
Step 1  (freeze v1, main)                 v1.0.0 tag + CHANGELOG note
                                          + protected, squash-only main
                                          → implement
  ↓
Step 2  (uv scaffold)                     pyproject + uv.lock + skeleton
                                          + strict tools + v2 CI; v1 gone
                                          → implement
  ↓
Step 3  (security gate)                   pre-commit gate + personal-data
                                          check + CI security + Dependabot
                                          → implement
  ↓
Step 4  (data-source register)            docs/DATA_SOURCES.md, verified
                                          live, with per-basin layer table
                                          → implement
  ↓
Step 5  (fixture recorder)                scripts/record_fixtures.py +
                                          recorded captures + harvest
                                          → implement
  ↓
Step 6  (replay corpus)                   scripts/fetch_replay_corpus.py +
                                          committed subset + corpus CI
                                          → implement
  ↓
Step 7  (QA + verify_phase01.py)          scripts/verify_phase01.py
                                          + docs/phase01-qa-findings.md
                                          + phase-verify.yml entry "01"
                                          → create

--- post-implementation ---

V1  v1.0.0 tags the release commit; main is the protected,
    squash-only default branch.
V2  weatherbot --version prints 2.0.0.dev0 on both runners;
    only the v2 skeleton remains; strict tools green.
V3  The four-check gate blocks planted values in the hook and
    in CI; actions pinned; gate is required.
V4  The register covers every §5 source with a verification
    date and the per-basin layer answer.
V5  Every required register source has a manifest-verified
    capture within budget, plus the six outlook maps.
V6  The corpus fetches four storms with matching checksums;
    the committed subset is within budget.
V7  verify_phase01.py --fast and --security exit 0 in
    phase-verify (01); the phase is closed.
```

Steps are sequential by dependency. Step 2 cuts its branch from the
protected `main` Step 1 creates and names the `gate` check that Step 1's
protection is waiting for; Step 3 wraps the tools Step 2 installs and adds
its `security` job to Step 2's `gate`; Step 4's register is committed
under Step 3's gate, whose landmark allowlist it cites, and it fixes the
source ids, layer names, query parameters, and User-Agent that Step 5's
recorder implements; Step 6 reuses Step 5's HTTP settings, compression
rule, and budget test, and reads the archive map Step 4 wrote; Step 7
verifies every prior step. This phase draws no steps in parallel, so the
Worktree rule permits no concurrent steps.

---

## Step 1 — Freeze v1 and move to `main` ✅

**Status:** Complete — PR #3 (2026-10-12)

> **Goal:** Preserve version 1 exactly as PyPI published it and put the
> repository on the branch and rules every later step assumes. Prove that
> PyPI's `weatherbot` 1.0.0 matches `5de67aa` by downloading the
> published sdist (checksum-verified against PyPI's digest, never
> installed) and comparing it against `git archive 5de67aa`, allowing
> only the approved `setup.cfg` formatting difference, then create the
> annotated tag `v1.0.0` on that commit and push it; add the v1 retirement
> note to `CHANGELOG.md` and correct the 1.0.0 date to 2025-09-29; rename
> `master` to `main` through GitHub's branch-rename API and in the local
> clone; make merges squash-only with the PR title as the commit subject
> and `delete_branch_on_merge` on; protect `main` (a pull request with zero
> approvals, linear history, conversation resolution, no force pushes or
> deletions, admins included); and replace the `master` wording in
> `AGENTS.md` and the project roadmap. Required status checks wait for
> Step 2, whose CI creates the `gate` check they will name. This step lands
> the ground rules; Steps 2–7 build on a protected `main`.

**Branch:** `feature/phase01-step1-freeze-v1`

**Deploys:** GitHub repository → the `v1.0.0` tag, `main` as the default
branch, the merge settings, and branch protection, all applied by this
step through the GitHub API before its PR opens; the merge itself changes
documentation only.

| Setting      | Value                                  |
| ------------ | -------------------------------------- |
| Model        | GPT-6.1 Sol                            |
| Backup       | Sonnet 5.5 — Claude Code · Effort High |
| Platform     | Codex                                  |
| Intelligence | Medium                                 |
| Conversation | **New**                                |

> Settings updated 2026-10-12: was GPT-6 Sol · Medium.
> Ran GPT-6.1 Sol · Medium, the newer version in the same model line.

**Model rationale:** Ordered repository operations through `git`, `gh`,
and the GitHub REST API, with two short documentation edits, are agentic
work (coding secondary) of Medium complexity: the risk lives in the order
of the outward actions, which this prompt fixes, not in reasoning depth.
The selector's quality pick at that level is Sonnet 5.5, but the
claude.ai Max weekly pool reads `tight` until Tue 2026-10-13 20:00 EDT,
so the selector sends this Medium step to the funded pool with headroom:
GPT-6 Sol on Codex, S-tier agentic and S-tier coding, paid by the ChatGPT
Pro 5x subscription at $0 marginal. Intelligence is set to Medium
explicitly, to match the step's Medium complexity rather than whatever
rung the model opens on. The Backup is Sonnet 5.5 on Claude Code
(claude.ai Max) at Effort High, the capped ladder's tight-pool rung for
Medium work. The conversation is new per phase-boundary hygiene.

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
       feature/phase01-step1-freeze-v1`
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
       Phase 1 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 1`
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

    THIS STEP: the hook does not
    exist yet (Step 3 wires it), so
    run the gate by hand before
    each commit: `gitleaks git
    --pre-commit --staged --redact`
    (gitleaks 8.30.1 is
    installed). The diff is
    documentation only, so SAST
    and the dependency audit have
    nothing to scan; say so in the
    PR body. The sensitive-data
    review covers the protection
    payload (no bypass actor, no
    force-push allowance) and the
    changelog text. The sdist and
    the payload file stay in the
    session scratch directory and
    are never committed.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 1 (Foundation and
    discovery). Step 1: Freeze v1 and move to `main`.

    Current state (before Phase 1; no step has run):

    - The default branch is `master` at `f071577` (PR #1,
      the v2 planning merge). `main` does not exist yet; until
      this step renames the branch, `master` is the ledger.
    - The last v1 commit is
      `45623a17ef3c6c3f96395f35ad211c7054c5cbbb` (2025-09-29
      13:31 EDT). PyPI lists `weatherbot` 1.0.0, wheel and
      sdist, uploaded 2025-09-29 17:54 UTC. No tag exists
      locally or on `origin`.
    - GitHub: no branch protection and no rulesets; squash,
      merge-commit, and rebase merges allowed;
      `delete_branch_on_merge` false; secret scanning and
      push protection on. v1's `.github/workflows/ci.yml`
      runs on pushes and PRs to `master`, `main`, and
      `develop`, so it checks this step's PR to `main`.
    - `gh pr edit` fails on this machine's token (no
      `read:org`): edit a PR body with `gh api -X PATCH
      repos/nathanramoscfa/weatherbot/pulls/<n> -F
      body=@<file>`.
    - `CHANGELOG.md` dates 1.0.0 as 2024-01-15 and keeps a v1
      `[Unreleased]` section above it.
    - Do not run v1 code or its tests: two v1 tests clear the
      working-directory `cache/`, which is how the 38
      recorded responses were lost on 2026-10-11 (this
      roadmap's Overview).

    Files to read (every file before drafting):
    - docs/roadmap/phase01-roadmap.md (this roadmap: the
      Overview rules, Current State, and this step).
    - docs/roadmap/ROADMAP.md (§5 "Branch management
      strategy" and the Phase 1 section).
    - AGENTS.md and CLAUDE.md (project rules; the `master`
      wording to replace).
    - CHANGELOG.md (the retirement note and the date fix).
    - .github/workflows/ci.yml (v1 CI's triggers).
  </context>

  <goal>
    Tag `v1.0.0` on the commit PyPI's 1.0.0 was built from,
    proven by an sdist comparison; record v1's retirement in
    `CHANGELOG.md`; make `main` the protected, squash-only
    default branch on GitHub and in the local clone; and
    update the `master` wording in `AGENTS.md` and the project
    roadmap.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Stage 1 for this step only: `main` does not exist yet,
      so cut the branch from a clean, up-to-date `master`
      (`git switch master && git pull --ff-only && git
      checkout -b feature/phase01-step1-freeze-v1`). After
      the rename below, `main` points at the same commit and
      Stages 3 to 5 run as written.
    </requirement>

    <requirement>
      Prove the tag target without running package code. Read
      the sdist URL and its SHA-256 digest from
      `https://pypi.org/pypi/weatherbot/1.0.0/json`, download
      `weatherbot-1.0.0.tar.gz` into the session scratch
      directory with `curl`, verify the digest, and extract it
      there. Extract `git archive 45623a1` beside it and
      compare `src/weatherbot/**` and the top-level files the
      sdist carries (`pyproject.toml`, `setup.cfg`,
      `README.md`, `LICENSE`, `DISCLAIMER.md`,
      `MANIFEST.in`), ignoring generated metadata (`PKG-INFO`,
      `*.egg-info/`, `setup.cfg`'s `[egg_info]` tag block).
      The operator approved on 2026-10-12 comparing `setup.cfg`
      by parsed section/key/value equality after removing that
      block: setuptools reserialized its indentation and
      whitespace. Every other compared file must match bytes.
      The verified release source is
      `5de67aa1ad7883243af65d4f4f713d78ce02f791`, the parent of
      `45623a1`; the latter's CLI whitespace cleanup is absent
      from the sdist. Tag the verified parent, not `45623a1`.
      Never `pip download` or `pip install` the sdist:
      building its metadata would run its code. If a
      non-generated file differs, compare the neighbouring
      commits (`git log --oneline -5 45623a1`) and tag the
      one whose tree matches; if none matches, stop and report
      the differing files to the operator before tagging
      anything. Record the comparison and its result in the PR
      body.
    </requirement>

    <requirement>
      Create and push the tag: `git tag -a v1.0.0 <commit> -m
      "weatherbot 1.0.0, the last v1 release (PyPI,
      2025-09-29)"`, then `git push origin v1.0.0`. Confirm
      that `git ls-remote --tags origin 'v1.0.0*'` shows the
      tag object and its peeled `^{}` line at the commit. No
      workflow runs on the tag push; v1 CI triggers on
      branches only.
    </requirement>

    <requirement>
      `CHANGELOG.md`: add, above the v1 history, a v2
      `[Unreleased]` heading with one entry: version 1 is
      retired; it stays installable with `pip install
      weatherbot==1.0.0` and its source is the `v1.0.0` tag;
      version 2 is a from-scratch rewrite specified in
      `docs/brief/weatherbot-v2-brief.md`. Correct the
      `[1.0.0]` date to 2025-09-29 (PyPI's upload record) and
      fold v1's old `[Unreleased]` entries into `[1.0.0]`,
      since the sdist comparison proves they shipped. Leave
      every other v1 line as it is.
    </requirement>

    <requirement>
      Rename the default branch through the API, which
      retargets open PRs, moves branch settings, and redirects
      old links: `gh api -X POST
      repos/nathanramoscfa/weatherbot/branches/master/rename
      -f new_name=main`. Then, locally: `git branch -m master
      main`, `git fetch origin --prune`, `git branch -u
      origin/main main`, and `git remote set-head origin -a`.
      Confirm `gh api repos/nathanramoscfa/weatherbot --jq
      .default_branch` prints `main`. Put the same four local
      commands in the PR body for any other clone.
    </requirement>

    <requirement>
      Merge settings: `gh api -X PATCH
      repos/nathanramoscfa/weatherbot -F
      allow_squash_merge=true -F allow_merge_commit=false -F
      allow_rebase_merge=false -F delete_branch_on_merge=true
      -f squash_merge_commit_title=PR_TITLE -f
      squash_merge_commit_message=PR_BODY`, then read them
      back.
    </requirement>

    <requirement>
      Protect `main` with `gh api -X PUT
      repos/nathanramoscfa/weatherbot/branches/main/protection
      --input <payload file>` using exactly this payload, then
      read it back:

      {
        "required_status_checks": null,
        "enforce_admins": true,
        "required_pull_request_reviews": {
          "required_approving_review_count": 0,
          "dismiss_stale_reviews": false,
          "require_code_owner_reviews": false
        },
        "restrictions": null,
        "required_linear_history": true,
        "allow_force_pushes": false,
        "allow_deletions": false,
        "required_conversation_resolution": true
      }

      Zero approvals lets the sole maintainer merge their own
      PR through the protected path, and `enforce_admins`
      keeps the admin on that path too. Step 2 replaces
      `required_status_checks` once its CI reports `gate`.
      Apply protection before Stage 3, so this step's own PR
      merges through it.
    </requirement>

    <requirement>
      Replace the `master` wording that describes the live
      branch: in `AGENTS.md`, "the code on `master`" and "The
      roadmap on `master`"; in the project roadmap, §5
      "Branching model" ("renamed from `master` in Phase 1.1;
      until that step merges, read `master`…") stated as done
      with this step's date, and the "Changes from the brief"
      bullet ("Until that step merges, `master` is the
      ledger", wrapped across two lines) in the past tense.
      Leave historical mentions (§2's gap table, the brief, v1
      files) as they are; Step 2 rewrites `pyproject.toml`'s
      URLs and v1's CI.
    </requirement>

    <requirement>
      In the Stage-3 commit that marks this step, besides the
      two `**Status:**` lines the lifecycle names, set Phase
      1's row in the project roadmap's "Phase Complexity
      Summary" (§8) to `In progress`, so the summary agrees
      with the phase heading until Step 7 sets it to
      `Complete`.
    </requirement>
  </requirements>
</task>
```

### Step 1 acceptance criteria

- The PR body records the sdist comparison: PyPI's SHA-256 digest
  verified, and no non-generated file differs between
  `weatherbot-1.0.0.tar.gz` and the tagged commit, allowing only the
  operator-approved `setup.cfg` serialization difference described in
  this step's task (parsed configuration values must match).
- `git ls-remote --tags origin` lists `v1.0.0` as an annotated tag that
  peels to `45623a17ef3c6c3f96395f35ad211c7054c5cbbb`, or to the commit
  the comparison proved, named in the PR body.
- `CHANGELOG.md` carries the retirement note (`weatherbot==1.0.0`, the
  `v1.0.0` tag, the brief), dates `[1.0.0]` 2025-09-29, and has exactly
  one `[Unreleased]` heading.
- `AGENTS.md` and the project roadmap name `main` as the ledger branch:
  `git grep -n -i "read .master. wherever" -- AGENTS.md
  docs/roadmap/ROADMAP.md` finds nothing, and the "Changes from the
  brief" bullet on the rename reads in the past tense.
- The project roadmap's Phase 1 `**Status:**` line reads `In progress —
  phase01-roadmap.md`, and its §8 row reads `In progress`.
- Locally, `git branch -vv` shows `main` tracking `origin/main` and `git
  remote show origin` reports `HEAD branch: main`.
- **Deployed & verified:** `gh api repos/nathanramoscfa/weatherbot --jq
  '{default_branch, delete_branch_on_merge, allow_squash_merge,
  allow_merge_commit, allow_rebase_merge}'` returns `main`, `true`,
  `true`, `false`, `false`; `gh api
  repos/nathanramoscfa/weatherbot/branches/main/protection` shows admins
  enforced, linear history required, force pushes and deletions disabled,
  a pull request required with zero approvals, conversation resolution
  required, and no required status checks; and this step's PR merged into
  `main` as one squash commit whose subject is its PR title followed by
  GitHub's `(#<n>)`.
- **Security gate clean** (always the final criterion): `gitleaks git
  --pre-commit --staged --redact` was clean before every commit; the diff
  is documentation only, as the PR body states; the sdist and the
  protection payload never left the scratch directory; and the protection
  payload grants no bypass actor and no force-push allowance.

---

## Step 2 — uv scaffold replaces v1 ✅

**Status:** Complete — PR #4 (2026-10-12)

> **Goal:** Replace version 1's tree with the version 2 chassis every
> later phase extends: a `uv_build` `pyproject.toml` for `weatherbot`
> 2.0.0.dev0 (Python 3.13 or later, `typer` as the only runtime
> dependency, dependency groups `dev` and `planning`, `[tool.uv]
> default-groups`), a committed `uv.lock` and `.python-version`; the
> package `src/weatherbot/` with the five layers `sources`, `engine`,
> `services`, `cli`, and `web` and a `weatherbot --version` command;
> import-linter contracts for the layering plus an AST test that bans I/O
> libraries from the engine; ruff with `select = ["ALL"]`, ruff format,
> pyright in strict mode, and pytest with respx, pytest-socket, and an
> autouse fixture that runs every test in a temporary working directory;
> a v2 `.github/workflows/ci.yml` (lint, typecheck, test and package smoke
> on ubuntu-latest and windows-latest, and the aggregate `gate`) whose
> `gate` becomes `main`'s required check; every v1 file deleted; a v2
> `README.md` status page, `CONTRIBUTING.md`, and `AGENTS.md`; and
> roadmodel moved into the `planning` group in `.venv`, with the registry
> override dropped. This step lands the chassis; Step 3 adds the security
> gate, and Steps 4–6 fill it with data.

**Branch:** `feature/phase01-step2-uv-scaffold`

**Deploys:** GitHub Actions → the v2 `ci.yml` replaces v1's on merge,
and this step sets `gate` as `main`'s required check through the API
once `gate` is green on its PR; GitHub repository → the unused
`SAFETY_API_KEY` Actions secret is deleted after the merge; the
operator's machine → the project gains `.venv` and the roadmodel
registry line loses its `venv:` override (outside git).

| Setting      | Value                                     |
| ------------ | ----------------------------------------- |
| Model        | Sonnet 5.5                                |
| Backup       | GPT-6 Sol — Codex · Intelligence High     |
| Platform     | Claude Code                               |
| Effort       | High                                      |
| Thinking     | On                                        |
| Conversation | **New**                                   |

**Model rationale:** A repository-wide replacement — new packaging,
strict tool configuration that must pass on two operating systems, an
import-architecture contract, a new CI workflow, and the deletion of v1 —
is coding work (agentic secondary) of High complexity: the pattern is
known, since judge-metrics runs the same stack, but the scope is
cross-cutting and every later phase inherits its choices. The selector
holds High work on Claude Code even while the claude.ai Max weekly pool
reads `tight`, and among the S-tier coding models, all tied on agentic,
Sonnet 5.5 wins on coverage (S or A in all seven categories); claude.ai
Max pays for it at $0 marginal. Effort High is a raise over Sonnet 5.5's
documented `medium` default, earned by cross-file strict-mode
configuration; not Extra High, because nothing here is novel. Thinking is
On, as it always is for this operator. The Backup is GPT-6 Sol on Codex
(ChatGPT Pro 5x) at Intelligence High, S-tier in coding and agentic work.
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
       feature/phase01-step2-uv-scaffold`
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
       Phase 1 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 1`
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

    THIS STEP: the hook arrives in
    Step 3, so run the gate by hand
    before each commit: `gitleaks
    git --pre-commit --staged
    --redact`; `uvx bandit -r src`;
    `uvx pip-audit --strict -r`
    over `uv export --frozen
    --no-emit-project --format
    requirements-txt`; and the
    review: no coordinate, key,
    or path under a user profile
    in any new file. The registry
    edit to
    `~/.config/roadmodel/projects.txt`
    stays outside git. The new CI
    workflow is a security-relevant
    diff: SHA-pinned actions,
    `contents: read`, no secrets,
    no `pull_request_target`.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 1 (Foundation and
    discovery). Step 2: uv scaffold replaces v1.

    Current state (as of Phase 1, post-Step 1):

    - `v1.0.0` tags the last v1 commit; `main` is the
      protected, squash-only default branch with no required
      status checks yet. v1's tree and CI are unchanged; a PR
      runs the workflow definitions on its own branch, so the
      new `ci.yml` checks this step's PR.
    - Tools: uv 0.12.15; Python 3.13 is not installed (`uv
      python install 3.13`). The roadmodel registry,
      `~/.config/roadmodel/projects.txt`, holds this
      project's line with a `venv:` override to an external
      environment; the updater
      (`~/.config/roadmodel/update_projects.py`) detects
      `.venv` and accepts `--dry-run`.
    - judge-metrics (https://github.com/nathanramoscfa/judge-metrics)
      is the precedent: its `pyproject.toml` (`uv_build`,
      `[dependency-groups] planning`, `[tool.uv]
      default-groups`) and `.github/workflows/ci.yml`
      (SHA-pinned `actions/checkout` and
      `astral-sh/setup-uv`).
    - `cache/`, `reports/`, `logs/`, and `state/` are v1
      runtime directories with local, untracked content,
      including the six 2025 reports Step 5 harvests. They
      must stay ignored, and nothing deletes them: `git clean`
      is forbidden in this phase.
    - v1 files to delete: `src/weatherbot/` (25 modules plus
      `data/`, `icons/`, `notifiers/`); `tests/` (18 files);
      `docs/README.md`, `docs/ai-integration.md`,
      `docs/alerts.md`, `docs/api-reference.md`,
      `docs/commands.md`, `docs/configuration.md`,
      `docs/development.md`, `docs/index.md`,
      `docs/installation.md`, `docs/security.md`,
      `docs/troubleshooting.md`, `docs/user-guide.md`;
      `scripts/*.ps1` (4); `setup.cfg`, `MANIFEST.in`,
      `Makefile`, `pyrightconfig.json`,
      `pre-commit-config.yaml`, `.safety-project.ini`,
      `env.example`, `logs/.gitkeep`, `state/.gitkeep`, and
      `.vscode/settings.json`.

    Files to read (every file before drafting):
    - docs/roadmap/phase01-roadmap.md (Overview, Current
      State, this step, and Step 3's goal, to avoid overlap).
    - docs/roadmap/ROADMAP.md (§3, the Phase 1 section, and
      §5's "Per-step security gate" and "Worktree strategy").
    - docs/brief/weatherbot-v2-brief.md (§6 architecture,
      §12 quality).
    - AGENTS.md, CLAUDE.md, README.md, CONTRIBUTING.md,
      CHANGELOG.md, DISCLAIMER.md.
    - pyproject.toml, .gitignore, .github/workflows/ci.yml
      (v1, all three replaced).
  </context>

  <goal>
    Ship a v2 project in which `uv sync --locked` followed by
    `uv run weatherbot --version` prints `2.0.0.dev0` on
    Windows and Ubuntu; strict ruff, pyright, import-linter,
    and pytest pass in a new CI on both runners, rolled into
    a required `gate` check; no v1 file remains in the tree;
    and roadmodel runs from the project's own `.venv`.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Packaging. `uv python install 3.13`; `.python-version`
      reads `3.13`. `pyproject.toml`: `[project]` name
      `weatherbot`, version `2.0.0.dev0`, a v2 description
      (a personal hurricane-threat monitor; informational
      only), `readme = "README.md"`, `license = "MIT"`,
      `requires-python = ">=3.13"`, pre-alpha classifiers,
      `dependencies = ["typer>=…"]` and nothing else,
      `[project.scripts] weatherbot = "weatherbot.cli:app"`,
      and project URLs on `main`. Build system `uv_build`
      bounded to the installed uv minor (`uv_build>=0.12.15,
      <0.13`); the sdist includes `DISCLAIMER.md`.
      `[dependency-groups]`: `dev` = pytest, pytest-socket,
      respx, httpx, ruff, pyright, and import-linter;
      `planning` = roadmodel (at least the kit's 0.2.80) and
      pip, with a comment saying why roadmodel is not an
      application dependency and why pip is there (the
      updater calls `.venv`'s `python -m pip`).
      `[tool.uv] default-groups = ["dev", "planning"]`.
      Commit `uv.lock`.
    </requirement>

    <requirement>
      Package skeleton, and nothing more:
      `src/weatherbot/__init__.py` (`__version__` from
      `importlib.metadata.version("weatherbot")`),
      `__main__.py` (`python -m weatherbot`), `py.typed`, and
      `cli/__init__.py`, `engine/__init__.py`,
      `sources/__init__.py`, `services/__init__.py`,
      `web/__init__.py`, each with a module docstring stating
      its layer's rule from the brief's §6. The CLI is a Typer
      `app` whose eager `--version` option prints the version
      string alone (`2.0.0.dev0`) and exits 0; `--help`
      works; no other command exists yet.
    </requirement>

    <requirement>
      Architecture contracts. `[tool.importlinter]` with
      `root_package = "weatherbot"` and two contracts: a
      forbidden contract keeping `weatherbot.engine` from
      importing `weatherbot.sources`, `weatherbot.services`,
      `weatherbot.cli`, and `weatherbot.web`; and a layers
      contract `weatherbot.cli | weatherbot.web` above
      `weatherbot.services` above `weatherbot.sources |
      weatherbot.engine` (independent siblings within a
      layer). `tests/test_architecture.py` runs both contracts
      and adds an AST scan of `src/weatherbot/engine/**/*.py`
      that fails on any import rooted at `httpx`, `requests`,
      `urllib`, `urllib3`, `socket`, `sqlite3`, `sqlalchemy`,
      `alembic`, `fastapi`, `starlette`, `uvicorn`,
      `anthropic`, or `apscheduler`, with a negative test that
      proves the scan catches a synthetic `import httpx`.
      Sources and the engine are independent because sources
      never interpret and the engine never fetches; the typed
      domain models both will share (project roadmap 2.1) get
      their own package, `weatherbot.models`, which Phase 2
      creates and adds to the contract as the lowest layer.
      Write that intent into `AGENTS.md`'s layer rules.
    </requirement>

    <requirement>
      Lint, format, types. `[tool.ruff]` targets py313 with
      line length 100 and `src = ["src", "tests",
      "scripts"]`; `[tool.ruff.lint] select = ["ALL"]` with
      `convention = "google"` for pydocstyle; ignore only the
      rules ruff's documentation lists as conflicting with
      `ruff format`, plus, under `tests/**` per-file ignores,
      `S101` and only the other rules tests genuinely need;
      every ignore carries a trailing comment with its reason,
      and every `noqa` names its rule and reason. `[tool.pyright]`:
      `typeCheckingMode = "strict"`, `pythonVersion =
      "3.13"`, `include = ["src", "tests", "scripts"]`,
      `venvPath = "."`, `venv = ".venv"`.
    </requirement>

    <requirement>
      Tests and guards. `[tool.pytest.ini_options]`:
      `testpaths = ["tests"]`, `addopts = "-ra
      --strict-markers --strict-config
      --allow-hosts=127.0.0.1,::1 -m 'not live and not
      corpus'"`, `filterwarnings = ["error"]`, and markers
      `live` (calls real services; run deliberately) and
      `corpus` (needs the replay-corpus cache). Use
      pytest-socket's `--allow-hosts`, not
      `--disable-socket`: asyncio on Windows opens a loopback
      socket pair that `--disable-socket` would block. Selecting
      `-m live` does not lift the guard, so every `live` test
      also carries pytest-socket's `enable_socket` marker.
      `tests/conftest.py` holds an autouse fixture that
      `monkeypatch.chdir(tmp_path)` so no test can read or
      write the repository through a relative path — the
      guard against the v1 cache loss. Add `tests/test_cli.py`
      (`--version` through Typer's `CliRunner`, and `python -m
      weatherbot --version` through a subprocess) and
      `tests/test_guards.py` (a connection to a non-loopback
      address fails with pytest-socket's error; the working
      directory during a test is not the repository root).
    </requirement>

    <requirement>
      CI. Replace `.github/workflows/ci.yml`: triggers `push`
      to `main` and `pull_request`; top-level `permissions:
      contents: read`; a concurrency group per ref that
      cancels superseded PR runs; `timeout-minutes` on every
      job. Jobs: `lint` (ubuntu-latest: `ruff check`, `ruff
      format --check`, `lint-imports`); `typecheck`
      (ubuntu-latest: `pyright`); `test` (matrix
      ubuntu-latest and windows-latest: `pytest`); `package`
      (the same matrix: `uv build`, install the wheel into a
      fresh `uv venv`, run that environment's `weatherbot
      --version`, and compare it with the project version);
      and `gate` (`needs` all four, `if: always()`, failing
      unless every needed job succeeded). Every `uses:`
      pinned to a full commit SHA with a `# vX.Y.Z` comment;
      `actions/checkout` with `persist-credentials: false`;
      `astral-sh/setup-uv` with its cache; `uv sync --locked`
      before the tools run; Python from `.python-version`.
    </requirement>

    <requirement>
      Required check. Once `gate` is green on this PR (Stage
      4, before merging), re-PUT Step 1's protection payload
      with `"required_status_checks": {"strict": true,
      "checks": [{"context": "gate"}]}` and read it back.
      After the merge, delete the now-unused Actions secret:
      `gh secret delete SAFETY_API_KEY --repo
      nathanramoscfa/weatherbot`.
    </requirement>

    <requirement>
      Delete v1 with `git rm`: every file in the context's
      list. Keep `LICENSE`, `DISCLAIMER.md`, `CHANGELOG.md`,
      `AGENTS.md`, `CLAUDE.md`, `docs/brief/`,
      `docs/roadmap/`, and `planning/`. Never delete untracked
      files.
    </requirement>

    <requirement>
      `.gitignore`, rewritten for v2: Python and uv artifacts
      (`.venv/`, `__pycache__/`, `*.py[cod]`,
      `.pytest_cache/`, `.ruff_cache/`, `.coverage*`,
      `htmlcov/`, `dist/`, `build/`, `*.egg-info/`);
      `.worktrees/`; `.env` and `.env.*`;
      `planning/user-context.md`; and the v1 runtime
      directories `cache/`, `reports/`, `logs/`, and `state/`
      as whole directories, under a comment that they hold
      local v1 data that must never be committed. Confirm with
      `git status --ignored` that the six 2025 reports are
      still present and ignored.
    </requirement>

    <requirement>
      Documentation. `README.md` becomes a v2 status page: one
      paragraph on what v2 is (the brief's §2), its status
      (rewrite in progress, Phase 1, nothing released; v1
      retired, `pip install weatherbot==1.0.0`, source at the
      `v1.0.0` tag), the disclaimer's essentials with a link
      to `DISCLAIMER.md`, a development quickstart (`uv
      sync`, `uv run weatherbot --version`, `uv run pytest`),
      and links to the brief and the roadmap — no v1 feature
      claims. `CONTRIBUTING.md` describes the v2 loop: uv, the
      tools, one step per branch and PR, Conventional Commits
      (Step 3 adds the gate). `AGENTS.md` replaces "Until the
      Phase 1 scaffold lands…" with the layers, their import
      rules, and the commands, and its planning-kit paragraph
      now says, as judge-metrics' does: roadmodel lives in the
      `planning` group in `.venv`; the daily updater upgrades
      it there with pip and re-exports `planning/`, but `uv
      sync` and every `uv run` put `.venv` back on the version
      `uv.lock` pins; so a step that finds a kit refresh
      uncommitted commits it first, on its own, together with
      the matching lock bump (`uv lock --upgrade-package
      roadmodel==<release>`), as `chore(planning): refresh the
      roadmodel kit to <release>`, taking the release from the
      latest `[weatherbot] <old> -> <new>` line of
      `~/.config/roadmodel/update.log` rather than from a
      `roadmodel` on `PATH`. `CHANGELOG.md`
      `[Unreleased]` gains Added (the scaffold) and Removed
      (v1 code, tests, docs, and packaging) entries.
    </requirement>

    <requirement>
      Move the planning kit's environment. After `uv sync`,
      confirm `.venv\Scripts\python -m pip --version` and `uv
      run roadmodel version` (at least 0.2.80; the CLI has no
      `--version` flag); run `uv run roadmodel export-kit .
      --force` and confirm `planning/` is unchanged, or commit
      the change first as its own `chore(planning)` commit.
      Then replace this project's line in
      `~/.config/roadmodel/projects.txt` with the bare path —
      outside git — and run `python
      ~/.config/roadmodel/update_projects.py --dry-run` to
      confirm it resolves this project to `.venv` with no
      override. The dry run lists every registered project,
      private ones included, with absolute paths: record in
      the PR body only this project's line, with its path
      replaced by `<repo>`, and never quote the others. The
      old external environment is no longer used; removing it
      is the operator's housekeeping.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with a `# <repo-relative path>` comment (the v1
      and judge-metrics convention); Markdown files follow
      their siblings in `docs/`, which carry none.
    </requirement>
  </requirements>
</task>
```

### Step 2 acceptance criteria

- On a fresh clone of the branch, `uv sync --locked` followed by `uv run
  weatherbot --version` prints `2.0.0.dev0` on the operator's Windows
  machine, and `ci.yml`'s `package` job proves the installed wheel does
  the same on ubuntu-latest and windows-latest.
- `git ls-files src/weatherbot` lists exactly the skeleton: `__init__.py`,
  `__main__.py`, `py.typed`, and the `__init__.py` of `cli`, `engine`,
  `services`, `sources`, and `web`.
- `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`,
  `uv run lint-imports`, and `uv run pytest` pass locally, and `ci.yml`'s
  `lint`, `typecheck`, `test`, and `package` jobs and `gate` are green on
  the PR.
- Ruff selects `ALL` with every ignore carrying a reason comment, and
  pyright runs in strict mode; before the PR opened, a throwaway `import
  httpx` in the engine failed `tests/test_architecture.py` and a throwaway
  engine import of `weatherbot.sources` failed `lint-imports` (both
  reverted, both recorded in the PR body).
- A connection to a non-loopback address fails under pytest-socket, and
  every test runs in a temporary working directory.
- No v1 file remains (every file in the context's list is gone), and `git
  status --ignored` still shows the six 2025 reports under `reports/`.
- `README.md`, `CONTRIBUTING.md`, `AGENTS.md`, and `CHANGELOG.md`
  describe v2 as specified; `README.md` links `DISCLAIMER.md` and makes no
  v1 feature claim; the built sdist contains `DISCLAIMER.md`.
- `.venv\Scripts\python -m pip --version` works, the registry line has no
  `venv:` override, the updater's dry run lists this project on `.venv`
  (the PR body quotes only that line, its path redacted), and `planning/`
  is unchanged by `export-kit` (or its change landed as its own
  `chore(planning)` commit).
- **Deployed & verified:** the first `ci.yml` run on `main` after the
  merge is green on both runners (`gh run list --workflow ci.yml --branch
  main --limit 1`); `gh api
  repos/nathanramoscfa/weatherbot/branches/main/protection --jq
  .required_status_checks` names `gate` with `strict: true`; and `gh
  secret list --repo nathanramoscfa/weatherbot` no longer lists
  `SAFETY_API_KEY`.
- **Security gate clean** (always the final criterion): gitleaks was
  clean on every commit's staged diff, `uvx bandit -r src` is clean,
  pip-audit over the exported `uv.lock` is clean, no new file holds a
  coordinate, a key, or a path under a user profile, the v1 deletion took
  `env.example` and the v1 Nassau default polygon out of the tree, and
  `.env` and the v1 runtime directories remain ignored.

---

## Step 3 — Security gate ✅

**Status:** Complete — PR #7 (2026-10-12)

> **Goal:** Wire the per-step security gate (project roadmap §5) so it
> runs before every commit and again in CI: `.pre-commit-config.yaml` with
> gitleaks, bandit, pip-audit through `scripts/audit_deps.py`, the
> personal-data check, ruff, ruff format, pyright, import contracts, size
> and hygiene hooks, and `no-commit-to-branch` for `main`, every hook
> pinned by SHA; `scripts/check_personal_data.py`, a stdlib-only checker
> with a denylist of the operator's values kept outside the repository, a
> CI pattern set, a public-landmark allowlist
> (`scripts/public_landmarks.toml`), output that never echoes a match, and
> a self-test; a `security` job in `ci.yml` that runs the same four checks
> and joins `gate`; Dependabot for uv and GitHub Actions, Dependabot alerts
> and security updates, private vulnerability reporting, and
> `SECURITY.md`; and proofs that a planted fake secret and a planted
> coordinate are each blocked by the hook and by CI. Every later commit in
> the project passes through this gate.

**Branch:** `feature/phase01-step3-security-gate`

**Deploys:** GitHub Actions → `ci.yml` gains the `security` job inside
`gate` on merge; GitHub repository → Dependabot alerts, Dependabot
security updates, and private vulnerability reporting, enabled by this
step through the API; the operator's machine → the pre-commit hook
installed in the clone and the personal-data denylist created in the
user configuration directory (outside git).

| Setting      | Value                                         |
| ------------ | --------------------------------------------- |
| Model        | Opus 5.5                                      |
| Backup       | GPT-6 Sol — Codex · Intelligence Extra High   |
| Platform     | Claude Code                                   |
| Effort       | Extra High                                    |
| Thinking     | On                                            |
| Conversation | **New**                                       |

**Model rationale:** The gate is the project's core control against its
first abuse case, personal data reaching a public repository, and it
spans many files that must agree: hook configuration, a new checker with
fail-closed semantics and redacted output, the CI mirror, repository
settings, and proofs by planted values. That is coding work with a
security-knowledge secondary at High complexity, verified across many
files. Among the S-tier coding models, Opus 5.5 and Fable 5.1 tie at S in
knowledge and on coverage, and cost breaks the tie to Opus 5.5; the
selector holds High work on Claude Code while the claude.ai Max weekly
pool reads `tight`, and the Max subscription pays at $0 marginal. Effort
Extra High, two rungs above Opus 5.5's documented `medium` default, is
earned by the multi-step verification across files; not Max, because the
gate's design is specified here and only its proof is demanding. Thinking
is On. The Backup is GPT-6 Sol on Codex (ChatGPT Pro 5x) at Intelligence
Extra High: no GPT model is S-tier in knowledge, and GPT-6 Sol leads the
S-tier coding GPT models on coverage. The conversation is new per
phase-boundary hygiene.

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
       feature/phase01-step3-security-gate`
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
       Phase 1 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 1`
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

    THIS STEP builds the gate, so
    run it by hand until the hook
    exists, then run `uv run
    pre-commit run --all-files`
    before the final commit. The
    operator's coordinates are
    read only by
    `--init-from-env`, which
    writes them outside the
    repository and prints a count:
    never print, log, quote, or
    commit a denylist value, and
    never ask the operator to
    paste one into the
    conversation. The proofs use
    synthetic values only, and
    none of them reaches `main`.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 1 (Foundation and
    discovery). Step 3: Security gate.

    Current state (as of Phase 1, post-Step 2):

    - `main` is protected and requires the `gate` check of
      `.github/workflows/ci.yml` (jobs `lint`, `typecheck`,
      `test`, `package`, `gate`). The v2 scaffold is in place:
      `pyproject.toml` (uv_build, groups `dev` and
      `planning`, strict ruff and pyright, import-linter),
      `uv.lock`, `tests/` with the socket and
      working-directory guards. No pre-commit configuration
      and no security job exist.
    - gitleaks 8.30.1 is installed locally; bandit,
      pip-audit, and pre-commit are not yet in the `dev`
      group.
    - The operator's coordinates are in v1's `.env` as
      `HOME_LAT` and `HOME_LON` (ignored). GitHub push
      protection blocks known provider token formats at push
      time; non-provider patterns are off. Dependabot
      security updates are off.
    - judge-metrics' `.pre-commit-config.yaml` and
      `scripts/audit_deps.py`
      (https://github.com/nathanramoscfa/judge-metrics) are
      the precedent for local `uv run` hooks and the
      pip-audit wrapper.

    Files to read (every file before drafting):
    - docs/roadmap/phase01-roadmap.md (Overview security
      rule, Current State "Security & sensitive-data
      surface", this step, and Step 5's manifest schema,
      which rule R3 below reads).
    - docs/roadmap/ROADMAP.md §5 ("Security & privacy
      strategy": data classification, threat model, per-step
      gate, controls by layer; "Defect handling & triage").
    - pyproject.toml, .github/workflows/ci.yml,
      CONTRIBUTING.md, .gitignore, tests/conftest.py.
  </context>

  <goal>
    Make the four-check gate (secret scan, SAST, dependency
    audit, personal-data check) run fail-closed in pre-commit
    and in CI, prove it blocks a planted secret and a planted
    coordinate in both places, harden the pipeline and the
    repository's security settings, and document the gate for
    every later step.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Add `bandit`, `pip-audit`, and `pre-commit` to the
      `dev` group. Configure bandit in `pyproject.toml`
      (`[tool.bandit]`) to scan `src` and `scripts`; tests are
      out of scope by path, never by skipping rules globally.
      `scripts/audit_deps.py` exports the locked set (`uv
      export --frozen --no-emit-project --format
      requirements-txt`) to a temporary file and runs
      `pip-audit --strict` over it, exiting non-zero on any
      finding.
    </requirement>

    <requirement>
      `scripts/public_landmarks.toml`: the public landmarks
      every request, test, document, and example may use — at
      least `miami-dade` (Miami-Dade County Hall, the Stephen
      P. Clark Government Center, 111 NW 1st Street, Miami)
      and `nassau` (Parliament Square, Nassau, New
      Providence) — each with `name`, `lat` and `lon` to four
      decimals, and `source`, the OpenStreetMap object URL the
      coordinates were read from.
    </requirement>

    <requirement>
      `scripts/check_personal_data.py`, standard library only,
      run by pre-commit on staged files, by CI, and by hand:
      - R1 denylist (local only): any denylist entry,
        case-insensitive, anywhere in a scanned file, fixtures
        and binaries included (scan bytes).
      - R2 coordinates: a decimal latitude/longitude pair
        (either order, comma or space separated, in range, at
        least three decimals each) or a `lat`/`lon`/
        `latitude`/`longitude` assignment with at least three
        decimals, in a tracked text file outside
        `tests/fixtures/recorded/` and `tests/fixtures/replay/`
        (NOAA payload trees, full of storm geometry). A match
        passes only when it equals an allowlisted landmark to
        three decimals.
      - R3 request coordinates: every coordinate inside a
        fixture manifest's `url` (NWS `/points/{lat},{lon}`,
        a `point=` parameter, Nominatim `lat`/`lon`) must be
        an allowlisted landmark.
      - R4 env files: no tracked `.env` or `*.env` file.
      - Output names `path:line` and the rule id, never the
        matched text, so no terminal, CI log, or transcript
        carries a personal value.
      - Denylist path: `WEATHERBOT_DENYLIST` if set, else
        `%APPDATA%\weatherbot\personal-denylist.txt` on
        Windows and `${XDG_CONFIG_HOME:-~/.config}/weatherbot/
        personal-denylist.txt` elsewhere — outside the
        repository, so every worktree shares it and no commit
        can carry it. Without `--ci`, a missing or empty
        denylist fails closed with setup instructions.
      - `--init-from-env PATH` reads `HOME_LAT` and
        `HOME_LON` from a dotenv file and writes denylist
        entries for the pair at two to six decimals, in both
        orders, plus the raw strings; it prints only the
        number of entries written. `--add` appends one value
        read from standard input without echoing it.
      - `--all` scans `git ls-files`; filenames given on the
        command line are scanned instead (pre-commit). `--ci`
        skips R1 and is set only in CI. `--self-test` plants,
        in a temporary directory, a synthetic coordinate pair
        generated away from every landmark, an allowlisted
        landmark, and, locally, the first denylist entry; it
        checks that R1 and R2 fire and the landmark passes,
        and prints only PASS or FAIL per rule.
    </requirement>

    <requirement>
      `tests/scripts/test_check_personal_data.py`: each rule
      fires on a planted sample and passes a clean one; the
      landmark passes R2 and R3; a coordinate under
      `tests/fixtures/recorded/` is ignored by R2, while a
      manifest URL with a non-landmark coordinate fails R3;
      the output never contains the planted value; a missing
      denylist fails closed without `--ci`; `--init-from-env`
      writes entries and prints no value. Use a synthetic
      dotenv in `tmp_path` and point `WEATHERBOT_DENYLIST` at
      `tmp_path`.
    </requirement>

    <requirement>
      `.pre-commit-config.yaml` at the repository root:
      `pre-commit-hooks` (trailing-whitespace,
      end-of-file-fixer, check-yaml, check-toml,
      check-merge-conflict, detect-private-key,
      check-added-large-files with `--maxkb=5120`, and
      no-commit-to-branch with `--branch main`); gitleaks
      through its official hook; and local `uv run` hooks for
      ruff check, ruff format --check, pyright, lint-imports,
      bandit, pip-audit through `scripts/audit_deps.py` (when
      `uv.lock` or `pyproject.toml` changes), and the
      personal-data check on staged files. Pin every hook
      repository to a full commit SHA with its version as a
      comment (`pre-commit autoupdate --freeze`). Run `uv run
      pre-commit install`.
    </requirement>

    <requirement>
      Keep recorded payloads byte-exact, since Step 5's
      contract tests compare each file's SHA-256 with the
      bytes NOAA sent. Exclude `^tests/fixtures/` from
      trailing-whitespace and end-of-file-fixer (ArcGIS JSON
      ends without a newline), and add a `.gitattributes`
      with `tests/fixtures/** -text`, so neither Git's line
      ending conversion nor a Windows checkout (CRLF on
      windows-latest) rewrites them. Do not add a global
      `* text=auto eol=lf`: it would rewrite payloads too.
      The read-only hooks — gitleaks, detect-private-key,
      check-added-large-files, and the personal-data check —
      still cover the fixture trees.
    </requirement>

    <requirement>
      Create the operator's denylist with `uv run python
      scripts/check_personal_data.py --init-from-env .env`
      (it prints a count only), then run `--self-test`
      locally. If `.env` lacks the keys, stop and ask the
      operator to run `--add` themselves.
    </requirement>

    <requirement>
      CI. Add a `security` job to `ci.yml` (ubuntu-latest):
      checkout with `fetch-depth: 0` and `persist-credentials:
      false`; gitleaks over the pushed or pull-request commit
      range with `--redact` (a pinned release binary verified
      by checksum, or `gitleaks/gitleaks-action` pinned by
      SHA, which needs no license on a personal account); `uv
      run bandit -c pyproject.toml -r src scripts`; `uv run
      python scripts/audit_deps.py`; and `uv run python
      scripts/check_personal_data.py --all --ci` and
      `--self-test --ci`. Every check after the first carries
      `if: '!cancelled()'`, so one run reports every finding
      instead of stopping at the first (proof b below depends
      on it). Add `security` to `gate`'s `needs`.
      Least-privilege `permissions:`, no secrets, no
      `pull_request_target`.
    </requirement>

    <requirement>
      Audit the pipeline: every `uses:` in every workflow
      pinned to a full commit SHA with a version comment;
      top-level `permissions: contents: read` or narrower;
      `timeout-minutes` on every job; `persist-credentials:
      false` on every checkout that does not push.
    </requirement>

    <requirement>
      `.github/dependabot.yml`: `uv` and `github-actions`,
      both at directory `/`, weekly, with grouped minor and
      patch updates and a `chore(deps)` commit prefix. Add
      `pre-commit` if Dependabot supports that ecosystem when
      the step runs; otherwise `CONTRIBUTING.md` documents
      `uv run pre-commit autoupdate --freeze`. No `npm` entry
      until `frontend/` exists (Phase 5).
    </requirement>

    <requirement>
      Repository settings through the API, each read back:
      Dependabot vulnerability alerts (`PUT
      repos/nathanramoscfa/weatherbot/vulnerability-alerts`),
      Dependabot security updates (`PUT
      repos/nathanramoscfa/weatherbot/automated-security-fixes`),
      and private vulnerability reporting (`PUT
      repos/nathanramoscfa/weatherbot/private-vulnerability-reporting`).
    </requirement>

    <requirement>
      `SECURITY.md`: report a vulnerability through GitHub's
      private vulnerability reporting; supported versions
      (2.x pre-releases on `main`; 1.0.0 retired and
      unsupported); what counts as a vulnerability here (a
      path that leaks personal data or a secret, model output
      reaching a level or a fact, a non-loopback bind without
      the LAN token); and the operator as owner.
      `CONTRIBUTING.md` gains a "Security gate" section: the
      four checks and where each runs, `uv run pre-commit
      install`, the denylist setup commands, and the rule that
      any `--no-verify` is recorded with a justification in
      the PR body.
    </requirement>

    <requirement>
      Proofs, each recorded in the PR body:
      (a) Hook — on a scratch branch, staging a file that
      assigns a synthetic high-entropy token to `api_key` is
      rejected by gitleaks, and staging a synthetic coordinate
      pair is rejected by the personal-data check; then
      delete the scratch branch.
      (b) CI — push one commit with both synthetic values,
      using `--no-verify`, to a throwaway branch
      `chore/phase01-gate-proof`, open a draft PR, confirm the
      `security` job fails on both findings with the token
      redacted in its log, then close the PR and delete the
      branch. Choose a token that matches gitleaks' generic
      API-key rule and no provider format, so GitHub push
      protection does not intercept it first. Never use a real
      credential or a denylist value.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with a `# <repo-relative path>` comment.
    </requirement>
  </requirements>
</task>
```

### Step 3 acceptance criteria

- `.pre-commit-config.yaml` runs gitleaks, bandit, pip-audit, the
  personal-data check, ruff, ruff format, pyright, lint-imports, and the
  hygiene hooks, with every hook repository pinned by SHA, and `uv run
  pre-commit run --all-files` passes on the PR's tree.
- The synthetic secret and coordinate were each rejected by the hook
  (proof a) and failed the `security` job on the throwaway draft PR (proof
  b); the PR body links that run, and the throwaway branch is deleted.
- `tests/scripts/test_check_personal_data.py` passes on both runners,
  including the redaction and fail-closed tests; `--self-test` passes
  locally with the denylist and in CI with `--ci`.
- `ci.yml`'s `security` job is green on the PR and is part of `gate`;
  every action in every workflow is pinned to a full SHA, and every
  workflow declares `permissions:`.
- `.github/dependabot.yml` covers `uv` and `github-actions`;
  `SECURITY.md` exists; `CONTRIBUTING.md` documents the gate and the
  denylist setup.
- The operator's denylist exists outside the repository, and
  `scripts/check_personal_data.py --all` passes locally with it, printing
  no value.
- **Deployed & verified:** the first `ci.yml` run on `main` after the
  merge is green, `security` included; `gh api
  repos/nathanramoscfa/weatherbot/vulnerability-alerts` answers 204,
  automated security fixes and private vulnerability reporting read back
  enabled, and a "Dependabot Updates" run for the new configuration
  appears in `gh run list` after the merge.
- **Security gate clean** (always the final criterion): this step's own
  diff passed the new hook end to end; no synthetic proof value and no
  denylist entry was committed to `main`; and the checker's output, the PR
  body, and the CI logs contain no personal value.

---

## Step 4 — Data-source register ✅

**Status:** Complete — PR #13 (2026-10-12)

> **Goal:** Write `docs/DATA_SOURCES.md`, the verified register of every
> source the brief's §5 names, from live discovery on the day the step
> runs: a register table with one row per source id (the ids become
> fixture directory names in Step 5 and client names in Phase 2) giving
> endpoint, format, fixture class, cadence, terms, and verification date;
> per-service sections that name every ArcGIS layer by name (storm-slot
> layers as `{slot} …` patterns) with geometry type, the fields present,
> the fields v2 plans to use, and the query parameters the recorder and
> Phase 2's clients will share; the per-basin answer to the brief's open
> question — what the arrival-time, probabilistic-wind, and surge layers
> return for each storm active that day; the NWS, text-product, graphic,
> RSS, archive, overlay, and geocoding endpoints with their etiquette and
> terms; the project User-Agent; and the sources v2 does not use (ATCF,
> storm-page scraping), with reasons. The register answers the open
> question for every basin with an active storm and leaves the others open
> with a date.

**Branch:** `feature/phase01-step4-data-source-register`

**Deploys:** nothing beyond merge.

| Setting      | Value                                         |
| ------------ | --------------------------------------------- |
| Model        | Opus 5.5                                      |
| Backup       | GPT-6 Sol — Codex · Intelligence Extra High   |
| Platform     | Claude Code                                   |
| Effort       | Extra High                                    |
| Thinking     | On                                            |
| Conversation | **New**                                       |

**Model rationale:** The register is grounded research: it must state
what NOAA's services return today without one remembered or invented
field, because every client, contract test, and engine rule after it
relies on it. That makes knowledge the primary category (agentic
secondary, for dozens of live probes) at High complexity, where the
selector requires S-tier knowledge: Opus 5.5 and Fable 5.1 tie on
agentic and on coverage, and cost breaks the tie to Opus 5.5, the
cheapest S-tier knowledge model in the catalog. The selector holds High
work on Claude Code while the claude.ai Max weekly pool reads `tight`, and
the Max subscription pays at $0 marginal. The ladder raises knowledge work
with cross-cutting scope one rung, from High to Extra High, two rungs
above Opus 5.5's `medium` default; Max would buy nothing more, since the
hard part is checking each claim against a live response, not reasoning
depth. Thinking is On. The Backup is GPT-6 Sol on Codex (ChatGPT Pro 5x)
at Intelligence Extra High; no non-Anthropic model is S-tier in
knowledge, so the backup drops that floor to the strongest A-tier option.
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
       feature/phase01-step4-data-source-register`
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
       Phase 1 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 1`
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

    THIS STEP: probes send only the
    coordinates in
    `scripts/public_landmarks.toml`,
    to public, keyless endpoints,
    with the project User-Agent.
    Probe scripts and raw
    responses stay in the session
    scratch directory; only the
    register is committed. The
    personal-data check (R2)
    passes on the document, and no
    endpoint that needs a
    credential enters the
    register as a v2 source.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 1 (Foundation and
    discovery). Step 4: Data-source register.

    Current state (as of Phase 1, post-Step 3):

    - The gate runs in pre-commit and in CI;
      `scripts/public_landmarks.toml` lists the Miami-Dade and
      Nassau landmarks, and the personal-data check rejects
      any other coordinate in a document.
    - The brief's §5 table, verified live on 2026-10-11,
      lists the sources and their v2 use; that day's roster
      had three active systems, one a major hurricane. The
      planning session's catalog of
      `tropical/NHC_tropical_weather` showed per-slot groups
      (`AT1` … each with Forecast Points, Track, Cone,
      Watch-Warning, Past Points and Track, Past Cumulative
      Wind Swath, Past and Forecast Wind Radii, Advisory Wind
      Field, Earliest Reasonable and Most Likely Arrival
      Time, Inundation and Tidal Mask) and the outlook group
      (Two-Day Current Location, Seven-Day Current Location,
      Development Motion, Seven-Day Potential Development
      Region). Layer ids are assigned per slot and shift; only
      names are stable.
    - On 2026-10-11 the NWS point query for Miami returned no
      alerts while the Miami-Dade county zone carried one
      (brief §5), so both query paths are required.
    - v1's request patterns are readable at the tag (`git
      show v1.0.0:src/weatherbot/nhc.py`, `nws.py`,
      `nhc_current_storms.py`); v1 queried the map service
      with `f=geojson` and `outSR=4326`.

    Files to read (every file before drafting):
    - docs/roadmap/phase01-roadmap.md (this step, and Step
      5's register parsing and manifest rules, which consume
      this document).
    - docs/brief/weatherbot-v2-brief.md (§5, §7, §14).
    - docs/roadmap/ROADMAP.md (Phase 2, for what the clients
      need; §5 "Risks & mitigations").
    - scripts/public_landmarks.toml.
  </context>

  <goal>
    Commit `docs/DATA_SOURCES.md`: a register, verified live
    and dated, of every source in the brief's §5 — ids,
    endpoints, formats, fixture classes, cadences, terms,
    layers by name with their fields and shared query
    parameters, the per-basin answer on arrival-time,
    probabilistic-wind, and surge layers, the User-Agent and
    etiquette, and the sources v2 does not use.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Probe live and read-only, with the User-Agent
      `weatherbot/2.0.0.dev0
      (+https://github.com/nathanramoscfa/weatherbot)` on
      every request, at most one request per second to
      `api.weather.gov` and to Nominatim, and coordinates only
      from `scripts/public_landmarks.toml`.
    </requirement>

    <requirement>
      The register table, with exactly this header (Step 5
      parses it):

      | Source id | Brief §5 source | Endpoint | Format | Fixture | Cadence | Terms | Verified |

      Source id: lowercase kebab-case, unique, stable. Start
      from this set and justify any change in the PR body:
      `nhc-current-storms`, `nhc-map-tropical-weather`,
      `nhc-map-tropical-summary`, `nhc-map-breakpoints`,
      `nhc-map-peak-surge`, `nhc-map-surge-risk`,
      `nhc-gis-rss`, `nhc-gis-archive`,
      `nhc-text-products`, `nhc-outlook-graphics`,
      `nws-points`, `nws-alerts-point`, `nws-alerts-zone`,
      `nws-zones`, `basemap-osm-tiles`, `overlay-radar`,
      `overlay-satellite`, `geocode-nominatim`. Fixture is
      `required` (Step 5 records it), `replay-corpus`
      (`nhc-gis-archive`; Step 6 records it), or `none —
      <reason>` (display-only content the code never parses,
      or content whose terms forbid redistribution in an MIT
      repository; OpenStreetMap tiles are `none`). Verified
      is the ISO date the row was checked live.
    </requirement>

    <requirement>
      Per-service sections. For each ArcGIS service: the
      catalog URL; how a client discovers layers (by name
      from `?f=json`, with numeric ids recorded only as "id
      on <date>"); a layer table with the header `| Layer name
      | Geometry | Fields present | Fields v2 uses | Notes |`,
      slot layers written as `{slot} Forecast Cone` with the
      slots listed (`AT1`–`AT5`, `EP1`–`EP5`, `CP1`–`CP5`);
      and the exact query parameters (`where`, `outFields`,
      `outSR=4326`, `f=geojson`, any server-side precision
      limit) that the recorder and Phase 2's clients will both
      use. Fill "Fields v2 uses" from the brief's §7 inputs and
      the project roadmap's 2.1 model list; a field not
      observed live is not listed.
    </requirement>

    <requirement>
      The open question (brief §14): per basin, a table with
      the header `| Storm | Arrival-time layers |
      Probabilistic winds 34/50/64 kt | Peak surge | Inundation
      | Checked |`, recording for each active storm (id, name,
      classification) what its layers returned on the
      verification date: a feature count, "empty", or
      "absent". A basin with no active storm reads "no active
      storm on <date>; open". Record which products the
      summary service serves across storms and which only per
      slot.
    </requirement>

    <requirement>
      NWS: `/points/{lat},{lon}` for both landmarks — the
      Nassau request returns the API's out-of-coverage error;
      record its status and body shape, since that is v2's
      non-US path — with the fields v2 uses as observed;
      `/alerts/active?point=`; `/alerts/active/zone/{zoneId}`
      for the county and forecast zones the Miami-Dade point
      returns; `/zones/{type}/{zoneId}`; and the API's
      User-Agent requirement and polite-use guidance, linked.
    </requirement>

    <requirement>
      Text products: compare NHC's `text/refresh` pages with
      the NWS API's `/products/types/{TCP|TWO}` JSON on one
      live product each, and record which path v2 uses and why.
      Prefer the structured JSON source when it carries the
      same product text and issuance time; no HTML scraping of
      storm pages.
    </requirement>

    <requirement>
      Graphics, RSS, archive: the six outlook graphic URLs
      (`two_{atl,pac,cpac}_{2d0,7d0}.png` — the brief's
      `two_epac_*` names return 404; the Eastern Pacific
      graphics are `two_pac_*`) with the headers that matter
      (`Last-Modified`, `ETag`, caching);
      `gis-at.xml`, `gis-ep.xml`, and `gis-cp.xml`; and the
      GIS archive's structure for the four replay storms
      (AL112017, AL052019, AL092022, AL142024): which file
      listings name the per-advisory forecast package, the
      wind-speed-probability files, and the arrival-time files,
      their naming in each year, and which products exist for
      which storm. Step 6 builds on this section.
    </requirement>

    <requirement>
      Overlays and geocoding: confirm one radar and one
      satellite (GOES) service the map can load as raster
      layers — NOAA first, the Iowa Environmental Mesonet
      otherwise — with endpoint, layer names, update cadence,
      and terms; cite OpenStreetMap's tile usage policy and
      Nominatim's usage policy (one request per second, an
      identifying User-Agent, results cached); set each fixture
      class by its terms.
    </requirement>

    <requirement>
      "Not used", with reasons: ATCF invest files (invests
      come from the outlook layers and the current-storms
      roster), NHC storm web pages (no HTML scraping), and any
      source that needs a key.
    </requirement>

    <requirement>
      A header section: the register's purpose; the
      User-Agent string and why it carries the repository URL
      and no email; the landmarks used (names, referring to
      `scripts/public_landmarks.toml`); how to re-verify
      (Step 5's recorder, and the "Source drift" triage
      class); and the verification date. Link the register
      from `README.md` and add a `CHANGELOG.md` `[Unreleased]`
      entry.
    </requirement>
  </requirements>
</task>
```

### Step 4 acceptance criteria

- `docs/DATA_SOURCES.md` has the register table with the exact header,
  one row per source id, every brief §5 source mapped to at least one id,
  and a `Verified` date on every row.
- Every ArcGIS layer is listed by name with its geometry, fields present,
  fields v2 uses, and the shared query parameters; no layer is identified
  by a numeric id alone.
- The per-basin table answers the open question for every basin with an
  active storm on the verification date and marks each other basin open
  with that date.
- The NWS section records both query paths for the Miami-Dade landmark
  and the out-of-coverage response for the Nassau landmark; the
  text-product path is chosen with its reason.
- One radar and one satellite service are confirmed with endpoint,
  layers, cadence, and terms; the OpenStreetMap and Nominatim policies are
  cited; ATCF and storm-page scraping are recorded as not used.
- The User-Agent string carries the repository URL and no personal
  address, and every coordinate in the document is an allowlisted
  landmark (the personal-data check passes in pre-commit and CI).
- **Security gate clean** (always the final criterion): the hook passed
  on every commit; no probe output, header dump, or scratch script was
  committed; and no endpoint requiring a credential was used.

---

## Step 5 — Fixture recorder and harvest ✅

**Status:** Complete — PR #14 (2026-10-12)

> **Goal:** Record a fixture of every `required` source in the register
> and harvest the six outlook maps the surviving v1 reports hold.
> `scripts/record_fixtures.py` (httpx with the register's User-Agent,
> query parameters, pacing, retries, and ArcGIS layer discovery by name)
> writes `tests/fixtures/recorded/<source-id>/<yyyy-mm-dd>/` with one
> `manifest.json` per capture directory (schema below) and stores any
> payload over 1 MiB gzip-compressed; its `harvest-v1` command extracts
> the six NHC seven-day outlook PNGs from
> `reports/hurricane_threat_analysis_2025*.html` with their provenance
> (and any `cache/*.json` the operator restored from a backup, mapped to
> URLs by recomputing v1's cache keys); `tests/fixtures/recorded/NOTICE.md`
> states the third-party terms; contract tests verify every capture
> (schema, checksum, parse by format, no unlisted file) and keep the
> register, the recorder, and the recorded service catalogs in agreement;
> recorder unit tests run without network through respx; and a test
> enforces the fixture budget (25 MiB in total, 5 MiB per stored file).
> Phase 2's clients are written against these captures.

**Branch:** `feature/phase01-step5-fixture-recorder`

**Deploys:** nothing beyond merge.

| Setting      | Value                                     |
| ------------ | ----------------------------------------- |
| Model        | Sonnet 5.5                                |
| Backup       | GPT-6 Sol — Codex · Intelligence High     |
| Platform     | Claude Code                               |
| Effort       | High                                      |
| Thinking     | On                                        |
| Conversation | **New**                                   |

**Model rationale:** A recorder that covers about fifteen sources in five
formats, discovers ArcGIS layers by name, writes checksummed manifests,
harvests embedded images, and is cross-checked against the register is
coding work (agentic secondary, since it runs live against NOAA) of High
complexity: many interacting concerns, each specified here, none novel.
The selector holds High work on Claude Code while the claude.ai Max
weekly pool reads `tight`, Sonnet 5.5 leads the S-tier coding models on
coverage, and the Max subscription pays at $0 marginal. Effort High, a
raise over Sonnet 5.5's `medium` default, is earned by the breadth of
formats and the cross-checks; Extra High would add pool burn without a
reasoning bottleneck to spend it on. Thinking is On. The Backup is GPT-6
Sol on Codex (ChatGPT Pro 5x) at Intelligence High. The conversation is
new per phase-boundary hygiene.

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
       feature/phase01-step5-fixture-recorder`
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
       Phase 1 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 1`
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

    THIS STEP adds network code
    and commits third-party data.
    Requests carry only landmark
    coordinates (rule R3 checks
    every manifest URL); manifests
    keep only the allowlisted
    response headers, never
    `set-cookie`; the harvest
    reads only the six 2025
    reports and writes only their
    outlook PNGs, never report
    HTML; bandit covers
    `scripts/`; and every stored
    file stays within the budget.
    The personal-data check with
    the local denylist runs over
    every capture before commit.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 1 (Foundation and
    discovery). Step 5: Fixture recorder and harvest.

    Current state (as of Phase 1, post-Step 4):

    - `docs/DATA_SOURCES.md` is the register: the table with
      the header `| Source id | Brief §5 source | Endpoint |
      Format | Fixture | Cadence | Terms | Verified |`;
      per-service layer tables with `{slot}` patterns; the
      shared query parameters; the User-Agent; the per-basin
      table; the text-product decision.
    - The gate's rule R3 checks every fixture manifest's
      `url` against `scripts/public_landmarks.toml`. It
      finds coordinates only in an NWS `/points/{lat},{lon}`
      path, a `point` parameter, and `lat`/`lon` (or
      `latitude`/`longitude`) parameters
      (`request_coordinates` in
      `scripts/check_personal_data.py`); if the recorder
      sends a coordinate any other way (an ArcGIS point
      `geometry`, say), extend that function and its tests
      in this step's PR. R1 scans `.gz` captures
      decompressed. A manifest is `manifest.json` or
      `*-manifest.json` under `tests/fixtures/`.
      Pre-commit's `check-added-large-files` caps a file at
      5120 KB; `.gitattributes` marks `tests/fixtures/**`
      `-text` and the whitespace hooks skip that tree, so a
      payload keeps its exact bytes on every platform.
      `httpx` and `respx` are in the `dev` group; the
      recorder is a development script, not package code
      (Phase 2 builds the clients in `weatherbot.sources`).
    - `reports/` holds six 2025 reports (ignored) embedding
      ten official PNGs: one seven-day Atlantic outlook map
      per report (`alt="NOAA 7-Day Atlantic Tropical Weather
      Outlook"`, 900×665, from
      `https://www.nhc.noaa.gov/xgtwo/two_atl_7d0.png`) and
      four forecast-cone graphics (Humberto, Imelda, Melissa
      twice), which are not a v2 source and stay where they
      are. Each report's filename carries the local (EDT)
      time it was written.
    - `cache/` holds one v1 test entry unless the operator
      restored the 38 lost responses from a backup. v1 keyed
      them `md5(f"{url}_{params}")` for the map service,
      `md5(url)` for current storms, and `"atcf_" +
      md5(url)` for ATCF (`git show
      v1.0.0:src/weatherbot/nhc.py`, `nhc_current_storms.py`,
      `atcf_client.py`).

    Files to read (every file before drafting):
    - docs/roadmap/phase01-roadmap.md (this step, and Step
      6's reuse of the budget test).
    - docs/DATA_SOURCES.md.
    - scripts/check_personal_data.py (rule R3) and
      scripts/public_landmarks.toml.
    - pyproject.toml, tests/conftest.py,
      .pre-commit-config.yaml.
    - docs/brief/weatherbot-v2-brief.md (§5).
  </context>

  <goal>
    Commit `scripts/record_fixtures.py`, a manifest-verified
    capture of every `required` register source, the six
    harvested outlook maps with provenance, a NOTICE for
    third-party terms, contract tests over every capture and
    across register, recorder, and recorded catalogs, recorder
    unit tests without network, and a test that enforces the
    fixture budget.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      The manifest. Every capture directory holds one
      `manifest.json` of this shape:

      {
        "schema": 1,
        "source": "nhc-current-storms",
        "recorded_at": "2026-10-20T15:02:11Z",
        "recorder": "scripts/record_fixtures.py",
        "user_agent": "weatherbot/2.0.0.dev0 (+https://github.com/nathanramoscfa/weatherbot)",
        "captures": [
          {
            "file": "CurrentStorms.json",
            "url": "https://www.nhc.noaa.gov/CurrentStorms.json",
            "status": 200,
            "fetched_at": "2026-10-20T15:02:11Z",
            "sha256": "<hex digest of the bytes as received>",
            "bytes": 4113,
            "stored_as": "raw",
            "headers": {"content-type": "application/json"},
            "origin": "live",
            "notes": ""
          }
        ]
      }

      `sha256` and `bytes` describe the payload as received.
      `stored_as` is `raw` or `gzip`; a gzip file adds `.gz`
      to its name and is written with `mtime=0`, so recording
      identical bytes yields an identical file. `headers`
      keeps only `content-type`, `content-length`,
      `last-modified`, `etag`, `date`, `cache-control`,
      `expires`, and `age`. `origin` is `live`,
      `harvest:v1-report`, or `harvest:v1-cache`; a harvested
      capture adds `harvested_from` and takes `fetched_at`
      from the report filename converted from EDT to UTC, with
      `notes` saying so.
    </requirement>

    <requirement>
      `scripts/record_fixtures.py` CLI: `record --all` or
      `record --source <id>…`, `--out` (default
      `tests/fixtures/recorded`), `--date` (tests only), and
      `harvest-v1`. One module-level `SOURCES` mapping from
      register ids to recording functions; one User-Agent
      constant equal to the register's; httpx with timeouts,
      retries with backoff on 5xx and connection errors, and
      pacing (at least one second between requests to
      `api.weather.gov` and to Nominatim; NHC requests run
      serially). A non-200 response the register documents
      (the Nassau `/points` response) is recorded as a capture
      with its status and body.
    </requirement>

    <requirement>
      ArcGIS: record each register map service's catalog
      (`?f=json` and `/layers?f=json`), resolve layers by name
      from it (never a hard-coded id), and record every
      register layer for every active slot plus the outlook
      layers with the register's query parameters, including
      the summary service's probabilistic-wind layers.
    </requirement>

    <requirement>
      Every other `required` source, per the register:
      current storms; the three GIS RSS feeds; the text
      products through the register's chosen path for every
      active storm and basin; the six outlook graphics; NWS
      points, point alerts, county and forecast-zone alerts,
      and zones; the overlay capabilities documents the
      register marks `required`; and one Nominatim reverse
      lookup per landmark.
    </requirement>

    <requirement>
      Size: store a payload over 1 MiB as gzip. A stored file
      over 5 MiB fails the run with its source and size named;
      shrink it through server-side query parameters recorded
      in the register in this PR, never by editing a payload.
    </requirement>

    <requirement>
      Harvest (`harvest-v1`): read the six 2025 reports,
      decode each embedded PNG whose `alt` names the NOAA
      seven-day Atlantic outlook, verify its PNG signature and
      dimensions, and write it to
      `tests/fixtures/recorded/nhc-outlook-graphics/<report
      date>/two_atl_7d0.png` with a manifest entry (`origin:
      harvest:v1-report`, `url` the xgtwo URL,
      `harvested_from`, `fetched_at` from the filename). The
      folder date is the local date in the report's filename,
      not the UTC date of `fetched_at`: the 2025-10-03 22:45
      EDT report falls on 2025-10-04 in UTC and would collide
      with the 2025-10-04 report's folder. Read
      nothing else from the reports, and never commit report
      HTML or the cone graphics. If `cache/` holds restored v1
      responses, recover each file's URL by recomputing v1's
      keys over v1's request set and harvest the ones whose
      URL belongs to a `required` register source; list the
      unrecoverable and out-of-register files in the PR body,
      not in fixtures.
    </requirement>

    <requirement>
      Run it: `record --all` on the step's date, then
      `harvest-v1`, and commit the captures. Retry a source
      that is down later in the session; a source that stays
      down is a Source-drift finding (an issue plus a register
      note), and the step is not complete until every
      `required` id has a capture.
    </requirement>

    <requirement>
      `tests/fixtures/recorded/NOTICE.md`: NOAA content is in
      the public domain; the Nominatim captures are ©
      OpenStreetMap contributors under ODbL 1.0; anything else
      follows the register's Terms column.
    </requirement>

    <requirement>
      Contract tests in `tests/contract/`:
      - `test_recorded_fixtures.py`: every manifest matches
        the schema; every listed file exists; checksum and size
        match after decompression; every file in a capture
        directory is listed; content parses by format (JSON and
        GeoJSON load, GeoJSON is a FeatureCollection, a PNG has
        its signature and the recorded dimensions, XML parses,
        text decodes); no stored header is outside the
        allowlist.
      - `test_register.py`: the register's ids equal
        `SOURCES` plus the rows that are not `required`; every
        `required` id has at least one capture with status
        200; every ArcGIS layer name in the register, with
        `{slot}` expanded over the slots in the recorded
        catalog, exists in that service's recorded catalog.
        `StormSurgeRisk` repeats its layer names, so the
        register names those layers by group path: a name
        containing ` / ` is a path of layer names from the
        service root, and `{n}` expands over the categories
        the register lists for that region (Step 4,
        2026-10-12).
      - `test_fixture_budget.py`: the stored bytes under
        `tests/fixtures/recorded/` total at most 25 MiB, and
        every stored file is at most 5 MiB (Step 6 extends it
        to the replay subset).
    </requirement>

    <requirement>
      Recorder unit tests in
      `tests/scripts/test_record_fixtures.py` (respx, no
      network): every request carries the User-Agent; layer
      resolution by name survives shifted ids; pacing holds
      under a fake clock; payloads over 1 MiB are stored as
      gzip, and the same bytes produce the same stored file;
      the harvest of a synthetic report with one outlook PNG
      and one other PNG takes only the outlook map;
      disallowed headers are dropped. Add one `live`-marked
      test, also carrying pytest-socket's `enable_socket`
      marker (Step 2's socket guard otherwise blocks it), that
      records `nhc-current-storms` into `tmp_path` and
      validates its manifest, and run it in this session with
      `uv run pytest -m live`.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with a `# <repo-relative path>` comment.
    </requirement>
  </requirements>
</task>
```

### Step 5 acceptance criteria

- `uv run python scripts/record_fixtures.py record --all` and `harvest-v1`
  ran on the step's date; `tests/fixtures/recorded/` holds a
  manifest-verified capture of every `required` register id, plus the
  six outlook maps from 2025-09-30, 10-03, 10-04, 10-06, 10-22, and 10-23
  with their provenance.
- `tests/contract/` passes on both runners: schema, checksums, formats,
  and the register ↔ recorder ↔ recorded-catalog agreement; the budget
  holds (at most 25 MiB in total, 5 MiB per stored file).
- The recorder's unit tests pass without network, and `uv run pytest -m
  live` passed in the session.
- Every coordinate in a manifest URL is an allowlisted landmark (R3
  passes in CI), and no manifest stores a header outside the allowlist.
- No report HTML, no cone graphic, and no file from `cache/` outside the
  register is committed; `NOTICE.md` states the third-party terms.
- **Security gate clean** (always the final criterion): the hook passed
  on every commit; bandit is clean over the recorder; and the
  personal-data check, with the local denylist and with R3 in CI, passed
  over every capture.

---

## Step 6 — Replay corpus

**Status:** Not started

> **Goal:** Build the historical replay corpus that Phase 3's harness and
> golden tests load. `scripts/fetch_replay_corpus.py` discovers the NHC
> GIS archive files for Irma (AL112017), Dorian (AL052019), Ian
> (AL092022), and Milton (AL142024) from the archive's file listings, as
> the register documents them; downloads the per-advisory forecast
> packages (shapefile zips, and KMZ only for a product with no shapefile)
> and, where the archive has them, the wind-speed-probability and
> arrival-time products into a git-ignored cache; verifies every file
> against the committed `tests/fixtures/replay/corpus-manifest.json` (URL,
> size, SHA-256, storm, advisory, product); and converts each advisory's
> forecast products (cone, track, points, watch-warning lines) into
> deterministic, gzip-compressed GeoJSON under
> `tests/fixtures/replay/<storm-id>/<advisory>/` — the committed subset,
> at most 10 MiB. `.github/workflows/replay-corpus.yml` restores the full
> cache from an actions cache keyed on the manifest's hash, fetches on a
> miss, verifies checksums, and runs twice a week to keep the cache alive and
> catch archive drift. Tests cover the subset on every pull request and
> the full cache when it is present.

**Branch:** `feature/phase01-step6-replay-corpus`

**Deploys:** GitHub Actions → `replay-corpus.yml` runs on merge (path
trigger), then twice a week and on demand; it is not a required check.

| Setting      | Value                                  |
| ------------ | -------------------------------------- |
| Model        | GPT-6 Sol                              |
| Backup       | Sonnet 5.5 — Claude Code · Effort High |
| Platform     | Codex                                  |
| Intelligence | Medium                                 |
| Conversation | **New**                                |

**Model rationale:** A bounded download, verify, and convert pipeline
over four storms in documented formats is coding work (agentic secondary,
since it drives the archive) of Medium complexity: the register already
maps the archive, so what remains is careful, well-specified
implementation. The selector's quality pick at that level is Sonnet 5.5,
but with the claude.ai Max weekly pool reading `tight`, the selector sends
Medium work to the funded pool with headroom: GPT-6 Sol on Codex, S-tier
in coding and agentic work, paid by the ChatGPT Pro 5x subscription at $0
marginal. Intelligence is set to Medium explicitly, to match the step's
complexity. The Backup is Sonnet 5.5 on Claude Code (claude.ai Max) at
Effort High, the capped ladder's tight-pool rung for Medium work. The
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
       feature/phase01-step6-replay-corpus`
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
       Phase 1 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 1`
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

    THIS STEP downloads archives
    and parses them: verify every
    file's SHA-256 against the
    committed manifest before
    reading it; read zip members
    in memory, or extract them
    only after rejecting absolute
    paths and `..`; never execute
    or import archive content.
    The new dependencies (pyshp,
    shapely) pass pip-audit. The
    workflow is read-only
    (`contents: read`),
    SHA-pinned, and uses no secret.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 1 (Foundation and
    discovery). Step 6: Replay corpus.

    Current state (as of Phase 1, post-Step 5):

    - `docs/DATA_SOURCES.md` documents the GIS archive for the
      four storms: the listing URLs, the naming in each year,
      and which products exist for which storm.
    - Step 4 found, on 2026-10-12: the arrival-time archive
      begins in 2018, so Irma has no arrival-time product;
      arrival times are KMZ only, and
      `archive_toa_results.php` ignores its `id` and `year`
      (one 1.9 MB page of every file since 2018: filter by
      storm id). Wind-speed probabilities are one file set
      per synoptic time with no storm in the name: match
      each advisory to the set whose time equals the
      `SYNOPTIME` in its `_fcst_` package. Ian's `_fcst_`
      packages stop at advisory 035, while `_5day_` runs
      to 038. Inundation zips are 10–22 MB each and are
      not part of the corpus.
    - `scripts/record_fixtures.py` holds the HTTP client
      settings (User-Agent, timeouts, retries) and the gzip
      writer (`mtime=0`); `tests/contract/test_fixture_budget.py`
      enforces the recorded budget. Step 5's names to reuse:
      `USER_AGENT`, `REQUEST_TIMEOUT`, `Fetcher` (with `Pacer`:
      per-host spacing, retries, backoff), `stored_form` (gzip
      above `GZIP_THRESHOLD_BYTES`), and `RecorderError`. The
      budget test lists its roots in `BUDGETED_ROOTS` (add
      `tests/fixtures/replay/` there, with its own 10 MiB cap);
      `tests/contract/fixture_support.py` holds the readers the
      contract tests share.
    - Archive files are immutable, so their checksums are
      stable once recorded; the archive is public and keyless,
      and polite use means serial requests with the project
      User-Agent.
    - `actions/cache` entries unused for seven days are
      evicted; scheduled workflows in a public repository stop
      after 60 days without repository activity.

    Files to read (every file before drafting):
    - docs/roadmap/phase01-roadmap.md (this step, Step 5's
      manifest rules, and Step 7's corpus checks).
    - docs/DATA_SOURCES.md (the archive section).
    - scripts/record_fixtures.py (reuse its client settings
      and gzip writer rather than duplicating them).
    - tests/contract/test_fixture_budget.py,
      .github/workflows/ci.yml (pinning and permission
      conventions), .gitignore, pyproject.toml.
    - docs/roadmap/ROADMAP.md (Phase 3, for what the replay
      harness needs).
  </context>

  <goal>
    Commit `scripts/fetch_replay_corpus.py`, the checksum
    manifest for the four storms' archive files, the
    reproducible GeoJSON subset within its budget, the
    `replay-corpus.yml` workflow, and tests over the subset and
    the full cache.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes.
    </requirement>

    <requirement>
      Add `pyshp` (a pure-Python shapefile reader) and
      `shapely` (geometry validity in tests) to the `dev`
      group; nothing that needs GDAL.
    </requirement>

    <requirement>
      `scripts/fetch_replay_corpus.py` commands: `fetch`
      (download missing files into the cache, default
      `.cache/replay-corpus/`, overridable with
      `WEATHERBOT_CORPUS_CACHE`); `verify` (every manifest
      entry present with matching size and SHA-256; non-zero
      exit on any mismatch); `convert` (rebuild the committed
      subset from the cache); and `manifest` (write
      `tests/fixtures/replay/corpus-manifest.json` from a
      fresh fetch — run once in this step, and later only for
      a deliberate refresh). Discovery reads the archive's
      file listings that the register names, never a storm web
      page.
    </requirement>

    <requirement>
      Conversion: per advisory and product, one GeoJSON
      FeatureCollection with the shapefile's attributes as
      properties and coordinates in the shapefile's
      geographic CRS. Record each `.prj` datum in the
      manifest, and stop and report if a file is projected or
      on a datum other than WGS84 or NAD83. Sort keys, use a
      fixed float format, and write gzip with `mtime=0`, so
      `convert` is reproducible byte for byte.
    </requirement>

    <requirement>
      The committed subset: every advisory's cone, track,
      points, and watch-warning lines for all four storms, at
      most 10 MiB stored in total. If that does not fit, keep
      for each storm the advisories whose cone or
      watch-warning lines intersect the box 20°N–31°N,
      88°W–72°W (Florida and the Bahamas), plus the first and
      last advisory, and record the rule in the manifest. The
      original archive files and the probability and
      arrival-time products stay in the cache.
    </requirement>

    <requirement>
      `.gitignore`: add `.cache/`.
    </requirement>

    <requirement>
      `.github/workflows/replay-corpus.yml`: triggers `push`
      to `main` and `pull_request` on changes to
      `scripts/fetch_replay_corpus.py` or
      `tests/fixtures/replay/**`, a `schedule` twice a week
      (inside GitHub's seven-day cache eviction), and
      `workflow_dispatch` with a boolean input
      `simulate_failure`. One ubuntu-latest job: restore
      `actions/cache` keyed on
      `hashFiles('tests/fixtures/replay/corpus-manifest.json')`,
      run `fetch` on a miss, then `verify` and `uv run pytest
      -m corpus`, and fail at the end when `simulate_failure`
      is true. SHA-pinned actions, `permissions: contents:
      read`, no secrets, `timeout-minutes`. It joins neither
      `gate` nor branch protection.
    </requirement>

    <requirement>
      Tests: `tests/replay/test_corpus_manifest.py` (schema;
      all four storms; every committed GeoJSON traces to
      manifest entries); `tests/replay/test_corpus_subset.py`
      (each storm's advisories in order, with any gap
      explained by the manifest; every cone a valid polygon
      under shapely; every point and track feature carrying
      its advisory number; and, under the `corpus` marker,
      the subset re-converting byte for byte from the cache);
      and `tests/contract/test_fixture_budget.py` extended to
      `tests/fixtures/replay/` at most 10 MiB.
    </requirement>

    <requirement>
      Run `manifest`, `verify`, and `convert`; commit the
      manifest and the subset. Record in
      `docs/DATA_SOURCES.md`'s archive section the cache size,
      the file count per storm, and which storms lack which
      products.
    </requirement>

    <requirement>
      The alarm proof: after the merge, dispatch
      `replay-corpus.yml` once with `simulate_failure: true`
      and confirm the run is red (GitHub's failure email is
      the alarm), then once without it and confirm it is
      green. Add both run URLs to the PR body through the REST
      API, for Step 7's QA findings.
    </requirement>

    <requirement>
      Filepath comment: every new Python, YAML, and TOML file
      starts with a `# <repo-relative path>` comment.
    </requirement>
  </requirements>
</task>
```

### Step 6 acceptance criteria

- `uv run python scripts/fetch_replay_corpus.py fetch` followed by
  `verify` downloads all four storms' files with every checksum matching
  the committed manifest, both on the operator's machine and in
  `replay-corpus.yml`.
- The committed subset covers all four storms, re-converts byte for byte
  from the cache, and stores at most 10 MiB; the recorded budget still
  holds.
- `tests/replay/` passes in `ci.yml` on both runners (subset) and with
  `-m corpus` in `replay-corpus.yml` (full cache).
- `docs/DATA_SOURCES.md` records the corpus's size, its file counts, and
  the products each storm lacks.
- **Deployed & verified:** after the merge, the path-triggered
  `replay-corpus.yml` run on `main` is green and saved the cache; a
  `simulate_failure: true` dispatch ran red and a plain dispatch ran
  green, and both run URLs are in the PR body.
- **Security gate clean** (always the final criterion): the hook passed
  on every commit; bandit is clean over the script; every download is
  checksum-verified before parsing and archive members are path-checked;
  pip-audit passed with pyshp and shapely; and the workflow is read-only,
  SHA-pinned, and secret-free.

---

## Step 7 — QA & Verification Script

**Status:** Not started

> **Goal:** Package the verification matrix into
> `scripts/verify_phase01.py` (with `--fast`, `--py`, `--corpus`,
> `--security`, `--all`, and `--post` modes), produce
> `docs/phase01-qa-findings.md`, and add `.github/workflows/phase-verify.yml`
> with matrix entry `"01"` and an aggregate `phase-verify` check required
> on `main`. The script's 50 numbered static checks cover every Step 1
> through Step 6 deliverable plus four self-checks; `--py` runs the lint,
> type, contract, and test suites; `--corpus` verifies the full replay
> cache; `--security` runs the four-check gate; and `--post` reports the
> V1–V7 matrix, including the GitHub readbacks and the updater dry run.
> The same step closes Phase 1 in this roadmap and in the project
> roadmap, and tags `v2.0.0-phase-1`.

**Branch:** `feature/phase01-step7-verify`

**Deploys:** GitHub Actions → the `phase-verify.yml` matrix entry is live
on merge; GitHub repository → `phase-verify` joins `main`'s required
checks through the API before the merge, and the `v2.0.0-phase-1` tag is
pushed after it.

| Setting      | Value                                  |
| ------------ | -------------------------------------- |
| Model        | GPT-6 Sol                              |
| Backup       | Sonnet 5.5 — Claude Code · Effort High |
| Platform     | Codex                                  |
| Intelligence | Medium                                 |
| Conversation | **New**                                |

**Model rationale:** Translating this roadmap's acceptance criteria into
numbered, independent static checks, a V-matrix, a workflow, and a
findings rollup is coding work (agentic secondary) of Medium complexity:
the structure follows judge-metrics' `scripts/verify_phaseNN.py`, and
every check's content is written down below. With the claude.ai Max
weekly pool reading `tight`, the selector sends Medium work to the funded
pool with headroom: GPT-6 Sol on Codex, S-tier in coding and agentic
work, paid by the ChatGPT Pro 5x subscription at $0 marginal, with
Intelligence set to Medium explicitly. The Backup is Sonnet 5.5 on Claude
Code (claude.ai Max) at Effort High. The conversation is new per
phase-boundary hygiene.

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
       feature/phase01-step7-verify`
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
       Phase 1 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 1`
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
       complete. Phase 1 is
       complete. You can now move
       on to Phase 2." That
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
       one before Phase 2.
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

    THIS STEP also AUTHORS the
    `--security` verify mode, so
    its own diff must still pass
    the gate before commit. The
    script reads the repository
    and runs the gate's tools; it
    never prints a denylist value,
    and `--post` reads GitHub
    settings through `gh` without
    writing any. The new workflow
    is SHA-pinned, `contents:
    read`, and secret-free.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 1 (Foundation and
    discovery). Step 7: QA + verification script.

    Steps 1 through 6 have been implemented. Now create the
    verification script, the QA findings document, and the
    `phase-verify.yml` workflow, then close the phase.

    Reference scripts (pattern templates):
    - the newest `scripts/verify_phaseNN.py` on judge-metrics'
      `main` (`verify_phase04.py` on 2026-10-11) and its
      `.github/workflows/phase-verify.yml`
      (https://github.com/nathanramoscfa/judge-metrics):
      the closest structural precedent — numbered,
      independent static checks reading the repository only;
      modes from `--fast` to `--post`; a V-matrix report.
      This repository has no earlier verify script;
      `verify_phase01.py` becomes the template later phases
      mirror.

    Phase 1 deliverables to verify (46 static checks across
    Steps 1 through 6, plus 4 Step 7 self-checks):

    Step 1 (freeze v1, `main`) — checks 1-6:
    1.  `v1.0.0` exists and is an annotated tag (`git
        cat-file -t v1.0.0` prints `tag`).
    2.  `v1.0.0^{commit}` is
        `45623a17ef3c6c3f96395f35ad211c7054c5cbbb`, or the
        commit Step 1's PR proved.
    3.  `CHANGELOG.md`'s retirement note names
        `weatherbot==1.0.0` and the `v1.0.0` tag.
    4.  `CHANGELOG.md` dates `[1.0.0]` 2025-09-29 and has
        exactly one `[Unreleased]` heading.
    5.  `AGENTS.md` names `main` as the ledger branch and does
        not contain "on `master`".
    6.  `docs/roadmap/ROADMAP.md` no longer matches "read
        `master` wherever" (case-insensitive), and its Phase 1
        row in §8 is not `Not started`.

    Step 2 (uv scaffold) — checks 7-20:
    7.  `pyproject.toml`: name `weatherbot`, version
        `2.0.0.dev0`, `requires-python = ">=3.13"`, build
        backend `uv_build`.
    8.  `.python-version` reads `3.13`, and `uv.lock` is
        tracked.
    9.  `git ls-files src/weatherbot` equals the eight-file
        skeleton.
    10. None of the v1 files Step 2 deleted is tracked.
    11. `[dependency-groups]` has `dev` and `planning`;
        `planning` lists `roadmodel` and `pip`; `[tool.uv]
        default-groups` names both.
    12. `[project.scripts]` maps `weatherbot` to
        `weatherbot.cli:app`, and `typer` is the only runtime
        dependency.
    13. `[tool.importlinter]` declares the engine-forbidden
        contract and the layers contract.
    14. `tests/test_architecture.py` exists and bans the I/O
        roots in the engine.
    15. Ruff selects `ALL`, and every ignore entry carries a
        trailing reason comment.
    16. Pyright's `typeCheckingMode` is `strict`.
    17. Pytest's options carry `--allow-hosts`,
        `--strict-markers`, and the `live` and `corpus`
        markers; `tests/conftest.py` changes the working
        directory to `tmp_path`.
    18. `.gitignore` ignores `.venv/`, `.worktrees/`, `.env`,
        `cache/`, `reports/`, `logs/`, `state/`, and
        `planning/user-context.md`.
    19. `README.md` links `DISCLAIMER.md`, names the `v1.0.0`
        tag, and does not contain "global coverage" in any
        letter case (v1's README says "Global Coverage").
    20. `.github/workflows/ci.yml` defines `lint`,
        `typecheck`, `test` (ubuntu-latest and
        windows-latest), `package`, and `gate`.

    Step 3 (security gate) — checks 21-30:
    21. `.pre-commit-config.yaml` defines gitleaks, bandit,
        pip-audit, the personal-data check, ruff, ruff format,
        pyright, lint-imports, check-added-large-files
        (`--maxkb=5120`), and no-commit-to-branch (`main`);
        its whitespace and end-of-file hooks exclude
        `tests/fixtures/`, which `.gitattributes` marks
        `-text`.
    22. Every pre-commit hook repository `rev` is a 40-hex
        SHA.
    23. `scripts/check_personal_data.py`,
        `scripts/audit_deps.py`, and
        `scripts/public_landmarks.toml` are tracked; the TOML
        lists at least two landmarks, each with a `source`.
    24. `ci.yml`'s `security` job runs gitleaks, bandit,
        `audit_deps.py`, and `check_personal_data.py --all
        --ci`, and `gate` needs it.
    25. Every `uses:` in `.github/workflows/*.yml` is pinned
        to a 40-hex SHA with a version comment.
    26. Every workflow declares top-level `permissions:`, and
        none uses `pull_request_target`.
    27. `.github/dependabot.yml` lists the `uv` and
        `github-actions` ecosystems.
    28. `SECURITY.md` exists and names private vulnerability
        reporting.
    29. No tracked file matches a full key shape: a PEM
        private-key header (five dashes, `BEGIN`, an optional
        key type, `PRIVATE KEY`, five dashes), an AWS access
        key id (`AKIA` plus 16 uppercase letters or digits),
        or an Anthropic key (`sk-ant-` plus 20 or more key
        characters). Build each pattern so it cannot match its
        own source or this document's description of it.
    30. No `.env` or `*.env` file is tracked.

    Step 4 (data-source register) — checks 31-35:
    31. `docs/DATA_SOURCES.md` exists and contains the exact
        register header.
    32. The register has at least 15 rows, each with a
        lowercase kebab-case id and an ISO `Verified` date,
        including `nhc-current-storms`,
        `nhc-map-tropical-weather`, `nws-points`,
        `nws-alerts-point`, and `nws-alerts-zone`.
    33. The register states the User-Agent with
        `github.com/nathanramoscfa/weatherbot` and no `@`.
        Check the User-Agent string itself, not the whole
        file: the register quotes JSON-LD keys such as
        `@id`.
    34. The register records ATCF and storm-page scraping as
        not used.
    35. The register contains the per-basin table header.

    Step 5 (fixture recorder) — checks 36-41:
    36. `scripts/record_fixtures.py` is tracked and defines
        `SOURCES`.
    37. Every register row with Fixture `required` has a
        `tests/fixtures/recorded/<id>/<date>/manifest.json`.
    38. `tests/fixtures/recorded/nhc-outlook-graphics/` holds
        harvested manifests for the six 2025 dates, each with
        `harvested_from`.
    39. `tests/fixtures/recorded/NOTICE.md` exists and names
        ODbL.
    40. `tests/contract/test_recorded_fixtures.py`,
        `test_register.py`, and `test_fixture_budget.py` are
        tracked.
    41. No manifest stores a `set-cookie` header, and no file
        under `reports/` is tracked.

    Step 6 (replay corpus) — checks 42-46:
    42. `scripts/fetch_replay_corpus.py` is tracked with the
        `fetch`, `verify`, `convert`, and `manifest` commands.
    43. `tests/fixtures/replay/corpus-manifest.json` names
        AL112017, AL052019, AL092022, and AL142024.
    44. `tests/fixtures/replay/` holds a committed subset
        directory for each of the four storms.
    45. `.github/workflows/replay-corpus.yml` has a
        `schedule`, a `workflow_dispatch` with
        `simulate_failure`, and an `actions/cache` keyed on
        the manifest's hash.
    46. `.gitignore` ignores `.cache/`.

    Step 7 self-checks — checks 47-50:
    47. `scripts/verify_phase01.py` is tracked and defines all
        six mode flags.
    48. `docs/phase01-qa-findings.md` exists.
    49. `docs/roadmap/phase01-roadmap.md` exists (this
        document).
    50. `.github/workflows/phase-verify.yml`'s matrix includes
        `"01"`.

    Files to read (every file before drafting):
    - docs/roadmap/phase01-roadmap.md (every step's
      acceptance criteria; Post-Implementation Verification).
    - all Phase 1 implementation files from Steps 1 through
      6, and every Phase 1 PR body (`gh pr view <n>`), for the
      findings rollup.
    - judge-metrics' newest `scripts/verify_phaseNN.py` on
      `main` (structure).
  </context>

  <goal>
    Create `scripts/verify_phase01.py` with 50 static checks
    (Steps 1 through 6, plus 4 Step 7 self-checks) and the
    post-implementation V1-V7 matrix; create
    `docs/phase01-qa-findings.md`; add the `phase-verify.yml`
    workflow with matrix entry `"01"` and make its aggregate
    check required; close Phase 1 in both roadmaps; tag
    `v2.0.0-phase-1`.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any
      changes, including that judge-metrics verify script
      end to end for structure, flag parsing, output format,
      PASS/FAIL conventions, and the final summary table.
      Mirror that format so later phases' scripts read the
      same in CI logs.
    </requirement>

    <requirement>
      `scripts/verify_phase01.py` modes:
      - `--fast`: the 50 static checks only; CI-safe on
        Ubuntu and Windows; no network; under 30 seconds;
        standard library only (pathlib, re, json, tomllib,
        hashlib, `git ls-files`).
      - `--py`: static checks + `ruff check`, `ruff format
        --check`, `pyright`, `lint-imports`, `pytest` (unit,
        contract, and replay-subset suites), and the package
        smoke (`uv build`, the wheel installed into a temporary
        `uv venv`, its `weatherbot --version` compared with the
        project version).
      - `--corpus`: static checks + `fetch_replay_corpus.py
        verify` (fetching on a miss) + `pytest -m corpus`.
      - `--security`: static checks + gitleaks (when
        installed; CI installs it), bandit, `audit_deps.py`,
        and `check_personal_data.py --all` (with `--ci` when
        the `CI` variable is set) and `--self-test`. Run
        gitleaks over history (`gitleaks git --redact`, clean
        because `.gitleaksignore` lists the two placeholder
        keys in version 1's history), never `gitleaks dir .`,
        which also reads the untracked `.venv` and v1 data
        (151 hits on 2026-10-12).
      - `--all`: static + py + corpus + security.
      - `--post`: static checks + the V1-V7 matrix: the suites
        above; `gh` readbacks when `gh` is signed in (default
        branch `main`, the merge settings, protection with
        `gate` and `phase-verify` required, `v1.0.0` on
        `origin` peeling to the release commit, Dependabot
        alerts enabled, the latest `ci.yml` and
        `replay-corpus.yml` runs on `main`, the recorded
        `simulate_failure` run); `gh pr checks` for the current
        branch; the roadmodel updater's dry run (local only,
        printing only this project's line, since the dry run
        lists every registered project); and `uv run pytest -m
        live`.

      Each static check reads the repository only, prints one
      PASS or FAIL line with its number, and is independent of
      the others. `--fast` exits 0 only when all 50 pass;
      every mode exits 1 on any failure.
    </requirement>

    <requirement>
      `tests/test_phase01_verification.py`:
      - `test_roadmap_doc_exists`.
      - `test_qa_findings_doc_exists`.
      - `test_verify_script_runs_fast` (a subprocess run of
        `--fast` exits 0, with `cwd` set to the repository
        root, since `tests/conftest.py` moves every test into
        `tmp_path`).
      - `test_phase_verify_matrix_includes_01`.
      Checks 1 and 2 need the `v1.0.0` tag, so give `ci.yml`'s
      `test` job checkout `fetch-depth: 0`; a shallow,
      tagless clone would turn `gate` red on both runners.
    </requirement>

    <requirement>
      `.github/workflows/phase-verify.yml`: triggers `push` to
      `main` and `pull_request`; matrix `phase: ["01"]`; a job
      `verify`, named `phase-verify (<phase>)` from the matrix
      value, that checks out with `fetch-depth: 0` (the tag
      checks need tags), runs `uv sync --locked`, then `uv
      run python scripts/verify_phase<phase>.py --fast` and
      `--security` (installing gitleaks as `ci.yml` does); and
      an aggregate job `phase-verify` that needs `verify` and
      fails unless it succeeded. SHA-pinned actions,
      `permissions: contents: read`, `persist-credentials:
      false`, `timeout-minutes`. Later phases append to the
      matrix and keep every entry.
    </requirement>

    <requirement>
      Once `phase-verify` is green on this PR (Stage 4, before
      merging), add it to `main`'s required checks beside
      `gate` (re-PUT the protection with both contexts) and
      read the protection back.
    </requirement>

    <requirement>
      `docs/phase01-qa-findings.md`: a rollup per step
      (finding, class, destination, guard), including at
      least the loss of the 38 v1 cache responses on
      2026-10-11 (class: a v1 implementation bug surfaced by a
      process step; guard: every v2 test runs in a temporary
      working directory, `tests/conftest.py`), every finding
      recorded in the Step 1 to Step 6 PR bodies, the per-basin
      layer answers still open, and the `simulate_failure`
      run URLs; then a "Pre-ship items" section with
      documented limitations and downstream follow-ups, each
      with the phase that owns it: Phase 2 reuses the
      register's query parameters, User-Agent, and fixtures;
      Phase 3 reads the ladder wording from `v1.0.0` and the
      probability and arrival-time products from the corpus
      cache; Phase 5 adds npm to Dependabot; an open basin is
      re-checked when a storm is active there.
    </requirement>

    <requirement>
      Mark the phase complete in the parent project roadmap
      (docs/roadmap/ROADMAP.md, beside this file) in the
      SAME Stage-3 commit that marks this step (Status rule):
      - `### Phase 1` gets `**Status:** Complete —
        <YYYY-MM-DD>; PR #<n>; v2.0.0-phase-1;
        phase01-roadmap.md` directly under its heading, and
        the heading ends in ✅.
      - Its row in the "Phase Complexity Summary" table reads
        `Complete` (Step 1's PR set it to `In progress`).
      - The header `> **Status:**` line names Phase 1 as
        shipped and Phase 2 as next.
      - Consistency audit: the Phase 1 "Acceptance criteria"
        there match this roadmap's V1-V7 checks.
      And in THIS roadmap, same commit: its phase-level
      `**Status:**` line (under the title) reads `Complete —
      <YYYY-MM-DD>`, the title and every step heading end in
      ✅, and every step's Summary Table Status cell reads
      `Complete — PR #<n>`.
    </requirement>

    <requirement>
      After the merge, tag the merge commit: `git tag -a
      v2.0.0-phase-1 <merge commit> -m "Phase 1: foundation and
      discovery"`, then `git push origin v2.0.0-phase-1`. The
      package version stays `2.0.0.dev0`.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative
      path as the first line (Python and YAML `#` comments;
      Markdown follows its siblings, which carry none).
    </requirement>
  </requirements>
</task>
```

### Step 7 acceptance criteria

- `scripts/verify_phase01.py` exists and passes on a clean tree after
  implementation; all six modes exist.
- The script has 50 static checks plus the V1–V7 post-implementation
  checks (75 in total).
- `--fast` runs in under 30 seconds on Ubuntu CI and on the operator's
  Windows machine.
- `--post` runs cleanly on the operator's Windows machine with `gh` signed
  in, reporting V1.1 through V7.4 green.
- `docs/phase01-qa-findings.md` is complete, with every rollup section and
  a destination for every finding.
- `.github/workflows/phase-verify.yml` runs matrix entry `"01"` on every
  pull request, and `phase-verify` is a required check on `main` beside
  `gate`.
- `--security` exits 0 (secret scan, SAST, dependency audit, and the
  personal-data check clean over the phase's surface); V7.4 is green.
- Branch protection still passes on the resulting PR.
- **Deployed & verified:** the first `phase-verify.yml` run on `main`
  after the merge is green; `gh api
  repos/nathanramoscfa/weatherbot/branches/main/protection --jq
  .required_status_checks` names both `gate` and `phase-verify`; and `git
  ls-remote --tags origin v2.0.0-phase-1` shows the tag at the merge
  commit.
- **Operations:** the twice-weekly `replay-corpus.yml` is this phase's only
  scheduled surface; its health signal (the run status on `main`) and its
  alarm (GitHub's failure email) exist and were seen to fire through Step
  6's `simulate_failure` dispatch, whose run URL the QA findings record.
- **Security gate clean** (always the final criterion): the pre-commit
  security gate passed on this step's diff, and the `security` job and
  `phase-verify (01)` are green.
- **Phase closed, nothing carried.** Every finding recorded in
  `docs/phase01-qa-findings.md` has a destination (fixed, an issue
  number, or a named phase that owns it), the "Not in scope" section
  below is current, and no untracked item remains. Every step of this
  roadmap, this one included, reads `**Status:** Complete — PR #…` on
  `main` under a ✅ heading, the Summary Table's Status column and this
  roadmap's phase-level Status line say `Complete` under a ✅ title, and
  the project roadmap's Phase 1 entry (under a ✅ heading), its
  summary-table row, and its header status line say `Complete` — all
  landed in this step's PR. This step's final response ends with the
  line "Step 7 is complete. Phase 1 is complete. You can now move on to
  Phase 2." in place of the usual "Step 7 is complete. You can now move on
  to Step 8." — same Stage 6 rule: no "Follow-ups", no trailer.

---

## Post-Implementation Verification

Every V1–V7 check below runs **automatically in CI** on every push and
pull request, except these. The GitHub readbacks (V1.2, V1.3, V3.4,
V6.4), the roadmodel updater's dry run (V2.4), and the live recorder
smoke (V5.4) run in `--post` on the operator's Windows machine, because
they need admin rights the workflow token lacks, the operator's local
registry, or the network. The full replay corpus (V6.3) runs in its own
workflow — on a path trigger, twice a week, and on demand — rather than on
every pull request.

| Mode         | Workflow                                              | Runner           | Coverage                                                                 |
| ------------ | ----------------------------------------------------- | ---------------- | ------------------------------------------------------------------------ |
| `--fast`     | `phase-verify.yml` (matrix entry `"01"`)              | Ubuntu           | Static checks 1–50: V1.1, V2.1, V3.1, V4.1, V5.1, V6.1, V7.1–V7.3          |
| `--py`       | `ci.yml` (`lint`, `typecheck`, `test`, `package`)     | Ubuntu + Windows | V2.2, V2.3, V3.3, V4.2, V5.2, V5.3, V6.2                                  |
| `--security` | `ci.yml` `security` and `phase-verify.yml`            | Ubuntu           | V3.2, V7.4 (secret scan + SAST + dependency audit + personal-data check)  |
| `--corpus`   | `replay-corpus.yml` (path trigger, 2×/week, dispatch) | Ubuntu           | V6.3 (full cache fetch, checksum verify, `pytest -m corpus`)              |
| `--post`     | local, on the operator's machine                      | Windows          | V1.2, V1.3, V2.4, V3.4, V5.4, V6.4 + the full V-check sweep               |

Local invocations remain available for ad-hoc runs and pre-release
sweeps:

```bash
uv run python scripts/verify_phase01.py --post   # static + V1-V7 + post checks
```

`--post` is the canonical command to run before tagging
`v2.0.0-phase-1`.

Other modes:

```bash
uv run python scripts/verify_phase01.py --fast      # static only (CI-safe)
uv run python scripts/verify_phase01.py --py        # + lint, types, tests
uv run python scripts/verify_phase01.py --corpus    # + full corpus verify
uv run python scripts/verify_phase01.py --security  # the four-check gate
uv run python scripts/verify_phase01.py --all       # py + corpus + security
```

The script reports each V-check by id (V1.1, V2.1, ...) so a failure in
any workflow above maps directly to the corresponding row below.

### V1 — Freeze v1 and `main`

> **Automated in CI.** `phase-verify.yml` → V1.1; `--post` on the
> operator's machine → V1.2 and V1.3.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V1.1 | Static checks 1–6 all PASS (annotated tag at the release commit, changelog note, `main` wording). | `phase-verify.yml` runs `verify_phase01.py --fast` on every push/PR.       |
| V1.2 | GitHub reads back `main` as default, squash-only merges, delete-on-merge, and the protection payload. | `--post` (`gh api`, admin read).                                           |
| V1.3 | `v1.0.0` on `origin` peels to the release commit the sdist comparison proved.                  | `--post` (`git ls-remote --tags origin`).                                  |

### V2 — uv scaffold

> **Automated in CI.** `phase-verify.yml` → V2.1; `ci.yml` → V2.2 and
> V2.3; `--post` → V2.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V2.1 | Static checks 7–20 all PASS (packaging, skeleton, v1 gone, strict configs, guards, CI jobs).  | `phase-verify.yml --fast`.                                                 |
| V2.2 | `ruff check`, `ruff format --check`, `pyright`, `lint-imports`, and `pytest` pass.             | `ci.yml` `lint`, `typecheck`, `test` (`--py` locally).                     |
| V2.3 | The installed wheel's `weatherbot --version` prints `2.0.0.dev0` on Ubuntu and Windows.       | `ci.yml` `package` matrix.                                                 |
| V2.4 | The roadmodel updater's dry run resolves this project to `.venv` with no override.            | `--post`, local only.                                                      |

### V3 — Security gate

> **Automated in CI.** `phase-verify.yml` → V3.1; `ci.yml` → V3.2 and
> V3.3; `--post` → V3.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V3.1 | Static checks 21–30 all PASS (hooks pinned, checker and allowlist, CI security job, SHA pins, permissions, Dependabot, `SECURITY.md`, no secret patterns). | `phase-verify.yml --fast`.                                                 |
| V3.2 | gitleaks, bandit, pip-audit, and the personal-data check (`--all --ci`, `--self-test --ci`) are clean. | `ci.yml` `security` and `phase-verify.yml --security`.                     |
| V3.3 | `tests/scripts/test_check_personal_data.py` passes, including redaction and fail-closed cases. | `ci.yml` `test`.                                                           |
| V3.4 | `main` requires `gate` and `phase-verify`; Dependabot alerts and security updates and private reporting are on; the local denylist self-test passes. | `--post` (`gh api`; local denylist).                                       |

### V4 — Data-source register

> **Automated in CI.** `phase-verify.yml` → V4.1; `ci.yml` → V4.2.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V4.1 | Static checks 31–35 all PASS (register header, ids and dates, User-Agent, not-used sources, per-basin table). | `phase-verify.yml --fast`.                                                 |
| V4.2 | The register, `record_fixtures.SOURCES`, and the recorded service catalogs agree (`test_register.py`). | `ci.yml` `test`.                                                           |

### V5 — Fixture recorder and harvest

> **Automated in CI.** `phase-verify.yml` → V5.1; `ci.yml` → V5.2 and
> V5.3; `--post` → V5.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V5.1 | Static checks 36–41 all PASS (recorder, a capture per required id, harvested maps, NOTICE, contract tests, no `set-cookie`, no reports). | `phase-verify.yml --fast`.                                                 |
| V5.2 | Every capture matches its manifest: schema, checksum, format, no unlisted file.              | `ci.yml` `test` (`tests/contract/`).                                       |
| V5.3 | The fixture budget holds: recorded ≤ 25 MiB, replay subset ≤ 10 MiB, every stored file ≤ 5 MiB. | `ci.yml` `test` (`test_fixture_budget.py`).                                |
| V5.4 | A live recording of `nhc-current-storms` produces a valid manifest.                           | `--post` (`pytest -m live`, network).                                      |

### V6 — Replay corpus

> **Automated in CI.** `phase-verify.yml` → V6.1; `ci.yml` → V6.2;
> `replay-corpus.yml` → V6.3; `--post` → V6.4.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V6.1 | Static checks 42–46 all PASS (script commands, manifest storms, subset dirs, workflow, ignore rule). | `phase-verify.yml --fast`.                                                 |
| V6.2 | The committed subset's tests pass: manifest trace, advisory order, valid cones, advisory numbers. | `ci.yml` `test` (`tests/replay/`).                                         |
| V6.3 | The full cache fetches and verifies against the manifest, and the subset re-converts byte for byte. | `replay-corpus.yml` (`--corpus` locally).                                  |
| V6.4 | The latest `replay-corpus.yml` run on `main` is green, and the recorded `simulate_failure` run is red. | `--post` (`gh run list`, `gh run view`).                                   |

### V7 — CI integration + security

> **Automated in CI.** `phase-verify.yml` → V7.1 through V7.4 on every
> push/PR.

| ID   | Check                                                                                         | Automation                                                                 |
| ---- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| V7.1 | `verify_phase01.py --fast` exits 0 on Ubuntu CI.                                              | `phase-verify.yml` matrix entry `"01"`.                                    |
| V7.2 | `phase-verify.yml`'s matrix includes `"01"`.                                                   | `phase-verify.yml --fast` static check 50.                                 |
| V7.3 | All 50 static checks in `verify_phase01.py` pass.                                             | `phase-verify.yml --fast` records a pass only when every static check passed. |
| V7.4 | `verify_phase01.py --security` exits 0 (secret scan + SAST + dependency audit + personal-data check). | `phase-verify.yml` `--security` and `ci.yml` `security` on every push/PR.  |

---

## Summary Table

| Step | Scope                    | Model                    | Platform     | Reasoning dial      | Thinking | Conv | Status      |
| ---- | ------------------------ | ------------------------ | ------------ | ------------------- | -------- | ---- | ----------- |
| 1    | Freeze v1, `main`        | GPT-6.1 Sol              | Codex        | Intelligence Med    | --       | New  | Complete — PR #3 |
| 2    | uv scaffold              | Sonnet 5.5               | Claude Code  | Effort High         | On       | New  | Complete — PR #4 |
| 3    | Security gate            | Opus 5.5                 | Claude Code  | Effort XHigh        | On       | New  | Complete — PR #7 |
| 4    | Data-source register     | Opus 5.5                 | Claude Code  | Effort XHigh        | On       | New  | Complete — PR #13 |
| 5    | Fixture recorder         | Sonnet 5.5               | Claude Code  | Effort High         | On       | New  | Complete — PR #14 |
| 6    | Replay corpus            | GPT-6 Sol                | Codex        | Intelligence Med    | --       | New  | Not started |
| 7    | QA + verify_phase01.py   | GPT-6 Sol                | Codex        | Intelligence Med    | --       | New  | Not started |
| V1   | Freeze v1, `main`        | CI: phase-verify.yml     | --           | --                  | --       | --   | --          |
| V2   | uv scaffold              | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V3   | Security gate            | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V4   | Data-source register     | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V5   | Fixture recorder         | CI: ci.yml               | --           | --                  | --       | --   | --          |
| V6   | Replay corpus            | CI: replay-corpus.yml    | --           | --                  | --       | --   | --          |
| V7   | CI integration           | CI: phase-verify.yml     | --           | --                  | --       | --   | --          |

---

## Model selection blocks

```text
PROMPT: Step 1 — Freeze v1 and move to `main`
MODEL: GPT-6 Sol
BACKUP: Sonnet 5.5
PLATFORM: Codex
EFFORT: Medium
THINKING: On
CONVERSATION: New
RATIONALE: TASK: agentic repository operations — a verified tag, a branch rename, protection, and merge settings — with two short documentation edits. PICK: GPT-6 Sol is S-tier agentic (AA Intelligence Index 47.6), the adequate Codex pick while the Claude weekly pool reads tight. EFFORT: Medium fits a fixed, ordered sequence of outward actions whose risk is sequencing rather than reasoning depth.

PROMPT: Step 2 — uv scaffold replaces v1
MODEL: Sonnet 5.5
BACKUP: GPT-6 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding — a repository-wide v2 scaffold with strict tooling on two operating systems, High complexity by its cross-cutting scope. PICK: Sonnet 5.5 is S-tier coding (AA Intelligence Index 56.0) and leads the S-tier coding models on coverage. EFFORT: High fits cross-file strict-mode configuration of a known pattern; nothing novel earns Extra High, and one deliverable needs no workflow.

PROMPT: Step 3 — Security gate
MODEL: Opus 5.5
BACKUP: GPT-6 Sol
PLATFORM: Claude Code
EFFORT: XHigh
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a security-knowledge secondary — the fail-closed four-check gate, a personal-data checker, its CI mirror, and planted-value proofs. PICK: Opus 5.5 is S-tier in coding and knowledge (AA Intelligence Index 57.6), tied with Fable 5.1 and cheaper. EFFORT: XHigh fits High complexity verified across many files; Max is not needed because the design is already specified.

PROMPT: Step 4 — Data-source register
MODEL: Opus 5.5
BACKUP: GPT-6 Sol
PLATFORM: Claude Code
EFFORT: XHigh
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: knowledge — a grounded, live-verified register of every NOAA source, with dozens of agentic probes, High complexity. PICK: Opus 5.5 is S-tier knowledge (HLE 61.4%), the cheapest S-tier knowledge model in the catalog. EFFORT: XHigh is the ladder's High raised one rung for knowledge work with cross-cutting scope; each claim is checked against a live response.

PROMPT: Step 5 — Fixture recorder and harvest
MODEL: Sonnet 5.5
BACKUP: GPT-6 Sol
PLATFORM: Claude Code
EFFORT: High
THINKING: On
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding — a multi-source fixture recorder with manifests, a harvest, and contract tests, agentic secondary, High complexity. PICK: Sonnet 5.5 is S-tier coding (AA Intelligence Index 56.0), first among the S-tier coding models on coverage. EFFORT: High fits broad but fully specified work with no novel reasoning bottleneck to justify Extra High.

PROMPT: Step 6 — Replay corpus
MODEL: GPT-6 Sol
BACKUP: Sonnet 5.5
PLATFORM: Codex
EFFORT: Medium
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding — a bounded download, verify, and convert pipeline for four archived storms, Medium complexity. PICK: GPT-6 Sol is S-tier coding (AA Intelligence Index 47.6), adequate on the Codex pool while the Claude weekly pool reads tight. EFFORT: Medium matches a well-specified pipeline whose formats and archive layout the register already documents.

PROMPT: Step 7 — QA + verify_phase01.py
MODEL: GPT-6 Sol
BACKUP: Sonnet 5.5
PLATFORM: Codex
EFFORT: Medium
THINKING: On
CONVERSATION: New
RATIONALE: TASK: mechanical translation of this roadmap's acceptance criteria into a verification script, a workflow, and a findings rollup. PICK: known pattern, no novel reasoning — roadmodel's "standard implementation, multi-file changes, and roadmap execution" default, here GPT-6 Sol, S-tier coding (AA Intelligence Index 47.6). EFFORT: Medium fits enumerated checks whose content this roadmap already writes down.
```

---

## Not in scope (from product roadmap)

The project roadmap's Phase 1 section carries no "Not in scope" list;
these items follow from its phase boundaries and its §6 "Out of Scope":

- Parsing a payload into domain models, the source clients in
  `weatherbot.sources`, SQLite, and Alembic. Phase 2 builds them against
  this phase's fixtures, register, and User-Agent, and puts the shared
  domain models in `weatherbot.models`, added to the layers contract
  below both `sources` and `engine`.
- The engine, its thresholds, golden expectations, and
  `docs/ALERT-LADDER.md`. Phase 3 owns them, reading v1's ladder wording
  from the `v1.0.0` tag and loading this phase's replay corpus.
- The scheduler, change detection, notifications, and Task Scheduler
  registration. Phase 4.
- The frontend, npm, Dependabot's npm entry, and `eslint-plugin-security`.
  Phase 5 adds them with `frontend/`.
- Claude, `ANTHROPIC_API_KEY`, and any model call in the application.
  Phase 6.
- Radar, satellite, surge, and probability layers in the user interface.
  Phase 7; this phase only confirms the services and records their terms.
- A PyPI release, trusted publishing, and LAN mode. Phase 8.

Additionally not in scope for this phase:

- A manually triggered live-smoke CI job for the source clients. Phase 2
  adds it beside its clients; this phase's live test runs locally.
- Re-recording fixtures on a schedule. Re-recording happens on demand
  under the "Source drift" triage class; Phase 4's heartbeat and staleness
  rules watch the live sources.
- A basin with no active storm on Step 4's or Step 5's date. Its layer
  question stays open in `docs/DATA_SOURCES.md` with that date and is
  re-checked by re-running the recorder when a storm is active there,
  owned by the phase active at that time.
- The four forecast-cone graphics in the v1 reports. They are not a v2
  source, so they stay in the untracked reports.
- Recovering the 38 lost v1 responses. Only an operator's backup can
  restore them; Step 5 harvests them if one appears.
- Deleting the external environment that served roadmodel before Step 2,
  and v1's untracked runtime directories. Both are the operator's
  housekeeping once Phase 1 closes.

---

_This roadmap is the execution plan for Phase 1. Each step's
`**Status:**` line is flipped by that step's own PR (Status rule), so this
file on `main` is the phase's ledger — `grep -n '^\*\*Status:\*\*'`
reports progress. After all steps and verification pass, and every
finding has a destination, Phase 1 is complete — declared with the line
"Phase 1 is complete. You can now move on to Phase 2." and nothing after
it — and Phase 2 (Sources and persistence) inherits a protected `main`
with the required `gate` and `phase-verify` checks, the uv project and its
fail-closed security gate, the register's source ids, query parameters,
and User-Agent, a manifest-verified recorded fixture of every source to
write its contract tests against, and the replay corpus that Phase 3's
harness will load._
