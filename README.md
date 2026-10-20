# Weatherbot

A personal hurricane-threat monitor. Weatherbot reads the official National
Hurricane Center (NHC) and National Weather Service (NWS) products for named
locations, decides a five-level threat from those products alone, notifies
on change, keeps history, and uses Claude to explain the situation in plain
language. It is a command-line tool plus a local-only web app; version 2
specifies both in [the project brief](docs/brief/weatherbot-v2-brief.md).

## Status

Version 2 is a from-scratch rewrite in progress. Phase 1 (foundation and
discovery) and Phase 2 (sources and persistence) are complete; Phase 3 (the
threat engine) is in progress.
No version 2 package is released. The commands below read the official
products and print them; they do not yet decide a threat level, which is
Phase 3's work. The plan lives in [the roadmap](docs/roadmap/ROADMAP.md).

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
weatherbot alerts --location "Miami-Dade County Hall"   # NWS alerts, in UTC and local time
weatherbot alerts --location "Parliament Square"        # outside NWS coverage: the watch-warning segments
weatherbot doctor                    # paths, database revision, every source and layer
weatherbot doctor --offline          # local checks only
```

`locations list`, `fetch`, `storms`, `alerts`, and `doctor` take `--json` and
print one JSON document whose schema is in [docs/schema/](docs/schema/).
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
