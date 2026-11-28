# Phase 9 Roadmap — Release 2.0

**Status:** In progress

## Overview

Phase 9 publishes Weatherbot 2.0.0 and opens the one widening the design allows.
Phases 1 to 8 built a local application that nobody outside this checkout can
install: the version still reads `2.0.0.dev0`, PyPI's newest release is the
retired 1.0.0 of September 2025, no workflow can publish, the README teaches `uv
run` from a checkout and links its documents by paths PyPI cannot resolve, and
the web server refuses every address but loopback. This phase makes the package
something a stranger can install and trust: a dependency set that a clean
install resolves to exactly what CI tested, on every Python a clean install can
pick; a tag-triggered pipeline that builds once, publishes through OIDC trusted
publishing behind two human gates, and then installs what it published on clean
Windows and Ubuntu runners; documentation written for someone who installed from
PyPI; and an optional LAN mode, behind a token, so the operator's phone on the
home network can open the dashboard. It moves no level and changes nothing the
engine decides: no ladder rule, threshold, golden, change kind, notification
kind, prompt, model, or AI product changes, and no database revision is written.
The two irreversible cutovers — a public 2.0.0 and the first bind to a
non-loopback address — each wait for their own readiness gate and the operator's
yes, and release candidates rehearse the whole path on TestPyPI first, a yank
and a patch included. It is one phase because every step ends in the same
artifact, and eight steps because each irreversible action has to stand alone.

The phase lands in 8 layers:

1. **What ships is what CI tests** — pywinrt moves to version 4 (the locked
   3.2.1 has no wheel for the current Python, 3.15, and a fresh install from
   PyPI already takes 4 without a test ever importing it), the lock is upgraded
   so the tested set is the set a clean install resolves, every runtime
   dependency at 1.0 or later is capped below its next major, the test suite
   runs at Python 3.13 and 3.15 on both runners, the classifiers declare 3.13 to
   3.15, and every open dependency pull request is merged, superseded, or closed
   with its reason. `README.md`'s status names Phase 9 in progress and Phase 8's
   check 52 moves to its tag. The phase flips to In progress.
2. **The release pipeline** — one version source, set by
   `scripts/set_version.py` and held by `tests/test_release_metadata.py`;
   `scripts/check_dist.py`, the allowlist every wheel and sdist must pass;
   `.github/workflows/release.yml`, which builds once from a tag on `main`,
   installs the built wheel on clean runners, publishes through OIDC from the
   protected `testpypi` or `pypi` environment after the operator's approval,
   installs what it published, and opens the GitHub Release with the notes, the
   files, and the replay corpus archive; the two environments, both trusted
   publishers, a ruleset that keeps release tags where they are,
   `docs/RELEASING.md`, the readiness record, the weekly install canary, and a
   dry run that publishes nothing.
3. **LAN mode** — `[web] lan`, `lan_address`, and `lan_hosts` add a second
   listener on one LAN address beside the unchanged loopback one; every API
   request that is not loopback-to-loopback carries the `WEATHERBOT_WEB_TOKEN`
   bearer token or the session cookie the SPA's token prompt obtains; failed
   tokens, LAN request rates, and LAN connections are limited; the LAN listener
   refuses to start without a usable token and address while loopback serves on,
   and every LAN start warns; `doctor`, `/api/health`, and the app shell's
   header say LAN mode is on; and `docs/LAN.md` is written, marked not yet
   supported.
4. **Documentation** — the README as the PyPI page, its links pinned to the
   release tag; `docs/GUIDE.md`, from install to every page and command;
   `docs/CONFIGURATION.md`, generated from the settings model with a `--check`;
   always-on setup, troubleshooting, the v1 to v2 migration note, the AI
   features and their cost, the ladder and the register finalized,
   `SECURITY.md`'s supported versions, and screenshots of the demonstration
   scenarios captured by a spec and committed.
5. **The release candidate** — `2.0.0rc1`, tagged with the operator's yes,
   published to TestPyPI after the operator approves the deployment, installed
   from the index on both runners, its TestPyPI page read back, and installed on
   the operator's service from the hash-checked wheel to soak.
6. **The readiness rehearsals** — the first non-loopback bind, on the operator's
   own network with the operator's phone, after which `docs/LAN.md` is marked
   supported; then yank and patch: rc1 yanked on TestPyPI, `2.0.0rc2` published
   as the patch, the operator's service rolled back and forward, every duration
   recorded.
7. **2.0.0** — the readiness record completed and signed by the operator, the
   version and the changelog set, `v2.0.0` tagged with the operator's yes,
   published to PyPI after the operator's approval, installed fresh on both
   runners, the operator's service upgraded from PyPI, and the install canary
   armed.
8. **QA + `verify_phase09.py`** — `scripts/verify_phase09.py` (`--fast`, `--py`,
   `--node`, `--ui`, `--live`, `--security`, `--all`, `--post`),
   `docs/phase09-qa-findings.md`, and matrix entry `"09"` beside `"01"` to
   `"08"` in `phase-verify.yml`; Phase 9 closed in this roadmap and the project
   roadmap.

The ship test for Phase 9 is straightforward: `uv tool install
weatherbot==2.0.0` and `pip install weatherbot==2.0.0` succeed on clean
`windows-latest` and `ubuntu-latest` runners on Python 3.13 and on the newest
CPython, `weatherbot --version` prints `2.0.0`, `weatherbot doctor --offline`
exits 0, and `weatherbot serve` answers `/api/health` with `2.0.0` and serves
the built dashboard with no Node, key, topic, or corpus; PyPI's two files are
byte-identical to the GitHub Release's and carry trusted-publishing
attestations; the test suite passes on Python 3.13 and 3.15 on both runners,
against a lock that a clean install resolves to; LAN mode refuses to start
without a usable token, rejects an unauthenticated non-loopback request,
rate-limits failed tokens, and has served the operator's phone on the operator's
network; the yank-and-patch rehearsal is recorded with its durations; the
readiness record is complete, signed by the operator, and linked from the pull
request whose merge commit `v2.0.0` tags; the operator's service reports `2.0.0`
installed from PyPI; Phases 1 to 8's verification still pass; and
`scripts/verify_phase09.py --fast` exits 0 on Ubuntu CI with `phase-verify (01)`
to `(09)` green.

**Pre-requisite:** Phase 8 closed on 2026-11-18 (PR #123; `v2.0.0-phase-8`),
with the operator's sign-off of 2026-11-17 that the web app is release-ready;
its pages are what the documentation pictures and the fresh-install smoke opens,
and its demonstration scenarios are what the screenshots show. Phase 5's
packaging (the SPA built into the wheel, the `package` job's install smoke,
`scripts/smoke_installed_web.py`) and its loopback guards (`web/guards.py`,
`web/server.py`) are what the pipeline and LAN mode extend. Phase 4's Task
Scheduler setup is the always-on guide's subject, Phase 6's credential handling
the AI guide's, and Phase 7's settings, retention, and ntfy channel the
configuration reference's subject and the LAN token's precedent: a secret read
from the environment only, whose presence `doctor` reports and whose value the
log redacts. The planning kit is roadmodel 0.2.116: its export equals the
committed `planning/`, and this roadmap's pull request pins it in `uv.lock`.

**Dependency:** No phase follows: the project roadmap ends at Phase 9. What
inherits this phase's work is the 2.0.x line — fixes, dependency updates, and
the issues still open (#33, #95, #121) — released through the pipeline and
the runbook this phase leaves, under the install canary's watch.

**Design rationale (decisions and clarifications of the brief and the project
roadmap).** Seventeen decisions, each made against measured, probed, or recorded
evidence while this roadmap was written (2026-11-18) and checked against the
code by an independent review of the draft; the steps cite them by number. The
project roadmap records each one that changes it, in this roadmap's own pull
request. Step agents treat them as settled spec unless the operator changes
them.

1. *Nothing the engine decides changes, and the application gains no outbound
   host.* No ladder rule, threshold, golden, change kind, cycle trigger,
   notification kind, prompt, model, or AI product changes, so Phase 3's
   digest-pinned replay goldens, Phase 4's approved notification goldens, and
   Phase 7's check 20 (`services/policy.py` and `tests/golden` equal to
   `v2.0.0-phase-6`) stay exact. No Alembic revision is written: the operator's
   database stays at `0010`, and every rollback inside the release series is
   migration-free. PyPI and TestPyPI are reached by the release workflow, the
   install canary, and the operator's installs, never by the application. The
   one new inbound path is LAN mode, off by default (Decision 9).
2. *What a clean install resolves is what CI tests, on every Python a clean
   install can pick.* Measured on 2026-11-18: the lock pins pywinrt 3.2.1, whose
   five Windows packages ship wheels for CPython 3.13 and 3.14 only, while
   CPython 3.15.2 is current; uv 0.12.15 offers managed downloads up to 3.14.7,
   a newer uv offers 3.15, and `uv tool install` on a machine without a matching
   Python downloads the newest it knows — so a clean Windows install on 3.15
   would try to build pywinrt 3.2.1 from source. Meanwhile the wheel's
   dependency floors are unbounded (`winrt-runtime>=3.2.1`), so a fresh install
   from PyPI already resolves pywinrt 4 — `winrt-runtime` 4.2.0 (published
   2026-11-17, wheels for 3.11 to 3.15) and the four projection packages, now
   pure Python at the epoch version `4!10.0.28000.2957` — which no test has ever
   imported: the test suite runs against the lock, the `package` job's smoke
   installs the wheel's newest dependencies without importing pywinrt, and
   `doctor`'s toast check reads stored deliveries. In the lock, only `pyyaml`
   (development tooling) also lacks a 3.15 wheel. So Step 1 moves to pywinrt 4
   and proves the toast channel on it with a real toast on the operator's
   desktop (with a yes); upgrades the lock so CI tests what a clean install
   takes on release day; runs the test suite at 3.13 (the floor) and 3.15 (the
   newest) on both runners; declares 3.13 to 3.15 in the classifiers; and caps
   every runtime dependency at 1.0 or later below its next major (as
   `pydantic<3` and `sqlalchemy<3` already are), so a future major cannot break
   a fresh install of 2.0.0. A package whose upgrade moves a replay or
   notification golden is held at its current version, with the reason recorded,
   because no golden changes in this phase (Decision 1). Dependencies below 1.0
   (FastAPI, Typer, uvicorn, httpx, tomlkit, defusedxml) keep floors only, and
   the install canary (Decision 8) is what notices when one breaks a fresh
   install. `requires-python` stays `>=3.13` with no upper bound, because a cap
   would send pip on a newer Python back to 1.0.0.
3. *One version, set by one command, checked wherever it appears.* The version
   lives in `pyproject.toml`; `uv.lock` records it, `docs/api/openapi.json` and
   `frontend/src/test/fixtures/health.json` carry it, and `tests/test_cli.py`,
   `README.md`, and `CONTRIBUTING.md` quote it today. Step 2 adds
   `scripts/set_version.py <version>`, which sets it through `uv version`,
   regenerates the OpenAPI document, the frontend's generated types, and the API
   fixtures, and rewrites the README's tag-pinned links (Decision 11);
   `tests/test_release_metadata.py` fails when any copy disagrees, when the
   version is not a PEP 440 version, or when a release version carries a
   `Development Status` classifier below Beta; and no test compares the
   installed version with a literal, nor does a document quote it (tests that
   write a synthetic `pyproject.toml` for a fake checkout keep theirs). A
   release tag must equal `v` plus the version, and the release workflow refuses
   any other.
4. *Every published file is built once, from a tag on `main`, and installed
   again after it is published.* `.github/workflows/release.yml` runs on tags
   matching `v[0-9]+.[0-9]+.[0-9]+` or `v[0-9]+.[0-9]+.[0-9]+rc[0-9]+` — the
   phase tags (`v2.0.0-phase-N`) match neither — and on `workflow_dispatch` as a
   dry run that publishes nothing. Its `build` job checks that the tag equals
   the version and that the tagged commit is on `origin/main`, runs `npm ci`,
   the frontend build, `uv build`, and `scripts/check_dist.py`, and uploads
   `dist/` and the corpus archive; `smoke-built` installs that wheel, with no
   lock, on clean `windows-latest` and `ubuntu-latest` runners at Python 3.13
   and at the newest CPython, through `scripts/release_smoke.py`; only then does
   `publish-testpypi` (release candidates) or `publish-pypi` (releases) run, in
   its environment, with `id-token: write` as its only permission, through
   `pypa/gh-action-pypi-publish` pinned to a full commit SHA, which uploads with
   OIDC and generates PEP 740 attestations; `smoke-published`, which runs when
   either publish job succeeded (a job that merely needs a skipped job is
   skipped too), installs from the index on both runners; and `github-release`,
   the only job with `contents: write`, creates the GitHub Release with the
   version's changelog section, the two files, and the corpus archive (Decision
   7), marked pre-release for a candidate. The workflow's default is
   `permissions: {}`, no job reads a repository secret, every action is pinned
   to a full commit SHA, it runs on GitHub-hosted runners only, and its
   concurrency group never cancels a release in progress.
5. *Two human gates stand before every upload, and release tags cannot move.* An
   agent pushes a release tag only after the operator's explicit yes
   (AskUserQuestion), and each publish job waits in its environment for the
   operator's own approval in GitHub's interface: an agent never approves a
   deployment through the API — a rule rather than a lock, since an agent works
   with the operator's own token — so every upload has a human click behind it.
   The `testpypi` and `pypi` environments name the operator as their required
   reviewer and admit tags only, so no branch can deploy (the workflow's own tag
   filter is what limits a run to release tags), and they allow self-review,
   because the operator both pushes and approves. A repository ruleset forbids
   deleting, updating, or force-moving a release tag, so a published version's
   tag always names the commit that built it. PyPI's `weatherbot` project exists
   (1.0.0, uploaded 2025-09-29), so its trusted publisher is added to that
   project; TestPyPI has none (its JSON API and simple index answer 404 for
   `weatherbot`), so a pending publisher creates it at the first upload. The
   operator configures both in their own browser with the values Step 2 hands
   over, and Step 2's kickoff confirms that the operator can manage the PyPI
   project and holds a TestPyPI account, because a lost account would block the
   release and must be found out first.
6. *TestPyPI rehearses everything; PyPI receives only 2.0.0.* `2.0.0rc1` and
   `2.0.0rc2` go to TestPyPI only, and no pre-release is ever uploaded to PyPI.
   TestPyPI hosts strangers' copies of common package names, so no smoke
   resolves a dependency through it: `scripts/release_smoke.py` downloads the
   exact wheel from the URL TestPyPI's JSON API lists, checks its SHA-256
   against the workflow's build, and installs that file with every dependency
   from PyPI. Step 6's rehearsal yanks rc1 and publishes rc2 as the patch,
   timing each stage, which replaces the project roadmap's "Under an hour (TBD
   once rehearsed)" with a measured figure.
7. *The replay corpus ships beside the release, not in it.* Phase 7's Decision
   17 kept the corpus a directory the operator names and left shipping it to the
   release. The committed subset is 1,710 files holding 7.9 MB, self-describing
   (`corpus-manifest.json` lists every file's size and SHA-256, which
   `ReplayCorpus` checks file by file as it reads) and public NOAA data
   (`NOTICE.md`). Bundled, it would make the 862 KB wheel ten times larger for a
   demonstration; downloaded by the application, it would add an outbound host.
   So the release workflow zips `tests/fixtures/replay` into
   `weatherbot-replay-corpus-<version>.zip` with a `.sha256` file, both attached
   to the GitHub Release, and the user guide says how to download, check, unzip,
   and name it in `[web] corpus` or `serve --corpus`. The package stays
   corpus-free.
8. *The published package has a health signal.*
   `.github/workflows/install-canary.yml` runs weekly and on dispatch: on clean
   `windows-latest` and `ubuntu-latest` runners it runs `uv tool install
   weatherbot` with nothing pinned — a new user's exact path — and
   `scripts/release_smoke.py`. A failure, such as a dependency's new release
   breaking a fresh install, reaches the operator as GitHub's failure email for
   a scheduled run, and its `simulate_failure` input proves that alarm, as
   `replay-corpus.yml`'s does; a simulated run carries its own `run-name`, so a
   probe can tell the latest real run from a rehearsed failure. GitHub disables
   a public repository's schedules after 60 days without activity, which would
   silence the signal, so `docs/RELEASING.md` says how to see and re-enable it
   and the readiness record names the limit. Step 2 adds it, reporting success
   without installing while PyPI's newest release is below 2.0.0; Step 7 arms
   and proves it.
