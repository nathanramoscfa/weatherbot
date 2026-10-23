<!-- docs/ALERT-LADDER.md -->
# The alert ladder

Weatherbot decides a level from official NHC and NWS products. Claude can explain
the result but cannot choose or change it. This is the shared wording for the CLI,
the web app, and briefing prompts.

**Weatherbot is informational only, never a substitute for official guidance.**
Follow local emergency management and official evacuation orders. Read the full
[disclaimer](../DISCLAIMER.md).

## How a level is decided

`assess(snapshot, location, thresholds)` uses the snapshot's completion instant
(the advisory's issuance in a replay). It reads no wall clock. The first matching
rule decides the level; all matches of that rule become its evidence. Within a
level, official products precede the operator's evacuation toggle, followed by
geometry and probabilities. A probability compares the band's **lower bound**,
not its midpoint or upper bound. Missing bands never imply a positive chance.

The operator's evacuation-order toggle sets level 4 while it is on, and its
evidence names when it was turned on. It is a present-day input: `weatherbot
replay` assesses a past storm with it off. `weatherbot status` stores every
assessment with its evidence and its changes; a replay is never stored.

An NWS alert counts only if it is Actual, is not a Cancel, and expires after the
snapshot instant. It covers the location if the point query returned it or its
UGC list names the location's forecast or county zone. A county-query alert for
other zones remains visible context and sets no level ([issue #10](https://github.com/nathanramoscfa/weatherbot/issues/10)).

An NHC watch-warning segment covers a location within the coastal reach if its
nearest point is inside the segment, or within the end tolerance if the nearest
point is an open end. A singleton is measured as a point. Distances use the
segment's CRS: WGS 84 for live products, the archive's 6,371,200 m sphere for
replays. No replay geometry is relabeled WGS 84. A breakpoint span names the
location's coast from the catalogue; the segment geometry decides coverage.

## Levels and actions

<!-- ladder:levels -->

| Level | Name | Actions |
| --- | --- | --- |
| 5 | Hurricane Warning | Shelter if not evacuated; expect outages; follow local orders |
| 4 | Warning / Watch / Evacuation | Evacuate vulnerable areas; secure transport; assume routes close |
| 3 | Watch / Hurricane Threat | Stock supplies; pack; set an exit plan |
| 2 | Tropical Storm Threat | Monitor daily; review plans |
| 1 | All Clear | Normal activities |

<!-- /ladder:levels -->

## Rules in priority order

<!-- ladder:rules -->

| Order | Rule | Level | Trigger | Products read |
| --- | --- | --- | --- | --- |
| 1 | `hurricane_warning` | 5 | A Hurricane Warning covers the location. | NWS alerts, NHC watch-warning segments |
| 2 | `tropical_storm_warning` | 4 | A Tropical Storm Warning covers the location. | NWS alerts, NHC watch-warning segments |
| 3 | `hurricane_watch` | 4 | A Hurricane Watch covers the location. | NWS alerts, NHC watch-warning segments |
| 4 | `evacuation_order` | 4 | The operator's evacuation-order toggle is on. | the location's evacuation-order toggle |
| 5 | `tropical_storm_watch` | 3 | A Tropical Storm Watch covers the location. | NWS alerts, NHC watch-warning segments |
| 6 | `hurricane_cone` | 3 | The location is inside the cone of a storm that is a hurricane at or before its closest approach, and that approach comes within the cone horizon. | NHC cones, NHC forecast points |
| 7 | `hurricane_wind_probability` | 3 | The location's 64-kt wind-speed probability band starts at or above the hurricane wind floor. | NHC 64-kt wind-speed probabilities |
| 8 | `storm_cone` | 2 | The location is inside the cone of any active storm. | NHC cones, NHC forecast points |
| 9 | `development_region` | 2 | The location is inside a seven-day potential development region whose chance is at least the development chance floor. | NHC tropical weather outlook development regions |
| 10 | `tropical_storm_wind_probability` | 2 | The location's 34-kt wind-speed probability band starts at or above the tropical-storm wind floor. | NHC 34-kt wind-speed probabilities |
| 11 | `all_clear` | 1 | No other rule matches. | none |

<!-- /ladder:rules -->

## Thresholds and their calibration

<!-- ladder:thresholds -->

| Threshold | Default | Unit | Outcome interval | Evidence |
| --- | --- | --- | --- | --- |
| `coastal_reach_km` | 25 | km | 3.79956 ≤ x < 112.159 | 25 km is inside the 7.6-29.1 km safety gap; covering lines pass within 3.8 km, non-covering alongside lines start at 58.2 km. |
| `segment_end_tolerance_km` | 5 | km | legal minimum ≤ x < 22.6101; legal minimum 0; the corpus cannot bind below it | 5 km is less than half the nearest short-ending segment distance (22.6 km); none of the covering landmark segments needs an end extension. |
| `cone_horizon_h` | 120 | h | 117 ≤ x ≤ legal maximum; legal maximum 120; the corpus cannot bind above it | 120 h is the round forecast maximum; the five pairs with a watch first reach level 3 at least 54 h before it. A 116 h horizon changes a recorded hurricane-cone outcome. |
| `hurricane_wind_floor_pct` | 10 | % | {10} | 10% separates adjacent recorded advisories; 5% promotes the weaker band, while 20% demotes the stronger. Every covering watch retains at least 54 h lead; named witnesses are in the calibration report. |
| `tropical_storm_wind_floor_pct` | 5 | % | {5} | 5% distinguishes the lowest positive 34-kt band from the <5% band. Ordering/reversal exceptions are recorded, never smoothed. |
| `development_chance_floor_pct` | 0 | % | legal minimum ≤ x ≤ 20; legal band floors only; legal minimum 0; the corpus cannot bind below it | 0% follows the brief: any seven-day region. The recorded Atlantic scenario is 20%; the archive has no outlook, so this is not corpus-calibrated. |

<!-- /ladder:thresholds -->

Each interval describes values that leave **every level and deciding rule**
unchanged when that threshold alone moves. It does not express a confidence
interval or a safety guarantee. Distances are continuous (inclusive lower,
exclusive upper bounds); hours are integer values, and probability floors must
be legal band lower bounds. Bounds are displayed to six decimal places; the
evidence file lists reproducible witness values just beyond each bound. An open end names the
legal domain boundary and cannot support a beyond-domain mutation. These
intervals are local to this corpus, these landmarks, and these scenarios.

The geographic defaults are deliberately tighter than the outcome intervals:
25 km lies within the factor-of-two gap, 7.6 to 29.1 km, and 5 km is less than
half the nearest short-ending segment's 22.6 km. A hidden match under a stronger
rule can preserve an outcome even when coverage has changed. The 120-hour cone
horizon and 10% hurricane floor retain at least 48 hours before every first
covering watch. The 5% tropical-storm floor reads the lowest positive band; a
0% floor would promote the `<5%` band. A development floor of 0% keeps the brief's
literal "any seven-day region" rule, even without a stated chance. The recorded
Atlantic 20% scenario binds that default; the archive has no outlook products.

## Incomplete assessments

Every input the assessment lacked is named. Its level is then a floor: "at
least level … from the available products," with the missing inputs alongside
it. All Clear with missing inputs is never a claim that those inputs were
checked. The subset has no arrival-time KMZ and replay has no outlook or NWS
alerts; the Miami-Dade replay therefore cannot claim complete coverage.

## Storm threats, arrival readings, and changes

Each storm has a threat record: its category and development text, whether its
cone covers the location, distance and bearing from the current center, and
the track's closest approach with its instant and lead. These describe the
official forecast; they do not alter a rule or level.

Earliest-reasonable and most-likely wind arrivals use only resolved instants
carried by the arrival products. The reader follows the straight path in the
product's geographic coordinates from the current center to the location and
uses the labelled isochrones it crosses. It reads before, between, or after
those instants, outside the 5% contour, or unresolved with a reason. A path
that leaves the contour and returns, or contradicts a closed contour, reads
nothing. Map-layer products without instants remain unresolved. Without a
product, the forecast track's closest approach is explicitly labelled
**"track closest approach, not a wind arrival"**. No label is parsed or instant
guessed by the engine.

`diff(previous, current)` emits level changes, new advisories, covering official
products added/changed/removed, and cones entered/left, in that order. The first
assessment has initial events. Missing cone information emits no entry or exit;
a missing source is not proof a storm disappeared. Changes do not smooth levels.

## Notifications

`weatherbot.services.policy.decide(state, assessment, changes, settings, now)`
decides each newly stored assessment once, as a pure function of its inputs.
Let $A$ be the location's announced level and $L$ the assessment's level, and
say the assessment is missing an input when it names an unavailable input whose
identity was not unavailable in the announcing assessment:

- **Escalation ($L > A$, or initial $L \ge 2$):** always sent immediately,
  never held and never suppressed by cooldown or quiet hours; $A$ becomes $L$,
  and any pending held drop is withdrawn. Initial level 1 is `informational`
  and sets $A$ to 1.
- **Drop ($L < A$):** held for a confirmation cycle at `now + confirm_after`
  when the assessment is missing a previously available input (at most
  `max_holds = 3` holds, after which the drop is decided as `"at least"`), or
  on the first drop when the assessment carries no `advisory_issued` event and
  no covering official product from the announcing assessment expired at or
  before `assessment.as_of` (the no-advisory check never holds the same drop
  twice). A drop that is not held is decided against its key `("level", A, L)`
  and sets $A$ to $L$.
- **Other triggers:** `advisory_issued` with `in_cone` true (`("advisory",
  atcf_id, advisory)`), `cone_entered` (`("cone", atcf_id)`), and
  `official_added` / `official_changed` (`("official", "nws_alert", codes)` for
  NWS alerts, so an update that keeps its codes is the same event, and
  `("official", "watch_warning_segment", atcf_id, codes)` for NHC segments).
  `official_removed`, `cone_left`, and `advisory_issued` outside the cone are
  `informational`.
- **Cooldown and quiet hours:** a keyed trigger sent within `[notifications]
  cooldown_hours` (default 6 h) is `repeat`. Outside an escalation cycle, a
  non-escalation trigger at level 1 or 2 during `[notifications]` quiet hours
  is `quiet_hours`; level 3 and above are never held back by quiet hours.
- **One notification per location per cycle:** emitted when at least one
  decision is `escalation` or `sent`. Its title is `"<location>: level <A>,
  <label>"`, with $A$ the announced level after the decisions — $L$, except
  while a drop is held, so a held drop never shows through another trigger's
  notification (quiet hours read the same level) — and its body has at most
  four lines: the level line first when the level decision was sent, followed
  by each sent trigger's `ChangeEvent.detail`, with no coordinates, distances,
  bearings, or arrival instants.

## What does not move the ladder

AI output, storm distance alone, wind radii, surge graphics, and arrivals do
not set a level. Storm Surge Warning/Watch and Extreme Wind Warning are
official context under the present specification; the operator's separate
[issue #33](https://github.com/nathanramoscfa/weatherbot/issues/33) owns whether
those events should change the ladder. Unknown official codes remain visible.

## Historical calibration — 2026-10-20

The corpus contains 310 advisories of Irma (2017), Dorian (2019), Ian (2022),
and Milton (2024). Each is replayed at Miami-Dade County Hall and Parliament
Square, Nassau: eight timelines, 620 assessments, plus the 13 shared recorded
scenarios. The corpus manifest, ruleset, advisory instants, deciding rules,
change kinds, and covering official codes are frozen in the goldens.

The original targets asked for 48 hours before the first covering watch,
level 2 before level 3, and no more direction reversals than official products.
Those requirements conflict: Milton's first advisory puts Miami-Dade inside
the hurricane cone (54 hours before the watch), its second cone misses, and
suppressing the first match loses the required lead. **On 2026-10-20 the
operator approved measured ordering and reversal exceptions while retaining
the 48-hour watch lead target.** No hysteresis, invented product, or smoothed
transition is added to conceal them. Dorian and Ian also first reach level 3
before level 2; the table reports every reversal exception.

<!-- calibration:lead-times -->

| Pair | First level 2 (advisory, UTC) | First level 3 (advisory, UTC) | First watch | First warning | L3 lead (h) | Reversals engine / official |
| --- | --- | --- | --- | --- | --- | --- |
| AL052019-miami-dade | 12 at 2019-08-27T09:00:00Z | 10 at 2019-08-26T21:00:00Z | — | — | — | 5 / 0 |
| AL052019-nassau | 12 at 2019-08-27T09:00:00Z | 8 at 2019-08-26T09:00:00Z | 24 at 2019-08-30T09:00:00Z | 26 at 2019-08-30T21:00:00Z | 96.0 | 7 / 1 |
| AL092022-miami-dade | 6 at 2022-09-24T15:00:00Z | 1 at 2022-09-23T09:00:00Z | 18 at 2022-09-27T15:00:00Z | 19 at 2022-09-27T21:00:00Z | 102.0 | 2 / 1 |
| AL092022-nassau | 1 at 2022-09-23T09:00:00Z | — | — | 19 at 2022-09-27T21:00:00Z | — | 2 / 1 |
| AL112017-miami-dade | 18 at 2017-09-03T21:00:00Z | 22 at 2017-09-04T21:00:00Z | 34 at 2017-09-07T15:00:00Z | 36 at 2017-09-08T03:00:00Z | 66.0 | 1 / 1 |
| AL112017-nassau | 16 at 2017-09-03T09:00:00Z | 19 at 2017-09-04T03:00:00Z | 31 at 2017-09-06T21:00:00Z | 33 at 2017-09-07T09:00:00Z | 66.0 | 5 / 3 |
| AL142024-miami-dade | 2 at 2024-10-05T21:00:00Z | 1 at 2024-10-05T15:00:00Z | 11 at 2024-10-07T21:00:00Z | 13A at 2024-10-08T12:00:00Z | 54.0 | 2 / 1 |
| AL142024-nassau | 1 at 2024-10-05T15:00:00Z | — | — | — | — | 0 / 0 |

<!-- /calibration:lead-times -->

"—" means the corpus contains no such level or covering watch/warning; no lead
claim is made for it. Ian at Nassau goes directly from level 2 to an official
level 4 warning. A reversal is a direction change among non-equal consecutive
levels, including the eventual decline. Closest approaches in the
[full evidence](ladder-calibration.json) are minima across the **forecasts**,
with their advisory and instant, not observed storm positions.

`scripts/calibrate_ladder.py --check` repeats the sweep and checks the evidence.
The mutation suite removes each non-fallback rule, swaps each adjacent pair,
and crosses each finite threshold bound. The model records exactly those
adjacent swaps the references cannot distinguish, including overlaps masked
by stronger rules and the non-matching `all_clear` fallback. The cached suite
cross-checks full probability products against the clipped landmark windows.
Golden changes require a new operator approval of the exact review digest;
an approval cannot be inferred from a regenerated file or a passing test.
