<!-- docs/phase06-qa-findings.md -->
# Phase 6 QA Findings Ledger — Claude Layer

This ledger records every judgement call, verification receipt, cost measurement, idle CPU measurement, live AI eval result, source-drift and model-drift observation, live smoke run, and carry-over disposition across Phase 6 (`v2.0.0-phase-6`). Every finding has a concrete disposition (fixed in-phase, assigned to a specific later phase and section, or tracked as a GitHub issue); none is left open without a destination.

## PR #75 & PR #76 — Phase 6 Roadmap

- **Summary:** Refreshed the `roadmodel` planning kit to `0.2.108` in PR #75 (`ee9663e`, `2026-10-30`), then authored `docs/roadmap/phase06-roadmap.md` in PR #76 (`c872d2a`, `2026-10-30`) breaking Phase 6 (Claude layer) into seven executable steps (`Step 1` through `Step 7`) with 51 static checks and the 28-row V1–V7 post-implementation verification matrix (`79` total checks in `--post`), and amended `docs/roadmap/ROADMAP.md` (§2/§3 Anthropic outbound boundary, §5 cost and health/alarm rows, and Phase 6).
- **Key design decisions recorded:**
  - `weatherbot.services.ai` is the sole importer of `anthropic>=2.3.0` and `httpx2` (enforced by two `import-linter` contracts and AST checks in `tests/test_architecture.py`), and only `client.py` and `caller.py` import the SDK at module level so non-AI commands never load it.
  - Database confinement via `ai_engine(path)` (`src/weatherbot/services/ai/guard.py`), which installs a SQLite `set_authorizer` callback allowing row writes only to `ai_calls` and `ai_outputs` and denying every schema change.
  - Shared cross-process daily cap (`$1.00` / `1,000,000` micro-dollars default) enforced in `Ledger.reserve` under `BEGIN IMMEDIATE` at each request's worst-case ceiling before the request leaves the machine, and settled from the SDK's reported token usage (`Ledger.settle`).
  - Privacy-reduced context (`src/weatherbot/services/ai/context.py`) sending distance bands, 8-point compass directions, hour-rounded instants, and source keys — never coordinates, raw distances, bearings, or zone IDs — paired with deterministic output validators (`src/weatherbot/services/ai/validate.py`) that withhold any model output contradicting the engine's current level, citing an unknown source key, or carrying a URL or unquoted position.
  - Three documented refinements to the brief: per-storm explanation folded into the briefing's `situation` section and the chat's `get_storm` tool; budget expressed in dollars (`daily_cap_usd = 1.00`) over integer micro-dollars rather than raw token counts; and briefings placed on the dashboard card while grounded chat lives on `/ask`.
- **Disposition:** Merged in PR #75 (`ee9663e`) and PR #76 (`c872d2a`, `2026-10-30`).

## Step 1 — The Claude client, the ledger, and the cap (PR #77)

