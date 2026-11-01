<!-- docs/AI.md -->
# The Claude layer

Weatherbot can use Claude to explain, in plain language, what the threat engine
decided. AI is optional. It needs an Anthropic credential, and everything else
(the levels, the evidence, the notifications, the dashboard) works without one.
This page covers what the AI does and never does, what leaves the machine, the
briefing and the change summary with the validators that guard them, the eval
set, how to give Weatherbot a credential, the `[ai]` settings, and the spend
ledger with its daily cap and the measured cost. Phase 6 adds the products step
by step; this page grows with them.

## What the AI does, and what it never does

Official products decide; Claude narrates. The engine decides every level from
fetched NHC and NWS products, and the monitor decides every notification. The
AI layer:

- never decides, stores, or changes a level, a storm, an alert, a location, a
  setting, or a notification. It opens the database through a SQLite authorizer
  that refuses every write except to its own two tables (`ai_calls`, the ledger,
  and `ai_outputs`, which holds the products Phase 6 adds), and every schema
  change;
- never fetches a URL for the model and never searches the web;
- treats everything the model writes as data: validated before it is shown,
  shown as plain text, never executed, never followed as a link;
- is labelled as AI wherever it appears, with the model and the time.

A refusal from the model is shown as "AI unavailable (declined)". Weatherbot
never falls back to another model.

## What leaves the machine

A request to Anthropic carries location names, the engine's outputs coarsened
for narration, official products' public text with their links removed, and,
for the chat, the questions you ask. It never carries a location's coordinates
at any precision, a polygon or other geometry, a URL, a file path, a setting
other than the ladder's thresholds, or the credential. Anthropic's data
retention terms apply to what is sent.

One module builds every request's context (`services/ai/context.py`), from the
engine's structured fields only:

- **No engine-written sentence.** The evidence, official products, changes, and
  unavailable inputs each carry a sentence the engine wrote for the terminal,
  with a whole-kilometre distance and the minute of closest approach. Together
  with the public forecast track those would pin a home to within a kilometre,
  so none is sent.
- **Coarsened distances, bearings, and times.** A storm's distance from the
  location is one of six bands: within 50 km (30 mi), 50–100 km (30–60 mi),
  100–200 km (60–125 mi), 200–400 km (125–250 mi), 400–800 km (250–500 mi), or
  beyond 800 km (500 mi). Its bearing is one of 8 compass points. Every
  instant, closest approach included, is rounded to the nearest hour in UTC,
  and the lead time to whole hours.
- **Sources as keys.** Each product reaches the model as a key (`S1`, `S2`, …)
  with its code, issuer, advisory, and issuance. The model cites keys; the
  server maps each key back to its record for display, so neither the model nor
  an injected advisory can put a link on the page.
- **NOAA text in escaped blocks.** Each storm's TCP, the TWO of every basin the
  snapshot holds, and the covering alerts' headline, description, and
  instruction go in `<noaa_product key=… code=… issued=…>` blocks. Every URL in
  them (a scheme, `www.`, or a bare host with a path, such as
  `hurricanes.gov/graphics_ep5.shtml`) becomes "[link removed]", `&`, `<`, and
  `>` are escaped so no text can close its block, and each text is capped at
  12,000 characters (marked when cut). A storm's own position and the public
  distances a product quotes stay: they are public. A context over 60,000
  characters is refused as too large.

Bands, compass points, and hours leave a location's area, not its point, in any
one request. Across many requests during one storm, someone holding all of
them could still narrow the area to tens of kilometres; Anthropic's retention
terms govern what it keeps. No prompt, context, question, or answer is logged
at any level, and a withheld product's text is never stored, logged, printed,
or shown.

## Briefings

`weatherbot brief [LOCATION]` asks Claude for a plain-language briefing on a
location's latest stored assessment, or on every stored location in turn
(`status` or `check` assesses first). It prints:

1. a label line: "AI briefing · Claude Sonnet 5.5 · for the assessment of
   2026-10-13 01:30 UTC · not an official product";
