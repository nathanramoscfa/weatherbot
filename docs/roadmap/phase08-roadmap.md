# Phase 8 Roadmap — UI/UX Redesign and Visual Dogfooding

**Status:** Not started

## Overview

Phase 8 turns a correct, complete web app into one that reads at a glance.
Phases 5 to 7 built every page to satisfy a functional contract and a DOM
assertion, and it shows: 173 `text-xs` (12 px) classes and 38 `text-[10px]` or
`text-[11px]` ones carry the explanations, raw rule ids such as
`hurricane_warning` and product codes such as `HWR` lead the cards, the export
paragraph sits above the fold, the map is a 520-pixel box above two cards of
checkboxes, and the five threat levels look much alike. Worse, two of the words
on screen are wrong: the level badge's own names ("Storm Watch", "Awareness")
are not the engine's, and the Settings page's ladder reference lists the rules
in the wrong order, under one name that does not exist, with products the engine
never reads. This phase redesigns the frontend into a meteorological command
center, makes the server the single source of its level vocabulary, builds
demonstration scenarios that put every level on screen while the real tropics
are quiet, and then looks at every page, in loops, first by an agent against a
written rubric and then with the operator, until the operator signs off. It
moves no level and changes nothing that leaves the machine: no ladder rule,
threshold, golden, change kind, cycle trigger, notification kind, prompt, or AI
product changes, no npm package is added, no database revision is written, and
nothing opens beyond loopback or is published (Phase 9). It is one phase because
every page shares one design system and one vocabulary, and it is ten steps
because each page must ship, and be looked at, on its own.

The phase lands in 10 layers:

1. **Demonstration scenarios** — `scripts/serve_demo.py --scenario
   {quiet,outlook,cone,watch,landfall}` drives a synthetic Atlantic storm, built
   in the live feeds' own formats at two decimals and labelled synthetic,
   through the real fetch, engine, storage, API, and event path, so the two
   public landmarks read every level from 1 to 5 by a named rule; the `landfall`
   scenario seeds the history that leads to it, and its AI panels replay
   briefings recorded live once, with the operator's yes. `README.md`'s status
   corrects the phase names that PR #108 renumbered, and Phase 7's check 59
   moves to its tag. The phase flips to In progress.
2. **The design system and readable type, everywhere** — Tailwind tokens in
   `frontend/src/index.css` (the operator's 15 px and 17 px prose sizes, a 13 px
   caption, threat tints for levels 1 to 5 in both themes, elevation, radius),
   primitives under `frontend/src/ui/`, the icon navigation with live status
   badges, every `text-xs` and pixel size replaced across all eight routes,
   `docs/DESIGN.md`, and the readability gate:
   `frontend/e2e/readability.spec.ts` checks size, contrast, line measure, and
   horizontal overflow in CI.
3. **Plain English and one vocabulary** — `GET /api/ladder` serves the engine's
   levels, rules, read products, and thresholds; `frontend/src/assessment/`
   gains the level vocabulary pinned to it, the five-step threat meter, the
   location hero (the engine's level name, the deciding rule's sentence, the
   actions), and the "Why this level / Official provenance & controls"
   disclosure that every rule id, code, source, zone, raw time, and the
   evacuation-order switch move into; the Settings ladder is rebuilt from the
   route.
4. **The command-center dashboard** — the one-line status and action bar with
   the next-advisory countdown and the export popover, location switcher cards
   with one featured location, stat tiles, the AI briefing card, and the live
   situation mini-map.
5. **The immersive map** — `/map` as a tall canvas with floating layer, legend,
   status, and advisory-slider panels over it, and the replay panel gone from
   it.
6. **The replay workbench** — `/replay` as a side-by-side map, scrubber, and
   level history beside the same location hero the dashboard uses, with no
   scrolling needed at 1440×900.
7. **Sectioned settings and the secondary pages** — five Settings tabs that deep
   links open, starter prompt chips on `/ask`, and the new hierarchy on
   `/storms`, `/alerts`, and `/timeline`.
8. **Loop 1: the AI visual dogfood** — `frontend/e2e/dogfood.spec.ts` renders
   every route for every scenario at 1440×900 and 390×844 in both themes, the
   agent inspects each screenshot against the rubric in
   `docs/phase08-dogfood.md`, logs every defect, and fixes and re-renders until
   a full round is clean; the whole-phase smoke, the idle measurement, and the
   redesigned alarms are proved.
9. **Loop 2: the operator's dogfood** — the operator walks every page and
   scenario on demonstration servers in their own browser, each item of feedback
   is logged and resolved, and the loop ends only at the operator's explicit
   sign-off; then the operator's service is upgraded and verified. Deployed on
   the operator's machine with the operator's yes.
10. **QA + `verify_phase08.py`** — `scripts/verify_phase08.py` (`--fast`,
    `--py`, `--node`, `--ui`, `--live`, `--security`, `--all`, `--post`),
    `docs/phase08-qa-findings.md` with the dogfood sign-off, and matrix entry
    `"08"` beside `"01"` to `"07"` in `phase-verify.yml`, with its own Node
    steps; Phase 8 closed in this roadmap and the project roadmap; the
    `v2.0.0-phase-8` tag.

The ship test for Phase 8 is straightforward: every scenario starts offline and
reads its declared level and rule for both landmarks, and the landfall
scenario's briefing for the Miami-Dade landmark passes the validators; no
`text-xs` or pixel font size remains under `frontend/src`, and the readability
gate reports no element of primary prose under 14 px, no text under 13 px, no
contrast below WCAG AA, no paragraph wider than 42 em, and no horizontal
overflow on any of the eight routes at 1440×900, 1280×800, and 360×740; no rule
id, product code, source id, or zone appears in a card's headline, and opening
the disclosure shows all of them with the evacuation-order switch; the level
names on screen equal the engine's and the Settings ladder equals `RULES`;
`/map` floats its controls over a canvas at least 70 percent of the viewport
tall and holds no replay panel, `/replay` shows its map, scrubber, and hero
headline together at 1440×900, and `/settings` opens each of its five tabs from
a link; both dogfood loops are complete, the operator's sign-off is recorded,
and the operator's `/api/health` reports the redesigned build; the server and
the tab each stay under 0.5 percent of a core idle; no npm package, `style=`
attribute, or CSP change was added; Phase 1's to Phase 7's verification still
pass; and `scripts/verify_phase08.py --fast` exits 0 on Ubuntu CI with
`phase-verify (01)` to `(08)` green.

