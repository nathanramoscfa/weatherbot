# Phase 1 QA findings

Phase 1 foundation and discovery, verified 2026-10-15. This is the disposition
ledger for [the phase roadmap](roadmap/phase01-roadmap.md), including the
findings and judgement calls in PRs #3, #4, #7, #13, #14, and #15. Official
products decide; the application scaffold makes no assessment yet.

Each row names its class, destination and guard. A named later phase owns a
documented limitation; it is not an unfinished Phase 1 implementation.

## Step 1 — Freeze v1 and protected main

Source: [PR #3](https://github.com/nathanramoscfa/weatherbot/pull/3).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Proposed release commit `45623a1` has CLI whitespace absent from the PyPI sdist; `5de67aa1ad7883243af65d4f4f713d78ce02f791` matches all 29 package files and five other release files exactly. `setup.cfg` differs only in serialization after generated metadata is excluded. | Spec rot / operator decision | Step 1 task and PR #3 record approval on 2026-10-12; annotated `v1.0.0` uses the proven commit. | Static checks 1–2 and V1.3 pin the accepted commit; verified sdist SHA-256 is recorded in PR #3. |
| v1 tests clear cache through relative paths and must not be run from this checkout. | Implementation bug | v1 retired; Step 2 provides temporary-directory guards. | `tests/conftest.py`, `tests/test_guards.py`; see the cache-loss row below. |
| Default-branch rename requires other clones to update tracking; direct pushes must remain blocked. | Process / repository configuration | PR #3 contains clone migration commands and readback evidence. | V1.2 checks squash-only merges, automatic deletion, enforced admins, linear history, PR reviews and conversation resolution. |
| A transient GitHub push failed and succeeded on retry. | External service incident | PR #4 records the recurrence and successful retry; no code change required. | Gate readbacks, not a successful local push, determine completion. |

## Step 2 — uv scaffold

Source: [PR #4](https://github.com/nathanramoscfa/weatherbot/pull/4).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| **38 recorded v1 cache responses were lost on 2026-10-11** when tests cleared a relative cache directory from the repository root. This was a v1 implementation bug surfaced by a process step. | Implementation bug | v2 test isolation implemented in Step 2; recovering originals requires an operator backup. Step 5 harvests restored entries. | Every v2 test changes cwd to `tmp_path` in `tests/conftest.py`; `tests/test_guards.py` proves relative writes cannot reach the repository. Never run `git clean` during Phase 1. |
| Engine imports can violate purity even when the imported library is not a project layer. | Architecture guard | `tests/test_architecture.py` and import-linter contracts; PR #4 records both reverted negative probes. | AST ban on 13 I/O roots and downward-only imports; static checks 13–14 and Python sweep. |
| `uv pip install --python <venv>/Scripts/python` fails on Windows without `.exe`. | Implementation bug, fixed in-step | CI package job and verifier use the environment directory. | Fresh-wheel smoke on Ubuntu and Windows; V2.3. |
| GitHub forces ANSI color in Typer help, breaking substring assertions. | Implementation bug, fixed in-step | `tests/test_cli.py` strips escape sequences. | Tested with and without `FORCE_COLOR=1 GITHUB_ACTIONS=true`; CI on both systems. |
| pytest-socket raises a warning while constructing its exception under warnings-as-errors. | Tool behavior | Guard test expects both warning and exception. | `tests/test_guards.py`. |
| Ruff 0.17's ALL includes CPY001 and its formatter reads Markdown fences. | Tool behavior / judgement call | Reasoned CPY001 ignore; planning export excluded in `pyproject.toml`. Test D103 and INP001 ignores explain collection conventions. | Static checks 15–16; strict lint/types remain required. |
| Root runtime ignore patterns could accidentally ignore similarly named fixture directories. | Implementation guard | Anchored `/cache/`, `/reports/`, `/logs/`, `/state/`; Python version pin no longer ignored. | Static checks 8 and 18. |
| A hard-coded CI job count would break whenever a new job joins the gate. | Process improvement | Step 3 removed EXPECTED_JOBS; every `needs` result must succeed. | `ci.yml` gate and static check 24. |
| v1 removal needed explicit operator approval; untracked reports and cache remained intact. | Operator decision | PR #4; v1 stays under `v1.0.0`. | Static check 10 reads the actual deletion set; no runtime-data deletion. |
| roadmodel moved into `.venv`, with pip in the planning group and no environment override. A dry run reported roadmap rules due for refresh. | Process / bookkeeping | Registry migration completed in Step 2; current roadmap skill governs execution. | V2.4 runs the local updater dry run and verifies this project's bare registry entry. UV_LOCKED prevents CI re-resolution. |
| Old SAFETY_API_KEY and workflow belonged to v1. | Retired configuration | Step 2 removed use; Step 7 readback confirms no repository secret with that name. | No workflow uses secrets; tracked env-file checks and security gate. |
| Seven text files were committed as CRLF, creating noisy future diffs. | Implementation bug | Issue #6 fixed in [PR #16](https://github.com/nathanramoscfa/weatherbot/pull/16), separately from Step 7. | Step 7 adds `mixed-line-ending --fix=lf`, excluding fixtures; `.gitattributes` retains `tests/fixtures/** -text`. |

## Step 3 — Security gate

Source: [PR #7](https://github.com/nathanramoscfa/weatherbot/pull/7).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| A skipped local hook could admit a token or personal coordinate. | Security control | PR #7's deliberate proof PR #5, now closed and its branch deleted. | [Failure run 38303548334](https://github.com/nathanramoscfa/weatherbot/actions/runs/38303548334): security and gate red; logs contain no planted values. The single `--no-verify` use is justified in PR #7 and never reached main. |
| Three-decimal rounding ties differ for the Nassau landmark. | Judgement call | Checker uses half a third-decimal unit tolerance; PR #7 records rationale. | Positive and negative synthetic coordinate tests. |
| Byte-only scanning misses compressed fixtures; corrupt/oversized gzip could evade inspection. | Security control | R1 also scans bounded decompressed bytes, failing closed on unreadable gzip. | Regression suite and local denylist self-test; no value printed. |
| Personal values can appear in filenames or in unexpected coordinate forms. | Security control | Filename redaction; R2 handles lng/camelCase and punctuation; R3 handles latitude/longitude and malformed coordinate URLs; R4 includes `.env.*`. | Synthetic regressions, redaction assertions and fail-closed tests. |
| A denylist inside the checkout, empty denylist, or overly short entries defeats isolation or usefulness. | Security control | Checker refuses these configurations; denylist stays outside Git. | Local self-test proves R1–R4. CI explicitly skips only R1 because it has no private denylist. |
| Scanner exceptions could leak input in a traceback. | Security control | Print sanitized setup messages or exception type only. | Redaction tests; verifier also reports exception type only. |
| `pre-commit autoupdate --freeze` chooses gitleaks v8.30.0 because v8.30.1 is off the default branch. | Tool behavior | Pin v8.30.1 manually with explanation in hook configuration. | CI and phase verification download the same checksum-verified binary; full SHA pins. |
| Full-history scans find two sequential-digit placeholder keys in deleted v1 docs; directory scans include untracked environments and runtime data. | Scanner configuration | Two reviewed fingerprints in `.gitleaksignore`; use `gitleaks git --redact`, never `gitleaks dir .`. | `--security` scans history; static credential backstop scans tracked bytes. |
| Auditing the editable development project or installing packages just to audit gives the wrong result. | Tool behavior | `audit_deps.py` exports every locked group with hashes and runs pip-audit `--strict --disable-pip`. | Vulnerable-pin negative probe in PR #7; audit runs in both required workflows. |
| Subprocess and deterministic synthetic-data findings need narrow justification. | SAST review | Inline nosec markers in the scripts; no shell and no security use of the seeded generator. | Bandit over src/scripts and Ruff S rules. |
| Dependabot supports pre-commit, in addition to uv and GitHub Actions; npm has no manifest yet. | Supply-chain configuration | Three ecosystems enabled; Phase 5 adds npm with frontend. | SHA-pinned hooks/actions; API readbacks for alerts, security updates and private reporting in V3.4. |
| Recorder could send a new coordinate URL form. | Downstream guard | Step 5 task requires extending `request_coordinates` before using a new form. | R3 tests every recorded request; requests use cited landmarks only. |

## Step 4 — Data-source register

Source: [PR #13](https://github.com/nathanramoscfa/weatherbot/pull/13).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| County-zone alerts can cover only other forecast zones in that county. | Architectural question | [Issue #10](https://github.com/nathanramoscfa/weatherbot/issues/10), Phases 2/3. | Preserve affectedZones/geocode and explicit point/zone distinction; Phase 3 must decide semantics with tests. |
| Arrival labels lack dates and time zones in the map layer; KMZ has timezone and pubAdvTime. | Architectural question | [Issue #11](https://github.com/nathanramoscfa/weatherbot/issues/11), Phases 2/3. | Do not infer a date/zone from a label; use archived metadata. |
| WSP products have no storm id; one product exists per synoptic time. | Architectural question | [Issue #12](https://github.com/nathanramoscfa/weatherbot/issues/12), Phases 2/3. | Step 6 associates WSP through authoritative SYNOPTIME; client persistence must preserve snapshot ownership. |
| NWS API gives identical advisory text with structured issuance time, without scraping HTML. | Spec rot / decision | Project roadmap Changes from the brief; register and recorder. | Contract tests compare source ids and query parameters; TCP requests filter by location and match storm id. |
| ArcGIS numeric ids move; StormSurgeRisk repeats layer names under region groups. | Source behavior | Register uses exact names and group paths; Step 5 task expands `{slot}` and `{n}`. | Name resolution and recorded-catalog contracts; no `|` inside table cells. |
| Server precision otherwise returns up to 15 decimals and inflates fixtures. | Judgement call | Shared `geometryPrecision=5` query in register/recorder. | Query-parameter contract and fixture budget tests. |
| Overlay fixtures need capabilities only; surge-risk needs its catalog; peak-surge captures empty shapes; OSM tiles are display-only. | Scope decision | Register Fixture cells and recorder. | Required-source coverage test; no bulk tile recording. |
| Empty Development Motion and Peak Storm Surge layers do not prove future feature fields. | Source limitation | Register records only observed schema; active-phase owner re-records when features appear. | Schema contracts change only with new evidence and verification date. |
| Atlantic and Central Pacific had no active storm on 2026-10-12; Eastern Pacific Simon answered the per-basin question. | Open source question | Register's dated per-basin table; active-phase owner rechecks with an active storm. | Preserve the open date; never present empty-basin evidence as verified active-storm behavior. |
| Arrival archive begins in 2018; toa listing ignores filters; Ian fcst stops at 035; WSP windows are synoptic. | Source limitation | Step 6 task, corpus manifest and register. | Coverage tests account for every missing product and intermediate advisory. |
| JSON-LD keys contain @; a file-wide no-email assertion would fail valid documentation. | Spec rot | Step 7 task and check 33 read the User-Agent block only. | Verifier regression for actual User-Agent scope. |
| Field order differs by slot; AT1 advisory field lacks idp_source; breakpoint geometry can be null; RSS placeholder pubDate can be future; PNG dimensions change; tropical-weather now includes a probability group. | Source facts | `docs/DATA_SOURCES.md`; Phase 2 consumes these facts. | Recorded-catalog/PNG contracts; no fixed field order, dimension, or placeholder-time assumption. |
| NWS documentation anticipates a future API-key requirement. | External policy risk | Register Not used / keyless rule; Phase 2 owns a decision if it changes. | No credentialed request introduced; source drift must update register and tests. |

## Step 5 — Fixture recorder and harvest

Source: [PR #14](https://github.com/nathanramoscfa/weatherbot/pull/14).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Capture-folder date is local; manifest timestamps are UTC. Harvest folders use report local date and EDT conversion. | Data convention | Recorder and register; PR #14. | Local-versus-UTC harvest regression; timezone boundary rejected when unknown. |
| Footprint layers need counts, surge-risk only catalog; slot layers and TCP products exist only for active slots. | Source convention | SOURCES and MapService definitions. | Register/recorder/catalog agreement and synthetic active-slot tests; off-season shape is a documented Phase 2 follow-up. |
| `file` is the stored name including .gz; hashes/sizes describe received bytes; content-length is wire size; PNG dimensions live in notes. | Manifest convention | Recorder schema and register Recorded fixtures. | Full checksum, gzip mtime, PNG-header and schema contracts. |
| Harvest had no requests: status 200 means v1 saved a success, headers empty, User-Agent names recorder convention. | Provenance decision | PR #14 and origin/harvested_from fields. | Harvest provenance and file-accounting contracts. |
| The only remaining v1 cache entry is v1's own test data; none of the 38 lost responses was restored. | Data loss limitation | Operator backup recovery; harvest implementation retained and tested. | Synthetic tests cover all v1 cache-key forms; cache harvest refuses to replace live captures. |
| Non-200 captures are permitted only for documented problem+json errors, and every source needs a successful response. | Error policy | Recorder handles Nassau's 404 points and 400 point-alert responses explicitly. | Documented-error and unlabelled-error tests. |
| Requests need pacing/retries, payload caps and atomic per-source replacement; one failed source must not discard successes. | Reliability control | Recorder implementation; PR #14 records intervals and independent failure semantics. | Fake-clock/respx tests for retries, renamed ids, truncation, size caps and failure preservation. |
| Recorder uses only existing `/points/`, point, lat and lon URL forms. | Security review | R3 unchanged after review. | Every manifest URL is checked in CI and locally; no cookie headers stored. |

## Step 6 — Replay corpus

Source: [PR #15](https://github.com/nathanramoscfa/weatherbot/pull/15).

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Every archive uses native geographic D_Sphere, radius 6,371,200 m; the original task required stopping. | Operator-approved spec change | Approval 2026-10-15 recorded in Step 6 task, register, corpus NOTICE and Phase 3 roadmap guidance. | WKT/source_crs preserved exactly; no WGS84 relabeling. Unsupported/projected CRS stops. Phase 3 must honor datum before geodesy. |
| 39 singleton warning lines occur in Dorian 056–062A across 13 advisories. | Official source defect | Point representation with unchanged attributes, source_geometry and geometry_note; documented in task/register/NOTICE. | Synthetic singleton regression and complete subset validation; no segment invented. |
| Some source rings have only interior winding; pyshp treats them as exterior rings. | Official source anomaly | PR #15 and register/NOTICE. | Every converted cone is valid; original archives remain pinned and untouched. |
| Four official cone values collided with prefixes of private decimal denylist entries. | Security false positive, fixed in-step | R1 matches whole numeric coordinate values including trailing zeros; strings/pairs retain substring matching. | Synthetic gzip regression proves exact private values still fail; no denylist value printed/changed, no fixture changed to evade the gate, no hook bypass. |
| Initial recording downloaded originals before conversion exposed singleton lines. | Recording recovery decision | Explicit `manifest --reuse-downloads` resumed from retained bytes plus fresh listings. | Flag forbidden for fetch/verify/convert; normal manifest recording fetches fresh bytes. |
| All 310 advisories fit: 1,201 compressed geometry files, 5,435,928 bytes; replay tree about 6.68 MiB. Originals: 1,199 archives, 117,177,968 bytes. | Measured result | Register and immutable corpus manifest. | No regional omissions; budget and byte-for-byte reconversion tests. |
| GitHub caches are branch-scoped and expire; a PR cache does not seed main. | Operations lesson | Step 6 verified a cold main fetch/cache save and recovery restoration. | Twice-weekly workflow, checksum verification on every restore, fetch on a miss. Alarm runs below. |
| PowerShell pipes can corrupt non-ASCII literals; concurrent environment shells can refer to retired venv. | Process lesson | Shared memory; use UTF-8 file writes/apply_patch and project uv environment. | No literal coordinate or credential printed; strict lint/type/gate before commit. |

### Alarm exercise

- [Initial main replay run 38799006199](https://github.com/nathanramoscfa/weatherbot/actions/runs/38799006199): green, cold fetch of all originals and cache saved.
- [Deliberate failure 38799080064](https://github.com/nathanramoscfa/weatherbot/actions/runs/38799080064): verification and both corpus tests passed, then **Prove the failure alarm** exited 1. This exercised the GitHub failure signal used for failure-email alerts.
- [Recovery dispatch 38800604462](https://github.com/nathanramoscfa/weatherbot/actions/runs/38800604462): green, restored main cache, checksum verification and byte-for-byte reconversion passed.
- V6.4 reads the latest main workflow status and the recorded failed dispatch's job steps. The signal owner is the operator; on archive drift, inspect the failed checksum, retain the pinned baseline, investigate the official source, and deliberately re-record only through a reviewed source-drift PR.

## Step 7 — Verification and closure

| Finding | Class | Destination | Guard |
| --- | --- | --- | --- |
| Shallow test checkouts lack v1 tag/history needed by the verifier test. | CI integration gap | Test job uses `fetch-depth: 0`, as does phase verification. | Ubuntu/Windows verifier subprocess test with 30-second timeout. |
| Verifier checks must continue after errors and never echo scanned values. | Verification integrity | `verify_phase01.py` reports exception types only. | Synthetic failing-check regression proves later checks run and private sample stays out of output. |
| A skipped tool is not affirmative evidence for phase closure. | Verification integrity | Aggregate V rows preserve SKIP; CI fails if gitleaks is missing. | Aggregate regression; local completion requires all 75 checks PASS. |
| The register has one table per basin, rather than a table headed Basin; Dependabot uses unquoted ecosystem scalars. | Spec rot / checker assumptions | Step 7's task and checker use the actual table header and all three basin sections; ecosystem checks read the existing scalar format. | Static checks 27/35. |
| Repeated Git index subprocesses made the first Windows fast sweep take about 60 seconds. | Performance bug, fixed in-step | Index snapshot cached once per invocation. | Fast-mode subprocess integration test has a 30-second timeout; corrected local sweep measured 8 seconds. |
| Existing CI/package evidence and GitHub configuration must be read back rather than inferred from local files. | Verification integrity | Post V matrix, protection API readback and deployed main workflow check. | Required aggregate phase-verify beside gate, no bypass actors, all PR checks green before squash merge. |
| Phase 1's exact scaffold/runtime assertions will become historical when later phases add modules or dependencies. | Downstream integration requirement | Phase 2 Step 1 (`feature/phase02-step1-domain-models`): checks 7, 9, and 12 read `v2.0.0-phase-1`. | Phase 2 must adapt historical assertions against `v2.0.0-phase-1`, while retaining live security and provenance checks and the Phase 1 matrix entry. |

## Pre-ship items

These are documented limitations and downstream owners, with no unassigned finding:

| Item | Owner / destination | Required next action |
| --- | --- | --- |
| Real source clients, models and persistence do not exist yet. | Phase 2 | Reuse the register's exact query parameters, User-Agent, source ids and recorded fixtures; add live-smoke CI with the clients. |
| County-zone semantics, arrival date/zone and snapshot ownership are open design decisions. | Phases 2/3, issues #10, #11, #12 | Resolve before presenting assessments; preserve original provenance. |
| Off-season slot behavior has synthetic coverage but no live off-season capture. | Phase 2 / source drift | Re-record all required sources together when that shape occurs. |
| Atlantic/Central Pacific active-storm layers and populated peak-surge schema remain open. | Phase active when a storm appears; register's dated basin table | Re-run the recorder and revise register/contracts with live evidence. |
| Threat engine and alert thresholds are unimplemented. | Phase 3 | Read ladder wording from `v1.0.0`; load WSP/arrival products from the full corpus cache; honor native D_Sphere, singleton Points and product gaps. |
| No runtime scheduling or unattended local surface yet. | Phase 4 | Add heartbeat, staleness and runtime alarms; Phase 1's only scheduled implementation surface is replay-corpus.yml. |
| No frontend/npm manifest yet. | Phase 5 | Add npm Dependabot and frontend security gates when frontend exists; obey OSM attribution/cache policy. |
| No AI client or API-key use in the application yet. | Phase 6 | Narration only; never use model output as an official fact. |
| Inundation/peak surge are outside this corpus; overlay tiles are display-only. | Phase 7 | Use registered display services and terms, without fabricating historical products. |
| Phase milestone is not a PyPI release; package stays 2.0.0.dev0. | Phase 8 | Implement release readiness and trusted publishing separately. |
| Lost v1 responses, old external environment and ignored runtime directories. | Operator housekeeping / backup recovery | Preserve ignored files; run harvest if a backup appears. |
| Dependency updates #8/#9 are independent maintenance. | Dependabot PRs #8/#9 | Review and validate separately; do not fold them into Phase 1 closure. |

Run `uv run python scripts/verify_phase01.py --post` for the canonical
50 static + 25 V-check sweep. `--fast` is offline and standard-library only;
`--py`, `--corpus`, `--security` and `--all` provide the same suites independently.
