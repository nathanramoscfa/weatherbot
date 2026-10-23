# Weatherbot

A personal hurricane-threat monitor. Weatherbot reads the official National
Hurricane Center (NHC) and National Weather Service (NWS) products for named
locations, decides a five-level threat from those products alone, notifies
on change, keeps history, and uses Claude to explain the situation in plain
language. It is a command-line tool plus a local-only web app; version 2
specifies both in [the project brief](docs/brief/weatherbot-v2-brief.md).

## Status

Version 2 is a from-scratch rewrite in progress. Phase 1 (foundation and
discovery), Phase 2 (sources and persistence), and Phase 3 (the threat
engine) are complete; Phase 4 (monitoring and notifications) is in progress.
No version 2 package is released. The commands below read the official
products, and `status` decides each location's level from them alone, with
the evidence behind it, and notifies you of a change through the in-app log
and a Windows toast; nothing runs on a schedule yet.
The plan lives in [the roadmap](docs/roadmap/ROADMAP.md).

## Commands

Run each command with `uv run weatherbot ...` from a checkout. The examples
use the two public landmarks the project tests with; add your own places the
same way. Your locations stay in your local database.

```sh
# Watch a place. The NWS says whether it covers the point; Nominatim names it, once.
weatherbot locations add "Miami-Dade County Hall" --lat 25.7757 --lon -80.1966
weatherbot locations add "Parliament Square" --lat 25.0778 --lon -77.3405
weatherbot locations add "Miami-Dade County Hall" --lat 25.7757 --lon -80.1966 --polygon county  # also store the county's shape
weatherbot locations list            # the only command that prints coordinates
weatherbot locations remove "Parliament Square"

weatherbot fetch                     # fetch every official source once; print each outcome
weatherbot storms                    # active storms, their products, the outlook, wind probabilities
weatherbot storms --no-fetch         # the same from the latest stored snapshot, with its age
weatherbot alerts --location "Miami-Dade County Hall"   # NWS alerts, which cover it, in UTC and local time
weatherbot alerts --location "Parliament Square"        # outside NWS coverage: the segments, covering ones first

# Decide and store each location's level: the evidence, every storm's threat, what changed.
weatherbot status
weatherbot status --location "Parliament Square" --no-fetch   # one location, from the latest stored snapshot

# An official evacuation order is in effect: hold the location at level 4 or above until off.
weatherbot locations evacuation "Miami-Dade County Hall" on
weatherbot locations evacuation "Miami-Dade County Hall" off

# Replay a historical storm's advisories at a location: its ladder, stored nowhere.
weatherbot replay AL112017 --location "Miami-Dade County Hall" --corpus tests/fixtures/replay
weatherbot replay AL112017 --location "Miami-Dade County Hall" --corpus tests/fixtures/replay --every

weatherbot doctor                    # paths, database revision, every source and layer
weatherbot doctor --offline          # local checks only, with the heartbeats

# One monitor cycle on demand: fetch, assess and store every location, record the heartbeats.
weatherbot check --once
weatherbot notify log                # the newest stored notifications first, with their deliveries

# Windows toasts: register Weatherbot's toast identity once (your account only; no administrator).
weatherbot notify setup
weatherbot notify test               # send a test notification through the log and the toast
weatherbot notify setup --remove     # remove the identity again

weatherbot config show               # every setting's value, and whether it came from the default, weatherbot.toml, or the environment
weatherbot config path               # where the settings file, the database, its backups, and the lock files live
```

`status` prints, for each location, the level and its deciding rule with each
piece of evidence, the actions, the official products that cover the location
(and county-zone alerts outside its zones), the wind-speed probabilities there,
each storm's threat (category, cone, distance and bearing from its center,
closest approach, and both wind arrivals), the changes since the previous
assessment, the location's breakpoint span, and its evacuation-order toggle.
When an input was unavailable the level reads "at least". Distances and
bearings stay on your terminal and in your local database. A rerun over the same
snapshot stores nothing new; `locations remove` removes a location's
assessments with it. `replay` reads only the corpus directory it is given;
`tests/fixtures/replay` holds four storms with probabilities around the two
landmarks only, and `scripts/fetch_replay_corpus.py convert --full` writes the
complete products for your own locations.

