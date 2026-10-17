# tests/sources/test_nhc_arrival_times.py
"""Tests of the arrival-time KMZ client: limits, resolution, roster checks, and fetching.

The archived Dorian 036 pair comes from the recorded ``nhc-arrival-times`` capture; every
other KMZ is built here, with one-decimal coordinates that name no place in particular.
"""

import io
import logging
import os
import zipfile
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from source_support import NOW, Quiet, entry, recorded, recorded_result, serve

from weatherbot.models import (
    Advisory,
    AdvisoryNumber,
    ArrivalTimeLine,
    ArrivalTimeProduct,
    Provenance,
    RosterProduct,
    StormClassification,
    StormSummary,
)
from weatherbot.sources import nhc_arrival_times as arrivals
from weatherbot.sources.drift import DRIFT_ATTRIBUTE
from weatherbot.sources.errors import SourceSchemaError

ARCHIVE = "https://www.nhc.noaa.gov/storm_graphics/api/AL052019_036adv_{kind}_toa_34.kmz"
EARLIEST_URL = ARCHIVE.format(kind="earliest_reasonable")
MOST_LIKELY_URL = ARCHIVE.format(kind="most_likely")
PUBLISHED = datetime(2019, 9, 2, 9, tzinfo=UTC)  # 500 AM EDT Mon Sep 02 2019
PUBLISHED_TEXT = "500 AM EDT Mon Sep 02 2019"
KML_NAMESPACE = "http://earth.google.com/kml/2.2"
OPENGIS_NAMESPACE = "http://www.opengis.net/kml/2.2"
OUTER = arrivals.OUTER_CONTOUR_LABEL
MEBIBYTE = 1024 * 1024


def at(day: int, hour: int) -> datetime:
    return datetime(2019, 9, day, hour, tzinfo=UTC)


EARLIEST_INSTANTS = {
    "Mon 8 am": at(2, 12),
    "Mon 2 pm": at(2, 18),
    "Mon 8 pm": at(3, 0),
    "Tue 2 am": at(3, 6),
    "Tue 8 am": at(3, 12),
    "Tue 8 pm": at(4, 0),
    "Wed 8 am": at(4, 12),
    "Wed 8 pm": at(5, 0),
    "Thu 8 am": at(5, 12),
    "Thu 8 pm": at(6, 0),
    "Fri 8 am": at(6, 12),
}
MOST_LIKELY_INSTANTS = {
    "Mon 2 pm": at(2, 18),
    "Mon 8 pm": at(3, 0),
    "Tue 8 am": at(3, 12),
    "Tue 8 pm": at(4, 0),
    "Wed 8 am": at(4, 12),
    "Wed 8 pm": at(5, 0),
    "Thu 8 am": at(5, 12),
    "Thu 8 pm": at(6, 0),
    "Fri 8 am": at(6, 12),
    "Fri 8 pm": at(7, 0),
}


def archived(url: str) -> tuple[bytes, Provenance]:
    directory = recorded("nhc-arrival-times")
    result = recorded_result(directory, entry(directory, url.rsplit("/", 1)[1]))
    return result.body, result.provenance()


def kml(  # noqa: PLR0913 - one keyword per statement a test varies
    *,
    namespace: str = KML_NAMESPACE,
    data: dict[str, str] | None = None,
    labels: tuple[str, ...] = ("Mon 8 am", OUTER),
    multi: bool = False,
    prolog: str = "",
    cells: int = 1,
) -> bytes:
    values = {
        "timezone": "EDT",
        "storm": "Hurricane Example",
        "atcfid": "AL052019",
        "advisoryNum": "36",
        "pubAdvTime": PUBLISHED_TEXT,
        **(data or {}),
    }
    extended = "".join(
        f'<Data name="{name}"><value>{value}</value></Data>' for name, value in values.items()
    )
    line = "<LineString><coordinates>-80.5,25.5,0 -79.5,26.5,0</coordinates></LineString>"
    geometry = f"<MultiGeometry>{line}{line}</MultiGeometry>" if multi else line
    marks = "".join(
        "<Placemark><description><![CDATA[<table><tr>"
        + f"<td>{label}</td>" * cells
        + f"</tr></table>]]></description>{geometry}</Placemark>"
        for label in labels
    )
    icon = "<Placemark><Point><coordinates>-80.5,25.5</coordinates></Point></Placemark>"
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>{prolog}<kml xmlns="{namespace}"><Document>'
        f"<ExtendedData>{extended}</ExtendedData>{icon}{marks}</Document></kml>"
    ).encode()