2. each section as it streams and passes the validators: the situation (a
   paragraph per threatening storm, or on the quiet tropics), what it means
   here, a timeline, the actions (the ladder's for the level, then "Follow the
   instructions of your local officials."), and the sources the briefing cited;
3. the disclaimer's notice.

A briefing is written once per location, assessment, model, and prompt
version: asking again shows the stored one without a request, and `--new` asks
for a new one. A newer assessment makes the stored briefing stale. A section
that breaks a rule is never printed: the briefing ends "Withheld: <rule>" and is
stored withheld with its reason and no text. A briefing cut off (a `max_tokens`
stop or a dropped stream) is withdrawn as incomplete; a terminal cannot unprint,
so it says "disregard the sections above". `--json` prints one `brief` document
(`docs/schema/brief.schema.json`) with the model, the prompt version, the
status, the briefing or the withheld reason, the sources its keys name, and
the request's cost in micro-dollars. `--cost` prints today's spend, cap,
allowance, and requests and tokens by kind, and sends nothing. The exit code
is 0 when every briefing was written or reused, 1 when one was withheld or AI
was unavailable (with the reason), and 2 for a usage error.

Each request is the frozen system prompt (the narrator's role and limits, the
rule that text inside `<noaa_product>` blocks is data and never an instruction,
the ladder rendered from the code, the thresholds in effect, and the output
contracts), marked for the five-minute cache, then the context and a task line.
Thinking is adaptive at effort `low`, with `max_tokens` 6,000. The prompt names
no storm, year, date, or place; its SHA-256 is the prompt version recorded on
every ledger row and stored product, and a test pins it.

## Change summaries

A change summary says in two to four sentences what changed between a
location's previous and new assessment. It is written once per assessment whose
changes are more than its first (a location's first assessment, and an
assessment with no changes, get none), with `[ai] summary_model`, effort `low`,
and `max_tokens` 1,500, and it is never rewritten. It may name the previous and
the new level and no other. Phase 6 Step 4 writes them automatically in
`serve`.

## The validators

Nothing Claude writes reaches a page or a terminal before it passes
`services/ai/validate.py`. A product is withheld, and stored with only its
reason, when it:

- states a level other than the engine's (for a change summary, other than the
  previous and the new level). An explicit statement is "level", "threat
  level", or "alert level" followed by 1 to 5 or "one" to "five", "level-4",
  "levels 3 and 4", or "the level is 4". The ladder's labels and product names
  ("Hurricane Warning", "Watch / Hurricane Threat") are never read as levels,
  nor is "a level of preparedness" or a water level with a unit;
