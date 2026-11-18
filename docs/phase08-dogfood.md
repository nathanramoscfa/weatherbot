<!-- docs/phase08-dogfood.md -->
# Phase 8 dogfood ledger

The record of Phase 8's two dogfood loops (Decision 17 of
`docs/roadmap/phase08-roadmap.md`): what looked wrong, on which render, and
where it was fixed. Step 8 adds the rubric and Loop 1's rounds; Step 9 adds Loop
2's rounds and the operator's sign-off. Screenshots are evidence, not repository
content: each is named by its key and lives under `frontend/test-results/`.

## Carried from Steps 2 to 7

Defects a step saw on a page it does not own (the roadmap's Triage rule), so
Loop 1 starts from a list rather than a memory. The key is the route, the
scenario, the viewport, and the theme; `any` means every value.

| Key | What looks wrong | Step that owns the page |
| --- | ---------------- | ----------------------- |
| `/` and `/replay`, any scenario with a track-closest-approach reading, 1440×900, any theme | `ArrivalTimeline`'s words row ("track: … (track closest approach, not a wind arrival)") is longer than the plot and is clipped at the chart's right edge; it was clipped at the old 10-unit size too | Step 4 (fixed in `ArrivalTimeline.tsx` `formatPlotWords`) |
| `/`, `landfall`, 1440×900, any theme | The arrival timeline and the wind-probability charts now stop at their `viewBox` width (420 and 560 px) so their labels are 13 px, which leaves the right part of a wide location card empty | Step 4 (fixed in `FeaturedLocation.tsx` two-column layout) |
| `/replay`, any scenario (Dorian at Parliament Square), 1440×900, any theme | `LevelHistoryChart`'s marker labels overlap where advisories crowd together ("L3L3", "L2" over "L2") | Step 6 (fixed in `LevelHistoryChart.tsx` `labeledMarkerIds` 28-unit gap and distinct-level filter) |
| `/replay`, any scenario, 1440×900, any theme | The level history chart (at most 560 px) sits in the left half of a full-width card | Step 6 (fixed in `Replay.tsx` `xl:grid-cols-2` workbench left column) |
| `/settings`, any scenario, any viewport, any theme | `LocationManager`'s minimum-level `<select>` (`"Level 2 — Monitor"`, `"Level 3 — Watch / Advisory"`, `"Level 5 — Extreme Threat"`) and `QuietHoursForm`'s explanatory copy still use pre-Step-3 informal level names instead of `levelLabel(n)` | Step 7 (fixed in `LocationManager.tsx` and `QuietHoursForm.tsx` via `levelLabel(n, ladder)`) |
| `/`, `/replay`, `/timeline`, any scenario, 360×740, any theme | Chart labels scale with the chart and render below 13 px at phone width; each chart's visually hidden table carries the data, and the readability gate skips chart internals (Decision 6) | Steps 4, 6, 7 (verified across `/`, `/replay`, and `/timeline` with accessible tables and viewBox caps) |

## Idle CPU measurements

- **Step 4 (Command-center dashboard):** `idle measurement: window=600.1s server_cpu=0.3229% (1.938s) tab_cpu=0.0087% (0.052s) roster_polls=0 cycles=0 ai_state=ready change_summaries=on budget=<0.5%`
- **Step 8 (after the last fix, `4b4ca28`):** `idle measurement: window=600.0s server_cpu=0.2682% (1.609s) tab_cpu=0.0057% (0.034s) roster_polls=0 cycles=0 ai_state=ready change_summaries=on budget=<0.5%`

## Loop 1 rubric

Judge every full-page render, including its footer; inspect interactive states in
`phase8.spec.ts` and the alarm proofs below. A pass needs every applicable item.

| Item | Pass | Fail |
| --- | --- | --- |
| Hierarchy | One primary headline per card; level and name legible within a second | Competing headlines, buried level, unexplained figure |
| Vocabulary | Engine words lead; provenance behind disclosure | Code, source ID, or raw timestamp leads a card |
| Colour | Threat tint marks threat, with number and words | Colour alone conveys a level or a neutral card mimics one |
| Type | Token scale; prose >=14 px, captions >=13 px; AA contrast | Small or faint explanation, inconsistent heading sizes |
| Spacing and alignment | Consistent padding, gaps, and aligned controls | Crowding, uneven gutters, clipped content |
| Density | Scannable groups and disclosures; comfortable phone wrapping | Wall of text, squeezed controls, long empty card |
| Empty, loading, error | Says what is absent, loading, or failed and what happens next | Blank card, false all-clear, silent failure, stuck spinner |
| Phone | No overlap or horizontal clipping; targets >=24 px | Cut-off text, overlapping controls, undersized target |
| Dark parity | Same information, hierarchy, and contrast in both themes | Missing border, unreadable text, unintended bright surface |
| Map panels | Storm and map controls remain visible; panels collapse | Panel hides storm, attribution, zoom, or another control |
| Focus | Keyboard focus has a visible outline and follows control order | Lost or invisible focus, inaccessible control |
| Disclaimer | Informational-only notice and full-text link present | Missing notice or inaccessible full text |

Severities: **blocker** = wrong or missing information or an unusable control;
**major** = a reader misreads or struggles; **minor** = visibly off but readable;
**polish** = taste. Exit requires a complete 240-image round with zero audit
findings and no blocker, major, or minor defect. Polish is fixed or listed for
Step 9's operator review.

Run `npm --prefix frontend run e2e:dogfood`. Keys are
`scenario-WIDTHxHEIGHT-theme/view`; twelve views, five scenarios, two sizes,
two themes. `frontend/test-results/dogfood/audit.json` records the source commit
and an entry for every render, including those without findings. The screenshot
path is in each entry. Preserve a round's ignored evidence before another run
(the default Playwright run clears `test-results/`). No pixels are committed.

### Round log

| Round | Date | Source commit | Renders judged | Audit findings | Blocker / major / minor / polish |
| --- | --- | --- | --- | --- | --- |
| 1 | 2026-11-17 | `7b3ceef` | 240 / 240 | 0 | 0 / 2 / 0 / 0 (DF-06, DF-07) |
| 2 | 2026-11-17 | `4b4ca28` | 240 / 240 | 0 | 0 / 0 / 0 / 0 |

Preflight on 2026-11-17: UI baseline `7742a81`, harness `275250e`.
It generated 196 images (48 judged); four outlook tests stopped because the
first SVG path was outside the map's fitted viewport. This was an incomplete
harness run, not an exit round. The ready marker now selects nondegenerate
visible geometry; the complete rounds supersede these preliminary captures.

Before the completed second round, two incomplete attempts exposed harness
navigation problems: a hash-only Settings navigation reused the health query,
and a fresh `about:blank` document rejected the theme storage write. `217fb8c`
and `4b4ca28` fix those waits and scope theme setup to the demonstration origin.
The page-error guard caught the latter; it remains unchanged. Neither attempt
counts as a full round.

Round 2 opened and judged every image against all applicable rubric items,
including the full-page footer. Its 240 unique review keys match the manifest
and 240 PNGs. Both themes and sizes show the corrected chart vocabulary, AI
labels, selected Settings tabs, complete location cards, and exposed map points.
Tables and tab strips intentionally scroll horizontally; chart internals keep
Decision 6's accessible-table exemption. No polish items remain for Loop 2.
Ignored evidence is preserved locally in `.roadmodel/dogfood-round1/` and
`.roadmodel/dogfood-round2/`, each with its audit and complete review record.

### Defects

| ID | Screenshot key | Rubric item | Severity | What was wrong | Fix commit or owning issue |
| --- | --- | --- | --- | --- | --- |
| DF-01 | `any/replay` | Vocabulary | Major | Axis said `L5 Cat.`, `L2 Aware`, and `L4 Warn`, confusing threat levels with hurricane categories | `7b3ceef`: neutral `Level N` ticks; regression in `LevelHistoryChart.test.tsx` |
| DF-02 | `any/settings-ai` | Density / alignment | Minor | Checkbox text and configuration keys split into separate flex fragments | `7b3ceef`: group label text; put keys on a caption line |
| DF-03 | `quiet-1440x900-light/settings-locations` | Evidence completeness | Major | Capture ended before the location form finished expanding | `7b3ceef`: wait for Add location, fonts, and two layout frames |
| DF-04 | `any-390x844-any/settings-{ai,retention,about}` | Phone controls | Major | Hash-selected tab stayed outside the visible tab strip | `7b3ceef`: reveal selection horizontally; browser regression in `settings-tabs.spec.ts` |
| DF-05 | `any-390x844-any/settings-ai` | Density | Minor | Request table squeezed numbers and model names into narrow fragments | `7b3ceef`: minimum table width within its existing scroller |
| DF-06 | `cone-1440x900-dark/settings-locations` | Evidence completeness | Major | Capture had the form but no watched-location cards; async queries were still pending | `01e0b6b`: await both landmark cards, health notice, and complete About content |
| DF-07 | `{cone,watch,landfall}-1440x900-any/map` | Map panels | Major | Fit used the entire canvas, leaving the current position or forecast points behind the open panels | `01e0b6b`: fit within measured HUD insets; browser point-occlusion regression in `map.spec.ts` |

### Alarm proofs in the redesigned shell

| Alarm | Proof |
| --- | --- |
| Stale monitor (`role="alert"`, names stale heartbeats and ages) | `frontend/src/app/AppShell.test.tsx`: staleness banner test |
| Reconnecting chip, recovery to Live | `frontend/src/app/AppShell.test.tsx`: same test emits stream error/open |
| AI daily cap | `frontend/e2e/ai.spec.ts`: capped demonstration server, `ai-state-banner` |
| Radar unavailable | `frontend/e2e/phase7.spec.ts`: aborted nowCOAST route, `radar-unavailable-banner` |
| Radar and satellite unavailable | `frontend/src/map/MapView.test.tsx`: both unavailable banner cases |
| Notification toast | `frontend/e2e/dashboard.spec.ts`: event-driven warning toast |

### Validation receipt

After the final fix on 2026-11-17: the default Playwright run passed all 32
tests, including `phase8.spec.ts`, the alarm browser proofs, map-point
visibility, phone hash tabs, and the existing readability gate. Vitest passed
50 files / 155 tests; build, typecheck, lint, and the 49-package license check
passed. Phase 5, 6, and 7 `--fast` passed 53, 51, and 65 checks respectively.
All 19 hooks in the local all-files pre-commit gate passed, including
secret/personal-data scanning, SAST, and both dependency audits. All captures
use the demonstration servers; no screenshot or audit file is committed.

## Loop 2 — operator dogfood

The operator walked the redesigned web app in their own browser on 2026-11-17
against the six offline demonstration servers started from
`feature/phase08-step9-operator-dogfood` (`7248531`, in temporary data
directories with only the two public landmarks and the synthetic storm):

- Default (`http://127.0.0.1:8799`, PID `8992`)
- `quiet` (`http://127.0.0.1:8802`, PID `90072`)
- `outlook` (`http://127.0.0.1:8803`, PID `45468`)
- `cone` (`http://127.0.0.1:8804`, PID `93876`)
- `watch` (`http://127.0.0.1:8805`, PID `48512`)
- `landfall` (`http://127.0.0.1:8806`, PID `26916`)

### Loop 2 round log

| Round | Date | Source commit | Scenarios & pages walked | Feedback items | Disposition |
| --- | --- | --- | --- | --- | --- |
| 1 | 2026-11-17 | `7248531` | Default (`8799`) and `quiet`, `outlook`, `cone`, `watch`, `landfall` (`8802`–`8806`) across `/`, `/map`, `/replay`, `/storms`, `/alerts`, `/timeline`, `/ask`, and `/settings` (`#locations`, `#notifications`, `#ai`, `#retention`, `#about`, `#disclaimer`) | 0 | Accepted as-is; operator signed off |

### Operator feedback

| Round | Page / scenario | Operator feedback (verbatim) | Disposition |
| --- | --- | --- | --- |
| 1 | All pages (`/`, `/map`, `/replay`, `/storms`, `/alerts`, `/timeline`, `/ask`, `/settings`) and all scenarios (`default`, `quiet`, `outlook`, `cone`, `watch`, `landfall`) | `"I have walked the pages and scenarios — the web app is ready to release (sign off Loop 2)"` | Signed off with no changes requested (`7248531`) |

### Demonstration server cleanup and idle status

- All six background demonstration servers started for Loop 2 (`PID 8992` on
  `8799`, `PID 90072` on `8802`, `PID 45468` on `8803`, `PID 93876` on `8804`,
  `PID 48512` on `8805`, and `PID 26916` on `8806`) were stopped immediately
  after sign-off and verified absent by process ID check (`remaining_pids=0`)
  and loopback port check.
- Because `/` was unchanged in Loop 2, Step 8's post-fix 600-second idle CPU
  receipt (`window=600.0s server_cpu=0.2682% (1.609s) tab_cpu=0.0057% (0.034s) roster_polls=0 cycles=0 ai_state=ready change_summaries=on budget=<0.5%`)
  remains the current measurement for the merged dashboard build.

### Sign-off

- **Operator sign-off (2026-11-17):** `"I have walked the pages and scenarios — the web app is ready to release (sign off Loop 2)"`
