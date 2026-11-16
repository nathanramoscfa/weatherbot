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
| `/` and `/replay`, any scenario with a track-closest-approach reading, 1440×900, any theme | `ArrivalTimeline`'s words row ("track: … (track closest approach, not a wind arrival)") is longer than the plot and is clipped at the chart's right edge; it was clipped at the old 10-unit size too | Step 4 |
| `/`, `landfall`, 1440×900, any theme | The arrival timeline and the wind-probability charts now stop at their `viewBox` width (420 and 560 px) so their labels are 13 px, which leaves the right part of a wide location card empty | Step 4 |
| `/replay`, any scenario (Dorian at Parliament Square), 1440×900, any theme | `LevelHistoryChart`'s marker labels overlap where advisories crowd together ("L3L3", "L2" over "L2") | Step 6 |
| `/replay`, any scenario, 1440×900, any theme | The level history chart (at most 560 px) sits in the left half of a full-width card | Step 6 |
| `/settings`, any scenario, any viewport, any theme | `LocationManager`'s minimum-level `<select>` (`"Level 2 — Monitor"`, `"Level 3 — Watch / Advisory"`, `"Level 5 — Extreme Threat"`) and `QuietHoursForm`'s explanatory copy still use pre-Step-3 informal level names instead of `levelLabel(n)` | Step 7 |
| `/`, `/replay`, `/timeline`, any scenario, 360×740, any theme | Chart labels scale with the chart and render below 13 px at phone width; each chart's visually hidden table carries the data, and the readability gate skips chart internals (Decision 6) | Steps 4, 6, 7 |
