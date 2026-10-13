# Third-party terms for the recorded fixtures

The files under `tests/fixtures/recorded/` are responses that public web services
sent to `scripts/record_fixtures.py`, stored byte for byte beside a `manifest.json` that
names each file's URL, time, and checksum. They are test data. Weatherbot's own licence
(`LICENSE`) covers the code in this repository, not these captures.

## NOAA

Content from the National Hurricane Center (`nhc-*` sources), the National Weather
Service API (`nws-*` sources), and NOAA nowCOAST (`overlay-*` sources) is a work of
the United States Government and is in the public domain. See the
[NWS disclaimer](https://www.weather.gov/disclaimer). The WMS capabilities documents
state `Fees` and `AccessConstraints` as `NONE`.

The six seven-day outlook maps from September and October 2025
(`nhc-outlook-graphics/2025-*`) are NHC graphics that version 1 of Weatherbot embedded in
its reports. They carry the same public-domain status.

## OpenStreetMap

The Nominatim captures (`geocode-nominatim`) are © OpenStreetMap contributors and
available under the Open Database Licence (ODbL) 1.0. See
<https://www.openstreetmap.org/copyright> and the
[Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/).

## Everything else

A source not named above follows the Terms column of `docs/DATA_SOURCES.md`, the
data-source register. The register's Fixture column says which sources are recorded.
