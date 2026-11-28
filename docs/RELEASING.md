<!-- docs/RELEASING.md -->
# Releasing Weatherbot

This runbook covers cutting release candidates (`2.0.0rcN`) and public releases
(`2.0.0`, `2.0.1`, ...), publishing through OpenID Connect (OIDC) trusted
publishing, verifying the published package, handling yank-and-patch rollbacks,
and operating the weekly install canary.

## Version shapes and tags

Weatherbot keeps a single version in `pyproject.toml`, managed exclusively by
`scripts/set_version.py`. Only three canonical PEP 440 shapes are accepted:

| Stage             | Version shape | Git tag       | `Development Status` classifier            | README `blob/` / `raw/` links | Publish target |
| ----------------- | ------------- | ------------- | ------------------------------------------ | ----------------------------- | -------------- |
| Development       | `X.Y.Z.devN`  | none          | `Development Status :: 2 - Pre-Alpha`      | `main`                        | none           |
| Release candidate | `X.Y.ZrcN`    | `vX.Y.ZrcN`   | `Development Status :: 4 - Beta`           | `vX.Y.ZrcN`                   | TestPyPI only  |
| Public release    | `X.Y.Z`       | `vX.Y.Z`      | `Development Status :: 5 - Production/Stable` | `vX.Y.Z`                   | PyPI           |

- No pre-release is ever uploaded to PyPI; TestPyPI rehearses every release
  candidate (`2.0.0rc1`, `2.0.0rc2`).
- Every release tag must equal `v` plus the `pyproject.toml` version and point
  to a commit on `origin/main`.
- The repository tag ruleset (`Protect release tags`, `refs/tags/v*`, active,
  no bypass actors) blocks deleting, updating, or force-moving any `v*` tag.

## Setting and checking the version

Run `scripts/set_version.py` from a feature branch cut from `main`:

```sh
uv run python scripts/set_version.py 2.0.0rc1
uv run python scripts/set_version.py --check
```

`set_version.py` updates:

1. `pyproject.toml` (`version` via `uv version <v> --no-sync` and the
   `Development Status` classifier)
2. `uv.lock` (`weatherbot` package version)
3. `docs/api/openapi.json` (`scripts/export_openapi.py`)
4. `frontend/src/api/schema.d.ts` (`npm --prefix frontend run api:generate`)
5. `frontend/src/test/fixtures/health.json` (and any other fixture via
   `scripts/export_api_fixtures.py`)
6. `docs/DATA_SOURCES.md` (`## User-Agent` code block)
7. `README.md` (`blob/<ref>/` and `raw/<ref>/` links; never `tree/v1.0.0`)

`tests/test_release_metadata.py` fails in CI whenever any copy disagrees.

## Readiness record

Every public release is gated by its readiness record
([docs/release-readiness-2.0.0.md](release-readiness-2.0.0.md)). Fill every row
with measured evidence, verify the personal-data scan, gitleaks, dependency
audits, live source smoke (within 7 days of the tag), candidate soak, LAN gate,
and yank-and-patch rehearsal, and record the operator's sign-off and date in the
pull request that bumps the version to `2.0.0`. Link the readiness record from
that PR's body.

## Cutting a release candidate or public release

Two human gates stand before every upload: an explicit operator **yes** before
pushing the tag, and the operator's own deployment approval in GitHub's
interface (`testpypi` or `pypi` environment). An agent never approves a
deployment through the GitHub API.

1. **Prepare the version PR** on a branch cut from `main`:
   - Run `uv run python scripts/set_version.py <version>`.
   - Update `CHANGELOG.md` so `## [<version>] - YYYY-MM-DD` sits above the
     previous release with a concise summary paragraph before the first `###`
     heading (this summary becomes the GitHub Release notes, followed by a link
     to the full section at `v<version>`).
   - For a public release, complete and sign `docs/release-readiness-2.0.0.md`.
   - Pass all local checks (`ruff`, `pyright`, `lint-imports`, `pytest`,
     frontend tests, all `--fast` verifiers, and the security gate).
   - Open the PR, wait for `gate` and `phase-verify` to go green, and
     squash-merge to `main`.
2. **Sync `main` and get the operator's yes** before tagging:
   ```sh
   git switch main
   git pull --ff-only origin main
   ```
3. **Create and push the annotated tag** on the merge commit of `main`:
   ```sh
   git tag -a v<version> -m "Weatherbot <version>"
   git push origin v<version>
   ```
4. **Approve the deployment in GitHub:**
   - `.github/workflows/release.yml` starts automatically and runs `build` and
     all four `smoke-built` entries (Ubuntu/Windows x Python 3.13/3.15).
   - When `smoke-built` turns green, `publish-testpypi` (for `rcN`) or
     `publish-pypi` (for `X.Y.Z`) pauses for review in its environment.
   - Open the Actions run in GitHub, review the build summary, and approve the
     deployment yourself.