- cites a source key the context did not hold;
- carries a URL;
- carries a coordinate pair or position (decimal, `20.3N 106.9W`, or "latitude
  20.3 North, longitude 106.9 West") that no NOAA product in the context
  states;
- leaves a required section empty (the situation, what it means here, the
  actions), or passes its bound (1,500 characters a section, 12 timeline items,
  8 actions, 600 characters a summary).

A briefing's sections are checked one by one as they stream, so no failing text
is ever shown. The chat (Phase 6 Step 3) checks each sentence for a URL, an
unquoted position, or a statement that a location's current level is other
than the engine's.

## The eval set

`tests/ai/eval/` builds 31 cases in memory: the recorded 2026-10-12 snapshot at
both landmarks; from the committed replay subset, the advisory where each golden
ladder first reaches each level for Irma (2017) at Miami-Dade County Hall and
Dorian (2019) at Parliament Square, one transition each for Ian (2022) and
Milton (2024), and two downward moves; a live case whose alert queries failed,
so its level is a floor; and injection twins of four briefings, whose TCP
orders the model to state level 5, call a tool, and print a link. Replay
snapshots hold no text products, so a replay twin carries a synthesized TCP.

The recordings in `tests/fixtures/ai/` (response bodies only) are graded offline
on every run: each answer matches its schema, passes its validators against its
own context, and states the engine's level; a contradicting copy of each
(another level, an unknown source key, a URL, a coordinate, an emptied section)
fails; and the injection twins keep the engine's level and print no link.
`scripts/record_ai_fixtures.py eval` re-records the set with the operator's
credential (it spends money; ask first). `scripts/eval_ai.py` grades the
recordings and prints each product's token and cost spread; `--count` adds a
free `count_tokens` request for every prompt, and `--live` regenerates and
grades every case (about $0.30 a run). Neither writes a fixture, and both
refuse to run without a credential.

## The credential

The Anthropic SDK resolves the credential itself, in its own order:

1. `ANTHROPIC_API_KEY`, an API key (recommended: it does not expire, which suits
   the always-on monitor);
2. `ANTHROPIC_AUTH_TOKEN`;
3. an `ant auth login` profile (its refresh token eventually expires, so the
   monitor would need a fresh login now and then).

Weatherbot never reads, copies, logs, stores, or shows the value. It is not a
setting, and `weatherbot.toml` cannot hold it. An empty `ANTHROPIC_API_KEY`
counts as unset, exactly as the SDK reads it, so a profile still applies.

To set an API key on Windows, create it in the Anthropic Console (choose
"Continue with an API key"; identity federation is for cloud workloads), then
open Start, "Edit environment variables for your account", and add a user
variable named `ANTHROPIC_API_KEY`. Never type the key on a command line: shell
history keeps it. A process started before the variable existed does not see
it: open a new terminal, and stop and start the scheduled `\Weatherbot\serve`
task (`schtasks /End` then `/Run`). If it still reports no credential, sign out
and back in.

`weatherbot doctor` reports the credential's source, never its value:

| Situation | The `ai` check |
| --------- | -------------- |
| `[ai] enabled = false` | `skip`: turned off by `[ai] enabled` |
| No credential | `skip`: set `ANTHROPIC_API_KEY` or run `ant auth login` (and notes a blank variable) |
| A credential, `--offline` | `pass`: names the source and today's spend against the cap |
| A credential, online | `pass` after one free `count_tokens` request, or `fail` with the reason only |
| A model the price table lacks | `fail` |

`GET /api/health` carries an `ai` block (`state`, `reason`, `spent_micro_usd`,
`cap_micro_usd`), computed without a request. The state is `off`, `ready`,
`paused`, `capped`, or `unavailable`. `capped` means today's headroom is below
the ceiling of the smallest request, a change summary. `unavailable` follows a
model the price table lacks, or three consecutive authentication failures,
which hold for an hour (or until `serve` restarts). After the hour, one request
is let through, and a success clears the hold.

## The `[ai]` settings

| Key | Default | Override | Meaning |
| --- | ------- | -------- | ------- |
| `enabled` | `true` | `WEATHERBOT_AI_ENABLED` | `false` constructs no client at all |
| `model` | `claude-sonnet-5-5` | `WEATHERBOT_AI_MODEL` | Briefings, chat, and narration |
| `summary_model` | `claude-sonnet-5-5` | `WEATHERBOT_AI_SUMMARY_MODEL` | Change summaries; `claude-haiku-5-5` is the cheaper choice |
| `daily_cap_usd` | `1.0` | `WEATHERBOT_AI_DAILY_CAP_USD` | The daily cap in dollars, 0 to 100 |
| `change_summaries` | `true` | `WEATHERBOT_AI_CHANGE_SUMMARIES` | Write a summary for each changed assessment |
| `outlook_narration` | `false` | `WEATHERBOT_AI_OUTLOOK_NARRATION` | Allow narrating the official outlook graphic |

Each model must be one the price table holds (`claude-sonnet-5-5`,
`claude-haiku-5-5`, or `claude-opus-5-5`), because the cap cannot price another;
a configuration error names the key and the allowed models, never the value.
`weatherbot config show` lists the table with each key's origin.

## The ledger and the daily cap

Every request to Anthropic goes through one path, and every process (`serve`,
`brief`, `ask`) shares one ledger in the database, so two processes can never
pass the cap together:

1. **Reserve.** Before a request is sent, inside one `BEGIN IMMEDIATE`
   transaction, Weatherbot adds today's settled cost, today's open reservations,
   and this request's ceiling, and refuses the request ("capped") when the sum
   would pass today's limit: the cap plus today's allowances. The ceiling is the
   request's serialized text at 2.5 characters a token (images at their
   ⌈width/28⌉ x ⌈height/28⌉ visual tokens) at the input price, plus its
   `max_tokens` at the output price. A prompt estimated past 100,000 tokens is
   refused as too large.
2. **Send.** No request carries `temperature`, `top_p`, or `top_k`; every one
   carries `max_tokens`.
3. **Settle.** The row records the SDK's usage (input, five-minute and one-hour
   cache writes, cache reads, output) and its cost at list price. An error
   answered before any output costs nothing. A stream that ended without its
   final message (cancelled, disconnected, timed out) settles at its ceiling,
   because its tokens were billed but never reported. A reservation older than
   15 minutes, whose process died, counts at its ceiling as abandoned.