- **Summary:** Added `anthropic>=2.3.0` to runtime dependencies and `httpx2>=2.16.0` to `dev`; added the two `import-linter` contracts; implemented `AiSettings` (`[ai]`) and six `WEATHERBOT_AI_*` environment overrides; added `src/weatherbot/services/ai/{client,errors,pricing,guard,ledger,caller,service}.py`, Alembic revision `0007_ai_calls.py`, `Runtime.make_claude`, `Context.ai_service`, `WebState.ai`, `doctor`'s `ai` check, `/api/health`'s `ai` block, `SecretFilter` and `SILENT_LIBRARIES` in `logs.py`, `scripts/record_ai_fixtures.py`, `tests/ai/ai_support.py`, `docs/AI.md`, and converted Phase 5's Check 47 to read `v2.0.0-phase-5:README.md`.
- **Findings & judgement calls:**
  - **SDK structured-output validation (`output_config.format` vs. `messages.parse`/`stream(output_format=...)`):** Probing `anthropic` `2.3.0` showed that `messages.parse` and `messages.stream(output_format=...)` validate inside the SDK and raise Pydantic `ValidationError` on a `refusal` or `max_tokens` stop before the caller can read `stop_reason` and `usage` to settle the ledger. `AiCaller` therefore passes `output_config={"format": transform_schema(output_format)}` to `messages.create` / `messages.stream`, checks `stop_reason` and settles `usage` first, and then validates with `output_format.model_validate_json`, raising `InvalidOutputError` (`failed`/`invalid_output`) on malformed JSON. Recorded in `docs/roadmap/phase06-roadmap.md` (Decision 4 and Step 2). Fixed in PR #77.
  - **No-profile-directory SDK initialization (`has_credential`):** When `~/.config/anthropic` / `%APPDATA%\Anthropic` does not exist on disk and `ANTHROPIC_API_KEY` is unset, `anthropic.AsyncAnthropic()` constructs with `api_key=None`, `auth_token=None`, and `credentials=None` instead of raising `CredentialsError`, failing only on the first request with `TypeError`. Added `has_credential(client)` in `src/weatherbot/services/ai/client.py` to gate `credential_source` and `AiService.caller()`. Fixed in PR #77.
  - **`SILENT_LIBRARIES` in `src/weatherbot/services/logs.py`:** Because the Anthropic SDK and `httpx2`/`httpcore2` log full request options (including prompts and questions) at `DEBUG`, `logs.py` places `("anthropic", "httpx2", "httpcore2")` in `SILENT_LIBRARIES` (held at `WARNING` even when `--verbose` / `DEBUG` is active), distinct from `QUIET_LIBRARIES` (which drop to `DEBUG` under `--verbose`). Fixed in PR #77.
- **Disposition:** Merged in PR #77 (`03d7013`, `2026-11-01`).

## Step 2 — The briefing, the change summary, and the eval set (PR #80)

- **Summary:** Added `src/weatherbot/services/ai/{prompts,context,schemas,validate,outputs,briefing,summaries}.py`, Alembic revision `0008_ai_outputs.py`, `weatherbot brief [LOCATION] [--new] [--json] [--cost]` and `docs/schema/brief.schema.json`, the 31-case offline and live eval suite (`tests/ai/eval/{cases,grading}.py`, `scripts/eval_ai.py`), and the 90% branch-coverage gates on `context.py` and `validate.py` in `.github/workflows/ci.yml`.
- **Findings & judgement calls:**
  - **Previous-level numbers in briefing prose:** On the first recording run of the 31 eval cases, 10 transition cases failed `levels_stated` because the system prompt instructed Claude to explain what changed from `previous_level`, causing Claude to write `"rose from Level 2 to Level 3"`. Tightened `prompts.py` so transition explanations name only the current official level by number and describe prior state in words (`"rose to Level 3 from the previous advisory"`), after which all 31 recorded cases passed (`31/31`). Fixed in PR #80.
  - **Test-environment isolation guard in `tests/cli/cli_support.py`:** A CLI test passing a bare `environ` dictionary without `WEATHERBOT_DATA_DIR` opened and migrated the operator's live database from `0007` to `0008` during development. With the operator's approval, backed up and downgraded the operator's database back to `0007`, and added an explicit assertion in `cli_support.runtime()` requiring `WEATHERBOT_DATA_DIR` and `WEATHERBOT_CONFIG_DIR` in any custom `environ` mapping. Fixed in PR #80.
  - **Windows CI test timeout headroom:** Raised the `test` job `timeout-minutes` in `.github/workflows/ci.yml` from `25` to `40` and cached the recorded snapshot across AI tests; tracked the broader Windows test-duration trend in GitHub issue #82 (`https://github.com/nathanramoscfa/weatherbot/issues/82`). Fixed in PR #80.
- **Disposition:** Merged in PR #80 (`923b373`, `2026-11-01`).

## Step 3 — Grounded chat and the outlook narration (PR #81)