def kmz(*members: tuple[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression) as archive:
        for name, data in members:
            archive.writestr(name, data)
    return buffer.getvalue()


def product_kmz(document: bytes | None = None) -> bytes:
    return kmz(("doc.kml", document or kml()), ("labels/am.png", b"\x89PNG label"))


def provenance(url: str = EARLIEST_URL) -> Provenance:
    return Provenance(
        source_id="nhc-arrival-times", url=url, status=200, fetched_at=NOW, sha256="0" * 64
    )


def roster_storm(
    *, issued_at: datetime = PUBLISHED, advisory: str = "036", atcf_id: str = "AL052019"
) -> StormSummary:
    def product(url: str) -> RosterProduct:
        return RosterProduct(advisory=AdvisoryNumber.parse(advisory), issued_at=issued_at, url=url)

    return StormSummary(
        atcf_id=atcf_id,
        slot="AT1",
        name="Example",
        classification=StormClassification.parse("HU"),
        intensity_kt=100,
        pressure_mb=950,
        latitude=25.0,
        longitude=-75.0,
        movement_dir_deg=None,
        movement_speed_mph=None,
        last_update=issued_at,
        public_advisory=product("https://www.nhc.noaa.gov/text/MIATCPAT1.shtml"),
        earliest_arrival_kmz=product(EARLIEST_URL.replace("AL052019", atcf_id)),
        most_likely_arrival_kmz=product(MOST_LIKELY_URL.replace("AL052019", atcf_id)),
        has_storm_surge_watch_warning=False,
        has_potential_storm_surge_flooding=False,
        has_peak_surge=False,
    )


def drift_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if hasattr(r, DRIFT_ATTRIBUTE)]


# The archived pair (issue #11's acceptance) -----------------------------------------------


@pytest.mark.parametrize(
    ("url", "instants"),
    [(EARLIEST_URL, EARLIEST_INSTANTS), (MOST_LIKELY_URL, MOST_LIKELY_INSTANTS)],
    ids=["earliest_reasonable", "most_likely"],
)
def test_the_archived_pair_resolves_every_label_to_the_listed_instant(
    url: str, instants: dict[str, datetime]
) -> None:
    body, origin = archived(url)

    product = arrivals.parse_arrival_kmz(body, origin)

    assert product.origin == "kmz"
    assert product.withheld_reason is None
    assert (product.atcf_id, product.advisory.number) == ("AL052019", AdvisoryNumber.parse("36"))
    assert (product.time_zone, product.published_at) == ("EDT", PUBLISHED)
    assert product.published_local_text == PUBLISHED_TEXT
    labelled = {line.label: line.valid_at for line in product.lines if not line.is_outer_contour}
    assert labelled == instants
    (outer,) = [line for line in product.lines if line.is_outer_contour]
    assert (outer.label, outer.valid_at, outer.unresolved_reason) == (None, None, None)
    assert product.lines[-1] is outer


def test_the_archived_pair_agrees_with_a_roster_storm_that_lists_it() -> None:
    body, origin = archived(EARLIEST_URL)

    product = arrivals.parse_arrival_kmz(body, origin, roster_storm())

    assert product.withheld_reason is None
    assert all(line.valid_at for line in product.lines if not line.is_outer_contour)