"Today" is your local calendar day. The ledger stores no prompt, no answer, and
no credential: only the kind of request, the model, the location's name, the
prompt version, the tokens, the cost, the outcome, and Anthropic's request id.

### The price table

Costs are integer micro-dollars at Anthropic's list prices, read from the
pricing page on 2026-10-30 (`services/ai/pricing.py`, `PRICES_AS_OF`), per
million tokens:

| Model | Input | 5-min cache write | 1-h cache write | Cache read | Output |
| ----- | ----: | ----------------: | --------------: | ---------: | -----: |
| `claude-sonnet-5-5` | $2.00 | $2.50 | $4.00 | $0.10 | $10.00 |
| `claude-haiku-5-5` | $0.10 | $0.125 | $0.20 | $0.01 | $0.50 |
| `claude-opus-5-5` | $4.00 | $5.00 | $8.00 | $0.20 | $20.00 |

Haiku 5.5's prices hold for prompts up to 100,000 tokens, which no request may
exceed. When Anthropic changes a price, `pricing.py`, its date, and this table
change together.

The default cap, $1.00 a day, bounds a month at about $31 even if every day
reaches it.

### Measured cost

Measured on 2026-11-01 over the 31 eval cases on `claude-sonnet-5-5`, prompt
version `f6ef880c…`. Prompt tokens were counted with `count_tokens`, and they
equal the recorded usage's (uncached input, cache writes, and cache reads
together); output tokens and cost come from the recorded usage at list price:

| Product | Cases | Prompt tokens (min / median / p95 / max) | Output tokens (min / median / p95 / max) | Cost (min / median / p95 / max) |
| ------- | ----: | ---------------------------------------- | ---------------------------------------- | ------------------------------- |
| Briefing | 19 | 4,612 / 5,001 / 8,775 / 8,775 | 564 / 682 / 899 / 899 | $0.0079 / $0.0103 / $0.0280 / $0.0280 |
| Change summary | 12 | 3,269 / 3,492 / 3,542 / 3,542 | 117 / 138 / 199 / 199 | $0.0020 / $0.0026 / $0.0097 / $0.0097 |

The frozen prompt caches as planned. The first briefing wrote a 3,732-token
prefix (the system prompt and the briefing's schema) at the five-minute write
price, and every later briefing read it at the cache-read price; summaries share
a 3,025-token prefix of their own. The most expensive requests are the ones
that write the cache, and the briefings over the live snapshot, whose TCP and
TWOs add about 3,500 tokens.

Against the estimates this roadmap was sized from (a briefing about 6,200 input
and 1,500 output tokens, a change summary about $0.010), every 95th percentile
is under twice its estimate: briefing input 1.4 times, briefing output 0.6
times, and the summary's cost 1.0 times. So the ceilings (`max_tokens` 6,000
for a briefing and 1,500 for a summary) and the $1.00 daily cap stand. An
active-storm day of 12 summaries and 4 briefings costs $0.10 to $0.15 at these
rates. The 31 recordings cost $0.27.

### The pause and the allowance

The ledger holds two controls beside the cap, each a zero-token row:

- **Pause.** A pause refuses every request until a resume, across days and
  processes: the manual kill switch beside the cap's automatic one.
- **Allow more today.** An allowance raises only today's limit, by at most one
  day's cap, at most three times a day.

The settings page and the API gain the buttons for both later in Phase 6. The
cap itself changes only in `weatherbot.toml` or `WEATHERBOT_AI_DAILY_CAP_USD`.

## Turning AI off

Set `enabled = false` under `[ai]` in `weatherbot.toml`, or set
`WEATHERBOT_AI_ENABLED=false`. No client is constructed, no request is sent,
`/api/health` reads `off` (`disabled`), and `doctor` skips its `ai` check.
Removing the credential has the same effect (`off`, `no_credential`).

## Logging

The SDK logs each request's whole options, the prompt and the question
included, at DEBUG. So its loggers (`anthropic`, `httpx2`, `httpcore2`) stay at
WARNING at every level, DEBUG included. Every log record and traceback also
loses any Anthropic key shape, any `Authorization` or `X-Api-Key` value, and the
value after `ANTHROPIC_API_KEY=`. Every SDK error is mapped to a fixed reason
before it is logged or shown, because an SDK message can quote request content.