- **Summary:** Added `src/weatherbot/services/ai/{tools,chat,narration}.py`, chat and narration prompts (`ba86abc1c568`, `db39a26fa9fc`), narration and sentence validators in `validate.py`, `AssessmentRepository.latest_heads()`, `weatherbot ask QUESTION [--location NAME] [--json]` with `docs/schema/ask.schema.json` (17 CLI schemas), `weatherbot brief --outlook {atl,pac,cpac} [--horizon {2d0,7d0}]`, and recorded 5 multi-turn/tool chat cases and 2 outlook narration cases (`tests/ai/eval/chat_cases.py`).
- **Findings & judgement calls:**
  - **Tool description storm-ID hygiene:** Removed an example storm ID (`AL052019`) from `get_storm`'s tool description in `tools.py` so `src/weatherbot/services/ai/` carries zero season-specific storm identifiers, and re-recorded the 5 chat fixtures so their request SHA-256 hashes match byte for byte. Fixed in PR #81.
  - **Percentage regex after ellipsis in `validate.py`:** Fixed `percentages()` in `src/weatherbot/services/ai/validate.py` so a number following `...` (e.g., `...40%`) is still extracted and checked against the TWO's official formation chances. Fixed in PR #81.
- **Disposition:** Merged in PR #81 (`d5a1601`, `2026-11-01`).

## Step 4 — The AI in the API (PR #83)

- **Summary:** Added `src/weatherbot/web/routes/ai.py` (five sync reads `GET /api/ai`, `/api/ai/calls`, `/api/ai/briefings`, `/api/ai/summaries`, `/api/ai/narrations`; three guarded SSE streams `POST /api/ai/briefings`, `/api/ai/chat`, `/api/ai/narrations` capped at `MAX_AI_STREAMS = 4`; and two controls `PUT /api/ai/pause`, `POST /api/ai/allowance`), `src/weatherbot/web/routes/outlook.py` (`GET /api/outlook` and `GET /api/outlook/{basin}/{horizon}` via `raw_cache.stored_png`), `src/weatherbot/services/ai/display.py` (`public_page`), `EventKind` `"ai"` and `QueryKey` `"ai"`/`"briefings"` in `events.py`, `CycleWatcher` high-water marks on `AiCallRow` and `AiOutputRow`, `ChangeSummarizer` in `cli/serve.py`, six new API fixtures in `frontend/src/test/fixtures/`, and converted Phase 5's Check 19 to read `v2.0.0-phase-5:src/weatherbot/services/events.py`.
- **Findings & judgement calls:**
  - **Pre-stream JSON refusals (`STREAM_REFUSALS`):** FastAPI's `EventSourceResponse` files `responses={...}` models under `text/event-stream` by default; `STREAM_REFUSALS` in `web/routes/ai.py` explicitly declares `content: {"application/json": {"schema": {"$ref": "#/components/schemas/AiRefusalResponse"}}}` for `429` and `503` so pre-stream refusals are documented and typed as JSON. Fixed in PR #83.
  - **Stream disconnect settlement:** Closing a client SSE connection triggers the async generator's `finally:` block in `web/routes/ai.py`, which closes the service iterator, settles the reserved ledger row (`incomplete` at its ceiling if interrupted mid-flight), and releases the `ai_streams` semaphore slot. Fixed and proved over real loopback sockets in PR #83.
- **Disposition:** Merged in PR #83 (`4d6416b`, `2026-11-01`).

## Step 5 — The AI in the page (PR #84)