# Disagreements leave every line unresolved, with the reason -------------------------------


def test_a_roster_issuance_ninety_minutes_from_pub_adv_time_leaves_every_line_unresolved(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body, origin = archived(EARLIEST_URL)
    storm = roster_storm(issued_at=PUBLISHED + timedelta(minutes=90))

    with caplog.at_level(logging.WARNING, "weatherbot.sources"):
        product = arrivals.parse_arrival_kmz(body, origin, storm)

    assert product.withheld_reason is not None
    assert "more than an hour from the roster's issuance" in product.withheld_reason
    for line in product.lines:
        assert line.valid_at is None
        assert line.unresolved_reason == (
            None if line.is_outer_contour else product.withheld_reason
        )
    assert any("nhc-arrival-times" in message for message in drift_messages(caplog))


def test_an_issuance_within_the_hour_still_resolves() -> None:
    body, origin = archived(EARLIEST_URL)

    product = arrivals.parse_arrival_kmz(
        body, origin, roster_storm(issued_at=PUBLISHED + timedelta(minutes=60))
    )

    assert product.withheld_reason is None


@pytest.mark.parametrize(
    ("storm", "data", "reason"),
    [
        (roster_storm(advisory="035"), {}, "not the roster's advNum 35"),
        (None, {"advisoryNum": "35"}, "not the URL's advisory 36"),
        (None, {"atcfid": "AL062019"}, "not the URL's storm AL052019"),
        (roster_storm(atcf_id="AL062019"), {}, "not the roster storm AL062019"),
        (None, {"timezone": "CDT"}, "is not the zone pubAdvTime names"),
    ],
    ids=["roster-advisory", "url-advisory", "url-storm", "roster-storm", "zone-mismatch"],
)
def test_a_disagreement_withholds_every_instant_and_names_itself(
    storm: StormSummary | None, data: dict[str, str], reason: str
) -> None:
    product = arrivals.parse_arrival_kmz(product_kmz(kml(data=data)), provenance(), storm)

    assert product.withheld_reason is not None
    assert reason in product.withheld_reason
    assert all(line.valid_at is None for line in product.lines)


def test_an_unknown_zone_leaves_every_line_unresolved_with_its_reason() -> None:
    data = {"timezone": "XST", "pubAdvTime": "500 AM XST Mon Sep 02 2019"}

    product = arrivals.parse_arrival_kmz(product_kmz(kml(data=data)), provenance())

    assert product.published_at is None
    assert product.advisory.issued_at is None
    assert product.withheld_reason is not None
    assert "names a zone outside the table" in product.withheld_reason
    labelled = [line for line in product.lines if not line.is_outer_contour]
    assert [line.unresolved_reason for line in labelled] == [product.withheld_reason]


def test_an_out_of_horizon_or_unreadable_label_is_unresolved_with_its_reason() -> None:
    product = arrivals.parse_arrival_kmz(
        product_kmz(kml(labels=("Sat 8 am", "Soon", "Fri 8 am", OUTER))), provenance()
    )

    reasons = {line.label: line.unresolved_reason for line in product.lines}
    assert product.withheld_reason is None
    assert reasons["Sat 8 am"] == "label 'Sat 8 am' lies beyond the 120-hour horizon"
    assert reasons["Soon"] == "label 'Soon' does not parse"
    assert reasons["Fri 8 am"] is None
    assert product.lines[2].valid_at == at(6, 12)


def test_the_opengis_namespace_and_a_multi_geometry_parse() -> None:
    product = arrivals.parse_arrival_kmz(
        product_kmz(kml(namespace=OPENGIS_NAMESPACE, multi=True)), provenance()
    )

    assert [line.geometry.type for line in product.lines] == ["MultiLineString"] * 2
    assert product.lines[0].valid_at == at(2, 12)
    assert product.lines[0].geometry.crs.name == "EPSG:4326"


# Hardening --------------------------------------------------------------------------------


def test_a_member_compressed_more_than_a_hundred_to_one_is_refused() -> None:
    body = kmz(("doc.kml", kml()), ("labels/blank.png", bytes(MEBIBYTE)))

    with pytest.raises(SourceSchemaError, match="compressed more than 100 to 1"):
        arrivals.parse_arrival_kmz(body, provenance())


def test_more_than_sixty_four_members_are_refused() -> None:
    labels = [(f"labels/{index}.png", b"png") for index in range(arrivals.MAX_MEMBERS)]
    body = kmz(("doc.kml", kml()), *labels)

    with pytest.raises(SourceSchemaError, match="65 members, over the limit of 64"):
        arrivals.parse_arrival_kmz(body, provenance())


@pytest.mark.parametrize("name", ["../doc.kml", "labels/../../doc.kml", "/doc.kml", "C:/doc.kml"])
def test_an_absolute_or_parent_relative_member_name_is_refused(name: str) -> None:
    body = kmz((name, kml()))

    with pytest.raises(SourceSchemaError, match="absolute or parent-relative"):
        arrivals.parse_arrival_kmz(body, provenance())


def test_an_archive_over_eight_mebibytes_uncompressed_is_refused() -> None:
    filler = os.urandom(arrivals.MAX_UNCOMPRESSED_BYTES)  # incompressible: no ratio refusal
    body = kmz(("doc.kml", kml()), ("labels/big.png", filler), compression=zipfile.ZIP_STORED)

    with pytest.raises(SourceSchemaError, match="expands to"):
        arrivals.read_kml(body)


def test_a_kml_with_an_internal_entity_declaration_is_refused() -> None:
    prolog = '<!DOCTYPE kml [<!ENTITY zone "EDT">]>'
    body = kmz(("doc.kml", kml(prolog=prolog, data={"timezone": "&zone;"})))

    with pytest.raises(SourceSchemaError, match="declares a DTD or an entity"):
        arrivals.parse_arrival_kmz(body, provenance())


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"not a zip", "not a readable zip archive"),
        (kmz(("labels/am.png", b"png")), "0 KML members, not one"),
        (kmz(("a.kml", kml()), ("b.kml", kml())), "2 KML members, not one"),
        (kmz(("doc.kml", b"<kml")), "not well-formed XML"),
        (kmz(("doc.kml", b"<kml xmlns='urn:other'/>")), "not <kml> in a KML 2.2 namespace"),
        (kmz(("doc.kml", kml(labels=()))), "no arrival-time line"),
        (kmz(("doc.kml", kml(cells=2))), "2 table cells, not one"),
    ],
    ids=["not-zip", "no-kml", "two-kml", "malformed", "wrong-root", "no-lines", "two-cells"],
)
def test_a_malformed_archive_or_kml_is_a_schema_error(body: bytes, message: str) -> None:
    with pytest.raises(SourceSchemaError, match=message):
        arrivals.parse_arrival_kmz(body, provenance())