5. **Wait for post-publish verification:**
   - `smoke-published` polls the index up to 10 minutes and verifies clean
     installs on all four runner/Python combinations.
   - `github-release` creates the GitHub Release (`--prerelease` for `rcN`)
     attaching the wheel, sdist, `weatherbot-replay-corpus-<version>.zip`, and
     its `.sha256` checksum.

## What `.github/workflows/release.yml` does

Top-level `permissions: {}`, `concurrency.cancel-in-progress: false`, GitHub-hosted
runners only, SHA-pinned actions, and zero repository secrets:

| Job                | Permissions       | What it does                                                                                             |
| ------------------ | ----------------- | -------------------------------------------------------------------------------------------------------- |
| `build`            | `contents: read`  | Verifies tag == version and commit ancestry on `origin/main` (or `main` on dry run), builds the frontend and distributions once, runs `scripts/check_dist.py`, zips `tests/fixtures/replay/` with `.sha256`, uploads `dist` and `corpus`. |
| `smoke-built`      | `contents: read`  | Matrix (`ubuntu-latest`, `windows-latest` x Python `3.13`, `3.15`): runs `scripts/release_smoke.py --wheel` with Node stripped from `PATH` and secrets cleared. |
| `publish-testpypi` | `id-token: write` | Candidate tags only, `testpypi` environment: uploads `dist/` to `https://test.pypi.org/legacy/` via OIDC with PEP 740 attestations. |
| `publish-pypi`     | `id-token: write` | Release tags only, `pypi` environment: uploads `dist/` to PyPI via OIDC with PEP 740 attestations.       |
| `smoke-published`  | `contents: read`  | Runs when either publish job succeeded; matrix (`ubuntu-latest`, `windows-latest` x `3.13`, `3.15`): downloads/checks TestPyPI wheel by SHA-256 (installing deps from PyPI) or runs both `uv tool install` and `pip install` from PyPI. |
| `github-release`   | `contents: write` | Runs only after `smoke-published` succeeds: creates the GitHub Release with `CHANGELOG.md` summary, `dist/*`, and `corpus/*`. |

### Dry run (`workflow_dispatch`)

To test the build, allowlist, corpus packaging, and all four `smoke-built`
checks without publishing anything:

```sh
gh workflow run release.yml --ref main
```

Both publish jobs, `smoke-published`, and `github-release` are skipped on a
dispatched run.

## Distribution allowlist and smoke scripts

