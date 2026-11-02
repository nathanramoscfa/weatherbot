<!-- docs/AI.md -->
# The Claude layer

Weatherbot can use Claude to explain, in plain language, what the threat engine
decided. AI is optional. It needs an Anthropic credential, and everything else
(the levels, the evidence, the notifications, the dashboard) works without one.
This page covers what the AI does and never does, what leaves the machine, the
briefing, the change summary, the chat with its tools, and the outlook
narration, with the validators that guard them, the eval set, how to give
Weatherbot a credential, the `[ai]` settings, the spend ledger with its daily
cap and the measured cost, and the loopback API the dashboard reads them
through. Phase 6 adds the products step by step; this page grows with them.

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
for narration, official products' public text with their links removed, for
the chat the questions you ask and what its tools read, and, with narration on,
NHC's public outlook graphic. It never carries a location's coordinates
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
the new level and no other.

`serve` writes them automatically while `[ai] change_summaries` is on (the
default). At start it marks the newest stored assessment, so history is never
backfilled; after every cycle (its own, or one another process ran) it reads
the assessments stored since and summarizes them newest first, one at a time,
while the AI is `ready`. Its mark moves past every assessment it reads, so a
summary missed while `serve` was down, or while AI was off, paused, or capped,
is never written later: a briefing covers it. It logs only each assessment's
id, the outcome, and its reason, and a failure never stops the monitor.

## The chat

`weatherbot ask QUESTION [--location NAME] [--json]` asks Claude one question
about your locations. Claude answers from Weatherbot's stored data only, which
it reads through nine read-only tools; it searches nothing and fetches no URL.
The command prints:

1. a label line: "AI answer · Claude Sonnet 5.5 · from Weatherbot's stored data
   · not an official product";
2. each tool's name as Claude uses it ("looked up: get_storm"), to standard
   error in plain text and dimmed in a terminal;
3. the answer, sentence by sentence, each sentence once it passes its checks;
4. the disclaimer's notice.