@pytest.mark.parametrize("field", sorted(arrivals.FIELDS_READ))
def test_a_missing_extended_data_key_is_a_schema_error_naming_it(field: str) -> None:
    body = kmz(("doc.kml", kml(data={"storm": "x"}).replace(f'name="{field}"'.encode(), b'n="x"')))

    with pytest.raises(SourceSchemaError, match=field):
        arrivals.parse_arrival_kmz(body, provenance())


@pytest.mark.parametrize(
    "url",
    [
        "http://www.nhc.noaa.gov/storm_graphics/api/AL052019_036adv_most_likely_toa_34.kmz",
        "https://nhc.noaa.gov.example/storm_graphics/api/AL052019_036adv_most_likely_toa_34.kmz",
        "https://www.nhc.noaa.gov/storm_graphics/api/AL052019_036adv_TRACK.kmz",
        "https://www.nhc.noaa.gov/storm_graphics/api/AL052019_036adv_most_likely_toa_50.kmz",
        "https://www.nhc.noaa.gov/storm_graphics/api/AL052019_036adv_most_likely_toa_34.kmz?x=1",
    ],
)
def test_a_url_outside_the_pattern_is_refused(url: str) -> None:
    with pytest.raises(SourceSchemaError, match="not fetched"):
        arrivals.check_url(url)
    with pytest.raises(SourceSchemaError, match="not fetched"):
        arrivals.parse_arrival_kmz(product_kmz(), provenance(url))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "link",
    [
        "https://example.org/AL052019_036adv_earliest_reasonable_toa_34.kmz",
        "https://www.nhc.noaa.gov/storm_graphics/api/AL062019_036adv_earliest_reasonable_toa_34.kmz",
        MOST_LIKELY_URL,
    ],
    ids=["other-host", "other-storm", "other-kind"],
)
async def test_a_roster_link_outside_the_pattern_is_never_fetched(link: str) -> None:
    storm = roster_storm()
    bad = storm.earliest_arrival_kmz
    assert bad is not None
    storm = storm.model_copy(update={"earliest_arrival_kmz": bad.model_copy(update={"url": link})})
    with respx.mock(assert_all_called=False) as router:
        route = router.route().mock(return_value=httpx.Response(200, content=product_kmz()))
        async with httpx.AsyncClient() as client:
            with pytest.raises(SourceSchemaError, match="not fetched"):
                await arrivals.fetch_arrival_times(Quiet().fetcher(client), [storm])
    assert not route.called


