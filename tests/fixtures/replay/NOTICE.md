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

Dorian advisories 056–062A contain 39 one-vertex watch-warning line
records. These are represented as Points, with the original geometry retained
in `source_geometry` and the reason in `geometry_note`; no segment is invented.
The source rings are preserved by pyshp, including its exterior-ring fallback
for shapefiles whose rings all have interior winding. All converted cones are
checked for validity. Original attributes are preserved without edits.

Missing watch-warning files mean the archive did not include that product for
that advisory; no empty warning product is invented. The manifest records
unavailable radii and arrival-time advisories, WSP-to-advisory associations via
the radii package's `SYNOPTIME`, and any deliberate subset omissions.

Weatherbot is informational only and never a substitute for official guidance.
See [DISCLAIMER.md](../../../DISCLAIMER.md).