**Pre-requisite:** Phase 7 closed on 2026-11-12 (PR #106; `v2.0.0-phase-7`), and
PR #108 inserted this phase before the release on 2026-11-13. Phase 7's replay
page, map layers, charts, settings editors, location manager, and report are the
surfaces this phase redesigns, and its Playwright guard, screenshot spec,
demonstration server, and idle measurement are the tools it extends. Phase 6's
AI panels, recordings, replay transport, and validators are what the scenarios'
briefings run through unchanged; Phase 5's guarded API, event stream, CSP with
its per-answer nonce, and `frontend/` chassis are what every page still sits on.
Phase 3's `RULES` and `AlertLevel` (PR #34) are the vocabulary `GET /api/ladder`
serves. The planning kit is roadmodel 0.2.114: the updater's export of it was
uncommitted, so this roadmap's pull request commits it on its own with the
matching `uv.lock` pin, after a `fix(deps)` commit that moves
`opentelemetry-api` to 1.45.2 for CVE-2026-126360, which the fail-closed
pre-commit audit reported and which blocked every commit (the same bump as
Dependabot's PR #109).

**Dependency:** Phase 9 (Release 2.0) does not start until Phase 8's V-checks
are green and the operator has signed off. Its documentation describes and
pictures the redesigned pages, its fresh-install smoke opens them with no key,
topic, or corpus, and its readiness scan covers the demonstration scenarios'
synthetic data and recordings.

**Design rationale (decisions and clarifications of the brief and the project
roadmap).** Twenty decisions, each made against recorded, measured, probed, or
researched evidence while this roadmap was written (2026-11-15), checked against
the code by an independent review of the draft; the steps cite them by number.
The project roadmap records each one that changes it, in this roadmap's own pull
request. Step agents treat them as settled spec unless the operator changes
them.

1. *Nothing here moves a level or changes what leaves the machine.* No ladder
   rule, threshold, golden, change kind, cycle trigger, notification kind,
   prompt, model, or AI product changes, so Phase 3's digest-pinned replay
   goldens, Phase 4's approved notification goldens, and Phase 7's check 20
   (`services/policy.py` and `tests/golden` equal to `v2.0.0-phase-6`) stay
   exact. The only server change is one read-only route (Decision 8), which
   serves engine metadata and no location data. No revision is written, so the
   operator's database stays at `0010`. No new outbound host, no secret, and no
   setting is added; `EDITABLE` keeps its 12 keys (Phase 7's check 25). The
   scenarios live in `scripts/` and `tests/fixtures/`, never in `src/`, so
   nothing season-specific or synthetic reaches the package.
2. *The scenarios come first, and they are live captures, not replays.* Every
   later step has to see all five levels, and today's demonstration shows two:
   from the recordings both landmarks read level 1
   (`scripts/export_api_fixtures.py`'s fixtures say `all_clear` for both), and
   the switch file adds a synthetic NWS Hurricane Warning for the Miami-Dade
   landmark's zone (`FLZ173`), which puts level 5 beside the recording's only
   storm, Eastern Pacific Hurricane Simon (`ep202026`, bin `EP5`, off Mexico) —
   a map nobody can read. The replay corpus cannot fill the gap:
   `AssessmentService` refuses a replay snapshot ("a replay snapshot is never
   assessed into history: history is live only"), and re-serving the archive's
   geometry as live data would relabel its 6,371,200 m sphere as WGS 84, which
   the engine's CRS rule forbids. So Step 1 builds a synthetic Atlantic storm in
   the live feeds' own formats — the roster entry and the tropical weather
   summary service's layers a live cycle actually reads (cone, track, forecast
   points, wind radii, arrival-time layers, and watch-warning segments, queried
   `where=1=1` and told apart by their `binnumber`, so an Atlantic slot such as
   `AT1` needs no other service), the wind-speed probability bands, the
   arrival-time KMZs the roster links, and the slot's TCP list and product —
   from the recorded captures' field shapes with new geometry at two decimals
   (the personal-data rule refuses three-decimal pairs outside the recorded
   trees), labelled synthetic in its own fields as `scripts/synthetic_surge.py`
   labels its surge (a `snippet` or description note and a `"synthetic": true`
   attribute where the format has a free field, the storm's name, an alert's
   headline and sender, the TCP's text), and named so no one mistakes it for a
   real storm. Its records' `Provenance.source_id` stays the register id the
   fetcher stamps (`models/provenance.py`'s `SourceId` is a closed literal of
   register ids, and a staged answer cannot change it), so no source, register
   row, or `src/` change is needed. Every per-storm URL a cycle requests must be
   staged: an unmatched request raises `respx`'s `AllMockedAssertionError`, an
   `AssertionError` that neither the fetcher (which catches
   `httpx.TransportError`) nor the snapshot's guard (which catches
   `SourceError`) turns into a failed source, so the cycle crashes. Each
   scenario stages the storm and its official products so both landmarks read a
   declared level by a declared rule (the table below), through the real fetch,
   engine, storage, API, and event path. The demo clock still starts at
   `source_support.NOW` (2026-10-13 01:30 UTC). The default demonstration and
   its switch file stay exactly as they are, so every Phase 5 to Phase 7 spec
   keeps its server and its expectations.
3. *AI text in a scenario is a real recording, made once with the operator's
   yes.* A briefing is never written by hand: "No model output is ever stored or
   shown as a fact", and a hand-written answer under an "AI briefing — Claude
   Sonnet 5.5" label would be one. The existing recordings answered the eval
   set's replay contexts, so against a scenario's context the validators
   withhold them (a source key or a level differs), which is itself a state
   worth seeing but not the only one. Step 1 extends
   `scripts/record_ai_fixtures.py` with a scenario kind that builds each
   scenario's database through the same code `serve_demo.py` uses and records,
   live, one briefing per landmark per scenario and each landmark's landfall
   escalation summary (the Miami-Dade landmark rises from 4 to 5 and the Nassau
   one from 3 to 4, and `validate_summary` allows only a summary's own two
   levels): twelve requests, at most $0.60 at Sonnet 5.5 list price (a briefing
   measured about $0.03, $0.05 at worst, and a summary about $0.01 in Phase 6).
   Each recording is registered as a case in `all_cases()` — kind `stream` for a
   briefing, `parse` for a summary — because `tests/ai/test_ai_fixtures.py`,
   which Phase 6's V5.2 selects, requires every manifest entry to be one, and
   the directory stays under its `BUDGET_BYTES` (1 MiB; 489,508 bytes on
   2026-11-15, about 18 KB a briefing). The command refuses without a
   credential, prints the request count and the ceiling, and runs only after the
   operator's yes; if the operator declines, the decision is recorded in this
   roadmap in Step 1's PR, the landfall test below expects `withheld`, and Phase
   8's check 6 expects no scenario recording. `DemoReplay` then answers by
   scenario and landmark; each scenario's seeding stores its briefings, and the
   landfall one its summary, through the real services before the server binds,
   because `serve`'s `ChangeSummarizer` primes to the newest stored assessment
   and never backfills; and a test fails if the landfall scenario's Miami-Dade
   briefing is ever withheld, so a later change to the synthetic storm that
   breaks a recording cannot pass unnoticed. Re-recording costs cents and
   follows the same yes.
4. *The type scale is the operator's, set as tokens, with one caption size.* PR
   #108 recorded "15px–17px (`text-sm` / `text-base`)" prose and a 14 px floor
   for explanations. Tailwind 4 reads its scale from CSS variables, so
   `frontend/src/index.css`'s `@theme` sets `--text-sm` to 0.9375 rem (15 px,
   line height 1.5) and `--text-base` to 1.0625 rem (17 px, line height 1.6),
   adds `--text-caption` at 0.8125 rem (13 px, line height 1.4) for meta text
   only (timestamps, units, badge text, legend and axis captions, footnotes),
   and sets the heading steps (`--text-lg` 20 px, `--text-xl` 24 px,
   `--text-2xl` 30 px). `text-xs` (12 px) and every arbitrary size
   (`text-[11px]`) then leave `frontend/src`; a static check holds that.
   Measured in non-test TSX on 2026-11-15: 173 `text-xs`, 38 `text-[10px]` or
   `text-[11px]`, 41 `text-sm`, and 19 `text-base`. The face stays the system
   stack (`ui-sans-serif, system-ui, …`, Segoe UI Variable on Windows 11), and
   every number that changes — a distance, a bearing, a percentage, an age, the
   countdown — sets `tabular-nums` so it does not jitter.
5. *No new package, no font download, no inline style, and the CSP stands.*
   Everything this phase needs is already installed or is a few lines of its
   own: `radix-ui` 1.8.1 ships the `Popover` the export control uses (portalled
   outside every render a `[style]` test inspects, and styled under the same
   nonce as the theme menu's `DropdownMenu`), `lucide-react` the icons, HTML the
   `<details>` disclosure, and `frontend/src/ui/` the tabs (Decision 13). A font
   package fails `licenses:check` (Inter and its peers are OFL-1.1, outside the
   allowlist of MIT, ISC, BSD-2-Clause, BSD-3-Clause, Apache-2.0, and 0BSD), and
   a font host would need a CSP entry and an outbound host.
   `@axe-core/playwright` would add an MPL-2.0 dev dependency, and any new name
   in `frontend/package.json` turns Phase 6's check 39 and Phase 7's check 43
   red, because both compare its dependency and devDependency names exactly; the
   readability gate's checks are a few dozen lines of in-page script instead
   (Decision 6). The CSP's `style-src` has no `unsafe-inline`, so no `style=`
   attribute enters (Phase 7's check 44): positions are Tailwind classes, and
   Radix's injected styles carry the existing per-answer nonce. `CSP_SUFFIX`,
   the twelve map layers, and `events.py`'s `QUERY_KEYS` stay exactly as they
   are (Phase 7's checks 35, 36, and 45); a new frontend query key nests under
   an existing prefix, as Phase 7's charts did under `timeline`.
6. *The readability gate is four computed checks, run in CI.*
   `frontend/e2e/readability.ts` exports `auditReadability(page)`, which
   inspects every visible element that has its own text inside `<header>`,
   `<main>`, and `<footer>`, skipping SVG chart internals, visually hidden text,
   closed `<details>` content, and everything inside the Leaflet container. (1)
   *Size*: an element of primary prose (`p`, `li`, `dd`, `dt`, `td`, `th`,
   `label`, `summary`, `blockquote`, `figcaption`, `legend`, `a`, `button`, and
   anything with `role="note"`, `"alert"`, or `"status"`) computes `font-size`
   of at least 14 px, and any other text at least 13 px — so a caption is a
   `<span>`, `<time>`, or `<small>` set in `text-caption`, never a paragraph.
   (2) *Contrast*: the WCAG 2.2 ratio between the text's colour and the first
   opaque background up its ancestors, alpha-composited, is at least 4.5:1, or
   3:1 for large text (24 px, or 18.66 px at weight 700); a background image or
   gradient behind text is a finding of its own, because its contrast cannot be
   computed. (3) *Measure*: a `p`, `li`, or `dd` holding 160 characters or more
   is at most 42 em wide (about 80 characters a line). (4) *Overflow*:
   `document.documentElement.scrollWidth` never exceeds `clientWidth`, and no
   audited element's box extends past the viewport's right edge unless an
   ancestor scrolls it on purpose (`overflow-x: auto` or `scroll`). The second
   half is needed because `AppShell.tsx`'s root clips horizontal overflow today
   (`overflow-x-hidden`), which hides it from the page-level measure; Step 2
   removes that clip. In CI the `browser` job runs `readability.spec.ts` over
   the eight routes — `/settings` once per tab and `/replay` with its storm
   loaded, twelve renders in all — at 1440×900, 1280×800, and 360×740 on the
   `quiet` and `landfall` scenario servers (the sparsest and the densest page;
   the default server's state depends on which spec flipped its switch file
   last), in light, and again at 1440×900 in dark for contrast: 96 renders,
   against a job whose whole Playwright run took 59 to 66 seconds of its
   15-minute bound on 2026-11-13. The dogfood harness runs the same audit over
   every scenario (Decision 17).
7. *Plain English leads; provenance is one click away and never removed.* A
   location's headline is the engine's level name with "At least" before it when
   the assessment is incomplete, then the deciding rule's sentence
   (`rule_trigger`, for example "A Hurricane Warning covers the location.") and
   the level's actions — words the API already serves — and never a rule id,
   product code, source id, zone, breakpoint span, or raw timestamp. Those, with
   the evidence, the official products, the unavailable inputs, the coverage,
   and on the dashboard the evacuation-order switch, move into a native
   `<details>` whose `<summary>` reads "Why this level / Official provenance &
   controls", closed by default. Native, because closed content stays in the DOM
   (Phase 7's `replay.spec.ts` and `phase7.spec.ts` read `hurricane_warning` and
   `HWR` from `replay-assessment-card` by text content, and a Radix
   `Collapsible` unmounts what it hides and sets inline styles that
   `assessment.test.tsx`'s `[style]` assertion refuses), it needs no script, it
   is keyboard- and screen-reader-native, and it prints. The four shared
   components (`LevelSummary`, `EvidenceList`, `OfficialProductList`,
   `ThreatTable`) render inside it as children, composed by each page, so Phase
   7's check 49 still finds their names in `Dashboard.tsx` and `Replay.tsx`.
   What a reader must not miss stays outside it: the "At least" floor, a
   toggle-changed note, and an evacuation order that is on.
8. *One vocabulary: the engine's, served by `GET /api/ladder`.* Two words on
   screen are wrong today. `ThreatLevelBadge`'s fallback names ("Hurricane
   Warning / Evacuation", "Tropical Storm Warning / Hurricane Watch", "Storm
   Watch", "Awareness") are not `AlertLevel`'s ("Hurricane Warning", "Warning /
   Watch / Evacuation", "Watch / Hurricane Threat", "Tropical Storm Threat"),
   and the dashboard calls the badge without the API's label. And
   `Settings.tsx`'s hand-written `LADDER_RULES` disagrees with `RULES` in order
   (it puts `evacuation_order` second and swaps rules 9 and 10), in one name
   (`tropical_storm_cone`, where the engine has `storm_cone`), in products (it
   credits Extreme Wind Warnings, Storm Surge Warnings and Watches, and 50-kt
   bands, none of which `engine/official.py`'s four `LADDER_EVENTS` or the 34-kt
   rule reads — issue #33 asks whether a surge product should move the ladder),
   and in codes (`TRW` and `TRA`, where `WatchWarningCode` has `TWR` and `TWA`).
   So the server becomes the one source: `GET /api/ladder`, a sync read route
   built by `services/ladder.py` (the services may import the engine; the web
   layer may not), answers the five levels (number, label, actions), the eleven
   rules in evaluation order (order, id, level, sentence, sources), the NWS
   events and NHC codes the ladder reads, and the thresholds the engine is
   running: the startup settings' (`settings.engine.thresholds()`, as `WebState`
   already uses for replay), because `LiveSettings` reloads only
   `[notifications]` and `[retention]`, so a value edited in the file since
   start is not yet the engine's and must not be shown as if it were.
   `scripts/export_api_fixtures.py` writes it as
   `frontend/src/test/fixtures/ladder.json`; the frontend's fallback table must
   equal that fixture (a Vitest test), and its query key is
   `invalidatableQueryKey("settings", "ladder")`, so a settings event refreshes
   it with no new `QueryKey`.
9. *The dashboard is a command center with one featured location.* A one-line
   status and action bar (wrapping below 1024 px) holds the snapshot's age and
   status, the next NHC product as a countdown, `Check now`, and `Export report`
   — a non-modal Radix `Popover` holding the all-locations link
   (`data-testid="export-report-all"`), each location's link, the "Include the
   AI briefing" box, and its caveat in one line, so the paragraph that explains
   the export leaves the page. Location switcher cards replace the comparison
   strip: one `<article>` per location, labelled with its name and holding the
   page's only heading that contains it (the specs match headings by substring,
   and a second match is a strict-mode failure), the level badge in the engine's
   words, the plain-English headline, the NWS-coverage caption (`phase7.spec.ts`
   reads "Outside NWS coverage" from a location's article), the sparkline, and a
   link to `#location-<slug>` that features it (`aria-current` on the featured
   one). The featured location — the highest level first, then list order, kept
   in that URL hash, which `locationCardId` already writes — shows its hero,
   meter, stat tiles, arrival timeline (`charts.spec.ts` needs
   `arrival-timeline` on `/`), AI briefing card (`region` "AI briefing for
   {name}"), changes since the last assessment, and the disclosure. The live
   situation mini-map is a card drawing cones, tracks, watches and warnings, and
   locations from the same `queryKeys.map()` query `/map` uses, with a link to
   `/map`. A spec that needs a location's briefing panel (`ai.spec.ts`,
   `report.spec.ts`) features that location first through its card.
10. *The countdown and the mini-map keep idle near zero.* The countdown resolves
    to the minute: one `setTimeout` to the next minute boundary, cleared on
    unmount and paused while `document.hidden`, with no `setInterval` anywhere
    new (Phase 7's check 37 already forbids one under `frontend/src/map/`).
    Leaflet runs no timer while nobody touches the map, and its tiles load
    during the settle, before any window opens. `scripts/measure_idle.py`
    measures exactly this page, since its `idle.spec.ts` opens `/`: the budget
    stays 0.5 percent of a core each for the server and the tab, last measured
    at 0.2656 and 0.0024 percent (2026-11-12).
11. *The map is the page; its controls float over it.* `/map`'s canvas fills the
    viewport below the header and is never shorter than 70 percent of it. Its
    panels sit over the canvas as siblings of the Leaflet container, never
    inside Leaflet's DOM: Layers (`region` "Map layer toggles", the twelve
    labels of today's flat `LAYER_TOGGLE_ITEMS` under four new headed groups
    from a `LAYER_GROUPS` constant beside it — Forecast: `cone`, `track`,
    `points`, `past_track`, `watches_warnings`, `outlook`; Wind & surge:
    `wind_radii`, `wind_probabilities`, `peak_surge`; Observations: `radar`,
    `satellite`; Locations: `locations` — with the wind-probability threshold
    inside it), Legend (sections for visible layers only, with the nowCOAST age
    note and the unavailable banners), a status chip (as-of time, origin, storm
    count, and Fit), and the advisory slider docked at the bottom
    (`AdvisorySlider` unchanged, whose own root keeps
    `data-testid="advisory-slider-panel"`; the dock carries no test id, because
    a second match breaks the strict locators in `layers.spec.ts` and
    `phase7.spec.ts`). The page keeps its `<h1>` "Map", visually hidden, because
    `AppShell.test.tsx` finds every route's heading by its exact name. Each
    panel is an opaque surface — no translucent glass over the tiles, because
    the readability audit composites a text's background from its ancestors, and
    the map behind a panel is not one of them — and a plain disclosure toggled
    by a button with `aria-expanded`, open by default at 1024 px and wider and
    collapsed below; a Radix `Popover` would portal out of the map's stacking
    context, and a modal one would trap focus. Leaflet's zoom and attribution
    stay uncovered. The replay panel (`data-testid="replay-panel"`, its two
    selects, and `replay-not-live-banner`) leaves `/map`, and a "Replay a past
    storm" link to `/replay` appears when `/api/health` reads `corpus: true`.
    `useLeafletMap`'s `ResizeObserver` (PR #105) re-fits the map whenever a
    panel or the viewport changes its box.
12. *Replay is a side-by-side workbench.* At 1280 px and wider `/replay` is two
    columns: the map (at least 60 percent of the viewport tall) with the
    scrubber and the level history chart beneath it, and a sticky column with
    the replay banner, the same location hero the dashboard uses, and the
    disclosure. Narrower, they stack: map, scrubber, hero, chart. At 1440×900
    the map, the scrubber, and the hero's headline all lie within the first
    viewport, which a browser test asserts from their bounding boxes. The "not
    live" banner stays non-dismissible, and the page shows no AI panel and no
    switch (`replay.spec.ts` counts zero of each).
13. *Settings has five tabs that deep links open.* A `Tabs` primitive of its own
    in `frontend/src/ui/Tabs.tsx` implements the WAI-ARIA tabs pattern
    (`role="tablist"`, `"tab"`, and `"tabpanel"`, `aria-selected` and
    `aria-controls`, a roving `tabindex`, arrow keys, Home, and End) in about a
    hundred lines, because Radix `Tabs` sets an inline `animation-duration` on
    mount and `Settings.test.tsx` asserts that the page renders no `[style]`
    element. Five tabs are bound to the URL hash: `#locations` (the default),
    `#notifications`, `#ai`, `#retention`, and `#about`. `#disclaimer` opens
    About and scrolls to the disclaimer, because the footer's "Read full
    disclaimer" links there; the AI section keeps `id="ai"`, because
    `ai.spec.ts` opens `/settings#ai`. The selection is read from the router's
    location (`useLocation().hash`) and written through `useNavigate()` with
    `replace: true`, so a reload keeps it: the footer link is a router `<Link>`,
    whose navigation fires no `hashchange`, and a raw `history.replaceState`
    would leave the router's location stale. Inactive panels unmount, so each
    panel's queries run when it is shown. About holds the ladder from `GET
    /api/ladder`, the effective settings, the full disclaimer, and the bundled
    licences; the restart and file-problem banners stay above the tabs, where
    every tab shows them.
14. *Ask's starter chips fill the question and never send it.* Every chat turn
    costs money (two to four cents in Phase 6's measure), so a chip only writes
    a question into the box and the operator presses Ask. Four chips are built
    from the chosen location's stored assessment and name it only by its chosen
    name: why it is at its level, what to do at this level, when winds could
    arrive, and what the cone means for it. They are disabled while AI is not
    ready, and the transcript takes the new hierarchy (question and answer,
    lookups as chips, the AI label on every answer).
15. *Storms, Alerts, and Timeline get the hierarchy, not new data.* Each card
    leads with words — an alert's event and the location it covers, a storm's
    name, classification, intensity, and motion, a timeline entry's level change
    in the engine's terms — with codes and ids in the same disclosure pattern,
    times as a relative age with the local time and a UTC caption, and empty
    states that say what will appear and when. No route or response field
    changes for them.
16. *The earlier phases' checks stay green, with one planned conversion, and
    every selected test file keeps its path.* An audit of all seven verifiers,
    their mutation tests, their JUnit selections, and the pinned tests no
    verifier names, against everything this phase does (2026-11-15; the table
    under "Verification surfaces"), found one check that must convert and a
    longer list that stays green only if the work is done a certain way. Phase
    7's check 59 converts in Step 1, because the README's live status text
    becomes wrong the moment it names this phase. Every frontend selection in
    every verifier is file-level — a JUnit `classname` such as
    `src/pages/Dashboard.test.tsx` or `map.spec.ts` — so test titles may change
    freely, but each selected file must keep its path and hold at least one
    test, all passing and none skipped, and the catch-all rows (the whole Vitest
    run, the whole Playwright run, and pytest) make every test required, new
    ones included. So no step moves or deletes a page, component, test, spec, or
    fixture an earlier check names; `map.spec.ts`, whose only test drives the
    replay panel this phase removes, is rewritten in place to test the live map;
    and `MapView.test.tsx` loses its replay-panel case and keeps the rest.
    Literal pins stay literal: `NAV_ITEMS` keeps one `{ to: "…", label: "…"`
    object per line in `AppShell.tsx`, in the same order, with no other `{ to:`
    object in that file (Phase 6's check 40, Phase 7's check 48);
    `Dashboard.tsx` and `Replay.tsx` each still name `LevelSummary`,
    `ThreatTable`, `OfficialProductList`, and `EvidenceList` (Phase 7's check
    49), which the disclosure takes as children; `DEFAULT_LAYER_VISIBILITY`
    keeps its twelve literals in `layers.ts` (check 36); `serve_demo.py` keeps
    `DemoReplay`, `request_kind`, `chat_round`, and `demo_claude` defined in
    itself, its flags, and every default byte-for-byte (Phase 6's check 41,
    Phase 7's check 57, `tests/scripts/test_serve_demo.py`);
    `simulate_advisory.py` keeps its pinned names (Phase 4's check 38);
    `README.md` keeps `### The dashboard` and its `## Commands` needles; and
    `role="img"` stays in `LevelSparkline.tsx` for Phase 7's mutation case.
    Every route keeps an `<h1>` with today's name (Dashboard, Map, Replay,
    Storms, Alerts, Timeline, Ask, Settings), visually hidden where the design
    wants, because `AppShell.test.tsx` finds each by its exact name; and
    `tests/ai/test_ai_fixtures.py` requires every AI recording to be a
    registered case within the directory's byte budget (Decision 3). Eight
    Vitest files assert that a render holds no `[style]` element (the Settings
    page, the assessment components, the four chart tests, quiet hours, and
    retention), and Radix `Tabs` and `Collapsible` set inline styles when they
    mount, so this phase builds its tabs and its disclosures without them
    (Decisions 7 and 13). No check is added to an older script, because each
    phase's `--post` pins the last phase's total: Phase 8's must assert 107.
17. *Dogfooding is two loops, each with a ledger and an exit rule.* Loop 1 (Step
    8): `frontend/e2e/dogfood.spec.ts`, tagged `@dogfood` and excluded from the
    default run as `@idle` is, renders every route (each Settings tab, `/replay`
    with its storm loaded) for every scenario at 1440×900 and 390×844 in light
    and dark — one test per scenario, viewport, and theme, twenty tests of
    twelve renders, each with its own raised timeout, since the configuration's
    120 seconds would not hold 48 — saves a full-page screenshot of each render,
    runs the readability audit, and writes
    `frontend/test-results/dogfood/audit.json`. The agent opens every screenshot
    and judges it against the rubric in `docs/phase08-dogfood.md` (hierarchy,
    the level legible in a second, vocabulary, colour used only for threat,
    spacing rhythm, alignment, empty and error states, the phone layout,
    dark-theme parity, the map's panels, focus visibility, and the disclaimer
    present), and logs each defect with its key (route, scenario, viewport,
    theme), rubric item, severity (blocker, major, minor, polish), and the
    commit that fixed it. A round ends when every screenshot has been judged;
    the loop ends after a full round that logs no blocker, major, or minor
    defect while the audit reports nothing. Loop 2 (Step 9): the operator walks
    every page in their own browser on this machine, one scenario per round, on
    demonstration servers started from the step branch; each item of feedback
    goes into the ledger in the operator's words with its disposition; the loop
    ends only at the operator's explicit sign-off, recorded in the ledger with
    its date, and the deploy follows.
18. *Screenshots are evidence, not repository content.* A full round is 240
    renders (twelve per scenario, viewport, and theme), at 100 to 300 KB a page,
    so no screenshot is committed: the harness writes under
    `frontend/test-results/` (git-ignored), the `browser` job keeps uploading
    `frontend/test-results/screenshots/` as an artifact, and the ledger names
    each screenshot by its key. Screenshots and the audit file show only the two
    public landmarks and the synthetic storm.
19. *The operator's machine is touched only with a yes, and only at Step 9.*
    Steps 1 to 8 and Step 10 change nothing there. Step 9's walkthrough runs
    demonstration servers in temporary data directories on loopback ports, and
    its deploy follows Phase 7's recipe after the operator's yes: `schtasks
    /End` on `\Weatherbot\serve`, `npm ci` and the build, `uv tool install
    --reinstall --from <checkout> weatherbot`, and `/Run`, away from HH:25, when
    `\Weatherbot\check` could restart `serve`. With no revision there is no
    migration. The Deployed & verified check reads `/api/health`'s
    `ui.index_sha256` against the built `src/weatherbot/web/static/index.html`.
20. *The version stays `2.0.0.dev0`, so health names the build.* `/api/health`
    names the built interface and the database head, which tells this build from
    the last without a version bump; the `v2.0.0-phase-8` tag marks the phase,
    and this roadmap's pull request adds its row to the project roadmap's
    "Release & tagging" table, which lists every phase tag but this one. Phase 9
    owns the release candidate.

The five scenarios (Decision 2), with the level and deciding rule each landmark
must read and the port the browser runs use:

| Scenario   | `simulated Miami-Dade` | `Parliament Square`        | Port |
| ---------- | ---------------------- | -------------------------- | ---- |
| `quiet`    | 1 `all_clear`          | 1 `all_clear`              | 8802 |
| `outlook`  | 2 `development_region` | 2 `development_region`     | 8803 |
| `cone`     | 3 `hurricane_cone`     | 2 `storm_cone`             | 8804 |
| `watch`    | 4 `hurricane_watch`    | 3 `tropical_storm_watch`   | 8805 |
| `landfall` | 5 `hurricane_warning`  | 4 `tropical_storm_warning` | 8806 |

Every scenario stages its own NWS alert answers for each query the Miami-Dade
landmark makes (its point, its forecast zone, and its county zone), so no
recorded alert leaks in: the newest recorded answers, dated 2026-10-17, hold a
Rip Current Statement. `quiet` holds no storm, no alert, and no outlook area.
`outlook` holds no storm and one seven-day development region over both
landmarks. In `cone` the storm is still a tropical storm at its closest approach
to the Nassau landmark and a hurricane by the Miami-Dade landmark's, both within
the cone horizon, and any 64-kt band staged at the Nassau landmark stays below
the 10 percent hurricane floor, or `hurricane_wind_probability` (rule 7, level
3) would outrank `storm_cone` (rule 8). `watch` adds an NWS Hurricane Watch for
`FLZ173` and NHC `HWA` and `TWA` segments within 25 km (`coastal_reach_km`) of
the two landmarks. `landfall` makes the storm a major hurricane at landfall with
an NWS Hurricane Warning and `HWR` and `TWR` segments, wind-speed probabilities
and arrival readings at both landmarks, and a seeded history of the three
earlier stages (`outlook`, `cone`, `watch`) as earlier advisories, so the
sparkline, the level history, the timeline, the escalation notifications, and
each landmark's change summary all have content. Every scenario's assessments
are complete, with no unavailable input: the roster and the summary service
answer, the in-coverage landmark's alert lists answer, every storm has a usable
cone, and every storm has forecast points and both arrival kinds
(`engine/assess.py`, `cones.py`, `threats.py`).

**Branch strategy.** Every step in this phase lands on its own short-lived
feature branch (`feature/phase08-step<M>-<slug>`), opens a pull request against
`main`, waits for the project's CI workflow to go green, and squash-merges with
a Conventional Commits subject line. Direct pushes to `main` are blocked by
branch protection. See the project roadmap's "Branch management strategy" for
the canonical naming convention, PR rules, and release tagging — this paragraph
confirms those rules apply unchanged within this phase. Per-step branches are
listed on each step header below as `**Branch:**` so reviewers can map commits
1:1 to the step they implement.

**Branch-first execution rule.** The very first action of every step — before
reading any files, before running any tool, before drafting any change — is to
check out the branch named in that step's `**Branch:**` line:

```sh
git checkout -b feature/phase08-step<M>-<slug>
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
feature/phase08-step<M>-<slug> <worktree-path> origin/main`, the worktree is
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
(the operator's coordinates, address, or typed place, credentials, tokens, an
ntfy topic) and no new insecure pattern (injection, a subprocess built from a
shell string, unsafe deserialization, a path read outside the directory it
names, markup built from text — `innerHTML`, `dangerouslySetInnerHTML`, or a
string handed to Leaflet — a `style=` attribute, a link to another origin
without `rel="noopener noreferrer"`, a new outbound host, a coordinate or AI
text in the browser's console, a key or token in a fixture, a response readable
from another origin, a state-changing request a cross-site page could send). The
gate is wired into the pre-commit hook and re-run in CI, so a security issue
introduced while implementing a step is caught during development — before it
reaches the branch, the PR, or `main`. See the project roadmap's "Security &
privacy strategy" → "Per-step security gate" for the canonical checks and
tooling; each step's XML `<task>` carries a `<security>` block restating them
for the agent, and each step's Acceptance Criteria ends with a security check.
AI coding agents executing a step MUST treat the security gate as part of the
step's definition of done, exactly like its tests. This phase adds no secret, no
setting, and no outbound host, but it does three things a careless step could
turn into a leak: it renders every page into screenshots and an audit file, it
records new AI answers with the operator's credential, and it shows the operator
the pages in their own browser. So every screenshot, audit, fixture, recording,
and ledger entry holds only the two public landmarks and the synthetic storm,
captured from demonstration servers in temporary data directories, never from
the operator's service; the recording run reads the credential the way Phase 6's
live eval did, from the operator's user environment into the child process only,
never printing, copying, or committing it, and builds fake keys at run time for
every test; and the redesign keeps every existing guard — the CSP with its
nonce, the same-origin write guard, the coordinate redaction in the console, and
the AI text kept as plain text. No step reads, prints, or quotes the operator's
coordinates, their place, or an assessment of it.

**Deploy-and-verify rule.** Merged is not deployed, and deployed is not
released. Every step header carries a `**Deploys:**` line naming the surface and
environment the step's merge reaches — or `nothing beyond merge` — and when
going live needs a reinstalled copy, a restarted task, a migration, or a tag,
the line says so and this step (or a named follow-on step) owns that event. Only
Step 9 deploys to the operator's machine; Steps 1 to 8 merge to `main`, and the
operator's copy takes all of them at Step 9 (Decision 19). For a step whose
Deploys line names a surface, Stage 4 of the lifecycle does not end at the
squash-merge: the step's acceptance criteria carry a **Deployed & verified**
bullet (`GET http://127.0.0.1:8765/api/health` on the operator's machine answers
from the reinstalled copy with this step's build, and the changed behaviour is
exercised there by the hands-off recipe the step names), and that bullet must be
green before the step is declared complete. No step introduces a required
environment variable or secret. Step 1's recording run spends a few cents of the
operator's Anthropic allowance: it states the request count and the cost ceiling
and runs only after the operator's yes, and no credential value ever transits a
chat, a PR, a log, or a fixture — an agent hands the operator a command to run
rather than asking for a value. A step reinstalls the operator's copy, restarts
`\Weatherbot\serve`, edits the operator's `weatherbot.toml`, spends against the
operator's credential, or opens a page or a window on the operator's desktop
only after the operator says yes to that exact action (AskUserQuestion); an
agent verifies with the public landmarks in a temporary data directory and reads
the operator's service only through `/api/health` and `doctor`. The operator
often reaches this machine from another computer, where a dialog raised on the
Windows desktop may never be seen, so an agent that needs the operator to act
first states the steps in the chat, then asks. See the project roadmap's
"Release & deployment strategy" for the surfaces table, promotion path, and
rollback.

**Triage rule.** Findings surfaced while executing a step are classified before
they are acted on, per the project roadmap's "Defect handling & triage": spec
rot → edit this roadmap's affected `<task>` block now; upstream gap → patch the
earlier step's prompt and add it to the carry-over checklist; implementation bug
→ fix in-step only if it blocks this step's acceptance criteria, otherwise an
issue and its own branch in a fresh conversation; architectural question → an
issue for a future phase; process improvement → recorded where the next
conversation will read it; security finding → jumps the queue by severity;
source drift (a NOAA shape the synthetic storm copies changed) → re-record the
affected source, update `docs/DATA_SOURCES.md` with the date, and add a contract
test in the same PR. A visual or readability defect found while executing a step
is fixed in that step when it is on a page the step owns, and otherwise logged
in `docs/phase08-dogfood.md` with the step that owns the page, so Loop 1 starts
from a list rather than a memory. The OpenAPI document is a contract: a change
to a route or a response model regenerates `docs/api/openapi.json`, the
frontend's generated types, and the exported fixtures in the same PR, and CI
fails while any is stale. A golden that changes is never "fixed" by regenerating
it: an engine or policy change that moves a replay or notification golden needs
the operator's approval in the PR, and this phase changes neither. A step's PR
contains the step plus blocking fixes only, and lists the issues it opened. When
a merged PR auto-closes an issue, the environment check is what earns the close
— reopen or follow up if a gap remains. `docs/phase08-qa-findings.md` is the
rollup: every finding, its class, and the guard added so the class cannot recur.

**Status rule.** Every step carries a `**Status:**` line directly under its `##
Step N — …` heading, before the Goal, and this file on `main` is the ledger of
what is done — never a chat transcript, never a later conversation
reconstructing history from `git log`. The line reads `Not started` when this
roadmap is written and is flipped by the step's OWN pull request: at Stage 3,
right after `gh pr create` returns the PR number, the agent sets it to `Complete
— PR #<n> (<YYYY-MM-DD>)`, appends ` ✅` to the step's heading (`## Step 5 — The
immersive map ✅`) so the completion shows in the rendered preview, the outline,
and the table of contents, sets the step's Summary Table Status cell to
`Complete — PR #<n>`, commits that edit on the step branch, and pushes. The PR
therefore carries its own completion mark, and the roadmap on `main` says a step
is complete exactly when that step's PR merges — never before. This file's
phase-level `**Status:**` line (under the title) and the project roadmap are
marked the same way, in the same commit: Step 1's PR flips both from `Not
started` to `In progress` (the project roadmap's `### Phase 8` line reads `In
progress — phase08-roadmap.md`, and its row in the "Phase Complexity Summary"
table reads `In progress`), and the final step's PR flips both to `Complete — …`
(the project roadmap's with its row in the "Phase Complexity Summary" table and
the header `> **Status:**` line) and appends ` ✅` to this file's `# ` title and
to the project roadmap's `### Phase 8` heading, so the project roadmap shows a
finished phase the way this file shows a finished step. There is no separate
"update the roadmaps" chore: a step whose PR merged without its Status line is a
lifecycle violation, and the next step's Stage 1 (and `/roadmap-step`) refuses
to start until the previous step reads `Complete`. If a post-merge check fails —
a Deployed & verified bullet, an alarm that never fired — the step is NOT
complete despite the merged line; say so, and the `hotfix/` PR that completes it
appends its own number to the line. `grep -n '^\*\*Status:\*\*'` on this file is
the phase's progress report, and the ✅ headings are the same report at a glance.

**Step lifecycle.** Every step in this phase follows the exact same six-stage
lifecycle, in order, with no exceptions. Each stage is a hard checkpoint — if a
stage is skipped, branch protection or the next step's Stage 1 will fail loudly,
and that is the safety net. AI coding agents MUST execute all six stages before
declaring a step complete.

1. **Create the branch.** Before any Read / Edit / Bash, run `git checkout -b
   feature/phase08-step<M>-<slug>` from a clean, up-to-date `main`. The exact
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
   branch (`docs: mark Phase 8 Step <M> complete`), and push — the PR now
   carries its own completion mark, so the roadmap on `main` will say the step
   is complete exactly when the PR merges (Status rule). On the phase's first
   step, the same commit sets this roadmap's phase-level `**Status:**` (under
   its title) and the project roadmap's Phase 8 `**Status:**` to `In progress`;
   on the final step, both to `Complete`, with ` ✅` appended to this roadmap's
   `# ` title and to the project roadmap's `### Phase 8` heading.

4. **Wait for green checks, then squash-merge.** Every required status check
   must report success: the aggregate `gate` check of `ci.yml` (lint, typecheck,
   the test matrix with the coverage floors, the package smoke, the frontend,
   the browser smoke, and the security scan) and the aggregate `phase-verify`
   check (`phase-verify (01)` through `(07)`, and `(08)` from Step 10). If the
   PR goes BEHIND main while waiting, refresh with `gh pr update-branch
   --rebase` — never merge `main` into the branch; `required_linear_history:
   true` enforces rebase. Once every check is green:

   ```sh
   gh pr merge <PR_NUMBER> --squash --delete-branch
   ```

   If this step's `**Deploys:**` line names a surface, the merge is not the
   finish line: run the Deployed & verified check from the acceptance criteria
   against the target environment now (see the Deploy-and-verify rule) before
   declaring the step complete.

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
   <worktree-path>`, then `git worktree prune` — because `git branch -D` refuses
   a branch still checked out in a worktree. Confirm with `git branch -vv` that
   only `main` and any intentional long-lived branches remain locally, and with
   `git worktree list` that only the primary tree remains.

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
   two steps.

---

## Current State (as of Phase 7)

### Design and shell surface

- `frontend/src/index.css` is four lines: the Tailwind import and the
  class-based `dark` variant. There is no token, no type scale, no threat
  palette, and no elevation; each component spells its own classes, and
  `frontend/index.html`'s `<body>` sets `bg-slate-50` and `dark:bg-slate-950`.
  Tailwind 4.3.3 reads its scale from CSS variables, so a `@theme` block can set
  it in one place. The face is the system stack, and
  `frontend/public/theme-init.js` sets the `dark` class from
  `localStorage['weatherbot.theme']` before first paint.
- Type is small by default. Measured in non-test TSX on 2026-11-15: 173
  `text-xs` (12 px), 38 `text-[10px]` or `text-[11px]`, 41 `text-sm` (14 px),
  and 19 `text-base`; the heaviest files are `Dashboard.tsx` (19 `text-xs`),
  `Replay.tsx` (18), `MapView.tsx` (15), and `LocationManager.tsx` (14).
- `frontend/src/app/AppShell.tsx` holds `NAV_ITEMS` (eight `{ to, label, end }`
  entries: Dashboard, Map, Replay, Storms, Alerts, Timeline, Ask, Settings)
  rendered as text links in a four-column grid on phones, a "Live" or
  "Reconnecting…" chip, the Radix `DropdownMenu` theme control
  (`ThemeMenu.tsx`), the stale-monitor banner (`role="alert"`), the footer's
  notice and "Read full disclaimer" link to `/settings#disclaimer`, and the
  Radix `Toast` stack for displayed notifications. It owns the `/api/health`
  query, which the dashboard reads with `enabled: false`.
- `frontend/src/app/ThreatLevelBadge.tsx` holds `describeThreatLevel`, whose
  fallback names are not the engine's (Decision 8), `LEVEL_SVG_CLASSES` for the
  charts, and the badge, which the dashboard renders without the API's label.
  Its colours are emerald, sky, amber, orange, and red.

### Dashboard surface

- `frontend/src/pages/Dashboard.tsx` (741 lines) opens with a "Monitor cycle
  controls" card: the heading, the snapshot's status and age, the next NHC
  product as a UTC time, `Export report` (`data-testid="export-report-all"`,
  shown when any assessment exists), `Check now`, a paragraph explaining the
  export, and the "Include the AI briefing" box. With two or more locations a
  `LocationComparisonStrip` (`data-testid="location-comparison-strip"`) lists
  each location's link, badge, sparkline, and raw rule code. Each
  `LocationLevelCard` is an `<article aria-label={name}>` with an `<h2>` of the
  name, an NWS-coverage pill, the time zone and breakpoint span, the badge, the
  sparkline, a per-location export link, the assessed time, `UnavailableBanner`,
  the toggle note, `LevelSummary` ("Deciding rule:" and the rule id in `<code>`)
  with `EvidenceList`, the evacuation-order switch (`role="switch"`),
  `BriefingPanel` (`region` "AI briefing for {name}"), `OfficialProductList`,
  `ThreatTable`, and the changes since the last assessment. A visually hidden
  live region (`data-testid="level-live-region"`) announces each location's
  level.
- `frontend/src/assessment/` (`LevelSummary`, `EvidenceList`,
  `OfficialProductList`, `ThreatTable`) is shared by the dashboard and `/replay`
  (Phase 7's check 49 requires both to import it). The charts in
  `frontend/src/charts/` are plain SVG with `role="img"`, a `<title>`, and a
  visually hidden table; each container is `relative overflow-hidden`, because a
  hidden table otherwise widened a 360-pixel page (Phase 7, Step 6).
- The API already serves the plain words the redesign needs: each assessment's
  `level` (`number`, `label`, `actions`), `rule`, and `rule_trigger` (the rule's
  sentence). `rule` is typed as a plain string in `docs/api/openapi.json`, so
  the frontend has no generated union of rule ids.

### Map surface

- `frontend/src/map/MapView.tsx` (851 lines) stacks a header card with `Fit`,
  the route errors, the `AdvisorySlider` (when more than one stored advisory
  exists and no replay runs), the replay panel when `/api/health` reads `corpus:
  true` (`data-testid="replay-panel"`, `#replay-storm-select`,
  `#replay-advisory-select`, `replay-not-live-banner`, `Back to live`), the map
  container (`data-testid="leaflet-map-container"`, 280 px tall on phones and
  520 px from `sm`), and beneath it two cards: the layer toggles (`region` "Map
  layer toggles", one checkbox per `LAYER_TOGGLE_ITEMS` entry with its
  unavailable reason, and `wind-probability-controls`) and the legend
  (`MAP_LEGEND_SECTIONS`, `nowcoast-age-note`, `radar-unavailable-banner`,
  `satellite-unavailable-banner`).
- `frontend/src/map/layers.ts` (1,794 lines) defines the twelve `MapLayerKey`s
  as one flat `LAYER_TOGGLE_ITEMS` list (no groups exist yet),
  `DEFAULT_LAYER_VISIBILITY` with the six depth layers off,
  `MAP_LEGEND_SECTIONS`, and the style functions; `useLeafletMap.ts` keeps one
  `L.Map` per container, builds popups and tooltips as DOM nodes, re-fits
  through a `ResizeObserver` (PR #105), and serves a second container as readily
  as the first; `AdvisorySlider.tsx` walks stored advisories.
- `frontend/e2e/map.spec.ts` (Phase 5) drives the replay picker on `/map` (Irma,
  advisory 031) and counts its overlay paths; `layers.spec.ts` and
  `phase7.spec.ts` toggle layers by label and read the slider, the
  stored-advisory banner, and the radar banner.

### Replay surface

- `frontend/src/pages/Replay.tsx` (812 lines) is one column: the header with the
  `Replay storm` and `Replay location` selects, the corpus-disabled and
  no-locations states, the non-dismissible `replay-banner`, the scrubber (play
  and pause, `AdvisorySlider` without its stored banner, `LevelHistoryChart`
  with its active marker, the replay notes), the map section
  (`replay-leaflet-map`, whose wrapper is hidden while the timeline loads, which
  is why `useLeafletMap` observes its size), and `replay-assessment-card` with
  the shared assessment components. A reader scrolls to see the level the map is
  drawing.

### Settings and secondary pages surface

- `frontend/src/pages/Settings.tsx` (455 lines) is one column of eleven cards:
  the header, the file-problem and restart banners, `LocationManager`,
  `NotificationChannels`, `QuietHoursForm`, `AiSettingsSection` (`id="ai"`),
  `RetentionPanel`, the effective-settings table, the hand-written alert ladder
  (`LADDER_RULES`, wrong in order, name, products, and codes — Decision 8), the
  full disclaimer (`id="disclaimer"`), and the bundled licences. The specs reach
  it by `/settings`, `/settings#ai`, and the footer's `/settings#disclaimer`,
  and `phase7.spec.ts` and `screens.spec.ts` read the locations, channels,
  quiet-hours, and retention cards on one page load.
- `frontend/src/pages/Ask.tsx` (326 lines) shows the engine's levels, the
  conversation (`list` "Transcript", `list` "Lookups", `chat-answer`), the
  `About` select, the `Your question` box, and `Ask`. `Storms.tsx` (339),
  `Alerts.tsx` (357), and `Timeline.tsx` (560, with `timeline-location-charts`
  and `timeline-show-older`) are lists of `text-xs` rows that lead with codes
  and UTC times.

### Demonstration and browser-test surface

- `scripts/serve_demo.py` runs `serve`'s monitor and web server in a temporary
  data directory with both public landmarks (`"simulated Miami-Dade"`, polygon
  `forecast`, zone `FLZ173`, inside NWS coverage; `"Parliament Square"`, the
  Nassau landmark, outside it), every request answered by the recordings through
  `respx` and all others refused. Its flags are `--port`, `--corpus`,
  `--roster-interval-minutes`, `--switch-file`, `--ai-replay`, `--ai-cap-usd`,
  `--ai-fail-auth`, and `--retention-days`. The recordings hold one storm,
  Eastern Pacific Hurricane Simon, so both landmarks start at level 1; the
  switch file serves advisory 023 and a synthetic NWS Hurricane Warning for
  `FLZ173` (`scripts/simulate_advisory.py`), which raises the Miami-Dade
  landmark to level 5. `DemoReplay` answers AI requests by kind from
  `tests/fixtures/ai/`, and `scripts/synthetic_surge.py` adds labelled synthetic
  surge features at two decimals. The clock starts at `source_support.NOW`.
- `frontend/playwright.config.ts` starts three demonstration servers — 8799 (the
  smoke's, with a one-minute roster and the switch file), 8800 (a $0.001 cap),
  and 8801 (a refused credential) — and runs one worker with `@idle` excluded.
  `frontend/e2e/guard.ts` serves OpenStreetMap and nowCOAST requests a local
  blank PNG and fails any other origin, any page error, any CSP violation, and
  any console message holding a landmark's coordinates or a recorded AI
  sentence; it does not fail a console error or an HTTP status, which a spec
  that cares asserts itself. Eleven specs exist (`ai`, `charts`, `dashboard`,
  `idle`, `layers`, `locations`, `map`, `phase7`, `replay`, `report`,
  `screens`); the default run of ten took 59 to 66 seconds in CI's `browser` job
  (15-minute bound) on 2026-11-13. `screens.spec.ts` saves the dashboard, map,
  replay, and settings pages at 1280×800 and 360×740 in both themes, which the
  job uploads.
- `scripts/measure_idle.py` starts `serve_demo.py` at production intervals with
  retention on, runs `idle.spec.ts` (which opens `/`) over a 600-second window,
  and fails at 0.5 percent of a core for either side; the last receipt read
  server 0.2656 and tab 0.0024 percent (2026-11-12).

### API and vocabulary surface

- The engine's vocabulary lives in three places the frontend cannot read:
  `AlertLevel`'s labels and actions (`models/ladder.py`), `RULES`
  (`engine/rules.py`: id, sentence, sources, in evaluation order), and the
  products the ladder reads (`engine/official.py`'s four `LADDER_EVENTS` by
  exact NWS event name and four `LADDER_CODES`, `HWR`, `TWR`, `HWA`, and `TWA`).
  `scripts/export_ladder.py` writes `docs/ALERT-LADDER.md` from them, and
  `services/assessments.py` maps each rule id to its sentence. No route serves
  the ladder.
- `src/weatherbot/web/` follows one pattern per read: a service function, a sync
  `def` route, a response model in `schemas.py`, a fixture from
  `scripts/export_api_fixtures.py` (checked by `tests/web/test_api_fixtures.py`
  and `--check`), an entry in `tests/web/test_api_privacy.py`, and a query key
  in `frontend/src/api/keys.ts`. `services/disclaimer.py` and
  `web/routes/disclaimer.py` are the closest precedent for static reference
  data.

### Security & sensitive-data surface

- The CSP allows `style-src 'self'` with a per-answer nonce and no
  `unsafe-inline`, and `img-src` the OpenStreetMap and nowCOAST hosts
  (`web/guards.py`'s `CSP_SUFFIX`); no tracked file under `frontend/src` holds a
  `style=` attribute (Phase 7's check 44), `innerHTML`, or
  `dangerouslySetInnerHTML` (Phase 6's check 38, which reads test files too);
  Leaflet popups are DOM nodes; AI text is rendered as plain text; and the guard
  fails a console message holding a coordinate.
  `scripts/check_personal_data.py`'s R2 refuses a coordinate pair at three or
  more decimals in tracked text outside `tests/fixtures/recorded` and
  `tests/fixtures/replay`, so synthetic geometry is written at two. Keys are
  built at run time in tests (Phase 1's check 29), and `tests/conftest.py`
  deletes every `ANTHROPIC_*` and `WEATHERBOT_*` variable.
- This phase handles no new class of data. What it adds that could leak is
  evidence: screenshots, an audit file, a ledger, and recordings, all made from
  demonstration servers that hold only the public landmarks and the synthetic
  storm.

### Operations & observability surface

- `/api/health` reports the version, the schema head (`0010`), the scheduler,
  the heartbeats, `stale`, `next_product_at`, `corpus`, the AI block, and
  `ui.index_sha256` (the first twelve hex digits of the built `index.html`),
  which is how a Deployed & verified check tells one interface build from the
  next. The interface is where four alarms reach the operator: the stale-monitor
  banner, the reconnecting chip, `AiStateBanner`, and the radar and satellite
  unavailable banners, plus the notification toasts. A redesign that loses one
  of them silences an alarm, so each must be seen to fire in the new shell (Step
  8).
- The operator's service runs under `\Weatherbot\serve` from
  `C:\Users\Admin\.local\bin\weatherbot.exe`, with `\Weatherbot\check` as the
  hourly fallback at HH:25; bare `weatherbot` on `PATH` is version 1. A deploy
  is `schtasks /End`, `npm ci` and the build, `uv tool install --reinstall
  --from <checkout> weatherbot`, and `/Run`. The operator's copy last deployed
  Phase 7 (`ui.index_sha256` `79fabd1a5019`, 2026-11-10).

### Documentation surface

- `README.md`'s `## Status` still says "Phase 8 (Release 2.0) is next", which PR
  #108 made wrong; Phase 7's check 59 pins that exact text and `CHANGELOG.md`'s
  `### Phase 7 — Depth`. `docs/ALERT-LADDER.md`, `docs/AI.md`,
  `docs/NOTIFICATIONS.md`, `docs/DATA_SOURCES.md`, and `CONTRIBUTING.md`
  describe behaviour this phase keeps. No document describes the design system,
  and no rubric says what a good page is.

### Verification surfaces

- `scripts/verify_phase07.py` is the structural template: 65 standard-library
  static checks, eight mutually exclusive modes (`--fast`, `--py`, `--node`,
  `--ui`, `--live`, `--security`, `--all`, `--post`), and 42 V rows built from
  JUnit evidence in which every selection must match a test, a failure fails,
  and a skip is never a pass; lines read `[PASS] 01: description (detail)` and
  the summary block `passed`, `failed`, `skipped`, `total`, exiting 0 only with
  none failed or skipped. Its `--post` runs the static checks, the node, Python,
  Playwright, live, and security suites, then the probes (`phase_verify_ci`,
  `protection_requires_both`, `verify_phase06_post`, the operator's locations,
  `doctor` and ntfy, health at head with the corpus, `measure_idle_probe`, and
  the `--fast` budget), then the matrix. It nests Phase 6's `--post` through
  `capture([... "scripts/verify_phase06.py", "--post"], timeout=14400,
  env=_operator_secret_env())`, reads its totals with `^
  (passed|failed|skipped|total)\s+(\d+)$`, and passes only at
  `EXPECTED_PHASE_06_POST_TOTAL` `"79"` with nothing failed or skipped. The
  totals 75, 73, 80, 80, 85, 79, and 107 are pinned by each phase's test file
  and by the next phase's `--post`, so Phase 8 asserts 107.
- Each of Phases 5 to 7's `--post` reruns the frontend suites and a 600-second
  idle window, so Phase 8's `--post` will run Vitest and Playwright four times
  and the idle window four times; no ledger records how long a nested sweep
  takes, so Step 10 measures it and sets its own nested timeout above Phase 7's.
- `.github/workflows/phase-verify.yml`'s `verify` job holds the one-line matrix
  `phase: ["01", "02", "03", "04", "05", "06", "07"]`, which Phase 1's check 50
  and Phase 7's check 64 read on one line; separate Node steps under the literal
  conditions `matrix.phase == '05'`, `'06'`, and `'07'` (`Set up Node`, `Set up
  Node (Phase 6)`, `Set up Node (Phase 7)` and their install steps, each
  `actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 # v7.1.0`), which
  Phases 5 to 7 read verbatim; and one `--security` step. Step 10 appends `"08"`
  at the end of the line and adds its own pair of Node steps, touching none of
  the others.
- How the verifiers select tests: the JUnit key is `classname.name`, a Vitest
  classname is the path under `frontend/` and a Playwright one the spec's path
  under `e2e/`, and every frontend selection in every verifier names a file,
  never a title. A selected file must keep its path and hold at least one test,
  all passing and none skipped. The catch-all rows (the whole Vitest run, the
  whole Playwright run, and pytest) make every other test required too,
  including `Replay.test.tsx`, `charts.spec.ts`, and every new Phase 8 test.
- Checks of the earlier phases that this phase's work could turn red, and how
  each stays green:

| Check | Reads | How Phase 8 keeps it green |
| ----- | ----- | -------------------------- |
| P1 3, 4 | `CHANGELOG.md` | one `[Unreleased]`; 1.0.0 lines kept |
| P1 6 | the ROADMAP's Phase 1 row | row kept |
| P1 10 | v1's deleted paths | no `docs/user-guide.md` and the like |
| P1 25, P5 33 | action pins | new Node steps pinned `# v7.1.0` |
| P1 29, P6 51, P7 65 | key shapes in text | fake keys built at run time |
| P1 41 | no tracked `reports/` | ledger lives in `docs/` |
| P1 50, P7 64 | one-line matrix | append `"08"`; new Node steps |
| P2 41, P3 47, P6 45, P7 55 | `## Commands` needles | kept |
| P2 43, P5 53 | the `--security` step | untouched |
| P3 8 | unique test basenames | every new name checked |
| P4 38 | `simulate_advisory.py` names | not refactored |
| P5 26, 27 | exact pins, npm scripts | no package; scripts kept |
| P5 30, 37, P6 38 | text under `frontend/src` | no binary; no `innerHTML` |
| P5 31 | `index.html` | no inline script or style; root div |
| P5 36, 41, 43, P6 36 | page, map, AI file paths | none moved |
| P5 39 | `new Notification(` | only `notify.ts` |
| P5 45, P6 42 | specs, ports 8799–8801 | kept; 8802–8806 added |
| P5 47 | `### The dashboard` | heading kept |
| P5 52, P6 50 | `'05'`, `'06'` Node steps | untouched |
| P6 37, 41 | `keys.ts`, `serve_demo.py` | literals and names kept |
| P6 39, P7 43 | package names | no package added |
| P6 40, P7 48 | `NAV_ITEMS` literals | one object a line, same order |
| P7 12, 23, 32, 38, 42 | settings, slider, charts files | none moved |
| P7 13, 40, 50, 54, 56 | Phase 7 specs | paths kept |
| P7 35 | `CSP_SUFFIX` | unchanged |
| P7 36 | layer defaults | twelve literals kept |
| P7 37 | `setInterval` under `src/map` | countdown lives elsewhere |
| P7 44 | `style=`, tests included | none added |
| P7 45 | `QUERY_KEYS`, charts key | unchanged; ladder key nests |
| P7 49 | four names in two pages | composed as children |
| P7 57 | `measure_idle.py` literals | kept |
| P7 59 | README's Status | read at the tag (Step 1) |

- V rows whose selected files this phase must rewrite while keeping their paths:
  Phase 5's V4.2 (`AppShell.test.tsx`, which asserts the navigation links' text
  is exactly the eight labels, a `Dashboard` heading, and the
  `/settings#disclaimer` link), V5.2 (the five page tests), V5.4
  (`screens.spec.ts`, which wants four Settings headings at once), V6.2
  (`MapView.test.tsx`, whose replay-panel case goes), V6.3 (`map.spec.ts`,
  rewritten in place), and V7.2 (`dashboard.spec.ts`); Phase 6's V5.2 (the AI
  files, `Ask.test.tsx`, which counts "Level 1" twice, and
  `BriefingPanel.test.tsx`, which counts level-4 headings), V5.3
  (`AiText.test.tsx`, which expects `whitespace-pre-line`), and V6.2
  (`ai.spec.ts`, whose refused-credential case checks both briefing panels on
  `/` at once); and Phase 7's V2.4 (`locations.spec.ts`, so Locations is the
  default tab), V5.3 and V5.4 (`AdvisorySlider.test.tsx` and `layers.spec.ts`,
  which need the layer panel open at the default 1280×720 viewport), V6.3 and
  V7.2 (the chart and assessment tests' `[style]` assertions), V6.4 and V9.2
  (`phase7.spec.ts`, which reads every Settings card on one load and
  `export-report-all` on `/`), V7.4 (`replay.spec.ts`), and V8.4
  (`report.spec.ts`, which needs Parliament Square's briefing panel and the AI
  box). The operator probes need the operator's service on the checkout's final
  build (Phase 5's V7.4 compares `ui.index_sha256`) and a settled briefing among
  its last 100 AI calls (Phase 6's V6.5). Phases 1 to 3's branch probes need
  every check on a pull request to pass, so no new job may be skipped on one.
- Pinned tests no verifier names (or that a catch-all row requires), each
  updated in the step that touches it: `tests/ai/test_ai_fixtures.py` (every
  manifest entry a case of `record_ai_fixtures.all_cases()` with its kind, and
  the directory under `BUDGET_BYTES`, 1 MiB; Phase 6's V5.2 selects it; Step 1),
  `frontend/src/app/AppShell.test.tsx` (an exact `<h1>` for each of the eight
  routes; every step), `tests/scripts/test_serve_demo.py` (the imports, the
  defaults, the exact TOML, and the replay kinds; Step 1),
  `tests/scripts/test_measure_idle.py` (the printed-line parsing),
  `tests/web/test_api_fixtures.py` (`is_stale()` false; a new fixture is
  tolerated; Step 3), `frontend/src/map/layers.test.ts` (`MAP_LEGEND_SECTIONS`'
  twelve categories, their counts, and NHC's colours, so the legend filters at
  render and keeps its data; Step 5), `Dashboard.test.tsx` (the strip's two
  sparklines and the live region's "Decided by all_clear." text; Step 4),
  `Settings.test.tsx` (four AI rows and no `[style]`; Step 7), `Storms.test.tsx`
  (six credits and five "Interpret (AI)" buttons; Step 7), `charts.spec.ts` (the
  strip, `#location-simulated-miami-dade`, and no overflow at 360 px; Step 4),
  and `map.spec.ts`'s marker paths (`a8,8` twice, at least five points, the
  cone's and track's colours; Step 5).
- Demonstration traps: a request the `respx` router does not match raises
  `AllMockedAssertionError`, an `AssertionError` that neither the fetcher nor
  the snapshot's guard catches, so an unstaged URL crashes a cycle instead of
  failing a source; and `_install_demo_instrumentation` makes the second
  `MonitorSchedule` a process builds skip its startup cycle, so anything that
  runs extra cycles before the server binds calls `MonitorService.run_cycle`
  directly.
- Playwright traps: specs run alphabetically on one worker against the shared
  8799 server, whose switch-file state outlives `dashboard.spec.ts` and
  `layers.spec.ts`, so a new spec must not depend on that server's level or
  leave a location or setting behind (`screens.spec.ts` expects exactly the two
  landmarks); no new spec is tagged `@idle`; no spec uses `toHaveScreenshot`
  baselines, because Windows and Linux render pixels differently; and no
  Playwright project re-runs the old specs at another width.

### Carry-over from Phase 7

Every item an earlier phase handed to this one, and where it lands. Phase 7's
roadmap and ledger were written before PR #108 renumbered the phases, so the
items they hand to "Phase 8 (Release 2.0)" belong to Phase 9 now:

| Item | Source | Lands in |
| ---- | ------ | -------- |
| P7 check 59 (`README.md` `## Status`) | P7 QA ledger | Step 1 |
| `README.md` names Phase 8 wrongly | PR #108 | Step 1 |
| Command-center UI, type, hierarchy | PR #108, ROADMAP 8.1–8.2 | Steps 2–7 |
| Level 1–5 demonstration states | PR #108, ROADMAP 8.3 | Step 1 |
| AI and operator dogfood loops | PR #108, ROADMAP 8.3 | Steps 8, 9 |
| Wrong ladder on the Settings page | this roadmap | Step 3 |
| Badge names not the engine's | this roadmap | Step 3 |
| `v2.0.0-phase-8` in "Release & tagging" | this roadmap | this PR |
| LAN mode, fresh-install smoke, 2.0.0 | P7 ledger item 1 | Phase 9 |
| Shipping the replay corpus | P7 Decision 17 | Phase 9 |
| Issue #95 (live surge capture) | P7 ledger | its issue |
| Issue #33 (surge, extreme wind) | P5–P7 ledgers | the operator |
| Issue #79 (`minimatch`, dev tooling) | P6, P7 ledgers | its issue |
| Dependabot PRs and the `PATH` shadow | P7 ledger | maintenance |

---

## Execution Order

```
Step 1  (scenarios)                       synthetic Atlantic storm + five
                                          scenarios + recorded briefings
                                          + README Status (P7 check 59)
                                          → implement
  ↓
Step 2  (design system + type)            tokens + ui/ primitives + icon
                                          nav + every page's type +
                                          DESIGN.md + readability gate
                                          → implement
  ↓
Step 3  (plain English + vocabulary)      GET /api/ladder + threat/
                                          vocabulary + meter + hero +
                                          provenance disclosure
                                          → implement
  ↓
Step 4  (command-center dashboard)        status bar + countdown + export
                                          popover + switcher cards + tiles
                                          + mini-map
                                          → implement
  ↓
Step 5  (immersive map)                   tall canvas + floating panels +
                                          no replay panel on /map
                                          → implement
  ↓
Step 6  (replay workbench)                side-by-side map, scrubber, chart,
                                          and hero
                                          → implement
  ↓
Step 7  (settings + secondary pages)      five tabs + deep links + Ask
                                          chips + Storms, Alerts, Timeline
                                          → implement
  ↓
Step 8  (loop 1: AI dogfood)              dogfood harness + rubric + ledger
                                          + rounds to clean + idle + alarms
                                          → implement
  ↓
Step 9  (loop 2: operator dogfood)        walkthroughs to sign-off +
                                          the operator's service upgraded
                                          → operate
  ↓
Step 10 (QA + verify_phase08.py)          scripts/verify_phase08.py
                                          + docs/phase08-qa-findings.md
                                          + phase-verify.yml entry "08"
                                          → create

--- post-implementation ---

V1  Every scenario starts offline and reads its declared levels
    and rules; the landfall briefing passes its validators.
V2  No small type remains; the readability gate passes on every
    route at three viewports; the navigation reads its badges.
V3  The ladder route equals the engine; headlines hold no code;
    the disclosure holds all provenance and the switch.
V4  The dashboard's bar, popover, switcher, tiles, briefing, and
    mini-map work, with no new poll.
V5  The map floats its panels over a tall canvas; no replay
    panel remains on /map.
V6  Replay shows map, scrubber, and headline together at
    1440×900, from the same hero as the dashboard.
V7  Each Settings tab opens from a link; chips fill, never send;
    the three lists lead with words.
V8  A full dogfood round is clean; idle holds; every alarm shows
    in the new shell.
V9  The operator signed off; the operator's service runs the
    redesigned build.
V10 verify_phase08.py --fast and --security exit 0 in
    phase-verify (08); the phase is closed.
```

Steps are sequential by dependency. Step 1 comes first because every later step
must look at all five levels, and the readability gate in Step 2 runs on Step
1's `quiet` and `landfall` servers. Step 2's tokens and primitives are what
every later page is built from, and its gate is what keeps every later step from
shrinking the type again. Step 3's vocabulary, hero, and disclosure are the
components the dashboard (Step 4) and the replay page (Step 6) compose, and its
ladder route is what the Settings tab (Step 7) renders. Step 5's floating panels
are the pattern Step 6 reuses around its own map. Steps 2 to 7 all edit
`frontend/src/`, the e2e specs, and the exported fixtures, and Steps 3 and 7 the
same Settings page, so this phase draws no steps in parallel, and the Worktree
rule permits no concurrent steps. Step 8 judges every page Steps 2 to 7 built,
Step 9 needs Step 8's clean round before the operator's time is spent, and Step
10 verifies every prior step.

---

## Step 1 — Demonstration scenarios

**Status:** Not started

> **Goal:** Put every level on screen while the real tropics are quiet.
> `scripts/demo_storm.py` builds a synthetic Atlantic storm, in the live feeds'
> own formats and at two decimals, labelled synthetic in its own fields;
> `scripts/demo_scenarios.py` declares the five scenarios of Decision 2's table
> — the staged answers each one serves and the level and deciding rule each
> landmark must read — and seeds the landfall scenario's history;
> `scripts/serve_demo.py --scenario NAME` serves one through the real fetch,
> engine, storage, API, and event path, while the default demonstration stays
> byte-for-byte what it was; `scripts/record_ai_fixtures.py --scenario` records
> each scenario's briefings and the landfall escalation summaries live, once,
> after the operator's yes, and `DemoReplay` answers by scenario and landmark;
> `frontend/playwright.config.ts` starts the `quiet` and `landfall` servers
> beside its three, and `frontend/e2e/scenarios.spec.ts` proves both render;
> `tests/scripts/test_demo_scenarios.py` asserts every scenario's levels, rules,
> completeness, offline run, and synthetic geometry; and `README.md`'s status
> names the phases as PR #108 renumbered them, with Phase 7's check 59 moved to
> its tag. This step flips the phase to In progress.

**Branch:** `feature/phase08-step1-scenarios`

**Deploys:** nothing beyond merge — the scenarios are a development and test
tool that no installed copy runs. The recording run spends at most $0.60 of the
operator's Anthropic allowance, once, after the operator's yes.

Settings — ladder (`roadmodel ladder --category coding --complexity high
--novel`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **Gemini 4 Argon** | **Opus 5.5**       | **Opus 5.5**       |
|               | Platform | Antigravity        | Claude Code        | Claude Code        |
|               | Level    | High               | High               | XHigh              |
|               | AA       | 52.6               | 53.6               | 56                 |
|               | Price    | $6.13/1M           | $6.76/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **Opus 5.5**       | **Gemini 4 Argon** | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Antigravity        | Antigravity        |
|               | Level    | Medium             | Medium             | High               |
|               | AA       | 51.2               | ≈49.8              | 52.6               |
|               | Price    | $6.39/1M           | $2.37/1M           | $6.13/1M           |
| **Backup**    | Model    | **GPT-6 Astra**    | **GPT-6 Astra**    | **GPT-6 Astra**    |
|               | Platform | Codex              | Codex              | Codex              |
|               | Level    | Medium             | High               | XHigh              |
|               | AA       | 49.6               | 50.9               | 52.4               |
|               | Price    | $11.85/1M          | $13.01/1M          | $17.73/1M          |

Ranked for coding, high complexity, novel. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level. ≈
estimated from the model's measured levels or its previous version's.

**Conversation:** New

**Model rationale:** Step 1 is coding with a knowledge secondary category — a
synthetic storm that must pass the live parsers' strict field contracts and
drive the engine's rules to named outcomes, five staged scenarios, a seeded
history, a recorder extension, and a replay mapping — at High complexity and
novel: no earlier step built a storm, and each scenario's level must come from
the real rules, never from a stub. On the step alone, the Quality Pick fits
best: Opus 5.5 on Claude Code at Effort XHigh, funded by the claude.ai Max
subscription (it always thinks, so there is no Thinking dial), gives the deepest
reading of how a cone's extent, a segment's reach, and a forecast point's
intensity decide a rule. The Balanced Pick, the same model at High, brings less
depth to the hardest part, the staging; the Cost Pick, Gemini 4 Argon at High on
Antigravity, trades some of that reasoning for price. The conversation is new,
per phase-boundary hygiene.

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
       feature/phase08-step1-scenarios`
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
       Phase 8 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 8`
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

    THIS STEP adds data, not surface: every synthetic coordinate is
    written at two decimals (the personal-data rule's R2 refuses
    three-decimal pairs outside the recorded trees), every synthetic
    answer says it is synthetic in its own fields as
    `scripts/synthetic_surge.py` does, and the storm's name says it is a
    demonstration, never a real or retired name; no `SourceId`, register
    row, or `src/` file changes. The scenarios run behind `respx` with
    every unmatched request refused, so none can reach the network, and
    `serve_demo.py` still deletes every `ANTHROPIC_*` variable and
    points the SDK's profile at an empty directory. The recording run is
    the one place a credential is used: it reads `ANTHROPIC_API_KEY`
    from the operator's user environment into the child process only, as
    Phase 6's live eval did, never prints, logs, copies, or commits it,
    and stops without one. Each new recording is scanned before commit:
    it holds the landmarks' names, levels, bands, compass points, hours,
    and the synthetic storm, never a coordinate or a URL (the AI context
    never carries one), and gitleaks and the personal-data check pass
    over it.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 8 (UI/UX redesign and visual
    dogfooding). Step 1: demonstration scenarios.

    Current state (as of Phase 7):

    - `scripts/serve_demo.py` serves the two public landmarks
      (`"simulated Miami-Dade"`, polygon `forecast`, zone `FLZ173`;
      `"Parliament Square"`, the Nassau landmark, outside NWS coverage)
      from the recordings through `recorded_services()`, whose router
      refuses any unmatched request by raising `AllMockedAssertionError`
      (an `AssertionError`: the fetcher catches only
      `httpx.TransportError` and the snapshot's guard only
      `SourceError`, so an unstaged URL crashes the cycle). The
      recordings hold one storm, Eastern Pacific Hurricane Simon
      (`ep202026`, bin `EP5`), so both landmarks read level 1.
      `--switch-file` serves `next_advisory_roster()` and
      `hurricane_warning_response()` from
      `scripts/simulate_advisory.py`, which raises the Miami-Dade
      landmark to level 5. The clock starts at `source_support.NOW`
      (2026-10-13 01:30 UTC) and advances with the wall clock.
      `_install_demo_instrumentation` makes the second `MonitorSchedule`
      a process builds skip its startup cycle.
    - `AssessmentService` refuses a replay snapshot, and the archive's
      geometry is on a 6,371,200 m sphere that must never be relabelled
      as WGS 84 (Decision 2), so a scenario cannot borrow a replayed
      advisory: its storm is synthetic, in live formats.
    - What a live cycle fetches for a storm (`services/snapshots.py`):
      the roster (`nhc_current_storms.py`), the tropical weather summary
      service's catalog and layers through
      `nhc_map.fetch_storm_products` (queried `where=1=1` and told apart
      by `binnumber`; the recorded templates are
      `tests/fixtures/recorded/nhc-map-tropical-summary/`'s
      `query-forecast-cone.geojson`, `query-forecast-track.geojson`,
      `query-forecast-points.geojson`,
      `query-advisory-wind-field.geojson`,
      `query-earliest-reasonable-arrival-time.geojson`, and the rest of
      that directory), the watch-warning breakpoints
      (`nhc-map-breakpoints/`), the wind-speed probabilities, the
      arrival-time KMZs the roster links (`nhc-arrival-times/`), and
      each storm's TCP list and product by its slot
      (`/products/types/TCP/locations/<slot>`; only `EP5` is recorded,
      in `nhc-text-products/`). The per-bin `nhc-map-tropical-weather/`
      files are not fetched by a cycle. NWS alerts come from
      `nws-alerts-point/` and `nws-alerts-zone/`; the newest recorded
      answers (2026-10-17) hold a Rip Current Statement.
    - What makes an assessment complete (`engine/assess.py`, `cones.py`,
      `threats.py`): the roster and summary sources answered, the
      in-coverage landmark's alert lists answered, a usable cone for
      every storm, and forecast points and both arrival kinds for every
      storm.
    - `Provenance.source_id` is the closed `SourceId` literal of
      register ids (`models/provenance.py`), stamped by the fetcher from
      each source module; `scripts/synthetic_surge.py` keeps
      `source_id="nhc-map-peak-surge"` and marks its features synthetic
      in their own fields (`snippet`, `popupinfo`'s `"synthetic":
      true`).
    - The ladder's thresholds (`models/ladder.py`'s `Thresholds`): a
      segment covers within `coastal_reach_km` (25 km), `cone_horizon_h`
      120, `hurricane_wind_floor_pct` 10,
      `tropical_storm_wind_floor_pct` 5, and
      `development_chance_floor_pct` 0 (any seven-day region).
      `engine/official.py` reads four NWS events by exact name and the
      codes `HWR`, `TWR`, `HWA`, `TWA`.
    - `DemoReplay` answers a briefing by the landmark its request names,
      every summary with one Irma recording, every chat turn with
      `chat-one-round`, and narrations by basin; the validators withhold
      an answer whose sources or level do not match the demonstration's
      context (`validate_summary` allows only a summary's own two
      levels). `scripts/record_ai_fixtures.py` records the eval set's
      cases from replay contexts; `tests/ai/test_ai_fixtures.py`
      requires every manifest entry to be a case of its `all_cases()`
      with that case's kind, and the directory to stay under
      `BUDGET_BYTES` (1 MiB; 489,508 bytes on 2026-11-15). `serve`'s
      `ChangeSummarizer` primes at start to the newest stored assessment
      and never backfills (`services/ai/summaries.py`).
    - `README.md`'s `## Status` says "Phase 8 (Release 2.0) is next";
      `scripts/verify_phase07.py`'s check 59 requires "Phase 7 (depth)
      are complete" and "Phase 8 (Release 2.0) is" in the live section
      and `### Phase 7 — Depth` in `CHANGELOG.md`; no mutation case in
      `tests/test_phase07_verification.py` touches it yet, and its
      `tagged` defaults to the Phase 6 tag.

    Files to read (every file before drafting):

    - docs/roadmap/phase08-roadmap.md (Decisions 1 to 3 and 16, the
      scenario table, the Verification surfaces audit, and this step).
    - scripts/serve_demo.py, simulate_advisory.py, synthetic_surge.py,
      record_ai_fixtures.py, and export_api_fixtures.py, with their
      tests in tests/scripts/ and tests/ai/test_ai_fixtures.py.
    - tests/cli/cli_support.py, tests/sources/source_support.py,
      tests/contract/fixture_support.py, and tests/ai/ai_support.py.
    - src/weatherbot/services/snapshots.py, and the parsers in
      src/weatherbot/sources/ for every source above
      (`nhc_current_storms.py`, `nhc_map.py`, `nhc_arrival_times.py`,
      `nhc_text_products.py`, `nws.py`), with docs/DATA_SOURCES.md's
      section for each and the recorded captures named above.
    - src/weatherbot/engine/assess.py, rules.py, official.py, cones.py,
      threats.py, breakpoints.py, and models/ladder.py and
      models/provenance.py.
    - src/weatherbot/services/assessments.py and services/monitor.py
      (how a cycle stores a snapshot and assessments), and
      services/ai/summaries.py and services/ai/briefing.py (how a
      summary and a briefing are written and validated).
    - frontend/playwright.config.ts and frontend/e2e/guard.ts.
    - scripts/verify_phase07.py (check 59 and `tagged`),
      tests/test_phase07_verification.py, README.md, and CHANGELOG.md.
  </context>

  <goal>
    Build the synthetic storm and the five scenarios, serve each through
    the real pipeline, record their AI answers once, prove the two
    browser servers render, and correct the README's phase names with
    check 59 converted.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `scripts/demo_storm.py` builds, for a given stage, every answer a
      live cycle requests for one Atlantic storm in an Atlantic slot no
      recording uses (such as `AT1`): the roster entry with its product
      links; the summary service's catalog and layer answers with the
      storm's features (`binnumber` set to the slot) — the forecast
      cone, the track, the forecast points (each with its intensity, so
      the cone rules can tell a tropical storm from a hurricane at a
      landmark's closest approach), the advisory wind field and forecast
      wind radii, and the arrival-time layers; the watch-warning
      breakpoints with their `tcww` codes; the wind-speed probability
      bands for 34, 50, and 64 kt; the two 34-kt arrival-time KMZs at
      the URLs the roster names; and the slot's TCP list and product.
      Every URL the cycle requests for the storm is staged, because an
      unstaged one crashes the cycle (context). Each answer starts from
      its recorded template's field shapes, so the parsers' declared
      field lists are satisfied, and carries new geometry at two
      decimals and a synthetic label in its own fields — a `snippet` or
      description note and `"synthetic": true` where the format has a
      free field, the TCP's text, the storm's name — while the fetcher
      stamps the register's `source_id` as usual. The storm's name says
      it is a demonstration. The track runs from the southeast past the
      Nassau landmark toward the Miami-Dade landmark, so one storm
      explains every scenario's map.
    </requirement>

    <requirement>
      `scripts/demo_scenarios.py` declares `SCENARIOS`, the five of
      Decision 2's table, each with its staged answers and its
      expectation — the level and deciding rule for each landmark,
      exactly as the table states, in a literal that Step 10's verifier
      reads by AST. Each scenario stages the roster, the storm's
      answers, the outlook layer (empty in `quiet`, one synthetic
      seven-day region over both landmarks in `outlook`), and the NWS
      alert answers for every query the Miami-Dade landmark makes (its
      point, its forecast zone `FLZ173`, and its county zone), built by
      its own generator for the four ladder events on
      `register_alert()`'s shape — `scripts/simulate_advisory.py` is not
      refactored, because Phase 4's check 38 and
      `tests/scripts/test_simulate_advisory.py` pin its
      `SIMULATED_MIAMI`, `main`, `TemporaryDirectory`,
      `recorded_services()`, and `run_simulation`. In `cone`, any 64-kt
      band at the Nassau landmark stays below the 10 percent floor, or
      `hurricane_wind_probability` would outrank `storm_cone`.
      `landfall` also declares its seeded history: the `outlook`,
      `cone`, and `watch` stages as earlier advisories, each a cycle run
      through `MonitorService.run_cycle` (never a second
      `MonitorSchedule`, which the instrumentation would make skip its
      startup cycle) at an earlier demo instant with an existing trigger
      (`roster`; `CycleTrigger` and Phase 4's check 8 fix the nine
      kinds), stored before the web server binds, so the landmarks'
      sparklines and timelines advance one stage at a time and the
      escalation notifications exist. Because `ChangeSummarizer` never
      backfills, the seeding itself writes each landmark's last
      escalation summary through `ChangeSummaryService` and the replayed
      transport, and every scenario stores each landmark's briefing
      through `BriefingService` after its last assessment the same way,
      so the briefing card and the summaries show on first load; `Brief
      me` still replays on demand.
    </requirement>

    <requirement>
      `scripts/serve_demo.py` gains `--scenario
      {quiet,outlook,cone,watch,landfall}`; without it the server is the
      default demonstration, byte-for-byte, so its switch file, its
      three servers, and every Phase 5 to Phase 7 spec keep working. A
      scenario server runs the scenario's history, then its startup
      cycle, before it binds, at production roster intervals unless
      `--roster-interval-minutes` says otherwise, and keeps serving the
      scenario's staged answers on every later fetch, so `Check now` and
      a roster poll reproduce the same levels. `--scenario` and
      `--switch-file` together exit 2 with a message. Keep every
      existing flag, default, and printed line (`pid=… address=…`,
      `roster_poll at=…`, `cycle id=…`), which `measure_idle.py` and the
      Phase 6 checks read: `_parse_args([])` still returns today's
      defaults with `scenario` `None`, `_configure_demo_environ` writes
      no `weatherbot.toml` unless `--retention-days` is given and then
      exactly `[retention]\nhistory_days = N\n`, and `DemoReplay`,
      `request_kind`, `chat_round`, `demo_claude`, `REPLAYED_BRIEFINGS`,
      `REPLAYED_SUMMARY`, and `REPLAYED_CHAT` stay defined in
      `serve_demo.py` itself (Phase 6's check 41 reads top-level
      definitions, not imports), so the scenario logic it needs is
      imported from `demo_scenarios.py` while those names stay put.
    </requirement>

    <requirement>
      AI (Decision 3): `scripts/record_ai_fixtures.py --scenario NAME`
      (and `--scenario all`) builds the scenario's database through the
      same code the server uses, then records, through the real services
      and the live API, one briefing per landmark and, for `landfall`,
      each landmark's escalation summary — twelve requests for `all`.
      Before any request it refuses without a credential, prints the
      request count and the ceiling (at most $0.60 at the list prices
      `services/ai/` holds), and asks; the agent runs it only after the
      operator's yes, with the credential read into the child process as
      Phase 6's recipe did. Recordings land in `tests/fixtures/ai/` as
      `scenario-<name>-<landmark>` files with manifest entries, each
      registered as a case in `all_cases()` (`stream` for a briefing,
      `parse` for a summary), within `BUDGET_BYTES`; `DemoReplay`
      answers a scenario server's briefing by scenario and landmark and
      its summary by scenario and landmark, falling back to today's
      mapping for the default server. If the operator declines, stop and
      record the decision in this roadmap in this PR: the scenarios keep
      the withheld state, the landfall test asserts `withheld`, and Step
      10's check 6 expects no scenario recording.
    </requirement>

    <requirement>
      Browser: `frontend/playwright.config.ts` adds two servers,
      `--scenario quiet --port 8802` and `--scenario landfall --port
      8806`, beside 8799, 8800, and 8801, with environment overrides
      like the others' (`E2E_QUIET_PORT`, `E2E_LANDFALL_PORT`); 8803 to
      8805 are reserved for Step 8's harness and not started here.
      `frontend/e2e/scenarios.spec.ts` opens each server's dashboard
      (`test.use({ baseURL })`, so the guard follows) and asserts the
      two landmarks' headings and levels (`landfall`: level 5 for the
      Miami-Dade landmark and level 4 for the Nassau one; `quiet`: level
      1 for both) and `/map` drawing the storm's cone on `landfall`; it
      records console errors itself and asserts none, because the guard
      fails only foreign requests, page errors, CSP events, and leaked
      coordinates or AI text.
    </requirement>

    <requirement>
      Tests: `tests/scripts/test_demo_scenarios.py` runs every scenario
      in a temporary data directory and asserts each landmark's stored
      level and rule against `SCENARIOS`, that every assessment is
      complete, that no request left the router, that the landfall
      history holds at least four assessments per landmark advancing one
      stage at a time with escalation notifications and both summaries
      stored, that every synthetic coordinate in every staged answer has
      at most two decimals and every synthetic answer carries its
      synthetic label, and that the landfall scenario's Miami-Dade
      briefing replays as `ok`, never withheld.
      `tests/scripts/test_demo_storm.py` covers the builder (each
      stage's answers parse through the real parsers).
      `tests/scripts/test_serve_demo.py` gains the flag's cases (each
      name, the default unchanged, the conflict with `--switch-file`),
      and `tests/ai/test_ai_fixtures.py` passes with the new manifest
      entries. Every test basename is new (Phase 3's check 8;
      `tests/engine/scenarios.py` already exists, so no file is named
      `test_scenarios.py`).
    </requirement>

    <requirement>
      Status: `README.md`'s `## Status` names Phases 1 to 7 complete,
      Phase 8 (UI/UX redesign and visual dogfooding) in progress, and
      Phase 9 (Release 2.0) next, keeping every other sentence and the
      commands below it; `CHANGELOG.md` gains `### Phase 8 — UI/UX
      redesign and visual dogfooding` under `## [Unreleased]` (one
      `[Unreleased]` heading stays, Phase 1's check 4). In the same PR,
      `scripts/verify_phase07.py`'s check 59 reads `README.md` through
      `tagged("README.md", tag=PHASE_7_TAG)` (the keyword matters: its
      `tagged` defaults to the Phase 6 tag) while its `CHANGELOG.md`
      clause stays live, and `tests/test_phase07_verification.py` gains
      two mutation cases like those Phase 7's Step 1 added for Phase 6's
      check 44: the live status no longer moves check 59, and the tagged
      status still decides it.
    </requirement>

    <requirement>
      `CONTRIBUTING.md`'s developer loop names the scenarios: how to
      start one, what each shows, and the recording command and its
      cost. Bandit scans `scripts/` (`-r src scripts`), so the new
      scripts use explicit checks and `raise`, never a bare `assert`
      (B101), and a subprocess, if any, takes a fixed argument list.
      Filepath comment: every new Python, TypeScript, YAML, or Markdown
      file gets its repository-relative path as its first line where the
      file type accepts comments, matching the sibling files.
    </requirement>
  </requirements>
</task>
```

### Step 1 acceptance criteria

- Each of the five scenarios starts offline in a temporary data directory and
  stores, for both landmarks, exactly the level and deciding rule Decision 2's
  table states, with complete assessments and no request outside the router.
- The landfall scenario holds a seeded history of at least four assessments per
  landmark that advances one stage at a time, with escalation notifications and
  both landmarks' change summaries, and its Miami-Dade briefing replays as `ok`.
- Every synthetic coordinate has at most two decimals, every synthetic answer
  carries its synthetic label in its own fields, the storm carries no real name,
  and no `src/` file changed.
- `serve_demo.py` without `--scenario` behaves exactly as before, and every
  Phase 5 to Phase 7 spec passes against it.
- `scenarios.spec.ts` passes on the `quiet` and `landfall` servers, and
  `tests/ai/test_ai_fixtures.py` passes with the scenario recordings.
- `README.md`'s status names Phase 8 in progress and Phase 9 (Release 2.0) next;
  Phase 7's check 59 reads its tag, with both mutation cases, and
  `verify_phase07.py --fast` passes.
- This roadmap's and the project roadmap's Phase 8 status lines read In
  progress.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean over the
  scripts and every new recording, SAST clean, dependency audit clean — no
  credential appears in any file, log, or output, and no scenario can reach the
  network, per the project roadmap's "Security & privacy strategy".

---

## Step 2 — The design system and readable type

**Status:** Not started

> **Goal:** Give every page one design language and type a reader can read.
> `frontend/src/index.css` gains a Tailwind `@theme` with the operator's type
> scale (Decision 4), a threat palette for levels 1 to 5 in both themes,
> surfaces, elevation, and radius; `frontend/src/ui/` gains the primitives every
> later step builds with (`Card`, `PageHeader`, `SectionHeading`, `StatTile`,
> `Callout`, `Chip`, `Button`, and `Disclosure` over a native `<details>`);
> `AppShell.tsx` gains icon navigation with live status badges that leave each
> link's name alone; every `text-xs` and pixel font size under `frontend/src` is
> replaced on all eight routes, and an ESLint rule keeps them out;
> `docs/DESIGN.md` records the system; and `frontend/e2e/readability.ts` with
> `readability.spec.ts` becomes the gate of Decision 6, run in CI on the `quiet`
> and `landfall` servers. Layouts stay where they are: Steps 3 to 7 restructure
> them with these parts.

**Branch:** `feature/phase08-step2-design-system`

**Deploys:** nothing beyond merge — the operator's copy takes this step at Step
9.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **Sonnet 5.5**     | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Claude Code        | Antigravity        | Claude Code        |
|               | Level    | XHigh              | High               | XHigh              |
|               | AA       | 51.9               | 52.6               | 56                 |
|               | Price    | $3.72/1M           | $6.13/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **GPT-6.1 Sol**    | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Codex              | Claude Code        | Antigravity        |
|               | Level    | High               | High               | High               |
|               | AA       | 50.2               | 53.6               | 52.6               |
|               | Price    | $2.86/1M           | $6.76/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6 Astra**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | High               | XHigh              |
|               | AA       | ≈45.2              | 50.9               | 52.4               |
|               | Price    | $2.31/1M           | $13.01/1M          | $17.73/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels or its previous version's.

**Conversation:** New

**Model rationale:** Step 2 is coding with a multimodal secondary category —
tokens, primitives, a shell, a sweep through every component, and a computed
gate, all of which must also be looked at — at High complexity, not novel:
Decisions 4 to 6 fix the scale, the palette's rule, and the gate's four checks.
On the step alone, the Quality Pick fits best: Opus 5.5 on Claude Code at Effort
XHigh, funded by the claude.ai Max subscription (it always thinks, so there is
no Thinking dial), brings the closest reading to some two hundred class
decisions, each of which is prose or caption, and to the contrast arithmetic
every later step depends on. The Balanced Pick, Gemini 4 Argon at High on
Antigravity, has the stronger eye for the palette and would fit nearly as well;
the Cost Pick, Sonnet 5.5 at XHigh, saves money with less margin across fifty
files. The conversation is new, per phase-boundary hygiene.

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
       feature/phase08-step2-design-system`
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
       Phase 8 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 8`
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

    THIS STEP changes presentation only, and the presentation rules are
    security rules here: no `style=` attribute (Phase 7's check 44 scans
    tests too), no `innerHTML` or `dangerouslySetInnerHTML` (Phase 5's
    check 37 and Phase 6's check 38, comments included), no new package
    or font host (Decision 5), and no change to `CSP_SUFFIX` or
    `index.html`'s nonce meta and external scripts (Phase 5's check 31).
    The badges read existing routes through shared query keys and poll
    nothing. The readability gate prints what it finds; a finding's text
    sample comes from a demonstration page that holds only the public
    landmarks and the synthetic storm, and the guard still fails any
    console message holding a coordinate. No binary file enters
    `frontend/src` (Phase 5's check 30 reads every file there as text).
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 8 (UI/UX redesign and visual
    dogfooding). Step 2: the design system and readable type.

    Current state (as of Phase 7, post-Phase-8 Step 1):

    - `frontend/src/index.css` holds only the Tailwind import and the
      class-based `dark` variant; components spell their own classes. In
      non-test TSX: 173 `text-xs`, 38 `text-[10px]` or `text-[11px]`, 41
      `text-sm`, 19 `text-base` (2026-11-15).
    - `AppShell.tsx`'s `NAV_ITEMS` are eight `{ to, label, end }`
      objects, one a line; Phase 6's check 40 reads the literal `{ to:
      "/ask", label: "Ask"` between `to: "/timeline"` and `to:
      "/settings"`, and Phase 7's check 48 requires the file's `{ to:
      "…"` objects to be exactly the eight paths in order.
      `AppShell.test.tsx` asserts the links' text is exactly the eight
      labels, a `Dashboard` heading, and the `/settings#disclaimer`
      footer link; `ai.spec.ts` and `charts.spec.ts` find links by exact
      name.
    - `ThreatLevelBadge.tsx`'s colours (emerald, sky, amber, orange,
      red) are the levels' hues the operator knows; `LEVEL_SVG_CLASSES`
      colours the charts.
    - Step 1's `quiet` (8802) and `landfall` (8806) servers start with
      every Playwright run; the demonstration pages hold only the
      landmarks and the synthetic storm.

    Files to read (every file before drafting):

    - docs/roadmap/phase08-roadmap.md (Decisions 4 to 6, 16, and 18, the
      Verification surfaces audit, and this step).
    - frontend/src/index.css, frontend/index.html,
      frontend/public/theme-init.js, frontend/vite.config.ts,
      frontend/eslint.config.js.
    - frontend/src/app/AppShell.tsx, ThemeMenu.tsx,
      ThreatLevelBadge.tsx, routes.tsx, and their tests.
    - Every TSX file under frontend/src/pages, settings, ai, assessment,
      charts, and map that holds `text-xs` or a pixel size (the counts
      above name the heaviest).
    - frontend/e2e/guard.ts, screens.spec.ts, and playwright.config.ts.
    - docs/roadmap/ROADMAP.md (§4 Phase 8, 8.1).
  </context>

  <goal>
    Land the tokens, the primitives, the redesigned shell, the type
    sweep, the lint rule, the design document, and the readability gate,
    with every route passing it.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Tokens (`frontend/src/index.css`): `@theme` sets `--text-caption`
      0.8125 rem (13 px, line height 1.4), `--text-sm` 0.9375 rem (15
      px, 1.5), `--text-base` 1.0625 rem (17 px, 1.6), `--text-lg` 1.25
      rem, `--text-xl` 1.5 rem, and `--text-2xl` 1.875 rem; a threat
      palette with, for each level 1 to 5, a tinted surface, a border, a
      foreground for text on that surface, and a solid accent, in the
      levels' existing hues, with dark-theme values under the `dark`
      class; neutral surfaces (page, card, raised card, inset), two
      elevation shadows, and the radius steps. Every text and surface
      pair the palette defines meets WCAG AA (4.5:1, or 3:1 for large
      text) in both themes, and `docs/DESIGN.md` lists each pair's
      measured ratio.
    </requirement>

    <requirement>
      Primitives (`frontend/src/ui/`, one file each, with tests): `Card`
      (surface, optional threat tint by level, elevation), `PageHeader`
      (title, one-line summary, actions slot), `SectionHeading`,
      `StatTile` (label, value in `tabular-nums`, unit, optional caption
      and trend), `Callout` (`note`, `warning`, `error`, `info`, mapped
      to `role="note"`, `"alert"`, or `"status"` as each existing use
      already has), `Chip`, `Button` and `LinkButton` (primary,
      secondary, ghost, danger; visible focus rings; at least 24 by 24
      CSS pixels), and `Disclosure` (a native `<details>` and
      `<summary>` with a chevron and a caption, closed by default, never
      a Radix collapsible — Decision 7). None sets a `style` attribute
      or reads the clock.
    </requirement>

    <requirement>
      Shell (`AppShell.tsx`): each `NAV_ITEMS` entry gains its lucide
      icon after its label on the same line (`{ to: "/ask", label:
      "Ask", icon: MessageCircle, end: false },`), so Phase 6's check 40
      and Phase 7's check 48 read what they read today, and no other `{
      to:` object appears in the file. Live status badges: the
      dashboard's highest current level, the active storm count, the
      covering alert count, the AI state when it is not ready (paused,
      capped, or off), and a warning mark on Settings when the monitor
      is stale — each read from an existing route through its shared
      query key (`assessments`, `storms`, `alerts`, `ai`, `health`),
      refreshed by the server's events, never polled. A badge renders
      beside its link, not inside it, is `aria-hidden`, and is described
      to assistive technology through the link's `aria-describedby`, so
      every link's text and accessible name stay its label
      (`AppShell.test.tsx`'s list, `ai.spec.ts`'s exact "Ask"). The
      navigation holds at 360 px without horizontal scrolling. Every
      route keeps its `<h1>` with today's name, visually hidden where
      the design wants, because `AppShell.test.tsx` finds each by its
      exact name. The header keeps the live or reconnecting chip and the
      theme menu; the stale banner, the footer's notice and disclaimer
      link, and the toasts take the new primitives and type.
    </requirement>

    <requirement>
      Sweep: every `text-xs`, `text-[10px]`, `text-[11px]`, and other
      arbitrary font size under `frontend/src` (tests included) is
      replaced: prose and controls by `text-sm` or `text-base`, meta by
      `text-caption` on a `<span>`, `<time>`, or `<small>` — never on a
      `<p>`, `<li>`, `<td>`, `<label>`, or `<button>` (Decision 6) — and
      headings by the scale. Cards and sections take the primitives
      where the swap is direct; no page's layout or behaviour changes in
      this step, and every existing test keeps its claims, edited only
      for the new class names and text. Numbers that change take
      `tabular-nums`. `eslint.config.js` adds a `no-restricted-syntax`
      rule that refuses a string or template literal containing
      `text-xs` or `text-[` followed by a length, so the lint at
      `--max-warnings 0` (the pre-commit hook and CI) keeps the sweep
      done.
    </requirement>

    <requirement>
      `docs/DESIGN.md`: the tokens and their ratios, each primitive and
      when to use it, the type rules (Decision 4 and the
      prose-or-caption rule), the vocabulary rules Step 3 completes
      (Decisions 7 and 8), the readability gate (Decision 6), layout
      breakpoints (Tailwind's `sm` 640, `md` 768, `lg` 1024, `xl` 1280),
      motion (`prefers-reduced-motion` honoured, no infinite animation
      on any page, for the idle budget), accessibility (focus rings,
      24-pixel targets, colour never the only signal, live regions), and
      the CSP rules (no `style=`, no markup from text, Radix styles
      under the nonce).
    </requirement>

    <requirement>
      Gate: `frontend/e2e/readability.ts` exports
      `auditReadability(page)` implementing Decision 6's four checks
      exactly as written, in-page, with no new package, returning
      findings that name the element (a short selector path), its
      computed value, and a text sample.
      `frontend/e2e/readability.spec.ts` runs it, under the guard, over
      eight renders — `/`, `/map`, `/replay` with its storm loaded,
      `/storms`, `/alerts`, `/timeline`, `/ask`, and `/settings` — at
      1440×900, 1280×800, and 360×740 on the `quiet` and `landfall`
      servers in light, and at 1440×900 in dark for contrast, and fails
      on any finding, printing every one. Step 7 makes the Settings
      render one per tab, twelve renders in all. The shell's root loses
      its `overflow-x-hidden`, which hides horizontal overflow from the
      page-level measure, and whatever overflow that reveals is fixed in
      this step. A unit test of the audit's contrast and luminance
      functions (`frontend/e2e/readability.unit.spec.ts`, run by
      Playwright without a server, or a Vitest file under `src/test/`)
      pins three known ratios.
    </requirement>

    <requirement>
      `docs/phase08-dogfood.md` starts here with its first-line path
      comment, a title, and a "Carried from Steps 2 to 7" table (key,
      what looks wrong, the step that owns the page), which this step
      and Steps 3 to 7 append to under the Triage rule whenever they see
      a defect on a page they do not own; Step 8 adds the rubric and the
      rounds. `screens.spec.ts` keeps capturing its pages, now including
      the `landfall` server's dashboard; `README.md`'s `### The
      dashboard` section (heading kept, Phase 5's check 47) says the
      pages follow `docs/DESIGN.md`; `CHANGELOG.md` notes the step.
      Filepath comment: every new Python, TypeScript, YAML, or Markdown
      file gets its repository-relative path as its first line where the
      file type accepts comments, matching the sibling files.
    </requirement>
  </requirements>
</task>
```

### Step 2 acceptance criteria

- `frontend/src/index.css` defines the type scale of Decision 4 and a threat
  palette whose every text and surface pair meets WCAG AA in both themes, with
  the ratios recorded in `docs/DESIGN.md`.
- No `text-xs` or arbitrary font size remains under `frontend/src`, and the lint
  refuses a new one.
- The navigation shows an icon per item and live badges from shared queries,
  every link's text and accessible name equal its label, and it fits at 360 px.
- `readability.spec.ts` passes on all eight renders at the three viewports on
  both scenario servers, and in dark at 1440×900, with no finding, and the shell
  no longer clips horizontal overflow.
- Every existing Vitest and Playwright test passes, edited only for class names
  and text; Phase 5 to Phase 7's `--fast` pass.
- `frontend/package.json`'s names, `CSP_SUFFIX`, and `index.html`'s scripts are
  unchanged, and no `style=` attribute exists under `frontend/src`.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean
  (ESLint with `eslint-plugin-security` at no warnings), dependency audit clean
  — and no markup is built from text, per the project roadmap's "Security &
  privacy strategy".

---

## Step 3 — Plain English and one vocabulary

**Status:** Not started

> **Goal:** Make every level read in the engine's own words, and keep the
> provenance one click away. `GET /api/ladder` (`services/ladder.py`,
> `web/routes/ladder.py`, `LadderResponse`) serves the five levels, the eleven
> rules in evaluation order, the NWS events and NHC codes the ladder reads, and
> the running thresholds; the exported fixture pins the frontend's fallback
> vocabulary in `frontend/src/assessment/vocabulary.ts`; `ThreatLevelBadge`
> shows the engine's level names; `ThreatMeter.tsx` draws the five-step ladder
> with the current step marked; `LocationHero.tsx` leads with the level name,
> the deciding rule's sentence, and the actions; and `WhyThisLevel.tsx`, a
> native `<details>` labelled "Why this level / Official provenance & controls",
> holds every rule id, product code, source id, zone, breakpoint span, raw time,
> unavailable input, and, on the dashboard, the evacuation-order switch. The
> dashboard's cards and `/replay`'s assessment card take the hero and the
> disclosure in place, and the Settings ladder is rebuilt from the route,
> replacing the hand-written one that contradicts the engine.

**Branch:** `feature/phase08-step3-plain-english`

**Deploys:** nothing beyond merge — the operator's copy takes this step at Step
9.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **Sonnet 5.5**     | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Claude Code        | Antigravity        | Claude Code        |
|               | Level    | XHigh              | High               | XHigh              |
|               | AA       | 51.9               | 52.6               | 56                 |
|               | Price    | $3.72/1M           | $6.13/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **GPT-6.1 Sol**    | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Codex              | Claude Code        | Antigravity        |
|               | Level    | High               | High               | High               |
|               | AA       | 50.2               | 53.6               | 52.6               |
|               | Price    | $2.86/1M           | $6.76/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6 Astra**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | High               | XHigh              |
|               | AA       | ≈45.2              | 50.9               | 52.4               |
|               | Price    | $2.31/1M           | $13.01/1M          | $17.73/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels or its previous version's.

**Conversation:** New

**Model rationale:** Step 3 is coding with a knowledge secondary category — a
service and a route over the engine's own metadata, a response model, the
OpenAPI document and fixtures, a vocabulary pinned to them, and the shared
components two pages compose, where a wrong word misstates an official product —
at High complexity, not novel: Decisions 7 and 8 fix what leads, what hides, and
where the words come from. On the step alone, the Quality Pick fits best: Opus
5.5 on Claude Code at Effort XHigh, funded by the claude.ai Max subscription (it
always thinks, so there is no Thinking dial), reads the ladder's semantics most
closely across the services, web, and frontend layers at once. The Balanced
Pick, Gemini 4 Argon at High, would build the components as well and the route
nearly so; the Cost Pick, Sonnet 5.5 at XHigh, trades away some of that
cross-layer care. The conversation is new, per phase-boundary hygiene.

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
       feature/phase08-step3-plain-english`
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
       Phase 8 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 8`
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

    THIS STEP adds one route, and it serves engine metadata only:
    levels, rules, product names, codes, and thresholds — no location,
    coordinate, zone, or assessment — and
    `tests/web/test_api_privacy.py` scans its answer like every other.
    It is a sync `def` route (Phase 5's check 17, Phase 6's check 32)
    behind the existing guards: same-origin, no cross-origin read,
    `no-store`. The web layer imports `services/ladder.py`, never the
    engine (`lint-imports`). On the page, the disclosure is native HTML,
    every value in it is text, and no rule id or code is turned into
    markup.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 8 (UI/UX redesign and visual
    dogfooding). Step 3: plain English and one vocabulary.

    Current state (as of Phase 7, post-Phase-8 Step 2):

    - Each assessment the API serves carries `level` (`number`, `label`,
      `actions`), `rule`, and `rule_trigger`; `rule` is a plain string
      in `docs/api/openapi.json`. `AlertLevel`'s labels and actions live
      in `models/ladder.py`, `RULES` (id, sentence, sources) in
      `engine/rules.py`, and the products the ladder reads in
      `engine/official.py` (`LADDER_EVENTS`: Hurricane Warning, Tropical
      Storm Warning, Hurricane Watch, Tropical Storm Watch;
      `LADDER_CODES`: `HWR`, `TWR`, `HWA`, `TWA`).
      `services/assessments.py` already maps each rule id to its
      sentence; `scripts/export_ladder.py` renders
      `docs/ALERT-LADDER.md` from the same sources.
    - `ThreatLevelBadge`'s fallback names differ from `AlertLevel`'s,
      and the dashboard renders it without the API's label (Decision 8).
      `Settings.tsx`'s `LADDER_RULES` is wrong in order, a rule's name,
      its products, and its codes (Decision 8).
    - `frontend/src/assessment/` holds `LevelSummary` ("Deciding rule:"
      and the rule id in `<code>` as its headline), `EvidenceList`
      (detail, code, source id, distance, issued time on one line),
      `OfficialProductList`, `ThreatTable`, and `UnavailableBanner`;
      `Dashboard.tsx` and `Replay.tsx` both compose them, and Phase 7's
      check 49 requires both files to name all four.
      `assessment.test.tsx` asserts no `[style]` element.
      `replay.spec.ts` and `phase7.spec.ts` read `hurricane_watch`,
      `hurricane_warning`, and `HWR` from `replay-assessment-card` by
      text content. `Dashboard.test.tsx` reads the live region's
      "Decided by all_clear." text.
    - Step 2's primitives (`Card`, `StatTile`, `Callout`, `Chip`,
      `Disclosure`) and tokens exist; the readability gate runs in CI.

    Files to read (every file before drafting):

    - docs/roadmap/phase08-roadmap.md (Decisions 7, 8, and 16, and this
      step) and docs/DESIGN.md.
    - src/weatherbot/models/ladder.py, engine/rules.py,
      engine/official.py, engine/__init__.py, services/assessments.py,
      services/disclaimer.py, and services/config.py (`LiveSettings` and
      what it reloads).
    - src/weatherbot/web/app.py, routes/disclaimer.py,
      routes/assessments.py, routes/settings.py, and schemas.py.
    - scripts/export_api_fixtures.py, scripts/export_openapi.py,
      scripts/export_ladder.py, tests/web/test_api_fixtures.py,
      tests/web/test_api_privacy.py, tests/web/test_openapi_export.py.
    - frontend/src/assessment/ (every file and `assessment.test.tsx`),
      app/ThreatLevelBadge.tsx, pages/Dashboard.tsx, pages/Replay.tsx,
      pages/Settings.tsx, api/keys.ts, and their tests.
    - frontend/e2e/replay.spec.ts and phase7.spec.ts.
  </context>

  <goal>
    Serve the ladder from the engine, pin the frontend's vocabulary to
    it, and lead every assessment with plain words while its provenance
    sits, complete, in the disclosure.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `services/ladder.py`: `ladder_reference(thresholds) ->
      LadderReference`, a frozen model of the five levels (number,
      label, actions) from `AlertLevel`, the eleven rules (order, id,
      level, sentence, sources) from `RULES`, the ladder's NWS events
      and NHC codes with the rule each sets from `engine/official.py`,
      and the thresholds' names, values, and units.
      `web/routes/ladder.py`: sync `GET /api/ladder` answering
      `LadderResponse` from the thresholds the engine is running —
      `WebState`'s startup settings (`settings.engine.thresholds()`,
      which `WebState` already uses for replay), never a re-read of the
      file, because `LiveSettings` reloads only `[notifications]` and
      `[retention]` and an edited `[engine]` applies at the next start
      (Decision 8) — registered in `web/app.py`. `docs/api/openapi.json`
      and `frontend/src/api/schema.d.ts` regenerate,
      `scripts/export_api_fixtures.py` writes
      `frontend/src/test/fixtures/ladder.json`, and
      `tests/web/test_api_privacy.py` covers the route.
    </requirement>

    <requirement>
      Vocabulary (`frontend/src/assessment/vocabulary.ts`): a typed
      fallback table of the five levels and eleven rules that a Vitest
      test proves equal to `ladder.json`; `useLadder()` over
      `queryKeys.ladder()` = `invalidatableQueryKey("settings",
      "ladder")` (a query under an existing server prefix, as Phase 7's
      charts nest under `timeline`, so `events.py`'s `QUERY_KEYS` is
      unchanged, Phase 7's check 45); `levelLabel(n)` and
      `ruleSentence(id)` returning the server's words, the fallback
      until the query resolves. `ThreatLevelBadge` takes its names from
      the vocabulary when no label is passed, and every caller that
      holds an assessment passes `level.label`.
    </requirement>

    <requirement>
      `ThreatMeter.tsx`: five steps in the threat palette, the current
      one emphasized and the others muted, each labelled with its number
      and name, rendered as an ordered list with `aria-current="step"`
      on the current one and a visually hidden "Level N of 5" — colour
      is never the only signal — and "at least" marked when the
      assessment is incomplete. It fits at 360 px.
    </requirement>

    <requirement>
      `LocationHero.tsx`: the location's level as "Level N — {engine
      name}", prefixed "At least" when incomplete; the deciding rule's
      sentence (`rule_trigger`); the level's actions; the meter; and the
      facts a reader must not miss — an incomplete assessment's floor, a
      toggle-changed note, an evacuation order that is on — as callouts
      beside the headline, not inside the disclosure. Its headline and
      sentence hold no rule id, product code (`HWR`, `TWA`, an NWS
      event's code), source id, zone, breakpoint span, or raw timestamp;
      a test asserts that with a pattern for snake-case ids and the code
      list. The assessed time reads as a relative age with the local
      time, and the UTC instant moves into the disclosure.
    </requirement>

    <requirement>
      `WhyThisLevel.tsx`: a `Disclosure` (native `<details>`) whose
      summary reads "Why this level / Official provenance & controls",
      closed by default, holding, in order: the deciding rule (its id
      and sentence); the evidence (`EvidenceList`, each entry leading
      with words, with its code, source id, distance, and issued time in
      local and UTC as captions); the official products
      (`OfficialProductList`); the threats (`ThreatTable`); the
      unavailable inputs; the coverage (inside or outside NWS coverage,
      the breakpoint span, the zones); the assessment's time and
      snapshot; and a `controls` slot. The four shared components are
      passed in as children by each page, so `Dashboard.tsx` and
      `Replay.tsx` still name all four (Phase 7's check 49) and nothing
      is copied. `LevelSummary` loses its "Deciding rule:" headline,
      which the hero now carries in words.
    </requirement>

    <requirement>
      Dashboard: each location card shows `LocationHero` and
      `WhyThisLevel`, with the evacuation-order switch (`role="switch"`,
      its label and its effect sentence unchanged) in the disclosure's
      `controls` slot and, when on, a callout in the hero; the
      comparison strip shows each level's name instead of its rule id;
      and the live region announces "{name}: Level N, {engine name}.
      {rule sentence}" (with "At least" when incomplete), with
      `Dashboard.test.tsx` updated to it. Replay:
      `replay-assessment-card` shows the same two components and no
      switch (the toggle is off for a past storm, and the hero says so);
      `replay.spec.ts` and `phase7.spec.ts` keep finding
      `hurricane_watch`, `hurricane_warning`, and `HWR` in the card's
      text, which the closed disclosure holds. Settings: the ladder card
      renders from `useLadder()` — eleven rules in engine order with
      their levels, sentences, and sources, and the read products and
      codes — and `LADDER_RULES` is deleted.
    </requirement>

    <requirement>
      Tests: `tests/services/test_ladder_reference.py` (levels equal
      `AlertLevel` in order with labels and actions; rules equal `RULES`
      in order with ids, sentences, and sources; events and codes equal
      `LADDER_EVENTS` and `LADDER_CODES`; thresholds equal the
      settings'; no coordinate), `tests/web/test_ladder_route.py` (sync
      route, 200, the model, the startup thresholds even after the file
      changes, the privacy scan), Vitest for the vocabulary's equality
      with the fixture, `ThreatMeter`, `LocationHero` (the headline
      pattern test and "At least"), `WhyThisLevel` (closed by default,
      every id and code present in the DOM, no `[style]`), the badge's
      names, and the Settings ladder (order and names from the fixture;
      no `tropical_storm_cone`, "Extreme Wind Warning", "Storm Surge
      Warning", or "Storm Surge Watch" anywhere under `frontend/src`;
      the `TRW` and `TRA` aliases that `layers.ts` and `Alerts.tsx` map
      beside `TWR` and `TWA` are harmless and stay). A new
      `frontend/e2e/plain-english.spec.ts` on the `landfall` server
      asserts that each hero's headline holds no snake-case id or code,
      and that opening the disclosure shows `hurricane_warning`, `HWR`,
      and the evacuation-order switch. `README.md`'s dashboard section
      and `CHANGELOG.md` follow.
    </requirement>

    <requirement>
      Filepath comment: every new Python, TypeScript, YAML, or Markdown
      file gets its repository-relative path as its first line where the
      file type accepts comments, matching the sibling files.
    </requirement>
  </requirements>
</task>
```

### Step 3 acceptance criteria

- `GET /api/ladder` answers the engine's five levels, eleven rules in evaluation
  order, read products and codes, and thresholds, as a sync route holding no
  location data, with the OpenAPI document, the generated types, and
  `ladder.json` current.
- The frontend's level and rule words equal `ladder.json`, every badge shows the
  engine's level name, and the Settings ladder equals `RULES`.
- No hero headline or sentence holds a rule id, product code, source id, zone,
  or raw timestamp, and opening the disclosure shows all of them and the
  evacuation-order switch.
- `Dashboard.tsx` and `Replay.tsx` both still compose `LevelSummary`,
  `ThreatTable`, `OfficialProductList`, and `EvidenceList`; Phase 7's `--fast`
  passes.
- `replay.spec.ts`, `phase7.spec.ts`, `plain-english.spec.ts`, and the
  readability gate pass; `assessment.test.tsx` finds no `[style]`.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — and the new route serves no location data and passes
  the privacy scan, per the project roadmap's "Security & privacy strategy".

---

## Step 4 — The command-center dashboard

**Status:** Not started

> **Goal:** Make `/` answer "how bad, where, and what now" in one look. A
> one-line status and action bar replaces the controls card: the snapshot's age
> and status, the next NHC product as a minute countdown, `Check now`, and an
> `Export report` popover that holds the downloads, the AI-briefing box, and its
> caveat; location switcher cards replace the comparison strip, each with the
> location's name, level, plain-English headline, and sparkline, and one
> featured location — chosen by level, kept in the URL hash — shows its
> `LocationHero`, threat meter, stat tiles, AI briefing card, changes, and
> `WhyThisLevel`; and a live situation mini-map card draws the storms, their
> watches and warnings, and the locations from the map query `/map` already
> uses. Every Decision 9 and 10 rule holds, idle stays near zero, and the specs
> that read this page are updated to it.

**Branch:** `feature/phase08-step4-dashboard`

**Deploys:** nothing beyond merge — the operator's copy takes this step at Step
9.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **Sonnet 5.5**     | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Claude Code        | Antigravity        | Claude Code        |
|               | Level    | XHigh              | High               | XHigh              |
|               | AA       | 51.9               | 52.6               | 56                 |
|               | Price    | $3.72/1M           | $6.13/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **GPT-6.1 Sol**    | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Codex              | Claude Code        | Antigravity        |
|               | Level    | High               | High               | High               |
|               | AA       | 50.2               | 53.6               | 52.6               |
|               | Price    | $2.86/1M           | $6.76/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6 Astra**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | High               | XHigh              |
|               | AA       | ≈45.2              | 50.9               | 52.4               |
|               | Price    | $2.31/1M           | $13.01/1M          | $17.73/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels or its previous version's.

**Conversation:** New

**Model rationale:** Step 4 is coding with a multimodal secondary category — a
page composed from Step 2's parts and Step 3's components, a popover, a
hash-bound selection, a countdown, and a second map, whose result is judged by
eye in five scenarios — at High complexity, not novel: Decisions 9 and 10 fix
the layout's contract and its idle cost. On the step alone, the Balanced Pick
fits best: Gemini 4 Argon on Antigravity at Effort High, with Thinking On, pairs
S-tier coding with strong visual judgement for hierarchy, spacing, and the
threat tints across levels. The Quality Pick, Opus 5.5 at XHigh, adds audit
depth a composition step needs less than Steps 2 and 3 did; the Cost Pick,
Sonnet 5.5 at XHigh, saves money with less eye for the result. The conversation
is new, per phase-boundary hygiene.

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
       feature/phase08-step4-dashboard`
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
       Phase 8 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 8`
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

    THIS STEP adds no route and no data path. The export popover links
    to the same `GET /api/report` downloads with the same query
    (`location`, `briefing=true`), whose answer stays an attachment
    under its sandbox CSP, and the AI box keeps its caveat, because a
    briefing's words can name a county. The mini-map reuses
    `useLeafletMap` and its OpenStreetMap tile policy (`referrerPolicy`,
    no `crossOrigin`), adds no overlay, and draws popups as DOM nodes.
    The countdown is a client timer that requests nothing. The featured
    location's hash is a slug of a name the operator typed, never a
    coordinate.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 8 (UI/UX redesign and visual
    dogfooding). Step 4: the command-center dashboard.

    Current state (as of Phase 7, post-Phase-8 Step 3):

    - `frontend/src/pages/Dashboard.tsx` opens with the "Monitor cycle
      controls" card (status line, `export-report-all`, `Check now`, the
      export paragraph, the AI box, the cycle and evacuation messages),
      then the comparison strip (`location-comparison-strip`, two or
      more locations) and one card per location, each now showing Step
      3's `LocationHero` and `WhyThisLevel`, with `BriefingPanel`, the
      charts, and the changes. `locationCardId(name)` writes
      `location-<slug>`; `buildReportHref(location, includeBriefing)`
      builds the report URL. The dashboard reads `/api/health` from
      `AppShell`'s query with `enabled: false` and `next_product_at`
      from it.
    - `useLeafletMap({ mapData, visibility, ... })` builds one map per
      container; `queryKeys.map()` is `/map`'s live query;
      `DEFAULT_LAYER_VISIBILITY` is in `layers.ts`.
    - Specs that read `/`: `dashboard.spec.ts` (both headings, the
      footer, the theme menu, `Live`, `Check now`, an `article` with
      "Level 5" and "Hurricane Warning", a toast), `charts.spec.ts` (the
      strip, `#location-simulated-miami-dade`, the sparkline, the
      arrival timeline, no overflow at 360 px), `report.spec.ts`
      (Parliament Square's briefing region, "Include the AI briefing",
      `export-report-all` with `briefing=true`), `ai.spec.ts` (`region`
      "AI briefing for {name}", `Brief me`, level-4 headings, and in its
      refused-credential case both panels at once), `layers.spec.ts` and
      `phase7.spec.ts` (`Check now`, a heading, `level-sparkline`,
      `export-report-all`, and `getByRole("article", { name })`
      containing "Outside NWS coverage" for a location it added), and
      `idle.spec.ts` (both headings). `AppShell.test.tsx` finds the
      page's `Dashboard` heading by its exact name.
      `BriefingPanel.test.tsx` and `ai.spec.ts` count level-4 headings.

    Files to read (every file before drafting):

    - docs/roadmap/phase08-roadmap.md (Decisions 9, 10, and 16, and this
      step) and docs/DESIGN.md.
    - frontend/src/pages/Dashboard.tsx, Dashboard.test.tsx, and
      format.ts; frontend/src/ai/BriefingPanel.tsx and its test;
      frontend/src/assessment/ (Step 3's components);
      frontend/src/charts/LevelSparkline.tsx and ArrivalTimeline.tsx;
      frontend/src/map/useLeafletMap.ts and layers.ts;
      frontend/src/app/AppShell.tsx; frontend/src/api/keys.ts.
    - frontend/e2e/dashboard.spec.ts, charts.spec.ts, report.spec.ts,
      ai.spec.ts, layers.spec.ts, phase7.spec.ts, idle.spec.ts,
      guard.ts.
    - scripts/measure_idle.py.
  </context>

  <goal>
    Rebuild `/` as the command center of Decision 9, within Decision
    10's idle cost, and update every spec that reads it.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Status and action bar (`frontend/src/dashboard/StatusBar.tsx`):
      one line at 1024 px and wider, wrapping cleanly below; the
      snapshot's status and age; the next NHC product as "Next NHC
      product in 42 min" (the local time in a caption, the UTC instant
      in its `title`), re-rendered by one `setTimeout` to the next
      minute boundary, cleared on unmount and paused while
      `document.hidden`, never `setInterval`; `Check now` with its
      spinner and its 202, 409, and 429 messages; and `Export report`.
      The page keeps an `<h1>` "Dashboard" (visually hidden if the
      design wants), which `AppShell.test.tsx` reads.
    </requirement>

    <requirement>
      Export popover (`frontend/src/dashboard/ExportPopover.tsx`): a
      non-modal Radix `Popover` (the `radix-ui` package's, styled under
      the existing nonce) holding the all-locations link
      (`data-testid="export-report-all"`), one link per location
      (`data-testid="export-report-{name}"`, `aria-label` "Export report
      for {name}"), the "Include the AI briefing" checkbox, and one line
      saying what the file holds and that a briefing's words can name a
      county. Escape and an outside click close it, focus returns to its
      button, and its content is portalled, outside every render a
      `[style]` test inspects.
    </requirement>

    <requirement>
      Location switcher (`frontend/src/dashboard/LocationSwitcher.tsx`):
      one `<article aria-label={name}>` per location, holding the page's
      only heading that contains the name (the specs match headings by
      substring, and two matches fail strict mode), the level badge with
      the engine's name, the plain-English headline, the NWS-coverage
      caption ("Inside NWS coverage" or "Outside NWS coverage", which
      `phase7.spec.ts` reads from the article), the sparkline, the
      assessed age, and a link to `#location-<slug>` (`aria-current` on
      the featured one) that features it. The featured location is the
      hash's, or else the highest level, then list order; Back and
      Forward move between features. With one location the switcher
      shows that location alone, and with none the empty state keeps its
      disclaimer essentials and its link to Settings.
    </requirement>

    <requirement>
      Featured location (`frontend/src/dashboard/FeaturedLocation.tsx`):
      `LocationHero` with its meter; stat tiles (`StatTile`) for what
      the assessment holds — the nearest storm's closest-approach
      distance and time, its bearing in compass words, the earliest and
      most likely arrival, the 34-kt and 64-kt chance at the latest
      synoptic time, and the number of storms tracked — each with a
      caption naming its product and a dash when the input is absent;
      `ArrivalTimeline` for the nearest storm
      (`data-testid="arrival-timeline"`, which `charts.spec.ts` needs
      visible on `/`); `BriefingPanel` (`region` "AI briefing for
      {name}", its level-4 section headings kept, or
      `BriefingPanel.test.tsx` and `ai.spec.ts` updated together); the
      changes since the last assessment in words; and `WhyThisLevel`
      with the evacuation-order switch in its `controls` slot. The four
      shared components stay named in `Dashboard.tsx` (Phase 7's check
      49).
    </requirement>

    <requirement>
      Live situation mini-map (`frontend/src/dashboard/MiniMap.tsx`): a
      card around a container passed to `useLeafletMap` with
      `queryKeys.map()`'s data (no second request) and a visibility of
      cones, tracks, forecast points, watches and warnings, and
      locations; no overlay, depth, slider, or panel; about 280 px tall,
      220 px on phones; a "Open the map" link to `/map`; and a one-line
      caption with the storm count and the snapshot's age. No
      `setInterval` enters `frontend/src/map/` (Phase 7's check 37), and
      no second `tileLayer.wms` exists anywhere.
    </requirement>

    <requirement>
      Layout: at 1280 px and wider, the bar across the top, the switcher
      beneath it, then two columns — the featured location (about two
      thirds) and the mini-map with the briefing card's status beneath
      it (about one third); at 1024 px, the mini-map below the featured
      location; on phones, one column in the order bar, switcher, hero,
      tiles, briefing, map, disclosure. The live region
      (`data-testid="level-live-region"`) stays. The readability gate
      passes on `/` at every viewport in every scenario the gate runs.
    </requirement>

    <requirement>
      Specs and tests: `Dashboard.test.tsx` rewritten for the bar (fake
      timers for the countdown, including the pause while hidden), the
      popover's contents, the switcher (one heading per name, the
      default by level, the hash), the tiles (`tabular-nums`, the dash),
      the featured briefing, the mini-map container, and the empty,
      loading, and error states; `dashboard.spec.ts`, `charts.spec.ts`,
      `report.spec.ts` (feature Parliament Square, open the popover,
      tick the box), `ai.spec.ts` (feature each location before reading
      its panel), `layers.spec.ts`, `phase7.spec.ts`, and `idle.spec.ts`
      updated to the new page, every file kept at its path with its
      claims; and a new `frontend/e2e/command-center.spec.ts` on the
      `landfall` server: the bar fits one line at 1440 px, the countdown
      reads minutes, the popover opens, closes on Escape, and returns
      focus, a switcher link features a location and Back restores the
      last, the mini-map draws the cone and both markers, and the page
      logs no console error (the spec records and asserts that itself;
      the guard does not).
    </requirement>

    <requirement>
      Idle: run `uv run python scripts/measure_idle.py` once on this
      machine after the page is done and put its line in the PR body;
      both shares stay under 0.5 percent (Decision 10). `README.md`'s
      `### The dashboard` section (heading kept) and `CHANGELOG.md`
      describe the page. Filepath comment: every new Python, TypeScript,
      YAML, or Markdown file gets its repository-relative path as its
      first line where the file type accepts comments, matching the
      sibling files.
    </requirement>
  </requirements>
</task>
```

### Step 4 acceptance criteria

- `/` shows the one-line bar with a minute countdown, `Check now`, and the
  export popover, the switcher with one heading per location, the featured
  location's hero, meter, tiles, briefing, changes, and disclosure, and the
  mini-map, in the layout described at each width.
- The featured location follows the hash, defaults to the highest level, and
  Back restores the previous one.
- The countdown uses one `setTimeout` per minute, pauses while hidden, and no
  `setInterval` was added; the idle measurement reads both shares under 0.5
  percent.
- `Dashboard.test.tsx`, `command-center.spec.ts`, and every updated spec pass;
  the readability gate passes on `/`.
- `Dashboard.tsx` still composes the four shared components, and Phase 5 to
  Phase 7's `--fast` pass.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — and the export and mini-map reuse the existing report
  route and tile policy with no new request, per the project roadmap's "Security
  & privacy strategy".

---

## Step 5 — The immersive map

**Status:** Not started

> **Goal:** Let the map be the page. `/map`'s canvas fills the viewport below
> the header, never shorter than 70 percent of it; its controls float over it as
> panels that are siblings of the Leaflet container — Layers (the twelve labels
> under four new groups, the wind-probability threshold), Legend (only the
> visible layers' sections, the nowCOAST age note, the unavailable banners), a
> status chip (as-of time, origin, storm count, Fit), and the advisory slider
> docked at the bottom — each a plain disclosure, open by default at 1024 px and
> wider; the replay panel leaves `/map` for a link to `/replay`; and
> `map.spec.ts` is rewritten in place to test the live map, with every other
> spec and test that reads the page updated to it.

**Branch:** `feature/phase08-step5-map`

**Deploys:** nothing beyond merge — the operator's copy takes this step at Step
9.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **Sonnet 5.5**     | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Claude Code        | Antigravity        | Claude Code        |
|               | Level    | XHigh              | High               | XHigh              |
|               | AA       | 51.9               | 52.6               | 56                 |
|               | Price    | $3.72/1M           | $6.13/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **GPT-6.1 Sol**    | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Codex              | Claude Code        | Antigravity        |
|               | Level    | High               | High               | High               |
|               | AA       | 50.2               | 53.6               | 52.6               |
|               | Price    | $2.86/1M           | $6.76/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6 Astra**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | High               | XHigh              |
|               | AA       | ≈45.2              | 50.9               | 52.4               |
|               | Price    | $2.31/1M           | $13.01/1M          | $17.73/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels or its previous version's.

**Conversation:** New

**Model rationale:** Step 5 is coding with a multimodal secondary category — a
full-viewport Leaflet canvas, four floating panels with their own focus and
stacking rules, the removal of a panel two specs drove, and a spec rewritten in
place — at High complexity, not novel: Decision 11 fixes the panels, their
defaults, and what leaves. On the step alone, the Balanced Pick fits best:
Gemini 4 Argon on Antigravity at Effort High, with Thinking On, brings the
strongest visual judgement in this ladder to panels that must leave the map
readable at every width. The Quality Pick, Opus 5.5 at XHigh, adds audit depth a
layout step needs less, and the Cost Pick, Sonnet 5.5 at XHigh, saves money with
less eye for occlusion and balance. The conversation is new, per phase-boundary
hygiene.

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
       feature/phase08-step5-map`
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
       Phase 8 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 8`
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

    THIS STEP moves controls, not requests: the overlays still load only
    while toggled on (Phase 7's `layers.spec.ts` proves no request
    before its toggle), `CSP_SUFFIX` is unchanged (Phase 7's check 35),
    `tileLayer.wms` stays confined to `useLeafletMap.ts` and no
    `setInterval` enters `frontend/src/map/` (check 37), and popups and
    tooltips stay DOM nodes built with `textContent`. The panels are
    plain elements over the map, so nothing is portalled and nothing
    sets an inline style.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 8 (UI/UX redesign and visual
    dogfooding). Step 5: the immersive map.

    Current state (as of Phase 7, post-Phase-8 Step 4):

    - `frontend/src/map/MapView.tsx` stacks a header card with `Fit`,
      the route errors, `AdvisorySlider` (when more than one stored
      advisory exists), the replay panel (`replay-panel`,
      `#replay-storm-select`, `#replay-advisory-select`,
      `replay-not-live-banner`, `Back to live`, shown when `/api/health`
      reads `corpus: true`), the map (`leaflet-map-container`, 280 px or
      520 px tall), and two cards below it: the layer toggles (`region`
      "Map layer toggles", checkboxes from `LAYER_TOGGLE_ITEMS` with
      "(not in this corpus)", "(live only)", or "(unavailable)" reasons,
      and `wind-probability-controls`) and the legend
      (`MAP_LEGEND_SECTIONS`, `nowcoast-age-note`,
      `radar-unavailable-banner`, `satellite-unavailable-banner`, the
      server clock). Replay state lives here as well as on `/replay`.
    - `layers.ts` keeps `LAYER_TOGGLE_ITEMS` as one flat list of twelve
      (no groups exist), `DEFAULT_LAYER_VISIBILITY` with twelve literals
      (Phase 7's check 36), and `MAP_LEGEND_SECTIONS` with twelve
      categories, counts, and NHC's colours that `layers.test.ts` pins;
      `AdvisorySlider.tsx`'s root is `<section aria-label="Advisory
      history" data-testid="advisory-slider-panel">`, with the
      stored-advisory banner inside it; `useLeafletMap.ts` observes its
      container's size (PR #105) and fits once per view mode.
    - `map.spec.ts` (Phase 5; selected by file in Phase 5's V6.3) has
      one test, which drives the replay picker; `MapView.test.tsx`
      (selected in V6.2) has a replay-panel case expecting "(not in this
      corpus)" five times, and two "(live only)" assertions.
      `layers.spec.ts` (Phase 7's V5.4) needs the "Map layer toggles"
      region visible with six labelled checkboxes,
      `wind-probability-controls`, `nowcoast-age-note`,
      `advisory-slider-panel`, `#advisory-history-slider`,
      `stored-advisory-banner` ("Stored advisory:", "not the latest",
      "(live only)" in the toggles region), and the peak-surge path.
      `phase7.spec.ts` reads the same panel, the slider, and
      `radar-unavailable-banner`.

    Files to read (every file before drafting):

    - docs/roadmap/phase08-roadmap.md (Decisions 11 and 16, and this
      step) and docs/DESIGN.md.
    - frontend/src/map/MapView.tsx, layers.ts, useLeafletMap.ts,
      AdvisorySlider.tsx, and their tests.
    - frontend/src/pages/Replay.tsx (where replay lives after this
      step).
    - frontend/e2e/map.spec.ts, layers.spec.ts, phase7.spec.ts,
      screens.spec.ts, guard.ts.
  </context>

  <goal>
    Rebuild `/map` as the canvas of Decision 11 with floating panels,
    remove its replay panel, and keep every map spec and test green at
    its path.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Canvas: the map container (`data-testid="leaflet-map-container"`,
      `aria-label` "Tropical cyclone threat map") fills the viewport
      below the header and above the footer with a minimum of 70 percent
      of the viewport's height (`min-h-[70vh]` with a `dvh`-based
      height), at full content width; the page's `<h1>` "Map" stays but
      is visually hidden (`AppShell.test.tsx` finds it by its exact
      name), so the map starts at the top of `<main>`. Route errors and
      the stored-advisory banner sit as panels over the map, not above
      it.
    </requirement>

    <requirement>
      Panels (`frontend/src/map/MapPanels.tsx` or one file each), each a
      `<section>` positioned over the map as a sibling of the Leaflet
      container, never inside Leaflet's DOM: Layers (`region` "Map layer
      toggles", the twelve existing labels and unavailable reasons under
      four headed groups — new work: a `LAYER_GROUPS` constant in
      `layers.ts` maps Forecast to `cone`, `track`, `points`,
      `past_track`, `watches_warnings`, and `outlook`, Wind & surge to
      `wind_radii`, `wind_probabilities`, and `peak_surge`, Observations
      to `radar` and `satellite`, and Locations to `locations`, while
      `LAYER_TOGGLE_ITEMS` and `DEFAULT_LAYER_VISIBILITY` stay as they
      are — and `wind-probability-controls` inside it when that layer is
      on); Legend (`region` "Map legend", the sections of
      `MAP_LEGEND_SECTIONS` whose layers are visible, filtered at render
      so the data `layers.test.ts` pins is unchanged, plus
      `nowcoast-age-note` and the unavailable banners); a status chip
      (as-of time, origin, storm count, and `Fit`); and the advisory
      slider (`AdvisorySlider` unchanged, docked at the bottom by a
      wrapper that carries no test id: the slider's own root already is
      `data-testid="advisory-slider-panel"`, and a second match would
      break the strict locators in `layers.spec.ts` and
      `phase7.spec.ts`). Each panel is an opaque card surface (no
      translucency over the tiles, Decision 11) with a header button
      with `aria-expanded` and `aria-controls` that collapses it to its
      title; panels are open by default at 1024 px and wider and
      collapsed below (read through `matchMedia` once at mount, then the
      operator's choice); keyboard focus moves through them in reading
      order; Leaflet's zoom control and attribution stay visible; and on
      a phone the open panel takes the bottom of the screen rather than
      covering the storm. No Radix `Popover` or `Dialog` is used inside
      the map (Decision 11).
    </requirement>

    <requirement>
      Replay leaves `/map`: the replay panel, its two selects, its
      banner, and `Back to live` are removed with the replay branches of
      `MapView`'s queries and visibility logic (the stored-advisory
      path, `snapshot_id`, stays); when `/api/health` reads `corpus:
      true`, the status chip links "Replay a past storm" to `/replay`.
      `useLeafletMap`'s `ResizeObserver` keeps the map fitted when a
      panel opens or the viewport changes.
    </requirement>

    <requirement>
      Specs and tests: `map.spec.ts` is rewritten in place (Phase 5's
      V6.3 selects it by file) as a live-map test on the `landfall`
      server: the canvas is at least 70 percent of the viewport tall,
      the cone, track, at least five points, and the two location
      markers draw (the same path selectors it uses today), toggling the
      cone in the Layers panel hides its paths, and no `replay-panel`
      exists. `MapView.test.tsx` drops its replay-panel case and gains
      the panels' cases (open by default with a wide `matchMedia`,
      collapsed with a narrow one, `aria-expanded`, the layer groups,
      the legend showing visible layers only, the replay link only with
      the corpus, and `radar-unavailable-banner` and
      `satellite-unavailable-banner` in the Legend panel after a
      reported tile error), keeping its other cases. `layers.spec.ts`
      and `phase7.spec.ts` keep their claims at the default 1280×720
      viewport, where the Layers panel is open; `screens.spec.ts` keeps
      its map screenshots.
    </requirement>

    <requirement>
      `README.md`'s dashboard section says how the map's panels work and
      where replay lives; `CHANGELOG.md` notes the step. Filepath
      comment: every new Python, TypeScript, YAML, or Markdown file gets
      its repository-relative path as its first line where the file type
      accepts comments, matching the sibling files.
    </requirement>
  </requirements>
</task>
```

### Step 5 acceptance criteria

- `/map`'s canvas is at least 70 percent of the viewport tall at every viewport,
  with the Layers, Legend, status, and slider panels floating over it, open by
  default at 1024 px and wider and collapsible by keyboard.
- The legend shows only visible layers' sections, and `MAP_LEGEND_SECTIONS` and
  `DEFAULT_LAYER_VISIBILITY` are unchanged.
- No replay panel, select, or banner remains on `/map`; a link to `/replay`
  shows with the corpus.
- `map.spec.ts` (rewritten in place), `MapView.test.tsx`, `layers.spec.ts`,
  `phase7.spec.ts`, and the readability gate pass; Phase 5 to Phase 7's `--fast`
  pass.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — and overlays still load only while toggled on, per
  the project roadmap's "Security & privacy strategy".

---

## Step 6 — The replay workbench

**Status:** Not started

> **Goal:** Let a past storm be read side by side. At 1280 px and wider
> `/replay` becomes two columns — the map, at least 60 percent of the viewport
> tall, with the scrubber and the level history chart beneath it, and a sticky
> column holding the non-dismissible replay banner, the same `LocationHero` the
> dashboard uses, and `WhyThisLevel` — so scrubbing shows the cone and the level
> change together, with the map, the scrubber, and the hero's headline all in
> the first viewport at 1440×900; narrower, they stack. Nothing about what
> replay computes, stores, sends, or publishes changes.

**Branch:** `feature/phase08-step6-replay`

**Deploys:** nothing beyond merge — the operator's copy takes this step at Step
9.

Settings — ladder (`roadmodel ladder --category coding --complexity medium`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **GPT-6.1 Sol**    | **Gemini 4 Argon** |
|               | Platform | Codex              | Codex              | Antigravity        |
|               | Level    | Medium             | High               | High               |
|               | AA       | 47.8               | 50.2               | 52.6               |
|               | Price    | $2.50/1M           | $2.86/1M           | $6.13/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Sonnet 5.5**     | **Opus 5.5**       |
|               | Platform | Claude Code        | Claude Code        | Claude Code        |
|               | Level    | Medium             | High               | High               |
|               | AA       | 40.8               | 46.8               | 53.6               |
|               | Price    | $3.18/1M           | $3.40/1M           | $6.76/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **Gemini 4 Argon** | **GPT-6.1 Sol**    |
|               | Platform | Antigravity        | Antigravity        | Codex              |
|               | Level    | Low                | Medium             | High               |
|               | AA       | ≈45.2              | ≈49.8              | 50.2               |
|               | Price    | $2.31/1M           | $2.37/1M           | $2.86/1M           |

Ranked for coding, medium complexity. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level. ≈
estimated from the model's measured levels or its previous version's.

**Conversation:** New

**Model rationale:** Step 6 is coding with a multimodal secondary category — one
page's layout around components that already exist, a map whose container must
never be measured at zero, and a viewport assertion — at Medium complexity, not
novel: Decision 12 fixes the columns, and Steps 3 and 5 supplied the hero and
the panel pattern. On the step alone, the Quality Pick fits best: Gemini 4 Argon
on Antigravity at Effort High, with Thinking On, brings the strongest visual
judgement in this ladder to a two-column workbench that must balance at every
width. The Balanced Pick, GPT-6.1 Sol at Intelligence High on Codex, would
deliver the same structure at lower cost with less eye for the result, and the
Cost Pick, GPT-6.1 Sol at Medium, suits the plumbing better than the layout. The
conversation is new, per phase-boundary hygiene.

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
       feature/phase08-step6-replay`
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
       Phase 8 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 8`
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

    THIS STEP is layout only: the replay routes, `ReplayTimelines`, and
    what a scrub reads are unchanged, so a whole scrub still writes no
    row, publishes no event, sends no notification, and calls no AI
    (`replay.spec.ts` asserts no `/api/ai` request, no AI label, and no
    switch). The page adds no request and no inline style.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 8 (UI/UX redesign and visual
    dogfooding). Step 6: the replay workbench.

    Current state (as of Phase 7, post-Phase-8 Step 5):

    - `frontend/src/pages/Replay.tsx` is one column: header with `Replay
      storm` and `Replay location`, the corpus-disabled and no-locations
      states, `replay-banner`, the scrubber section (play and pause,
      `AdvisorySlider` with `showStoredBanner={false}`,
      `LevelHistoryChart` with `activeAsOf`, the replay notes), the map
      (`replay-leaflet-map`, whose wrapper is hidden while the timeline
      loads; `useLeafletMap` re-fits through its `ResizeObserver`, PR
      #105), and `replay-assessment-card`, which since Step 3 shows
      `LocationHero` and `WhyThisLevel` with the four shared components
      as children (Phase 7's check 49 reads their names in this file).
      `isPlaying` is derived, never set in an effect
      (`react-hooks/set-state-in-effect`).
    - `replay.spec.ts` (Phase 7's V7.4) scrubs Dorian at the Nassau
      landmark from advisory 1 to 24 (level 4, `hurricane_watch`) and 26
      (level 5, `hurricane_warning`, `HWR`), checks loaded tiles and an
      overlay larger than 100 by 100 pixels, and counts no AI label and
      no switch; `phase7.spec.ts` and `screens.spec.ts` open the page
      too. Step 5's map panels are the pattern for anything that floats
      over this map.

    Files to read (every file before drafting):

    - docs/roadmap/phase08-roadmap.md (Decisions 12 and 16, and this
      step) and docs/DESIGN.md.
    - frontend/src/pages/Replay.tsx and Replay.test.tsx;
      frontend/src/assessment/ (Step 3's components);
      frontend/src/charts/LevelHistoryChart.tsx;
      frontend/src/map/useLeafletMap.ts, AdvisorySlider.tsx, and Step
      5's panels.
    - frontend/e2e/replay.spec.ts, phase7.spec.ts, screens.spec.ts.
  </context>

  <goal>
    Lay `/replay` out as the workbench of Decision 12 and prove the
    first-viewport rule in a browser.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Layout: at 1280 px and wider, a two-column grid — left, the map
      (at least 60 percent of the viewport tall) with the scrubber
      (play, pause, the slider, the advisory's number and time) and
      `LevelHistoryChart` beneath it; right, a sticky column with
      `replay-banner`, `replay-assessment-card` (`LocationHero`, then
      `WhyThisLevel` with the replay notes), and the storm and location
      pickers above them. Below 1280 px: pickers, banner, map, scrubber,
      hero, chart, disclosure. The map's container is never `display:
      none` while mounted (a loading state overlays it instead), so
      Leaflet never measures it at zero, and the `ResizeObserver` keeps
      fitting it when the columns change.
    </requirement>

    <requirement>
      Behaviour stays: the page's `<h1>` "Replay" (`AppShell.test.tsx`,
      `replay.spec.ts`, and `screens.spec.ts` find it by its exact
      name), the "not live" banner's text and non-dismissible state, the
      corpus-disabled and no-locations states (restyled with `Callout`),
      play and pause, keyboard stepping on the slider, the chart's
      active marker following the scrubbed step, the location's
      evacuation order off for a past storm and said so in the hero, and
      no AI panel or switch.
    </requirement>

    <requirement>
      Tests: `Replay.test.tsx` updated for the structure (the hero and
      disclosure in the card, the banner, the scrubber, the chart, no
      switch); `replay.spec.ts` keeps its Dorian flow and gains, at
      1440×900, an assertion that the map, the slider, and the hero's
      headline each have a bounding box inside the first 900 pixels,
      and, at 390×844, that they stack in the stated order;
      `phase7.spec.ts` and `screens.spec.ts` stay green. The readability
      gate passes on `/replay`.
    </requirement>

    <requirement>
      `README.md`'s dashboard section describes the workbench;
      `CHANGELOG.md` notes the step. Filepath comment: every new Python,
      TypeScript, YAML, or Markdown file gets its repository-relative
      path as its first line where the file type accepts comments,
      matching the sibling files.
    </requirement>
  </requirements>
</task>
```

### Step 6 acceptance criteria

- At 1440×900, `/replay` shows the map, the scrubber, and the hero's headline
  together without scrolling, in two columns; at phone width they stack in the
  stated order.
- Scrubbing Dorian at the Nassau landmark reads level 4 at advisory 24 and level
  5 at advisory 26 in the hero, with `hurricane_watch`, `hurricane_warning`, and
  `HWR` in the card's disclosure.
- The map is never measured at zero; tiles and the overlay load in both layouts.
- `Replay.test.tsx`, `replay.spec.ts`, `phase7.spec.ts`, `screens.spec.ts`, and
  the readability gate pass; `Replay.tsx` still composes the four shared
  components.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — and a scrub still writes, publishes, sends, and asks
  nothing, per the project roadmap's "Security & privacy strategy".

---

## Step 7 — Sectioned settings and the secondary pages

**Status:** Not started

> **Goal:** Finish the pages a reader visits second. `frontend/src/ui/Tabs.tsx`
> implements the WAI-ARIA tabs pattern without Radix; `/settings` becomes five
> tabs — Locations, Notifications & Quiet Hours, AI & Budget, History &
> Retention, and Threat Ladder & About — bound to the URL hash (`#locations`,
> `#notifications`, `#ai`, `#retention`, `#about`, with `#disclaimer` opening
> About at the disclaimer); `/ask` gains four starter prompt chips that fill the
> question and never send it, and a conversation layout; and `/storms`,
> `/alerts`, and `/timeline` lead every card with words, keep codes in the
> disclosure pattern, and say what an empty list is waiting for. The readability
> gate's Settings renders become one per tab.

**Branch:** `feature/phase08-step7-settings-pages`

**Deploys:** nothing beyond merge — the operator's copy takes this step at Step
9.

Settings — ladder (`roadmodel ladder --category coding --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **Sonnet 5.5**     | **Gemini 4 Argon** | **Opus 5.5**       |
|               | Platform | Claude Code        | Antigravity        | Claude Code        |
|               | Level    | XHigh              | High               | XHigh              |
|               | AA       | 51.9               | 52.6               | 56                 |
|               | Price    | $3.72/1M           | $6.13/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **GPT-6.1 Sol**    | **Opus 5.5**       | **Gemini 4 Argon** |
|               | Platform | Codex              | Claude Code        | Antigravity        |
|               | Level    | High               | High               | High               |
|               | AA       | 50.2               | 53.6               | 52.6               |
|               | Price    | $2.86/1M           | $6.76/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **GPT-6 Astra**    | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Codex              | Codex              |
|               | Level    | Low                | High               | XHigh              |
|               | AA       | ≈45.2              | 50.9               | 52.4               |
|               | Price    | $2.31/1M           | $13.01/1M          | $17.73/1M          |

Ranked for coding, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels or its previous version's.

**Conversation:** New

**Model rationale:** Step 7 is coding with a multimodal secondary category — an
accessible tabs primitive bound to the hash, a page split five ways without
losing a deep link, chips, and three list pages, all judged by eye — at High
complexity for its breadth, not novel: Decisions 13 to 15 fix the tabs, the
chips' rule, and the lists' hierarchy. On the step alone, the Balanced Pick fits
best: Gemini 4 Argon on Antigravity at Effort High, with Thinking On, pairs
S-tier coding with the visual judgement five pages of hierarchy need. The
Quality Pick, Opus 5.5 at XHigh, adds depth the tabs' keyboard contract could
use but the rest does not; the Cost Pick, Sonnet 5.5 at XHigh, saves money with
less eye across five pages. The conversation is new, per phase-boundary hygiene.

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
       feature/phase08-step7-settings-pages`
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
       Phase 8 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 8`
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

    THIS STEP keeps every write where it was: the settings editors still
    save through `PUT /api/settings` with its allowlist, its SHA-256
    guard, and its refusals (Phase 7's check 25 keeps `EDITABLE` at 12
    keys), the location manager through its routes, and the AI controls
    through theirs, all same-origin. A chip writes text into the
    question box and sends nothing; a chat turn still costs only when
    the operator presses Ask. The hash names a tab, never data. No tab,
    chip, or list sets an inline style (`Settings.test.tsx`,
    `QuietHoursForm.test.tsx`, and `RetentionPanel.test.tsx` assert no
    `[style]`).
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 8 (UI/UX redesign and visual
    dogfooding). Step 7: sectioned settings and the secondary pages.

    Current state (as of Phase 7, post-Phase-8 Step 6):

    - `frontend/src/pages/Settings.tsx` is one column: header,
      file-problem and restart banners, `LocationManager`,
      `NotificationChannels`, `QuietHoursForm`, `AiSettingsSection`
      (`id="ai"`), `RetentionPanel`, the effective-settings table, the
      ladder card (from `GET /api/ladder` since Step 3), the full
      disclaimer (`id="disclaimer"`), and the licences. Phase 7's checks
      12, 23, and 32 require the four settings components and their
      tests at their paths. `Settings.test.tsx` renders every card at
      once, counts four AI rows, and asserts no `[style]`.
    - Links into the page: the footer's `/settings#disclaimer`;
      `ai.spec.ts`'s `/settings#ai` ("Allow $… more today");
      `locations.spec.ts` and `phase7.spec.ts` open `/settings` and
      expect the location manager; `phase7.spec.ts` and
      `screens.spec.ts` read the channels, quiet-hours, and retention
      cards in the same page load.
    - `frontend/src/pages/Ask.tsx` shows the engine's levels, the
      transcript (`list` "Transcript", `list` "Lookups", `chat-answer`),
      `About`, `Your question`, and `Ask`; `Ask.test.tsx` counts "Level
      1" twice. `Storms.tsx`, `Alerts.tsx`, and `Timeline.tsx` lead rows
      with codes and UTC times; `Storms.test.tsx` counts six credits and
      five "Interpret (AI)" buttons; `Timeline.tsx` holds
      `timeline-location-charts` and `timeline-show-older`.

    Files to read (every file before drafting):

    - docs/roadmap/phase08-roadmap.md (Decisions 13 to 16, and this
      step) and docs/DESIGN.md.
    - frontend/src/pages/Settings.tsx, Ask.tsx, Storms.tsx, Alerts.tsx,
      Timeline.tsx, OutlookGraphics.tsx, and their tests.
    - frontend/src/settings/ (every file and test),
      frontend/src/ai/AiSettingsSection.tsx, frontend/src/ai/useChat.ts.
    - frontend/src/app/AppShell.tsx (the footer link).
    - frontend/e2e/phase7.spec.ts, locations.spec.ts, ai.spec.ts,
      screens.spec.ts, charts.spec.ts, readability.spec.ts.
  </context>

  <goal>
    Ship the tabs primitive, the five-tab Settings page with its deep
    links, the Ask chips and layout, and the three list pages'
    hierarchy, with every spec that reads them updated.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      `frontend/src/ui/Tabs.tsx`: `Tabs`, `TabList`, `Tab`, and
      `TabPanel` implementing the WAI-ARIA tabs pattern —
      `role="tablist"` with an accessible name, `role="tab"` with
      `aria-selected`, `aria-controls`, and a roving `tabindex`,
      `role="tabpanel"` with `aria-labelledby` and `tabindex="0"`;
      ArrowLeft and ArrowRight move between tabs, Home and End go to the
      ends, and selection follows focus — controlled by a `value` and
      `onValueChange`, rendering only the active panel, and setting no
      inline style. `Tabs.test.tsx` covers the roles, the keys, and the
      absence of `[style]`.
    </requirement>

    <requirement>
      Settings: the banners stay above the tabs; the tabs and their
      hashes are Locations (`#locations`, the default when the hash is
      empty or unknown: `LocationManager`), Notifications & Quiet Hours
      (`#notifications`: `NotificationChannels`, `QuietHoursForm`), AI &
      Budget (`#ai`: `AiSettingsSection`, keeping `id="ai"`), History &
      Retention (`#retention`: `RetentionPanel`), and Threat Ladder &
      About (`#about`: the ladder, the effective-settings table, the
      full disclaimer with `id="disclaimer"`, and the licences). The
      selected tab is derived from the router's location
      (`useLocation().hash`), so loading `/settings#disclaimer`, or the
      footer's router `<Link to="/settings#disclaimer">` while already
      on the page (a router navigation fires no `hashchange`), selects
      About and scrolls the disclaimer into view; choosing a tab writes
      the hash through `useNavigate()` with `replace: true`, never a raw
      `history.replaceState`, which would leave the router's location
      stale, so a reload keeps the tab. On a phone the tab list scrolls
      horizontally inside itself, never the page.
    </requirement>

    <requirement>
      Ask (Decision 14): four chips above the question box, built from
      the chosen location's stored assessment and naming it only by its
      chosen name — why it is at its level, what to do at this level,
      when winds could arrive, and what the cone means for it; each chip
      is a button with `data-testid="ask-chip-<n>"` that writes its
      question into `Your question`, moves focus there, and sends
      nothing; chips are disabled while AI is not ready, with the state
      banner saying why. The conversation takes the new hierarchy: each
      question and answer as a bubble, lookups as chips under the
      answer, and the AI label on every answer
      (`data-testid="ai-label"`); the page's `<h1>` "Ask"
      (`AppShell.test.tsx`), the section headed "Conversation",
      `chat-answer`, the `Transcript` and `Lookups` lists, `About`, and
      `Ask` keep their names for `ai.spec.ts`.
    </requirement>

    <requirement>
      Storms, Alerts, Timeline (Decision 15): Storms leads each storm
      with its name, classification, intensity, and motion in words,
      with its identifiers, advisory number, and products in a
      `Disclosure`, and keeps the outlook graphics, their credits, and
      "Interpret (AI)"; Alerts leads each alert with its event and the
      location it covers, its expiry as a relative age with the local
      time, and its codes, zones, and how it was found in a
      `Disclosure`; Timeline leads each entry with the level change in
      the engine's words and the time as a relative age, with the
      entry's rule id, raw instants, and delivery details in a
      `Disclosure`, keeps the location charts and "Show older", and
      makes its filter the first control. Each page's empty state says
      what will appear and when.
    </requirement>

    <requirement>
      Specs and tests: `Settings.test.tsx` rewritten per tab inside a
      memory router (default Locations; each hash; `#disclaimer`,
      including a router navigation to it while the page is open; the
      keys; four AI rows on the AI tab; the ladder from the fixture; no
      `[style]`); `Ask.test.tsx` (chips fill and do not send; disabled
      when AI is not ready; the "Level 1" count updated),
      `Storms.test.tsx`, `Alerts.test.tsx`, and `Timeline.test.tsx`
      updated; `phase7.spec.ts` and `screens.spec.ts` reach each card
      through its tab (by clicking the tab or opening its hash),
      `locations.spec.ts` keeps its flow on the default tab, and
      `ai.spec.ts`'s `/settings#ai` still finds the allowance button;
      `readability.spec.ts`'s Settings renders become one per tab; and a
      new `frontend/e2e/settings-tabs.spec.ts` opens each hash, follows
      the footer's disclaimer link, reloads on a tab, and checks
      keyboard navigation. Every file keeps its path.
    </requirement>

    <requirement>
      `README.md`'s dashboard section names the tabs and the chips;
      `CHANGELOG.md` notes the step. Filepath comment: every new Python,
      TypeScript, YAML, or Markdown file gets its repository-relative
      path as its first line where the file type accepts comments,
      matching the sibling files.
    </requirement>
  </requirements>
</task>
```

### Step 7 acceptance criteria

- `/settings` shows five tabs that keyboard and pointer both operate, opens the
  right tab from each hash, opens About at the disclaimer from the footer link,
  and keeps the tab across a reload.
- The four settings components and their tests keep their paths and their saves;
  `Settings.test.tsx` finds no `[style]`.
- `/ask`'s chips fill the question and send nothing, are disabled while AI is
  not ready, and every answer carries its AI label.
- `/storms`, `/alerts`, and `/timeline` lead with words, keep codes and
  identifiers in disclosures, and explain their empty states.
- `settings-tabs.spec.ts`, every updated spec and test, and the readability gate
  (one render per tab) pass; Phase 5 to Phase 7's `--fast` pass.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — every write still goes through its guarded route, and
  no chip sends a request, per the project roadmap's "Security & privacy
  strategy".

---

## Step 8 — Loop 1: the AI visual dogfood

**Status:** Not started

> **Goal:** Look at every page the way a reader will, and fix what looks wrong
> until a whole round is clean. `frontend/e2e/dogfood.spec.ts`, tagged
> `@dogfood`, renders twelve views — every route, each Settings tab, `/replay`
> with its storm loaded — for each of the five scenarios at 1440×900 and 390×844
> in light and dark (240 renders), saves a full-page screenshot of each under
> `frontend/test-results/dogfood/`, runs the readability audit on each, and
> writes `audit.json`; `docs/phase08-dogfood.md` holds the rubric, the round
> log, and the defect ledger; the agent judges every screenshot against the
> rubric, logs and fixes each defect, and renders again until the exit rule of
> Decision 17 holds. The step also lands the whole-phase smoke
> `frontend/e2e/phase8.spec.ts`, proves each alarm the interface carries still
> fires in the new shell, and records the idle measurement.

**Branch:** `feature/phase08-step8-ai-dogfood`

**Deploys:** nothing beyond merge — the operator's copy takes this step at Step
9.

Settings — ladder (`roadmodel ladder --category multimodal --complexity high`):

|               |          | Cost                 | Balanced             | Quality                 |
| ------------- | -------- | -------------------- | -------------------- | ----------------------- |
| **Pick**      | Model    | **GPT-6.1 Sol**      | **GPT-6.1 Sol**      | **Fable 5.1**           |
|               | Platform | Codex                | Codex                | claude.ai web / desktop |
|               | Level    | Medium               | High                 | XHigh                   |
|               | AA       | 47.8                 | 50.2                 | 53.2                    |
|               | Price    | $2.50/1M             | $2.86/1M             | $21.38/1M               |
| **Runner‑up** | Model    | **Sonnet 5.5**       | **Sonnet 5.5**       | **GPT-6.1 Sol**         |
|               | Platform | Claude Code          | Claude Code          | Codex                   |
|               | Level    | High                 | XHigh                | XHigh                   |
|               | AA       | 46.8                 | 51.9                 | 51                      |
|               | Price    | $3.40/1M             | $3.72/1M             | $4.00/1M                |
| **Backup**    | Model    | **Gemini 3.8 Flash** | **Gemini 3.8 Flash** | **Gemini 3.8 Flash**    |
|               | Platform | Antigravity          | Antigravity          | Antigravity             |
|               | Level    | Low                  | Medium               | High                    |
|               | AA       | 33.5                 | 39.8                 | 40.9                    |
|               | Price    | $0.98/1M             | $1.99/1M             | $3.16/1M                |

Ranked for multimodal, high complexity. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level.

**Conversation:** New

**Model rationale:** Step 8 is multimodal with a coding secondary category —
investigating screenshots and fixing the layouts they show, the selector's own
example of that pairing, here 240 renders a round across five scenarios, two
viewports, and two themes, with a computed audit beside each — at High
complexity, not novel: Decision 17 fixes the harness, the rubric's items, and
the exit rule. On the step alone, the Balanced Runner-up fits best: Sonnet 5.5
on Claude Code at Effort XHigh, funded by the claude.ai Max subscription (it
always thinks, so there is no Thinking dial), opens each screenshot with the
same tools that run the harness and edit the code, so a round is one session.
The Balanced Pick, GPT-6.1 Sol at Intelligence High on Codex, does the same loop
at a lower price; the Quality Pick, Fable 5.1, runs on claude.ai's web and
desktop apps, which have no terminal or codebase tools, so it could judge only
screenshots pasted into it by hand; and the Cost Pick, GPT-6.1 Sol at Medium,
has less margin for a long run of visual judgements. The conversation is new,
per phase-boundary hygiene.

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
       feature/phase08-step8-ai-dogfood`
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
       Phase 8 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 8`
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
       complete. You can now move
       on to Step 9." That
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
       one before Step 9.
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

    THIS STEP produces evidence, and the evidence stays clean: the
    harness runs only against the demonstration servers in temporary
    data directories, so every screenshot and `audit.json` holds the
    public landmarks and the synthetic storm and nothing of the
    operator's; neither is committed (Decision 18;
    `frontend/test-results/` is git-ignored), and the ledger names
    screenshots by key. Fixes are presentation changes under every
    earlier rule — no `style=`, no markup from text, no new package, no
    CSP change — and the guard still fails any foreign request, page
    error, CSP event, or coordinate or AI text in the console.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 8 (UI/UX redesign and visual
    dogfooding). Step 8: Loop 1, the AI visual dogfood.

    Current state (as of Phase 7, post-Phase-8 Step 7):

    - Every page is redesigned: the tokens, primitives, and shell (Step
      2), the vocabulary, hero, meter, and disclosure (Step 3), the
      dashboard (Step 4), the map (Step 5), the replay workbench (Step
      6), and Settings, Ask, Storms, Alerts, and Timeline (Step 7).
      `readability.spec.ts` runs the four-check audit in CI on the
      `quiet` and `landfall` servers; findings outside a step's own
      pages were logged in `docs/phase08-dogfood.md` by the steps that
      saw them (the Triage rule).
    - `frontend/playwright.config.ts` starts 8799, 8800, 8801, 8802
      (`quiet`), and 8806 (`landfall`); 8803 to 8805 (`outlook`, `cone`,
      `watch`) are reserved. `isIdleRun` shows how a tagged run changes
      the configuration; `grepInvert` excludes `@idle` from default
      runs.
    - The interface carries four alarms and the toasts: the
      stale-monitor banner and the reconnecting chip (`AppShell.tsx`),
      `AiStateBanner`, and the radar and satellite unavailable banners;
      `ai.spec.ts`'s capped server, `phase7.spec.ts`'s aborted nowCOAST
      route, `dashboard.spec.ts`'s toast, and Step 5's
      `MapView.test.tsx` cases already reach several of them. The guard
      fails foreign requests, page errors, CSP events, and coordinates
      or AI text in the console, but not a console error or an HTTP
      status.
    - `scripts/measure_idle.py` measures `/` for 600 seconds; the budget
      is 0.5 percent each side.

    Files to read (every file before drafting):

    - docs/roadmap/phase08-roadmap.md (Decisions 6, 17, and 18, the
      scenario table, and this step), docs/DESIGN.md, and
      docs/phase08-dogfood.md (started in Step 2, with the defects Steps
      2 to 7 carried).
    - frontend/playwright.config.ts, frontend/package.json (scripts),
      frontend/e2e/guard.ts, readability.ts, readability.spec.ts,
      screens.spec.ts, scenarios.spec.ts, phase7.spec.ts.
    - frontend/src/app/AppShell.tsx and AppShell.test.tsx,
      frontend/src/ai/AiStateBanner.tsx.
    - scripts/serve_demo.py (the scenario flags) and
      scripts/measure_idle.py.
  </context>

  <goal>
    Build the dogfood harness and the ledger, run Loop 1 to a clean
    round, and land the whole-phase smoke, the alarm proofs, and the
    idle receipt.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Harness: `frontend/e2e/dogfood.spec.ts`, every test tagged
      `@dogfood`, one test per scenario, viewport, and theme — twenty
      tests, each visiting the twelve views at its viewport (1440×900 or
      390×844) and theme on its scenario's server (`test.use({ baseURL
      })`, so the guard follows), with a raised `test.setTimeout`,
      because the configuration's 120 seconds would not hold twelve
      full-page renders and audits — waiting for each view's ready
      marker, saving a full-page screenshot under
      `frontend/test-results/dogfood/`, in one folder per scenario,
      viewport, and theme and named by view, running `auditReadability`,
      appending to `frontend/test-results/dogfood/audit.json`, and
      failing at its end, listing everything, if any finding exists.
      `frontend/playwright.config.ts` starts the `outlook`, `cone`, and
      `watch` servers (8803 to 8805) only for a `@dogfood` run and
      excludes `@dogfood` from the default run, as it does `@idle`;
      `frontend/package.json` gains `"e2e:dogfood": "playwright test
      --grep @dogfood"` and keeps every existing script (Phase 5's check
      27). No spec uses `toHaveScreenshot`.
    </requirement>

    <requirement>
      Ledger (`docs/phase08-dogfood.md`, which keeps Step 2's carried
      table, every carried defect either fixed in a round or owned by an
      issue): the rubric — hierarchy (one primary headline per card, the
      level legible within a second), vocabulary (the engine's words, no
      code in a headline), colour (threat tints only for threat, never
      the only signal), type (the scale, nothing smaller than a
      caption), spacing rhythm and alignment, density (no wall of text,
      no crowding at phone width), empty, loading, and error states, the
      phone layout (no overlap, nothing cut off, targets at least 24
      pixels), dark-theme parity, the map's panels (the storm never
      hidden), focus visibility, and the disclaimer present — each with
      what passes and what fails; severities (blocker: wrong or missing
      information or an unusable control; major: a reader misreads or
      struggles; minor: visibly off but readable; polish: taste); the
      round log (date, commit, renders judged, audit findings, defects
      by severity); the defect table (id, key, rubric item, severity,
      what was wrong, the commit that fixed it, or the issue that owns
      it); and an empty Loop 2 section Step 9 fills.
    </requirement>

    <requirement>
      Loop: run the harness, open and judge every screenshot of the
      round against the rubric (not a sample), log each defect, fix it
      in this branch, and render again. A round ends when all 240
      screenshots are judged. The loop ends after a full round that logs
      no blocker, major, or minor defect while `audit.json` holds no
      finding; polish items are either fixed or listed for the
      operator's review in Step 9. Each round's line in the log names
      its commit. Fixes keep every spec and test green, and every file
      an earlier check names keeps its path.
    </requirement>

    <requirement>
      Whole-phase smoke: `frontend/e2e/phase8.spec.ts` (default run,
      `landfall` server) walks the redesigned surface in one browser
      flow — the dashboard's bar, popover, switcher, hero, tiles, and
      mini-map; opening a disclosure to the evacuation-order switch; the
      map's panels collapsing and reopening; the replay workbench
      scrubbed to a level change; each Settings tab by its hash; a chip
      filling the Ask box without a request to `/api/ai/chat`; and the
      three list pages' headlines — with no console error (recorded and
      asserted by the spec, since the guard does not) and no CSP event,
      page error, or foreign request (the guard's).
    </requirement>

    <requirement>
      Alarms in the new shell: `AppShell.test.tsx` proves the
      stale-monitor banner (from a stale health answer, `role="alert"`,
      naming the stale heartbeat) and the reconnecting chip (from the
      event stream's reconnecting state); `ai.spec.ts`'s capped server
      proves `AiStateBanner`; `phase7.spec.ts` proves the radar banner
      in a browser and Step 5's `MapView.test.tsx` cases prove both the
      radar and the satellite banner; `dashboard.spec.ts` proves the
      toast. Each passes against the redesigned components, and the
      ledger lists where each alarm is proved.
    </requirement>

    <requirement>
      Idle: run `uv run python scripts/measure_idle.py` on this machine
      after the last fix and record its line in the ledger and the PR
      body; both shares stay under 0.5 percent. `CHANGELOG.md` notes the
      step. Filepath comment: every new Python, TypeScript, YAML, or
      Markdown file gets its repository-relative path as its first line
      where the file type accepts comments, matching the sibling files.
    </requirement>
  </requirements>
</task>
```

### Step 8 acceptance criteria

- `npm --prefix frontend run e2e:dogfood` renders all 240 views across the five
  scenarios, two viewports, and two themes, and `audit.json` holds no finding.
- `docs/phase08-dogfood.md` holds the rubric, every round's log line, and every
  defect with its fix commit or owning issue; the last full round logs no
  blocker, major, or minor defect.
- `phase8.spec.ts` passes in the default run; each interface alarm is proved
  against the redesigned shell, and the ledger says where.
- The idle measurement reads both shares under 0.5 percent, recorded in the
  ledger.
- The default Playwright run, Vitest, and Phase 5 to Phase 7's `--fast` pass; no
  committed file holds a screenshot.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — and every screenshot and audit came from a
  demonstration server, per the project roadmap's "Security & privacy strategy".

---

## Step 9 — Loop 2: the operator's dogfood

**Status:** Not started

> **Goal:** Put the redesign in front of the person it is for and keep at it
> until they say it is ready. The operator walks every page in their own browser
> on this machine, one scenario per round, on demonstration servers started from
> this step's branch; each item of feedback goes into `docs/phase08-dogfood.md`
> in the operator's words with its disposition, the fixes land in this branch
> with the readability gate and every spec green, and the loop ends only at the
> operator's explicit sign-off, recorded with its date. Then the pull request
> merges, the operator's service is upgraded with their yes, and its
> `/api/health` reports the redesigned build.

**Branch:** `feature/phase08-step9-operator-dogfood`

**Deploys:** the operator's local service (`\Weatherbot\serve` under Task
Scheduler, the installed `weatherbot` tool) → the operator's Windows machine,
after the merge and the operator's yes: `schtasks /End`, `npm ci` and the build,
`uv tool install --reinstall --from <checkout> weatherbot`, and `/Run`, away
from HH:25. No revision, so no migration.

Settings — ladder (`roadmodel ladder --category agentic --complexity high`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **Sonnet 5.5**     | **Opus 5.5**       |
|               | Platform | Codex              | Claude Code        | Claude Code        |
|               | Level    | Medium             | XHigh              | XHigh              |
|               | AA       | 47.8               | 51.9               | 56                 |
|               | Price    | $2.50/1M           | $3.72/1M           | $8.29/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **GPT-6.1 Sol**    | **Gemini 4 Argon** |
|               | Platform | Claude Code        | Codex              | Antigravity        |
|               | Level    | High               | XHigh              | High               |
|               | AA       | 46.8               | 51                 | 52.6               |
|               | Price    | $3.40/1M           | $4.00/1M           | $6.13/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **Gemini 4 Argon** | **GPT-6 Astra**    |
|               | Platform | Antigravity        | Antigravity        | Codex              |
|               | Level    | Low                | Medium             | XHigh              |
|               | AA       | ≈45.2              | ≈49.8              | 52.4               |
|               | Price    | $2.31/1M           | $2.37/1M           | $17.73/1M          |

Ranked for agentic, high complexity. Price: list $ per 1M tokens (3 in : 1 out),
the output part scaled by the tokens the model writes at that level. ≈ estimated
from the model's measured levels or its previous version's.

**Conversation:** New

**Model rationale:** Step 9 is agentic with a coding secondary category — a long
session paced by the operator, several rounds of judgement on feedback that is
often about taste, fixes across pages under every earlier rule, background
servers to start and stop, and an on-machine deployment — at High complexity,
not novel: Decisions 17 and 19 fix the protocol, the exit, and the deploy. On
the step alone, the Quality Pick fits best: Opus 5.5 on Claude Code at Effort
XHigh, funded by the claude.ai Max subscription (it always thinks, so there is
no Thinking dial), turns loosely worded feedback into the right change with the
least back-and-forth, and the operator's time is this step's scarcest input. The
Balanced Pick, Sonnet 5.5 at XHigh, runs the same loop at lower cost with a
little less judgement per round; the Cost Pick, GPT-6.1 Sol at Intelligence
Medium on Codex, suits the mechanics better than the design conversation. The
conversation is new, per phase-boundary hygiene.

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
       feature/phase08-step9-operator-dogfood`
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
       Phase 8 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 8`
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
       shape "Step 9 is
       complete. You can now move
       on to Step 10." That
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
       one before Step 10.
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

    THIS STEP touches the operator's machine twice, and both times only
    with a yes. The walkthrough runs demonstration servers in temporary
    data directories on loopback ports, so the operator sees only the
    landmarks and the synthetic storm, and no screenshot or text of the
    operator's own service is captured, logged, or committed; the ledger
    records the operator's feedback about the pages, never their places.
    Every server this step starts runs in the background and is stopped
    before the step ends. The deploy reinstalls from this checkout,
    restarts the task, and is read back only through `/api/health` and
    `doctor`; no credential, topic, or setting is touched.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 8 (UI/UX redesign and visual
    dogfooding). Step 9: Loop 2, the operator's dogfood.

    Current state (as of Phase 7, post-Phase-8 Step 8):

    - Loop 1 ended on a clean round: `docs/phase08-dogfood.md` holds the
      rubric, the round log, the defect table, any polish items left for
      the operator, and an empty Loop 2 section. `npm --prefix frontend
      run e2e:dogfood`, the readability gate, the whole-phase smoke, and
      the idle receipt are green on `main`.
    - Demonstration servers: `uv run python scripts/serve_demo.py --port
      8799` (the default), and `--scenario
      quiet|outlook|cone|watch|landfall` on 8802 to 8806; each serves
      the built interface from `src/weatherbot/web/static`, so a fix to
      the frontend needs `npm --prefix frontend run build` and a restart
      of the servers before the operator looks again.
    - The operator's service runs Phase 7's build (`ui.index_sha256`
      `79fabd1a5019`) under `\Weatherbot\serve`, with
      `\Weatherbot\check` hourly at HH:25 and the database at `0010`.
      The installed tool is `C:\Users\Admin\.local\bin\weatherbot.exe`;
      bare `weatherbot` on `PATH` is version 1. The operator often
      reaches this machine from another computer, where a dialog raised
      on the Windows desktop may never be seen.

    Files to read (every file before drafting):

    - docs/roadmap/phase08-roadmap.md (Decisions 17, 19, and 20, and
      this step), docs/phase08-dogfood.md, and docs/DESIGN.md.
    - scripts/serve_demo.py (the flags) and frontend/package.json (the
      scripts).
    - docs/roadmap/phase07-roadmap.md, Step 9 (the deploy recipe Phase 7
      used).
  </context>

  <goal>
    Run Loop 2 to the operator's explicit sign-off, merge, deploy to the
    operator's service with their yes, and verify it there.
  </goal>

  <requirements>
    <requirement>
      Read all files listed in context before making any changes.
    </requirement>

    <requirement>
      Walkthrough: build the interface, start the default and the five
      scenario servers in the background from this branch, and give the
      operator, in the chat before any question, the six addresses and a
      short checklist for the round (the pages to open, the levels each
      scenario should show, and the questions the rubric asks); then
      ask, with AskUserQuestion, whether they have looked and what they
      want changed. One scenario leads each round, and every page is
      walked at least once across the rounds, on the operator's usual
      screen and, if they wish, at phone width. Never open a window on
      the operator's desktop without a yes.
    </requirement>

    <requirement>
      Feedback: each item goes into the Loop 2 section of
      `docs/phase08-dogfood.md` in the operator's words, with its round,
      the page, and its disposition — fixed (the commit), declined with
      the reason the operator accepted, or owned by an issue the agent
      opened. Fixes follow every earlier rule (no new package, no
      `style=`, no markup from text, no CSP change, every pinned path
      and literal kept), keep the readability gate, the default
      Playwright run, Vitest, and the dogfood harness's audit green, and
      are rebuilt and re-served before the next round. A fix that would
      change a decision of this roadmap is the operator's call, recorded
      in the roadmap in this PR.
    </requirement>

    <requirement>
      Exit: the loop ends only when the operator says, in the chat, that
      the web app is ready to release; their words and the date go into
      the ledger's sign-off line. Then stop every server this step
      started and confirm with a process check, keyed on the process ids
      it recorded, that none remains.
    </requirement>

    <requirement>
      Merge and deploy: open the PR (the ledger, the fixes), mark the
      step, wait for green checks, and squash-merge. Then, after the
      operator's yes and away from HH:25: `schtasks /End /TN
      "\Weatherbot\serve"`; on the merged `main`, `npm --prefix frontend
      ci` and `npm --prefix frontend run build`; `uv tool install
      --reinstall --from <checkout> weatherbot`; `schtasks /Run /TN
      "\Weatherbot\serve"`. If `/` changed in Loop 2, run `uv run python
      scripts/measure_idle.py` again and record its line in the ledger.
    </requirement>

    <requirement>
      Deployed & verified: `GET http://127.0.0.1:8765/api/health`
      answers with `ui.index_sha256` equal to the first twelve
      hexadecimal digits of the SHA-256 of the built
      `src/weatherbot/web/static/index.html`, the database current at
      `0010`, and `corpus` as the operator had it;
      `C:\Users\Admin\.local\bin\weatherbot.exe doctor --offline --json`
      passes its `web` check; and the operator, asked with
      AskUserQuestion after being told what to open, confirms the
      redesigned dashboard shows their own locations. The agent never
      captures the operator's page.
    </requirement>
  </requirements>
</task>
```

### Step 9 acceptance criteria

- The operator walked every page across the rounds; every item of feedback is in
  `docs/phase08-dogfood.md` with its disposition.
- The ledger records the operator's explicit sign-off with its date.
- Every fix kept the readability gate, the default Playwright run, Vitest, and
  the dogfood audit green, and every pinned path and literal.
- Every server the step started is stopped.
- **Deployed & verified:** the operator's `/api/health` reports
  `ui.index_sha256` equal to the merged build's, the database at `0010`, and
  `doctor --offline --json` passes `web`; the operator confirmed the redesigned
  dashboard shows their locations.
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff — secret/personal-data scan clean, SAST clean,
  dependency audit clean — and nothing of the operator's service or places was
  captured, logged, or committed, per the project roadmap's "Security & privacy
  strategy".

---

## Step 10 — QA & Verification Script

**Status:** Not started

> **Goal:** Package the verification matrix into `scripts/verify_phase08.py`
> (with `--fast`, `--py`, `--node`, `--ui`, `--live`, `--security`, `--all`, and
> `--post` modes), produce `docs/phase08-qa-findings.md`, add `"08"` to the
> `phase-verify.yml` matrix beside `"01"` to `"07"`, and close the phase. The
> script reads every Step 1 through Step 9 deliverable with standard-library
> static checks and builds the V1–V10 matrix from JUnit evidence: the offline
> pytest run with its coverage floors, the frontend's commands and Vitest run,
> and the default Playwright run; in `--post` on the operator's machine it adds
> Phase 7's own `--post` sweep, the dogfood harness with its audit, the
> operator's service, and the idle measurement. The closure marks Phase 8
> complete in both roadmaps and in `README.md`, names the checks Phase 9 must
> keep or convert, and tags `v2.0.0-phase-8`.

**Branch:** `feature/phase08-step10-verify`

**Deploys:** GitHub Actions → `phase-verify (08)` runs on every push and pull
request from the merge on, under the required aggregate `phase-verify`; its
first run on `main` must be green, and the annotated `v2.0.0-phase-8` tag must
peel to the merge commit.

Settings — ladder (`roadmodel ladder --category coding --complexity medium`):

|               |          | Cost               | Balanced           | Quality            |
| ------------- | -------- | ------------------ | ------------------ | ------------------ |
| **Pick**      | Model    | **GPT-6.1 Sol**    | **GPT-6.1 Sol**    | **Gemini 4 Argon** |
|               | Platform | Codex              | Codex              | Antigravity        |
|               | Level    | Medium             | High               | High               |
|               | AA       | 47.8               | 50.2               | 52.6               |
|               | Price    | $2.50/1M           | $2.86/1M           | $6.13/1M           |
| **Runner‑up** | Model    | **Sonnet 5.5**     | **Sonnet 5.5**     | **Opus 5.5**       |
|               | Platform | Claude Code        | Claude Code        | Claude Code        |
|               | Level    | Medium             | High               | High               |
|               | AA       | 40.8               | 46.8               | 53.6               |
|               | Price    | $3.18/1M           | $3.40/1M           | $6.76/1M           |
| **Backup**    | Model    | **Gemini 4 Argon** | **Gemini 4 Argon** | **GPT-6.1 Sol**    |
|               | Platform | Antigravity        | Antigravity        | Codex              |
|               | Level    | Low                | Medium             | High               |
|               | AA       | ≈45.2              | ≈49.8              | 50.2               |
|               | Price    | $2.31/1M           | $2.37/1M           | $2.86/1M           |

Ranked for coding, medium complexity. Price: list $ per 1M tokens (3 in : 1
out), the output part scaled by the tokens the model writes at that level. ≈
estimated from the model's measured levels or its previous version's.

**Conversation:** New

**Model rationale:** Step 10 is coding with an agentic secondary category at
Medium complexity, not novel: a mechanical translation of this roadmap's
acceptance criteria into a verification script, a matrix entry, and a findings
rollup, on a template six phases old, with one long nested sweep to run and
time. On the step alone, the Balanced Pick fits best: GPT-6.1 Sol on Codex at
Intelligence High, funded by the ChatGPT subscription, handles a long,
enumerated translation reliably at a moderate price. The Quality Pick, Gemini 4
Argon at High, has depth a known pattern does not need, and the Cost Pick,
GPT-6.1 Sol at Medium, has less margin over sixty checks and their mutation
cases. The conversation is new, per phase-boundary hygiene.

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
       feature/phase08-step10-verify`
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
       Phase 8 `**Status:**` to
       `In progress`; on the final
       step, both to `Complete`,
       with ` ✅` appended to this
       roadmap's `# ` title and to
       the parent's `### Phase 8`
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
       shape "Step 10 is
       complete. Phase 8 is
       complete. You can now move
       on to Phase 9." That
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
       one before Phase 9.
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

    THIS STEP also AUTHORS the `--security` verify mode, so its own diff
    must still pass the gate before commit. `--security` runs both
    stacks' gates (gitleaks, bandit over `src` and `scripts`, `pip-audit
    --strict`, the personal-data check over every tracked file, `npm
    audit --audit-level=high`, and ESLint with `eslint-plugin-security`)
    and scans every text file under Phase 8's paths for key and token
    shapes, built at run time so the script holds none. `--post` reads
    the operator's service only through `/api/health` and `doctor`,
    passes the operator's secrets only to the nested Phase 7 sweep's
    child process (from `HKCU\Environment`, as Phase 7 did), and says so
    before it starts; it runs the dogfood harness only against the
    demonstration servers.
  </security>

  <context>
    Weatherbot, version 2 rewrite. Phase 8 (UI/UX redesign and visual
    dogfooding). Step 10: QA and the verification script.

    Steps 1 through 9 have been implemented. Now create the verification
    script, the QA findings document, and the CI matrix entry, and close
    the phase.

    Reference scripts (pattern templates):

    - scripts/verify_phase07.py (the closest structural precedent:
      modes, `Select`, JUnit evidence, `tagged`, the nested sweep, the
      summary block).
    - scripts/verify_phase06.py (secondary reference).

    Facts the script must honour (the Verification surfaces audit in
    this roadmap):

    - Each phase's `--post` pins the last phase's total: Phase 8 nests
      `verify_phase07.py --post` and passes only at `"107"` (`passed
      107`, `failed 0`, `skipped 0`), with the operator's secrets from
      `HKCU\Environment` in the child's environment only. Phases 5 to 7
      each rerun the frontend suites and a 600-second idle window, so
      the nested sweep is long: time it once, record it in the QA
      document, and set the nested timeout to at least one and a half
      times it, never below 14400 seconds.
    - Every frontend selection is file-level
      (`Select("src/pages/Dashboard.test.tsx")`,
      `Select("map.spec.ts")`); a selected file must exist and hold at
      least one test, all passing and none skipped.
    - `phase-verify.yml`'s matrix is one line, and Phases 5 to 7's
      checks read their Node steps verbatim: append `"08"` at the end of
      the line and add `Set up Node (Phase 8)` and `Install frontend
      dependencies (Phase 8)` under `if: "!cancelled() && matrix.phase
      == '08'"`, pinned
      `actions/setup-node@949feb2413d6458794dcd2491c4babbbce0c15c1 #
      v7.1.0`, touching nothing else.
    - The operator probes of Phases 5 to 7 need the operator's service
      on the checkout's final build (Phase 5's V7.4) and a settled
      briefing among its last 100 AI calls (Phase 6's V6.5): if this
      step changes the frontend, redeploy first with the operator's yes,
      and if no briefing is among the last 100 calls, ask the operator
      to press Brief me once (a few cents) before `--post`.

    Phase 8 deliverables to verify (54 static checks across Steps 1
    through 9 plus 6 Step 10 self-checks, 60 in all):

    Step 1 (scenarios) — checks 1–7:
    1. `scripts/demo_storm.py` and `scripts/demo_scenarios.py` tracked;
       `SCENARIOS` names `quiet`, `outlook`, `cone`, `watch`,
       `landfall`.
    2. The scenarios' declared expectations equal Decision 2's table
       (read from their literal by AST).
    3. `serve_demo.py` holds `"--scenario"` with the five choices beside
       `"--switch-file"`, and still defines `DemoReplay`,
       `request_kind`, `chat_round`, and `demo_claude` at top level.
    4. No coordinate in `demo_storm.py` or `demo_scenarios.py` carries
       three or more decimals, their staged answers carry the synthetic
       label in their own fields, and no file under `src/` names a
       synthetic source.
    5. `playwright.config.ts` holds `"8802"` and `"8806"` beside
       `"8799"`, `"8800"`, `"8801"`; `frontend/e2e/scenarios.spec.ts`
       tracked.
    6. `tests/scripts/test_demo_scenarios.py` and `test_demo_storm.py`
       tracked; `record_ai_fixtures.py` holds `--scenario` and registers
       the scenario cases; `tests/fixtures/ai/manifest.json` lists the
       scenario recordings (ten briefings, two summaries), unless Step
       1's PR recorded the operator's decline.
    7. `verify_phase07.py`'s check 59 reads `tagged("README.md",
       tag=PHASE_7_TAG)` (AST) with its two mutation cases in
       `tests/test_phase07_verification.py`.

    Step 2 (design system) — checks 8–16:
    8. `index.css`'s `@theme` sets `--text-sm` 0.9375rem, `--text-base`
       1.0625rem, and `--text-caption` 0.8125rem.
    9. No tracked `.ts` or `.tsx` under `frontend/src` holds `text-xs`
       or an arbitrary font size (`text-[` and a length).
    10. `eslint.config.js` holds the `no-restricted-syntax` type rule.
    11. The `frontend/src/ui/` primitives and their tests tracked;
        `Disclosure.tsx` renders `<details` and imports no Radix.
    12. `NAV_ITEMS` holds eight one-line objects with `icon` after
        `label`, in order, and the badges are described through
        `aria-describedby`.
    13. `docs/DESIGN.md` tracked with its token, primitive, type,
        vocabulary, readability, accessibility, and CSP sections.
    14. `frontend/e2e/readability.ts` exports `auditReadability`;
        `readability.spec.ts` names 1440, 1280, and 360 and the ports
        8802 and 8806.
    15. The audit's unit test of contrast tracked.
    16. `docs/phase08-dogfood.md` tracked with its carried-findings
        table.

    Step 3 (plain English) — checks 17–24:
    17. `services/ladder.py` defines `ladder_reference`;
        `web/routes/ladder.py` defines a sync `def` for `/api/ladder`,
        registered in `web/app.py`; the web layer imports no engine
        module.
    18. `docs/api/openapi.json` holds `/api/ladder` and
        `LadderResponse`; `frontend/src/test/fixtures/ladder.json`
        tracked.
    19. `keys.ts` holds `invalidatableQueryKey("settings", "ladder")`.
    20. `frontend/src/assessment/` holds `vocabulary.ts`,
        `ThreatMeter.tsx`, `LocationHero.tsx`, and `WhyThisLevel.tsx`
        with tests.
    21. `WhyThisLevel.tsx` uses the native disclosure and holds "Why
        this level / Official provenance & controls".
    22. `Settings.tsx` holds no `LADDER_RULES`; nothing under
        `frontend/src` holds `tropical_storm_cone`, "Extreme Wind
        Warning", "Storm Surge Warning", or "Storm Surge Watch".
    23. `ThreatLevelBadge.tsx` holds none of the old fallback names
        ("Storm Watch", "Awareness", "Hurricane Warning / Evacuation",
        "Tropical Storm Warning / Hurricane Watch").
    24. `tests/services/test_ladder_reference.py`,
        `tests/web/test_ladder_route.py`, and
        `frontend/e2e/plain-english.spec.ts` tracked.

    Step 4 (dashboard) — checks 25–30:
    25. `frontend/src/dashboard/` holds `StatusBar.tsx`,
        `ExportPopover.tsx`, `LocationSwitcher.tsx`,
        `FeaturedLocation.tsx`, and `MiniMap.tsx`.
    26. The countdown uses `setTimeout` and `document.hidden` (or
        `visibilitychange`) and no `setInterval`.
    27. `ExportPopover.tsx` imports `Popover` from `radix-ui` and holds
        `export-report-all` and "Include the AI briefing".
    28. `MiniMap.tsx` calls `useLeafletMap` and adds no tile layer of
        its own.
    29. `Dashboard.tsx` holds `level-live-region` and a `Dashboard`
        heading.
    30. `frontend/e2e/command-center.spec.ts` tracked.

    Step 5 (map) — checks 31–35:
    31. `MapView.tsx` holds none of `replay-panel`,
        `replay-storm-select`, `replay-advisory-select`,
        `replay-not-live-banner`.
    32. The map's panels hold `aria-expanded`, "Map layer toggles", "Map
        legend", and a 70vh minimum height; `layers.ts` holds
        `LAYER_GROUPS`; and `advisory-slider-panel` appears in exactly
        one non-test file under `frontend/src`, `AdvisorySlider.tsx`.
    33. `map.spec.ts` tracked, holds `leaflet-map-container` and no
        `replay-storm-select`.
    34. `MapView.tsx` (or the status chip) links to `/replay`.
    35. Nothing under `frontend/src/map/` imports a Radix `Popover` or
        `Dialog`.

    Step 6 (replay) — checks 36–38:
    36. `Replay.tsx` holds `LocationHero` and `WhyThisLevel` and an
        `xl:` two-column grid.
    37. `replay.spec.ts` holds a 1440×900 viewport and a bounding-box
        assertion.
    38. `frontend/src/pages/Replay.test.tsx` tracked.

    Step 7 (settings and pages) — checks 39–44:
    39. `frontend/src/ui/Tabs.tsx` holds `role="tablist"`, `role="tab"`,
        `role="tabpanel"`, and `aria-selected`, imports no Radix, and
        `Tabs.test.tsx` is tracked.
    40. `Settings.tsx` holds the hashes `locations`, `notifications`,
        `ai`, `retention`, `about`, and `disclaimer`, reads
        `useLocation` and writes with `replace: true`, holds no
        `history.replaceState`, and still imports the four settings
        components.
    41. `Ask.tsx` holds the starter chips (`data-testid` prefix
        `ask-chip`).
    42. `Storms.tsx`, `Alerts.tsx`, and `Timeline.tsx` use the
        disclosure primitive.
    43. `frontend/e2e/settings-tabs.spec.ts` tracked.
    44. `readability.spec.ts` names each Settings hash.

    Step 8 (Loop 1) — checks 45–50:
    45. `frontend/e2e/dogfood.spec.ts` tracked, every test tagged
        `@dogfood`, naming the five scenarios, 1440×900 and 390×844, and
        both themes.
    46. `playwright.config.ts` excludes `@dogfood` from default runs and
        starts 8803 to 8805 only for it; `package.json` holds
        `e2e:dogfood`.
    47. `docs/phase08-dogfood.md` holds the rubric, the round log, the
        defect table, a last full round with no blocker, major, or minor
        defect, and an idle line with `budget=<0.5%`.
    48. `frontend/e2e/phase8.spec.ts` tracked.
    49. No image is tracked under `frontend/` except the existing
        `frontend/e2e/blank-tile.png` and `frontend/public/` assets.
    50. `AppShell.test.tsx` covers the stale banner and the reconnecting
        chip.

    Step 9 and the closure — checks 51–54 (51 from Step 9, 52 from this
    step's closure, 53 from the roadmap's own PR, 54 from Steps 4 to 7):
    51. `docs/phase08-dogfood.md`'s Loop 2 section holds at least one
        round and a sign-off line with a date.
    52. `README.md`'s `## Status` names Phase 8 (UI/UX redesign and
        visual dogfooding) complete and Phase 9 (Release 2.0) next, and
        `CHANGELOG.md` holds `### Phase 8 — UI/UX redesign and visual
        dogfooding`.
    53. `docs/roadmap/ROADMAP.md`'s "Release & tagging" table lists
        `v2.0.0-phase-8`.
    54. `README.md`'s `### The dashboard` section names the switcher,
        the map's panels, the replay workbench, and the Settings tabs.

    Step 10 self-checks — checks 55–60:
    55. `scripts/verify_phase08.py` self-check: 60 static checks, 38 V
        rows, eight mode flags, and the nested total `"107"`.
    56. `docs/phase08-qa-findings.md` exists with every rollup section.
    57. `docs/roadmap/phase08-roadmap.md` exists (this document) with
        `## Step 1 —` to `## Step 10 —`.
    58. `phase-verify.yml`'s one-line matrix begins `"01"` to `"08"`,
        with separate Node steps for `'08'` and the `'05'`, `'06'`, and
        `'07'` steps untouched.
    59. The security gate is wired: the pre-commit hooks, the
        `--security` step, and no key or token shape in any text file
        under Phase 8's paths.
    60. No binary file under `frontend/src` or `src/weatherbot/web/` (so
        Phase 5's and Phase 6's text scans keep reading every file).

    Files to read:

    - scripts/verify_phase07.py end to end, and
      tests/test_phase07_verification.py.
    - Every Phase 8 implementation file from Steps 1 through 9,
      docs/phase08-dogfood.md, and this roadmap's Verification surfaces
      audit.
  </context>

  <goal>
    Create `scripts/verify_phase08.py` with 60 static checks and the
    V1–V10 matrix of 38 rows (98 in `--post`),
    `tests/test_phase08_verification.py`, `docs/phase08-qa-findings.md`,
    and matrix entry `"08"`; close Phase 8 in both roadmaps and the
    README; tag `v2.0.0-phase-8`.
  </goal>

  <requirements>
    <requirement>
      Read scripts/verify_phase07.py end to end for structure, flag
      parsing, output format, the `Select` and JUnit conventions, the
      nested sweep, and the final summary. Mirror the format exactly so
      the Phase 8 script is visually continuous with the Phase 7 script
      in CI logs.
    </requirement>

    <requirement>
      `scripts/verify_phase08.py` modes, mutually exclusive: no flag
      (static checks and `--py`); `--fast` (static checks only, standard
      library only, under 30 seconds on Ubuntu CI); `--py` (ruff, ruff
      format, pyright for Windows and Linux, lint-imports, the three
      `--check` exporters, `pytest -n auto` with JUnit XML and the four
      coverage floors, `smoke_installed_web.py`); `--node` (`npm ci`,
      `audit signatures`, `api:check`, `lint`, `typecheck`, Vitest with
      JUnit XML, `build`, `licenses:check`); `--ui` (the default
      Playwright run with JUnit XML; never `@dogfood` or `@idle`);
      `--live` (`pytest -m live`, landmarks only); `--security` (both
      stacks' gates and the key-shape scan); `--all` (`--py`, `--node`,
      `--ui`, `--live`, `--security`); and `--post` (`--all`, then the
      probes: `phase_verify_ci` for `"01"` to `"08"`,
      `protection_requires_both`, `verify_phase07_post` at `"107"`,
      `dogfood_probe` running `npm --prefix frontend run e2e:dogfood`
      and requiring no audit finding, `operator_health_ui_build`
      comparing `ui.index_sha256` with the built `index.html`,
      `operator_doctor_web`, `measure_idle_probe`, and the `--fast`
      budget; then the matrix). Static checks use `tracked`, `read`,
      `contains`, `tagged`, and `ast` only, print `[PASS] NN:
      description (detail)`, and are independent.
    </requirement>

    <requirement>
      V1–V10 (38 rows), each built from JUnit evidence or a probe as
      listed in this roadmap's Post-Implementation Verification tables:
      V1 (5), V2 (4), V3 (5), V4 (4), V5 (3), V6 (3), V7 (3), V8 (4), V9
      (3), V10 (4). Every Vitest and Playwright selection is file-level;
      a missing file, a failure, or a skip fails its row.
    </requirement>

    <requirement>
      `tests/test_phase08_verification.py`: `--fast` passes in under 30
      seconds; `"08"` is in `phase-verify.yml`; a changed deliverable
      turns exactly its check red for one deliverable per step
      (asserting `failed == [check]`); skipped JUnit evidence fails
      closed; a failing probe fails `--post`; and check 52's two
      mutation cases (the live status moves it until Phase 9 converts
      it).
    </requirement>

    <requirement>
      Update `.github/workflows/phase-verify.yml`: append `"08"` at the
      end of the one-line `matrix.phase` list and add the Phase 8 Node
      steps as stated in context, preserving every prior entry and step.
    </requirement>

    <requirement>
      Create `docs/phase08-qa-findings.md` with a rollup for this
      roadmap's PR and every Step 1 through Step 9 (summary, findings
      and judgement calls, disposition), the dogfood summary (rounds,
      defects by severity, the carried defects' fates, and the
      operator's sign-off in their words with its date), the idle
      receipts, the live and browser runs, the nested sweep's measured
      duration, an "Exact vs. growth-proof Phase 8 checks for Phase 9"
      table (check 52 is exact and converts to `tagged("README.md",
      tag=PHASE_8_TAG)` in the Phase 9 step that edits the status), and
      a "Pre-ship items" section in which every item has a destination
      (Phase 9's documentation, release, LAN mode, and corpus decision;
      issues #95, #33, and #79).
    </requirement>

    <requirement>
      Mark the phase complete in the parent project roadmap
      (docs/roadmap/ROADMAP.md, beside this file) in the SAME Stage-3
      commit that marks this step (Status rule): `### Phase 8` gets
      `**Status:** Complete — <YYYY-MM-DD>; PR #<n>; v2.0.0-phase-8;
      phase08-roadmap.md` directly under its heading, and the heading
      ends in ✅; its row in the "Phase Complexity Summary" table reads
      `Complete`; the header `> **Status:**` line names Phase 8 as
      shipped and Phase 9 as next; and the Phase 8 "Acceptance criteria"
      there match this roadmap's V1–V10 checks. And in THIS roadmap,
      same commit: its phase-level `**Status:**` line reads `Complete —
      <YYYY-MM-DD>`, the title and every step heading end in ✅, and
      every step's Summary Table Status cell reads `Complete — PR #<n>`.
      `README.md`'s `## Status` names Phase 8 complete and Phase 9
      (Release 2.0) next, and `CHANGELOG.md` and `CONTRIBUTING.md`
      follow.
    </requirement>

    <requirement>
      Script must print clear pass / fail per check, exit 0 on success,
      and exit 1 on any failure or skip. After the merge, create the
      annotated tag `v2.0.0-phase-8` on the merge commit and push it.
    </requirement>

    <requirement>
      Filepath comment: every new file gets the repository-relative path
      as the first line.
    </requirement>
  </requirements>
</task>
```

### Step 10 acceptance criteria

- `scripts/verify_phase08.py` exists and passes on a clean tree
  post-implementation, with 60 static checks and 38 V rows (98 in `--post`).
- `--fast` runs in under 30 seconds on Ubuntu CI.
- `--post` runs cleanly on the operator's machine: Phase 7's nested sweep
  reports all 107, the dogfood harness reports no finding, the operator's
  service reports the final build, and the idle measurement holds; the nested
  sweep's duration is recorded.
- `docs/phase08-qa-findings.md` is complete with every rollup section and the
  operator's sign-off.
- `.github/workflows/phase-verify.yml`'s matrix includes `"01"` to `"08"`; the
  new check appears on every PR.
- `--security` exits 0 (secret/PII scan, SAST, and dependency audit clean over
  the phase's surface); V10.4 is green.
- Branch protection still passes on the resulting PR, and the annotated
  `v2.0.0-phase-8` tag peels to the merge commit.
- **Deployed & verified:** the first `phase-verify` run on `main` after the
  merge is green for `"01"` to `"08"`, branch protection still requires `gate`
  and `phase-verify`, and `git rev-parse v2.0.0-phase-8^{commit}` equals the
  merge commit.
- **Operations:** the interface's alarms — the stale-monitor banner, the
  reconnecting chip, the AI state banner, the radar banner, and the toasts — are
  proved in the redesigned shell (V8.4 and the specs Step 8 names), and the
  operator's `/api/health` names the deployed build (V9.2).
- **Security gate clean** (always the final criterion): the pre-commit security
  gate passed on this step's diff and the security workflow is green.
- **Phase closed, nothing carried.** Every finding recorded in
  `docs/phase08-qa-findings.md` has a destination (fixed, an issue number, or a
  named phase that owns it), the "Not in scope" section below is current, and no
  un-tracked item remains. Every step of this roadmap, this one included, reads
  `**Status:** Complete — PR #…` on `main` under a ✅ heading, the Summary
  Table's Status column and this roadmap's phase-level Status line say
  `Complete` under a ✅ title, and the parent project roadmap's Phase 8 entry
  (under a ✅ heading), its summary-table row, and its header status line say
  `Complete` — all landed in this step's PR. This step's final response ends
  with two lines and nothing after them: "Step 10 is complete. You can now move
  on to Step 11." is replaced by "Step 10 is complete. Phase 8 is complete. You
  can now move on to Phase 9." — same Stage 6 rule: no "Follow-ups", no trailer.

---

## Post-Implementation Verification

Every V1–V10 check below runs **automatically in CI** on every push and pull
request, except these. Phase 7's own `--post` sweep (V1.5), the dogfood
harness's full render matrix (V8.2), the idle measurement (V4.4), and the
operator's running service (V9.2, V9.3) run in `--post` on the operator's
Windows machine, because they need the operator's environment, the installed
copy, ten quiet minutes, or a long browser run; the nested Phase 7 sweep in turn
nests Phases 6 to 1 and spends about $0.40 on Phase 6's live AI eval, after the
operator's yes. The two dogfood loops' judgements are operator wall-clock and
agent work, recorded in `docs/phase08-dogfood.md`; their machine-checkable
halves (a clean audit, a dated sign-off) are V8.2 and check 51. CI never holds
an Anthropic credential or an ntfy topic: every test there uses a fake built at
run time or a recording.

| Mode         | Workflow                        | Runner  | Coverage          |
| ------------ | ------------------------------- | ------- | ----------------- |
| `--fast`     | `phase-verify.yml` (`"08"`)     | Ubuntu  | static checks     |
| `--py`       | `ci.yml` test, package          | both    | Python rows       |
| `--node`     | `ci.yml` frontend               | Ubuntu  | frontend rows     |
| `--ui`       | `ci.yml` browser                | Ubuntu  | browser rows      |
| `--security` | `ci.yml` security, phase-verify | Ubuntu  | V10.4             |
| `--live`     | `live-smoke.yml` (dispatch)     | Ubuntu  | live tests        |
| `--all`      | none (local)                    | Windows | all but post      |
| `--post`     | local, operator's machine       | Windows | every V row       |

In the tables, `fast` is `phase-verify.yml`'s `--fast`, `ci` is `ci.yml`'s
`test` job (`--py`), `node` its `frontend` job (`--node`), `ui` its `browser`
job (`--ui`), `sec` the `security` job and `--security`, and `post` the
operator's machine only.

Local invocations remain available for ad-hoc runs and pre-release sweeps:

```bash
uv run python scripts/verify_phase08.py --post   # static + V1-V10 + post checks
```

`--post` is the canonical command to run before tagging `v2.0.0-phase-8`. It
starts demonstration servers and a headless browser in temporary data
directories, asks before the nested live AI eval and states its cost, reads the
operator's running service only through `/api/health` and `doctor`, and says so
before it starts.

Other modes:

```bash
uv run python scripts/verify_phase08.py --fast      # static only (CI-safe)
uv run python scripts/verify_phase08.py --py        # + lint, types, tests
uv run python scripts/verify_phase08.py --node      # + frontend toolchain
uv run python scripts/verify_phase08.py --ui        # + browser smoke
uv run python scripts/verify_phase08.py --live      # + live, landmarks only
uv run python scripts/verify_phase08.py --security  # the gate, both stacks
uv run python scripts/verify_phase08.py --all       # all but --post
```

The script reports each V-check by id (V1.1, V2.1, ...) so a failure in any
workflow above maps directly to the corresponding row below.

### V1 — Demonstration scenarios

> **Automated in CI.** `phase-verify.yml` → V1.1; `ci.yml` → V1.2 and V1.3; the
> `browser` job → V1.4; `--post` on the operator's machine → V1.5.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V1.1  | Static checks 1–7 all PASS.                                  | fast |
| V1.2  | Scenario tests: every level and rule, offline, two decimals. | ci   |
| V1.3  | `test_serve_demo.py`: the default unchanged, the new flag.   | ci   |
| V1.4  | `scenarios.spec.ts` renders the quiet and landfall servers.  | ui   |
| V1.5  | `verify_phase07.py --post` passes all 107 (and 6 to 1).      | post |

### V2 — The design system and readable type

> **Automated in CI.** `phase-verify.yml` → V2.1; the `frontend` job → V2.2 and
> V2.4; the `browser` job → V2.3.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V2.1  | Static checks 8–16 all PASS.                                 | fast |
| V2.2  | The `ui/` primitives' tests and `AppShell.test.tsx` pass.    | node |
| V2.3  | `readability.spec.ts`: no finding on any render.             | ui   |
| V2.4  | `--node` exits 0: lint with the type rule, build, licences.  | node |

### V3 — Plain English and one vocabulary

> **Automated in CI.** `phase-verify.yml` → V3.1; `ci.yml` → V3.2 and V3.3; the
> `frontend` job → V3.4; the `browser` job → V3.5.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V3.1  | Static checks 17–24 all PASS.                                | fast |
| V3.2  | The ladder service and route tests pass; no location data.   | ci   |
| V3.3  | The OpenAPI and fixture exporters' `--check` pass.           | ci   |
| V3.4  | The assessment components' Vitest files pass.               | node |
| V3.5  | `plain-english.spec.ts` and `replay.spec.ts` pass.           | ui   |

### V4 — The command-center dashboard

> **Automated in CI.** `phase-verify.yml` → V4.1; the `frontend` job → V4.2; the
> `browser` job → V4.3; `--post` on the operator's machine → V4.4.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V4.1  | Static checks 25–30 all PASS.                                | fast |
| V4.2  | `Dashboard.test.tsx` and the dashboard components' tests.    | node |
| V4.3  | `command-center`, `dashboard`, `report`, `ai` specs pass.    | ui   |
| V4.4  | Server and tab each stay under 0.5% of a core idle.          | post |

### V5 — The immersive map

> **Automated in CI.** `phase-verify.yml` → V5.1; the `frontend` job → V5.2; the
> `browser` job → V5.3.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V5.1  | Static checks 31–35 all PASS.                                | fast |
| V5.2  | `MapView.test.tsx` and `layers.test.ts` pass.                | node |
| V5.3  | `map.spec.ts` and `layers.spec.ts` pass.                     | ui   |

### V6 — The replay workbench

> **Automated in CI.** `phase-verify.yml` → V6.1; the `frontend` job → V6.2; the
> `browser` job → V6.3.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V6.1  | Static checks 36–38 all PASS.                                | fast |
| V6.2  | `Replay.test.tsx` passes.                                    | node |
| V6.3  | `replay.spec.ts`: map, slider, headline in the first view.   | ui   |

### V7 — Sectioned settings and the secondary pages

> **Automated in CI.** `phase-verify.yml` → V7.1; the `frontend` job → V7.2; the
> `browser` job → V7.3.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V7.1  | Static checks 39–44 all PASS.                                | fast |
| V7.2  | Tabs, Settings, Ask, and the list pages' tests pass.         | node |
| V7.3  | `settings-tabs`, `phase7`, and `locations` specs pass.       | ui   |

### V8 — Loop 1: the AI visual dogfood

> **Automated in CI.** `phase-verify.yml` → V8.1; the `browser` job → V8.3; the
> `frontend` job → V8.4; `--post` on the operator's machine → V8.2.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V8.1  | Static checks 45–50 all PASS.                                | fast |
| V8.2  | `e2e:dogfood` renders 240 views with no audit finding.       | post |
| V8.3  | `phase8.spec.ts` walks the whole redesign cleanly.           | ui   |
| V8.4  | `AppShell.test.tsx`'s stale and reconnecting cases pass.     | node |

### V9 — Loop 2: the operator's dogfood

> **Automated in CI.** `phase-verify.yml` → V9.1; `--post` on the operator's
> machine → V9.2 and V9.3.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V9.1  | Static checks 51–54 all PASS (the dated sign-off included).  | fast |
| V9.2  | The operator's `/api/health` names this build at the head.   | post |
| V9.3  | The operator's `doctor --offline --json` passes `web`.       | post |

### V10 — CI integration + security

> **Automated in CI.** `phase-verify.yml` → V10.1 through V10.4 on every
> push/PR.

| ID    | Check                                                        | Runs |
| ----- | ------------------------------------------------------------ | ---- |
| V10.1 | `verify_phase08.py --fast` exits 0 on Ubuntu CI.             | fast |
| V10.2 | `phase-verify.yml`'s matrix includes `"01"` to `"08"`.       | fast |
| V10.3 | All 60 static checks in `verify_phase08.py` pass.            | fast |
| V10.4 | `--security` exits 0 over both stacks.                       | sec  |

---

## Summary Table

| Step | Scope                          | Model          | Status             |
| ---- | ------------------------------ | -------------- | ------------------ |
| 1    | Scenarios + recordings         | Opus 5.5       | Not started        |
| 2    | Design system + type gate      | Opus 5.5       | Not started        |
| 3    | Plain English + ladder route   | Opus 5.5       | Not started        |
| 4    | Command-center dashboard       | Gemini 4 Argon | Not started        |
| 5    | Immersive map                  | Gemini 4 Argon | Not started        |
| 6    | Replay workbench               | Gemini 4 Argon | Not started        |
| 7    | Settings tabs + pages          | Gemini 4 Argon | Not started        |
| 8    | Loop 1: AI dogfood             | Sonnet 5.5     | Not started        |
| 9    | Loop 2: operator dogfood       | Opus 5.5       | Not started        |
| 10   | QA + verify_phase08.py         | GPT-6.1 Sol    | Not started        |
| V1   | Scenarios + recordings         | CI             | --                 |
| V2   | Design system + type gate      | CI             | --                 |
| V3   | Plain English + ladder route   | CI             | --                 |
| V4   | Command-center dashboard       | CI             | --                 |
| V5   | Immersive map                  | CI             | --                 |
| V6   | Replay workbench               | CI             | --                 |
| V7   | Settings tabs + pages          | CI             | --                 |
| V8   | Loop 1: AI dogfood             | CI             | --                 |
| V9   | Loop 2: operator dogfood       | CI             | --                 |
| V10  | CI integration                 | CI             | --                 |

Each step's row restates the option its Model rationale names as the best fit on
the step's merits; the platform, the dials, and the other ranks and columns live
in the step's own Settings, and the operator picks the option.

---

## Model selection blocks

Each block restates the option the step's Model rationale names as its best fit
— its model and that column's Backup from another maker; the other options are
named in the rationale and the Settings, and the operator picks the option.

```text
PROMPT: Step 1 — Demonstration scenarios
MODEL: Opus 5.5
BACKUP: GPT-6 Astra
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a knowledge secondary — a synthetic
storm in live formats that must drive the real rules to named
levels, five scenarios, a seeded history, and live recordings,
High complexity and novel. PICK: Opus 5.5, S-tier in coding (AA
56 at XHigh), the ladder's Quality pick; Runner-up Gemini 4 Argon
at High. EFFORT: XHigh fits staging geometry against the rules.

PROMPT: Step 2 — The design system and readable type
MODEL: Opus 5.5
BACKUP: GPT-6 Astra
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a multimodal secondary — tokens,
primitives, a shell, a sweep through every component, and a
computed gate, High complexity. PICK: Opus 5.5 (AA 56 at XHigh),
the ladder's Quality pick; Runner-up Gemini 4 Argon at High.
EFFORT: XHigh fits two hundred prose-or-caption judgements and
the contrast arithmetic every later step relies on.

PROMPT: Step 3 — Plain English and one vocabulary
MODEL: Opus 5.5
BACKUP: GPT-6 Astra
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: coding with a knowledge secondary — a route over
the engine's metadata, the OpenAPI document and fixtures, and the
components two pages share, High complexity. PICK: Opus 5.5 (AA
56 at XHigh), the ladder's Quality pick; Runner-up Gemini 4 Argon
at High. EFFORT: XHigh fits a change where a wrong word misstates
an official product.

PROMPT: Step 4 — The command-center dashboard
MODEL: Gemini 4 Argon
BACKUP: GPT-6 Astra
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a multimodal secondary — a page
composed from the design system, a popover, a hash-bound
selection, a countdown, and a mini-map, High complexity. PICK:
Gemini 4 Argon, S-tier in coding with multimodal strength (AA
52.6 at High), the ladder's Balanced pick; Runner-up Opus 5.5 at
High. EFFORT: High fits composition this roadmap specifies.

PROMPT: Step 5 — The immersive map
MODEL: Gemini 4 Argon
BACKUP: GPT-6 Astra
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a multimodal secondary — a
full-viewport canvas with floating panels and a spec rewritten in
place, High complexity. PICK: Gemini 4 Argon (AA 52.6 at High),
the ladder's Balanced pick; Runner-up Opus 5.5 at High. EFFORT:
High fits panels that must never hide the storm.

PROMPT: Step 6 — The replay workbench
MODEL: Gemini 4 Argon
BACKUP: GPT-6.1 Sol
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a multimodal secondary — one page's
two-column layout around existing components, Medium complexity.
PICK: Gemini 4 Argon (AA 52.6 at High), the ladder's Quality pick;
Runner-up Opus 5.5 at High. EFFORT: High fits a workbench that
must balance at every width.

PROMPT: Step 7 — Sectioned settings and the secondary pages
MODEL: Gemini 4 Argon
BACKUP: GPT-6 Astra
PLATFORM: Antigravity
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: coding with a multimodal secondary — an accessible
tabs primitive bound to the hash, five-way Settings, chips, and
three list pages, High complexity for its breadth. PICK: Gemini 4
Argon (AA 52.6 at High), the ladder's Balanced pick; Runner-up
Opus 5.5 at High. EFFORT: High fits known patterns across five
pages.

PROMPT: Step 8 — Loop 1: the AI visual dogfood
MODEL: Sonnet 5.5
BACKUP: Gemini 3.8 Flash
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: multimodal with a coding secondary — judging 240
screenshots a round against a rubric and fixing what they show,
High complexity. PICK: Sonnet 5.5 (AA 51.9 at XHigh), the ladder's
Balanced runner-up, which opens screenshots with the same tools
that run the harness; the Balanced pick is GPT-6.1 Sol at High,
and the Quality pick, Fable 5.1, runs only where no terminal or
codebase tools exist. EFFORT: XHigh fits a long run of visual
judgements.

PROMPT: Step 9 — Loop 2: the operator's dogfood
MODEL: Opus 5.5
BACKUP: GPT-6 Astra
PLATFORM: Claude Code
EFFORT: XHigh
ORCHESTRATION: None
CONVERSATION: New
RATIONALE: TASK: agentic with a coding secondary — rounds of the
operator's feedback turned into fixes, background servers, and an
on-machine deployment, High complexity. PICK: Opus 5.5 (AA 56 at
XHigh), the ladder's Quality pick; Runner-up Gemini 4 Argon at
High. EFFORT: XHigh fits judgement on feedback about taste, where
the operator's time is the scarce input.

PROMPT: Step 10 — QA + verify_phase08.py
MODEL: GPT-6.1 Sol
BACKUP: Gemini 4 Argon
PLATFORM: Codex
EFFORT: High
THINKING: On
CONVERSATION: New
RATIONALE: TASK: mechanical translation of this roadmap's
acceptance criteria into a verification script, a matrix entry,
and a findings rollup. PICK: known pattern, no novel reasoning —
GPT-6.1 Sol on Codex (AA 50.2 at High), the ladder's Balanced
pick; Runner-up Sonnet 5.5 at High. EFFORT: High is the level the
ladder prints for this column; enumerated checks whose content
this roadmap writes down need no more.
```

---

## Not in scope (from product roadmap)

The project roadmap's Phase 8 section carries no "Not in scope" list; these
items follow from its phase boundaries, its acceptance criteria, and its §6 "Out
of Scope":

- Any change to the ladder, its thresholds, the policy, a prompt, or an AI
  product, and the answer to issue #33 (whether a surge or extreme-wind product
  moves the ladder). A rule change follows Phase 3's golden process with the
  operator's approval, in a change of its own.
- Release documentation, screenshots for it, the PyPI release, the always-on
  guide, LAN mode, and the fresh-install smoke. Phase 9, which pictures and
  documents the pages this phase builds.
- Public hosting, accounts, mobile apps, SMS, email, Slack, and Discord (§6).
  The phone layout is a responsive page, not an app.
- Coverage outside the three NHC basins, model-driven search, any forecast of
  Weatherbot's own, and automated evacuation orders (§6).

Additionally not in scope for this phase:

- A web font, an icon set beyond `lucide-react`, a component library, a chart
  library, an accessibility-testing package, or any other npm package (Decision
  5). Phase 6's check 39 and Phase 7's check 43 stay exact.
- A CSP change, a new outbound host, or a new map layer (Phase 7's checks 35 and
  36 stay exact). The tile proxy stays issue #95's condition.
- A database revision, a new setting, or an editable `[web]`, `[engine]`,
  `[monitor]`, `[http]`, or `[logging]` key; `EDITABLE` keeps its 12 keys (Phase
  7's check 25).
- Pixel-diff screenshot baselines (`toHaveScreenshot`): Windows and Linux render
  differently, and the rubric and the computed audit judge the pages instead.
  Committing screenshots (Decision 18).
- Replay snapshots in history or as demonstration data (Decision 2): history
  stays live only, and the archive's sphere is never relabelled.
- Synthetic storms or scenarios in the installed package: they live in
  `scripts/` and `tests/fixtures/`, and Phase 9's readiness scan reviews them.
- Shipping or downloading the replay corpus. Phase 9 decides it with the
  release.
- Translating the interface or its vocabulary into another language. The
  engine's words are English, and so is the page.
- Issue #79 (`minimatch` in dev tooling), the open Dependabot pull requests, and
  removing version 1 from the operator's `PATH`. Independent maintenance and the
  operator's housekeeping, outside every step.
- A package version bump. The version stays `2.0.0.dev0` until Phase 9's release
  candidate; `/api/health` names the build, and the milestone tag marks the
  phase.

---

_This roadmap is the execution plan for Phase 8. Each step's `**Status:**` line
is flipped by that step's own PR (Status rule), so this file on `main` is the
phase's ledger — `grep -n '^\*\*Status:\*\*'` reports progress. After all steps
and verification pass, and every finding has a destination, Phase 8 is complete
— declared with the line "Phase 8 is complete. You can now move on to Phase 9."
and nothing after it — and Phase 9 (Release 2.0) inherits a web app that reads
at a glance: one design system with type a reader can read, the engine's own
words on every level with the provenance a click away, a command-center
dashboard, a map that is the page, a side-by-side replay, sectioned settings,
demonstration scenarios that show every level, a readability gate in CI, and an
operator who has signed off — all of which its documentation pictures, its
fresh-install smoke opens with no key, topic, or corpus, and its readiness scan
clears._