9. *LAN mode adds an authenticated listener; loopback does not change.* The
   brief's D8 allows LAN access "behind a token" for one reason: a phone on the
   home network. `[web] lan` (false by default) turns it on; `[web] lan_address`
   names one specific IPv4 or IPv6 address of this machine, stored in its
   canonical form — the wildcards `0.0.0.0` and `::` are refused, because they
   would also listen on a café's Wi-Fi or a VPN interface; and `[web] lan_hosts`
   lists the extra `Host` names the LAN listener answers, such as the machine's
   name, never `*`. Their overrides are `WEATHERBOT_WEB_LAN`,
   `WEATHERBOT_WEB_LAN_ADDRESS`, and `WEATHERBOT_WEB_LAN_HOSTS`. The loopback
   listener keeps its address, port, and behaviour; the LAN listener is a second
   socket on the same port. The token is `WEATHERBOT_WEB_TOKEN`, read from the
   environment only, like the ntfy topic: at least 32 characters
   (`secrets.token_urlsafe(24)`), and never in `weatherbot.toml`, a log line, a
   response, `/api/settings`, an error, the database, or a URL's query. A
   request is exempt only when both its client and its listening address parse
   as loopback; every other request to the API (`/api/…`), one whose addresses
   are missing or unparseable included, must present `Authorization: Bearer
   <token>` or a valid session cookie, while the built page and its static
   files, which hold no data and ship in the wheel, load without credentials so
   the token prompt can appear; `POST /api/session` takes the token as JSON and
   answers with an `HttpOnly; SameSite=Strict; Path=/` cookie holding an
   expiring HMAC-SHA-256 value keyed by the token, so changing the token revokes
   every session, and every comparison is constant-time. The SPA's token prompt
   appears on a 401 and posts the token once; no link carries the token, because
   a URL holding it, even in its fragment, stays in the phone's history and can
   sync. Failed bearer tokens and failed `POST /api/session` attempts are
   limited per peer address and in total (429 with `Retry-After`), while a
   missing, expired, or stale cookie only answers 401 and is expired, so a phone
   holding an old cookie is never locked out; a LAN peer's request rate and the
   LAN listener's concurrent connections are capped too, so the network cannot
   starve the loopback listener, with a test proving that a dashboard load and
   its event stream stay well inside the limit. When LAN mode is on and the
   token or the address is missing, short, loopback, or a wildcard, the LAN
   listener refuses to start: `serve` logs each reason at ERROR, never a value,
   and keeps monitoring and serving loopback, because a configuration mistake
   must never stop the hurricane monitor, and `/api/health` and `doctor`'s `web`
   check report it; the same happens when the LAN socket cannot bind (the
   address has left the machine). Every start with LAN on prints and logs a
   warning: the address, that the traffic is unencrypted HTTP, that anyone on
   the network who holds the token can read the locations, change settings,
   spend the AI allowance, and prune history, that LAN mode belongs on a trusted
   home network only, and how to turn it off. `/api/health` reports `lan` (on or
   off, the address, whether it listens, and why not, never the token), and the
   app shell's header shows a LAN chip. Every existing guard stays: the host
   allowlist, now per listener — `ALLOWED_HOSTS` (unchanged) on the loopback
   socket, only `lan_address` and `lan_hosts` on the LAN socket, so a spoofable
   LAN name never reaches the unauthenticated loopback API — the fetch-metadata
   and same-origin write guard, tightened so a cookie-authenticated LAN write
   must carry `Sec-Fetch-Site: same-origin` (with a `SameSite=Strict` cookie,
   the CSRF defence), JSON-only writes, the CSP and its nonce (`CSP_SUFFIX`
   stays exact), no cross-origin read, `proxy_headers=False` (so no header can
   claim a loopback peer), and `limit_concurrency`. Browser notifications need a
   secure context, which `http://<lan address>` is not, so `notify.ts` reports
   them unavailable there and the guide points the phone to ntfy. `[web]` stays
   out of `EDITABLE` (Phase 7's check 25). No package is added: `hmac` and
   `secrets` are standard library, and the limiter is a few dozen lines of its
   own. TLS is not in this release (Not in scope).
10. *LAN mode is supported only after it has served the operator's phone.* The
    first non-loopback bind is one of the project roadmap's two irreversible
    cutovers. Step 3 ships LAN mode with `docs/LAN.md` marked "not yet
    supported"; Step 6 runs its readiness gate on the operator's own network
    with a yes before every action: a token the operator generates and sets
    without it ever crossing the chat; a Windows Defender Firewall rule for the
    Private profile and the port only; the operator's phone loading the
    dashboard and its live updates through the token prompt; the refusals proved
    against the LAN address (no token, a wrong token rate-limited, a foreign
    `Host`); the startup warning in the log; and `doctor`'s `web` check. Only
    then is the guide marked supported. Whether LAN mode stays on afterwards is
    the operator's choice, recorded.
11. *The documentation is written for someone who installed from PyPI.* The
    README is the PyPI page: what Weatherbot is and is not, one screenshot, the
    install (`uv tool install weatherbot`, which fetches a Python 3.13 or later
    when the machine has none; pipx; pip in a virtual environment), a quick
    start, the disclaimer, and an index of the guides. Every link in it is
    absolute and pinned to the version's tag
    (`https://github.com/nathanramoscfa/weatherbot/blob/v<version>/…`), because
    PyPI resolves no relative link, and `scripts/set_version.py` rewrites them.
    `docs/GUIDE.md` runs from install to uninstall: first run, every page, every
    command, notifications, AI, replay, the report, settings, history, LAN mode,
    and upgrading. `docs/CONFIGURATION.md` is generated from `Settings`,
    `ENVIRONMENT_OVERRIDES`, and `EDITABLE` by
    `scripts/export_config_reference.py`, whose `--check` runs in CI, so no key
    is undocumented or stale. Always-on setup (`docs/ALWAYS-ON.md`),
    troubleshooting (`docs/TROUBLESHOOTING.md`), the migration note
    (`docs/MIGRATING.md`), and the LAN guide are pages of their own;
    `docs/AI.md`, `docs/ALERT-LADDER.md`, `docs/DATA_SOURCES.md`, and
    `docs/NOTIFICATIONS.md` are read against the installed product and corrected
    wherever they assume a checkout. Tests hold the guide to every Typer command
    and every setting, and every relative link in tracked Markdown to a tracked
    file.
12. *Screenshots are documentation now, so a few are committed.* Phase 8's
    Decision 18 kept its 240 dogfood renders out of the repository; the release
    documentation, "and screenshots for it", is what Phase 8 handed to this
    phase. `frontend/docs-capture/capture.spec.ts`, under its own
    `frontend/playwright.docs.config.ts` and run by `npm --prefix frontend run
    docs:screenshots` (the default configuration's `/@idle|@dogfood/` is pinned
    by Phase 8's check 46, so it is never edited), captures a fixed set — the
    dashboard, the map, replay, the Storms page, and Settings — from the
    scenario servers at 1280×800 in light, plus the dashboard in dark, into
    `docs/images/` as PNG files of at most 300 KB each and 2 MB in all. They
    show only the two public landmarks and Hurricane Demo, and every caption
    says the storm is a demonstration.
13. *The readiness record is evidence, signed by the operator, and the pull
    request that tags the release links it.* `docs/release-readiness-2.0.0.md`
    starts in Step 2 with every item open, and each later step fills its own
    rows: the personal-data scan of the tree with the operator's local denylist
    and of the built wheel and sdist (both files built into a temporary
    directory, because the checkout's `dist/` still holds version 1's files, and
    extracted before the scan, because the checker refuses an archive of more
    than 64 members and the wheel holds 186); gitleaks over the full history;
    the dependency audits (`pip-audit --strict` over the lock, `npm audit
    --omit=dev`, the bundled-licence check), with the development-only
    advisory (#121; Step 1's lock closed #79) named as not shipped; each
    disclaimer surface tied to the test that proves it; the documentation
    complete; every source re-verified live by `live-smoke.yml` within seven
    days of the tag; the synthetic scenarios and recordings confirmed absent
    from both files; each release candidate's smokes and its soak on the
    operator's service (24 hours or more, `doctor` passing, no stale
    heartbeat); the LAN gate; the rollback
    rehearsal and its durations; every open issue and pull request with its
    disposition; and the operator's sign-off with its date.
14. *Phase 9's own checks read the release at its tag.* `v2.0.0` is this phase's
    milestone, as the project roadmap's "Release & tagging" table already says:
    it peels to Step 7's merge commit, the source of the published files.
    `verify_phase09.py` reads every release fact that later maintenance may
    change — the version, the README, the changelog, the classifiers — at that
    tag, so a 2.0.1 never turns `phase-verify (09)` red, and no `v2.0.0-phase-9`
    tag is made. Step 8 lands after the release and changes nothing that ships.
15. *The earlier phases' checks stay green, with three planned conversions, and
    three version checks become version-agnostic.* An audit of all eight
    verifiers and their pinned tests against everything this phase changes
    (2026-11-18; the table under "Verification surfaces") found that most checks
    read by inclusion — runner names in `ci.yml`'s jobs, paths in the OpenAPI
    document, entries in the phase matrix, prefixes such as `starlette>=` — and
    stay green as this phase grows them. Three are exact and convert, each in
    the pull request that first changes what it reads: Phase 8's check 52 (the
    README's `## Status` names Phase 8 complete and Phase 9 next) reads
    `tagged("README.md", tag=PHASE_8_TAG)` from Step 1; Phase 6's check 1 (the
    exact requirement string `anthropic>=2.3.0`) reads its anthropic clause at
    `v2.0.0-phase-6` from Step 1, which caps anthropic below 3; and Phase 8's
    check 54 (`### The dashboard` names `LocationSwitcher`, `MapPanels`, `replay
    workbench`, and `Settings tabs`) reads at `v2.0.0-phase-8` from Step 4,
    whose README describes the dashboard in a reader's words. Three version
    checks fail on the first version bump unless Step 2 changes them:
    `tests/test_cli.py` compares `__version__` with the literal `2.0.0.dev0`;
    `tests/contract/test_recorded_fixtures.py` requires every recorded
    manifest's `user_agent` to equal the current `USER_AGENT`, which embeds the
    version, while `tests/contract/test_register.py` ties the register's
    User-Agent block to it; and `scripts/fetch_replay_corpus.py`'s
    `load_manifest` refuses `tests/fixtures/replay/corpus-manifest.json` unless
    its `user_agent` is the current one, which breaks `tests/replay/` and
    `replay-corpus.yml`, whose latest run on `main` Phase 1's `--post` reads. So
    every manifest, which records what was sent, is checked against the
    User-Agent's shape with any PEP 440 version and never rewritten (the corpus
    manifest's hash keys the replay cache), and `scripts/set_version.py`
    rewrites the register's block. Phase 4's `--post` reads `ci.yml`'s job names
    `test (ubuntu-latest)` and `test (windows-latest)`, so Step 1's Python 3.13
    entries keep exactly those names. Literal pins stay literal:
    `requires-python = ">=3.13"` (Phase 1's check 7); `CHANGELOG.md`'s one `##
    [Unreleased]`, its `## [1.0.0] - 2025-09-29`, "weatherbot==1.0.0", "v1.0.0",
    "retired", `### Phase 7 — Depth`, and `### Phase 8 — UI/UX redesign and
    visual dogfooding`; the README's `## Commands` heading and section naming
    `weatherbot status`, `replay`, `locations evacuation`, `brief`, `ask`,
    `prune`, `report`, and `--place`, its `### The dashboard` heading,
    "DISCLAIMER.md", and "v1.0.0", and never the words "global coverage";
    `docs/ALERT-LADDER.md`'s three generated blocks and disclaimer link;
    `docs/AI.md`'s, `docs/NOTIFICATIONS.md`'s, and `docs/DESIGN.md`'s pinned
    headings and recorded figures; the register's header row, per-basin table,
    `## Not used` section, and ISO dates; `EDITABLE`'s 12 keys,
    `ALLOWED_HOSTS`'s exact tuple, `ENVIRONMENT_OVERRIDES` as a literal dict,
    `server.py`'s `EmbeddedUvicornServer`, `capture_signals`,
    `SO_EXCLUSIVEADDRUSE`, and `timeout_graceful_shutdown`, `toast.py`'s names
    and its lazy pywinrt import, no settings field named with "token" or
    "topic", `logs.py`'s secret literals, `CSP_SUFFIX`, the frontend's package
    names and leaflet's exact 1.x pin, `NAV_ITEMS`, the twelve map layers, and
    `QUERY_KEYS`; and `playwright.config.ts`'s `/@idle|@dogfood/`, which is why
    the documentation screenshots run under their own configuration (Decision
    12). Every new workflow pins each `uses:` to a full SHA followed by a `#
    vX.Y.Z` comment (Phase 1's pin check), declares a top-level `permissions:`,
    and has no `pull_request_target`; no image is tracked under `frontend/`
    (Phase 8's check 49); and the new documents avoid version 1's deleted paths,
    which include `docs/configuration.md`, `docs/troubleshooting.md`, and
    `docs/user-guide.md` (Phase 1's check 10 compares exact paths, so the
    repository's upper-case names pass). No check is added to an older script,
    because each phase's `--post` pins the previous phase's total: Phase 9's
    must assert 98.
16. *The operator's machine is touched only with a yes.* Step 1 shows one real
    toast on the operator's desktop; Step 5 installs the release candidate on
    the operator's service; Step 6 binds the first LAN address and rolls the
    service back and forward; Step 7 upgrades it from PyPI; Step 8's `--post`
    runs the nested phases' desktop tests (real toasts and a Task Scheduler
    probe) and `simulate_advisory.py`. Each deploy follows one recipe, away from
    HH:25 (when `\Weatherbot\check` may start `serve`): `schtasks /End /TN
    \Weatherbot\serve`, the install (`uv tool install --reinstall` of the
    hash-checked candidate wheel, or of `weatherbot==2.0.0` from PyPI),
    `schtasks /Run`, then `/api/health` and `doctor --offline --json` read back.
    An agent hands the operator a command to run rather than asking for a value:
    the LAN token, the PyPI and TestPyPI accounts, and the Anthropic credential
    never cross the chat, a pull request, a log, or a fixture. No step reads,
    prints, or quotes the operator's coordinates or places. The operator often
    reaches this machine from another computer, where a dialog on the Windows
    desktop may never be seen, so an agent that needs the operator to act states
    the steps in the chat first, then asks.
17. *Version 1 is retired on PyPI too, with the operator's yes.* 1.0.0 declares
    `Requires-Python >=3.11`, so once 2.0.0 is out, `pip install weatherbot` on
    Python 3.11 or 3.12 silently installs the retired version and its "global
    coverage" claims. Yanking 1.0.0 (PEP 592) keeps `pip install
    weatherbot==1.0.0` working, as the README promises, while an unpinned
    install on an older Python fails with pip's note that 2.0.0 needs Python
    3.13. Step 7 recommends it and yanks only with the operator's yes, after
    2.0.0 is live; the migration note says the same either way.

**Branch strategy.** Every step in this phase lands on its own short-lived
feature branch (`feature/phase09-step<M>-<slug>`), opens a pull request against
`main`, waits for the project's CI workflow to go green, and squash-merges with
a Conventional Commits subject line. Direct pushes to `main` are blocked by
branch protection. See the project roadmap's "Branch management strategy" for
the canonical naming convention, PR rules, and release tagging — this paragraph
confirms those rules apply unchanged within this phase. Per-step branches are
listed on each step header below as `**Branch:**` so reviewers can map commits
1:1 to the step they implement. A release tag (`v2.0.0rc1`, `v2.0.0rc2`,
`v2.0.0`) is pushed only on a merge commit of `main`, after its step's pull
request has merged and the operator has said yes (Decision 5); a tag is never
pushed from a step branch.

**Branch-first execution rule.** The very first action of every step — before
reading any files, before running any tool, before drafting any change — is to
check out the branch named in that step's `**Branch:**` line:

```sh
git checkout -b feature/phase09-step<M>-<slug>
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
feature/phase09-step<M>-<slug> <worktree-path> origin/main`, the worktree is
bootstrapped before any test or build (`uv sync` and `npm ci` in its `frontend/`
— a worktree has none of the primary tree's untracked state, such as `.venv`,
`frontend/node_modules`, the built interface, or the replay cache, and it must
never borrow the primary tree's `.venv`), the Stage 4 merge runs from the
primary tree, and Stage 5 removes the worktree BEFORE pruning the branch.
Undeclared parallelism is a lifecycle violation, not a shortcut. Worktree
location for this project: git-ignored `.worktrees/<branch-slug>/` inside the
repository, matching the project roadmap.

**Security-first execution rule.** Security is not a phase — it is a gate on
every commit of every step. Before each `git commit`, the step's work must pass
the local, fail-closed security gate: secret/personal-data scan clean, SAST
clean, dependency audit clean, and a diff review confirming no sensitive data
(the operator's coordinates, address, typed place, or LAN address, a credential,
a token, an ntfy topic) and no new insecure pattern (injection, a subprocess
built from a shell string, unsafe deserialization, a path read outside the
directory it names, markup built from text, a `style=` attribute, a new outbound
host in the application, a coordinate or AI text in the browser's console, a key
or token in a fixture, a response readable from another origin, a state-changing
request a cross-site page could send). This phase adds three surfaces a careless
step could turn into a leak or a hole, and the gate reads each of them: the
release workflow, which is a trust boundary (every action pinned to a full
commit SHA, `permissions: {}` by default with `id-token: write` and `contents:
write` each in one job only, no repository secret, no `pull_request_target`, no
self-hosted runner, no expression from an untrusted context interpolated into a
`run:` script); the published files, which must hold nothing personal and
nothing from `tests/` or `scripts/` (`scripts/check_dist.py` and the
personal-data scan of both files); and LAN mode, whose token must never reach a
URL's query, a log line, a response, the database, a fixture, or the chat, whose
comparisons are constant-time, and under which no route may answer a
non-loopback peer without authentication. The gate is wired into the pre-commit
hook and re-run in CI, so a security issue introduced while implementing a step
is caught during development — before it reaches the branch, the PR, or `main`.
See the project roadmap's "Security & privacy strategy" → "Per-step security
gate" for the canonical checks and tooling; each step's XML `<task>` carries a
`<security>` block restating them for the agent, and each step's Acceptance
Criteria ends with a security check. AI coding agents executing a step MUST
treat the security gate as part of the step's definition of done, exactly like
its tests. Tests build every token and key at run time (Phase 1's check 29), and
`tests/conftest.py` deletes every `ANTHROPIC_*` and `WEATHERBOT_*` variable, so
no test reaches the operator's credentials.

**Deploy-and-verify rule.** Merged is not deployed, and deployed is not
released. Every step header carries a `**Deploys:**` line naming the surface and
environment the step's merge reaches — or `nothing beyond merge` — and when
going live needs a tag, an upload, a reinstalled copy, a restarted task, or a
repository setting, the line says so and this step (or a named follow-on step)
owns that event. This phase deploys to five surfaces: the repository's settings
and workflows (Step 2), TestPyPI (Steps 5 and 6), PyPI and the GitHub Release
(Step 7), the operator's local service (Steps 5, 6, and 7), and the install
canary's schedule (Step 7). For a step whose Deploys line names a surface, Stage
4 of the lifecycle does not end at the squash-merge: the step's acceptance
criteria carry a **Deployed & verified** bullet — the index's JSON answers with
the version and files whose SHA-256 match the workflow's build, the smoke jobs
passed after publication, and `GET http://127.0.0.1:8765/api/health` on the
operator's machine answers with the expected version — and that bullet must be
green before the step is declared complete. Step 3 introduces
`WEATHERBOT_WEB_TOKEN`, an optional variable needed only with LAN mode on; Step
6 sets it on the operator's machine, in the User environment variables the ntfy
topic already uses, and proves it by authenticated round-trips (the phone's
session and a bearer request against the LAN address), never by listing a
variable's name. A step uploads a file, pushes a tag, changes a repository
setting, reinstalls the operator's copy, restarts `\Weatherbot\serve`, edits the
operator's `weatherbot.toml`, opens a page or a window on the operator's
desktop, or runs a desktop test or a `--post` sweep only after the operator says
yes to that exact action (AskUserQuestion), and the operator approves every
deployment in GitHub's interface themselves (Decision 5). See the project
roadmap's "Release & deployment strategy" for the surfaces table, promotion
path, staged-rollout rule, and rollback.

**Triage rule.** Findings surfaced while executing a step are classified before
they are acted on, per the project roadmap's "Defect handling & triage": spec
rot → edit this roadmap's affected `<task>` block now; upstream gap → patch the
earlier step's prompt and add it to the carry-over checklist; implementation bug
→ fix in-step only if it blocks this step's acceptance criteria, otherwise an
issue and its own branch in a fresh conversation; architectural question → an
issue for a future version; process improvement → recorded where the next
conversation will read it; security finding → jumps the queue by severity;
source drift (a NOAA product changed shape, found by the release window's live
smoke) → re-record the affected source, update `docs/DATA_SOURCES.md` with the
date, and add a contract test in the same PR. A release has its own rules: a
version is never uploaded twice (PyPI and TestPyPI refuse a filename they have
seen, even after a deletion), so a published file that fails its smoke is yanked
and followed by a new version, never replaced; a publish job that fails before
uploading (a refused OIDC exchange, a misconfigured publisher) is fixed at its
cause and re-run on the same tag; and a release tag already pushed is never
moved or deleted (the ruleset refuses it). A documentation defect found by a
later step is fixed in that step when it is about that step's surface, and
otherwise recorded for the release readiness record. The OpenAPI document is a
contract: a change to a route or a response model regenerates
`docs/api/openapi.json`, the frontend's generated types, and the exported
fixtures in the same PR, and CI fails while any is stale. A golden that changes
is never "fixed" by regenerating it, and this phase changes none. A step's PR
contains the step plus blocking fixes only, and lists the issues it opened. When
a merged PR auto-closes an issue, the environment check is what earns the close
— reopen or follow up if a gap remains. `docs/phase09-qa-findings.md` is the
rollup: every finding, its class, and the guard added so the class cannot recur.

**Status rule.** Every step carries a `**Status:**` line directly under its `##
Step N — …` heading, before the Goal, and this file on `main` is the ledger of
what is done — never a chat transcript, never a later conversation
reconstructing history from `git log`. The line reads `Not started` when this
roadmap is written and is flipped by the step's OWN pull request: at Stage 3,
right after `gh pr create` returns the PR number, the agent sets it to `Complete
— PR #<n> (<YYYY-MM-DD>)`, appends ` ✅` to the step's heading (`## Step 5 — The
release candidate ✅`) so the completion shows in the rendered preview, the
outline, and the table of contents, sets the step's Summary Table Status cell to
`Complete — PR #<n>`, commits that edit on the step branch, and pushes. The PR
therefore carries its own completion mark, and the roadmap on `main` says a step
is complete exactly when that step's PR merges — never before. This file's
phase-level `**Status:**` line (under the title) and the project roadmap are
marked the same way, in the same commit: Step 1's PR flips both from `Not
started` to `In progress` (the project roadmap's `### Phase 9` line reads `In
progress — phase09-roadmap.md`, and its row in the "Phase Complexity Summary"
table reads `In progress`), and the final step's PR flips both to `Complete — …`
(the project roadmap's with its row in the "Phase Complexity Summary" table and
the header `> **Status:**` line) and appends ` ✅` to this file's `# ` title and
to the project roadmap's `### Phase 9` heading, so the project roadmap shows a
finished phase the way this file shows a finished step. There is no separate
"update the roadmaps" chore: a step whose PR merged without its Status line is a
lifecycle violation, and the next step's Stage 1 (and `/roadmap-step`) refuses
to start until the previous step reads `Complete`. If a post-merge check fails —
a Deployed & verified bullet, a smoke after publication, an alarm that never
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
   feature/phase09-step<M>-<slug>` from a clean, up-to-date `main`. The exact
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
   branch (`docs: mark Phase 9 Step <M> complete`), and push — the PR now
   carries its own completion mark, so the roadmap on `main` will say the step
   is complete exactly when the PR merges (Status rule). On the phase's first
   step, the same commit sets this roadmap's phase-level `**Status:**` (under
   its title) and the project roadmap's Phase 9 `**Status:**` to `In progress`;
   on the final step, both to `Complete`, with ` ✅` appended to this roadmap's
   `# ` title and to the project roadmap's `### Phase 9` heading.

4. **Wait for green checks, then squash-merge.** Every required status check
   must report success: the aggregate `gate` check of `ci.yml` (lint, typecheck,
   the test matrix with the coverage floors, the package smoke, the frontend,
   the browser smoke, and the security scan) and the aggregate `phase-verify`
   check (`phase-verify (01)` through `(08)`, and `(09)` from Step 8). If the PR
   goes BEHIND main while waiting, refresh with `gh pr update-branch --rebase` —
   never merge `main` into the branch; `required_linear_history: true` enforces
   rebase. Once every check is green:

   ```sh
   gh pr merge <PR_NUMBER> --squash --delete-branch
   ```

If this step's `**Deploys:**` line names a surface, the merge is not the finish
line: run the Deployed & verified check from the acceptance criteria against the
target environment now (see the Deploy-and-verify rule) before declaring the
step complete.

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
<worktree-path>`, then `git worktree prune` — because `git branch -D` refuses a
branch still checked out in a worktree. Confirm with `git branch -vv` that only
`main` and any intentional long-lived branches remain locally, and with `git
worktree list` that only the primary tree remains.

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
   two steps. Step 8, the last step of the last phase, ends instead with "Step 8
   is complete. Phase 9 is complete. The roadmap is complete.", because no Phase
   10 exists.

---

## Current State (as of Phase 8)

### Package and dependency surface

- `pyproject.toml` declares `weatherbot` `2.0.0.dev0`, `requires-python =
  ">=3.13"`, the `uv_build` backend (`>=0.12.15,<0.13`), `license = "MIT"` with
  `license-files = ["LICENSE"]`, `Development Status :: 2 - Pre-Alpha`, the
  single Python classifier `3.13`, and five project URLs. `uv build` on
  2026-11-18 wrote an 862,191-byte wheel (186 files: the package,
  `weatherbot/DISCLAIMER.md`, and the built interface under
  `weatherbot/web/static/`, whose largest file is the 924 KB script bundle) and
  a 779,583-byte sdist (`src/`, `pyproject.toml`, `README.md`, `LICENSE`,
  `DISCLAIMER.md`, `PKG-INFO`, and a `pyproject.toml.orig` that `uv_build`
  writes beside the normalized `pyproject.toml`); neither holds `tests/`,
  `scripts/`, `frontend/`, or `docs/`. The wheel's metadata reads
  `Metadata-Version: 2.4`, `License-Expression: MIT`, and `Requires-Python:
  >=3.13`, and it is `py3-none-any`.
- Runtime dependencies are floors only, except `pydantic<3` and `sqlalchemy<3`,
  so a fresh install takes each dependency's newest release, while CI tests
  `uv.lock`. Five Windows-only packages carry the toast channel —
  `winrt-runtime` and the projections `winrt-windows-data-xml-dom`,
  `winrt-windows-foundation`, `winrt-windows-foundation-collections`, and
  `winrt-windows-ui-notifications` — locked at 3.2.1 with `cp313` and `cp314`
  wheels only. PyPI's newest are `winrt-runtime` 4.2.0 (2026-11-17, `cp311` to
  `cp315`, `win32`, `win_amd64`, `win_arm64`) and the four projections at
  `4!10.0.28000.2957` (2026-10-31, pure Python, requiring
  `winrt-runtime>=4.0.0,<5`). `services/toast.py` imports
  `winrt.windows.ui.notifications` and `winrt.windows.data.xml.dom` lazily, on
  the first toast only. Of every compiled package in the lock, only `pyyaml`
  (development tooling) and the five winrt packages lack a `cp315` wheel.
- CPython 3.15.2 is current (python.org, 2026-11-18). The project pins
  `.python-version` 3.13; the installed uv, 0.12.15, offers managed downloads up
  to 3.14.7. CI's `test`, `typecheck`, and `package` jobs run Python 3.13 only,
  on `ubuntu-latest` and `windows-latest`.
- Five Dependabot pull requests are open: #8 (actions minor and patch,
  `astral-sh/setup-uv`), #31 (`uv_build` `>=0.13.8,<0.14`), #47 (`virtualenv`,
  GHSA-cx6f-vjhg-g3cc), #107 (fifteen Python minor and patch updates), and #114
  (fourteen npm updates), beside #120, a roadmap refresh whose `browser`,
  `phase-verify (05)` to `(07)`, and `security` checks fail. Issues #79
  (`minimatch`) and #121 (`picomatch <= 4.0.7`, no patched release) are
  advisories in frontend development tooling only; the CI audit runs `npm audit
  --omit=dev` for that reason.

### Release and publishing surface

- PyPI's `weatherbot` holds one release, 1.0.0 (wheel and sdist uploaded
  2025-09-29), whose metadata declares `Requires-Python >=3.11`, the author
  "Weather Alert System", and project URLs on `blob/master`. TestPyPI answers
  404 for `weatherbot` from both its JSON API and its simple index: the name is
  unregistered there.
- No workflow builds for publication or publishes. The repository has no GitHub
  environments, no rulesets (so any tag can be moved or deleted), and no GitHub
  Releases; its tags are `v1.0.0` and `v2.0.0-phase-1` to `v2.0.0-phase-8`.
  Branch protection on `main` requires `gate` and `phase-verify` (strict),
  enforces admins and linear history, and allows squash merges only, with
  `delete_branch_on_merge`.
- `ci.yml`'s `package` job is the nearest thing to a release smoke: on both
  runners it builds the frontend and `uv build`, checks the sdist for
  `DISCLAIMER.md`, installs the wheel into a fresh virtual environment, compares
  `weatherbot --version` with `uv version --short`, asserts the wheel holds
  `index.html` and `licenses.json`, opens a new database at head from the
  installed package, and runs `scripts/smoke_installed_web.py`, which starts
  `weatherbot serve --no-open` in temporary directories with outbound traffic
  sent to a dead proxy, then checks `/api/health`'s `version` and `ui.present`
  and `/`'s nonce-carrying CSP. Its `uv pip install` of the wheel takes no
  constraints, so it resolves each dependency's newest release — pywinrt 4 on
  `windows-latest` — on Python 3.13, but nothing in it imports pywinrt, and it
  runs before anything is published. `weatherbot doctor --offline` in empty
  temporary directories exits 0 (checked 2026-11-18).
- The project roadmap's "Release & deployment strategy" names PyPI and TestPyPI
  as surfaces released by a tag-triggered workflow with trusted publishing and
  verified by a fresh-install smoke, and its Rollback table gives "Yank the
  release, publish a patch" with "Under an hour (TBD once rehearsed)".

### Web server and network surface

- `[web]` (`services/config.py` `WebSettings`) holds `host` (default
  `127.0.0.1`; a validator refuses anything but `127.0.0.1`, `::1`, or
  `localhost`, with a message that still says "remote access belongs to Phase
  8"), `port` (8765; 0 or 1024 to 65535), and `corpus`; `ENVIRONMENT_OVERRIDES`
  maps them to `WEATHERBOT_WEB_HOST`, `WEATHERBOT_WEB_PORT`, and
  `WEATHERBOT_WEB_CORPUS`. `[web]` is not in `settings_file.EDITABLE`, so `PUT
  /api/settings` cannot change it (Phase 7's check 25).
- `web/server.py`'s `WebServer` binds one socket (`SO_EXCLUSIVEADDRUSE` on
  Windows) and runs uvicorn on it with `proxy_headers=False`,
  `limit_concurrency=64`, no access log, and no server header; `cli/serve.py`
  builds it from `settings.web.host` and `settings.web.port`.
- `web/guards.py` installs three pure ASGI layers: `SecurityHeadersMiddleware`
  (outermost: the CSP, `X-Frame-Options: DENY`, `Cross-Origin-Opener-Policy` and
  `-Resource-Policy: same-origin`, `no-store` on `/api/`, every
  `Access-Control-Allow-*` removed), Starlette's `TrustedHostMiddleware` over
  the fixed `ALLOWED_HOSTS = ("127.0.0.1", "localhost", "[::1]")`, and
  `FetchMetadataAndWriteGuard` (no `OPTIONS`; a cross-site `Sec-Fetch-Site`
  refused on `/api/`; a write whose `Sec-Fetch-Site` is not `same-origin`, or
  whose `Origin` is not `http://<Host>`, refused; every write JSON; a write
  carrying neither header, as a non-browser client sends, passes). Nothing
  authenticates a request, because only loopback can reach the server.
- The SPA connects its event stream with `EventSource("/api/events")` and its
  API through `openapi-fetch` (`frontend/src/api/client.ts`); both are
  same-origin, so a cookie would ride along with no code change.
  `frontend/src/notifications/notify.ts` uses the Notification API, which
  browsers grant only in a secure context: `http://127.0.0.1` is one, and
  `http://<a LAN address>` is not.
- The data classification already lists the LAN bearer token beside the ntfy
  topic ("Same handling as the API key"; "required for any non-loopback bind"),
  and `SECURITY.md` already names "a non-loopback bind without the LAN token" as
  a vulnerability. `services/logs.py`'s `SecretFilter` redacts
  `ANTHROPIC_API_KEY`, `WEATHERBOT_NTFY_TOPIC`, and `WEATHERBOT_NTFY_TOKEN`
  values and assignments at every level.

### Documentation surface

- `README.md` (446 lines) is written for a checkout: "No version 2 package is
  released", every command example uses `uv run weatherbot`, running unattended
  starts from `uv tool install --from .`, its `## Status` names Phase 8 complete
  and Phase 9 next (Phase 8's check 52 pins that text), its development
  quickstart quotes `2.0.0.dev0`, and its document links are relative
  (`docs/AI.md`), which PyPI's page cannot resolve; its only absolute links are
  the disclaimer, the `v1.0.0` tree, and uv's documentation. It keeps the
  headings `### Running unattended`, `### The dashboard`, `## Disclaimer`, `##
  Development quickstart`, `## Documents`, and `## License`.
- `CHANGELOG.md` keeps one `## [Unreleased]` section holding `### Phase 8` back
  to `### Phase 3`, the Phase 1 and 2 verification notes, and `### Added`, `###
  Changed`, and `### Removed`, above `## [1.0.0] - 2025-09-29` and version 1's
  own sections. `docs/AI.md` (728 lines), `docs/ALERT-LADDER.md` (232; its three
  tables generated by `scripts/export_ladder.py --check`),
  `docs/DATA_SOURCES.md` (1,204), `docs/NOTIFICATIONS.md` (230), and
  `docs/DESIGN.md` (332) are developer-facing, current, and assume a checkout in
  places; `docs/AI.md` still says "Phase 6 adds the products step by step". No
  user guide, configuration reference, always-on guide, troubleshooting page, or
  migration note exists, and no screenshot is committed.
- `SECURITY.md` supports "2.x pre-releases on `main`" and retires 1.0.0.
  `DISCLAIMER.md` ships in the wheel and the sdist and is shown by the CLI's
  first run, every read command, the web footer, and every assessment view.

### Security & sensitive-data surface

- The gate is the same everywhere: `gitleaks` (8.30.1, checksum-verified in CI),
  `scripts/check_personal_data.py` (R1 the operator's local denylist, R2
  three-decimal coordinate pairs outside the recorded trees, R3 request
  coordinates in manifests, R4 no environment files; it reads gzip and zip
  members within bounds), `bandit` over `src` and `scripts`,
  `scripts/audit_deps.py` (`pip-audit --strict` over the whole lock), ESLint
  with `eslint-plugin-security`, and `npm audit --audit-level=high --omit=dev`.
  Every third-party action is pinned to a full commit SHA, every workflow
  declares least-privilege `permissions:`, none uses `pull_request_target`, and
  all run on GitHub-hosted runners.
- This phase adds three sensitive surfaces: the publishing credential, which
  OIDC replaces with a short-lived token minted only inside an approved
  environment's job (no PyPI token is ever created or stored); the published
  files, which reach everyone who installs; and the LAN token, the project's
  first credential that admits a request to the API.

### Operations & observability surface

- `/api/health` reports the version, the schema head (`0010`), the scheduler,
  the heartbeats, `stale`, `next_product_at`, `corpus`, the AI block, and
  `ui.index_sha256`; `doctor` reports the paths, the migrations, every source,
  the tasks, the `PATH`, the web check, toast, ntfy, and AI. The operator's
  service runs Phase 8's build (`ui.index_sha256` `825fa957cd69`, deployed
  2026-11-17) under `\Weatherbot\serve` from
  `C:\Users\Admin\.local\bin\weatherbot.exe`, installed from the checkout at
  `2.0.0.dev0`, with `\Weatherbot\check` hourly at HH:25; bare `weatherbot` on
  `PATH` is version 1.
- The released package has no health signal: nothing notices if a dependency's
  new release breaks a fresh install of the published version.
  `replay-corpus.yml` (scheduled, with a `simulate_failure` input) and
  `live-smoke.yml` (manual) are the precedents for a scheduled workflow whose
  failure email is the alarm and for a manual live check.

### Verification surfaces

- `scripts/verify_phase08.py` is the structural template: 60 standard-library
  static checks, eight mutually exclusive modes (`--fast`, `--py`, `--node`,
  `--ui`, `--live`, `--security`, `--all`, `--post`), and 38 V rows built from
  JUnit evidence in which every selection must match a test, a failure fails,
  and a skip is never a pass; lines read `[PASS] 01: description (detail)` and
  the summary block `passed`, `failed`, `skipped`, `total`, exiting 0 only with
  none failed or skipped, and its `STATIC_CHECKS` descriptions are ASCII-only,
  because a Windows `cp1252` console cannot decode `…` in a child's output. Its
  `--post` nests `verify_phase07.py --post` (expected total `107`, measured at
  7,562.5 s, under `NESTED_SWEEP_TIMEOUT_SECONDS = 14400`), runs the dogfood
  probe, the idle measurement, and the operator's health and `doctor` probes,
  and totals 98. Indented `[FAIL]` and `[SKIP]` lines from a nested run are read
  with `line.lstrip()`.
- `.github/workflows/phase-verify.yml`'s `verify` job holds the one-line matrix
  `phase: ["01", "02", "03", "04", "05", "06", "07", "08"]`, separate Node steps
  under the literal conditions `matrix.phase == '05'` to `'08'` (each
  `actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0`), and
  one `--security` step; the aggregate `phase-verify` job is required. Step 8
  appends `"09"` and adds its own Node pair, touching none of the others.
- How the verifiers select tests: the JUnit key is `classname.name`; a Vitest
  classname is the path under `frontend/` and a Playwright one the spec's path
  under `e2e/`, so every frontend selection names a file and never a title. A
  selected file must keep its path and hold at least one test, all passing and
  none skipped, and the catch-all rows (the whole Vitest run, the whole
  Playwright run, and pytest) make every other test required too, new ones
  included.
- Checks of the earlier phases, and pinned tests, that this phase's work could
  turn red, and how each stays green (Decision 15):

| Check | Reads | How Phase 9 keeps it green |
| ----- | ----- | -------------------------- |
| P1 3, 4 | `CHANGELOG.md` | one `[Unreleased]`; 1.0.0 lines kept |
| P1 7 | `requires-python` | stays `>=3.13`; version at tag |
| P1 10 | v1's deleted paths | upper-case new doc names |
| P1 README | `DISCLAIMER.md`, `v1.0.0` | kept; no "global coverage" |
| P1 pins, permissions | every workflow | SHA, `# vX`; `permissions:` |
| P1 User-Agent, register | register | version rewritten; rows kept |
| P2, P3 47, P6 45, P7 55 | `## Commands` needles | section and words kept |
| P3 5, P7 2, budget test | `test` job tokens | kept in the 3.15 entries too |
| P3 36 | ladder blocks, link | edits outside the blocks |
| P4 26 | `toast.py` names, lazy import | kept on pywinrt 4 |
| P4 31 | runners in three jobs | both runners kept |
| P4 post | jobs `test (<os>)` | 3.13 entries keep the names |
| P4 winrt check | `winrt-*` prefixes, marker | pywinrt 4 keeps both |
| P5 1 | `fastapi>=` and peers | caps keep the prefix |
| P5 4 | exact `ALLOWED_HOSTS` | kept; LAN hosts apart |
| P5 5 | `server.py` names | kept with two listeners |
| P5 6 | literal `ENVIRONMENT_OVERRIDES` | new entries literal |
| P5 13, 9; OpenAPI tests | paths included | `/api/session` only adds |
| P5 32 | build, `uv build`, smoke | order kept in `package` |
| P5 39 | `notify.ts` needles | kept; only `notify.ts` |
| P5 40 | leaflet's exact 1.x pin | kept exact (#114) |
| P5 47 | `### The dashboard` | heading kept |
| P6 1 | `anthropic>=2.3.0` | clause read at its tag (Step 1) |
| P6 20, 43 | `docs/AI.md` needles | headings, figures kept |
| P6 39, P7 43 | package names | no package added |
| P6 40, P7 48 | `NAV_ITEMS` | LAN chip outside it |
| P7 16 | no `token` or `topic` field | LAN fields are `lan*` |
| P7 22 | `logs.py` secret literals | kept; web token added |
| P7 23 | `NOTIFICATIONS.md` | headings kept |
| P7 25 | `EDITABLE` | `[web]` stays out |
| P7 35 | `CSP_SUFFIX` | unchanged |
| P7 44, P8 9 | `style=`, small type | none added |
| P7 59, P8 52 | changelog headings | kept |
| P8 13 | `docs/DESIGN.md` | headings kept |
| P8 46 | `/@idle\|@dogfood/` literal | docs capture config apart |
| P8 49, 60 | images, binaries | screenshots in `docs/` |
| P8 52 | README `## Status` | read at its tag (Step 1) |
| P8 53, 57 | ROADMAP rows | rows kept |
| P8 54 | dashboard component names | read at its tag (Step 4) |
| P1 50, P7 64, P8 58 | matrix line, Node steps | append `"09"`; own pair |
| `test_cli.py` | `2.0.0.dev0` literal | metadata-derived (Step 2) |
| recorded manifests | UA equals current | shape-checked (Step 2) |
| corpus manifest, P1 post | UA equals current | shape-checked (Step 2) |
| `test_register.py` | register UA | rewritten by the tool |
| `--check` exports | OpenAPI, fixtures | regenerated by the tool |

- Phase 9's `--post` nests Phase 8's (`EXPECTED_PHASE_08_POST_TOTAL` `"98"`),
  which nests Phases 7 to 1 in turn: Vitest and Playwright run five times, the
  600-second idle window four times, Phases 4 and 5 run their desktop tests
  (real toasts and a Task Scheduler probe) and `simulate_advisory.py` on the
  operator's desktop, and the nested probes read the operator's service — Phase
  5's V7.4 compares `ui.index_sha256` with the checkout's built `index.html`,
  Phase 6's V6.5 needs a settled briefing among its last 100 AI calls, and Phase
  7's probes need `corpus: true` and the operator's locations — so Step 8 runs
  on the 2.0.0 the operator installed, measures the nested duration, and sets
  its own timeout above it.

### Carry-over from Phase 8

Every item an earlier phase handed to this one, and where it lands:

| Item                                   | Source           | Lands in       |
| -------------------------------------- | ---------------- | -------------- |
| P8 check 52 (`README.md` `## Status`)  | P8 QA ledger     | Step 1         |
| Documentation, screenshots, user guide | ROADMAP 9.1, P8  | Step 4         |
| Tag-triggered TestPyPI and PyPI        | ROADMAP 9.2      | Steps 2, 5, 7  |
| Fresh-install smoke, both runners      | ROADMAP 9.2, P7  | Steps 2, 5, 7  |
| Readiness checklist, scenario scan     | ROADMAP 9.3, P8  | Steps 2–7      |
| Rollback rehearsed (yank and patch)    | ROADMAP 9.3      | Step 6         |
| LAN mode and its readiness sub-step    | ROADMAP 9.3, P7  | Steps 3, 6     |
| Shipping the replay corpus             | P7 Decision 17   | Steps 2, 4, 7  |
| `[web]` stays out of `EDITABLE`        | ROADMAP Phase 9  | Step 3         |
| The version bump from `2.0.0.dev0`     | P8 Decision 20   | Steps 2, 5, 7  |
| Dependabot PRs #8, #31, #47, #107, #114  | P7, P8 ledgers   | Step 1         |
| Roadmap refresh PR #120                | PR #120          | this PR        |
| Issues #79, #121 (dev-only advisories) | P6–P8 ledgers    | Step 7 record  |
| Issue #95 (tile proxy, conditional)    | P7 ledger        | its issue      |
| Issue #33 (surge, extreme wind)        | P5–P8 ledgers    | the operator   |
| Version 1 on the operator's `PATH`     | P7, P8 ledgers   | Step 4 guide   |
| 1.0.0 still resolvable on Python 3.11  | this roadmap     | Step 7         |
| pywinrt 4 and Python 3.15 wheels       | this roadmap     | Step 1         |

---

## Execution Order

```
Step 1  (what ships is tested)            pywinrt 4 + lock upgrade + caps
                                          + Python 3.15 in CI + Dependabot
                                          + README Status (P8 check 52)
                                          → implement
  ↓
Step 2  (release pipeline)                set_version + check_dist +
                                          release.yml + environments +
                                          ruleset + RELEASING.md + dry run
                                          → implement
  ↓
Step 3  (LAN mode)                        [web] lan + second listener +
                                          token + session + limiter +
                                          prompt + docs/LAN.md (not yet)
                                          → implement
  ↓
Step 4  (documentation)                   README for PyPI + GUIDE.md +
                                          CONFIGURATION.md + guides +
                                          screenshots
                                          → implement
  ↓
Step 5  (release candidate)               2.0.0rc1 → TestPyPI + smokes
                                          + the operator's service soaks
                                          → operate
  ↓
Step 6  (readiness rehearsals)            first LAN bind with the phone +
                                          yank rc1, publish rc2, roll back
                                          and forward
                                          → operate
  ↓
Step 7  (2.0.0)                           readiness signed → v2.0.0 →
                                          PyPI + smokes + operator upgrade
                                          + install canary armed
                                          → operate
  ↓
Step 8  (QA + verify_phase09.py)          scripts/verify_phase09.py
                                          + docs/phase09-qa-findings.md
                                          + phase-verify.yml entry "09"
                                          → create

--- post-implementation ---

V1  The lock is upgraded, pywinrt 4 toasts, 3.13 and 3.15 pass
    on both runners, and caps hold every 1.0+ dependency.
V2  One version source; dist passes the allowlist; the release
    workflow's dry run builds and smokes without publishing.
V3  LAN mode refuses without a token, authenticates every LAN
    request, limits failures, and warns at every start.
V4  The README renders for PyPI; the guide, the reference, and
    the screenshots match the product.
V5  2.0.0rc1 is on TestPyPI, installed on both runners and on
    the operator's service.
V6  The phone used LAN mode; rc1 was yanked and rc2 published;
    the rollback is timed.
V7  2.0.0 is on PyPI with attestations, installed on both runners
    and the operator's service; the canary is armed.
V8  verify_phase09.py --fast and --security exit 0 in
    phase-verify (09); the phase is closed.
```

Steps are sequential by dependency. Step 1 comes first because the release must
test what it ships: the pipeline in Step 2 installs the built wheel on the
newest Python, which the pywinrt move is what makes possible, and every later
step builds on the upgraded lock. Step 2's version tool, allowlist, and workflow
are what Steps 5 to 7 run, and its dry run proves the build and the smokes
before anything can be published. Step 3 comes before the documentation because
the guide documents LAN mode, and before the release candidate because rc1 must
carry the code Step 6 rehearses on the operator's network. Step 4's
documentation must be in rc1, so TestPyPI shows the page PyPI will show. Step
5's candidate is what Step 6 yanks, and Step 6's rehearsals are readiness items
Step 7 cannot sign without. Step 8 verifies every prior step after the release.
Every step edits `pyproject.toml`, `uv.lock`, the README, or a workflow, and
Steps 5 to 7 each publish a version the next one depends on, so this phase draws
no steps in parallel, and the Worktree rule permits no concurrent steps.

---

## Step 1 — What ships is what CI tests ✅

**Status:** Complete — PR #129 (2026-11-28)

> **Goal:** Make the dependency set a clean install resolves the one CI tests,
> on every Python a clean install can pick (Decision 2), and open the phase.
> pywinrt moves to version 4 in `pyproject.toml` and `uv.lock`,
> `src/weatherbot/services/toast.py` is proved on it with a real toast on the
> operator's desktop, `uv lock --upgrade` brings every locked package current
> with its fallout fixed, every runtime dependency at 1.0 or later gains an
> upper bound below its next major (Phase 6's check 1 reading its anthropic
> clause at `v2.0.0-phase-6`), `.github/workflows/ci.yml`'s `test` and `package`
> jobs run Python 3.13 and 3.15 on both runners, the classifiers declare 3.13 to
> 3.15, `tests/test_dependency_policy.py` holds all of it (caps,
> `requires-python`, and a 3.13 and a 3.15 wheel on both platforms for every
> compiled runtime package), and the open Dependabot pull requests (#8, #31,
> #47, #107, #114) are superseded or closed with their reasons; `README.md`'s
> `## Status` names Phase 9 in progress, Phase 8's check 52 reads the README at
> `v2.0.0-phase-8`, `CHANGELOG.md` gains `### Phase 9 — Release 2.0`, and both
> roadmaps mark the phase In progress.

**Branch:** `feature/phase09-step1-tested-dependencies`

**Deploys:** nothing beyond merge — the CI matrix is live on merge; the
operator's service takes the upgraded set with the release candidate at Step 5.
The desktop toast test runs once from this branch, on the operator's desktop,
with a yes.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost                  | Balanced              | Quality            |
| ------------- | -------- | --------------------- | --------------------- | ------------------ |
| **Pick**      | Model    | **Gemini 4 Hydrogen** | **Gemini 4 Hydrogen** | **Opus 5.5**       |
|               | Platform | Gemini (web / app)    | Gemini (web / app)    | Claude Code        |
|               | Level    | Medium                | High                  | XHigh              |
|               | AA       | ≈48.8                 | ≈51.6                 | 56                 |
|               | Price    | ≈$2.62/1M             | ≈$3.00/1M             | $8.29/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**        | **Opus 5.5**          | **Gemini 4 Neon**  |
|               | Platform | Claude Code           | Claude Code           | Gemini (web / app) |
|               | Level    | XHigh                 | High                  | XHigh              |
|               | AA       | 51.9                  | 53.6                  | ≈56.9              |
|               | Price    | $3.72/1M              | $6.76/1M              | ≈$8.25/1M          |
| **Backup**    | Model    | **GPT-6.2 Sol**       | **GPT-6.2 Sol**       | **GPT-6.2 Sol**    |
|               | Platform | Codex                 | Codex                 | Codex              |
|               | Level    | Medium                | High                  | XHigh              |
|               | AA       | ≈49.8                 | ≈52.2                 | ≈53                |
|               | Price    | ≈$3.50/1M             | ≈$4.00/1M             | ≈$5.50/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels or its previous version's.

> Ran 2026-11-28: Quality Pick or Balanced Runner-up — Opus 5.5 · XHigh or High.

**Conversation:** New

> Settings updated 2026-11-19 (refresh): Cost Pick was Sonnet 5.5 · XHigh, Balanced Pick was Gemini
> 4 Argon · High, Cost Runner-up was Gemini 4 Argon · Low, Quality Runner-up was Gemini 4 Argon ·
> High, Cost Backup was GPT-6.1 Sol · XHigh, Balanced Backup was GPT-6 Astra · High, Quality Backup
> was GPT-6 Astra · XHigh. Re-ranked against the current roadmodel catalog.

**Model rationale:** Step 1 is coding with an agentic secondary category — a
lock upgrade across every group, a dependency's new major with an import path
that only Windows exercises, a CI matrix, two verifier conversions, and a
handful of pull requests to dispose of — at High complexity for its breadth, not
novel: Decision 2 fixes every rule, and the fallout is found by the gates rather
than by design. On the step alone, the Cost Pick fits best: Gemini 4 Hydrogen on
Gemini (web / app) at Medium. It meets the selection threshold at the lowest
estimated cost for this classification. The Balanced Pick is Gemini 4 Hydrogen
on Gemini (web / app) at High, and the Quality Pick is Opus 5.5 on Claude Code
at XHigh.

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
       feature/phase09-step1-tested-dependencies`
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
       Phase 9 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 9`
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

    THIS STEP changes what every future install downloads, so the dependency
    audit reads the upgraded lock in full (`scripts/audit_deps.py`, every
    group) and the frontend's production dependencies (`npm audit
    --audit-level=high --omit=dev`), and each package whose major version
    moves is checked on its registry page (the maintainer, the release date,
    no yank) before it enters the lock. The desktop toast runs `uv run pytest
    -m desktop -k toast` on the operator's desktop only after the operator's
    yes — never the whole marker, whose Task Scheduler test registers and
    deletes `\Weatherbot\probe` — and shows the test's own text, never a
    location. Closing a Dependabot pull request is an outward-facing action:
    comment the reason, and never close one whose update this branch does not
    carry without saying why.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 9 (Release 2.0). Step 1: what ships
    is what CI tests.

    Current state (as of Phase 8, the start of Phase 9):

    - `pyproject.toml`: `requires-python = ">=3.13"`; runtime dependencies are
      floors only except `pydantic<3` and `sqlalchemy<3`; the five Windows
      packages (`winrt-runtime`, `winrt-windows-data-xml-dom`,
      `winrt-windows-foundation`, `winrt-windows-foundation-collections`,
      `winrt-windows-ui-notifications`) are `>=3.2.1 ; sys_platform ==
      'win32'` and locked at 3.2.1, whose wheels cover `cp313` and `cp314`
      only. `winrt-runtime` 4.2.0 (2026-11-17) has wheels for `cp311` to
      `cp315`, and the projections at `4!10.0.28000.2957` are pure Python and
      require `winrt-runtime>=4.0.0,<5`. Of the lock's compiled packages, only
      these five and `pyyaml` (6.0.3; no `cp315` wheel yet, development
      tooling) lack a 3.15 wheel. CPython 3.15.2 is current.
    - `src/weatherbot/services/toast.py` imports
      `winrt.windows.ui.notifications` and `winrt.windows.data.xml.dom` lazily
      on the first toast; `tests/desktop/test_toast_desktop.py` (`-m desktop`,
      deselected by default) shows a real toast.
    - `uv tree --outdated` on 2026-11-18 listed, among others, `anthropic`
      2.3.0 → 2.10.0, `fastapi` 0.162.0 → 0.165.0, `typer` 0.27.3 → 0.29.2,
      `ruff` 0.17.0 → 0.17.5, `pytest` 9.1.1 → 9.2.0, and `import-linter` 2.15
      → 2.17. `pyproject.toml` sets `filterwarnings = ["error"]`, so a new
      deprecation fails tests.
    - `.github/workflows/ci.yml`: `test` (matrix `os: [ubuntu-latest,
      windows-latest]`, `timeout-minutes: 40`, `pytest -n auto` with the four
      90 percent floors, `COVERAGE_FILE` in the runner's temp) and `package`
      (builds the frontend and `uv build`, installs the wheel into a fresh
      environment, `scripts/smoke_installed_web.py`) run Python 3.13 from
      `.python-version`; uv honours `UV_PYTHON`. `tests/test_ci_budget.py` and
      Phase 3's check 5, Phase 4's check 31, and Phase 7's check 2 read the
      `test` job's tokens by inclusion.
    - `scripts/verify_phase06.py`'s check 1 requires the exact string
      `anthropic>=2.3.0` in `[project] dependencies`;
      `scripts/verify_phase08.py`'s check 52 reads `README.md`'s live `##
      Status` for "Phase 8 (UI/UX redesign and visual\ndogfooding) are
      complete" and "Phase 9 (Release 2.0) is next"; its `tagged(relative,
      root, *, tag=PHASE_7_TAG)` helper and `PHASE_8_TAG` exist, and
      `tests/test_phase08_verification.py` pins check 52 in two tests (near
      lines 304 and 328).
    - Open Dependabot pull requests: #8 (`astral-sh/setup-uv` 10.1.0 →
      10.3.3), #31 (`uv_build` `>=0.13.8,<0.14`), #47 (`virtualenv`,
      GHSA-cx6f-vjhg-g3cc), #107 (fifteen Python minor and patch updates),
      #114 (fourteen npm updates). Phase 5's check 26 needs exact versions for
      `react`, `react-dom`, `typescript` (5.x), `vite`, `openapi-typescript`,
      and `eslint-plugin-security`.
    - `uv run` re-syncs `.venv` to the lock, which also moves roadmodel (the
      `planning` group) to the lock's pin.

    Files to read (every file before drafting):

    - docs/roadmap/phase09-roadmap.md (Decisions 1, 2, and 15, and this step)
      and docs/roadmap/ROADMAP.md (Phase 9).
    - pyproject.toml, .python-version, and `uv lock --upgrade --dry-run`
      output.
    - src/weatherbot/services/toast.py, tests/services/test_toast*.py, and
      tests/desktop/test_toast_desktop.py.
    - .github/workflows/ci.yml, tests/test_ci_budget.py, and
      .github/dependabot.yml.
    - scripts/verify_phase06.py (check 1) with
      tests/test_phase06_verification.py, and scripts/verify_phase08.py
      (checks 52 and 55) with tests/test_phase08_verification.py.
    - README.md (`## Status`) and CHANGELOG.md (the top of `## [Unreleased]`).
    - `gh pr view 8 31 47 107 114` (each pull request's updates and checks).
  </context>

  <goal>
    Upgrade the lock, move to pywinrt 4 with a proved toast, cap the stable
    majors, test on Python 3.13 and 3.15, dispose of the dependency pull
    requests, and open Phase 9 in the README, the changelog, and both
    roadmaps.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      pywinrt 4. Change the five requirements to floors at the versions you
      lock (`winrt-runtime>=4.2.0` and the projections at
      `>=4!10.0.28000.2957`, each `; sys_platform == 'win32'`) with an upper
      bound below the next major of `winrt-runtime` (`<5`) and below the next
      epoch of the projections; keep each requirement starting with its
      package name and carrying the marker (Phase 4's check reads both). Make
      `services/toast.py` and its tests work on version 4 without loading
      pywinrt at import time. Then state in the chat what the desktop test
      will show, ask with AskUserQuestion, and only after a yes run `uv run
      pytest -m desktop -k toast` on the operator's desktop; record the date
      and the result in the PR body.
    </requirement>

    <requirement>
      The lock. Run `uv lock --upgrade` and fix everything it breaks — new
      ruff findings (fix them; an ignore needs an inline reason), pyright, a
      deprecation under `filterwarnings = ["error"]`, a changed API — until
      every gate passes on both runners. Update the frontend's production and
      development dependencies to the versions #114 carries (keeping the exact
      pins Phase 5's check 26 needs and TypeScript 5), and the
      `astral-sh/setup-uv` pin to the commit #8 names (full SHA and its `#
      vX.Y.Z` comment, in every workflow). Move `[build-system] requires` to
      the `uv_build` range #31 names only if `uv build` still writes a wheel
      and an sdist with the same file lists as today (compare them in the PR
      body); otherwise close #31 with that reason. A package whose upgrade
      moves a replay or notification golden (Phase 3's digests, Phase 4's
      approved notifications, `replay-corpus.yml`'s `pytest -m corpus`) is
      held at its current version with a cap and a reason in the PR body; a
      golden is never regenerated (Decision 1). After each `uv lock
      --upgrade`, put roadmodel back on its current pin (`uv lock
      --upgrade-package roadmodel==<the pin>`): the daily updater owns kit
      refreshes, each in its own `chore(planning)` commit (AGENTS.md). Re-run
      `uv lock --upgrade` immediately before opening the PR, so the lock is
      current on the day it merges.
    </requirement>

    <requirement>
      Caps. For every runtime requirement whose locked version is 1.0 or
      later, add an upper bound below its next major: `alembic<2`,
      `anthropic<3`, `platformdirs<5`, `pyproj<4`, `rich<16`, `shapely<3`,
      `starlette<2`, and the pywinrt bounds above, keeping `pydantic<3` and
      `sqlalchemy<3`; `tzdata` (calendar versions) keeps its floor only, and
      so do the requirements below 1.0 (`defusedxml`, `fastapi`, `httpx`,
      `tomlkit`, `typer`, `uvicorn`). Leave each floor where it is unless the
      upgrade needs a newer one. Keep `requires-python = ">=3.13"` exactly.
      Convert Phase 6's check 1 in the same commit: its `anthropic>=2.3.0`
      clause reads `tagged("pyproject.toml", tag=PHASE_6_TAG)` (add the
      helper's `tag` parameter if absent), a live clause requires one
      requirement starting `anthropic>=` with an upper bound below 3, and the
      `httpx2` clauses stay live; add tests for it to
      tests/test_phase06_verification.py (none pin check 1 today) and update
      its docstring.
    </requirement>

    <requirement>
      Python 3.15. In `ci.yml`, give `test` and `package` a `python: ["3.13",
      "3.15"]` dimension beside `os`, set `UV_PYTHON: ${{ matrix.python }}` in
      their environment, and keep the 3.13 entries' names exactly `test
      (ubuntu-latest)` and `test (windows-latest)`, which Phase 4's `--post`
      reads (`name: ${{ matrix.python == '3.13' && format('test ({0})',
      matrix.os) || format('test ({0}, {1})', matrix.os, matrix.python) }}`,
      and the same pattern for `package`); keep every step, token, floor, and
      timeout as it is, so the inclusion checks and `tests/test_ci_budget.py`
      still read them. `typecheck` stays on 3.13 (`pythonVersion = "3.13"`).
      Add `Programming Language :: Python :: 3.14` and `3.15` to the
      classifiers. If a development-only package has no 3.15 wheel and cannot
      build, say which in the PR body and take the newest version that
      installs.
    </requirement>

    <requirement>
      Add tests/test_dependency_policy.py (standard library and `packaging`
      only, reading `pyproject.toml` and `uv.lock`):
      - test_requires_python_has_no_upper_bound (exactly `>=3.13`).
      - test_stable_runtime_requirements_are_capped (each runtime requirement
        locked at 1.0 or later is capped below its next major; epochs and
        calendar versions handled as above).
      - test_requirements_below_1_0_have_floors_only.
      - test_classifiers_name_python_3_13_to_3_15.
      - test_compiled_runtime_wheels_cover_3_13_and_3_15 (every compiled
        package in the runtime closure of `uv.lock` has a wheel for both
        Pythons on each platform its marker allows: `win_amd64` alone for the
        Windows-only pywinrt runtime, `win_amd64` and `manylinux` `x86_64` for
        the rest; `abi3` counts; a pure wheel needs no tag).
    </requirement>

    <requirement>
      Dependabot. After this branch's lock, pins, and
      `frontend/package-lock.json` carry each update, comment on #8, #31, #47,
      #107, and #114 naming this PR; close any Dependabot does not close
      itself once this PR merges, with the reason, and list every disposition
      in the PR body. Do not merge them separately: this PR supersedes them.
    </requirement>

    <requirement>
      Open the phase. Set `README.md`'s `## Status` to name Phases 1 to 8
      complete and Phase 9 (Release 2.0) in progress, keeping "No version 2
      package is released" true until Step 7, and keep every other README
      needle (Decision 15). Convert Phase 8's check 52 in the same commit:
      `status = markdown_section(tagged("README.md", tag=PHASE_8_TAG), "##
      Status")`, the `CHANGELOG.md` clause live, the docstring saying Phase 9
      Step 1 moved the live Status on, and the two tests in
      tests/test_phase08_verification.py rewritten so a moved live Status
      passes and a missing changelog heading still fails. Add `### Phase 9 —
      Release 2.0` at the top of `## [Unreleased]` in `CHANGELOG.md` with this
      step's entries. Stage 3's commit sets this roadmap's and the project
      roadmap's Phase 9 `**Status:**` lines and the project roadmap's "Phase
      Complexity Summary" row to `In progress`.
    </requirement>

    <requirement>
      Before every commit, run all eight verifiers' `--fast` (`uv run python
      scripts/verify_phase0N.py --fast`, N from 1 to 8); each must exit 0.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative path as the
      first line where the file type accepts comments.
    </requirement>
  </requirements>
</task>
```

### Step 1 acceptance criteria

- `uv.lock` resolves `winrt-runtime` 4.2.0 or later and the four projections at
  `4!10.0.28000.2957` or later on Windows; the toast unit tests pass on
  `windows-latest`, and `uv run pytest -m desktop -k toast` showed one real
  toast on the operator's desktop on Python 3.13 after the operator's yes (date
  and result in the PR body).
- The lock is the output of `uv lock --upgrade` on this branch (re-run before
  the PR opens), and every gate passes on it: ruff, ruff format, pyright on both
  platforms, lint-imports, pytest with the four coverage floors, the frontend
  suites, the browser smoke, and the security scan.
- `tests/test_dependency_policy.py` passes: every runtime requirement whose
  locked version is 1.0 or later has an upper bound below its next major, every
  requirement below 1.0 has a floor only, `requires-python` is exactly `>=3.13`,
  the classifiers name Python 3.13, 3.14, and 3.15, and every compiled runtime
  package in the lock has a `cp313` and a `cp315` (or `abi3`) wheel for each
  platform its marker allows (`win_amd64` alone for pywinrt's runtime).
- `ci.yml`'s `test` and `package` jobs report four entries each (Python 3.13 and
  3.15 on `ubuntu-latest` and `windows-latest`) and all eight pass on this PR,
  the 3.13 entries keeping the names `test (ubuntu-latest)` and `test
  (windows-latest)` that Phase 4's `--post` reads; `typecheck` and the other
  jobs are unchanged; `tests/test_ci_budget.py` passes; `replay-corpus.yml`,
  which a lock change triggers, passes on this PR.
- Phase 6's check 1 reads `anthropic>=2.3.0` at `v2.0.0-phase-6` and requires a
  live `anthropic>=` requirement capped below 3, with mutation tests added (none
  pin it today); Phase 8's check 52 reads `## Status` at `v2.0.0-phase-8` with
  the `CHANGELOG.md` clause live, and its two tests in
  `tests/test_phase08_verification.py` updated; `verify_phase01.py` to
  `verify_phase08.py` `--fast` all exit 0.
- Each of #8, #31, #47, #107, and #114 is closed — by Dependabot once `main`
  carries its update, or with a comment naming this PR and the reason — and the
  PR body lists every disposition.
- `README.md`'s `## Status` names Phases 1 to 8 complete and Phase 9 (Release
  2.0) in progress; both roadmaps read `In progress`; `CHANGELOG.md` holds `###
  Phase 9 — Release 2.0` under the one `## [Unreleased]`.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  and `scripts/audit_deps.py` (`pip-audit --strict` over the upgraded lock) and
  `npm audit --audit-level=high --omit=dev` clean — and every bumped package was
  checked against its registry page for a typo-squat or a yanked release; the
  desktop toast showed only the test's text.

---

## Step 2 — The release pipeline ✅

**Status:** Complete — PR #131 (2026-11-28)

> **Goal:** Build everything a release needs and prove it without publishing
> (Decisions 3 to 8 and 13). `scripts/set_version.py` sets the version
> everywhere it lives and `tests/test_release_metadata.py` holds every copy to
> it, with `tests/test_cli.py`, the recorded-manifest User-Agent test, and
> `scripts/fetch_replay_corpus.py`'s corpus-manifest check made
> version-agnostic; `scripts/check_dist.py` is the allowlist every wheel and
> sdist must pass, run by `ci.yml`'s `package` job; `scripts/release_smoke.py`
> installs a built wheel, a TestPyPI file by its digest, a PyPI release, or the
> newest release, on a clean environment, and checks it;
> `.github/workflows/release.yml` builds once from a release tag on `main`,
> smokes the built wheel, publishes through OIDC from the `testpypi` or `pypi`
> environment after the operator's approval, smokes what it published, and opens
> the GitHub Release with the corpus archive;
> `.github/workflows/install-canary.yml` waits, weekly, for 2.0.0; the two
> environments, both trusted publishers (configured by the operator), and a
> ruleset that keeps release tags in place exist; `docs/RELEASING.md` is the
> runbook and `docs/release-readiness-2.0.0.md` the record; and a dispatched dry
> run on `main` builds and smokes on both runners while publishing nothing.

**Branch:** `feature/phase09-step2-release-pipeline`

**Deploys:** the repository's settings and workflows → GitHub: the `testpypi`
and `pypi` environments and the release-tag ruleset (created with the operator's
yes), `release.yml` and `install-canary.yml` (live on merge), and the trusted
publishers on PyPI and TestPyPI (configured by the operator in their own
browser). Nothing is published: the Deployed & verified check is a dispatched
dry run and a dispatched canary.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost                  | Balanced              | Quality            |
| ------------- | -------- | --------------------- | --------------------- | ------------------ |
| **Pick**      | Model    | **Gemini 4 Hydrogen** | **Gemini 4 Hydrogen** | **Opus 5.5**       |
|               | Platform | Gemini (web / app)    | Gemini (web / app)    | Claude Code        |
|               | Level    | Medium                | High                  | XHigh              |
|               | AA       | ≈48.8                 | ≈51.6                 | 56                 |
|               | Price    | ≈$2.62/1M             | ≈$3.00/1M             | $8.29/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**        | **Opus 5.5**          | **Gemini 4 Neon**  |
|               | Platform | Claude Code           | Claude Code           | Gemini (web / app) |
|               | Level    | XHigh                 | High                  | XHigh              |
|               | AA       | 51.9                  | 53.6                  | ≈56.9              |
|               | Price    | $3.72/1M              | $6.76/1M              | ≈$8.25/1M          |
| **Backup**    | Model    | **GPT-6.2 Sol**       | **GPT-6.2 Sol**       | **GPT-6.2 Sol**    |
|               | Platform | Codex                 | Codex                 | Codex              |
|               | Level    | Medium                | High                  | XHigh              |
|               | AA       | ≈49.8                 | ≈52.2                 | ≈53                |
|               | Price    | ≈$3.50/1M             | ≈$4.00/1M             | ≈$5.50/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels or its previous version's.

> Ran 2026-11-28: Quality Runner-up — Gemini 4 Neon · XHigh (Antigravity; ladder printed Gemini (web / app) from the 2026-11-19 refresh).

**Conversation:** New

> Settings updated 2026-11-19 (refresh): Cost Pick was Sonnet 5.5 · XHigh, Balanced Pick was Gemini
> 4 Argon · High, Cost Runner-up was Gemini 4 Argon · Low, Quality Runner-up was Gemini 4 Argon ·
> High, Cost Backup was GPT-6.1 Sol · XHigh, Balanced Backup was GPT-6 Astra · High, Quality Backup
> was GPT-6 Astra · XHigh. Re-ranked against the current roadmodel catalog.

**Model rationale:** Step 2 is coding with an agentic secondary category — three
scripts, two workflows, two environments, a ruleset, and two registry settings,
wired so an upload can happen only from a tag on `main`, after a smoke, behind
the operator's approval — at High complexity, not novel: PyPA's trusted-
publishing pattern is well documented, but this workflow is the project's widest
trust boundary, and a mistake in it is public and permanent rather than a red
check. On the step alone, the Quality Pick fits best: Opus 5.5 on Claude Code at
XHigh. It gives this classification priority for capability and reasoning depth.
The Cost Pick is Gemini 4 Hydrogen on Gemini (web / app) at Medium, and the
Balanced Pick is Gemini 4 Hydrogen on Gemini (web / app) at High.

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
       feature/phase09-step2-release-pipeline`
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
       Phase 9 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 9`
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

    THIS STEP builds the project's widest trust boundary. The workflows hold
    no secret: publishing uses OIDC, so no PyPI or TestPyPI token is ever
    created, stored, or pasted, and a publish job's only permission is
    `id-token: write`, inside its environment. Every action is pinned to the
    full commit SHA its release tag peels to (resolve it with `git ls-remote
    https://github.com/<owner>/<repo> 'refs/tags/<tag>^{}'`; an annotated
    tag's own SHA is not a commit) with a `# vX.Y.Z` comment; the workflow
    default is `permissions: {}`; no `run:` script interpolates `${{
    github.event.* }}`, a tag name, or any other untrusted value (pass them
    through `env:`); nothing runs on `pull_request_target` or a self-hosted
    runner. The environments, the ruleset, and the trusted publishers are
    repository and registry settings: create each only after the operator's
    yes, never approve a deployment through the API, and hand the operator the
    publisher values rather than asking for any credential.
    `scripts/check_dist.py` and `scripts/release_smoke.py` write only into
    temporary directories, and the smoke clears every `ANTHROPIC_*` and
    `WEATHERBOT_*` variable from the child's environment.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 9 (Release 2.0). Step 2: the release
    pipeline.

    Current state (as of Phase 8, post-Phase-9 Step 1):

    - The version, `2.0.0.dev0`, lives in `pyproject.toml` and `uv.lock` (`uv
      version <v>` sets both), reaches `weatherbot.__version__` through
      `importlib.metadata`, and is copied into `docs/api/openapi.json`
      (`scripts/export_openapi.py --check`),
      `frontend/src/test/fixtures/health.json`
      (`scripts/export_api_fixtures.py --check`), and `sources.USER_AGENT`
      (`weatherbot/<version>
      (+https://github.com/nathanramoscfa/weatherbot)`), which
      `docs/DATA_SOURCES.md`'s `## User-Agent` block spells.
      `tests/test_cli.py` pins `EXPECTED_VERSION = "2.0.0.dev0"`;
      `tests/contract/test_recorded_fixtures.py` asserts
      `manifest["user_agent"] == recorder.USER_AGENT == register_user_agent()`
      for every recorded manifest; `tests/contract/test_register.py` ties the
      register's block to `__version__`. Phase 1's check for the block needs
      only the repository URL and no `@`.
    - `ci.yml`'s `package` job builds the frontend, runs `uv build`, checks
      the sdist for `DISCLAIMER.md`, installs the wheel, and runs
      `scripts/smoke_installed_web.py`; Phase 5's check 32 needs the frontend
      build, `uv build`, and the smoke in that order. On 2026-11-18 the wheel
      held 186 files (the package, `weatherbot/DISCLAIMER.md`,
      `weatherbot/web/static/`) and the sdist `src/`, `pyproject.toml`,
      `pyproject.toml.orig`, `README.md`, `LICENSE`, `DISCLAIMER.md`, and
      `PKG-INFO`.
    - `scripts/smoke_installed_web.py` resolves `weatherbot` beside
      `sys.executable` or on `PATH`, starts `serve --no-open` in temporary
      directories with outbound traffic sent to a dead proxy, and checks
      `/api/health` and `/`. `weatherbot doctor --offline --json` exits 0 in
      empty temporary directories.
    - `scripts/fetch_replay_corpus.py`'s `load_manifest` raises unless
      `tests/fixtures/replay/corpus-manifest.json`'s `user_agent` equals the
      current `USER_AGENT`; `tests/replay/test_corpus_manifest.py` and
      `tests/replay/test_corpus_subset.py` call it in the default run,
      `replay-corpus.yml` runs it on every lock or `pyproject.toml` change,
      and Phase 1's `--post` needs that workflow's latest run on `main` green.
      The manifest's hash keys the replay cache, so it is never rewritten.
    - PyPI's `weatherbot` holds 1.0.0 only; TestPyPI answers 404 for it. The
      repository has no environments, no rulesets, and no GitHub Releases.
      `pypa/gh-action-pypi-publish`'s latest release on 2026-11-18 was
      `v1.14.3` (resolve its peeled commit; do not trust this line).
      `replay-corpus.yml` is the precedent for a `simulate_failure` dispatch
      input.
    - `tests/fixtures/replay/` (1,710 files holding 7.9 MB;
      `corpus-manifest.json` lists each file's size and SHA-256; `NOTICE.md`)
      is the committed corpus, which `ReplayCorpus` checks file by file as it
      reads.
    - Every workflow must keep Phase 1's rules: each `uses:` matches
      `<action>@<40 hex> # ... v<digit>...`, a top-level `permissions:`, and
      no `pull_request_target:`.

    Files to read (every file before drafting):

    - docs/roadmap/phase09-roadmap.md (Decisions 3 to 8, 13, and 15, and this
      step) and docs/roadmap/ROADMAP.md ("Release & deployment strategy",
      "Release & tagging").
    - pyproject.toml, src/weatherbot/__init__.py,
      src/weatherbot/sources/__init__.py, and docs/DATA_SOURCES.md (`##
      User-Agent`).
    - scripts/export_openapi.py, scripts/export_api_fixtures.py,
      scripts/smoke_installed_web.py, and scripts/check_personal_data.py.
    - tests/test_cli.py, tests/contract/test_recorded_fixtures.py,
      tests/contract/test_register.py, and tests/contract/fixture_support.py.
    - .github/workflows/ci.yml, .github/workflows/replay-corpus.yml, and
      .github/workflows/live-smoke.yml.
    - scripts/verify_phase01.py (the workflow pin and permission checks) and
      scripts/verify_phase05.py (check 32).
  </context>

  <goal>
    Ship the version tool, the allowlist, the smoke, the release and canary
    workflows, the environments, the ruleset, the runbook, and the readiness
    record, and prove the pipeline with a dry run that publishes nothing.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Kickoff, before writing workflow code: in the chat, ask the operator to
      confirm that they can sign in to pypi.org with two-factor authentication
      and see `weatherbot` under "Your projects" with the Owner role, and that
      they hold a test.pypi.org account with two-factor authentication (create
      one if not). A lost PyPI account blocks the release: if the operator
      cannot manage the project, stop and record it as a blocker in this
      roadmap's Step 2 before going on.
    </requirement>

    <requirement>
      `scripts/set_version.py <version>`: accept only `X.Y.Z`, `X.Y.ZrcN`, and
      `X.Y.Z.devN` (PEP 440 by `packaging.version`); run `uv version <version>
      --no-sync`; regenerate `docs/api/openapi.json`, the frontend's types
      (`npm --prefix frontend run api:generate`), and the API fixtures with
      the existing scripts; rewrite `docs/DATA_SOURCES.md`'s `## User-Agent`
      block to the new version; rewrite every
      `https://github.com/nathanramoscfa/weatherbot/blob/<ref>/` and
      `.../raw/<ref>/` link in `README.md` (never the `tree/v1.0.0` link to
      version 1) to `v<version>` for a candidate or a release and to `main`
      for a development version; and set the `Development Status` classifier
      (`2 - Pre-Alpha` for `.devN`, `4 - Beta` for `rcN`, `5 -
      Production/Stable` for a release). `--check` exits non-zero when any
      copy disagrees with `pyproject.toml`. It prints each file it changed.
    </requirement>

    <requirement>
      Tests for the version:
      - tests/test_release_metadata.py: the copies agree (`pyproject.toml`,
        the lock's `weatherbot` entry, `weatherbot.__version__`, the OpenAPI
        document's `info.version`, the health fixture, the register's block);
        the version is a PEP 440 version of one of the three shapes; a
        candidate or release carries `Development Status :: 4 - Beta` or `5 -
        Production/Stable`; and `set_version.py`'s logic round-trips in a
        temporary copy with its subprocess runner injected, so the unit test
        runs no `uv` or `npm`. The real round trip — `2.0.0rc1`, the full
        pytest suite, then `2.0.0.dev0` restoring every file byte for byte —
        runs once during this step in a temporary copy outside the repository
        (with `frontend/node_modules`), and the PR body records it.
      - tests/test_cli.py compares `weatherbot --version` with
        `importlib.metadata.version("weatherbot")`, never a literal.
      - tests/contract/test_recorded_fixtures.py checks each manifest's
        `user_agent` against `^weatherbot/<PEP 440 version>
        \(\+https://github\.com/nathanramoscfa/weatherbot\)$`, because a
        manifest records what was sent, while `register_user_agent() ==
        recorder.USER_AGENT` stays exact; tests/contract/test_register.py
        keeps tying the register to `__version__`. No recorded manifest is
        rewritten.
      - `scripts/fetch_replay_corpus.py`'s `load_manifest` accepts a
        `user_agent` of the same shape with any PEP 440 version and still
        refuses another shape, with a test in
        tests/scripts/test_fetch_replay_corpus.py; `corpus-manifest.json` is
        not rewritten.
      - README.md and CONTRIBUTING.md stop quoting `2.0.0.dev0` (say "prints
        the version").
    </requirement>

    <requirement>
      `scripts/check_dist.py DIST --version V` (standard library only):
      exactly one `weatherbot-V-py3-none-any.whl` and one
      `weatherbot-V.tar.gz`; the wheel holds only `weatherbot/` and
      `weatherbot-V.dist-info/` members, including
      `weatherbot/web/static/index.html`,
      `weatherbot/web/static/licenses.json`, `weatherbot/DISCLAIMER.md`,
      `weatherbot/py.typed`, and the Alembic versions, and no `__pycache__`,
      `.pyc`, `tests/`, `scripts/`, `frontend/`, `docs/`, `.env`, `.sqlite3`,
      or `.toml`; its `METADATA` reads `Name: weatherbot`, `Version: V`,
      `Requires-Python: >=3.13`, `License-Expression: MIT`, and
      `Description-Content-Type: text/markdown`; the sdist's top level is
      exactly `PKG-INFO`, `pyproject.toml`, `pyproject.toml.orig`,
      `README.md`, `LICENSE`, `DISCLAIMER.md`, and `src/`; the wheel stays
      under 5 MB; no text member holds the synthetic storm's identifiers
      (`AL802026`, `Hurricane Demo`), so no demonstration data ships; every
      text member passes `check_personal_data.py`'s CI rules (extract to a
      temporary directory first). It prints each file's size and SHA-256. Add
      it to `ci.yml`'s `package` job after `uv build` and before the smoke
      (Phase 5's check 32 order holds). Tests:
      tests/scripts/test_check_dist.py builds small fake distributions for
      each failure.
    </requirement>

    <requirement>
      `scripts/release_smoke.py` (standard library only) with three sources:
      `--wheel PATH`; `--index pypi|testpypi --version V [--sha256 HEX]`; and
      `--latest --min-version 2.0.0`; and `--python X`, passed to `uv tool
      install --python X` and used to create the `pip` environment, so each
      matrix entry tests its own Python. For TestPyPI it reads
      `https://test.pypi.org/pypi/weatherbot/V/json`, downloads the listed
      `py3-none-any` wheel, checks its SHA-256 against `--sha256`, and
      installs that file, so no dependency resolves through TestPyPI; for PyPI
      it runs `uv tool install weatherbot==V` and, separately, `pip install
      weatherbot==V` into a fresh virtual environment; `--latest` runs `uv
      tool install weatherbot` with nothing pinned and exits 0 with "no
      release at or above 2.0.0 on PyPI" while there is none. Each install
      uses temporary `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR`, data, and configuration
      directories, a `PATH` from which every directory holding `node` is
      removed (asserting `shutil.which("node")` is `None`), and an environment
      without `ANTHROPIC_*` or `WEATHERBOT_*`; it then checks `weatherbot
      --version`, `weatherbot doctor --offline --json` (exit 0),
      `scripts/smoke_installed_web.py` against the installed executable, and
      on Windows that the installed environment's Python imports
      `winrt.windows.ui.notifications` and `winrt.windows.data.xml.dom` and
      loads the toast channel's XML into an `XmlDocument` without showing a
      toast. It polls an index's JSON for up to ten minutes before installing.
      Tests: tests/scripts/test_release_smoke.py with the network and
      `subprocess` replaced.
    </requirement>

    <requirement>
      `.github/workflows/release.yml`, on GitHub-hosted runners only:
      - `on: push: tags: ["v[0-9]+.[0-9]+.[0-9]+",
        "v[0-9]+.[0-9]+.[0-9]+rc[0-9]+"]` and `workflow_dispatch` (a dry run);
        top-level `permissions: {}`; `concurrency: { group: release-${{
        github.ref }}, cancel-in-progress: false }`; `env: UV_LOCKED: "1"`.
      - `build` (`contents: read`): checkout with full history and
        `persist-credentials: false`; for a tag, require `v` + `uv version
        --short` to equal the tag and `git merge-base --is-ancestor
        "$GITHUB_SHA" origin/main`; for a dispatch, require the ref to be
        `main`; `npm --prefix frontend ci`, the frontend build, `uv build`,
        `uv run python scripts/check_dist.py dist --version <v>`; zip
        `tests/fixtures/replay/` into `weatherbot-replay-corpus-<v>.zip` with
        a `.sha256` file; upload `dist` and `corpus` as artifacts; output the
        version, whether it is a candidate, and the wheel's SHA-256.
      - `smoke-built` (needs `build`; `contents: read`; matrix `os:
        [ubuntu-latest, windows-latest]`, `python: ["3.13", "3.15"]`):
        download `dist` and run `release_smoke.py --wheel <the wheel> --python
        ${{ matrix.python }}`.
      - `publish-testpypi` (a candidate tag only; needs `smoke-built`;
        `environment: { name: testpypi, url:
        https://test.pypi.org/project/weatherbot/<v>/ }`; `permissions: {
        id-token: write }`): download `dist` and run
        `pypa/gh-action-pypi-publish` with `repository-url:
        https://test.pypi.org/legacy/`. `publish-pypi` (a release tag only;
        `environment: pypi`): the same against PyPI. The action generates the
        attestations.
      - `smoke-published` (needs both publish jobs, with `if: ${{ !cancelled()
        && (needs.publish-testpypi.result == 'success' ||
        needs.publish-pypi.result == 'success') }}`, because a job that needs
        a skipped job is otherwise skipped too; matrix as above), with
        `--python ${{ matrix.python }}`: `release_smoke.py --index testpypi
        --version <v> --sha256 <wheel digest>` or `--index pypi --version
        <v>`.
      - `github-release` (needs `smoke-published`, with `if: ${{ !cancelled()
        && needs.smoke-published.result == 'success' }}`; `permissions: {
        contents: write }`; a checkout of the tag for `CHANGELOG.md`;
        `GH_TOKEN: ${{ github.token }}` in its environment): `gh release
        create "v$VERSION" --verify-tag --title "Weatherbot $VERSION"
        --notes-file <notes> dist/* corpus/*`, with `--prerelease` for a
        candidate, where the notes are the version's summary from
        `CHANGELOG.md` (its section's text before the first `###` heading) and
        a link to the full section at the tag, because the whole version 2
        section approaches GitHub's 125,000-character limit for release notes.
    </requirement>

    <requirement>
      `.github/workflows/install-canary.yml`: `schedule` weekly (a fixed
      off-hour minute, such as `cron: "41 9 * * 2"`) and `workflow_dispatch`
      with a boolean `simulate_failure`; a `run-name` that says when a run
      simulates a failure (`${{ inputs.simulate_failure && 'install-canary
      (simulated failure)' || 'install-canary' }}`), so a probe can find the
      latest real run; `permissions: contents: read`; matrix `os:
      [ubuntu-latest, windows-latest]`; `release_smoke.py --latest
      --min-version 2.0.0`; a final step that fails on purpose when
      `simulate_failure` is true, after the smoke, as `replay-corpus.yml`'s
      does. Tests: tests/test_release_workflow.py reads both workflows at the
      text level, as the verifiers' `job()` helper does (PyYAML is only a
      transitive dependency, has no stubs under pyright's strict mode, and
      loads `on:` as `True`), and asserts every rule in this step's acceptance
      criteria.
    </requirement>

    <requirement>
      Repository settings, each after the operator's yes, through `gh api`:
      the environments `testpypi` and `pypi`, each with the operator as
      required reviewer and a deployment policy admitting tags only (`v*`), so
      no branch can deploy — the workflow's tag filter is what limits a run to
      release tags — and self-review allowed, because the operator both pushes
      and approves; and a tag ruleset on `refs/tags/v*` blocking deletion,
      update, and non-fast-forward, with no bypass actor. Read each back and
      record the readbacks (no token or personal value) in the PR body.
    </requirement>

    <requirement>
      Trusted publishers, configured by the operator: give them, in the chat,
      the exact values for PyPI (project `weatherbot` → Manage → Publishing →
      add a GitHub publisher: owner `nathanramoscfa`, repository `weatherbot`,
      workflow `release.yml`, environment `pypi`) and for TestPyPI (Publishing
      → add a pending publisher: project name `weatherbot`, the same owner and
      repository, workflow `release.yml`, environment `testpypi`); then ask,
      with AskUserQuestion, whether both are saved. Neither can be proved
      before an upload; Step 5's candidate proves TestPyPI's, Step 7 PyPI's,
      and `docs/RELEASING.md` says what to do if a publish job is refused.
    </requirement>

    <requirement>
      `docs/RELEASING.md` (new): the version shapes and tags;
      `set_version.py`; the readiness record; cutting a candidate and a
      release (the PR, the operator's yes, `git tag -a v<version> -m
      "Weatherbot <version>"` on the merge commit, `git push origin
      v<version>`, the operator's approval in the environment); what each job
      does; the smokes and the GitHub Release; yank and patch (the yank in the
      project's release options with a reason, the next version through the
      same path, and why a version is never re-uploaded); the operator's
      upgrade and rollback recipes (Decision 16); the canary, its alarm, and
      GitHub's rule that disables a public repository's schedules after 60
      days without activity (how to see it, and `gh workflow enable`); and the
      failure modes (a tag that does not match the version, a refused OIDC
      exchange, a slow index, a failed smoke after upload). Add a "Releasing"
      pointer to `CONTRIBUTING.md`.
    </requirement>

    <requirement>
      `docs/release-readiness-2.0.0.md` (new): one table row per Decision 13
      item (the item, its evidence, the step that fills it, and its state),
      Step 1's rows filled from its PR (the lock upgrade, pywinrt 4 and the
      desktop toast, Python 3.13 and 3.15, the Dependabot dispositions), and
      the sign-off line left for Step 7. Add `### Phase 9 — Release 2.0`
      entries to `CHANGELOG.md` for this step.
    </requirement>

    <requirement>
      After the merge (Deployed & verified): dispatch `release.yml` on `main`
      and `install-canary.yml` on `main` (both publish nothing), wait for both
      with `gh run watch`, and report the run URLs and results in the chat; a
      workflow file must be on `main` before it can be dispatched, so Step 5's
      pull request copies them into `docs/release-readiness-2.0.0.md`'s Step 2
      rows, and this roadmap's Step 5 `<context>` gains a line naming them
      (Stage 6).
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative path as the
      first line where the file type accepts comments.
    </requirement>
  </requirements>
</task>
```

### Step 2 acceptance criteria

- `scripts/set_version.py` run in a scratch copy of the checkout with `2.0.0rc1`
  changes `pyproject.toml`, `uv.lock`, `README.md`'s pinned links,
  `docs/api/openapi.json`, `frontend/src/api/schema.d.ts` (if it carries the
  version), `frontend/src/test/fixtures/health.json`, the register's User-Agent
  block, and the `Development Status` classifier, after which the full pytest
  suite (`tests/replay/` and `tests/contract/` included) and every `--check`
  export pass there; `2.0.0.dev0` restores the checkout byte for byte (test).
- `scripts/check_dist.py` passes in `ci.yml`'s `package` job on all four entries
  and fails, in its tests, on a wheel holding `tests/`, a wheel without
  `weatherbot/web/static/index.html`, a second wheel, a version mismatch, and an
  sdist with an unlisted top-level path.
- `tests/test_release_workflow.py` passes: `release.yml` runs only on the two
  release-tag patterns and `workflow_dispatch`; its top-level permissions are
  `{}`; `id-token: write` appears only in `publish-testpypi` and `publish-pypi`,
  each in its environment, and `contents: write` only in `github-release`; both
  publish jobs need `smoke-built`; `smoke-published` runs when either publish
  job succeeded and `github-release` only after it; every `uses:` is a full SHA
  with a `# vX.Y.Z` comment; nothing interpolates `github.event` or a tag name
  into a `run:` script; and its concurrency never cancels a release.
  `install-canary.yml` passes the same pin and permission rules.
- `gh api` reads back both environments with the operator as required reviewer,
  tags as the only deployment refs, and self-review allowed, and the ruleset
  active with deletion, update, and non-fast-forward blocked for `refs/tags/v*`;
  the operator has confirmed the PyPI and TestPyPI trusted publishers with the
  exact values, and that they manage the PyPI project with two-factor
  authentication.
- `docs/RELEASING.md` covers versions, tags, the record, a candidate, a release,
  the approvals, the smokes, the GitHub Release, yank and patch, the operator's
  upgrade and rollback, the canary, and the failure modes;
  `docs/release-readiness-2.0.0.md` lists every Decision 13 item with Step 1's
  rows filled in.
- **Deployed & verified:** after the merge, `gh workflow run release.yml --ref
  main` completed with `build` and all four `smoke-built` entries green and
  every publish and release job skipped, its artifacts holding one wheel, one
  sdist, and the corpus archive with its `.sha256`; `gh workflow run
  install-canary.yml --ref main` completed green, reporting that PyPI has no 2.x
  release yet.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff, and the workflows were reviewed as a trust
  boundary — no repository secret, no long-lived PyPI or TestPyPI token
  anywhere, least-privilege permissions per job, SHA-pinned actions (each
  resolved from the release tag's peeled commit), no untrusted expression in a
  script, GitHub-hosted runners only — and no repository setting changed without
  the operator's yes.

---

## Step 3 — LAN mode

**Status:** Not started

> **Goal:** Let the operator's phone on the home network open the dashboard,
> behind a token, without changing anything a loopback request sees (Decision
> 9). `[web] lan`, `lan_address`, and `lan_hosts` join `WebSettings` with their
> overrides; `src/weatherbot/services/lan.py` reads and checks
> `WEATHERBOT_WEB_TOKEN`, signs and verifies session cookies, and limits failed
> authentications and LAN request rates; `src/weatherbot/web/server.py` binds a
> second socket on the LAN address and port beside the loopback one;
> `src/weatherbot/web/guards.py` gains `LanAuthGuard`, which exempts only a
> request whose client and listening addresses are both loopback and admits
> every other API request only with the bearer token or a valid session cookie,
> and `ListenerHostGuard`, which accepts loopback names on the loopback socket
> and LAN names on the LAN socket; `src/weatherbot/web/routes/session.py` serves
> `POST` and `DELETE /api/session`; `/api/health` reports `lan`, `doctor`'s
> `web` check reads it, and the app shell shows a LAN chip; the SPA's token
> prompt answers a 401 and browser notifications report themselves unavailable
> outside a secure context; `cli/serve.py` keeps the LAN listener down, with
> loopback serving on, when the token or the address is unusable, and warns at
> every LAN start; and `docs/LAN.md` documents it as not yet supported, until
> Step 6's gate.

**Branch:** `feature/phase09-step3-lan-mode`

**Deploys:** nothing beyond merge. LAN mode is off by default, the operator's
service is not reinstalled here, and the first non-loopback bind is Step 6's,
after rc1 carries this code.

Settings — ladder (`roadmodel ladder --category coding --complexity high
--novel`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **Gemini 4 Neon**  | **Opus 5.5**       | **Opus 5.5**       |
|               | Platform | Gemini (web / app) | Claude Code        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | ≈54.9              | 53.6               | 56                 |
|               | Price    | ≈$6.00/1M          | $6.76/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **Opus 5.5**       | **Gemini 4 Neon**  | **Gemini 4 Neon**  |
|               | Platform | Claude Code        | Gemini (web / app) | Gemini (web / app) |
|               | Level    | Medium             | High               | XHigh              |
|               | AA       | 51.2               | ≈54.9              | ≈56.9              |
|               | Price    | $6.39/1M           | ≈$6.00/1M          | ≈$8.25/1M          |
| **Backup**    | Model    | **GPT-6.2 Sol**    | **GPT-6.2 Sol**    | **GPT-6.2 Sol**    |
|               | Platform | Codex              | Codex              | Codex              |
|               | Level    | Medium             | High               | XHigh              |
|               | AA       | ≈49.8              | ≈52.2              | ≈53                |
|               | Price    | ≈$3.50/1M          | ≈$4.00/1M          | ≈$5.50/1M          |

Ranked for coding, high complexity, novel. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level. ≈
estimated from the model's measured levels or its previous version's.

**Conversation:** New

> Settings updated 2026-11-19 (refresh): Cost Pick was Gemini 4 Argon · High, Balanced Runner-up was
> Gemini 4 Argon · Medium, Quality Runner-up was Gemini 4 Argon · High, Cost Backup was GPT-6 Astra
> · Medium, Balanced Backup was GPT-6 Astra · High, Quality Backup was GPT-6 Astra · XHigh. Re-
> ranked against the current roadmodel catalog.

**Model rationale:** Step 3 is coding with a planning secondary category — the
project's first authentication path: a second listener, a token that must never
leak, signed cookies, constant-time comparisons, two limiters, a guard that must
leave every loopback behaviour unchanged, and a token prompt in the SPA — at
High complexity and novel, because nothing in the codebase authenticates a
request today and an error here is a hole in the home network rather than a
failing test. On the step alone, the Quality Pick fits best: Opus 5.5 on Claude
Code at XHigh. It gives this classification priority for capability and
reasoning depth. The Cost Pick is Gemini 4 Neon on Gemini (web / app) at High,
and the Balanced Pick is Opus 5.5 on Claude Code at High.

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
       feature/phase09-step3-lan-mode`
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
       Phase 9 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 9`
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

    THIS STEP builds the project's first authenticated surface, so the gate
    reads the diff as an attacker on the same Wi-Fi would: no route may answer
    a request that arrived on the LAN socket without the token or a valid
    session; `WEATHERBOT_WEB_TOKEN` is read from the environment only (never a
    `Settings` field, an `ENVIRONMENT_OVERRIDES` entry, `weatherbot.toml`,
    `/api/settings`, a query string, a log, an error, a response, the
    database, or a fixture); every comparison uses `hmac.compare_digest`; the
    session cookie is `HttpOnly` and `SameSite=Strict` and keyed by the token,
    so rotating the token revokes it; the limiters are bounded in memory; no
    header can make a LAN request look like a loopback one (the guard exempts
    only a request whose ASGI `client` and `server` addresses both parse as
    loopback, treats a missing or unparseable address as a LAN request, and
    uvicorn keeps `proxy_headers=False`); and `SecretFilter` redacts the
    token's value and assignment like the ntfy topic's. Tests build tokens at
    run time and use documentation addresses only; the operator's LAN address
    never enters the repository.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 9 (Release 2.0). Step 3: LAN mode.

    Current state (as of Phase 8, post-Phase-9 Step 2):

    - `services/config.py`'s `WebSettings` holds `host` (a validator refuses
      anything but `127.0.0.1`, `::1`, or `localhost`; its message still says
      "remote access belongs to Phase 8"), `port`, and `corpus`;
      `ENVIRONMENT_OVERRIDES` maps `("web", ...)` to `WEATHERBOT_WEB_*`, and
      `load_settings` merges an override as the raw string, so a list-valued
      key needs a `mode="before"` validator that splits on commas.
      `settings_file.EDITABLE` holds 12 keys and no `[web]` key, and Phase 7's
      check 25 pins that.
    - `web/server.py`'s `WebServer` binds one socket through
      `_create_bound_socket` (`SO_EXCLUSIVEADDRUSE` on Windows) and serves
      uvicorn on it with `proxy_headers=False` and `limit_concurrency=64`;
      `_bind_address` treats only `::1` as IPv6. uvicorn's
      `Server.serve(sockets=[...])` accepts several sockets, and its ASGI
      scope carries `server` (the listening socket's address) and `client`
      (the peer).
    - `web/guards.py`: `SecurityHeadersMiddleware` (outermost),
      `TrustedHostMiddleware` over the fixed `ALLOWED_HOSTS`, and
      `FetchMetadataAndWriteGuard` (a write whose `Sec-Fetch-Site` is not
      `same-origin` or whose `Origin` is not `http://<Host>` is refused, every
      write is JSON, and a write carrying neither header passes); `CSP_SUFFIX`
      is pinned exactly by Phase 7's check 35. uvicorn puts each connection's
      canonical local address text in the scope's `server` (it can be `None`),
      and Starlette compares a bracketed IPv6 `Host` as text.
    - Pins this step must keep: Phase 5's check 4 (`ALLOWED_HOSTS` exactly
      `("127.0.0.1", "localhost", "[::1]")`), check 5 (`server.py`'s
      `EmbeddedUvicornServer`, a `uvicorn.Server` subclass with
      `capture_signals`, a `SystemExit` catch, `SO_EXCLUSIVEADDRUSE`,
      `timeout_graceful_shutdown`), and check 6 (`ENVIRONMENT_OVERRIDES` a
      literal dict); Phase 7's check 16 (no settings field whose name contains
      `token` or `topic`) and check 22 (`_NTFY_TOKEN_SHAPE`,
      `_SECRET_ENV_VARS`, and both ntfy names in `logs.py`).
    - `services/logs.py`'s `SecretFilter` and `redact_secrets` redact
      `ANTHROPIC_API_KEY`, `WEATHERBOT_NTFY_TOPIC`, and
      `WEATHERBOT_NTFY_TOKEN`; `services/doctor.py`'s `web_check` probes
      `/api/health` on loopback; `docs/NOTIFICATIONS.md` documents setting a
      secret in the Windows User environment variables, which is the precedent
      for the token.
    - The SPA calls the API through `openapi-fetch`
      (`frontend/src/api/client.ts`, which supports middleware) and the event
      stream through `EventSource("/api/events")`
      (`frontend/src/events/useEventStream.ts`); an `EventSource` that
      receives a 401 closes and does not retry.
      `frontend/src/notifications/notify.ts` is the only file that may call
      `new Notification(` (Phase 5's check 39). `AppShell.tsx` keeps
      `NAV_ITEMS` one `{ to: "…", label: "…"` object per line with no other `{
      to:` object in the file (Phase 6's check 40, Phase 7's check 48), and
      every route keeps its exact `<h1>`.
    - Step 2 left `scripts/set_version.py`, `scripts/check_dist.py`,
      `scripts/release_smoke.py`, and `tests/test_release_metadata.py`; this
      step regenerates the OpenAPI document, the frontend's types, and the
      fixtures with the existing export scripts, not by hand, and the version
      stays `2.0.0.dev0`.

    Files to read (every file before drafting):

    - docs/roadmap/phase09-roadmap.md (Decisions 1, 9, 10, and 15, and this
      step).
    - src/weatherbot/services/config.py,
      src/weatherbot/services/settings_file.py,
      src/weatherbot/services/logs.py, and src/weatherbot/services/doctor.py
      (`web_check`).
    - src/weatherbot/web/server.py, src/weatherbot/web/guards.py,
      src/weatherbot/web/app.py, src/weatherbot/web/schemas.py
      (`HealthResponse`), and src/weatherbot/web/routes/health.py.
    - src/weatherbot/cli/serve.py and src/weatherbot/cli/runtime.py.
    - tests/web/ (the guard and server tests and their fixtures),
      tests/services/test_doctor*.py, and tests/conftest.py.
    - frontend/src/api/client.ts, frontend/src/events/useEventStream.ts,
      frontend/src/notifications/notify.ts, frontend/src/app/AppShell.tsx, and
      frontend/src/main.tsx.
    - docs/NOTIFICATIONS.md ("Setting up ntfy") and SECURITY.md.
  </context>

  <goal>
    Ship LAN mode, off by default and documented as not yet supported: a
    second, authenticated listener on one LAN address, the token, sessions,
    limits, the refusals, the warning, the health and `doctor` signals, and
    the token prompt, with every loopback behaviour unchanged.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Settings. `WebSettings` gains `lan: bool = False`, `lan_address: str =
      ""`, and `lan_hosts: list[str] = []`, with the overrides
      `WEATHERBOT_WEB_LAN`, `WEATHERBOT_WEB_LAN_ADDRESS`, and
      `WEATHERBOT_WEB_LAN_HOSTS` (comma-separated, split by a `mode="before"`
      validator). `lan_address` must parse with `ipaddress.ip_address`, is
      stored as its `.compressed` form, and must be none of loopback,
      unspecified (`0.0.0.0`, `::`), multicast, link-local, or globally
      routable (`is_global`), so only a private or shared-space address of
      this machine passes; a model validator requires it when `lan` is true.
      Each `lan_hosts` entry is a lowercase host name (RFC 1123 labels) or an
      address, never `*` and never with a port. `host` keeps its loopback-only
      rule, with a message that points at `[web] lan` instead of "Phase 8".
      `[web]` stays out of `EDITABLE`. Regenerate
      `docs/schema/config.schema.json` with `scripts/export_schemas.py`.
    </requirement>

    <requirement>
      `src/weatherbot/services/lan.py` (new; services may be imported by `cli`
      and `web`):
      - `TOKEN_VARIABLE = "WEATHERBOT_WEB_TOKEN"`, `MIN_TOKEN_LENGTH = 32`,
        and `lan_token(environ) -> str` raising a `LanConfigError` whose
        message names the problem (unset, too short, whitespace) and never the
        value.
      - `lan_problems(web, environ) -> tuple[str, ...]`: every reason LAN mode
        cannot start, for `serve` and `doctor` alike.
      - `SessionSigner(token, clock)`: `issue() -> str` returns
        `<expiry>.<nonce>.<mac>`, where `mac` is base64url HMAC-SHA-256 over
        `<expiry>.<nonce>` keyed by a key derived from the token, expiring
        after 30 days; `verify(value) -> bool` parses defensively, checks the
        expiry against the injected clock, and compares with
        `hmac.compare_digest`.
      - `FailureLimiter` (at most 5 failed bearer tokens or `POST
        /api/session` attempts per peer address, and 30 across all peers, per
        5 minutes; `retry_after(peer)` in whole seconds),
        `LAN_CONNECTION_LIMIT` (16 concurrent LAN connections, below the
        server's 64), and `RateLimiter` (a token bucket per LAN peer whose
        capacity is at least three times the dashboard burst you measure in
        this step), each on an injected monotonic clock and each holding at
        most 1,024 peers (least recently seen evicted).
    </requirement>

    <requirement>
      The server. `WebServer` takes an optional `lan_address`; it binds the
      loopback socket first, then the LAN socket on the port the loopback
      socket actually bound (so `port = 0` still works), chooses `AF_INET6`
      for any IPv6 literal, and serves both through one uvicorn server. A LAN
      bind failure logs a WARNING naming the error type, leaves loopback
      serving, and sets `lan_listening = False`; a loopback bind failure keeps
      today's behaviour. `cli/serve.py` calls `lan_problems` before binding;
      when LAN mode is on and anything is wrong, it logs each reason at ERROR
      (never a value), binds loopback only, and keeps monitoring, because a
      configuration mistake must never stop the monitor; otherwise it prints
      to standard error and logs at WARNING, at every LAN start, one warning
      naming the address and port, that the traffic is unencrypted HTTP, that
      anyone on the network holding the token can read the locations, change
      settings, spend the AI allowance, and prune history, that LAN mode
      belongs on a trusted home network only, and how to turn it off (`[web]
      lan = false`, or unset `WEATHERBOT_WEB_LAN`).
    </requirement>

    <requirement>
      The guards. With LAN mode off, `install_guards` is unchanged. With it
      on, `install_guards(app, lan=...)` replaces Starlette's
      `TrustedHostMiddleware` with `ListenerHostGuard`, which applies
      `ALLOWED_HOSTS` (unchanged) to requests on the loopback socket and only
      `lan_address` (canonical, bracketed when IPv6) and `lan_hosts` to
      requests on the LAN socket (400 otherwise), and adds `LanAuthGuard`
      inside `SecurityHeadersMiddleware`. A request is exempt only when its
      ASGI `client` and `server` addresses both parse as loopback; any other
      request, a missing or unparseable address included, is a LAN request,
      decided by addresses and never by a header. A LAN request to `/api/`
      other than `POST /api/session` needs `Authorization: Bearer <token>` or
      a valid `weatherbot_session` cookie, else 401 with `WWW-Authenticate:
      Bearer` and a JSON detail (a stale cookie is expired in the same
      answer); a LAN `GET` of the built shell and its static files needs
      neither, because the bundle holds no data and is published in the wheel.
      A failed bearer token counts against `FailureLimiter` (429 with
      `Retry-After` once exceeded, checked before any comparison); a missing
      or invalid cookie never counts. Admitted LAN requests count against
      `RateLimiter`, and connections beyond `LAN_CONNECTION_LIMIT` answer 503.
      A cookie-authenticated LAN write must also carry `Sec-Fetch-Site:
      same-origin` (browsers always send it), else 403; a bearer-authenticated
      write passes the existing `FetchMetadataAndWriteGuard`. That guard, the
      CSP, and `CSP_SUFFIX` do not change.
    </requirement>

    <requirement>
      Routes and health. `src/weatherbot/web/routes/session.py`: `POST
      /api/session` takes `{"token": str}` and answers 204 with `Set-Cookie:
      weatherbot_session=<value>; HttpOnly; SameSite=Strict; Path=/;
      Max-Age=2592000` when the token matches (401 and a counted failure when
      not), and 404 when LAN mode is off; `DELETE /api/session` answers 204
      and expires the cookie. `HealthResponse` gains `lan: LanHealth`
      (`enabled`, `address` or null, `listening`), never the token. Regenerate
      `docs/api/openapi.json` (`scripts/export_openapi.py`), the frontend's
      types (`npm --prefix frontend run api:generate`), and the API fixtures
      (`scripts/export_api_fixtures.py`). `doctor`'s `web` check names LAN
      mode and its address when on, and fails when `lan_problems` reports
      anything or `/api/health` says the LAN socket is not listening.
      `SecretFilter` adds `WEATHERBOT_WEB_TOKEN` to `_SECRET_ENV_VARS` and to
      the assignment pattern.
    </requirement>

    <requirement>
      The SPA. A middleware in `frontend/src/api/client.ts` turns a 401 from
      `/api/` into an app-level "token needed" state; the app shell then
      renders `frontend/src/lan/TokenPrompt.tsx` (a labelled password input
      and a submit button, plain text only, keyboard-reachable, in the Phase 8
      design system), which posts `/api/session` once and reloads the page on
      204, so the event stream reconnects with the cookie. The shell's header
      shows a "LAN mode" chip with the address when `/api/health` reports
      `lan.enabled`, outside `NAV_ITEMS`. `notify.ts` reports browser
      notifications unavailable, with a sentence pointing at ntfy, when
      `window.isSecureContext` is false. No npm package is added; no `style=`,
      `innerHTML`, or new `{ to:` object enters; every route keeps its `<h1>`.
    </requirement>

    <requirement>
      Measure the dashboard burst: start `scripts/serve_demo.py --scenario
      landfall` on a free loopback port, load `/` with Playwright, count the
      requests until the page settles (the event stream included), stop the
      server, and set `RateLimiter`'s capacity to at least three times that
      count; record the count and the setting in the PR body. Stop every
      server you start.
    </requirement>

    <requirement>
      `docs/LAN.md` (new): a "Status: not yet supported — rehearsed in Phase 9
      Step 6" line at the top; what LAN mode is for (the phone on the home
      network) and what it is not (public access, TLS); generating the token
      in the operator's own terminal (`python -c "import secrets;
      print(secrets.token_urlsafe(24))"`) and setting it in the Windows User
      environment variables, never on a command line; finding the machine's
      LAN address (`ipconfig`) and setting `[web] lan`, `lan_address`, and
      optionally `lan_hosts`, with documentation-range examples
      (`192.0.2.20`); the Windows Defender Firewall rule for the Private
      profile, the port, and the address only (`New-NetFirewallRule`, from an
      elevated PowerShell), and the dialog Windows may raise on the desktop at
      the first LAN start, whose Cancel creates block rules that override the
      port rule; restarting `\Weatherbot\serve`; opening the dashboard on the
      phone and entering the token; the risks (unencrypted HTTP on a shared
      network, the cookie's 30 days, anyone with the token can change
      settings); rotating the token; turning LAN mode off; and what `doctor`
      and the status chip show.
    </requirement>

    <requirement>
      Tests:
      - tests/services/test_lan.py: the token rules; `lan_problems` for every
        refusal; the signer (issue, verify, expiry, tamper, another token);
        both limiters (windows, `Retry-After`, eviction at 1,024 peers).
      - tests/services/test_lan_settings.py: `lan_address` and `lan_hosts`
        validation, the override split, the model validator, and `[web]`
        absent from `EDITABLE`.
      - tests/web/test_lan_guard.py: through the ASGI app with explicit
        `client` and `server` addresses (a raw ASGI scope, or a transport that
        sets both): the 401 matrix, missing and unparseable addresses
        included; the static shell; bearer; cookie; tampered, expired, and
        old-token cookies, each expired in the answer; token rotation; the
        per-listener hosts (400 both ways); 403 for a cookie-authenticated
        write without `same-origin`; 429 after five failed tokens from one
        peer and thirty from all; a stale cookie never counted; the connection
        cap; the dashboard burst inside the limit; a loopback request
        untouched; and no response holding the token.
      - tests/web/test_lan_server.py: two sockets through `socket_factory`; a
        refusing LAN socket leaves loopback serving with `lan_listening`
        false; `port = 0`.
      - tests/cli/test_serve_lan.py: for each problem, the LAN listener kept
        down, loopback serving, and the reason logged at ERROR with no value;
        the warning on standard error and in the log at WARNING; a token built
        at run time absent from every captured stream.
      - tests/services/test_doctor_lan.py (or the existing doctor test file):
        pass, fail on a problem, fail when not listening.
      - Vitest: `frontend/src/lan/TokenPrompt.test.tsx` (prompt on 401, post,
        reload, error on 401), the chip, and `notify.ts` in an insecure
        context.
    </requirement>

    <requirement>
      Record the decision in `CHANGELOG.md` under `### Phase 9 — Release 2.0`
      (LAN mode, off by default, documented as not yet supported) and add LAN
      mode's line to `SECURITY.md` ("What counts as a vulnerability here"
      already names a non-loopback bind without the token; add a request
      admitted on the LAN socket without the token or a session).
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative path as the
      first line where the file type accepts comments.
    </requirement>
  </requirements>
</task>
```

### Step 3 acceptance criteria

- With `[web] lan = false` (the default), `serve` binds the loopback socket only
  and every existing test passes unchanged; no route, header, or response
  differs for a loopback request.
- With `[web] lan = true` and `WEATHERBOT_WEB_TOKEN` unset, shorter than 32
  characters, or holding whitespace, or `lan_address` empty, loopback,
  unspecified, multicast, link-local, or globally routable, the LAN listener
  never binds: `serve` logs each reason at ERROR (never a value), keeps
  monitoring and serving loopback, and `/api/health` and `doctor`'s `web` check
  report it; `lan_hosts` refuses `*`, a port, and anything that is not a host
  name or an address; `lan_address` is stored in its canonical form (tests).
- A request that is not loopback-to-loopback — one with a missing or unparseable
  client or server address included — answers 401 without credentials on every
  `/api/` path except `POST /api/session`, while the built shell and its assets
  answer 200; the bearer token and a valid session cookie each admit it; a
  tampered, expired, or old-token cookie answers 401 and is expired; a LAN name
  on the loopback socket and a loopback name on the LAN socket each answer 400;
  and a cookie-authenticated LAN write without `Sec-Fetch-Site: same-origin`, or
  with a foreign `Origin`, answers 403 (tests through the ASGI app with explicit
  client and server addresses).
- The sixth failed bearer token or `POST /api/session` from one peer within five
  minutes, or the thirtieth from all peers, answers 429 with `Retry-After`; a
  stale cookie never counts; the limiters' memory is bounded; LAN connections
  are capped below the server's 64; and a measured dashboard load with its event
  stream stays inside the request-rate limit with at least three times headroom
  (tests; the measured burst is recorded in the PR body).
- `POST /api/session` sets a cookie with `HttpOnly`, `SameSite=Strict`,
  `Path=/`, and `Max-Age`, answers 404 when LAN mode is off, and `DELETE
  /api/session` clears it; changing the token revokes every session (tests).
- When the LAN socket cannot bind, loopback serves on, `/api/health` reports
  `lan.listening` false, and `doctor`'s `web` check fails saying why, never with
  a value (test with a refusing socket factory); with LAN on and listening, the
  check passes and names LAN mode.
- Every start with LAN on prints the warning to standard error and logs it at
  WARNING; no response body, log record, stored row, exception, or URL ever
  holds the token (tests scan for a token built at run time).
- The SPA shows the token prompt on a 401, reloads after a successful `POST
  /api/session`, shows the LAN chip from `/api/health`, and reports browser
  notifications unavailable when `window.isSecureContext` is false (Vitest); the
  readability gate and every Playwright spec pass.
- `docs/LAN.md` exists, says "not yet supported" at the top, and covers the
  token, the address, the firewall rule, the phone, the risks, and turning it
  off; `[web]` is still outside `EDITABLE`; `CSP_SUFFIX` is unchanged;
  `docs/api/openapi.json`, the frontend's generated types, the API fixtures, and
  `docs/schema/config.schema.json` are regenerated and their `--check` runs
  pass.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean
  (no new bandit or ESLint finding), dependency audit clean (no package added) —
  and the authentication path was reviewed against the data classification: the
  token is read from the environment only, compared in constant time, redacted
  from every log, and absent from every URL, response, and fixture; every test
  token and address is built at run time from documentation ranges
  (192.0.2.0/24, 2001:db8::/32).

---

## Step 4 — Documentation

**Status:** Not started

> **Goal:** Write the documentation for someone who installed from PyPI
> (Decisions 11 and 12). `README.md` becomes the PyPI page — what Weatherbot is
> and never is, a screenshot, the install, a quick start, the commands, the
> dashboard, the documents, and the disclaimer — with every link absolute and
> pinned by `scripts/set_version.py`; `docs/GUIDE.md` runs from install to
> uninstall; `docs/CONFIGURATION.md` is generated by
> `scripts/export_config_reference.py` from `Settings`, `ENVIRONMENT_OVERRIDES`,
> and `EDITABLE`, with a test that fails when it is stale; `docs/ALWAYS-ON.md`,
> `docs/TROUBLESHOOTING.md`, and `docs/MIGRATING.md` are new; `docs/AI.md`,
> `docs/ALERT-LADDER.md`, `docs/DATA_SOURCES.md`, `docs/NOTIFICATIONS.md`,
> `docs/LAN.md`, `SECURITY.md`, and `CONTRIBUTING.md` are read against the
> installed product and corrected; `frontend/playwright.docs.config.ts` and
> `frontend/docs-capture/capture.spec.ts` capture the screenshots into
> `docs/images/`; `tests/test_docs.py` holds the links, the README's needles,
> the guide's coverage of every command and setting, and the screenshot budget;
> and Phase 8's check 54 reads `### The dashboard` at `v2.0.0-phase-8`.

**Branch:** `feature/phase09-step4-documentation`

**Deploys:** nothing beyond merge — the documents are live on GitHub at merge;
the README reaches TestPyPI's page with the release candidate (Step 5) and
PyPI's with 2.0.0 (Step 7).

Settings — ladder (`roadmodel ladder --category long-context --complexity
high`):

|               |          | Cost                | Balanced            | Quality             |
| ------------- | -------- | ------------------- | ------------------- | ------------------- |
| **Pick**      | Model    | **Sonnet 5.5**      | **Opus 5.5**        | **Opus 5.5**        |
|               | Platform | Claude Code         | Claude Code         | Claude Code         |
|               | Level    | XHigh               | High                | XHigh               |
|               | AA       | 51.9                | 53.6                | 56                  |
|               | Price    | $3.72/1M            | $6.76/1M            | $8.29/1M            |
| **Runner‑up** | Model    | **Gemini 4 Carbon** | **Gemini 4 Carbon** | **Gemini 4 Carbon** |
|               | Platform | Gemini (web / app)  | Gemini (web / app)  | Gemini (web / app)  |
|               | Level    | Low                 | Medium              | High                |
|               | AA       | ≈46.2               | ≈50.8               | ≈53.6               |
|               | Price    | ≈$3.00/1M           | ≈$3.50/1M           | ≈$4.00/1M           |
| **Backup**    | Model    | **GPT-6.2 Sol**     | **GPT-6.2 Sol**     | **GPT-6.2 Sol**     |
|               | Platform | Codex               | Codex               | Codex               |
|               | Level    | Medium              | High                | XHigh               |
|               | AA       | ≈49.8               | ≈52.2               | ≈53                 |
|               | Price    | ≈$3.50/1M           | ≈$4.00/1M           | ≈$5.50/1M           |

Ranked for long-context, high complexity. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level. ≈
estimated from the model's measured levels or its previous version's.

**Conversation:** New

> Settings updated 2026-11-19 (refresh): Cost Pick was GPT-6.1 Sol · Medium, Balanced Pick was
> GPT-6.1 Sol · High, Cost Runner-up was Sonnet 5.5 · High, Balanced Runner-up was Opus 5.5 · High,
> Quality Runner-up was GPT-6.1 Sol · XHigh, Cost Backup was Gemini 4 Carbon · Low, Balanced Backup
> was Gemini 4 Carbon · Medium, Quality Backup was Gemini 4 Carbon · High. Re-ranked against the
> current roadmodel catalog.

**Model rationale:** Step 4 is long-context with a knowledge secondary category
— documentation that must agree, sentence by sentence, with a codebase of eight
phases, its settings model, its commands, its four existing guides, and the
pages the screenshots show — at High complexity for its scope and the cost of a
wrong instruction to a stranger, not novel. On the step alone, the Quality Pick
fits best: Opus 5.5 on Claude Code at XHigh. It gives this classification
priority for capability and reasoning depth. The Cost Pick is Sonnet 5.5 on
Claude Code at XHigh, and the Balanced Pick is Opus 5.5 on Claude Code at High.

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
       feature/phase09-step4-documentation`
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
       Phase 9 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 9`
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

    THIS STEP publishes words and pictures to everyone who reads the
    repository or PyPI, so every example uses a public landmark from
    `scripts/public_landmarks.toml`, a documentation address (192.0.2.0/24,
    2001:db8::/32), or an obvious placeholder (`<your token>`), never a real
    token, topic, key, the operator's place, or the operator's LAN address.
    The screenshots come from the scenario servers in temporary data
    directories, never from the operator's service, and show only the two
    landmarks and Hurricane Demo; each is checked by eye and passes
    `check_personal_data.py` before it is committed. The guides tell readers
    how to keep secrets out of shell history and out of bug reports.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 9 (Release 2.0). Step 4:
    documentation.

    Current state (as of Phase 8, post-Phase-9 Step 3):

    - `README.md` (446 lines) is written for a checkout (`uv run weatherbot
      …`, `uv tool install --from .`), links its documents by relative paths,
      and keeps `## Status`, `## Commands` (with `### Running unattended` and
      `### The dashboard` inside it), `## Disclaimer`, `## Development
      quickstart`, `## Documents`, and `## License`. Live checks need the `##
      Commands` section to name `weatherbot status`, `weatherbot replay`,
      `weatherbot locations evacuation`, `weatherbot brief`, `weatherbot ask`,
      `weatherbot prune`, `weatherbot report`, and `--place`; the `### The
      dashboard` heading; "DISCLAIMER.md" and "v1.0.0"; and never "global
      coverage" (Decision 15). Phase 8's check 54 reads `### The dashboard`
      for `LocationSwitcher`, `MapPanels`, `replay workbench`, and `Settings
      tabs`, live; this step converts it.
    - `scripts/set_version.py` (Step 2) rewrites
      `https://github.com/nathanramoscfa/weatherbot/blob/<ref>/` and
      `/raw/<ref>/` links in the README to `main` for a development version
      and to `v<version>` otherwise.
    - The commands (from the Typer app): `fetch`, `storms`, `alerts`,
      `status`, `replay`, `doctor`, `check`, `serve`, `install-task`,
      `uninstall-task`, `brief`, `ask`, `prune`, `report`, `locations
      add|list|remove|evacuation`, `config show|path`, and `notify
      log|setup|test`.
    - Settings: `services/config.py`'s `Settings` (tables `[logging]`,
      `[http]`, `[engine]`, `[monitor]`, `[notifications]`, `[web]` with Step
      3's LAN keys, `[ai]`, `[retention]`), `ENVIRONMENT_OVERRIDES`, and
      `settings_file.EDITABLE` (12 keys and when each applies);
      environment-only variables: `ANTHROPIC_API_KEY` (or an `ant auth login`
      profile), `WEATHERBOT_NTFY_TOPIC`, `WEATHERBOT_NTFY_TOKEN`,
      `WEATHERBOT_WEB_TOKEN`, `WEATHERBOT_DATA_DIR`, and
      `WEATHERBOT_CONFIG_DIR`. `docs/schema/config.schema.json` is exported by
      `scripts/export_schemas.py --check`.
    - Guides that exist: `docs/AI.md` (its pinned headings and recorded
      figures stay; it still says "Phase 6 adds the products step by step"),
      `docs/ALERT-LADDER.md` (three blocks generated by
      `scripts/export_ladder.py --check` and a link to `../DISCLAIMER.md`),
      `docs/DATA_SOURCES.md` (the register; its header row, per-basin table,
      `## Not used`, and ISO dates stay), `docs/NOTIFICATIONS.md`,
      `docs/DESIGN.md`, and Step 3's `docs/LAN.md` (marked not yet supported).
      Version 1's deleted paths include `docs/configuration.md`,
      `docs/troubleshooting.md`, and `docs/user-guide.md`; Phase 1's check 10
      compares exact paths.
    - Screenshots: the scenario servers (`scripts/serve_demo.py --scenario
      quiet|outlook|cone|watch|landfall`, ports 8802 to 8806) serve the built
      interface; `frontend/playwright.config.ts` must keep `/@idle|@dogfood/`
      (Phase 8's check 46), and no image may be tracked under `frontend/`
      (check 49).
    - The replay corpus reaches users as
      `weatherbot-replay-corpus-<version>.zip` on the GitHub Release (Decision
      7).

    Files to read (every file before drafting):

    - docs/roadmap/phase09-roadmap.md (Decisions 2, 7, 9, 11, 12, and 15, and
      this step).
    - README.md, CONTRIBUTING.md, SECURITY.md, DISCLAIMER.md, and CHANGELOG.md
      (the top).
    - docs/AI.md, docs/ALERT-LADDER.md, docs/DATA_SOURCES.md,
      docs/NOTIFICATIONS.md, docs/LAN.md, and docs/DESIGN.md.
    - src/weatherbot/services/config.py,
      src/weatherbot/services/settings_file.py, src/weatherbot/cli/__init__.py
      and each command module's options, and src/weatherbot/services/tasks.py.
    - scripts/export_schemas.py (the pattern for a generator with `--check`),
      scripts/serve_demo.py, and frontend/playwright.config.ts.
    - scripts/verify_phase08.py (check 54) with
      tests/test_phase08_verification.py.
    - `git show v1.0.0:README.md` (version 1's commands and `.env` settings,
      for the migration note).
  </context>

  <goal>
    Write the README as the PyPI page, the user guide, the generated
    configuration reference, the always-on, troubleshooting, and migration
    guides, correct the existing guides against the installed product, capture
    and commit the screenshots, and hold all of it with tests.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `README.md`, in this order: the title and a two-sentence description;
      one screenshot (the landfall dashboard) with a caption saying Hurricane
      Demo is demonstration data; what Weatherbot does and what it never does
      (official products decide, Claude narrates, nothing personal leaves
      except what the guides name); `## Status`; `## Install` (`uv tool
      install weatherbot`, which fetches Python 3.13 or later when the machine
      has none; `pipx install weatherbot`; `pip install weatherbot` in a
      Python 3.13+ virtual environment; a note that on Python 3.11 or 3.12 pip
      finds only the retired 1.0.0); `## Quick start` (`weatherbot serve`,
      adding a place, `weatherbot doctor`); `## Commands` with every command
      and its needles, run as `weatherbot …`; `### Running unattended` (short,
      linking `docs/ALWAYS-ON.md`); `### The dashboard` in a reader's words
      (cards for each place, the map, replay, the tabs of Settings); `##
      Documentation` (each guide with one line); `## Disclaimer` (linking
      `DISCLAIMER.md`); `## Development` (linking `CONTRIBUTING.md`); `##
      License`. Keep "Version 1 is retired" with its `v1.0.0` link. Every link
      is absolute (`https://github.com/nathanramoscfa/weatherbot/blob/main/…`,
      images through `…/raw/main/docs/images/…`), so `set_version.py` can pin
      them.
    </requirement>

    <requirement>
      Convert Phase 8's check 54 in the same commit as the README: `dashboard
      = markdown_section(tagged("README.md", tag=PHASE_8_TAG), "### The
      dashboard")`, its docstring saying Phase 9 Step 4 rewrote the section
      for readers, and tests added to tests/test_phase08_verification.py (none
      pin check 54 today) so a rewritten live section passes and a tag without
      the section fails.
    </requirement>

    <requirement>
      `docs/GUIDE.md`: install (and the Python note), first run and the
      disclaimer, adding places (`locations add`, the dashboard's first-run
      card, outside NWS coverage), the dashboard, the map and its layers,
      replay (download the corpus archive from the release page, check its
      SHA-256, unzip, set `[web] corpus` or `serve --corpus`), Storms, Alerts,
      and Timeline, the AI briefing and Ask (the credential, the cost, the
      daily cap, turning it off; link `docs/AI.md`), notifications (link
      `docs/NOTIFICATIONS.md`), the report, Settings and history retention,
      running unattended (link `docs/ALWAYS-ON.md`), LAN mode (link
      `docs/LAN.md`, saying whether it is supported yet), every command (a
      table of command paths and one line each), where the data lives on
      Windows and Linux and the two directory overrides, upgrading (`uv tool
      upgrade weatherbot`, then restart the task) and uninstalling
      (`uninstall-task`, `uv tool uninstall weatherbot`, the data directory),
      and getting help (`docs/TROUBLESHOOTING.md`, `SECURITY.md`). Use the
      screenshots where a page is described.
    </requirement>

    <requirement>
      `scripts/export_config_reference.py` (`--check` writes nothing and exits
      non-zero when stale) writes `docs/CONFIGURATION.md`: one section per
      table, one row per key (name, type, default, allowed values or range,
      environment variable, whether Settings edits it and when it applies, and
      a one-line description), then the environment-only variables with what
      each is for and that it is never written to `weatherbot.toml`.
      Descriptions come from `Field(description=...)` on the settings models;
      add any that are missing and regenerate `docs/schema/config.schema.json`
      with `scripts/export_schemas.py`. Test:
      tests/scripts/test_export_config_reference.py (current, and stale after
      a change).
    </requirement>

    <requirement>
      `docs/ALWAYS-ON.md`: Windows (install with `uv tool install`,
      `weatherbot install-task`, what `\Weatherbot\serve` and
      `\Weatherbot\check` do, sleep, hibernation, and battery, checking with
      `doctor` and `status`, after an upgrade, `uninstall-task`); Linux (an
      example systemd user service for `weatherbot serve --no-open` and a
      timer for `weatherbot check --once --if-stale`, with `loginctl
      enable-linger`, marked as an example Weatherbot does not install or
      test). `docs/TROUBLESHOOTING.md`, by symptom, each starting from
      `weatherbot doctor`: the dashboard does not open (the port, the host, a
      firewall), the stale banner, no toast, no phone notification, AI paused
      or refused, a migration failed at start, `weatherbot` runs version 1
      (`doctor`'s path check), pip installed 1.0.0 (Python too old), the
      replay page asks for a corpus, LAN mode refuses or the phone cannot
      connect, and how to report a problem without a coordinate, token, or
      key. `docs/MIGRATING.md`: what changed from version 1 (its commands
      mapped to version 2's: `run` to `serve` and `check`, `ai-analysis` to
      `brief` and `ask`, `test-alert` to `notify test`, `check-coverage` to
      `locations add` and `doctor`, `show-map` to the map page, `state` to
      `status` and the timeline, `debug` to `doctor`), configuration (`.env`'s
      location and OpenAI key to `locations add`, `weatherbot.toml`, and an
      Anthropic credential), what is not carried over (state, reports, the
      cache), the features version 1 claimed that version 2 does not have and
      why, uninstalling version 1 and fixing a `PATH` that still finds it, and
      that 1.0.0 stays installable by an exact pin.
    </requirement>

    <requirement>
      Correct the existing guides for an installed reader, adding and
      correcting text but never removing a pinned heading or recorded figure
      (Decision 15): `docs/AI.md` (the Phase 6 wording, the installed
      commands), `docs/NOTIFICATIONS.md` (installed commands),
      `docs/ALERT-LADDER.md` (outside its generated blocks;
      `scripts/export_ladder.py --check` passes), `docs/DATA_SOURCES.md` (a
      short note for readers at the top; the dates are refreshed at Step 7),
      `docs/LAN.md` (cross-links only; it stays "not yet supported"),
      `SECURITY.md` (supported versions: 2.0.x yes; pre-releases and 1.0.0 no;
      the private reporting section unchanged), and `CONTRIBUTING.md` (the
      development quickstart no longer quotes a version).
    </requirement>

    <requirement>
      Screenshots: `frontend/playwright.docs.config.ts` (its own `testDir`,
      `frontend/docs-capture/`, starting the `landfall` server on 8806 and any
      other scenario server it needs, the same way `playwright.config.ts`
      does) and `frontend/docs-capture/capture.spec.ts`, run by a new npm
      script `docs:screenshots` (`playwright test --config
      playwright.docs.config.ts`), capture at 1280×800, with animations
      disabled and the clock frozen where the page shows a countdown: the
      landfall dashboard in light and in dark, the landfall map, `/replay`
      with a corpus storm loaded, `/storms`, and `/settings#about`, into
      `docs/images/` as `dashboard.png`, `dashboard-dark.png`, `map.png`,
      `replay.png`, `storms.png`, and `settings.png`. Keep each under 300 KB
      (crop to the viewport; reduce colours if needed, without new
      dependencies) and the six under 2 MB. The default `npm run e2e` never
      runs them.
    </requirement>

    <requirement>
      tests/test_docs.py:
      - test_readme_has_no_relative_links_and_pins_repository_links (to `main`
        for a development version, to `v<version>` otherwise; the
        `tree/v1.0.0` link to version 1 is exempt).
      - test_readme_keeps_its_pinned_needles (every Decision 15 needle, and no
        "global coverage").
      - test_every_relative_markdown_link_resolves (every tracked `.md`
        outside `planning/`; fix every broken link it finds in older
        documents).
      - test_guide_names_every_command (from the Typer app's registered
        command paths).
      - test_configuration_reference_names_every_setting_and_variable.
      - test_screenshots_are_tracked_pngs_within_budget.
    </requirement>

    <requirement>
      Add `### Phase 9 — Release 2.0` entries to `CHANGELOG.md` for this step,
      and update `docs/release-readiness-2.0.0.md`'s "documentation complete"
      row with the evidence (the test names and the list of guides).
    </requirement>

    <requirement>
      Before every commit, run all eight verifiers' `--fast`; each must exit
      0. Stop every server you start.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative path as the
      first line where the file type accepts comments (Markdown files carry
      the `<!-- path -->` comment the existing guides use).
    </requirement>
  </requirements>
</task>
```

### Step 4 acceptance criteria

- `README.md` holds no relative link; every repository link reads
  `https://github.com/nathanramoscfa/weatherbot/blob/main/…` or `…/raw/main/…`
  (the `tree/v1.0.0` link to version 1 aside) while the version is a development
  version (`scripts/set_version.py` pins them to the tag at Steps 5 to 7); it
  keeps every needle of Decision 15 and never says "global coverage"; and
  `tests/test_docs.py` checks all of it.
- `docs/GUIDE.md` names every Typer command path and links
  `docs/CONFIGURATION.md`, which documents every `Settings` key with its
  default, its environment variable, and whether Settings can edit it, plus
  every environment-only variable; `scripts/export_config_reference.py --check`
  passes and fails on a stale file (tests).
- `docs/ALWAYS-ON.md`, `docs/TROUBLESHOOTING.md`, and `docs/MIGRATING.md` exist
  with the content this step names; every relative link in every tracked
  Markdown file outside `planning/` resolves to a tracked file (test).
- Six screenshots are tracked under `docs/images/`, each a PNG of at most 300 KB
  and all at most 2 MB, captured by `npm --prefix frontend run docs:screenshots`
  from the scenario servers, showing only the public landmarks and Hurricane
  Demo, each captioned as demonstration data; no image is tracked under
  `frontend/` (Phase 8's check 49) and `playwright.config.ts` is unchanged.
- Phase 8's check 54 reads `### The dashboard` at `v2.0.0-phase-8`, with tests
  added; `verify_phase01.py` to `verify_phase08.py` `--fast` all exit 0;
  `scripts/export_ladder.py --check` passes.
- `SECURITY.md`'s supported versions name 2.0.x, and its private reporting
  section is unchanged; `docs/AI.md` no longer says "Phase 6 adds the products
  step by step".
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff; every example in the documents uses a public
  landmark, a documentation address (192.0.2.0/24), or a placeholder, never a
  real token, topic, key, or the operator's place; the screenshots were checked
  by eye and by `check_personal_data.py` before commit.

---

## Step 5 — The release candidate

**Status:** Not started

> **Goal:** Run the whole release path once where a mistake costs nothing
> (Decision 6). `scripts/set_version.py 2.0.0rc1` sets the version, the README's
> pinned links, and `Development Status :: 4 - Beta`; `CHANGELOG.md` gains `##
> [2.0.0rc1] - <date>`, whose summary opens the version 2 entries now under it;
> the README's `## Status` says 2.0.0 is in release-candidate testing;
> `docs/release-readiness-2.0.0.md` takes Step 2's dry-run evidence. After the
> merge and the operator's yes, `v2.0.0rc1` is tagged on the merge commit;
> `release.yml` builds and smokes it; the agent downloads the built files and
> scans them with the operator's local denylist before the operator approves the
> `testpypi` deployment; TestPyPI receives rc1 with its attestations; both
> runners install it from the index; the pre-release appears on GitHub with the
> corpus archive; TestPyPI's page is read back; and the operator's service runs
> rc1 from the hash-checked wheel, starting the soak that Step 7's record
> requires.

**Branch:** `feature/phase09-step5-release-candidate`

**Deploys:** TestPyPI (`weatherbot` `2.0.0rc1`, created by the pending publisher
at the first upload) and the GitHub Release `v2.0.0rc1` (pre-release) → through
`release.yml`, after the merge, the operator's yes to the tag, and the
operator's approval of the `testpypi` deployment; then the operator's local
service → rc1 installed from the hash-checked wheel, after the operator's yes
(Decision 16).

Settings — ladder (`roadmodel ladder --category agentic --complexity medium`):

|               |          | Cost                  | Balanced              | Quality             |
| ------------- | -------- | --------------------- | --------------------- | ------------------- |
| **Pick**      | Model    | **Haiku 5.5**         | **Gemini 4 Hydrogen** | **Opus 5.5**        |
|               | Platform | Claude Code           | Gemini (web / app)    | Claude Code         |
|               | Level    | High                  | Low                   | High                |
|               | AA       | 37.8                  | ≈43.1                 | 53.6                |
|               | Price    | $0.26/1M              | ≈$2.25/1M             | $6.76/1M            |
| **Runner‑up** | Model    | **Gemini 4 Hydrogen** | **Opus 5.5**          | **Gemini 4 Carbon** |
|               | Platform | Gemini (web / app)    | Claude Code           | Gemini (web / app)  |
|               | Level    | Low                   | Medium                | High                |
|               | AA       | ≈43.1                 | 51.2                  | ≈53.6               |
|               | Price    | ≈$2.25/1M             | $6.39/1M              | ≈$4.00/1M           |
| **Backup**    | Model    | **GPT-6.2 Sol**       | **GPT-6.2 Sol**       | **GPT-6.2 Astra**   |
|               | Platform | Codex                 | Codex                 | Codex               |
|               | Level    | Low                   | Medium                | High                |
|               | AA       | ≈44.1                 | ≈49.8                 | ≈53.2               |
|               | Price    | ≈$3.00/1M             | ≈$3.50/1M             | ≈$16.00/1M          |

Ranked for agentic, medium complexity. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level. ≈
estimated from the model's measured levels or its previous version's.

**Conversation:** New

> Settings updated 2026-11-19 (refresh): Cost Pick was GPT-6.1 Sol · Low, Balanced Pick was Gemini 4
> Argon · High, Cost Runner-up was Sonnet 5.5 · High, Quality Runner-up was Gemini 4 Argon · High,
> Cost Backup was Gemini 4 Argon · Low, Balanced Backup was GPT-6.1 Sol · Medium, Quality Backup was
> GPT-6 Astra · High. Re-ranked against the current roadmodel catalog.

**Model rationale:** Step 5 is agentic with a coding secondary category — a
version bump, a changelog section, a tag, a watched workflow with a human
approval in the middle, a scan, an index read back, and a deploy on the
operator's machine — at Medium complexity, not novel: Step 2's runbook fixes
every action, and TestPyPI forgives what PyPI would not. On the step alone, the
Balanced Pick fits best: Gemini 4 Hydrogen on Gemini (web / app) at Low. It
balances the reasoning demands of this classification with estimated token cost.
The Cost Pick is Haiku 5.5 on Claude Code at High, and the Quality Pick is Opus
5.5 on Claude Code at High.

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
       feature/phase09-step5-release-candidate`
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
       Phase 9 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 9`
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

    THIS STEP makes the project's first upload and touches the operator's
    machine. The tag is pushed only after the operator's yes; the `testpypi`
    deployment is approved by the operator in GitHub's interface, never by an
    agent through the API; and before that approval the agent downloads the
    run's `dist` artifact (`gh run download <run> -n dist`) into a temporary
    directory and runs `scripts/check_personal_data.py` on both files with the
    operator's local denylist, which prints only rule ids and paths, never a
    value. The operator's service is reinstalled only from a wheel whose
    SHA-256 equals the run's build. No smoke resolves a dependency through
    TestPyPI.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 9 (Release 2.0). Step 5: the release
    candidate.

    Current state (as of Phase 8, post-Phase-9 Step 4):

    - Step 2's PR shipped `scripts/set_version.py`, `scripts/check_dist.py`,
      `scripts/release_smoke.py`, `.github/workflows/release.yml`
      (tag-triggered; `build`, `smoke-built`, `publish-testpypi` in the
      `testpypi` environment, `smoke-published`, `github-release`),
      `install-canary.yml`, the environments, the tag ruleset, the trusted
      publishers, `docs/RELEASING.md`, and `docs/release-readiness-2.0.0.md`.
      Its post-merge dry run and canary dispatch results are recorded here by
      Step 2's Stage 6.
    - Step 3 shipped LAN mode, off by default; Step 4 wrote the README for
      PyPI (links on `main`, pinned by `set_version.py`) and the guides.
    - `CHANGELOG.md`: one `## [Unreleased]` holding `### Phase 9 — Release
      2.0` back to `### Phase 3 — Threat engine`, the Phase 1 and 2
      verification notes, and `### Added`, `### Changed`, `### Removed`, above
      `## [1.0.0] - 2025-09-29`. Phase 1's checks need exactly one `##
      [Unreleased]` and the 1.0.0 lines; Phases 7 and 8 need their `### Phase`
      headings anywhere.
    - The operator's service runs `2.0.0.dev0` (Phase 8's build) under
      `\Weatherbot\serve` from `C:\Users\Admin\.local\bin\weatherbot.exe`;
      `\Weatherbot\check` runs at HH:25. The operator often reaches this
      machine from another computer.

    Files to read (every file before drafting):

    - docs/roadmap/phase09-roadmap.md (Decisions 4 to 6, 13, and 16, and this
      step), docs/RELEASING.md, and docs/release-readiness-2.0.0.md.
    - scripts/set_version.py, scripts/release_smoke.py, and
      .github/workflows/release.yml.
    - README.md (`## Status`) and CHANGELOG.md.
  </context>

  <goal>
    Publish `2.0.0rc1` to TestPyPI through the real pipeline, prove it
    installs on both runners and reads well on TestPyPI's page, and start its
    soak on the operator's service.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      On the branch: run `uv run python scripts/set_version.py 2.0.0rc1`; move
      the version 2 entries of `## [Unreleased]` under a new `## [2.0.0rc1] -
      <today>` heading, opened by a summary of at most forty lines (what
      version 2 is, what changed from 1.0.0 that breaks — Python 3.13 or
      later, the new commands and configuration, Anthropic instead of OpenAI —
      a pointer to `docs/MIGRATING.md`, and that this is a release candidate
      on TestPyPI), keeping one empty `## [Unreleased]` above it; set the
      README's `## Status` to say 2.0.0 is in release-candidate testing on
      TestPyPI and that PyPI's current release is the retired 1.0.0; copy Step
      2's dry-run and canary evidence into the record. Open the PR; merge when
      green.
    </requirement>

    <requirement>
      After the merge: in the chat, state the tag, the commit, what the
      workflow will do, and that the operator will be asked to approve the
      `testpypi` deployment; then ask with AskUserQuestion. On a yes: `git tag
      -a v2.0.0rc1 -m "Weatherbot 2.0.0rc1" <merge commit>` and `git push
      origin v2.0.0rc1`. Watch the run (`gh run watch`).
    </requirement>

    <requirement>
      When `publish-testpypi` waits for approval: download `dist`, extract
      both files into a temporary directory (the checker refuses an archive of
      more than 64 members, and the wheel holds 186) and run `uv run python
      scripts/check_personal_data.py` over the extracted files with the
      operator's denylist, and compare both files' SHA-256 with the `build`
      job's output. Only if both are clean, ask the operator to approve the
      deployment in GitHub's interface (give the run URL), and wait. If a
      publish job is refused by TestPyPI (the pending publisher), follow
      `docs/RELEASING.md`: fix the publisher and re-run the job on the same
      tag; never re-tag.
    </requirement>

    <requirement>
      Read back: `https://test.pypi.org/pypi/weatherbot/2.0.0rc1/json` (files,
      digests, `requires_python`, the description's content type), TestPyPI's
      integrity endpoint for each file, the GitHub pre-release's assets, and
      the project page's rendered description (links and images resolve). Fix
      any README defect in Step 6's PR, and record it.
    </requirement>

    <requirement>
      Deploy to the operator's service (Decision 16): state the recipe in the
      chat and ask with AskUserQuestion; on a yes, away from HH:25, `schtasks
      /End /TN \Weatherbot\serve`, download the rc1 wheel from the GitHub
      pre-release into a temporary directory, check its SHA-256 against the
      run's build, `uv tool install --reinstall <wheel>` (the tool's Python
      3.13 or later), `schtasks /Run /TN \Weatherbot\serve`, then read `GET
      http://127.0.0.1:8765/api/health` and `weatherbot doctor --offline
      --json`. Record the time the soak starts.
    </requirement>

    <requirement>
      The tag follows the merge, so rc1's evidence (run URL, smokes, the
      scan's result as counts, digests, the soak's start) cannot be in this
      step's PR: at Stage 6, write it into Step 6's `<context>` in this
      roadmap (a `docs:` PR of its own if this step's PR has merged, as the
      lifecycle allows for spec edits), and Step 6's PR copies it into
      `docs/release-readiness-2.0.0.md`.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative path as the
      first line where the file type accepts comments.
    </requirement>
  </requirements>
</task>
```

### Step 5 acceptance criteria

- `main` reads `2.0.0rc1` everywhere `tests/test_release_metadata.py` looks; the
  README's links point at `v2.0.0rc1`; `CHANGELOG.md` keeps one `##
  [Unreleased]` and adds `## [2.0.0rc1] - <date>` above the version 2 entries;
  every gate and all eight verifiers' `--fast` pass.
- `v2.0.0rc1` is an annotated tag on the merge commit, made after the operator's
  yes; `release.yml`'s run for it passed `build`, all four `smoke-built`
  entries, `publish-testpypi` (approved by the operator in GitHub's interface
  after the denylist scan of the built files came back clean), all four
  `smoke-published` entries, and `github-release`.
- **Deployed & verified:** `https://test.pypi.org/pypi/weatherbot/2.0.0rc1/json`
  lists one wheel and one sdist whose SHA-256 equal the run's build and the
  GitHub pre-release's assets; TestPyPI's integrity endpoint answers a
  provenance for each file; the pre-release holds the two files, the corpus
  archive, and its `.sha256`; the TestPyPI project page's description renders
  the README with working links and images; and `GET
  http://127.0.0.1:8765/api/health` on the operator's machine answers
  `"version": "2.0.0rc1"`, `ui.present` true, and the database at `0010`, with
  `weatherbot doctor --offline --json` passing `web` and `migrations`.
- `docs/release-readiness-2.0.0.md` holds Step 2's dry-run and canary runs;
  rc1's run, smokes, denylist scan result (counts only), and soak start are
  written into Step 6's `<context>` for Step 6's PR to record, because the tag
  follows this step's merge.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff; the built files passed
  `check_personal_data.py` with the operator's denylist before the upload was
  approved (the checker printed no match); no credential, token, or the
  operator's place appeared in the chat, the PR, or a log; and the operator's
  service was touched only after the operator's yes.

---

## Step 6 — The readiness rehearsals

**Status:** Not started

> **Goal:** Pass the two readiness gates that only real use can pass (Decisions
> 6 and 10). First the LAN gate, on rc1 as the operator's service runs it: the
> operator generates and sets `WEATHERBOT_WEB_TOKEN` without it crossing the
> chat, sets `[web] lan` and `lan_address`, adds a Windows Defender Firewall
> rule for the Private profile and the port, and opens the dashboard on their
> phone through the token prompt, while the agent proves the refusals against
> the LAN address and reads the warning and `doctor`; then `docs/LAN.md` is
> marked supported, with the date. Then yank and patch: this step's pull request
> sets `2.0.0rc2` (with every blocking fix from rc1's soak and the LAN gate) and
> its changelog section; after the merge the operator yanks rc1 on TestPyPI, rc2
> is tagged and published through the same gates, both runners install it,
> yanked rc1 still installs by an exact pin while an unpinned pre-release
> install takes rc2, and the operator's service moves to rc2, back to rc1, and
> forward to rc2 — each stage timed, for Step 7's record and the project
> roadmap's Rollback table.

**Branch:** `feature/phase09-step6-readiness-rehearsals`

**Deploys:** the operator's local service → LAN mode on the operator's network
(with a yes at each action), then rc2, rc1, and rc2 again; TestPyPI → rc1 yanked
by the operator, `2.0.0rc2` published through `release.yml` with the operator's
yes to the tag and approval of the deployment; the GitHub Release `v2.0.0rc2`
(pre-release).

Settings — ladder (`roadmodel ladder --category agentic --complexity high`):

|               |          | Cost                  | Balanced              | Quality            |
| ------------- | -------- | --------------------- | --------------------- | ------------------ |
| **Pick**      | Model    | **Gemini 4 Hydrogen** | **Sonnet 5.5**        | **Opus 5.5**       |
|               | Platform | Gemini (web / app)    | Claude Code           | Claude Code        |
|               | Level    | Medium                | XHigh                 | XHigh              |
|               | AA       | ≈48.8                 | 51.9                  | 56                 |
|               | Price    | ≈$2.62/1M             | $3.72/1M              | $8.29/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**        | **Gemini 4 Hydrogen** | **Gemini 4 Neon**  |
|               | Platform | Claude Code           | Gemini (web / app)    | Gemini (web / app) |
|               | Level    | High                  | High                  | XHigh              |
|               | AA       | 46.8                  | ≈51.6                 | ≈56.9              |
|               | Price    | $3.40/1M              | ≈$3.00/1M             | ≈$8.25/1M          |
| **Backup**    | Model    | **GPT-6.2 Sol**       | **GPT-6.2 Sol**       | **GPT-6.2 Astra**  |
|               | Platform | Codex                 | Codex                 | Codex              |
|               | Level    | Medium                | XHigh                 | XHigh              |
|               | AA       | ≈49.8                 | ≈53                   | ≈54.7              |
|               | Price    | ≈$3.50/1M             | ≈$5.50/1M             | ≈$22.00/1M         |

Ranked for agentic, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels or its previous version's.

**Conversation:** New

> Settings updated 2026-11-19 (refresh): Cost Pick was GPT-6.1 Sol · Medium, Balanced Runner-up was
> GPT-6.1 Sol · High, Quality Runner-up was Gemini 4 Argon · High, Cost Backup was Gemini 4 Argon ·
> Low, Balanced Backup was Gemini 4 Argon · Medium, Quality Backup was GPT-6 Astra · XHigh. Re-
> ranked against the current roadmodel catalog.

**Model rationale:** Step 6 is agentic with a planning secondary category — the
first exposure of the operator's machine to their network, a credential that
must never cross the chat, a firewall rule, a phone in the operator's hand,
refusals to prove from the outside, a yank no one can take back cleanly, a
second candidate through the full pipeline, and three timed deploys — at High
complexity for the number of interacting actions and the cost of a wrong one,
not novel: Decisions 6, 9, 10, and 16 fix the protocol. On the step alone, the
Quality Pick fits best: Opus 5.5 on Claude Code at XHigh. It gives this
classification priority for capability and reasoning depth. The Cost Pick is
Gemini 4 Hydrogen on Gemini (web / app) at Medium, and the Balanced Pick is
Sonnet 5.5 on Claude Code at XHigh.

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
       feature/phase09-step6-readiness-rehearsals`
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
       Phase 9 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 9`
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

    THIS STEP opens the operator's machine to their network for the first
    time. The token is generated and set by the operator in their own terminal
    and the Windows User environment variables dialog (`docs/LAN.md`), never
    typed into the chat, a command line an agent runs, a file, or a log; the
    one bearer request this step makes reads the token from the User
    environment inside the command
    (`[Environment]::GetEnvironmentVariable('WEATHERBOT_WEB_TOKEN','User')`
    into a variable) and never prints it. The LAN address, the phone, and the
    network's name are the operator's private details: they appear in no
    commit, record, PR, or chat summary (write "the LAN address"). The
    firewall rule admits the Private profile and the port only, and is created
    by the operator from an elevated PowerShell with the command the agent
    hands over. Every action on the operator's machine, TestPyPI, or the tag
    waits for a yes; both uploads wait for the operator's approval after a
    clean denylist scan.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 9 (Release 2.0). Step 6: the
    readiness rehearsals.

    Current state (as of Phase 8, post-Phase-9 Step 5):

    - `2.0.0rc1` is on TestPyPI and the GitHub pre-release `v2.0.0rc1`,
      published through `release.yml` (Step 5); the operator's service runs it
      from the hash-checked wheel (soak start recorded by Step 5's Stage 6
      below this line, with rc1's run URL, smokes, scan counts, and digests,
      for this step's PR to copy into the record).
    - LAN mode (Step 3): `[web] lan`, `lan_address`, `lan_hosts`;
      `WEATHERBOT_WEB_TOKEN` (at least 32 characters); the second listener;
      `POST /api/session` and its cookie; the limits (the sixth failure in
      five minutes answers 429); the startup warning; `/api/health`'s `lan`;
      `doctor`'s `web` check; `docs/LAN.md`, marked "not yet supported". A
      scheduled task inherits the User environment only when it starts, so
      `\Weatherbot\serve` must be restarted after the token is set.
    - `docs/RELEASING.md` holds the yank-and-patch runbook and the operator's
      upgrade and rollback recipes; PEP 592: a yanked file is ignored by an
      unpinned install and still served for an exact pin.
    - The operator often reaches this machine from another computer, where a
      dialog on the Windows desktop may never be seen: state the steps in the
      chat before every question.

    Files to read (every file before drafting):

    - docs/roadmap/phase09-roadmap.md (Decisions 6, 9, 10, and 16, and this
      step), docs/LAN.md, docs/RELEASING.md, and
      docs/release-readiness-2.0.0.md.
    - src/weatherbot/services/lan.py, src/weatherbot/web/guards.py
      (`LanAuthGuard`), and src/weatherbot/cli/serve.py (the warning).
    - scripts/set_version.py and CHANGELOG.md.
  </context>

  <goal>
    Pass the LAN gate on the operator's network and mark LAN mode supported;
    then rehearse yank and patch on TestPyPI and the operator's rollback,
    timing every stage.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      The LAN gate (before the PR), one action at a time, each after the
      operator's yes: (1) the operator generates the token and sets
      `WEATHERBOT_WEB_TOKEN` in the User environment variables, following
      `docs/LAN.md`; (2) the operator reads their LAN address from `ipconfig`,
      and, with a yes, the agent sets `[web] lan = true` and `lan_address` in
      the operator's `weatherbot.toml` (never committed); (3) warn the
      operator that Windows may raise a firewall dialog on the desktop at the
      first LAN start and that Cancel creates block rules overriding the port
      rule; the operator creates the firewall rule from an elevated PowerShell
      with the command the agent hands over (`New-NetFirewallRule -DisplayName
      "Weatherbot LAN" -Direction Inbound -Action Allow -Protocol TCP
      -LocalPort 8765 -LocalAddress <the LAN address> -Profile Private`); (4)
      restart `\Weatherbot\serve` away from HH:25; (5) the agent reads the
      log's warning, `/api/health`'s `lan`, and `doctor --offline --json`; (6)
      from this machine against the LAN address, in this order, because a
      wrong token locks this peer out for five minutes: the shell 200, one
      bearer request 200 with the token read inside the command, no
      credentials 401, a foreign `Host` 400, loopback 200 without a token, and
      last, the sixth wrong token 429 with `Retry-After`; (7) the operator
      opens `http://<the LAN address>:8765/` on their phone on the same Wi-Fi,
      enters the token in the prompt, sees the dashboard and the LAN chip, and
      sees a live update (a `Check now` from the phone, or the next event);
      (8) the operator chooses to keep LAN mode on or turn it off (`[web] lan
      = false` and a restart, removing the rule if they wish). Record each
      result and the choice, dated, without the address, the token, the phone,
      or the network's name.
    </requirement>

    <requirement>
      Fix every blocking defect the soak or the gate found on this branch,
      with tests (Triage rule); a defect that does not block the release
      becomes an issue named in the record.
    </requirement>

    <requirement>
      The PR: `uv run python scripts/set_version.py 2.0.0rc2`; `## [2.0.0rc2]
      - <today>` in `CHANGELOG.md` with the changes since rc1 (LAN mode
      supported; each fix) under the one `## [Unreleased]`; `docs/LAN.md`'s
      status line "Supported — rehearsed on <date>" and its sections checked
      against what the gate showed; the record's LAN-gate rows and Step 5's
      rc1 evidence. Merge when green.
    </requirement>

    <requirement>
      Yank and patch (after the merge), timing each stage from one clock: (t0)
      the operator, told the rehearsal's premise ("rc1 regressed"), yanks rc1
      on test.pypi.org (Manage → Releases → 2.0.0rc1 → Options → Yank, with
      the reason "Rehearsal of the yank-and-patch runbook"); (t1) with a yes,
      tag `v2.0.0rc2` on the merge commit and push; the run builds and smokes;
      the agent scans the built files with the operator's denylist and checks
      their digests; the operator approves `testpypi`; (t2) `smoke-published`
      passes on all four entries, which is the patch being installable; then
      read back rc1's yank and rc2's files, and in temporary virtual
      environments prove `pip install --no-deps --index-url
      https://test.pypi.org/simple/ weatherbot==2.0.0rc1` installs the yanked
      file while `pip install --no-deps --pre --index-url
      https://test.pypi.org/simple/ "weatherbot<2.0.0rc2"` finds no version,
      because a yank hides a file from every range that is not an exact pin.
    </requirement>

    <requirement>
      The operator's rollback, each after a yes, away from HH:25 (Decision
      16): reinstall rc2 from its hash-checked wheel (time it), roll back to
      rc1's wheel (time it; this is the "pin the previous version" rollback),
      and forward to rc2 again; after each, read `/api/health`'s version and
      `doctor --offline --json`. No revision separates them, so no migration
      runs. If rc2 changed LAN code and LAN mode is on, repeat proof (6) of
      the gate on rc2 and record it.
    </requirement>

    <requirement>
      At Stage 6, write the durations (t0 to t2 and each reinstall) and the
      run URLs into Step 7's `<context>` in this roadmap (a `docs:` PR of its
      own if this step's PR has merged), so Step 7's PR records them in
      `docs/release-readiness-2.0.0.md` and replaces "Under an hour (TBD once
      rehearsed)" in the project roadmap's Rollback table.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative path as the
      first line where the file type accepts comments.
    </requirement>
  </requirements>
</task>
```

### Step 6 acceptance criteria

- The LAN gate passed on the operator's network with rc1: the phone loaded the
  dashboard through the token prompt and showed a live update; from the LAN
  address, a request without credentials answered 401, the sixth wrong token 429
  with `Retry-After`, a foreign `Host` 400, and the shell 200; loopback still
  answered without a token; the warning was in the log; `doctor`'s `web` check
  passed naming LAN mode; the firewall rule admits the Private profile and the
  port only. The results, dated, are in `docs/release-readiness-2.0.0.md` (no
  address, token, or device name), with the operator's choice to keep LAN mode
  on or turn it off.
- `docs/LAN.md` reads "Supported — rehearsed on <date>"; `main` reads `2.0.0rc2`
  everywhere; `CHANGELOG.md` adds `## [2.0.0rc2] - <date>` (changes since rc1)
  under the one `## [Unreleased]`; every gate and all eight verifiers' `--fast`
  pass.
- **Deployed & verified:** rc1 shows as yanked, with a reason, in
  `https://test.pypi.org/pypi/weatherbot/2.0.0rc1/json`; `release.yml`'s run for
  `v2.0.0rc2` passed every job, the deployment approved by the operator after a
  clean denylist scan; `https://test.pypi.org/pypi/weatherbot/2.0.0rc2/json`
  lists files whose SHA-256 equal the run's build and the pre-release's assets;
  `pip install --no-deps --index-url https://test.pypi.org/simple/
  weatherbot==2.0.0rc1` installs the yanked file while `--pre
  "weatherbot<2.0.0rc2"` finds no version, each in a temporary virtual
  environment; and the operator's `/api/health` answered `2.0.0rc2`, then
  `2.0.0rc1`, then `2.0.0rc2`, with `doctor --offline --json` passing after
  each.
- The durations — from the decision to yank to rc2 installable from the index,
  and each reinstall of the operator's service — are written into Step 7's
  `<context>` for Step 7's PR to record in the readiness record and in the
  project roadmap's Rollback table.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff; the token, the LAN address, the phone, and
  the network's name never appeared in the chat, the PR, a log line, or the
  record; every action on the operator's machine, the firewall, and TestPyPI
  followed the operator's yes; and both uploads were approved by the operator
  after clean scans.

---

## Step 7 — 2.0.0

**Status:** Not started

> **Goal:** Release Weatherbot 2.0.0 as a decision, not a side effect (Decisions
> 5, 8, 13, 16, and 17). The readiness record is completed — the scans, the
> audits, the disclaimer surfaces, the documentation, the live re-verification
> of every source, the absence of demonstration data from the files, the
> candidates' smokes and soak, the LAN gate, the rehearsal's durations, and a
> disposition for every open issue and pull request — and the operator signs it.
> This step's pull request sets `2.0.0` (`Development Status :: 5 -
> Production/Stable`, the README's links on `v2.0.0`), adds `## [2.0.0] -
> <date>` with the release summary, sets the README's `## Status` to the
> release, records the rehearsal in the project roadmap's Rollback table, and
> links the signed record. After the merge and the operator's yes, `v2.0.0` is
> tagged; the built files are scanned with the denylist before the operator
> approves the `pypi` deployment; PyPI receives 2.0.0 with its attestations;
> both runners install it with `uv tool install` and `pip`; the GitHub Release
> carries the notes, the files, and the corpus archive; the operator's service
> is upgraded from PyPI and reports 2.0.0; the install canary is proved to run
> and to alarm; and, with the operator's yes, 1.0.0 is yanked.

**Branch:** `feature/phase09-step7-release`

**Deploys:** PyPI (`weatherbot` `2.0.0`) and the GitHub Release `v2.0.0` →
through `release.yml`, after the merge, the operator's yes to the tag, and the
operator's approval of the `pypi` deployment; the operator's local service →
`weatherbot==2.0.0` from PyPI, after a yes; the install canary's schedule (live
since Step 2) → its first install of 2.0.0 and its alarm, proved by dispatch;
PyPI's 1.0.0 → yanked by the operator, only with their yes.

Settings — ladder (`roadmodel ladder --category agentic --complexity high`):

|               |          | Cost                  | Balanced              | Quality            |
| ------------- | -------- | --------------------- | --------------------- | ------------------ |
| **Pick**      | Model    | **Gemini 4 Hydrogen** | **Sonnet 5.5**        | **Opus 5.5**       |
|               | Platform | Gemini (web / app)    | Claude Code           | Claude Code        |
|               | Level    | Medium                | XHigh                 | XHigh              |
|               | AA       | ≈48.8                 | 51.9                  | 56                 |
|               | Price    | ≈$2.62/1M             | $3.72/1M              | $8.29/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**        | **Gemini 4 Hydrogen** | **Gemini 4 Neon**  |
|               | Platform | Claude Code           | Gemini (web / app)    | Gemini (web / app) |
|               | Level    | High                  | High                  | XHigh              |
|               | AA       | 46.8                  | ≈51.6                 | ≈56.9              |
|               | Price    | $3.40/1M              | ≈$3.00/1M             | ≈$8.25/1M          |
| **Backup**    | Model    | **GPT-6.2 Sol**       | **GPT-6.2 Sol**       | **GPT-6.2 Astra**  |
|               | Platform | Codex                 | Codex                 | Codex              |
|               | Level    | Medium                | XHigh                 | XHigh              |
|               | AA       | ≈49.8                 | ≈53                   | ≈54.7              |
|               | Price    | ≈$3.50/1M             | ≈$5.50/1M             | ≈$22.00/1M         |

Ranked for agentic, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels or its previous version's.

**Conversation:** New

> Settings updated 2026-11-19 (refresh): Cost Pick was GPT-6.1 Sol · Medium, Balanced Runner-up was
> GPT-6.1 Sol · High, Quality Runner-up was Gemini 4 Argon · High, Cost Backup was Gemini 4 Argon ·
> Low, Balanced Backup was Gemini 4 Argon · Medium, Quality Backup was GPT-6 Astra · XHigh. Re-
> ranked against the current roadmodel catalog.

**Model rationale:** Step 7 is agentic with a knowledge secondary category — a
record of a dozen kinds of evidence to complete and check, a version and a
changelog to set, a tag, a publish behind a scan and an approval, two kinds of
fresh install, an upgrade on the operator's machine, an alarm to prove, and a
yank to recommend — at High complexity because every action is public and
permanent, not novel: Steps 2, 5, and 6 rehearsed each of them. On the step
alone, the Quality Pick fits best: Opus 5.5 on Claude Code at XHigh. It gives
this classification priority for capability and reasoning depth. The Cost Pick
is Gemini 4 Hydrogen on Gemini (web / app) at Medium, and the Balanced Pick is
Sonnet 5.5 on Claude Code at XHigh.

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
       feature/phase09-step7-release`
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
       Phase 9 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 9`
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
       complete. You can now move
       on to Step 8." That
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
       one before Step 8.
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

    THIS STEP is the irreversible one. The record is signed by the operator
    before the tag; the tag is pushed only after the operator's yes; the
    `pypi` deployment is approved by the operator in GitHub's interface after
    the agent has downloaded the run's `dist`, scanned both files' extracted
    contents with the operator's local denylist, and matched their SHA-256 to
    the build, never by an agent through the API; the operator's service is
    upgraded only from PyPI's `weatherbot==2.0.0` after a yes; and 1.0.0 is
    yanked only by the operator, only with their yes. The record and the PR
    carry evidence (run URLs, digests, counts, dates), never an address, a
    token, the operator's place, or a scan's matched text.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 9 (Release 2.0). Step 7: 2.0.0.

    Current state (as of Phase 8, post-Phase-9 Step 6):

    - `2.0.0rc2` is on TestPyPI (rc1 yanked) and the GitHub pre-release
      `v2.0.0rc2`; the operator's service runs rc2; LAN mode is supported and
      is on or off as the operator chose (Step 6). Step 6's Stage 6 writes the
      rehearsal's durations and run URLs below this line.
    - `docs/release-readiness-2.0.0.md` holds the rows Steps 1 to 6 filled;
      the rows left are this step's: the denylist scans, gitleaks over the
      full history, the audits and licences, the disclaimer surfaces, the live
      re-verification, the demonstration data's absence, the soak's end, the
      dispositions, and the sign-off.
    - `live-smoke.yml` runs the live tests (`pytest -m live`) against NHC,
      NWS, and Nominatim with the public landmarks; `docs/DATA_SOURCES.md`'s
      register rows carry a `Verified` ISO date each.
    - The disclaimer is shown by the CLI's first run and every read command,
      the web footer and every assessment view, the report, `README.md`, and
      `DISCLAIMER.md` in both files; earlier phases' tests prove each.
    - Open issues: #33 (the operator's question about surge and extreme-wind
      products; no ladder change in 2.0.0), #121 (a development-only
      advisory; Step 1's lock, minimatch 11.0.9, closed #79 in PR #129), #95
      (the conditional tile proxy). Any Dependabot pull request opened since
      Step 1 needs a disposition too.
    - PyPI's 1.0.0 declares `Requires-Python >=3.11` (Decision 17).

    Files to read (every file before drafting):

    - docs/roadmap/phase09-roadmap.md (Decisions 5, 8, 13, 16, and 17, and
      this step), docs/RELEASING.md, docs/release-readiness-2.0.0.md, and
      docs/MIGRATING.md.
    - docs/roadmap/ROADMAP.md ("Release & tagging", "Rollback", Phase 9).
    - README.md (`## Status`), CHANGELOG.md, and scripts/set_version.py.
  </context>

  <goal>
    Complete and sign the readiness record, release 2.0.0 to PyPI through the
    rehearsed path, verify it fresh on both runners and on the operator's
    service, prove the canary's alarm, and settle version 1's fate with the
    operator.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Complete the record (before the PR): `gitleaks git --redact` over the
      full history (exit 0); `uv run python scripts/check_personal_data.py
      --all` with the operator's denylist (exit 0); `scripts/audit_deps.py`,
      `npm --prefix frontend audit --audit-level=high --omit=dev`, and `npm
      --prefix frontend run licenses:check` (exit 0, with #121 named as
      development-only, absent from the wheel); each disclaimer surface
      with the test that proves it; dispatch `live-smoke.yml` on `main` and,
      when it passes, refresh the `Verified` date of each register row whose
      source it exercised; confirm from `scripts/check_dist.py`'s rules and
      rc2's files that no demonstration data or recording ships; the soak's
      end (at least 24 hours of rc1 or rc2 on the operator's service with
      `doctor` passing and no stale heartbeat, read from `/api/health` and
      `doctor`); Step 6's durations; and a disposition for every open issue
      and pull request. Then show the operator the record's summary in the
      chat and ask, with AskUserQuestion, whether they sign it; record the
      sign-off and its date.
    </requirement>

    <requirement>
      The PR: `uv run python scripts/set_version.py 2.0.0`; `## [2.0.0] -
      <today>` above the candidates' sections with the release summary (at
      most forty lines: what 2.0.0 is, what breaks from 1.0.0, Python 3.13 or
      later, the migration note, LAN mode, the corpus archive, and that the
      candidates' entries below are part of the release), keeping one `##
      [Unreleased]`; the README's `## Status` saying 2.0.0 is released (and no
      longer that no version 2 package is released); the project roadmap's
      Rollback table with the measured times; the record linked from the PR
      body. Merge when green.
    </requirement>

    <requirement>
      After the merge: in the chat, state the tag, the commit, the record's
      sign-off, what the workflow will do, and that the operator will approve
      the `pypi` deployment; ask with AskUserQuestion. On a yes: `git tag -a
      v2.0.0 -m "Weatherbot 2.0.0" <merge commit>` and `git push origin
      v2.0.0`; watch the run; when `publish-pypi` waits, download `dist`,
      extract both files into a temporary directory, scan the extracted files
      with the denylist, match their digests to the build, and only then ask
      the operator to approve in GitHub's interface. If PyPI refuses the
      trusted publisher, fix the publisher and re-run the job on the same tag
      (`docs/RELEASING.md`); never re-tag.
    </requirement>

    <requirement>
      Read back PyPI's JSON (2.0.0 latest; the files' digests equal the
      build's and the GitHub Release's), its integrity endpoint for each file,
      the project page's rendered description, and the GitHub Release (notes,
      files, corpus archive, `.sha256`).
    </requirement>

    <requirement>
      Upgrade the operator's service (Decision 16), after a yes, away from
      HH:25: `schtasks /End`, `uv tool install --reinstall weatherbot==2.0.0`
      (from PyPI), `schtasks /Run`; read `/api/health` (version `2.0.0`,
      `corpus` true — keep `[web] corpus` pointing at a corpus directory, the
      checkout's or the release archive's) and `doctor --offline --json`.
    </requirement>

    <requirement>
      The canary: dispatch `install-canary.yml` (expect both runners to
      install 2.0.0 and pass), then dispatch it with `simulate_failure` and
      ask the operator to confirm GitHub's failure email arrived; report both
      runs.
    </requirement>

    <requirement>
      Version 1 (Decision 17): explain the recommendation and ask with
      AskUserQuestion; on a yes, the operator yanks 1.0.0 on pypi.org with the
      reason "Retired; install weatherbot 2.x (Python 3.13 or later), or pin
      ==1.0.0"; verify in a temporary environment that `pip install --no-deps
      weatherbot==1.0.0` still installs and that an unpinned install on Python
      3.12 finds no version (uv's `--python 3.12 --dry-run` is enough). Report
      the decision either way; Step 8's PR records it and makes
      `docs/MIGRATING.md` match it.
    </requirement>

    <requirement>
      At Stage 6, write into Step 8's `<context>` the release's run URL, the
      digests, the canary runs, the operator's health readback, and the yank
      decision.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative path as the
      first line where the file type accepts comments.
    </requirement>
  </requirements>
</task>
```

### Step 7 acceptance criteria

- `docs/release-readiness-2.0.0.md` has every row filled with evidence and the
  operator's sign-off with its date, recorded before the tag; this step's PR
  body links it; the project roadmap's Rollback table gives the measured
  yank-and-patch and reinstall times.
- `main` reads `2.0.0` everywhere (`Development Status :: 5 -
  Production/Stable`, the README's links on `v2.0.0`); `CHANGELOG.md` holds `##
  [2.0.0] - <date>` under the one `## [Unreleased]`; the README's `## Status`
  says 2.0.0 is released; every gate and all eight verifiers' `--fast` pass.
- **Deployed & verified:** `v2.0.0` is an annotated tag on this step's merge
  commit, made after the operator's yes; `release.yml`'s run for it passed every
  job, `publish-pypi` approved by the operator after a clean denylist scan;
  `https://pypi.org/pypi/weatherbot/json` reports `2.0.0` as the latest version
  with one wheel and one sdist whose SHA-256 equal the run's build and the
  GitHub Release's assets, and PyPI's integrity endpoint answers a provenance
  for each; all four `smoke-published` entries passed (`uv tool install
  weatherbot==2.0.0` and `pip install weatherbot==2.0.0`, Python 3.13 and the
  newest, both runners, no Node, key, topic, or corpus); and `GET
  http://127.0.0.1:8765/api/health` on the operator's machine answers
  `"version": "2.0.0"` from the PyPI install, `ui.present` true, the database at
  `0010`, and `corpus` true, with `doctor --offline --json` passing.
- The install canary's dispatched run installed 2.0.0 and passed on both
  runners, and a dispatch with `simulate_failure` failed and reached the
  operator as GitHub's failure email (the operator confirmed it arrived).
- 1.0.0 is yanked with a reason, or the operator declined; the decision, its
  date, the canary runs, and the release's readbacks are written into Step 8's
  `<context>`, and Step 8's PR records them in the readiness record and makes
  `docs/MIGRATING.md` match the decision.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff; the published files passed the denylist scan
  before the upload was approved; no long-lived token exists for PyPI; and every
  outward action (the tag, the approval, the upgrade, the yank) followed the
  operator's yes.

---

## Step 8 — QA & Verification Script

**Status:** Not started

> **Goal:** Package the verification matrix into `scripts/verify_phase09.py`
> (with `--fast`, `--py`, `--node`, `--ui`, `--live`, `--security`, `--all`, and
> `--post`), produce `docs/phase09-qa-findings.md`, and add `"09"` to the
> `phase-verify.yml` matrix with its own Node steps. The script checks every
> Step 1 to Step 7 deliverable — reading every release fact at the `v2.0.0` tag
> (Decision 14) — runs the Phase 9 test slices in the appropriate modes, and in
> `--post` nests `verify_phase08.py --post` (expecting 98) and probes PyPI,
> TestPyPI, the GitHub Releases, the release and canary runs, the repository's
> settings, and the operator's service. This step records Step 7's post-merge
> evidence and the 1.0.0 decision in the readiness record, closes Phase 9 in
> this roadmap and the project roadmap, and ends the roadmap.

**Branch:** `feature/phase09-step8-verify`

**Deploys:** nothing beyond merge — the CI matrix entry is live on merge.

Settings — ladder (`roadmodel ladder --category coding --complexity medium`):

|               |          | Cost                 | Balanced              | Quality             |
| ------------- | -------- | -------------------- | --------------------- | ------------------- |
| **Pick**      | Model    | **Gemini 3.8 Flash** | **Gemini 4 Hydrogen** | **Opus 5.5**        |
|               | Platform | Antigravity          | Gemini (web / app)    | Claude Code         |
|               | Level    | Medium               | Low                   | High                |
|               | AA       | 39.8                 | ≈43.1                 | 53.6                |
|               | Price    | $1.99/1M             | ≈$2.25/1M             | $6.76/1M            |
| **Runner‑up** | Model    | **GPT-6.2 Sol**      | **Opus 5.5**          | **Gemini 4 Carbon** |
|               | Platform | Codex                | Claude Code           | Gemini (web / app)  |
|               | Level    | Low                  | Medium                | High                |
|               | AA       | ≈44.1                | 51.2                  | ≈53.6               |
|               | Price    | ≈$3.00/1M            | $6.39/1M              | ≈$4.00/1M           |
| **Backup**    | Model    | **Sonnet 5.5**       | **GPT-6.2 Sol**       | **GPT-6.2 Sol**     |
|               | Platform | Claude Code          | Codex                 | Codex               |
|               | Level    | Medium               | Medium                | High                |
|               | AA       | 40.8                 | ≈49.8                 | ≈52.2               |
|               | Price    | $3.18/1M             | ≈$3.50/1M             | ≈$4.00/1M           |

Ranked for coding, medium complexity. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level. ≈
estimated from the model's measured levels or its previous version's.

**Conversation:** New

> Settings updated 2026-11-19 (refresh): Cost Pick was GPT-6.1 Sol · Medium, Balanced Pick was
> GPT-6.1 Sol · High, Quality Pick was Gemini 4 Argon · High, Cost Runner-up was Sonnet 5.5 · High,
> Balanced Runner-up was Gemini 4 Carbon · Medium, Quality Runner-up was Opus 5.5 · High, Cost
> Backup was Gemini 4 Argon · Low, Balanced Backup was Opus 5.5 · Medium, Quality Backup was GPT-6.1
> Sol · High. Re-ranked against the current roadmodel catalog.

**Model rationale:** Step 8 is coding with a long-context secondary category —
the mechanical translation of `verify_phase08.py`'s structure into this phase's
deliverables, about fifty-six static checks and thirty-two V rows, a test file,
a findings ledger, a matrix entry, and the closure edits — at Medium complexity,
not novel: the template, the output format, and the nesting rule are all fixed.
On the step alone, the Balanced Pick fits best: Gemini 4 Hydrogen on Gemini (web
/ app) at Low. It balances the reasoning demands of this classification with
estimated token cost. The Cost Pick is Gemini 3.8 Flash on Antigravity at
Medium, and the Quality Pick is Opus 5.5 on Claude Code at High.

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
       feature/phase09-step8-verify`
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
       Phase 9 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 9`
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
       shape "Step 8 is
       complete. Phase 9 is
       complete. The roadmap is
       complete." That
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
       one before any later work.
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

    THIS STEP also authors the `--security` mode, so its own diff must pass
    the gate before commit. Its probes read PyPI's, TestPyPI's, and GitHub's
    public APIs and the operator's service through `/api/health` and `doctor`
    only; they print versions, digests, run conclusions, and counts, never the
    operator's place, the LAN address, a token, or a scanned file's content.
    The nested `--post` passes the operator's credentials to child processes
    the way Phases 6 to 8 do (`_operator_ai_env()` in Phase 6,
    `_operator_secret_env()` in Phases 7 and 8). Before `--post` runs, the
    agent states in the chat that the nested phases run desktop tests (real
    toasts and a Task Scheduler probe) and `simulate_advisory.py` on the
    operator's desktop and spend about $0.40 on Phase 6's live eval, and asks
    with AskUserQuestion.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 9 (Release 2.0). Step 8: QA +
    verification script.

    Steps 1 through 7 have been implemented and 2.0.0 is on PyPI. Step 7's
    Stage 6 writes below this line the release's run URL, the digests, the
    canary runs, the operator's health readback, and the 1.0.0 decision, which
    this step's PR records in `docs/release-readiness-2.0.0.md` (and in
    `docs/MIGRATING.md`, if the decision changed it).

    Reference scripts (pattern templates):

    - scripts/verify_phase08.py (closest structural precedent: 60 static
      checks, 38 V rows, eight modes, the nested `--post` at "107",
      `NESTED_SWEEP_TIMEOUT_SECONDS`, the JUnit evidence rules, ASCII
      descriptions).
    - scripts/verify_phase07.py (secondary pattern reference: the live probes
      and `_operator_secret_env()`).

    Phase 9 deliverables to verify (50 static checks across Steps 1 through 7
    plus 6 Step 8 self-checks). A check marked "at the tag" reads `git show
    v2.0.0:<path>` through a `tagged()` helper (Decision 14):

    Step 1 (what ships is tested) — checks 1-7:
    1. At the tag, the five pywinrt requirements carry the `sys_platform ==
       'win32'` marker, `winrt-runtime` has a floor of 4.2.0 or later and
       `<5`.
    2. At the tag, every runtime requirement of 1.0 or later has an upper
       bound.
    3. At the tag, the classifiers name Python 3.13, 3.14, and 3.15; live,
       `requires-python` is `>=3.13`.
    4. At the tag, `ci.yml`'s `test` and `package` jobs name `"3.15"` and
       `UV_PYTHON`, and its 3.13 entries keep the names `test (<os>)`.
    5. `tests/test_dependency_policy.py` is tracked.
    6. `verify_phase06.py`'s check 1 reads its anthropic clause through
       `tagged("pyproject.toml", tag=PHASE_6_TAG)`.
    7. `verify_phase08.py`'s check 52 reads `tagged("README.md",
       tag=PHASE_8_TAG)`.

    Step 2 (release pipeline) — checks 8-17:
    8. `scripts/set_version.py`, `check_dist.py`, and `release_smoke.py` and
       their tests are tracked.
    9. `tests/test_release_metadata.py` is tracked and `tests/test_cli.py`
       holds no version literal.
    10. `tests/contract/test_recorded_fixtures.py` checks the manifests'
        User-Agent by pattern.
    11. `release.yml` triggers on the two release-tag patterns and
        `workflow_dispatch` only.
    12. `release.yml`'s top-level permissions are `{}`; `id-token: write`
        appears only in the two publish jobs and `contents: write` only in
        `github-release`.
    13. The publish jobs name the `testpypi` and `pypi` environments and a
        SHA-pinned `pypa/gh-action-pypi-publish`, and TestPyPI's names
        `https://test.pypi.org/legacy/`.
    14. `release.yml` runs `check_dist.py` and `release_smoke.py`, smokes on
        both runners and Python 3.15, and attaches
        `weatherbot-replay-corpus-`.
    15. `install-canary.yml` has a schedule, `workflow_dispatch`,
        `simulate_failure`, and `--latest`.
    16. `ci.yml`'s `package` job runs `check_dist.py` after `uv build` and
        before the smoke.
    17. `docs/RELEASING.md` and `docs/release-readiness-2.0.0.md` are tracked
        with their required headings.

    Step 3 (LAN mode) — checks 18-27:
    18. `WebSettings` declares `lan`, `lan_address`, and `lan_hosts`, and
        `ENVIRONMENT_OVERRIDES` maps them.
    19. `services/lan.py` defines `TOKEN_VARIABLE = "WEATHERBOT_WEB_TOKEN"`,
        `MIN_TOKEN_LENGTH = 32`, `SessionSigner`, `FailureLimiter`, and
        `RateLimiter`.
    20. `services/lan.py` compares with `hmac.compare_digest`.
    21. `web/guards.py` defines `LanAuthGuard`.
    22. `web/routes/session.py` serves `/api/session`, which
        `docs/api/openapi.json` holds.
    23. `HealthResponse` declares `lan`, and the health fixture holds it.
    24. `services/logs.py`'s secret variables include `WEATHERBOT_WEB_TOKEN`.
    25. `cli/serve.py` calls `lan_problems` and its warning names unencrypted
        traffic.
    26. `frontend/src/lan/TokenPrompt.tsx` and its test are tracked, and
        `notify.ts` reads `isSecureContext`.
    27. At the tag, `docs/LAN.md` reads "Supported".

    Step 4 (documentation) — checks 28-36:
    28. At the tag, `README.md` holds no relative link and pins its repository
        links to `v2.0.0`.
    29. At the tag, `README.md` has `## Install` naming `uv tool install
        weatherbot`.
    30. `docs/GUIDE.md`, `docs/ALWAYS-ON.md`, `docs/TROUBLESHOOTING.md`, and
        `docs/MIGRATING.md` are tracked.
    31. `docs/CONFIGURATION.md` and `scripts/export_config_reference.py` (with
        `--check`) are tracked.
    32. `docs/images/` holds six PNG files, each at most 300 KB and all at
        most 2 MB.
    33. `frontend/playwright.docs.config.ts`,
        `frontend/docs-capture/capture.spec.ts`, and the `docs:screenshots`
        script exist, and `playwright.config.ts` still holds
        `/@idle|@dogfood/`.
    34. `verify_phase08.py`'s check 54 reads `tagged("README.md",
        tag=PHASE_8_TAG)`.
    35. `tests/test_docs.py` is tracked.
    36. `SECURITY.md` names 2.0.x as supported.

    Step 5 (release candidate) — checks 37-39:
    37. `CHANGELOG.md` holds `## [2.0.0rc1] - ` with an ISO date.
    38. `v2.0.0rc1` is an annotated tag whose `pyproject.toml` reads
        `2.0.0rc1` and whose commit is on `main`.
    39. `docs/release-readiness-2.0.0.md` holds rc1's run and soak rows
        (recorded by Step 6's PR).

    Step 6 (readiness rehearsals) — checks 40-43:
    40. `v2.0.0rc2` is an annotated tag whose `pyproject.toml` reads
        `2.0.0rc2` and whose commit is on `main`.
    41. `CHANGELOG.md` holds `## [2.0.0rc2] - ` with an ISO date.
    42. The record holds the LAN gate's rows (Step 6's PR) and the rehearsal's
        durations (Step 7's PR).
    43. The project roadmap's Rollback table no longer says "TBD once
        rehearsed" (Step 7's PR).

    Step 7 (2.0.0) — checks 44-50:
    44. `v2.0.0` is an annotated tag on `main` whose `pyproject.toml` reads
        `2.0.0` with `Development Status :: 5 - Production/Stable`.
    45. `CHANGELOG.md` holds `## [2.0.0] - ` with an ISO date and exactly one
        `## [Unreleased]`.
    46. At the tag, `README.md`'s `## Status` names 2.0.0 released.
    47. At the tag, the record holds the operator's sign-off with a date.
    48. The project roadmap's "Release & tagging" table lists `v2.0.0rc1`,
        `v2.0.0rc2`, and `v2.0.0`.
    49. At the tag, `docs/api/openapi.json` and the health fixture read
        `2.0.0`.
    50. At the tag, the register's User-Agent block reads `weatherbot/2.0.0`.

    Step 8 self-checks — checks 51-56:
    51. `scripts/verify_phase09.py` is tracked, parses, and declares 56 static
        checks, 32 V rows, eight modes, and the nested total "98".
    52. `docs/phase09-qa-findings.md` exists with its rollup sections.
    53. `docs/roadmap/phase09-roadmap.md` (this doc) holds Steps 1 to 8, and
        the project roadmap holds `### Phase 9 — Release 2.0`.
    54. `.github/workflows/phase-verify.yml`'s one-line matrix includes `"01"`
        to `"09"`, with its Phase 9 Node pair.
    55. The security gate is wired (the pre-commit hooks and `--security` in
        `phase-verify.yml`) and no secret shape is tracked under the phase's
        paths.
    56. `tests/test_phase09_verification.py` is tracked.

    Files to read:

    - scripts/verify_phase08.py (primary structural template) and
      tests/test_phase08_verification.py.
    - all Phase 9 implementation files from Steps 1 through 7,
      docs/release-readiness-2.0.0.md, and docs/RELEASING.md.
  </context>

  <goal>
    Create `scripts/verify_phase09.py` with 56 static checks (50 across Steps
    1 through 7, 6 self-checks) and a V1-V8 matrix of 32 rows; create
    `docs/phase09-qa-findings.md`; add `"09"` to the `phase-verify.yml` matrix
    with its Node pair; record Step 7's evidence; and close Phase 9 and the
    roadmap.
  </goal>

  <requirements>
    <requirement>
      Read scripts/verify_phase08.py end-to-end for structure, flag parsing,
      output format, the `Check` and `VRow` conventions, the JUnit evidence
      rules, the nested `--post` (`capture(...,
      timeout=NESTED_SWEEP_TIMEOUT_SECONDS, env=_operator_secret_env())`, the
      totals block read with the same pattern `verify_phase08.py` uses,
      indented `[FAIL]`/`[SKIP]` lines read with `line.lstrip()`), and the
      final summary block. Mirror the format exactly so the Phase 9 script is
      visually continuous with Phase 8's in CI logs.
    </requirement>

    <requirement>
      `scripts/verify_phase09.py` modes (mutually exclusive):
      - `--fast`: the static checks only, standard library only, CI-safe on
        Ubuntu, under 30 seconds; no network, no subprocess beyond `git`.
      - `--py`: ruff, ruff format, pyright (both platforms), lint-imports,
        pytest with JUnit XML and the four 90 percent floors,
        `export_schemas.py --check`, `export_openapi.py --check`,
        `export_api_fixtures.py --check`, `export_config_reference.py
        --check`, `export_ladder.py --check`, `set_version.py --check`, and
        `uv build` into a temporary directory checked by `check_dist.py`.
      - `--node`: ESLint, typecheck, Vitest with JUnit, the build, and
        `licenses:check`.
      - `--ui`: the default Playwright run (excluding `@idle` and `@dogfood`).
      - `--live`: PyPI's and TestPyPI's JSON and integrity endpoints, the
        GitHub Releases' assets, and the release, canary, and live-smoke runs
        through `gh api`.
      - `--security`: the security gate over both stacks and a secret-shape
        scan over the Phase 9 paths (exits non-zero on any finding).
      - `--all`: `--py`, `--node`, `--ui`, `--live`, and `--security`.
      - `--post`: `--all`, then `verify_phase08.py --post` (expect "98"), then
        the probes (the environments and the ruleset read back;
        `protection_requires_both`; the operator's `/api/health` at `2.0.0`
        with `ui.present`, `corpus` true, and the database at `0010`; `doctor
        --offline --json` passing `web`; with LAN mode on, an unauthenticated
        request to the LAN address answering 401; and the `--fast` budget),
        then the V matrix. Each static check prints `[PASS] NN: description
        (detail)`; descriptions are ASCII.
    </requirement>

    <requirement>
      At least ONE static check must be security-oriented and confirm the
      security gate is wired, not bypassed: check 55 (the pre-commit hooks for
      gitleaks, the personal-data check, bandit, and pip-audit; `--security`
      in `phase-verify.yml`; no private-key PEM header — the five-dash BEGIN
      line — and no key prefix such as `AKIA` or `ghp_` committed under the
      phase's paths). Checks 12 and 13 hold the release workflow's trust
      boundary.
    </requirement>

    <requirement>
      Post-implementation V-checks (V1-V8, 32 rows; every row cites JUnit
      evidence, a command, or an API readback, and a skip is never a pass):
      - V1 (4): V1.1 static 1-7; V1.2 tests/test_dependency_policy.py; V1.3
        the toast tests (JUnit, on Windows); V1.4 the latest `ci.yml` run on
        `main` passed its 3.13 and 3.15 entries on both runners.
      - V2 (4): V2.1 static 8-17; V2.2 the release-metadata, check-dist,
        release-smoke, and workflow tests; V2.3 a fresh `uv build` passes
        `check_dist.py`; V2.4 the environments and the ruleset read back as
        Step 2 set them.
      - V3 (4): V3.1 static 18-27; V3.2 the LAN pytest files; V3.3 the LAN
        Vitest files; V3.4 the operator's `/api/health` `lan` agrees with the
        record's choice, and with LAN on an unauthenticated LAN request
        answers 401.
      - V4 (4): V4.1 static 28-36; V4.2 tests/test_docs.py and the reference's
        test; V4.3 the reference, ladder, and schema `--check` runs; V4.4 the
        README at the tag pins every repository link to `v2.0.0`.
      - V5 (3): V5.1 static 37-39; V5.2 TestPyPI lists rc1 (yanked) and rc2
        with digests equal to their GitHub pre-releases' assets; V5.3 the
        release runs for both candidates passed every job.
      - V6 (3): V6.1 static 40-43; V6.2 on TestPyPI, `==2.0.0rc1` still
        resolves while `--pre "weatherbot<2.0.0rc2"` finds no version (`pip
        download --no-deps` into a temporary directory); V6.3 the record's LAN
        gate and rehearsal rows hold dates and durations.
      - V7 (5): V7.1 static 44-50; V7.2 PyPI's latest is 2.0.0, its files'
        digests equal the GitHub Release's, and each has a provenance; V7.3
        the release run for `v2.0.0` passed every job, with four
        `smoke-published` entries; V7.4 the operator's `/api/health` reads
        `2.0.0` and `doctor --offline --json` passes; V7.5 the canary's latest
        real run passed (its `run-name` tells real runs from simulated ones)
        and a simulated run failed.
      - V8 (5): V8.1 `--fast` exits 0 in `phase-verify (09)`; V8.2 the matrix
        includes `"09"`; V8.3 every static check passes; V8.4 `--security`
        exits 0; V8.5 the nested `verify_phase08.py --post` reported 98 with
        none failed or skipped.
    </requirement>

    <requirement>
      Create tests/test_phase09_verification.py: `--fast` under 30 seconds;
      `"09"` in the matrix; one red-check isolation per step (a fixture
      repository whose single missing deliverable fails exactly its check,
      including the tagged reads); JUnit evidence that fails closed on a skip;
      probe failures reported, not raised; and the subprocess tests set
      `PYTHONIOENCODING="utf-8"`.
    </requirement>

    <requirement>
      Update `.github/workflows/phase-verify.yml`: append `"09"` to the
      one-line `matrix.phase` list and add `Set up Node (Phase 9)` and
      `Install frontend dependencies (Phase 9)` under `if: "!cancelled() &&
      matrix.phase == '09'"`, pinned like the others
      (`actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0`
      or its successor's SHA and comment), leaving `'05'` to `'08'` untouched.
      Preserve every prior entry; this is an additive change.
    </requirement>

    <requirement>
      Create `docs/phase09-qa-findings.md`: a rollup for this roadmap's PR and
      Steps 1 to 7 (each finding, its class, and the guard added), the Step 8
      verify-script rollup with the measured nested `--post` duration and the
      timeout set from it, the release's evidence (versions, digests, runs,
      the canary's alarm), the exact-versus-growth-proof table for Phase 9's
      checks (every release fact reads at `v2.0.0`, so a 2.0.x changes none),
      and a "Pre-ship items" section noting documented limitations and their
      destinations in the 2.0.x line.
    </requirement>

    <requirement>
      Record Step 7's evidence and the 1.0.0 decision in
      `docs/release-readiness-2.0.0.md`, and make `docs/MIGRATING.md` match
      the decision. Add a `### Phase 9 verification` note under the one `##
      [Unreleased]` in `CHANGELOG.md`.
    </requirement>

    <requirement>
      Mark the phase complete in the project roadmap (docs/roadmap/ROADMAP.md,
      beside this file) in the SAME Stage-3 commit that marks this step
      (Status rule):
      - `### Phase 9 — Release 2.0` gets `**Status:** Complete — <YYYY-MM-DD>;
        PR #<n>; v2.0.0; phase09-roadmap.md` directly under its heading, and
        the heading ends in ✅.
      - Its row in the "Phase Complexity Summary" table reads `Complete` (Step
        1's PR set it to `In progress`).
      - The header `> **Status:**` line names Phase 9 as complete and
        Weatherbot 2.0.0 as released, and says the roadmap is complete.
      - Consistency audit: the Phase 9 "Acceptance criteria" there match this
        roadmap's V1-V8 checks. And in THIS roadmap, same commit: its
        phase-level `**Status:**` line (under the title) reads `Complete —
        <YYYY-MM-DD>`, the title and every step heading end in ✅, and every
        step's Summary Table Status cell reads `Complete — PR #<n>`.
    </requirement>

    <requirement>
      Script must be tracked and runnable (`uv run python
      scripts/verify_phase09.py --fast`), print clear pass / fail per check,
      exit 0 on success, exit 1 on any failure. Mirror the exact output
      format, check-numbering convention, and summary table from
      verify_phase08.py so CI log diffing across phases is frictionless.

      `--fast` must complete in under 30 seconds on Ubuntu CI.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repo-relative path as the
      first line.
    </requirement>
  </requirements>
</task>
```

### Step 8 acceptance criteria

- `scripts/verify_phase09.py` exists, is tracked, and passes on a clean tree
  after Step 7: 56 static checks and 32 V rows (88 in `--post`), in eight
  mutually exclusive modes, with `verify_phase08.py`'s output format, `[PASS]`,
  `[FAIL]`, and `[SKIP]` lines, and summary block.
- `--fast` runs in under 30 seconds on Ubuntu CI with the standard library only,
  and its `STATIC_CHECKS` descriptions are ASCII.
- `--post` runs cleanly on the operator's machine with 2.0.0 installed: the
  nested `verify_phase08.py --post` reports 98 with none failed or skipped,
  under a nested timeout set at least 1.5 times the duration measured in this
  step, and every Phase 9 probe passes.
- `docs/phase09-qa-findings.md` is complete, with every rollup section and the
  measured `--post` duration.
- `.github/workflows/phase-verify.yml`'s matrix line ends `"08", "09"]`, its
  `Set up Node (Phase 9)` and `Install frontend dependencies (Phase 9)` steps
  run under `matrix.phase == '09'`, the other phases' steps are untouched, and
  `phase-verify (09)` appears and passes on this PR.
- `--security` exists and exits 0 (secret/personal-data scan, SAST, and
  dependency audit clean over the phase's surface); V8.4 is green.
- Branch protection still passes on the resulting PR (`gate` and
  `phase-verify`).
- **Operations:** the published package's health signal and alarm exist and have
  been seen to fire: the install canary's latest real run installed 2.0.0 on
  both runners, and its `simulate_failure` dispatch failed and reached the
  operator as GitHub's failure email (Step 7); `--post` reads the canary's
  latest run, and `/api/health` with `doctor` on the operator's 2.0.0.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff and the security workflow is green.
- **Phase closed, nothing carried.** Every finding recorded in
  `docs/phase09-qa-findings.md` has a destination (fixed, an issue number, or
  the 2.0.x line), the "Not in scope" section below is current, and no
  un-tracked item remains. Every step of this roadmap, this one included, reads
  `**Status:** Complete — PR #…` on `main` under a ✅ heading, the Summary
  Table's Status column and this roadmap's phase-level Status line say
  `Complete` under a ✅ title, and the project roadmap's Phase 9 entry (under a ✅
  heading), its summary-table row, and its header status line say `Complete` —
  all landed in this step's PR. This step's final response ends with one line
  and nothing after it: "Step 8 is complete. Phase 9 is complete. The roadmap is
  complete." — the last step of the last phase names no next step or phase; same
  Stage 6 rule: no "Follow-ups", no trailer.

---

## Post-Implementation Verification

Every V1–V8 check below runs **automatically in CI** on every push and pull
request, except these. The registry, release, and canary readbacks (V1.4, V2.4,
V5.2, V5.3, V6.2, V7.2, V7.3, V7.5) read public APIs and GitHub's run history in
`--live` and `--post`, because they verify events — an upload, a yank, a
scheduled run — that a pull request's checks cannot cause; the operator's
service (V3.4, V7.4) and the nested Phase 8 sweep (V8.5) run in `--post` on the
operator's Windows machine, because they need the installed 2.0.0, the
operator's environment, and several hours, and the nested sweep in turn nests
Phases 7 to 1 and spends about $0.40 on Phase 6's live AI eval, after the
operator's yes. The releases themselves are operator wall-clock work in Steps 5
to 7, each gated by the operator's yes and approval, and recorded in
`docs/release-readiness-2.0.0.md`; the toast test (V1.3's desktop half) and the
LAN gate (V3.4's first proof) happened once on the operator's machine and are
evidence in the record. CI never holds a PyPI token, an Anthropic credential, an
ntfy topic, or a LAN token: publishing uses OIDC inside an approved environment,
and every test uses a fake built at run time.

| Mode         | Workflow                        | Runner  | Coverage          |
| ------------ | ------------------------------- | ------- | ----------------- |
| `--fast`     | `phase-verify.yml` (`"09"`)     | Ubuntu  | static checks     |
| `--py`       | `ci.yml` test, package          | both    | Python rows       |
| `--node`     | `ci.yml` frontend               | Ubuntu  | frontend rows     |
| `--ui`       | `ci.yml` browser                | Ubuntu  | browser rows      |
| `--security` | `ci.yml` security, phase-verify | Ubuntu  | V8.4              |
| `--live`     | none (local; public APIs)       | any     | release readbacks |
| `--all`      | none (local)                    | Windows | all but post      |
| `--post`     | local, operator's machine       | Windows | every V row       |

In the tables, `fast` is `phase-verify.yml`'s `--fast`, `ci` is `ci.yml`'s
`test` job (`--py`), `node` its `frontend` job (`--node`), `ui` its `browser`
job (`--ui`), `sec` the `security` job and `--security`, `live` the `--live`
readbacks, and `post` the operator's machine only.

Local invocations remain available for ad-hoc runs and pre-release sweeps:

```bash
uv run python scripts/verify_phase09.py --post   # static + V1-V8 + post checks
```

`--post` is the canonical command to run before declaring the phase closed. It
builds into temporary directories, starts demonstration servers and a headless
browser in temporary data directories, asks before the nested live AI eval and
states its cost, reads the operator's running service only through `/api/health`
and `doctor`, and says so before it starts.

Other modes:

```bash
uv run python scripts/verify_phase09.py --fast      # static only (CI-safe)
uv run python scripts/verify_phase09.py --py        # + lint, types, tests
uv run python scripts/verify_phase09.py --node      # + frontend toolchain
uv run python scripts/verify_phase09.py --ui        # + browser smoke
uv run python scripts/verify_phase09.py --live      # + release readbacks
uv run python scripts/verify_phase09.py --security  # the gate, both stacks
uv run python scripts/verify_phase09.py --all       # all but --post
```

The script reports each V-check by id (V1.1, V2.1, ...) so a failure in any
workflow above maps directly to the corresponding row below.

### V1 — What ships is what CI tests

> **Automated in CI.** `phase-verify.yml` → V1.1; `ci.yml` → V1.2 and V1.3;
> `--live` → V1.4.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V1.1  | Static checks 1–7 all PASS.                                  | fast |
| V1.2  | `test_dependency_policy.py`: caps, Pythons, 3.15 wheels.     | ci   |
| V1.3  | The toast tests pass on Windows against pywinrt 4.           | ci   |
| V1.4  | `main`'s last `ci.yml` run passed 3.13 and 3.15, both OSes.  | live |

### V2 — The release pipeline

> **Automated in CI.** `phase-verify.yml` → V2.1; `ci.yml` → V2.2 and V2.3;
> `--post` → V2.4.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V2.1  | Static checks 8–17 all PASS.                                 | fast |
| V2.2  | Release-metadata, check-dist, smoke, and workflow tests.     | ci   |
| V2.3  | A fresh `uv build` passes `check_dist.py`.                   | ci   |
| V2.4  | Both environments and the tag ruleset read back as set.      | post |

### V3 — LAN mode

> **Automated in CI.** `phase-verify.yml` → V3.1; `ci.yml` → V3.2; the
> `frontend` job → V3.3; `--post` → V3.4.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V3.1  | Static checks 18–27 all PASS.                                | fast |
| V3.2  | The LAN tests: refusals, 401s, cookies, limits, warning.     | ci   |
| V3.3  | `TokenPrompt.test.tsx`, the chip, and `notify.ts` pass.      | node |
| V3.4  | The operator's `lan` matches the record; LAN 401 when on.    | post |

### V4 — Documentation

> **Automated in CI.** `phase-verify.yml` → V4.1 and V4.4; `ci.yml` → V4.2 and
> V4.3.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V4.1  | Static checks 28–36 all PASS.                                | fast |
| V4.2  | `test_docs.py` and the configuration reference's test pass.  | ci   |
| V4.3  | The reference, ladder, and schema `--check` runs exit 0.     | ci   |
| V4.4  | The README at `v2.0.0` pins every repository link to it.     | fast |

### V5 — The release candidate

> **Automated in CI.** `phase-verify.yml` → V5.1; `--live` → V5.2 and V5.3.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V5.1  | Static checks 37–39 all PASS.                                | fast |
| V5.2  | TestPyPI's rc1 (yanked) and rc2 match their releases' files. | live |
| V5.3  | Both candidates' release runs passed every job.              | live |

### V6 — The readiness rehearsals

> **Automated in CI.** `phase-verify.yml` → V6.1 and V6.3; `--live` → V6.2.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V6.1  | Static checks 40–43 all PASS.                                | fast |
| V6.2  | Yanked rc1: an exact pin resolves; `<2.0.0rc2` does not.     | live |
| V6.3  | The record dates the LAN gate and times the rehearsal.       | fast |

### V7 — 2.0.0

> **Automated in CI.** `phase-verify.yml` → V7.1; `--live` → V7.2, V7.3, and
> V7.5; `--post` → V7.4.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V7.1  | Static checks 44–50 all PASS.                                | fast |
| V7.2  | PyPI's latest is 2.0.0; files match; provenance for each.    | live |
| V7.3  | The `v2.0.0` release run passed, four published smokes.      | live |
| V7.4  | The operator's health reads 2.0.0; `doctor` passes.          | post |
| V7.5  | The canary's last real run passed; a simulated one failed.   | live |

### V8 — CI integration + security

> **Automated in CI.** `phase-verify.yml` → V8.1 through V8.4 on every push/PR;
> `--post` → V8.5.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V8.1  | `verify_phase09.py --fast` exits 0 in `phase-verify (09)`.   | fast |
| V8.2  | `phase-verify.yml` matrix includes `"09"`.                   | fast |
| V8.3  | All 56 static checks in `verify_phase09.py` pass.            | fast |
| V8.4  | `--security` exits 0 (secret scan, SAST, dependency audit).  | sec  |
| V8.5  | Nested `verify_phase08.py --post` reports 98, none failed.   | post |

---

## Summary Table

| Step | Scope                          | Model          | Status             |
| ---- | ------------------------------ | -------------- | ------------------ |
| 1    | Tested dependencies, Pythons   | Gemini 4 Hydrogen | Complete — PR #129 |
| 2    | Release pipeline               | Opus 5.5       | Complete — PR #131 |
| 3    | LAN mode                       | Opus 5.5       | Not started        |
| 4    | Documentation                  | Opus 5.5       | Not started        |
| 5    | Release candidate (TestPyPI)   | Gemini 4 Hydrogen | Not started        |
| 6    | LAN gate, yank and patch       | Opus 5.5       | Not started        |
| 7    | 2.0.0 on PyPI                  | Opus 5.5       | Not started        |
| 8    | QA + verify_phase09.py         | Gemini 4 Hydrogen | Not started        |
| V1   | What ships is tested           | CI             | --                 |
| V2   | Release pipeline               | CI             | --                 |
| V3   | LAN mode                       | CI             | --                 |
| V4   | Documentation                  | CI             | --                 |
| V5   | Release candidate              | CI             | --                 |
| V6   | Readiness rehearsals           | CI             | --                 |
| V7   | 2.0.0                          | CI             | --                 |
| V8   | CI integration                 | CI             | --                 |

---

## Model selection blocks

```text
PROMPT: Step 1 — What ships is what CI tests
MODEL: Gemini 4 Hydrogen
BACKUP: GPT-6.2 Sol — Codex · Intelligence Medium
PLATFORM: Gemini (web / app)
EFFORT: Medium
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding, a lock upgrade, a dependency's new major, a CI matrix,
and two verifier conversions. On the step alone, the Cost Pick fits best: Gemini
4 Hydrogen on Gemini (web / app) at Medium. It meets the selection threshold at
the lowest estimated cost for this classification. The Balanced Pick is Gemini 4
Hydrogen on Gemini (web / app) at High, and the Quality Pick is Opus 5.5 on
Claude Code at XHigh.

PROMPT: Step 2 — The release pipeline
MODEL: Opus 5.5
BACKUP: GPT-6.2 Sol — Codex · Intelligence XHigh
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding, the release workflow, its environments, publishers,
ruleset, and scripts. On the step alone, the Quality Pick fits best: Opus 5.5 on
Claude Code at XHigh. It gives this classification priority for capability and
reasoning depth. The Cost Pick is Gemini 4 Hydrogen on Gemini (web / app) at
Medium, and the Balanced Pick is Gemini 4 Hydrogen on Gemini (web / app) at
High.

PROMPT: Step 3 — LAN mode
MODEL: Opus 5.5
BACKUP: GPT-6.2 Sol — Codex · Intelligence XHigh
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding, novel, the project's first authentication path. On the
step alone, the Quality Pick fits best: Opus 5.5 on Claude Code at XHigh. It
gives this classification priority for capability and reasoning depth. The Cost
Pick is Gemini 4 Neon on Gemini (web / app) at High, and the Balanced Pick is
Opus 5.5 on Claude Code at High.

PROMPT: Step 4 — Documentation
MODEL: Opus 5.5
BACKUP: GPT-6.2 Sol — Codex · Intelligence XHigh
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: long-context, documentation that must agree with the whole
codebase. On the step alone, the Quality Pick fits best: Opus 5.5 on Claude Code
at XHigh. It gives this classification priority for capability and reasoning
depth. The Cost Pick is Sonnet 5.5 on Claude Code at XHigh, and the Balanced
Pick is Opus 5.5 on Claude Code at High.

PROMPT: Step 5 — The release candidate
MODEL: Gemini 4 Hydrogen
BACKUP: GPT-6.2 Sol — Codex · Intelligence Medium
PLATFORM: Gemini (web / app)
EFFORT: Low
THINKING: On
CONVERSATION: New
RATIONALE: TASK: agentic, a scripted release run on TestPyPI with a human
approval inside it. On the step alone, the Balanced Pick fits best: Gemini 4
Hydrogen on Gemini (web / app) at Low. It balances the reasoning demands of this
classification with estimated token cost. The Cost Pick is Haiku 5.5 on Claude
Code at High, and the Quality Pick is Opus 5.5 on Claude Code at High.

PROMPT: Step 6 — The readiness rehearsals
MODEL: Opus 5.5
BACKUP: GPT-6.2 Astra — Codex · Intelligence XHigh
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: agentic, the first LAN exposure, a yank, a second candidate,
and timed rollbacks. On the step alone, the Quality Pick fits best: Opus 5.5 on
Claude Code at XHigh. It gives this classification priority for capability and
reasoning depth. The Cost Pick is Gemini 4 Hydrogen on Gemini (web / app) at
Medium, and the Balanced Pick is Sonnet 5.5 on Claude Code at XHigh.

PROMPT: Step 7 — 2.0.0
MODEL: Opus 5.5
BACKUP: GPT-6.2 Astra — Codex · Intelligence XHigh
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: agentic, the irreversible release and its readiness sign-off.
On the step alone, the Quality Pick fits best: Opus 5.5 on Claude Code at XHigh.
It gives this classification priority for capability and reasoning depth. The
Cost Pick is Gemini 4 Hydrogen on Gemini (web / app) at Medium, and the Balanced
Pick is Sonnet 5.5 on Claude Code at XHigh.

PROMPT: Step 8 — QA + verify_phase09.py
MODEL: Gemini 4 Hydrogen
BACKUP: GPT-6.2 Sol — Codex · Intelligence Medium
PLATFORM: Gemini (web / app)
EFFORT: Low
THINKING: On
CONVERSATION: New
RATIONALE: TASK: mechanical translation of the prior verify-script template into
this phase's deliverables. On the step alone, the Balanced Pick fits best:
Gemini 4 Hydrogen on Gemini (web / app) at Low. It balances the reasoning
demands of this classification with estimated token cost. The Cost Pick is
Gemini 3.8 Flash on Antigravity at Medium, and the Quality Pick is Opus 5.5 on
Claude Code at High.
```

---

## Not in scope (from product roadmap)

Per [`docs/roadmap/ROADMAP.md`](ROADMAP.md) Phase 9 and §6 "Out of Scope":

- Public hosting, multi-user accounts, and any authentication beyond the LAN
  token (§6). LAN mode serves one operator's devices on one home network.
- Coverage outside the three NHC basins, model-driven search, any forecast of
  Weatherbot's own, and automated evacuation orders (§6).
- Mobile applications, SMS, email, Slack, and Discord (§6). The phone opens the
  responsive page over LAN mode and receives ntfy pushes.
- A change to the ladder, its thresholds, the policy, a prompt, or an AI
  product, and the answer to issue #33. A rule change follows Phase 3's golden
  process with the operator's approval, in a release of its own.

Additionally not in scope for this phase:

- TLS for LAN mode (a certificate the phone must trust, renewal, and HSTS). LAN
  mode is unencrypted HTTP on a trusted home network, and its guide and warning
  say so; TLS is an issue for a later version.
- A QR code, a pairing link, or another aid for entering the token. A QR code
  needs a new package, and a link holding the token, even in its fragment, stays
  in the phone's history; the token prompt carries it in 2.0.0.
- A pre-release on PyPI, a conda-forge or winget package, a standalone
  executable, or a Docker image. PyPI's wheel and sdist are the only artifacts,
  beside the GitHub Release's copies and the corpus archive.
- Installing a Linux service automatically. `docs/ALWAYS-ON.md` gives an example
  systemd unit; `install-task` remains Windows-only.
- A `serve --check` flag. The project roadmap's 9.2 names one for the
  fresh-install smoke; `scripts/release_smoke.py`, which runs `serve` through
  `scripts/smoke_installed_web.py`, does that job without adding a command (the
  project roadmap records the change in this roadmap's PR).
- Shipping the replay corpus inside the wheel or downloading it from the
  application (Decision 7).
- A version after 2.0.0 (`2.0.1.dev0` or later). The first change after the
  release sets it, through `scripts/set_version.py`.
- Issue #121 (a development-only advisory, absent from the wheel), #95
  (the tile proxy, conditional on a refusal that has not come), and new
  Dependabot pull requests after Step 7. They belong to the 2.0.x line.
- Removing version 1 from the operator's `PATH`. The operator's housekeeping;
  `docs/MIGRATING.md` and `doctor`'s path check explain it.

---

_This roadmap is the execution plan for Phase 9. Each step's `**Status:**` line
is flipped by that step's own PR (Status rule), so this file on `main` is the
phase's ledger — `grep -n '^\*\*Status:\*\*'` reports progress. After all steps
and verification pass, and every finding has a destination, Phase 9 is complete
— declared with the line "Step 8 is complete. Phase 9 is complete. The roadmap
is complete." and nothing after it — and, with no Phase 10 to follow, the 2.0.x
line inherits a released Weatherbot 2.0.0 on PyPI: a dependency set that a clean
install resolves to exactly what CI tests on Python 3.13 to 3.15, a release
workflow that builds once from a protected tag and publishes only through OIDC
behind the operator's approval, a runbook rehearsed through a yank and a patch,
documentation written for a reader who installed it, an optional LAN mode proved
on the operator's own network, and an install canary that will say when the
world has broken a fresh install._