# Fetching and the snapshot rule -----------------------------------------------------------


@pytest.mark.anyio
async def test_fetch_reads_both_files_a_roster_storm_links() -> None:
    with respx.mock(assert_all_called=False) as router:
        serve(router, recorded("nhc-arrival-times"))
        async with httpx.AsyncClient() as client:
            result = await arrivals.fetch_arrival_times(Quiet().fetcher(client), [roster_storm()])

    assert [p.kind for p in result.records] == ["earliest_reasonable", "most_likely"]
    assert [r.url for r in result.responses] == [EARLIEST_URL, MOST_LIKELY_URL]
    assert all(p.withheld_reason is None for p in result.records)
    assert all(p.provenance.source_id == "nhc-arrival-times" for p in result.records)


@pytest.mark.anyio
async def test_no_storm_means_no_request() -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.route()
        async with httpx.AsyncClient() as client:
            result = await arrivals.fetch_arrival_times(Quiet().fetcher(client), [])
    assert result.records == ()
    assert not route.called


def _map_layer_twin(product: ArrivalTimeProduct, kind: str) -> ArrivalTimeProduct:
    return ArrivalTimeProduct.model_validate(
        {
            "atcf_id": product.atcf_id,
            "advisory": Advisory(
                atcf_id=product.atcf_id,
                number=product.advisory.number,
                issued_at=PUBLISHED,
                local_text=None,
                issued_at_source="roster",
            ),
            "provenance": product.provenance,
            "kind": kind,
            "time_zone": None,
            "published_at": None,
            "published_local_text": None,
            "origin": "map_layer",
            "lines": tuple(
                ArrivalTimeLine.resolve(line.label, line.geometry, origin="map_layer")
                for line in product.lines
            ),
        }
    )


def test_a_kmz_product_supersedes_the_map_layer_product_of_its_storm_advisory_and_kind() -> None:
    body, origin = archived(EARLIEST_URL)
    from_kmz = arrivals.parse_arrival_kmz(body, origin)
    same = _map_layer_twin(from_kmz, "earliest_reasonable")
    other_kind = _map_layer_twin(from_kmz, "most_likely")

    kept = arrivals.prefer_kmz([same, from_kmz, other_kind])

    assert kept == (from_kmz, other_kind)
    assert arrivals.prefer_kmz([same]) == (same,)
