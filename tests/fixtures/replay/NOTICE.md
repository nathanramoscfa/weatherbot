# Replay corpus attribution and coordinate policy

These are official National Hurricane Center products, public-domain United
States government data. The archive URLs, original byte counts, SHA-256 hashes,
advisory associations, and each shapefile's original projection WKT are recorded
in `corpus-manifest.json`. Original archives remain in the ignored cache.

The compressed FeatureCollections preserve the original attributes and native
geographic coordinates, rounded to seven decimal places. The `source_crs` member
records the datum and WKT. Geographic `D_Sphere` coordinates use a sphere of
radius 6,371,200 metres: **they have not been transformed to WGS84 and are not
RFC 7946 WGS84 GeoJSON**. Consumers must honor the recorded CRS. The operator
approved native-coordinate preservation on 2026-10-15.

Dorian advisories 056–062A contain 36 one-vertex watch-warning line
records, three in each of 12 advisories (057A has no watch-warning product).
These are represented as Points, with the original geometry retained
in `source_geometry` and the reason in `geometry_note`; no segment is invented.
The source rings are preserved by pyshp, including its exterior-ring fallback
for shapefiles whose rings all have interior winding. All converted cones are
checked for validity. Original attributes are preserved without edits.

Missing watch-warning files mean the archive did not include that product for
that advisory; no empty warning product is invented. The manifest records
unavailable radii and arrival-time advisories, WSP-to-advisory associations via
the radii package's `SYNOPTIME`, any deliberate subset omissions, and the day
the originals were recorded (`recorded_on`).

## Wind-speed-probability windows

`<storm>/wsp/<yyyymmddhh>/wsp-<34|50|64>kt.geojson.gz` holds each synoptic
time's 5 km wind-speed-probability product, **clipped** to two windows: the
boxes reaching one degree of latitude and longitude on each side of each
public landmark in `scripts/public_landmarks.toml`, in the product's own
coordinates. The `window` member names the landmarks, the half-width, and the
covered MultiPolygon. A windowed product says nothing outside its window: read
it only at a point inside the window. A file is written even when no band
reaches either window.

A band Shapely finds invalid is made valid before clipping, and its feature
records the original reason in `geometry_note`; where clipping left a part
self-touching, that part is made valid again and the note says so. A source
record with a NULL shape has no area and is omitted. The `PERCENTAGE` labels
are kept as published. The complete products stay in the ignored cache;
`scripts/fetch_replay_corpus.py convert --full --out DIR` converts them, with
every forecast product and arrival-time KMZ, outside the checkout.

Weatherbot is informational only and never a substitute for official guidance.
See [DISCLAIMER.md](../../../DISCLAIMER.md).
