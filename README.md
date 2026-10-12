# Weatherbot

A personal hurricane-threat monitor. Weatherbot reads the official National
Hurricane Center (NHC) and National Weather Service (NWS) products for named
locations, decides a five-level threat from those products alone, notifies
on change, keeps history, and uses Claude to explain the situation in plain
language. It is a command-line tool plus a local-only web app; version 2
specifies both in [the project brief](docs/brief/weatherbot-v2-brief.md).

## Status

Version 2 is a from-scratch rewrite in progress. It is in Phase 1
(foundation and discovery) and nothing is released: the package builds and
`weatherbot --version` runs, and that is all. The plan lives in
[the roadmap](docs/roadmap/ROADMAP.md).

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

## Documents

- [The v2 brief](docs/brief/weatherbot-v2-brief.md): what version 2 is and
  the decisions behind it.
- [The project roadmap](docs/roadmap/ROADMAP.md) and its
  [phase roadmaps](docs/roadmap/): how the work is sequenced.
- [CHANGELOG.md](CHANGELOG.md): what has changed.

## License

[MIT](LICENSE)
