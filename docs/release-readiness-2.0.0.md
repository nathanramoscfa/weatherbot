<!-- docs/release-readiness-2.0.0.md -->
# Weatherbot 2.0.0 — Release Readiness Record

This checklist tracks every readiness requirement for publishing Weatherbot
`2.0.0` to PyPI (Phase 9 Decision 13). Each item is filled with concrete
evidence by its owning step before the `v2.0.0` tag is cut in Step 7, and the
pull request whose merge commit `v2.0.0` tags links this document.

## Readiness checklist

| #  | Readiness item | Evidence | Owner | State |
| -- | -------------- | -------- | ----- | ----- |
| 1  | Tested dependency set (`uv.lock` upgraded, pywinrt 4 with desktop toast, capped stable majors, Python 3.13 & 3.15 CI on Ubuntu and Windows, Dependabot PRs disposed) | PR #129 (`d852d51`, 2026-11-28): `winrt-runtime>=4.2.1,<5` and projections `>=4!10.0.28000.2957,<5!0`; desktop toast passed and seen by operator (2026-11-28 04:40 UTC); 4,147 tests passed on 3.13 and 3.15 (coverage 98.85%); CI 25/25 green on Ubuntu & Windows; `tests/test_dependency_policy.py` passes; Dependabot #8, #31, #47, #107/#128, #114 disposed; issue #79 closed | Step 1 | Complete |
| 2  | Release pipeline, GitHub environments, tag ruleset, OIDC Trusted Publishers, and dry-run proof | Environments `testpypi` (`28869826909`) and `pypi` (`28869828511`) with required reviewer `nathanramoscfa`, self-review allowed, tag pattern `v*`; active tag ruleset `Protect release tags` (`28304687`) on `refs/tags/v*`; PyPI Owner (2FA), TestPyPI (2FA), and both Trusted Publishers confirmed by operator (2026-11-28); post-merge `release.yml` dry run and `install-canary.yml` dispatch URLs to be copied here in Step 5 | Step 2 / Step 5 | In progress |
| 3  | Personal-data scan of the repository tree with the operator's local denylist | Pending final pre-tag run of `uv run python scripts/check_personal_data.py --all` with the operator's local denylist | Step 7 | Open |
| 4  | Personal-data scan of the built wheel and sdist (built into a temporary directory and extracted before scanning, bypassing the 64-member zip bound) | Pending final pre-tag build into a temporary directory, extraction, and scan with the operator's local denylist (plus CI rules via `scripts/check_dist.py`) | Step 7 | Open |
| 5  | Gitleaks secret scan over the full Git history | Pending final pre-tag `gitleaks git --redact` scan over full history | Step 7 | Open |
| 6  | Dependency audits (`pip-audit --strict` over `uv.lock`, `npm audit --audit-level=high --omit=dev`, bundled-licence check) | Step 1 baseline clean (PR #129; #79 closed by minimatch 11.0.9); dev-only advisory #121 (`picomatch <= 4.0.7`) is absent from the shipped wheel; pending final pre-tag audit in Step 7 | Step 7 | Open |
| 7  | Every disclaimer surface tied to the test that proves it | Pending documentation & test audit matrix | Step 4 / Step 7 | Open |
| 8  | Documentation complete (README for PyPI with tag-pinned links, `docs/GUIDE.md`, generated `docs/CONFIGURATION.md`, `docs/ALWAYS-ON.md`, `docs/TROUBLESHOOTING.md`, `docs/MIGRATING.md`, finalized `AI.md`/`ALERT-LADDER.md`/`DATA_SOURCES.md`/`NOTIFICATIONS.md`, `SECURITY.md`, and demonstration screenshots) | Pending Step 4 documentation PR | Step 4 | Open |
| 9  | Every external source re-verified live by `live-smoke.yml` within 7 days of the `v2.0.0` tag | Pending `live-smoke.yml` run URL and date within 7 days of tag | Step 7 | Open |
| 10 | Synthetic demonstration scenarios (`AL802026`, `Hurricane Demo`) and test fixtures confirmed absent from both wheel and sdist | Automated gate added in `scripts/check_dist.py` (Step 2); pending final pre-tag verification on `2.0.0` artifacts | Step 7 | Open |
| 11 | Release candidate `2.0.0rc1` published to TestPyPI, post-publish smokes green on both runners, and soaked >= 24 hours on the operator's service (`doctor` passing, no stale heartbeat) | Pending Step 5 release run URL, TestPyPI verification, and >= 24h soak log | Step 5 | Open |
| 12 | LAN mode readiness gate (first non-loopback bind on operator's home network, phone loading dashboard & live updates via token prompt, refusals verified, startup warning logged, `doctor` web check green, `docs/LAN.md` marked supported) | Pending Step 3 implementation and Step 6 live rehearsal | Step 6 | Open |
| 13 | Rollback rehearsal (yank `2.0.0rc1` on TestPyPI, publish `2.0.0rc2` patch, roll operator service back and forward, every stage duration recorded) | Pending Step 6 rehearsal and measured durations | Step 6 | Open |
| 14 | Open issues and pull requests dispositioned | Pending final Step 7 inventory (tracking open issues #33, #95, #121, #125 and stale PR #120) | Step 7 | Open |
| 15 | Post-release install health signal (`install-canary.yml` armed and proved; GitHub 60-day schedule-inactivity disable limit documented in `docs/RELEASING.md`) | Workflow added in Step 2; armed and proved with real + simulated-failure runs after `2.0.0` publishes | Step 7 | Open |

## Operator sign-off

- **Status:** Pending Step 7 readiness review.
- **Approved by:** _TBD (Step 7)_
- **Date:** _TBD (Step 7)_
- **Tagging PR:** _TBD (Step 7)_