Every command that fetches (`fetch`, `storms`, `alerts`, `status`, and
`check --once`) runs one monitor cycle, under a lock every Weatherbot process
shares, and records it with a heartbeat per source. When another cycle is
running, the command says so and exits 1. `status` shows a yellow banner when a
heartbeat is stale (its last success is older than twice the cadence a scheduled
monitor promised for it); a manual command promises no cadence, so it never
makes data look stale.

`status` and `check --once` send each notification the policy decides through
the in-app log and, on Windows, a toast: the title, its first two lines, and
the disclaimer's reminder, under the identity `notify setup` registers.
`notify log` shows each delivery's result. A toast reads `delivered` when Windows
accepted it, `disabled` when Windows' notification settings turn Weatherbot off
(with the setting), `failed` with Windows' error code, or `unavailable` before
`notify setup` and everywhere but Windows. With Do Not Disturb on, Windows
files the toast in the notification center without showing it, and tells
Weatherbot nothing. `notify test` exits 1 when the toast failed, was disabled,
or was unavailable on Windows. Set `toast = false` under `[notifications]` in
`weatherbot.toml` to keep notifications in the log only.

`locations list`, `fetch`, `storms`, `alerts`, `status`, `replay`, `doctor`,
`check --once`, `notify log`, `notify setup`, `notify test`, `config show`, and
`config path` take `--json` and print one JSON document whose schema is in
[docs/schema/](docs/schema/).
`--verbose` (before the command: `weatherbot --verbose fetch`) logs at DEBUG
to standard error. The exit status is 0 when everything answered, 1 when a
source failed or a check did, and 2 for a usage error. With one location,
`alerts` needs no `--location`. The first command shows the disclaimer, and
every read command ends with a one-line reminder of it.

Version 1 is retired. It remains installable with
`pip install weatherbot==1.0.0`, and its source is the
[`v1.0.0` tag](https://github.com/nathanramoscfa/weatherbot/tree/v1.0.0).

## Disclaimer

Weatherbot is informational only. It is not an official source, is not
affiliated with or endorsed by NOAA, the NHC, or the NWS, and is never a
substitute for official guidance: follow your local emergency management
authorities and official evacuation orders. The software is provided "as
is", without warranty, and its authors accept no liability for decisions
made from it. Read the full text in
[DISCLAIMER.md](https://github.com/nathanramoscfa/weatherbot/blob/main/DISCLAIMER.md).

## Development quickstart

Weatherbot uses [uv](https://docs.astral.sh/uv/) and Python 3.13.

```sh
uv sync                      # create .venv and install the locked dependencies
uv run weatherbot --version  # prints 2.0.0.dev0
uv run pytest                # run the tests
```

[CONTRIBUTING.md](CONTRIBUTING.md) describes the full development loop.
Weatherbot keeps its database and optional `weatherbot.toml` in your user
directories (`%LOCALAPPDATA%\weatherbot` on Windows), never in the
repository; "Local data" there lists the paths and the overrides.

## Documents

- [The v2 brief](docs/brief/weatherbot-v2-brief.md): what version 2 is and
  the decisions behind it.
- [The project roadmap](docs/roadmap/ROADMAP.md) and its
  [phase roadmaps](docs/roadmap/): how the work is sequenced.
- [The data-source register](docs/DATA_SOURCES.md): every official
  source version 2 reads, verified live, with its endpoints, terms, and
  etiquette.
- [The alert ladder](docs/ALERT-LADDER.md): levels, actions, ordered rules,
  calibrated thresholds, and the historical replay evidence.
- [CHANGELOG.md](CHANGELOG.md): what has changed.

## License

[MIT](LICENSE)