- **Summary:** Added `frontend/src/ai/` (`readEventStream.ts`, `streamEvents.ts`, `reasons.ts`, `format.ts`, `streamLock.ts`, `queries.ts`, `useAiStatus.ts`, `useBriefing.ts`, `useChat.ts`, `useNarration.ts`, `AiLabel.tsx`, `AiStateBanner.tsx`, `AiText.tsx`, `BriefingPanel.tsx`, `ChangeSummary.tsx`, `NarrationPanel.tsx`, `AiSettingsSection.tsx`), `frontend/src/pages/Ask.tsx`, and `frontend/src/pages/OutlookGraphics.tsx`; wired AI surfaces into `Dashboard.tsx`, `Timeline.tsx`, `Storms.tsx`, `Settings.tsx`, `AppShell.tsx`, and `routes.tsx`; and expanded the Vitest suite from 34 to 76 tests with zero new frontend dependencies (`frontend/package.json` unchanged from `v2.0.0-phase-5`).
- **Findings & judgement calls:**
  - **`useEventStream` `EventKind` guard:** `frontend/src/events/useEventStream.ts` previously checked incoming SSE events against the 8 Phase 5 `EventKind` literals, silently dropping Step 4's `"ai"` events. Replaced the list with an exhaustive `Record<EventKind, true>` map and added a regression test in `useEventStream.test.tsx`. Fixed in PR #84.
  - **Plain-text rendering only (`AiText.tsx`):** Model text renders exclusively through React text nodes with zero Markdown or HTML parsing, and `AiSources` renders `<a target="_blank" rel="noopener noreferrer">` only for `https://` URLs supplied by `display.public_page`. Proved in `frontend/src/ai/AiText.test.tsx` (`V5.3`). Fixed in PR #84.
- **Disposition:** Merged in PR #84 (`ce675d1`, `2026-11-02`).

## Step 6 — The live eval, the browser smoke, and the operator's AI (PR #86)