The question is 1 to 2,000 characters. Its message starts with a short preamble
that names the official level and the assessment hour of the location asked
about (`--location`), or of every location, so the answer starts from the
engine's level. A sentence that states another current level for a location
("Miami-Dade County Hall is now level 4", "the official level is 4", "level 4
now"), carries a URL, or carries a position that no NOAA text the tools returned
states is never shown. The rest of the answer is withheld ("Withheld: level"),
and a terminal, which cannot unprint, says to disregard the answer above.
`--json` prints one `ask` document (`docs/schema/ask.schema.json`) with the
question, the location, the status, the answer or the reason it was withheld or
unavailable, the tools used, the model, Anthropic's request ids, and the cost
in micro-dollars. The exit code is 0 when the answer arrived whole, 1 when it
was withheld or AI was unavailable, and 2 for a usage error.

Each request is the chat's own frozen prompt and the nine tool definitions,
each with a five-minute cache marker, then the conversation so far. Thinking is
adaptive at effort `medium`, `max_tokens` is 4,000 a request, and `tool_choice`
is `auto`. The prompt tells Claude to write "is level N" only for a location's
current official level, and to describe any other level by its label.
Fine-grained tool-input streaming stays off, so the API checks every tool call
against its strict schema. The tool calls of one round run together, and their
results return in one message. A turn that still asks for a lookup after six
rounds ends "AI unavailable: the answer needed too many lookups". Every round is
one request in the ledger (kind `chat`), under the same cap.

### The tools

| Tool | Input | Returns |
| ---- | ----- | ------- |
| `list_locations` | none | each location's name, current level, completeness, and assessment hour; never a point |
| `get_assessment` | a location | the briefing's context without its NOAA texts: the level, rule, evidence, official products, wind probabilities, each storm's threat, the changes, and the sources |
| `get_evidence` | a location | the deciding rule, its trigger, each matching product, and the unavailable inputs |
| `get_alerts` | a location | the official products that cover it; each NWS alert's headline, description, and instruction as NOAA text |
| `get_storms` | none | each active storm's name, ATCF id, basin, classification, category, and latest advisory |
| `get_storm` | an ATCF id | the storm's summary, what it means for each location, and its latest TCP as NOAA text |
| `get_outlook` | `atl`, `pac`, or `cpac` | the basin's TWO as NOAA text and the outlook areas' chances of formation |
| `get_ladder` | none | the ladder's text and the thresholds in effect |
| `get_history` | a location, 1 to 10 | the most recent assessments' levels and changes, newest first |

Each tool reads the stored data through the AI engine, which refuses every
write. Each returns the same privacy-reduced shapes a briefing's context uses:
no coordinate, geometry, URL, path, or engine-written sentence; distances as
bands, bearings as compass points, times to the hour; NOAA text in escaped
blocks without its links. A storm's own position, which its TCP states, is
public and stays inside the TCP's block. No input takes a URL, a path, a query,
or SQL. Before a call runs, Weatherbot checks its name against the nine and
validates its input again. An unknown tool, a bad input, or an unknown location
or storm gets an error result that lists the allowed values, and nothing else is
read. Every result is at most 8,000 characters, and a longer one is cut and
marked.

### Conversations and their bounds

`weatherbot ask` is one turn. In `serve` (from Phase 6 Step 4), a conversation
lives in memory only: append-only, with every block Claude returned kept as
received (thinking and tool blocks included), so each request replays the
history byte for byte. At most 8 conversations of 20 questions are kept. Each is
dropped after 2 idle hours or a restart, and a withheld or unavailable answer
closes its conversation. When a newer assessment is stored between two
questions, a system message after the new question states the new official
levels. Questions are never logged, at any level.

## The outlook narration

With `outlook_narration = true` under `[ai]` (it is off by default), `weatherbot
brief --outlook {atl,pac,cpac} [--horizon {2d0,7d0}]` prints an "AI
interpretation of the official graphic" for the basin's graphical tropical
weather outlook, seven days by default. The graphic is the PNG stored with the
latest snapshot, read by its SHA-256 from the raw-response cache, so nothing is
downloaded. It is sent as an image with the basin's TWO in an escaped block,
under the narration's own frozen prompt. Thinking is adaptive at effort `low`,
with `max_tokens` 2,000. The ledger counts the image at its visual tokens (825
for a 900 by 679 map), not its base64 text.

The narration has a summary, an item per marked area (where it lies, and its
chance as the TWO states it), and a caveat. It is withheld when it states any
level, a URL, or a position, lacks its caveat, passes its bounds, or states a
chance that the TWO's text does not. Chances are compared as numbers, so "20%"
matches the TWO's "20 percent". A narration is stored once per graphic, TWO
text, model, and prompt version, and asking again shows the stored one without a
request (`--new` asks for a new one). `--json` adds a `narration` entry to the
`brief` document.

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
is ever shown. The chat checks each sentence for a URL, an unquoted position, or
a statement that a location's current level is other than the engine's. A
narration may state no level at all, no URL, and no position, and only the
chances its TWO states.

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

`tests/ai/eval/chat_cases.py` adds five recorded chat turns over both landmarks
and the recorded snapshot (one lookup, several lookups at once and then once
more, a ladder question, a storm question, and the twin of a storm question
whose TCP carries the hostile lines), and two narrations (the Atlantic seven-day
and the Eastern Pacific two-day graphics). A chat recording keeps every round's
event stream. Its test replays the turn against its own database, and each
request must equal the recorded one byte for byte. The injection twin's calls
stay within the nine tools with valid inputs, and its answer states the
engine's level and prints no link. `scripts/record_ai_fixtures.py chat narration`
re-records them (ask first).

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

Measured on 2026-11-01 over the recorded chat turns and narrations (Phase 6
Step 3), on `claude-sonnet-5-5`, from the recorded usage at list price:

| Product | Cases | Requests | Prompt tokens a request (min / max) | Output tokens a request (min / max) | Cost (min / max) |
| ------- | ----: | -------: | ----------------------------------- | ----------------------------------- | ---------------- |
| Chat turn | 5 | 2 to 3 | 3,991 / 10,867 | 55 / 635 | $0.0092 / $0.0270 a turn |
| Narration | 2 | 1 | 2,496 / 2,643 | 270 / 288 | $0.0051 / $0.0088 |

The chat's tools and prompt form a cached prefix of about 3,800 tokens, which
every round after the first reads at the cache-read price; each later round
also reads the conversation so far from the cache. A narration's prompt caches
the same way (1,360 tokens), and its image counts 825 visual tokens. Against the
estimates (a chat turn $0.02 to $0.035, a narration about $0.01), both stay at
or under, so `max_tokens` 4,000 a round, six rounds a turn, 2,000 a narration,
and the $1.00 cap stand. The committed chat and narration recordings cost
$0.11.

### The pause and the allowance

The ledger holds two controls beside the cap, each a zero-token row:

- **Pause.** A pause refuses every request until a resume, across days and
  processes: the manual kill switch beside the cap's automatic one.
- **Allow more today.** An allowance raises only today's limit, by at most one
  day's cap, at most three times a day.

The API's controls write both (`PUT /api/ai/pause`, `POST /api/ai/allowance`,
below); the settings page gains their buttons in Phase 6 Step 5. The cap itself
changes only in `weatherbot.toml` or `WEATHERBOT_AI_DAILY_CAP_USD`.