- `scripts/check_dist.py dist --version <v>` (standard library only): verifies
  exactly one wheel and one sdist matching `<v>`, wheel under 5 MB, allowlisted
  wheel prefixes and sdist top-level entries, `METADATA` and `PKG-INFO` fields,
  absence of `__pycache__`, `.pyc`, `tests/`, `scripts/`, `frontend/`, `docs/`,
  `.env`, `.sqlite3`, `.toml`, absence of synthetic storm markers (`AL802026`,
  `Hurricane Demo`), and clean `check_personal_data.py` CI scan of every
  extracted member (generic R2 skips Vite's minified third-party
  `web/static/assets/*.js` and `*.css` bundles, which contain Leaflet's Web
  Mercator pole-latitude constant and `lucide-react` SVG icon paths, while
  `frontend/src/` is R2-scanned by `check_personal_data.py --all`; pass
  `--with-denylist` locally to scan every extracted member, minified assets
  included, against the operator's denylist).
- `scripts/release_smoke.py` (standard library only): installs in temporary
  directories without Node on `PATH` and without `ANTHROPIC_*` or `WEATHERBOT_*`,
  then checks `weatherbot --version`, `weatherbot doctor --offline --json`,
  `scripts/smoke_installed_web.py`, and (on Windows) importing pywinrt 4 and
  loading `toast_xml(...)` into `XmlDocument` without showing a toast.

## Trusted publishers (OIDC)

No PyPI or TestPyPI API token is created or stored. Both registries trust
`release.yml` through OIDC:

- **PyPI** (`weatherbot` -> Manage -> Publishing -> GitHub publisher):
  owner `nathanramoscfa`, repository `weatherbot`, workflow `release.yml`,
  environment `pypi`.
- **TestPyPI** (Publishing -> pending/project GitHub publisher):
  project `weatherbot`, owner `nathanramoscfa`, repository `weatherbot`,
  workflow `release.yml`, environment `testpypi`.

## Yank and patch

PyPI and TestPyPI **never allow a filename to be uploaded twice**, even after a
file is deleted. A broken published release is never replaced in place:

1. **Yank the bad release** (PEP 592) in the project's release management page
   on TestPyPI or PyPI (**Manage -> Releases -> <version> -> Options -> Yank**)
   with a clear reason (for example, `"Superseded by 2.0.0rc2; regression in ..."`).
   Yanking stops unpinned installs from picking the broken version while keeping
   explicit `weatherbot==<version>` pins reproducible.
2. **Fix on a branch from `main`**, bump to the next version (`2.0.0rc2` or
   `2.0.1`) with `scripts/set_version.py`, update `CHANGELOG.md`, merge, and tag
   the new version through the same pipeline.
3. **Never delete or force-move a pushed tag** — the tag ruleset refuses it.

## Operator local service upgrade and rollback

Run away from `:25` past the hour (when `\Weatherbot\check` may restart
`\Weatherbot\serve`). Always obtain the operator's yes before touching the
local service.

### Upgrade (or install candidate wheel)

```powershell
# 1. Stop the running service
schtasks /End /TN \Weatherbot\serve

# 2a. Install from PyPI (for a public release)
uv tool install --reinstall weatherbot==2.0.0

# 2b. Or install a hash-checked candidate wheel downloaded from the GitHub Release
#     (verify SHA-256 against the release workflow's build output first)
# uv tool install --reinstall C:\path\to\weatherbot-2.0.0rc1-py3-none-any.whl

# 3. Restart the service
schtasks /Run /TN \Weatherbot\serve

# 4. Read back health and doctor
curl.exe -sS http://127.0.0.1:8765/api/health
& "$env:USERPROFILE\.local\bin\weatherbot.exe" doctor --offline --json
```

### Rollback

```powershell
schtasks /End /TN \Weatherbot\serve
uv tool install --reinstall weatherbot==<previous-version>
# Or reinstall from a local wheel / checkout if rolling back to a pre-PyPI build
schtasks /Run /TN \Weatherbot\serve
curl.exe -sS http://127.0.0.1:8765/api/health
& "$env:USERPROFILE\.local\bin\weatherbot.exe" doctor --offline --json
```

Phase 9 adds no Alembic migration (`0010` throughout), so rolling back inside
the 2.0.x line requires no database restore. If a future release migrates the
database, restore the pre-migration copy from `%LOCALAPPDATA%\weatherbot\backups\`.

## Weekly install canary

`.github/workflows/install-canary.yml` runs every Tuesday at `09:41 UTC`
(`cron: "41 9 * * 2"`) and on manual dispatch. On clean `ubuntu-latest` and
`windows-latest` runners it runs:

```sh
uv run --no-project python scripts/release_smoke.py --latest --min-version 2.0.0
```

- While PyPI's latest release is below `2.0.0`, the script exits 0 without
  installing.
- Once `2.0.0` is live, the canary runs an unpinned `uv tool install weatherbot`
  every week; any broken upstream dependency triggers GitHub's scheduled-run
  failure email.
- Prove the alarm with `gh workflow run install-canary.yml --ref main -f simulate_failure=true`.
  Simulated runs carry the distinct `run-name` `install-canary (simulated failure)`.
- **60-day GitHub inactivity rule:** GitHub automatically disables scheduled
  workflows on public repositories after 60 days with no repository activity,
  which silences the canary. Check and re-enable with:
  ```sh
  gh workflow view install-canary.yml
  gh workflow enable install-canary.yml
  ```

## Failure modes and recovery

| Failure mode | Cause | Recovery |
| --- | --- | --- |
| `tag vX does not match pyproject.toml version vY` | Tag was pushed before merging the version PR or with a typo | Do not move the tag; fix the version on `main` (or cut the next version) and push a matching tag |
| `tagged commit is not on origin/main` | Tag points to a feature branch commit | Merge to `main` first and tag the `main` merge commit with a fresh version |
| Refused OIDC exchange in `publish-*` | Trusted publisher owner/repo/workflow/environment mismatch, or environment policy rejected the ref | Fix the publisher or environment configuration at its cause, then re-run failed jobs on the **same tag** (nothing was uploaded) |
| Slow index propagation in `smoke-published` | TestPyPI or PyPI CDN took longer than the 10-minute poll window | Confirm the wheel appears at `/pypi/weatherbot/<v>/json`, then re-run the failed `smoke-published` job |
| `smoke-published` fails after upload | Published wheel or unpinned dependency is broken on a target OS/Python | Yank the published release immediately with a reason, fix the cause on `main`, and cut the next version (`rc2` or patch); never re-upload the same version |
| GitHub Release creation fails | `CHANGELOG.md` heading mismatch or transient API error | Re-run the `github-release` job once fixed (or verify tag assets match the workflow's `dist` and `corpus` artifacts) |