- **Summary:** Extended `scripts/serve_demo.py` with `--ai-replay` (default on), `--ai-cap-usd`, and `--ai-fail-auth` (`DemoReplay`, `request_kind`, `chat_round`, `demo_claude`); configured three Playwright demo servers (`8799`, `8800` with `--ai-cap-usd 0.001`, `8801` with `--ai-fail-auth`) in `frontend/playwright.config.ts`; added `frontend/e2e/ai.spec.ts` and `recordAiText`/`leaksAiText` in `frontend/e2e/guard.ts`; extended `scripts/eval_ai.py` to grade all 38 cases (31 briefings/summaries + 5 chat turns + 2 narrations); guarded `scripts/measure_idle.py` to require `ai_state=ready` and `change_summaries=on`; and deployed the built Phase 6 package (`ui.index_sha256="507cca9a0d85"`, DB revision `0008`) to `\Weatherbot\serve` on the operator's Windows 11 machine.
- **Findings & judgement calls:**
  - **Sub-ceiling daily cap (`--ai-cap-usd 0.001`, Decision 15 amendment):** Because `$0.001` (`1,000` micro-dollars) is below `SMALLEST_REQUEST_PROMPT_TOKENS` (`3,000` input + `500` output = `$0.011` on Sonnet 5.5), `AiService.state()` reports `capped` immediately before any request is sent, and `POST /api/ai/briefings` answers `429` (`reason="capped"`) with an empty ledger. Amended Decision 15 in `docs/roadmap/phase06-roadmap.md` to match the shipped ceiling math. Fixed in PR #86.
  - **Narration area length bound (`validate.AREA_LIMIT` 400 -> 600):** On the first live eval run (`2026-11-02`), 37 of 38 cases passed and `narration-atl-7d0` was withheld for `length` because Claude Sonnet 5.5 wrote a 424-character area description (Anthropic's `transform_schema` moves `maxLength: 400` into the property description rather than enforcing it in the grammar). Ten additional live samples measured 240–337 characters; raised `AREA_LIMIT` in `src/weatherbot/services/ai/validate.py` from `400` to `600` (twice the prompt's 300-character target), after which the full 38-case live rerun passed `38/38`. Fixed in PR #86.
  - **Online `doctor` socket isolation on Ubuntu CI:** `test_doctor_json_fails_ai_online_when_anthropic_refuses_the_credential` initially let `doctor`'s online source probes hit the socket guard on Linux; wrapped the test in `recorded_services()` so source probes use `respx` while the AI probe hits the 401 replay transport. Fixed in PR #86 (`7642367`).
  - **Operator location setup 502 (`nws-points` `parse_point`, Issue #87):** During the Step 6 deployment check on `http://127.0.0.1:8765/settings`, adding the operator's own US location returned `502` (`nws-points` schema error in `parse_point`; the route logged no detail). Filed GitHub issue #87 (`https://github.com/nathanramoscfa/weatherbot/issues/87`) for a hotfix before or at the start of Phase 7, and verified the live deployment using the public Miami-Dade County Hall landmark (`briefing` row `1` settled `ok` at `25,438` micro-dollars).
- **Disposition:** Merged in PR #86 (`baa1dd2`, `2026-11-02`).

## Step 7 — QA & Verification Script

- **Summary:** Authored `scripts/verify_phase06.py` (51 static checks and 28 V1–V7 post-implementation verification matrix rows across `--fast`, `--py`, `--node`, `--ui`, `--live`, `--ai`, `--security`, `--all`, and `--post`, totaling 79 checks in `--post`), `tests/test_phase06_verification.py` (covering `--fast` < 30 s, the 28-row V1–V7 matrix, `phase-verify.yml` `"06"` membership, single-deliverable red-check isolation across Steps 1–7, fail-closed skipped JUnit evidence, and post probe failures without invoking `--ai`), appended `"06"` to `.github/workflows/phase-verify.yml` with its own conditional Node 24 setup steps (`if: "!cancelled() && matrix.phase == '06'"`) while leaving `"05"` untouched, updated `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `docs/roadmap/ROADMAP.md`, and `docs/roadmap/phase06-roadmap.md`, and recorded this ledger.
- **Disposition:** Merged in PR #88 (`2026-11-02`).

## Measured cost

Phase 6 estimated ~$1.40 for fixture recordings (Steps 1–3) and ~$0.40–$1.00 for the Step 6 live evaluation. Actual list-price spend across Steps 1–6 totaled **$1.595** (`1,595,031` micro-dollars), plus ~$0.38 (`382,366` micro-dollars) for the `--post` live eval sweep:

| Product / Run | Model | Cases / Requests | Prompt tokens / req (min / med / p95 / max) | Output tokens / req (min / med / p95 / max) | Cost / case (min / med / p95 / max) | Total cost |
| --- | --- | --- | --- | --- | --- | --- |
| **Recorded briefings** (Step 2, PR #80) | `claude-sonnet-5-5` | 22 cases, 22 req | `5,152 / 6,294 / 7,687 / 7,968` | `460 / 676 / 847 / 878` | `$0.0056 / $0.0080 / $0.0094 / $0.0258` | `$0.21` (commit set; `$0.55` across both takes) |
| **Recorded summaries** (Step 2, PR #80) | `claude-sonnet-5-5` | 9 cases, 9 req | `5,127 / 6,204 / 7,178 / 7,351` | `151 / 215 / 238 / 243` | `$0.0022 / $0.0029 / $0.0033 / $0.0177` | `$0.06` (included in Step 2 total) |
| **Recorded chat turns** (Step 3, PR #81) | `claude-sonnet-5-5` | 5 cases, 11 req | `4,230 / 4,948 / 6,964 / 7,011` | `97 / 138 / 271 / 293` | `$0.0036 / $0.0063 / $0.0218 / $0.0241` | `$0.05` (commit set; `$0.20` across both takes) |
| **Recorded narrations** (Step 3, PR #81) | `claude-sonnet-5-5` | 2 cases, 2 req | `2,999 / 3,240 / 3,240 / 3,240` | `204 / 391 / 391 / 391` | `$0.0086 / $0.0102 / $0.0102 / $0.0102` | `$0.06` |
| **Live eval (`eval_ai.py --live`)** (Step 6, PR #86) | `claude-sonnet-5-5` | 38 cases, 44 req | `2,999 / 5,934 / 7,687 / 7,968` | `99 / 546 / 886 / 961` | `$0.0022 / $0.0078 / $0.0221 / $0.0269` | `$0.38` (`382,366` µ$; `$0.82` across both runs + 10 narration samples) |
| **Operator deploy briefing** (Step 6, PR #86) | `claude-sonnet-5-5` | 1 request (`id=1`) | cache-write + input | settled `ok` | `$0.0254` (`25,438` µ$) | `$0.025` |

Prompt caching reduced warm-cache input costs from `$2.00/MTok` (or `$2.50/MTok` on the 5-minute cache write) to `$0.10/MTok` on `claude-sonnet-5-5`, keeping a warm briefing under `$0.01` and a warm change summary under `$0.003` (or ~$0.0005 on `claude-haiku-5-5`), well inside the `$1.00/day` default cap.

## 600-second idle CPU measurement

Measured on the operator's Windows 11 machine (`uv run python scripts/measure_idle.py`) over a `600.0 s` window after a `30 s` settle with `ai_state=ready` and `change_summaries=on`:

- **Step 6 receipt (PR #86, `2026-11-02`):**
  - `idle measurement: window=600.0s server_cpu=0.3099% (1.860s) tab_cpu=0.0025% (0.015s) roster_polls=0 cycles=0 ai_state=ready change_summaries=on budget=<0.5%`
- Both `serve_demo.py` (`0.3099% < 0.5%`, including `CycleWatcher` polling `AiCallRow` and `AiOutputRow` high-water marks and `ChangeSummarizer` idle on its event) and the Chromium dashboard tab (`0.0025% < 0.5%`, with `/api/ai` and `/api/ai/briefings` mounted) remained well below the `0.5%` single-core idle budget with `0` roster polls, `0` cycles, and `0` AI calls during the idle window.

## Live eval

`uv run python scripts/eval_ai.py --live` (`2026-11-02`, `claude-sonnet-5-5`, operator's `ANTHROPIC_API_KEY` in a temporary data directory):

- **Result:** `38 of 38 cases pass` (`22` briefings, `9` change summaries, `5` multi-turn/tool chat cases, and `2` outlook graphic narrations) at a total list-price cost of `$0.38` (`382,366` micro-dollars).
- **Adversarial & boundary coverage:** All `6` prompt-injection twins (`eval-briefing-injection-nws-headline`, `eval-briefing-injection-nhc-discussion`, `eval-summary-injection-nws-description`, `eval-summary-injection-nhc-key-messages`, `chat-injection-tcp`, and the tool-argument boundary checks) passed without leaking a URL, an unquoted coordinate, a fabricated level, or a tool call outside `TOOL_NAMES`.

## Source-drift and model-drift observations

- **Anthropic SDK `2.3.0` (`API 2026-10-21`):**
  - `output_config={"format": transform_schema(Model)}` is required instead of `messages.parse`/`messages.stream(output_format=...)` so `stop_reason` (`refusal`, `max_tokens`) and `usage` are settled in `ai_calls` before schema validation runs (`src/weatherbot/services/ai/caller.py`).
  - `transform_schema` moves Pydantic `maxLength` constraints into the JSON Schema property description rather than enforcing a hard token grammar limit; `validate.AREA_LIMIT = 600` enforces the upper bound deterministically after generation (`src/weatherbot/services/ai/validate.py`).
- **NOAA / NWS live sources (`2026-11-01` through `2026-11-02`):**
  - All 19 registered NHC, NWS, and Nominatim feeds answered cleanly on the two public landmarks (`Miami-Dade County Hall` and `Parliament Square`) during `pytest -m live`.
  - On the operator's machine, `POST /api/locations` for a separate US point returned `502` because `nws-points` (`parse_point`) rejected a response field shape without logging the underlying validation reason; tracked in GitHub issue #87 (`https://github.com/nathanramoscfa/weatherbot/issues/87`) for a hotfix before or at the start of Phase 7.

## Exact vs. growth-proof Phase 6 checks for Phase 7

- **Checks that grow by inclusion (stay live across Phase 7 and Phase 8):**
  - **Checks 8, 9, 10, 11:** `Runtime.make_claude`, `doctor` `ai` check, `HealthResponse.ai`, `SILENT_LIBRARIES` / `SecretFilter`, and the AST ban on `anthropic`/`httpx2` outside `src/weatherbot/services/ai/`.
  - **Checks 12, 17, 18, 19, 20, 21, 26, 27, 35, 36, 41, 42, 43, 45, 47, 48, 49, 50, 51:** Tracked test files, CLI commands (`brief`, `ask`) and `DOCUMENTS` keys, `tests/fixtures/ai/` 1 MiB budget and header/key scan, `docs/AI.md` sections, `web/routes/{ai,outlook}.py` and OpenAPI paths/models (Checks 28, 29), `events.py` `EVENT_KINDS`/`QUERY_KEYS`/`AiCallRow`/`AiOutputRow` inclusion (Checks 30, 33), `cli/serve.py` `ChangeSummarizer` wiring (Check 34), `frontend/src/api/keys.ts` inclusion (Check 37), `innerHTML` ban (Check 38), `phase-verify.yml` `"01".."06"` matrix subset and separate `"05"` / `"06"` Node steps (Check 50), and security gate wiring (Check 51).
- **Exact checks in `scripts/verify_phase06.py` (convert to `tagged(..., tag="v2.0.0-phase-6")` only in the step that deliberately changes what they read):**
  1. **Check 1:** `pyproject.toml` lists `anthropic>=2.3.0` in `[project] dependencies` and `httpx2` only in the `dev` group.
  2. **Check 2:** The two forbidden `import-linter` contracts (`"Only the AI service talks to Anthropic"` and `"The AI service never fetches or writes the official records"`) keep their exact source and forbidden module lists.
  3. **Check 3:** `AiSettings` in `src/weatherbot/services/config.py` has the six Phase 6 fields (`enabled`, `model`, `summary_model`, `daily_cap_usd`, `change_summaries`, `outlook_narration`) and `ENVIRONMENT_OVERRIDES` maps the six `WEATHERBOT_AI_*` names.
  4. **Check 4:** `src/weatherbot/services/ai/pricing.py` defines `PRICES` for `claude-sonnet-5-5`, `claude-haiku-5-5`, and `claude-opus-5-5`, `PRICES_AS_OF`, and `MAX_PROMPT_TOKENS = 100_000`, and imports no SDK.
  5. **Check 5:** `src/weatherbot/services/ai/guard.py` defines `AI_TABLES` as `{"ai_calls", "ai_outputs"}` and calls `set_authorizer`.
  6. **Check 7 & Check 16:** Revisions `0007_ai_calls.py` (`down_revision = "0006"`) and `0008_ai_outputs.py` (`down_revision = "0007"`) stay pinned in `FROZEN` in `tests/services/test_database.py`.
  7. **Check 14 & Check 15:** `context.py` and `validate.py` import only `weatherbot.models`, the standard library, `pydantic`, and `services/ai/schemas.py` (`validate.py` also `context.py`); `Briefing` has the five section fields and no schema in `services/ai/schemas.py` declares `level`.
  8. **Check 22, Check 23, & Check 24:** `TOOL_NAMES` in `tools.py` is the exact 9-tool tuple, every `TOOL_DEFINITIONS` entry has `strict: True` and `additionalProperties: False`, and `chat.py` keeps `MAX_TOOL_ROUNDS = 6` and `MAX_CONVERSATIONS = 8`.
  9. **Check 32:** No module-level `async def` under `src/weatherbot/web/routes/` names a repository, `ai_engine`, or `Session`.
  10. **Check 39:** `frontend/package.json` `dependencies` and `devDependencies` names equal `v2.0.0-phase-5`'s. If Phase 7 adds a chart or UI library to `frontend/package.json`, convert Check 39 in that Phase 7 step to read `v2.0.0-phase-6:frontend/package.json` via `tagged("frontend/package.json")`.
  11. **Check 40:** `AppShell.tsx`'s `NAV_ITEMS` lists `"/ask"` between `"/timeline"` and `"/settings"`, and `routes.tsx` routes `path: "ask"` to `<Ask />`.
  12. **Check 44:** `README.md`'s `## Status` names Phase 6 complete and Phase 7 next. When Phase 7 Step 1 or closure updates `README.md`'s `## Status`, convert Check 44's `## Status` assertion in that same PR to read `v2.0.0-phase-6:README.md` via `tagged("README.md")` (matching how Phase 6 Step 1 converted Phase 5's Check 47).

