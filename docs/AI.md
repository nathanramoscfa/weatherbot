<!-- docs/AI.md -->
# The Claude layer

Weatherbot can use Claude to explain, in plain language, what the threat engine
decided. AI is optional. It needs an Anthropic credential, and everything else
(the levels, the evidence, the notifications, the dashboard) works without one.
This page covers what the AI does and never does, what leaves the machine, how
to give Weatherbot a credential, the `[ai]` settings, and the spend ledger with
its daily cap. Phase 6 adds the products step by step; this page grows with
them.

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
retention terms apply to what is sent. The exact shape of each product's
request, and the coarsening (distance bands, compass points, hours), is
documented here as each product lands.

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
reaches it. The measured cost of each product is recorded here as the products
land.

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