## The API

`serve`'s loopback API carries the AI under every guard of the rest of the API
(`docs/api/openapi.json` is the contract). Nothing it answers carries the key,
a prompt, a context, or a question.

**Reads.** Plain reads that send nothing to Anthropic:

- `GET /api/ai`: the state, its reason, where the credential comes from
  (`environment`, `auth_token`, `profile`, or `none`, never its value), the
  models, the features, the pause, and today's meter: spend, open
  reservations, the cap, today's allowances and how many remain, the request
  count, and tokens in total and by kind.
- `GET /api/ai/calls?limit=` (at most 100): the ledger, newest first. Each row
  is a kind, a model, a location name, a status, its times, tokens, cost, stop
  reason, refusal category, and error kind; no row carries text.
- `GET /api/ai/briefings?location=`: each watched location's newest stored
  briefing (its sections, or its withheld reason and no text), with the model,
  the prompt version, the assessment it was written for, when it was stored,
  and whether a newer assessment has made it stale.
- `GET /api/ai/summaries?location=&limit=` (at most 200): the stored change
  summaries, newest first.
- `GET /api/ai/narrations`: the newest stored narration of each of the latest
  snapshot's outlook graphics, and whether narration is on.

A source in a stored product is resolved from its stored record (its key,
register source, title, code, issuer, advisory, and issuance), never from the
model. Its `url` is only a public NOAA product page that names no point: NHC's
pages for NHC's sources and the NWS alerts portal for a zone alert. A source
whose requests name a point (an NWS point or point-alert query, a geocode) has
no link at all.

**Streams.** A request spends money, so each is a `POST` behind the same-origin
JSON rule: a foreign `Origin` or a cross-site `Sec-Fetch-Site` answers 403 and
a body that is not JSON 415, so a hostile page can neither start a request nor
read its answer. The answer is a stream of server-sent events, each a JSON
object with a `kind`; the page reads it with `fetch`, because `EventSource`
cannot `POST`.

- `POST /api/ai/briefings` (`{"location": ..., "new": false}`): `started` (the
  model, the assessment and its time, the prompt version), a `section` per
  validated section, then `done` (the stored briefing's id and time, and
  whether it was reused); or `withheld` (remove every section shown) or
  `unavailable`, each with a reason and fixed text.
- `POST /api/ai/chat` (`{"question": ..., "conversation_id": null,
  "location": null}`, a question of 1 to 2,000 characters): `started` (the
  conversation and the model), a `tool` per lookup (its name only), a `text`
  per checked sentence, then `done`; or `withheld` or `unavailable`.
- `POST /api/ai/narrations` (`{"basin": "atl", "horizon": "7d0"}`): `started`,
  then `done` with the narration; or `withheld` or `unavailable` (`disabled`
  while `[ai] outlook_narration` is off).