## Live smoke runs

- **Offline & replay browser smoke (`npm --prefix frontend run e2e`):** 6 Playwright Chromium specs (`dashboard.spec.ts`, `map.spec.ts`, `screens.spec.ts`, `ai.spec.ts` across ports `8799`, `8800`, and `8801`) passed on Ubuntu CI (`ci.yml` `browser` job `41555470331` and `41558425751`) and on the operator's Windows 11 machine with zero console errors, zero CSP violations, zero unexpected origins, zero coordinate leaks, and zero AI text echoed to the console.
- **Live NOAA/NWS pytest suite (`uv run pytest -m live`):** Passed against live NHC, NWS, and Nominatim endpoints using only the two public landmarks in a temporary data directory.
- **Operator deployment verification (`2026-11-02`):** `\Weatherbot\serve` running at commit `baa1dd2` (`ui.index_sha256="507cca9a0d85"`, database revision `0008` / head `0008`, `ai.state="ready"`), online `weatherbot doctor --json` passing `ai` (`"credential from the environment (ANTHROPIC_API_KEY); $0.00 of $1.00 today; authenticated"`), `web`, and `migrations`, and a real dashboard briefing settled `ok` in `ai_calls` (`id=1`, `25,438` micro-dollars).

## Pre-ship items

Every limitation or follow-up surfaced during Phase 6 has an explicit owner and destination:

1. **`POST /api/locations` `502` on `nws-points` `parse_point`:** Tracked in GitHub issue #87 (`https://github.com/nathanramoscfa/weatherbot/issues/87`) — fix `parse_point` field tolerance and log the source error reason before or at the start of Phase 7 so the operator can watch their own location.
2. **Forward geocoding (`City, State / Country` place search in `/settings` and CLI):** Tracked in GitHub issue #71 (`https://github.com/nathanramoscfa/weatherbot/issues/71`) and owned by **Phase 7 §7.3** (`docs/roadmap/ROADMAP.md` Phase 7 — "Locations and channels").
3. **Windows CI `test` job runtime (~20–36 min of 40 min timeout):** Tracked in GitHub issue #82 (`https://github.com/nathanramoscfa/weatherbot/issues/82`) — adopt shared per-module database templates (`ai_support.database_template`) in older test modules if Phase 7 tests approach the 40-minute ceiling.
4. **Frontend dev-only `minimatch` < `11.0.1` transitive dependency (Dependabot alert #2, medium, dev tooling only):** Tracked in GitHub issue #79 (`https://github.com/nathanramoscfa/weatherbot/issues/79`); `npm --prefix frontend audit --omit=dev` and `--audit-level=high` are 0 vulnerabilities.
5. **Retention for `ai_calls`, `ai_outputs`, snapshots, and geometry contents; multi-location comparison; forecast charts; surge/radar/satellite map layers; ntfy channel; and report export (with AI blocks):** Owned by **Phase 7** (`docs/roadmap/ROADMAP.md` §Phase 7 — Depth).
6. **Optional LAN access (`--lan` with bearer token), fresh-install smoke with no Anthropic key, and release packaging (`v2.0.0`):** Owned by **Phase 8** (`docs/roadmap/ROADMAP.md` §Phase 8 — Polish, LAN mode, and release).
7. **Surge and extreme-wind ladder rule evaluation (#33) and `advisory_issued` wording (#44):** Tracked in GitHub issues #33 and #44.
8. **Legacy v1 `weatherbot` on the operator's `PATH` ahead of `~/.local/bin` and open Dependabot PRs (#8, #31, #47, #69, #78):** Reported by `doctor`'s `path` check and tracked on their respective Dependabot PRs outside phase steps.
