# Data-source register

**Verified:** 2026-10-12, live, between 21:36 and 22:09 UTC. Times are UTC
unless a product's own local time is quoted.

**Amended:** 2026-10-17, live, between 04:10 and 04:17 UTC, for Phase 2
Step 3: the `nhc-arrival-times` row, its section
[Arrival-time KMZ](#arrival-time-kmz), the narrowed "Not used" row on
per-storm KMZ, and the "Fields v2 uses" lists of the text products and the
GIS feeds. Every other statement keeps 2026-10-12, or the date its own
amendment names.

## Purpose

This register lists every external source Weatherbot version 2 reads, as
the services answered on the verification date. It covers every source in
[the brief's §5](brief/weatherbot-v2-brief.md#5-data-sources-verified-live-on-2026-10-11).
Each source has a stable id. Step 5's recorder stores its fixtures under
`tests/fixtures/recorded/<source-id>/`, and Phase 2 names its clients
after it. The register also fixes the shared query parameters, the
User-Agent, and each source's etiquette, and it answers the brief's open
question (§14) on arrival-time, probabilistic-wind, and surge layers. A
field appears here only if a live response contained it. A statement
changes only together with a new verification date.

## How it was verified

- 475 read-only requests, sent serially from one machine with the project
  User-Agent. Requests to `api.weather.gov` were at least 1.2 seconds
  apart, requests to Nominatim at least 1.5 seconds apart, and all others
  at least 1 second apart.
- The only coordinates sent were the two public landmarks in
  [`scripts/public_landmarks.toml`](../scripts/public_landmarks.toml):
  Miami-Dade County Hall (the Stephen P. Clark Government Center) in Miami,
  and Parliament Square in Nassau. Map-tile probes used the zoom-5
  Web Mercator tile that contains the Miami-Dade landmark.
- No endpoint needed a credential. Probe scripts and raw responses stayed
  outside the repository. The fixtures are Step 5's job.

## User-Agent

Every request sends:

```text
weatherbot/2.0.0.dev0 (+https://github.com/nathanramoscfa/weatherbot)
```

The NWS API requires a User-Agent that identifies the application, and
asks for contact details (a website or an email) so it can reach the
owner of a misbehaving client. The OpenStreetMap tile and Nominatim
policies require a User-Agent that identifies the application, and
Nominatim's adds that the stock User-Agents of HTTP libraries "will not
do". The repository URL meets all three policies. It identifies the application and gives a contact
route (issues and private vulnerability reporting) without putting a
personal email address into a public repository and a public package
(brief §5 and §12). The version part follows the package version. The
one definition is `weatherbot.sources.USER_AGENT`, built from the
package version; the fixture recorder imports it, and a contract test
keeps it equal to the string above.

## Re-verifying

- `uv run python scripts/record_fixtures.py record --all` (Step 5)
  re-records every `required` source with the parameters below. Its
  contract tests fail when the register, the recorder, and the recorded
  catalogs disagree.
- A layer, field, or product that changed or disappeared is a
  **Source drift** finding (project roadmap §5, "Defect handling &
  triage"). Re-record the fixture, update this register with the new
  date, and add a contract test in the same pull request.
- The per-basin answers below are a snapshot of one day. A basin marked
  open is answered on the first day it has an active storm.

## Recorded fixtures

`scripts/record_fixtures.py` stores what each `required` source answered in
`tests/fixtures/recorded/<source-id>/<yyyy-mm-dd>/`. The date is the recording
machine's local date, and the times inside are UTC. One `manifest.json` per
directory lists every file with its URL, status, time, SHA-256, size, and the
response headers on an allowlist (never `set-cookie`).
`tests/fixtures/recorded/NOTICE.md` states the third-party terms.

- **Bytes.** `sha256` and `bytes` describe the payload as received. A payload
  over 1 MiB is stored gzip-compressed, so the file has a `.gz` suffix. A
  manifest's `content-length` header is the length NOAA put on the wire,
  which is the compressed length when the response was compressed.
- **ArcGIS services.** Every service records its catalog (`catalog.json`) and
  its layer schemas (`layers.json`). The two NHC tropical services, the
  breakpoint service, and the peak-surge service then record one GeoJSON query
  per feature layer with the shared parameters above. A storm-slot layer is
  recorded only for an active slot, and a `Footprint_*` layer is recorded as a
  count. `StormSurgeRisk` records its catalog only.
- **Text products.** For every active storm slot, the NWS API's TCP list and
  its newest product; for each basin, the TWO list and its newest product.
- **Arrival-time KMZ** (added 2026-10-17). The archived Dorian 036 pair,
  always, and both files every active storm's roster objects link, stored
  as received. Every URL is checked against the pattern before the first
  request.
- **Documented errors.** The Nassau landmark's `/points` response (404) and
  `alerts/active?point=` response (400) are recorded with their status and
  `application/problem+json` body.
- **Harvested files.** `nhc-outlook-graphics/2025-*` holds the seven-day
  Atlantic maps that the version 1 reports embedded. The folder is the
  report's local date, and `fetched_at` is the report's local time (EDT)
  converted to UTC.

## Register

| Source id | Brief §5 source | Endpoint | Format | Fixture | Cadence | Terms | Verified |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `nhc-current-storms` | `CurrentStorms.json` | `https://www.nhc.noaa.gov/CurrentStorms.json` | JSON | `required` | Rewritten after each advisory (at 21:24 for the 21:00 advisory); advisories every 6 h with intermediates between; `max-age=300`, `ETag`, `Last-Modified`, 304 honored | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nhc-arrival-times` | `CurrentStorms.json` | `https://www.nhc.noaa.gov/storm_graphics/api/{ID}_{adv}adv_{earliest_reasonable,most_likely}_toa_34.kmz` | KMZ (KML 2.2 in a zip) | `required` | Per full advisory; `ETag`, `Last-Modified` | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-17 |
| `nhc-map-tropical-weather` | MapServer `tropical/NHC_tropical_weather` | `https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/NHC_tropical_weather/MapServer` | ArcGIS JSON catalog; GeoJSON queries | `required` | Per advisory for storm slots, per outlook for the outlook layers, per synoptic time (6 h) for probabilistic winds; queries `max-age=0,must-revalidate` | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nhc-map-tropical-summary` | MapServer `tropical/NHC_tropical_weather_summary` | `https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/NHC_tropical_weather_summary/MapServer` | ArcGIS JSON catalog; GeoJSON queries | `required` | As `nhc-map-tropical-weather` | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nhc-map-breakpoints` | MapServers `NHC_Breakpoints`, `NHC_PeakStormSurge`, `StormSurgeRisk` | `https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/NHC_Breakpoints/MapServer` | ArcGIS JSON catalog; GeoJSON queries | `required` | Static catalogue; loaded 2026-04-30 | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nhc-map-peak-surge` | MapServers `NHC_Breakpoints`, `NHC_PeakStormSurge`, `StormSurgeRisk` | `https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/NHC_PeakStormSurge/MapServer` | ArcGIS JSON catalog; GeoJSON queries | `required` | Per advisory when NHC issues a peak-surge forecast; empty otherwise | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nhc-map-surge-risk` | MapServers `NHC_Breakpoints`, `NHC_PeakStormSurge`, `StormSurgeRisk` | `https://mapservices.weather.noaa.gov/tropical/rest/services/tropical/StormSurgeRisk/MapServer` | ArcGIS JSON catalog; PNG from `export` | `required` | Static hazard maps | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nhc-gis-rss` | NHC GIS archive and `gis-at.xml` | `https://www.nhc.noaa.gov/gis-{at,ep,cp}.xml` | RSS 2.0 XML | `required` | Items per advisory; feed rewritten periodically; `max-age=300`, `ETag`, `Last-Modified` | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nhc-gis-archive` | NHC GIS archive and `gis-at.xml` | `https://www.nhc.noaa.gov/gis/archive_forecast.php?year={yyyy}` | HTML listings; ZIP (shapefiles), KMZ, KML | `replay-corpus` | Static per season | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nhc-text-products` | NHC text products (TCP, TWO) | `https://api.weather.gov/products/types/{TCP,TWO}/locations/{location}` | JSON-LD (`application/ld+json`) | `required` | TCP per advisory; TWO four times a day; `max-age=120` | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nhc-outlook-graphics` | NHC outlook graphics | `https://www.nhc.noaa.gov/xgtwo/two_{atl,pac,cpac}_{2d0,7d0}.png` | PNG | `required` | Per outlook, and redrawn with advisories; `max-age=300`, `ETag`, `Last-Modified`, 304 honored | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nws-points` | NWS API | `https://api.weather.gov/points/{lat},{lon}` | GeoJSON (`application/geo+json`); `application/problem+json` on error | `required` | Static per point; `max-age=86400` | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nws-alerts-point` | NWS API | `https://api.weather.gov/alerts/active?point={lat},{lon}` | GeoJSON (`application/geo+json`); `application/problem+json` on error | `required` | Any time; `max-age=5` | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nws-alerts-zone` | NWS API | `https://api.weather.gov/alerts/active/zone/{zoneId}` | GeoJSON (`application/geo+json`) | `required` | Any time; `max-age=5` | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `nws-zones` | NWS API | `https://api.weather.gov/zones/{type}/{zoneId}` | GeoJSON (`application/geo+json`) | `required` | Static (zones effective 2026-04-16); `max-age` of weeks, `Last-Modified` | Public domain ([NWS disclaimer](https://www.weather.gov/disclaimer)) | 2026-10-12 |
| `basemap-osm-tiles` | OpenStreetMap tiles | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | PNG tiles | `none — display-only: the browser loads tiles directly and the code never parses one; the OSMF tile policy forbids bulk download` | Cached per the tile's own headers (`max-age` of days) | [OSMF Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/); visible attribution required | 2026-10-12 |
| `overlay-radar` | NOAA or Iowa Environmental Mesonet radar and GOES WMS layers | `https://nowcoast.noaa.gov/geoserver/weather_radar/ows` | WMS 1.3.0 capabilities XML; PNG tiles | `required` | Mosaic about every 4 min; tiles `max-age=240` | Public domain (NOAA); WMS `Fees` and `AccessConstraints` read `NONE` | 2026-10-12 |
| `overlay-satellite` | NOAA or Iowa Environmental Mesonet radar and GOES WMS layers | `https://nowcoast.noaa.gov/geoserver/satellite/ows` | WMS 1.3.0 capabilities XML; PNG tiles | `required` | GOES composites every 5 min; tiles `max-age=240` | Public domain (NOAA); WMS `Fees` and `AccessConstraints` read `NONE` | 2026-10-12 |
| `geocode-nominatim` | Nominatim reverse geocoding | `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}` | JSON | `required` | Once per location at setup, cached for good; at most 1 request per second | [OSMF Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/); © OpenStreetMap contributors, ODbL 1.0 | 2026-10-12 |

The `required` overlay rows record each WMS capabilities document, which
names the layers the map loads. The tiles themselves are display-only.

## NHC current storms

`nhc-current-storms`: `GET https://www.nhc.noaa.gov/CurrentStorms.json`.
The response is `application/json` with `Cache-Control: max-age=300`, an
`ETag`, and a `Last-Modified`. A conditional request carrying both
validators returned 304. The body is `{"activeStorms": [...]}`. On the
verification date it held one storm, `EP202026` (Hurricane Simon), and the
file was last modified at 21:24 for that storm's 21:00 advisory.

- **Fields present per storm:** `id`, `binNumber`, `name`,
  `classification`, `intensity`, `pressure`, `latitude`, `longitude`,
  `latitudeNumeric`, `longitudeNumeric`, `movementDir`, `movementSpeed`,
  `lastUpdate`. Then come the product objects:
  - `publicAdvisory`, `forecastAdvisory`, `windSpeedProbabilities`,
    `forecastDiscussion`, `forecastGraphics`, each with `advNum`,
    `issuance`, `fileUpdateTime`, `url`;
  - `forecastTrack`, `windWatchesWarnings`, `trackCone`,
    `initialWindExtent`, `forecastWindRadiiGIS`, each with `advNum`,
    `issuance`, `fileUpdateTime`, `zipFile`, `kmzFile`;
  - `bestTrackGIS`, without `advNum`;
  - `earliestArrivalTimeTSWindsGIS` and `mostLikelyTimeTSWindsGIS`, each
    with `advNum`, `issuance`, `fileUpdateTime`, `kmzFile`;
  - `windSpeedProbabilitiesGIS`, with `issuance`, `fileUpdateTime`,
    `zipFile5km`, `zipFile0p5deg`, `kmzFile34kt`, `kmzFile50kt`,
    `kmzFile64kt`;
  - `stormSurgeWatchWarningGIS`, `potentialStormSurgeFloodingGIS`, and
    `peakSurgeKML`, all `null` for Simon.
- **Fields v2 uses:** `id`, `binNumber`, `name`, `classification`,
  `intensity`, `pressure`, `latitudeNumeric`, `longitudeNumeric`,
  `movementDir`, `movementSpeed`, `lastUpdate`, `publicAdvisory.advNum`,
  `publicAdvisory.issuance`, `stormSurgeWatchWarningGIS`,
  `potentialStormSurgeFloodingGIS`, and `peakSurgeKML` (whether each is
  null), and, amended 2026-10-16 for the map and arrival-time clients,
  `trackCone.advNum`, `trackCone.issuance`,
  `windSpeedProbabilitiesGIS.issuance`,
  `earliestArrivalTimeTSWindsGIS.advNum`,
  `earliestArrivalTimeTSWindsGIS.issuance`,
  `earliestArrivalTimeTSWindsGIS.kmzFile`,
  `mostLikelyTimeTSWindsGIS.advNum`, `mostLikelyTimeTSWindsGIS.issuance`,
  and `mostLikelyTimeTSWindsGIS.kmzFile`. A product object that is
  absent or null leaves its product unlisted; one that is present must
  carry these members.
- `weatherbot.sources.nhc_current_storms` reads exactly the fields above
  (`FIELDS_READ`), and `tests/contract/test_field_coverage.py` keeps the
  two lists equal. The map layers' "Fields v2 uses" columns below are
  held to their parsers the same way.
- `intensity` and `pressure` are strings (`"85"`, `"969"`). `binNumber`
  (`EP5`) is the map-service slot and the NWS API's TCP location. It joins
  the roster to the `{slot}` layers and to the text products.
- `publicAdvisory.issuance` is the nominal advisory time (21:00). The
  TCP's own WMO time was 20:51.
- The product objects link to NHC HTML pages and archive files. v2
  follows none of the HTML links.
- **Units (recorded 2026-10-16).** NHC's
  [Tropical Cyclone Status JSON File Reference](https://www.nhc.noaa.gov/productexamples/NHC_Tropical_Cyclone_Status_JSON_File_Reference.pdf)
  (last updated 2019-04-08, linked from NHC's product examples page)
  states `intensity` in knots, `pressure` in millibars, `movementDir` in
  "decimal degrees from true north", and `movementSpeed` in **miles per
  hour**, and lists the classification codes `TD`, `STD`, `TS`, `HU`,
  `STS`, `PTC`, `TY`, and `PC`. The models name the fields
  `intensity_kt`, `pressure_mb`, `movement_dir_deg`, and
  `movement_speed_mph`. The recorded TCP agrees: Simon's 85 kt and 3
  appear there as 100 mph and "AT 3 MPH". The forecast points' speed is
  in knots (below), so the two speeds differ in unit.

## Arrival-time KMZ

`nhc-arrival-times`, added 2026-10-17. The roster's
`earliestArrivalTimeTSWindsGIS.kmzFile` and
`mostLikelyTimeTSWindsGIS.kmzFile` link one KMZ each per full advisory:
`https://www.nhc.noaa.gov/storm_graphics/api/{ID}_{adv}adv_{earliest_reasonable,most_likely}_toa_34.kmz`,
with `{ID}` in upper case and `{adv}` three digits. Intermediate
advisories have none. The GIS archive serves the same files for past
storms (see [GIS archive](#gis-archive)).

- **Verified 2026-10-17.** Both files of every active storm, `EP212026`
  (Trudy, advisory 015, `pubAdvTime` `900 PM CST Fri Oct 16 2026`) and
  `EP202026` (Simon, post-tropical, advisory 038, `200 PM MST Fri Oct 16
  2026`), and the archived pair of `AL052019` (Dorian) advisory 036
  returned 200, `application/vnd.google-earth.kmz`, 9,109 to 37,795 bytes,
  with an `ETag` and a `Last-Modified`. The roster gave each product's
  `issuance` and `advNum`, which agreed with `pubAdvTime` and
  `advisoryNum`.
- **Structure.** Every file held 12 members: one KML,
  `{ID}_{n}_{kind}_toa_34.kml` with the advisory unpadded
  (`AL052019_36_earliest_reasonable_toa_34.kml`), and 11 label images
  under `labels/`. The KML is in namespace
  `http://earth.google.com/kml/2.2`. Its Document's `ExtendedData` holds
  `Data` named `timezone` (`EDT`, `CST`, `MST`), `storm`, `atcfid`,
  `advisoryNum` (unpadded, `36`), and `pubAdvTime`
  (`500 AM EDT Mon Sep 02 2019`). Each line is a Placemark with a
  LineString and a `description` whose single HTML table cell is its
  label (`Mon 8 am`), or `Wind Speed Probability 5% contour` for the outer
  contour. The other Placemarks are the label icons, Points with no
  description. Dorian 036 has 11 labelled lines in the earliest-reasonable
  file and 10 in the most-likely file, each plus the contour; Trudy 015
  has 5 and 7; Simon 038 has the contour only.
- **Fields v2 uses:** `timezone`, `advisoryNum`, `atcfid`, and
  `pubAdvTime`.
- **Why v2 reads it.** Issue
  [#11](https://github.com/nathanramoscfa/weatherbot/issues/11) chose this
  file (option b). The map layers' labels carry no date and no zone, and
  the slot's `advdate` belongs to the latest advisory, which can be an
  intermediate one: on 2026-10-12 the `EP5` cone was advisory 22A while
  the arrival lines belonged to advisory 22, three hours earlier.
- **Resolution rule** (`weatherbot.models.resolve_arrival_label`). A label
  resolves to the first instant at or after `pubAdvTime` whose local
  weekday and clock time, in the product's `timezone`, match it, provided
  it falls less than 120 hours after `pubAdvTime`. A label that does not
  parse, an unknown zone, or an instant beyond the horizon leaves the line
  without an instant and with the reason. The outer contour has no time.
- **Checks.** `pubAdvTime` must agree with the roster's `issuance` within
  an hour, `advisoryNum` must equal the roster's `advNum` and the URL's
  advisory, `atcfid` must equal the storm's, and `timezone` must be the
  zone `pubAdvTime` names. Otherwise every line stays unresolved with the
  reason, and the client logs a Source-drift warning.
- **Fallback.** The map layers' arrival lines remain a label-only product
  for display when the KMZ is unavailable. In a snapshot, a KMZ product
  supersedes the map-layer product of the same storm, advisory, and kind.
- **Limits.** The client and the recorder follow a link only when it
  matches the pattern above on `www.nhc.noaa.gov` over HTTPS. They open
  the archive in memory with at most 64 members, none absolute or
  containing `..`, at most 8 MiB uncompressed, and no member compressed
  more than 100 to 1. They parse the one KML member with `defusedxml` and
  ignore the label images.
- **Recorded fixtures.** The recorder always records the archived Dorian
  036 pair, whose SHA-256 values the replay corpus manifest pins, and
  every active storm's roster-linked pair. Each roster-linked capture's
  `notes` give the roster's `advNum` and `issuance`.

## ArcGIS map services

All five services sit in the `tropical` folder of
`https://mapservices.weather.noaa.gov/tropical/rest/services` (ArcGIS REST API
version 11.3). Each reports `capabilities` `Map,Query,Data`,
`supportedQueryFormats` `JSON, geoJSON, PBF`, and `maxRecordCount` 2000.

### Discovering layers

A client fetches the service catalog, `<service>/MapServer?f=json`, which
gives every layer's `id`, `name`, `type`, `geometryType`,
`parentLayerId`, and `subLayerIds`. The fields come from
`<service>/MapServer/layers?f=json`. The client resolves each layer by its
exact name, or by its group path where names repeat (`StormSurgeRisk`),
and queries the id it found that day. It never stores an id. Ids shift: on
2026-10-12, `NHC_tropical_weather` numbered `AT1` as id 4 and each further
slot 26 higher (`EP5` 238, `CP5` 368). `Probabilistic Winds` was 394, and
`Seven-Day: Development Motion` was 398, after every slot, although it is
listed with the outlook. That service's `/layers` document is 2.3 MB.

### Shared query parameters

The recorder and Phase 2's clients query a feature layer with
`GET <service>/MapServer/<id>/query` and these parameters
(`weatherbot.sources.arcgis.QUERY_PARAMETERS`):

| Parameter | Value | Why |
| --- | --- | --- |
| `where` | `1=1` | Every feature. A slot layer holds one storm. |
| `outFields` | `*` | Every field. Clients read fields by name. |
| `outSR` | `4326` | WGS 84. The two NHC tropical services report `GCS_Sphere` (radius 6,371,200 m), `NHC_Breakpoints` and `NHC_PeakStormSurge` in 4326, and `StormSurgeRisk` in Web Mercator (3857). |
| `f` | `geojson` | A GeoJSON FeatureCollection. Each feature's `id` is its `objectid`. |
| `geometryPrecision` | `5` | The server-side precision limit: five decimals, about 1 m. Without it, coordinates carry up to 15 decimals. On 2026-10-12, `Probabilistic Winds 34 kts` fell from 1,080,909 to 568,089 bytes and `Forecast Cone` from 37,047 to 20,013. |

- **Paging.** A response holds at most 2000 features. The largest layer
  on the verification date was `Watch_Warning_Breakpoints`, with 549. A
  truncated GeoJSON response carries a top-level `exceededTransferLimit:
  true`, which was observed with `resultRecordCount=100`. A client then
  pages with `resultOffset`, `resultRecordCount`, and
  `orderByFields=objectid`, which every feature layer supports.
- **Empty layers.** An empty layer returns
  `{"type": "FeatureCollection", "features": []}`, 42 bytes.
- **Counts.** `returnCountOnly=true&f=json` returns `{"count": n}`. This
  register's per-layer counts came from it.
- **Dates.** `idp_filedate` and `idp_ingestdate` are epoch milliseconds.
  Simon's 21:00 cone, for example, carried an `idp_filedate` of 21:08:17.
- **Caching.** Queries answer `Cache-Control: max-age=0,must-revalidate`
  with an `ETag`.
- **Rasters.** Raster layers (`Image_Inun_{slot}` and the
  `StormSurgeRisk` images) are drawn, not queried. A request to
  `<service>/MapServer/export` with `layers=show:<id>`, a `bbox` in
  `bboxSR=3857`, `imageSR=3857`, `size=256,256`, `format=png32`,
  `transparent=true`, and `f=image` returned a 256×256 PNG from
  `StormSurgeRisk`.

### `tropical/NHC_tropical_weather`

`nhc-map-tropical-weather`. The catalog has 400 layers: the outlook group,
fifteen storm slots, and a probabilistic-wind group. `{slot}` in a layer
name stands for each of `AT1`–`AT5`, `EP1`–`EP5`, and `CP1`–`CP5`. Every
slot group has the same 26 names with its slot substituted.

A slot is active when `nhc-current-storms` lists its `binNumber`. On the
verification date only `EP5` was active, and every layer of the other
fourteen slots returned no features. The recorder records every layer
below for each active slot, plus the outlook and probabilistic-wind
layers.

Each slot has the same field names, but their order differs between slots
(for example `EP4 Forecast Points` and `CP3 Forecast Points`). One field
set differs: `AT1 Advisory Wind Field` lacks `idp_source`. Clients read
fields by name, never by position.

"Fields present" is the live schema. "Fields v2 uses" lists fields seen in
live features, except where a note says otherwise. Group layer names keep
NOAA's spelling (`Past Track Infomation`).

| Layer name | Geometry | Fields present | Fields v2 uses | Notes |
| --- | --- | --- | --- | --- |
| `Graphical Tropical Weather Outlook` | group | — | — |  |
| `Two-Day: Current Location` | point | `objectid`, `basin`, `prob2day`, `risk2day`, `prob7day`, `risk7day`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape` | `basin`, `prob2day`, `risk2day`, `prob7day`, `risk7day`, `idp_source`, `idp_filedate` | Marker for a disturbance in the outlook. `idp_filedate` (epoch ms) is the `OutlookArea`'s issuance (added 2026-10-16). |
| `Seven-Day Outlook` | group | — | — |  |
| `Seven-Day: Current Location` | point | `objectid`, `basin`, `prob2day`, `risk2day`, `prob7day`, `risk7day`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape` | `basin`, `prob2day`, `risk2day`, `prob7day`, `risk7day`, `idp_source`, `idp_filedate` | As above, seven-day. |
| `Seven-Day: Development Motion` | polyline | `objectid`, `basin`, `prob2day`, `risk2day`, `prob7day`, `risk7day`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_length(shape)` | `basin`, `prob2day`, `risk2day`, `prob7day`, `risk7day`, `idp_source`, `idp_filedate` | Arrow on the map, an `OutlookArea`. No features on 2026-10-12; the fields v2 uses are the other outlook layers', all in the schema (amended 2026-10-16). |
| `Seven-Day: Potential Development Region` | polygon | `objectid`, `basin`, `prob2day`, `risk2day`, `prob7day`, `risk7day`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_area(shape)`, `st_perimeter(shape)` | `basin`, `prob2day`, `risk2day`, `prob7day`, `risk7day`, `idp_source`, `idp_filedate` | `OutlookArea`; a level-2 trigger. `prob*` are strings such as `20%`; `idp_source` carries the outlook stamp (`gtwo_areas_202610121711`); `idp_filedate` dates it (added 2026-10-16). |
| `{slot}` | group | — | — |  |
| `{slot} Forecast Information` | group | — | — |  |
| `{slot} Forecast Points` | point | `objectid`, `stormname`, `stormtype`, `dvlbl`, `basin`, `advdate`, `advisnum`, `fcstprd`, `gust`, `maxwind`, `mslp`, `ssnum`, `datelbl`, `tcdvlp`, `tcdir`, `tcspd`, `fldatelbl`, `lat`, `lon`, `stormnum`, `stormsrc`, `tau`, `timezone`, `validtime`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `binnumber` | `stormname`, `stormtype`, `tcdvlp`, `basin`, `binnumber`, `stormnum`, `advisnum`, `advdate`, `tau`, `validtime`, `fldatelbl`, `maxwind`, `gust`, `mslp`, `tcdir`, `tcspd`, `ssnum`, `dvlbl` | `TrackPoint`. `validtime` reads `DD/HHMM` in UTC (`12/1800`); `fldatelbl` and `advdate` are local text (`200 PM MST Mon Oct 12 2026`). `9999` stands in for a missing `mslp`, `tcdir`, or `tcspd`. |
| `{slot} Forecast Track` | polyline | `objectid`, `stormname`, `stormtype`, `basin`, `advdate`, `advisnum`, `fcstprd`, `stormnum`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_length(shape)`, `binnumber` | `advisnum`, `advdate`, `binnumber` | `ForecastTrack`, a line on the map; `advdate` dates its advisory (added 2026-10-16). |
| `{slot} Forecast Cone` | polygon | `objectid`, `stormname`, `stormtype`, `basin`, `advdate`, `advisnum`, `fcstprd`, `stormnum`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_area(shape)`, `st_perimeter(shape)`, `binnumber` | `stormname`, `stormtype`, `basin`, `stormnum`, `advisnum`, `advdate`, `fcstprd`, `binnumber`, `idp_source` | `ConeGeometry`; one polygon per advisory. |
| `{slot} Watch-Warning` | polyline | `objectid`, `stormname`, `stormtype`, `basin`, `advdate`, `advisnum`, `fcstprd`, `stormnum`, `tcww`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_length(shape)`, `binnumber` | `tcww`, `stormname`, `advisnum`, `advdate`, `binnumber` | `WatchWarningSegment`. `tcww` codes seen: `HWA`, `HWR`. |
| `{slot} Past Track Infomation` | group | — | — |  |
| `{slot} Past Points` | point | `objectid`, `stormname`, `stormtype`, `stormnum`, `intensity`, `basin`, `mslp`, `dtg`, `year`, `month`, `day`, `hhmm`, `lat`, `lon`, `ss`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `binnumber` | `dtg`, `intensity`, `mslp`, `stormtype`, `ss` | History on the map. |
| `{slot} Past Track` | polyline | `objectid`, `stormtype`, `stormnum`, `ss`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_length(shape)`, `binnumber` | `stormtype`, `ss` | History on the map. |
| `{slot} Past Cumulative Wind Swath` | polygon | `objectid`, `radii`, `stormid`, `basin`, `stormnum`, `advnum`, `startdtg`, `enddtg`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_area(shape)`, `st_perimeter(shape)`, `binnumber` | `radii` | Map layer. |
| `{slot} Past Wind Radii` | polygon | `objectid`, `radii`, `stormid`, `basin`, `stormnum`, `advnum`, `synoptime`, `timezone`, `ne`, `se`, `sw`, `nw`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_area(shape)`, `st_perimeter(shape)`, `binnumber` | — | Not used in 2.0. |
| `{slot} Wind Information` | group | — | — |  |
| `{slot} Forecast Wind Radii` | polygon | `objectid`, `radii`, `stormid`, `basin`, `stormnum`, `advnum`, `validtime`, `synoptime`, `timezone`, `tau`, `ne`, `se`, `sw`, `nw`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_area(shape)`, `st_perimeter(shape)`, `binnumber` | `radii`, `tau`, `validtime`, `synoptime`, `ne`, `se`, `sw`, `nw`, `advnum`, `stormid`, `binnumber` | `WindRadii`. `validtime` and `synoptime` are `YYYYMMDDHH` strings and `timezone` reads `UTC`; `ne`, `se`, `sw`, `nw` are quadrant extents (the layer states no unit). |
| `{slot} Advisory Wind Field` | polygon | `objectid`, `radii`, `stormid`, `basin`, `stormnum`, `advnum`, `validtime`, `synoptime`, `timezone`, `tau`, `ne`, `se`, `sw`, `nw`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_area(shape)`, `st_perimeter(shape)`, `binnumber` | `radii`, `validtime`, `synoptime`, `ne`, `se`, `sw`, `nw`, `advnum`, `stormid`, `binnumber` | `WindRadii` at `tau` 0. `AT1` alone lacks `idp_source` here. |
| `{slot} Arrival Time of TS Winds` | group | — | — |  |
| `{slot} Earliest Reasonable Arrival Time` | polyline | `arrival_time`, `objectid`, `name`, `folderpath`, `symbolid`, `altmode`, `base`, `clamped`, `extruded`, `idp_ingestdate`, `idp_filedate`, `idp_source`, `idp_subset`, `binnumber`, `snippet`, `popupinfo`, `shape`, `st_length(shape)` | `arrival_time`, `folderpath`, `idp_subset`, `binnumber` | `ArrivalTime`. `arrival_time` is a label such as `Tue 8 am` with no date or zone; one line has a blank label (the 5% wind-probability contour). `folderpath` names the storm and advisory. |
| `{slot} Most Likely Arrival Time` | polyline | `arrival_time`, `objectid`, `name`, `folderpath`, `symbolid`, `altmode`, `base`, `clamped`, `extruded`, `idp_ingestdate`, `idp_filedate`, `idp_source`, `idp_subset`, `binnumber`, `snippet`, `popupinfo`, `shape`, `st_length(shape)` | `arrival_time`, `folderpath`, `idp_subset`, `binnumber` | As above. |
| `{slot} Inundation and Tidal Mask` | group | — | — |  |
| `{slot} Inundation` | mosaic | — | — |  |
| `Boundary_Inun_{slot}` | polygon | `objectid`, `shape`, `st_area(shape)`, `st_perimeter(shape)` | — | Mosaic boundary. |
| `Footprint_Inun_{slot}` | polygon | `objectid`, `name`, `minps`, `maxps`, `lowps`, `highps`, `category`, `tag`, `groupname`, `productname`, `centerx`, `centery`, `zorder`, `typeid`, `itemts`, `urihash`, `uri`, `idp_ingestdate`, `idp_filedate`, `idp_subset`, `binnumber`, `shape`, `raster`, `st_area(shape)`, `st_perimeter(shape)` | — | Counted only: a non-zero count means the slot has an inundation raster. |
| `Image_Inun_{slot}` | raster | — | — | Rendered with `export`; not queried. |
| `{slot} Tidal Mask` | mosaic | — | — |  |
| `Boundary_TMask_{slot}` | polygon | `objectid`, `shape`, `st_area(shape)`, `st_perimeter(shape)` | — | Mosaic boundary. |
| `Footprint_TMask_{slot}` | polygon | `objectid`, `name`, `minps`, `maxps`, `lowps`, `highps`, `category`, `tag`, `groupname`, `productname`, `centerx`, `centery`, `zorder`, `typeid`, `itemts`, `urihash`, `uri`, `idp_ingestdate`, `idp_filedate`, `idp_subset`, `binnumber`, `shape`, `raster`, `st_area(shape)`, `st_perimeter(shape)` | — | Counted only. |
| `Image_TMask_{slot}` | raster | — | — | Rendered with `export`; not queried. |
| `Probabilistic Winds` | group | — | — |  |
| `Probabilistic Winds 34 kts` | polygon | `objectid`, `percentage`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_area(shape)`, `st_perimeter(shape)` | `percentage`, `idp_source` | `WindProbability`. One product per synoptic time: no storm id. `percentage` bands are strings (`5-10%` …); `idp_source` names the synoptic time (`2026101218_wsp34knt120hr_5km`). |
| `Probabilistic Winds 50 kts` | polygon | `objectid`, `percentage`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_area(shape)`, `st_perimeter(shape)` | `percentage`, `idp_source` | As above. |
| `Probabilistic Winds 64 kts` | polygon | `objectid`, `percentage`, `idp_source`, `idp_filedate`, `idp_ingestdate`, `shape`, `st_area(shape)`, `st_perimeter(shape)` | `percentage`, `idp_source` | As above. |

**Units (recorded 2026-10-16).** The map layers state no unit. The field
metadata (`*.shp.xml`) inside the archived forecast packages of the same
products does, and the models take their units from it (read from the
replay cache's `al052019_5day_036.zip` and `al052019_fcst_036.zip`):

- `{slot} Forecast Points` (`_5day_pts`): `MAXWIND` "the highest 1-minute
  average wind … (knots)", `GUST` "(knots)", `MSLP` "in Millibars",
  `TCDIR` "(degrees)", and `TCSPD` "(knots)", so `max_wind_kt`, `gust_kt`,
  `mslp_mb`, `direction_deg`, and `speed_kt`. `VALIDTIME` is `dd/hhmm`.
- `{slot} Forecast Wind Radii` and `{slot} Advisory Wind Field`
  (`_forecastradii`, `_initialradii`): `RADII` "the wind speed in knots",
  and `NE`, `SE`, `SW`, `NW` "the largest distance of wind speed in
  Nautical Miles" per quadrant, so `threshold_kt` and `ne_extent_nmi` …
  `nw_extent_nmi`. `SYNOPTIME` is the forecast cycle's 0000, 0600, 1200,
  or 1800 UTC.

### `tropical/NHC_tropical_weather_summary`

`nhc-map-tropical-summary`. The same products as the slot service, merged
across storms: each layer holds every active storm's features, told apart
by `binnumber`. Forecast points and the arrival-time layers also carry
the storm id in `idp_subset`.

With one storm active on the verification date, every one of the 23
feature layers returned the same count as its counterpart in the slot
service (the `EP5` layer for a storm product), and the
GeoJSON of `Forecast Cone` and `Probabilistic Winds 34 kts` was
byte-identical to the slot service's. The recorder records the catalog
and every feature layer.

| Layer name | Geometry | Fields present | Fields v2 uses | Notes |
| --- | --- | --- | --- | --- |
| `Graphical Tropical Weather Outlook` | group | — | — |  |
| `Two-Day: Current Location` | point | as in `NHC_tropical_weather` | as in `NHC_tropical_weather` |  |
| `Seven-Day Outlook` | group | — | — |  |
| `Seven-Day: Current Location` | point | as in `NHC_tropical_weather` | as in `NHC_tropical_weather` |  |
| `Seven-Day: Development Motion` | polyline | as in `NHC_tropical_weather` | as in `NHC_tropical_weather` |  |
| `Seven-Day: Potential Development Region` | polygon | as in `NHC_tropical_weather` | as in `NHC_tropical_weather` |  |
| `Forecast Information` | group | — | — |  |
| `Forecast Points` | point | as `{slot} Forecast Points`, plus `idp_subset` | as `{slot} Forecast Points` | `idp_subset` holds the storm id (`ep202026`). |
| `Forecast Track` | polyline | as `{slot} Forecast Track` | as `{slot} Forecast Track` |  |
| `Forecast Cone` | polygon | as `{slot} Forecast Cone` | as `{slot} Forecast Cone` |  |
| `Watch-Warning` | polyline | as `{slot} Watch-Warning` | as `{slot} Watch-Warning` |  |
| `Past Track Infomation` | group | — | — |  |
| `Past Points` | point | as `{slot} Past Points` | as `{slot} Past Points` |  |
| `Past Track` | polyline | as `{slot} Past Track` | as `{slot} Past Track` |  |
| `Past Cumulative Wind Swath` | polygon | as `{slot} Past Cumulative Wind Swath` | as `{slot} Past Cumulative Wind Swath` |  |
| `Past Wind Radii` | polygon | as `{slot} Past Wind Radii` | — |  |
| `Wind Information` | group | — | — |  |
| `Forecast Wind Radii` | polygon | as `{slot} Forecast Wind Radii` | as `{slot} Forecast Wind Radii` |  |
| `Advisory Wind Field` | polygon | as `{slot} Advisory Wind Field` | as `{slot} Advisory Wind Field` |  |
| `Arrival Time of TS Winds` | group | — | — |  |
| `Earliest Reasonable Arrival Time` | polyline | as `{slot} Earliest Reasonable Arrival Time` | as `{slot} Earliest Reasonable Arrival Time` |  |
| `Most Likely Arrival Time` | polyline | as `{slot} Most Likely Arrival Time` | as `{slot} Most Likely Arrival Time` |  |
| `Inundation and Tidal Mask` | group | — | — |  |
| `Inundation` | mosaic | — | — |  |
| `Boundary_Inun` | polygon | as `Boundary_Inun_{slot}` | — |  |
| `Footprint_Inun` | polygon | as `Footprint_Inun_{slot}` | — |  |
| `Image_Inun` | raster | — | — |  |
| `Tidal Mask` | mosaic | — | — |  |
| `Boundary_TMask` | polygon | as `Boundary_TMask_{slot}` | — |  |
| `Footprint_TMask` | polygon | as `Footprint_TMask_{slot}` | — |  |
| `Image_TMask` | raster | — | — |  |
| `Probabilistic Winds` | group | — | — |  |
| `Probabilistic Winds 34 kts` | polygon | as in `NHC_tropical_weather` | as in `NHC_tropical_weather` |  |
| `Probabilistic Winds 50 kts` | polygon | as in `NHC_tropical_weather` | as in `NHC_tropical_weather` |  |
| `Probabilistic Winds 64 kts` | polygon | as in `NHC_tropical_weather` | as in `NHC_tropical_weather` |  |

### `tropical/NHC_Breakpoints`

`nhc-map-breakpoints`. The coastal breakpoint catalogue, used to name the
segment a watch or warning covers in evidence text, and to give a non-US
location its nearest breakpoint span (brief §5 and D3). Both layers were
loaded on 2026-04-30 (`idp_filedate`). The recorder records the catalog
and both layers.

| Layer name | Geometry | Fields present | Fields v2 uses | Notes |
| --- | --- | --- | --- | --- |
| `Watch_Warning_Breakpoints` | point | `objectid`, `name`, `lat`, `lon`, `state`, `country`, `idp_filedate`, `idp_ingestdate` | `name`, `lat`, `lon`, `state`, `country` | Features carry `geometry: null`; the position is in `lat` and `lon`. Six Bahamas regions, such as `Bahamas (NW)`. |
| `StormSurge_Communication_Points` | point | `objectid`, `name`, `latitude`, `longitude`, `shape`, `idp_filedate`, `idp_ingestdate` | — | Not used in 2.0. |

### `tropical/NHC_PeakStormSurge`

`nhc-map-peak-surge`. The peak storm-surge forecast. All three layers
were empty on the verification date, matching the roster's `null`
`peakSurgeKML` for Simon. The archived Milton forecast
(`AL142024_PeakStormSurge_008adv.kml`, read on 2026-10-12) holds folders
`Polygons`, `Lines`, `Breakpoints`, `Line Labels`, and `Polygon Labels`.
Placemark names read `<segment>...<range>` (`Tampa Bay...8-12 ft`), and
descriptions are JSON with `peak_surge_range` and `color`. How the
service's `name` and `popupinfo` fields carry these stays open until a
live capture has features. The recorder records the catalog and all three
layers, empty or not.

| Layer name | Geometry | Fields present | Fields v2 uses | Notes |
| --- | --- | --- | --- | --- |
| `Points` | point | `idp_source`, `idp_subset`, `idp_filedate`, `idp_ingestdate`, `objectid`, `name`, `folderpath`, `symbolid`, `altmode`, `base`, `snippet`, `popupinfo`, `haslabel`, `labelid`, `shape` | — | No features on 2026-10-12; fields are set at the first capture with features. |
| `Lines` | polyline | `objectid`, `name`, `folderpath`, `symbolid`, `altmode`, `base`, `clamped`, `extruded`, `snippet`, `popupinfo`, `shape`, `idp_source`, `idp_subset`, `idp_filedate`, `idp_ingestdate`, `st_length(shape)`, `shape_leng` | — | No features on 2026-10-12; fields are set at the first capture with features. |
| `Polygons` | polygon | `objectid`, `name`, `folderpath`, `symbolid`, `altmode`, `base`, `clamped`, `extruded`, `snippet`, `popupinfo`, `shape`, `idp_source`, `idp_subset`, `idp_filedate`, `idp_ingestdate`, `st_area(shape)`, `st_perimeter(shape)`, `shape_leng` | — | No features on 2026-10-12; fields are set at the first capture with features. |

### `tropical/StormSurgeRisk`

`nhc-map-surge-risk`. National storm-surge hazard rasters by category,
static. Names repeat in every region (`Category 1`, `Boundary`), so each
layer is named here by its group path, with segments separated by ` / `.
`{n}` stands for each category in its region's row. NOAA spells the region
`Hispanola`. No region covers the Bahamas.

v2 draws `Atlantic / US East and Gulf Coast / Category {n} / Image` for US
Atlantic and Gulf locations through `export`. It queries no layer here,
and the recorder records only this service's catalog.

| Layer name | Geometry | Fields present | Fields v2 uses | Notes |
| --- | --- | --- | --- | --- |
| `Atlantic` | group | — | — | |
| `Atlantic / US East and Gulf Coast` | group | — | — | Categories 1–5. |
| `Atlantic / US East and Gulf Coast / Category {n}` | mosaic | — | — | |
| `Atlantic / US East and Gulf Coast / Category {n} / Boundary` | polygon | `OBJECTID`, `Shape`, `Shape_Length`, `Shape_Area` | — | Mosaic boundary. |
| `Atlantic / US East and Gulf Coast / Category {n} / Footprint` | polygon | `OBJECTID`, `Shape`, `Raster`, `Name`, `MinPS`, `MaxPS`, `LowPS`, `HighPS`, `Category`, `Tag`, `GroupName`, `ProductName`, `CenterX`, `CenterY`, `ZOrder`, `TypeID`, `ItemTS`, `UriHash`, `Uri`, `Shape_Length`, `Shape_Area` | — | Mosaic footprints. |
| `Atlantic / US East and Gulf Coast / Category {n} / Image` | raster | — | — | Rendered with `export`. |
| `Atlantic / Puerto Rico and USVI` | group | — | — | Categories 1–5. |
| `Atlantic / Puerto Rico and USVI / Category {n}` | mosaic | — | — | |
| `Atlantic / Puerto Rico and USVI / Category {n} / Boundary` | polygon | `OBJECTID`, `Shape`, `Shape_Length`, `Shape_Area` | — | Mosaic boundary. |
| `Atlantic / Puerto Rico and USVI / Category {n} / Footprint` | polygon | `OBJECTID`, `Shape`, `Raster`, `Name`, `MinPS`, `MaxPS`, `LowPS`, `HighPS`, `Category`, `Tag`, `GroupName`, `ProductName`, `CenterX`, `CenterY`, `ZOrder`, `TypeID`, `ItemTS`, `UriHash`, `Uri`, `Shape_Length`, `Shape_Area` | — | Mosaic footprints. |
| `Atlantic / Puerto Rico and USVI / Category {n} / Image` | raster | — | — |  |
| `Atlantic / Hispanola` | group | — | — | Categories 1–5. |
| `Atlantic / Hispanola / Category {n}` | mosaic | — | — | |
| `Atlantic / Hispanola / Category {n} / Boundary` | polygon | `OBJECTID`, `Shape`, `Shape_Length`, `Shape_Area` | — | Mosaic boundary. |
| `Atlantic / Hispanola / Category {n} / Footprint` | polygon | `OBJECTID`, `Shape`, `Raster`, `Name`, `MinPS`, `MaxPS`, `LowPS`, `HighPS`, `Category`, `Tag`, `GroupName`, `ProductName`, `CenterX`, `CenterY`, `ZOrder`, `TypeID`, `ItemTS`, `UriHash`, `Uri`, `Shape_Length`, `Shape_Area` | — | Mosaic footprints. |
| `Atlantic / Hispanola / Category {n} / Image` | raster | — | — |  |
| `Atlantic / Yucatan` | group | — | — | Categories 1–5. |
| `Atlantic / Yucatan / Category {n}` | mosaic | — | — | |
| `Atlantic / Yucatan / Category {n} / Boundary` | polygon | `OBJECTID`, `Shape`, `Shape_Length`, `Shape_Area` | — | Mosaic boundary. |
| `Atlantic / Yucatan / Category {n} / Footprint` | polygon | `OBJECTID`, `Shape`, `Raster`, `Name`, `MinPS`, `MaxPS`, `LowPS`, `HighPS`, `Category`, `Tag`, `GroupName`, `ProductName`, `CenterX`, `CenterY`, `ZOrder`, `TypeID`, `ItemTS`, `UriHash`, `Uri`, `Shape_Length`, `Shape_Area` | — | Mosaic footprints. |
| `Atlantic / Yucatan / Category {n} / Image` | raster | — | — |  |
| `Pacific` | group | — | — | |
| `Pacific / Hawaii (category 1-4)` | group | — | — | Categories 1–4. |
| `Pacific / Hawaii (category 1-4) / Category {n}` | mosaic | — | — | |
| `Pacific / Hawaii (category 1-4) / Category {n} / Boundary` | polygon | `OBJECTID`, `Shape`, `Shape_Length`, `Shape_Area` | — | Mosaic boundary. |
| `Pacific / Hawaii (category 1-4) / Category {n} / Footprint` | polygon | `OBJECTID`, `Shape`, `Raster`, `Name`, `MinPS`, `MaxPS`, `LowPS`, `HighPS`, `Category`, `Tag`, `GroupName`, `ProductName`, `CenterX`, `CenterY`, `ZOrder`, `TypeID`, `ItemTS`, `UriHash`, `Uri`, `Shape_Length`, `Shape_Area` | — | Mosaic footprints. |
| `Pacific / Hawaii (category 1-4) / Category {n} / Image` | raster | — | — |  |
| `Pacific / Southern California (category 1-2)` | group | — | — | Categories 1–2. |
| `Pacific / Southern California (category 1-2) / Category {n}` | mosaic | — | — | |
| `Pacific / Southern California (category 1-2) / Category {n} / Boundary` | polygon | `OBJECTID`, `Shape`, `Shape_Length`, `Shape_Area` | — | Mosaic boundary. |
| `Pacific / Southern California (category 1-2) / Category {n} / Footprint` | polygon | `OBJECTID`, `Shape`, `Raster`, `Name`, `MinPS`, `MaxPS`, `LowPS`, `HighPS`, `Category`, `Tag`, `GroupName`, `ProductName`, `CenterX`, `CenterY`, `ZOrder`, `TypeID`, `ItemTS`, `UriHash`, `Uri`, `Shape_Length`, `Shape_Area` | — | Mosaic footprints. |
| `Pacific / Southern California (category 1-2) / Category {n} / Image` | raster | — | — |  |
| `Pacific / Guam` | group | — | — | Categories 1–5. |
| `Pacific / Guam / Category {n}` | mosaic | — | — | |
| `Pacific / Guam / Category {n} / Boundary` | polygon | `OBJECTID`, `Shape`, `Shape_Length`, `Shape_Area` | — | Mosaic boundary. |
| `Pacific / Guam / Category {n} / Footprint` | polygon | `OBJECTID`, `Shape`, `Raster`, `Name`, `MinPS`, `MaxPS`, `LowPS`, `HighPS`, `Category`, `Tag`, `GroupName`, `ProductName`, `CenterX`, `CenterY`, `ZOrder`, `TypeID`, `ItemTS`, `UriHash`, `Uri`, `Shape_Length`, `Shape_Area` | — | Mosaic footprints. |
| `Pacific / Guam / Category {n} / Image` | raster | — | — |  |
| `Pacific / American Samoa` | group | — | — | Categories 1–5. |
| `Pacific / American Samoa / Category {n}` | mosaic | — | — | |
| `Pacific / American Samoa / Category {n} / Boundary` | polygon | `OBJECTID`, `Shape`, `Shape_Length`, `Shape_Area` | — | Mosaic boundary. |
| `Pacific / American Samoa / Category {n} / Footprint` | polygon | `OBJECTID`, `Shape`, `Raster`, `Name`, `MinPS`, `MaxPS`, `LowPS`, `HighPS`, `Category`, `Tag`, `GroupName`, `ProductName`, `CenterX`, `CenterY`, `ZOrder`, `TypeID`, `ItemTS`, `UriHash`, `Uri`, `Shape_Length`, `Shape_Area` | — | Mosaic footprints. |
| `Pacific / American Samoa / Category {n} / Image` | raster | — | — |  |

## Arrival-time, probabilistic-wind, and surge layers by basin

The brief's open question (§14) asks whether these layers exist for every
storm in every basin. The answers below come from layer counts and
GeoJSON queries run between 21:39 and 21:47 UTC on 2026-10-12, after the
21:00 advisory. "Empty" means the layer exists and returned no features;
"absent" would mean the layer does not exist.

### Atlantic

| Storm | Arrival-time layers | Probabilistic winds 34/50/64 kt | Peak surge | Inundation | Checked |
| --- | --- | --- | --- | --- | --- |
| no active storm on 2026-10-12; open | — | — | — | — | 2026-10-12 |

The Atlantic held one outlook area that day (`Seven-Day: Potential
Development Region`, `basin` `Atlantic`, `prob7day` `20%`, `risk7day`
`Low`). The GIS archive holds arrival-time,
inundation, and peak-surge files for Atlantic storms (see
[GIS archive](#gis-archive)), so these products exist in the basin.
Whether the live layers fill for every Atlantic storm stays open.

### Eastern Pacific

| Storm | Arrival-time layers | Probabilistic winds 34/50/64 kt | Peak surge | Inundation | Checked |
| --- | --- | --- | --- | --- | --- |
| `EP202026` Simon, hurricane (`HU`), slot `EP5`, advisory 22 | `EP5 Earliest Reasonable Arrival Time` 7; `EP5 Most Likely Arrival Time` 7 | 11 / 11 / 11 (one product per synoptic time, 2026101218; no storm id) | empty (`Points` 0, `Lines` 0, `Polygons` 0) | empty (`Footprint_Inun_EP5` 0, `Footprint_TMask_EP5` 0) | 2026-10-12 |

- **Arrival-time layers** were populated for a hurricane whose watches
  and warnings were all in Mexico (a hurricane warning for Las Islas
  Marias, a hurricane watch from Cabo Corrientes to Bahia Tempehuaya), so
  they are not limited to US threats. Each layer
  had six labelled lines plus one with a blank label. The product's KMZ
  (`EP202026_022adv_earliest_reasonable_toa_34.kmz`) names that line the
  "Wind Speed Probability 5% contour". Labels such as `Tue 8 am` carry
  neither date nor zone. The KMZ states `timezone` `MST` and `pubAdvTime`
  `200 PM MST Mon Oct 12 2026` in its `ExtendedData`, but the map layer keeps
  neither. Issue [#11](https://github.com/nathanramoscfa/weatherbot/issues/11) chose the KMZ
  to date them (amended 2026-10-17; see [Arrival-time KMZ](#arrival-time-kmz)).
- **Probabilistic winds** carry no storm field. `idp_source` names the
  synoptic time (`2026101218_wsp34knt120hr_5km`), the same file the
  roster lists under Simon's `windSpeedProbabilitiesGIS`. They are one
  product per synoptic time, not one per storm. Issue
  [#12](https://github.com/nathanramoscfa/weatherbot/issues/12) decides whether v2 ties
  them to a storm or to the snapshot.
- **Peak surge and inundation** were empty, consistent with the roster's
  `null` surge objects for Simon.

### Central Pacific

| Storm | Arrival-time layers | Probabilistic winds 34/50/64 kt | Peak surge | Inundation | Checked |
| --- | --- | --- | --- | --- | --- |
| no active storm on 2026-10-12; open | — | — | — | — | 2026-10-12 |

### Summary service versus slots

The summary service serves every slot product across storms: forecast
points, track, cone, watches and warnings, past points and track, wind
swath and radii, the advisory wind field, both arrival-time layers, and
inundation and tidal mask. It also serves the outlook layers and the
probabilistic winds. No product is served only per slot. The slot service
separates storms by layer name, and the summary separates them by the
`binnumber` field. The probabilistic winds are not a slot product in
either service. They are a top-level group, byte-identical in both.

## NWS API

### Points

`nws-points`. For the Miami-Dade landmark,
`GET https://api.weather.gov/points/25.7757,-80.1966` returned 200,
`application/geo+json`, with `Cache-Control: public, max-age=86400,
s-maxage=86400`.

- **Properties present:** `@id`, `@type`, `cwa`, `type`, `forecastOffice`,
  `gridId`, `gridX`, `gridY`, `forecast`, `forecastHourly`,
  `forecastGridData`, `observationStations`, `relativeLocation`
  (`city`, `state`, `distance`, `bearing`), `forecastZone`, `county`,
  `fireWeatherZone`, `timeZone`, `radarStation`, `astronomicalData`,
  `nwr`.
- **Values:** `cwa` `MFL`; `forecastZone` `…/zones/forecast/FLZ173`;
  `county` `…/zones/county/FLC086`; `fireWeatherZone` `…/zones/fire/FLZ173`;
  `timeZone` `America/New_York`; `radarStation` `KAMX`;
  `relativeLocation` Miami, FL.
- **Fields v2 uses:** `forecastZone` and `county` (the zone id is the last
  path segment), `cwa`, `timeZone`, and `relativeLocation.properties.city`
  and `state`.

For the Nassau landmark, `GET https://api.weather.gov/points/25.0778,-77.3405`
returned the API's out-of-coverage error: 404, `application/problem+json`,
`Cache-Control: private, max-age=86400`. The body:

```json
{
  "correlationId": "<request id>",
  "title": "Data Unavailable For Requested Point",
  "type": "https://api.weather.gov/problems/InvalidPoint",
  "status": 404,
  "detail": "Unable to provide data for requested point 25.0778,-77.3405",
  "instance": "https://api.weather.gov/requests/<request id>"
}
```

This is v2's non-US path. A location whose `/points` returns
`InvalidPoint` has no NWS zones. Its official watches and warnings come
from `{slot} Watch-Warning` and `Watch_Warning_Breakpoints`.

### Alerts at a point

`nws-alerts-point`: `GET https://api.weather.gov/alerts/active?point={lat},{lon}`.

- **Miami-Dade:** 200, a FeatureCollection with no features, plus `title`
  and `updated`.
- **Nassau:** 400, `application/problem+json`, `type`
  `https://api.weather.gov/problems/InvalidParameter`, `detail`
  `Parameter "point" is invalid: out of bounds`. A non-US location never
  calls this path.

### Alerts for a zone

`nws-alerts-zone`: `GET https://api.weather.gov/alerts/active/zone/{zoneId}`,
`Cache-Control: public, max-age=5`, with an `ETag`. The point and the
county disagreed again on 2026-10-12, as they had on 2026-10-11 (brief
§5):

- `FLC086` (Miami-Dade County, the landmark's `county`) returned one
  alert: a Coastal Flood Statement from NWS Miami FL covering Coastal
  Collier County, Mainland Monroe, and Far South Miami-Dade County
  (`affectedZones` `FLZ069`, `FLZ075`, `FLZ174`). Its `geocode.SAME`
  includes `012086` and its `geometry` is `null`.
- `FLZ173` (Coastal Miami Dade County, the landmark's forecast and fire
  zone) returned none.

A county query returns alerts for any part of the county, including
forecast zones that do not contain the location. `affectedZones` and
`geocode.UGC` say which zones an alert covers. How the engine weighs a
county alert outside the location's own forecast zone is recorded in
issue [#10](https://github.com/nathanramoscfa/weatherbot/issues/10).

- **Alert properties present:** `@id`, `@type`, `id`, `areaDesc`,
  `geocode` (`SAME`, `UGC`), `affectedZones`, `references`, `sent`,
  `effective`, `onset`, `expires`, `ends`, `status`, `messageType`,
  `category`, `severity`, `certainty`, `urgency`, `event`, `sender`,
  `senderName`, `headline`, `description`, `instruction`, `response`,
  `note`, `parameters` (`AWIPSidentifier`, `WMOidentifier`,
  `NWSheadline`, `BLOCKCHANNEL`, `VTEC`, `eventEndingTime`,
  `expiredReferences`), `scope`, `code`, `language`, `web`, `eventCode`.
- **Fields v2 uses:** `id`, `event`, `headline`, `severity`, `certainty`,
  `urgency`, `status`, `messageType`, `category`, `sent`, `effective`,
  `onset`, `expires`, `ends`, `areaDesc`, `affectedZones`, `geocode`,
  `senderName`, `references`, `parameters.VTEC`, `parameters.NWSheadline`,
  `description`, `instruction`.

### Zones

`nws-zones`: `GET https://api.weather.gov/zones/{type}/{zoneId}` for the
zones the point returned. The responses were `county/FLC086` (784,207
bytes), `forecast/FLZ173` (300,392), and `fire/FLZ173` (300,840). Each is
a MultiPolygon with a `Cache-Control` `max-age` of 24 to 30 days
(`s-maxage=604800`) and a `Last-Modified`.

- **Properties present:** `@id`, `@type`, `id`, `type`, `name`,
  `effectiveDate`, `expirationDate`, `state`, `forecastOffice`,
  `gridIdentifier`, `awipsLocationIdentifier`, `cwa`, `forecastOffices`,
  `timeZone`, `observationStations`, `radarStation`.
- **Fields v2 uses:** `id`, `type`, `name`, `state`, `cwa`, `timeZone`,
  `effectiveDate`, and the geometry (the map, and a location's optional
  polygon).

### User-Agent and polite use

The [API documentation](https://www.weather.gov/documentation/services-web-api)
says: "A User Agent is required to identify your application", and
contact details let NWS reach the owner if the string "is associated to a
security event". It adds that the User-Agent "will be replaced with an
API key in the future". If that happens, the four `nws-*` rows become a
keyed source and need a decision.

The rate limit "is not public information, but allows a generous amount
for typical use". A request over the limit returns an error and "may be
retried after the limit clears (typically within 5 seconds)".

v2 sends at most one request per second to `api.weather.gov` and polls
alerts at the scheduler's cadence (Phase 4). It caches points and zones,
whose own lifetimes are a day or more.

## Text products

`nhc-text-products`. One live product of each kind was compared between
NHC's pages and the NWS API: Simon's TCP, advisory 22, and the Atlantic
TWO of 2 PM EDT.

| | NHC page | NWS API |
| --- | --- | --- |
| Request | `https://www.nhc.noaa.gov/text/MIATCPEP5.shtml` (the roster's `publicAdvisory.url`); `text/refresh/MIATCPEP5+shtml/` served the same page | `https://api.weather.gov/products/types/TCP/locations/EP5`, then `https://api.weather.gov/products/{id}` |
| Format | HTML, the product in one `<pre>` | JSON-LD: `@id`, `id`, `wmoCollectiveId`, `issuingOffice`, `issuanceTime`, `productCode`, `productName`, `productText` |
| Issuance | in the text only | `issuanceTime` `2026-10-12T20:51:00+00:00`, matching the WMO line `WTPZ35 KNHC 122051` |
| Caching | `max-age=60`, no validators | `max-age=120` |
| Text | identical, line for line, plus an "en Español" link inside the TWO's `<pre>` | identical |

**Decision: v2 reads text products from the NWS API.** It carries the
same text with a structured issuance time and WMO identifiers, as JSON,
so no HTML is scraped.

- **Locations:** TCP by slot (`AT1`–`AT5`, `EP1`–`EP5`, `CP1`–`CP5`). At
  21:39 the list held `AT4`, `EP3`, `EP5`, and Guam's `PQ1` and `PQ3`. TWO
  by basin: `AT` (`ABNT20 KNHC`), `EP` (`ABPZ20 KNHC`), and `CP`
  (`ACPN50 PHFO`). `SAT`, `SEP`, and `SCP` hold the Spanish
  editions: the NHC page's "en Español" link points to `MIATWOSAT`.
- **Filtering:** the unfiltered `/products/types/TCP` also lists Guam's
  advisories (`PGUM`), so a client always asks by location. A slot is
  reused by later storms in a season. The text's header line names the
  ATCF id (`EP202026`), which a client matches.
- **History:** the `EP5` TCP list held 41 products, back to 2026-10-07
  14:57. The `AT` TWO list held 28, back to 2026-10-05 23:30.
- **Etiquette:** the API's one-request-per-second pacing applies.
- **Fields v2 uses:** a product's `id`, `issuanceTime`, `wmoCollectiveId`,
  `issuingOffice`, and `productText` (listed 2026-10-17).
- A TCP's storm comes from the ATCF id on its header line, and its
  advisory from the text's "ADVISORY NUMBER 22A".
- **List fields v2 uses:** each list item's `id` and `issuanceTime`; the
  newest item names the product to fetch (listed 2026-10-17).

## Outlook graphics

`nhc-outlook-graphics`: `GET https://www.nhc.noaa.gov/xgtwo/<file>`.

| File | Status | Bytes | Size (px) | Last-Modified |
| --- | --- | --- | --- | --- |
| `two_atl_2d0.png` | 200 | 215,215 | 900×679 | 17:12:13 |
| `two_atl_7d0.png` | 200 | 68,608 | 900×679 | 17:12:13 |
| `two_pac_2d0.png` | 200 | 164,799 | 900×547 | 20:52:47 |
| `two_pac_7d0.png` | 200 | 47,795 | 900×547 | 20:52:47 |
| `two_cpac_2d0.png` | 200 | 162,665 | 900×679 | 17:12:12 |
| `two_cpac_7d0.png` | 200 | 35,321 | 900×679 | 17:12:12 |
| `two_epac_2d0.png`, `two_epac_7d0.png` | 404 | — | — | — |

- **Names:** the brief's `two_epac_*` names still return 404. The Eastern
  Pacific maps are `two_pac_*`.
- **Caching:** every graphic sends `Cache-Control: max-age=300`, an
  `ETag`, and a `Last-Modified`. A conditional request for
  `two_atl_7d0.png` returned 304.
- **Redraws:** the Eastern Pacific maps were redrawn at 20:52 with Simon's
  advisory, not only at outlook times.
- **Dimensions** change over time. The v1 reports of 2025 embed
  `two_atl_7d0.png` at 900×665; on 2026-10-12 it was 900×679. A contract
  test compares each capture with its own recorded size.

## GIS RSS feeds

`nhc-gis-rss`: `GET https://www.nhc.noaa.gov/gis-at.xml`, `gis-ep.xml`,
and `gis-cp.xml`. Each is RSS 2.0 as `text/xml`, with the `georss`, `gml`,
and `nhc` (`https://www.nhc.noaa.gov`) namespaces, `Cache-Control:
max-age=300`, an `ETag`, and a `Last-Modified`.

- **With a storm.** `gis-ep.xml` carried eight items for Simon. A
  `Summary` item linked the TCP page and held an `nhc:Cyclone` element
  with `center`, `type`, `name`, `wallet` (`EP5`), `atcf` (`EP202026`),
  `datetime`, `movement`, `pressure`, `wind`, and `headline`. Seven
  product items followed: the advisory forecast shapefile, the track,
  cone, and watch/warning KMZ files, the wind-field shapefile, and the
  best-track shapefile and KMZ. Every item has `title`, `description`,
  `pubDate`, `link`, `guid` (for example
  `gis-forecast-shp-ep202026-022-202610122053`), and `author`.
- **Without a storm.** `gis-at.xml` and `gis-cp.xml` each held one item,
  "There are no tropical cyclones at this time.", whose `pubDate` lay in
  the future (`Wed, 14 Oct 2026 05:03:28 GMT` in `gis-at.xml`). The
  placeholder's `pubDate` is not a time.
- **Rewrites.** `gis-ep.xml` was rewritten at 21:46:32, 22 minutes after
  the previous version, with only the channel `pubDate` changed. A
  conditional request after the rewrite returned 200.
- **Fields v2 uses:** each item's `guid`, `title`, `link`, and `pubDate`,
  and, where the item has one, `nhc:Cyclone.atcf` and `nhc:Cyclone.wallet`
  (written as paths 2026-10-17).
- Change detection compares the items' guids. The channel `pubDate` is
  not read, because NHC rewrites it without changing an item.

## GIS archive

`nhc-gis-archive`, the replay corpus that Step 6 fetches for Irma
(AL112017), Dorian (AL052019), Ian (AL092022), and Milton (AL142024). The
listing pages are HTML and relative to `https://www.nhc.noaa.gov/gis/`.
For each storm, one file of each product was requested on 2026-10-12
and answered 200; Irma's arrival-time URL answered 404. The
`Last-Modified` dates of archived files are when the archive was written,
not issuance times.

| Product | Listing | File URL | Notes |
| --- | --- | --- | --- |
| Advisory forecast: track, cone, points, watches and warnings | `archive_forecast.php?year={yyyy}`, then `archive_forecast_results.php?id={bb}{nn}&year={yyyy}` | `https://www.nhc.noaa.gov/gis/forecast/archive/{id}_5day_{adv}.zip` | `{id}` in lower case (`al112017`). `{adv}` is three digits, plus `A` for an intermediate advisory. Shapefiles, 33–41 KB each where checked. |
| Wind field and forecast radii | the same listing | `https://www.nhc.noaa.gov/gis/forecast/archive/{id}_fcst_{adv}.zip` | Shapefiles with `SYNOPTIME` (`YYYYMMDDHH`). |
| Wind-speed probabilities | `archive_wsp.php?year={yyyy}` | `https://www.nhc.noaa.gov/gis/forecast/archive/{yyyymmddhh}_wsp_120hr5km.zip` (polygons), `_wsp_120hrhalfDeg.zip` (points), `_wsp{34,50,64}knt120hr_5km.kmz` | One set per synoptic time, with no storm in the name. The 2017 listing also has `tenthDeg` files, from January to May only. |
| Arrival time of tropical-storm-force winds | `archive_toa.php?year={yyyy}`, years from 2018 | `https://www.nhc.noaa.gov/storm_graphics/api/{ID}_{adv}adv_{earliest_reasonable,most_likely}_toa_34.kmz` | `{ID}` in upper case (`AL052019`). KMZ only, full advisories only. `archive_toa_results.php` ignores its `id` and `year` and lists all 14,730 files since 2018 in one 1.9 MB page. |
| Potential storm-surge flooding (inundation) | `archive_inundation.php?year={yyyy}`, then `archive_inundation_results.php?id={bb}{nn}&year={yy}` | `https://www.nhc.noaa.gov/gis/inundation/forecasts/{BB}{nn}{yy}_{adv}_{inundation,tidalmask}.zip` | Two-digit year and two-digit advisory (`AL1117_34_inundation.zip`). 10–22 MB each. |
| Peak storm surge | `archive_peakSurge.php?year={yyyy}`, then `archive_peakSurge_results.php?id={bb}{nn}&year={yy}` | `https://www.nhc.noaa.gov/gis/peakSurge/{ID}_PeakStormSurge_{adv}adv.kml`; in 2022, `{ID}_ExperimentalPeakStormSurge_{adv}adv.kml` | KML, 0.5–1.2 MB each. |

What exists for each replay storm (counts are files per product; the WSP
check covers every six-hourly synoptic time from the storm's first to its
last `fcst` package):

| Storm | `_5day_` | `_fcst_` | Wind-speed probabilities | Arrival times | Inundation | Peak surge |
| --- | --- | --- | --- | --- | --- | --- |
| AL112017 Irma | 84: 001–052, 32 intermediates | 84, as `_5day_` | complete, 2017083012–2017091200 (51 times) | none: the archive begins in 2018, and `AL112017_001adv_…` returns 404 | 18 advisories, 34–51 | none ("No files found") |
| AL052019 Dorian | 117: 001–064, 53 intermediates | 117, as `_5day_` | complete, 2019082412–2019090900 (63 times) | 64 advisories, 001–064, both kinds | 21 advisories, 33–53 | none ("No files found") |
| AL092022 Ian | 68: 001–038, 30 intermediates | 65: 001–035 | complete, 2022092306–2022100106 (33 times) | 35 advisories, 001–035, both kinds | 20 advisories, 12–33 except 21 and 23 | 29 `Experimental` files, 011–033A |
| AL142024 Milton | 41: 001–023, 18 intermediates | 41, as `_5day_` | complete, 2024100512–2024101018 (22 times) | 23 advisories, 001–023, both kinds | 17 advisories, 05–22 except 09 | 22 files, 008–023 |

### Replay corpus recorded 2026-10-15

`tests/fixtures/replay/corpus-manifest.json` pins 1,199 original archive
files, 117,177,968 bytes (111.75 MiB), by URL, size, and SHA-256. The
ignored cache defaults to `.cache/replay-corpus/`; set
`WEATHERBOT_CORPUS_CACHE` or pass `--cache` to use another directory.
Discovery reads the listings above, not storm web pages. Forecast and
probability products use shapefile zips; arrival times use KMZ because
no shapefile is available. WSP includes both the 5 km polygons and
half-degree points, with advisory associations taken from `SYNOPTIME`
in the radii packages, not a guessed issuance time.

| Storm | Forecast advisories / 5day files | Radii files | WSP files | Arrival KMZ files | Total cache files | Cache bytes |
| --- | --- | --- | --- | --- | --- | --- |
| AL112017 Irma | 84 | 84 | 102 | 0 | 270 | 32,727,720 |
| AL052019 Dorian | 117 | 117 | 126 | 128 | 488 | 46,005,977 |
| AL092022 Ian | 68 | 65 | 66 | 70 | 269 | 20,883,514 |
| AL142024 Milton | 41 | 41 | 44 | 46 | 172 | 17,560,757 |

Irma has no arrival-time product (the archive begins in 2018). The other
storms have both arrival products only for full advisories: Dorian
001–064, Ian 001–035, and Milton 001–023. Intermediate advisories have
none, and Ian's full advisories 036–038 lack both radii and arrival
products. Every available radii synoptic time has both WSP shapefile
products. Watch-warning geometry exists in 271 forecast packages; the
other packages lack that product. The manifest records these gaps;
no absent product is fabricated. Inundation and peak surge are outside
this corpus.

The committed subset contains 1,201 compressed FeatureCollections,
5,435,928 bytes (5.18 MiB), covering **all 310 advisories**. With the
manifest and notice, the replay tree is about 6.68 MiB, below its
10 MiB cap. Every cone is a valid polygon; source attributes are
preserved, keys sorted, floats fixed to seven decimals, and gzip
`mtime` fixed to zero. The regional fallback rule was not needed.

Every archived `.prj` in this corpus declares geographic `D_Sphere`,
radius 6,371,200 m. With operator approval on 2026-10-15, conversion
preserves that native CRS and records exact WKT in the manifest and
`source_crs` in each collection. These coordinates have **not** been
transformed to WGS84; the output is GeoJSON-shaped native-CRS data,
not RFC 7946 WGS84 GeoJSON. Consumers must honor this provenance.
Projected or unsupported datums still stop conversion.

Dorian 056–062A has 39 one-vertex watch-warning records across 13
advisories. Conversion represents those as Points, retains the source
line in `source_geometry`, and adds `geometry_note`; it invents no line
segment. pyshp also preserves rings when the source has only interior
winding by treating them as exterior rings; all resulting cones pass
validity checks. The original archives remain untouched in the cache.

```sh
uv run python scripts/fetch_replay_corpus.py fetch
uv run python scripts/fetch_replay_corpus.py verify
uv run python scripts/fetch_replay_corpus.py convert
uv run pytest -m corpus
```

`manifest` deliberately refreshes the trust baseline from a fresh
download; review its diff before committing. `manifest --reuse-downloads`
resumes an interrupted initial recording using retained bytes and fresh
listings; it establishes new checksums, so it is forbidden for `fetch`,
`verify`, or `convert`. Normal fetches never rewrite checksums or accept
corrupt existing files. Every parse follows checksum verification;
archive members are bounded, path-checked, and read in memory.

`replay-corpus.yml` verifies the original cache and byte-for-byte
reconversion on relevant PRs and merges, on demand, and at 08:23 UTC
Mondays and Thursdays. Its actions cache is keyed only on the manifest
hash. It is read-only, keyless, and outside required branch checks.
GitHub can evict unused caches after seven days and disable scheduled
workflows after 60 days without repository activity; a miss fetches the
pinned originals again. The `simulate_failure` dispatch proves the
failure alarm after verification and tests have passed.

## Overlays

Both overlays come from NOAA's nowCOAST, so the Iowa Environmental
Mesonet is the fallback. Each is a WMS 1.3.0 service whose capabilities
read `Fees` `NONE` and `AccessConstraints` `NONE`. A 256×256 `GetMap`
(`crs=EPSG:3857`, `format=image/png`, `transparent=true`) over the
Miami-Dade landmark's zoom-5 tile returned a PNG for every layer below,
with `Cache-Control: max-age=240, public`. Each layer has a `time`
dimension whose default is the latest image.

| Source id | Service | Layer | Content | Cadence |
| --- | --- | --- | --- | --- |
| `overlay-radar` | `https://nowcoast.noaa.gov/geoserver/weather_radar/ows` | `conus_base_reflectivity_mosaic` (style `weather_radar_base_reflectivity`) | MRMS base-reflectivity mosaic, 1 km. The layer's extent covers both landmarks. | "updated approximately every 4 minutes"; image times were 3–4 min apart |
| `overlay-satellite` | `https://nowcoast.noaa.gov/geoserver/satellite/ows` | `goes_longwave_imagery` (day and night), `goes_visible_imagery` (daylight) | GOES-East and GOES-West composites | "updated with new GOES-EAST and GOES-WEST composite images every 5 minutes" |

The fallback is the Iowa Environmental Mesonet. Its capabilities were
read on 2026-10-12, but no `GetMap` was sent:

- radar: `https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0q.cgi`,
  layer `nexrad-n0q-900913`;
- satellite: `https://mesonet.agron.iastate.edu/cgi-bin/wms/goes_east.cgi`,
  layers `conus_ch01` … `conus_ch16` and `fulldisk_ch01` … `fulldisk_ch16`.

Its [disclaimer](https://mesonet.agron.iastate.edu/disclaimer.php) puts
its materials in the public domain and appreciates attribution.

## OpenStreetMap: basemap and geocoding

- **Tiles** (`basemap-osm-tiles`):
  `https://tile.openstreetmap.org/{z}/{x}/{y}.png`. One tile (`0/0/0`)
  returned 200 with `max-age=528077, stale-while-revalidate=604800` and an
  `ETag`. The
  [tile usage policy](https://operations.osmfoundation.org/policies/tiles/)
  requires that URL, visible licence attribution, a User-Agent that
  "clearly identifies your application", a Referer from web pages, and
  caching per the HTTP headers. It forbids bulk download, prefetching,
  and no-cache headers. The browser loads tiles directly, so nothing is
  recorded.
- **Reverse geocoding** (`geocode-nominatim`):
  `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}`.
  - Miami-Dade landmark: `Miami-Dade County Office, 111, Northwest 1st
    Street, …, Miami, Miami-Dade County, Florida, 33128, United States`
    (`osm_type` `node`).
  - Nassau landmark: `Parliament Square, Nassau, New Providence, The
    Bahamas` (`relation` 14900727, the landmark's own source object).
  - **Fields present:** `place_id`, `licence`, `osm_type`, `osm_id`,
    `lat`, `lon`, `category`, `type`, `place_rank`, `importance`,
    `addresstype`, `name`, `display_name`, `address`, `boundingbox`.
  - **Fields v2 uses:** `display_name`, `name`, `address`
    (`country_code`, `country`), `licence`, `osm_type`, `osm_id`.
  - **Policy:** the
    [usage policy](https://operations.osmfoundation.org/policies/nominatim/)
    sets "an absolute maximum of 1 request per second" and a User-Agent
    or Referer that identifies the application. It requires visible
    attribution, says results "must be cached on your side", and calls
    periodic requests bulk geocoding. v2 geocodes each location once, at
    setup, and keeps the result. The data is © OpenStreetMap
    contributors under ODbL 1.0.

## Not used

| Source | Why not |
| --- | --- |
| ATCF invest files (v1's `atcf_client.py`) | Invests come from the outlook layers (`Two-Day: Current Location`, `Seven-Day: Potential Development Region`), and storms from `nhc-current-storms`. v2 takes storms and disturbances only from official products. |
| NHC storm web pages (`graphics_{slot}.shtml`, `text/*.shtml`, `text/refresh/…`) | No HTML scraping. Text products come from the NWS API, and geometry from the map services. |
| Live per-storm shapefiles and KMZ (`forecast/archive/*_latest.zip`, `storm_graphics/api/*.kmz`), except the arrival-time KMZ | The map services serve the same products as GeoJSON. The archive copies serve only the replay corpus (Step 6). The arrival-time KMZ is read (`nhc-arrival-times`, amended 2026-10-17): its `timezone` and `pubAdvTime` date the arrival lines, which the map layers cannot (issue #11). |
| Arrival-time and wind-speed-probability GRIB2 (`https://ftp.nhc.ncep.noaa.gov/toa/`, `/wsp/`), probabilistic storm surge | The map layers carry what v2 shows. Gridded data would add a GRIB dependency for no rule in the brief. |
| `two_epac_{2d0,7d0}.png` | 404. The working names are `two_pac_*`. |
| Any source that needs a key | None of the sources above needs one. If NWS replaces its User-Agent requirement with an API key, as its documentation says it will, the `nws-*` rows need a decision first. |