Before a stream begins, a state other than `ready` answers 503 with a JSON
`detail` naming the reason (`disabled`, `no_credential`, `paused`,
`auth_failed`, ...), `capped` answers 429, and at most four AI streams run at
once on the server: a fifth answers 429 `busy`. A reservation refused once the
stream has begun ends it with an `unavailable` event. When the page is closed,
the server cancels the request and the ledger settles it (at its ceiling, as
`incomplete`, because tokens may have been billed).

**Controls.** `PUT /api/ai/pause` (`{"paused": true}` or `false`) writes a
pause or resume row when the state changes, and `POST /api/ai/allowance`
(`{"usd": 0.5}`) adds more than nothing and at most one day's cap to today's
limit (422 otherwise), three times a day (a fourth answers 409). Both answer
the status of `GET /api/ai`.

**The official outlook graphics.** `GET /api/outlook` lists the outlook
graphics the latest snapshot stored (basin, horizon, size, SHA-256, and when it
was fetched), and `GET /api/outlook/{basin}/{horizon}` serves one as
`image/png`, read from the stored answers by its SHA-256, never from a path or
the network; any other basin or horizon, a missing graphic, or a body that is
not that PNG answers 404.

**Events.** The dashboard's event stream (`GET /api/events`) carries an `ai`
event, naming ids, a kind, a status, and a location, never text: a settled
request and a pause or an allowance invalidate the `ai` query, and a stored
briefing, summary, or narration invalidates `briefings`. The cycle watcher
reads the newest `ai_calls` and `ai_outputs` ids every 10 seconds, so a
`weatherbot brief` or `ask` in a terminal reaches an open page within 15
seconds.

## The page

The dashboard shows the AI beneath or beside the engine's level, never in its
place, and labels every block: the kind, the model's display name, when it was
written (in the browser's zone and in UTC), and "AI-generated · may be wrong ·
the level above comes from official products".

- **Dashboard.** Each location card holds an AI briefing panel after the
  deciding rule, the evidence, and the evacuation toggle: the stored briefing
  with its sources, and "Brief me", which streams a new one section by section
  with a writing indicator until the stored briefing replaces the draft. A
  withheld briefing shows only "Withheld:" and its reason; a briefing written
  for an older assessment says which one and offers "Brief me again".
- **Timeline.** Each assessment entry with a stored change summary shows it
  beneath the engine's changes, labeled, or its withheld reason.
- **Ask (`/ask`).** The engine's level badges for every location above the
  chat, a location picker, the transcript (each lookup as a chip such as
  "Reading storms", the answer appearing sentence by sentence), a question box
  of at most 2,000 characters with a counter, and "New conversation". A
  withheld or unavailable answer closes the conversation. The conversation id
  lives only in the page, so a reload starts afresh.
- **Storms.** The Graphical Tropical Weather Outlook section shows NHC's six
  official graphics from the stored snapshot, credited to the National
  Hurricane Center; with `[ai] outlook_narration` on, each has its stored
  narration or "Interpret (AI)", labeled "AI interpretation of the official
  graphic".
- **Settings (`#ai`).** The state and its reason, where the credential comes
  from (never its value), the models and features, today's meter (spend and
  reservations against the cap and allowances, as a bar with the values in
  text), the recent requests (kind, model, tokens, cost, status, time), "Pause
  AI" or "Resume AI", and "Allow $X more today" behind a confirmation. Every
  value refreshes from the `ai` events.

When AI cannot answer, a banner says why: off (no credential, with how to add
one; or `[ai] enabled = false`), paused by you, today's cap reached (it resets
at midnight; you can allow more in Settings), or unavailable with its reason
("authentication failed — check the credential, then restart serve"). A page
runs one AI stream at a time, and every AI button waits while it runs; leaving
the page cancels the stream.

Every AI text is plain text in a paragraph that keeps its line breaks: never
Markdown or HTML, so `<script>`, `&amp;`, or `[a link](https://…)` in model
text shows exactly as written. The only links are a source's `url` from the
API, opened with `rel="noopener noreferrer"`. The page writes no AI text,
question, or answer to the console, sends AI requests only as same-origin JSON
through the generated client, and never talks to Anthropic.

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
