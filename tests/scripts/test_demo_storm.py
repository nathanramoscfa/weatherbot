# tests/scripts/test_demo_storm.py
"""``scripts/demo_storm.py``: each stage's answers parse through the real parsers, unchanged."""

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from source_support import NOW

import demo_storm
from weatherbot.models import SourceId, StormProducts, StormSummary
from weatherbot.services.logs import collect_drift
from weatherbot.sources import nhc_arrival_times, nhc_current_storms, nhc_map, nhc_text_products
from weatherbot.sources.http import FetchResult

SUMMARY: SourceId = "nhc-map-tropical-summary"
TEST_STORM_NUMBERS = range(80, 90)
"""ATCF reserves storm numbers 80 to 89 for test storms."""


def _result(source: SourceId, url: str, answer: demo_storm.StagedAnswer) -> FetchResult:
    return FetchResult(
        source_id=source,
        url=url,
        status=answer.status,
        body=answer.body,
        headers={"content-type": answer.content_type},
        fetched_at=NOW,
        sha256=hashlib.sha256(answer.body).hexdigest(),
    )


def _roster(answers: dict[str, demo_storm.StagedAnswer]) -> tuple[StormSummary, ...]:
    result = _result("nhc-current-storms", demo_storm.ROSTER_URL, answers[demo_storm.ROSTER_URL])
    return nhc_current_storms.parse_current_storms(result.body, result.provenance())


def _products(
    answers: dict[str, demo_storm.StagedAnswer], storms: tuple[StormSummary, ...]
) -> StormProducts:
    urls = demo_storm.summary_layer_urls()
    records: list[object] = []
    for name in nhc_map.STORM_LAYERS:
        result = _result(SUMMARY, urls[name], answers[urls[name]])
        records.extend(
            nhc_map.parse_layer(name, json.loads(result.body), result.provenance(), storms)
        )
    for name in nhc_map.STORM_DISPLAY_LAYERS:
        result = _result(SUMMARY, urls[name], answers[urls[name]])
        assert nhc_map.parse_layer(name, json.loads(result.body), result.provenance())
    (products,) = nhc_map.assemble_storm_products(storms, records)  # pyright: ignore[reportArgumentType] - parsed records
    return products


@pytest.mark.parametrize("stage", demo_storm.STAGE_NAMES)
def test_each_stage_parses_through_the_real_parsers_without_drift(
    stage: demo_storm.StageName,
) -> None:
    answers = demo_storm.stage_answers(stage)
    urls = demo_storm.summary_layer_urls()
    advisory = demo_storm.STAGES[stage].advisory

    with collect_drift() as drift:
        storms = _roster(answers)
        products = _products(answers, storms)
        winds = [
            nhc_map.parse_wind_probabilities(
                name,
                json.loads(answers[urls[name]].body),
                _result(SUMMARY, urls[name], answers[urls[name]]).provenance(),
            )
            for name in demo_storm.WIND_LAYERS.values()
        ]
        nhc_map.check_wind_probability_issuance([w for w in winds if w is not None], storms)
        kmz = [
            nhc_arrival_times.parse_arrival_kmz(
                answers[url].body,
                _result("nhc-arrival-times", url, answers[url]).provenance(),
                storms[0],
            )
            for url in (
                demo_storm.kmz_url(demo_storm.STAGES[stage], kind)
                for kind in demo_storm.ARRIVAL_KINDS
            )
        ]
        listing = answers[demo_storm.tcp_list_url()]
        identifier = nhc_text_products.newest_product_id(listing.body, "nhc-text-products", "list")
        product_url = f"{demo_storm.API_ROOT}/products/{identifier}"
        tcp = nhc_text_products.parse_text_product(
            answers[product_url].body,
            _result("nhc-text-products", product_url, answers[product_url]).provenance(),
            code="TCP",
            location=demo_storm.SLOT,
        )
        attributed = nhc_text_products.attribute_tcp(tcp, storms[0])

    assert list(drift.warnings) == []
    (storm,) = storms
    assert (storm.atcf_id, storm.slot, storm.name) == (demo_storm.ATCF_ID, "AT1", "Demo")
    assert products.cone is not None
    assert products.track is not None
    assert len(products.track_points) == len(demo_storm.TAUS)
    assert products.wind_radii
    assert {product.kind for product in products.arrival_times} == set(demo_storm.ARRIVAL_KINDS)
    assert [int(w.threshold_kt) for w in winds if w is not None] == [34, 50, 64]
    assert all(product.withheld_reason is None for product in kmz)
    assert all(line.valid_at or line.is_outer_contour for product in kmz for line in product.lines)
    assert attributed is not None
    assert tcp.advisory is not None
    assert tcp.advisory.number == advisory
    codes = [segment.tcww.raw for segment in products.watch_warnings]
    assert codes == [code for code, _ in demo_storm.STAGES[stage].segments]


def test_the_storm_is_a_test_storm_with_a_demonstration_name() -> None:
    assert demo_storm.ATCF_ID.startswith("AL")
    assert int(demo_storm.ATCF_ID[2:4]) in TEST_STORM_NUMBERS
    assert demo_storm.NAME == "Demo"
    assert int(demo_storm.ATCF_ID[2:4]) == demo_storm.STORM_NUMBER


@pytest.mark.parametrize("stage", demo_storm.STAGE_NAMES)
def test_every_coordinate_has_at_most_two_decimals_and_every_answer_says_synthetic(
    stage: demo_storm.StageName,
) -> None:
    answers = demo_storm.stage_answers(stage)

    positions = demo_storm.synthetic_positions(answers)
    assert positions
    assert max(demo_storm.decimals(value) for value in positions) <= 2  # noqa: PLR2004 - R2's bound

    for url, answer in answers.items():
        if answer.content_type == demo_storm.KMZ_TYPE:
            with zipfile.ZipFile(io.BytesIO(answer.body)) as archive:
                kml = archive.read(archive.namelist()[0]).decode("utf-8")
            assert '<Data name="synthetic"><value>true</value></Data>' in kml, url
            assert "(synthetic demonstration)" in kml, url
            continue
        document = json.loads(answer.body)
        if "features" in document:
            for feature in document["features"]:
                assert feature["properties"]["synthetic"] is True, url
                assert feature["properties"]["snippet"] == demo_storm.SYNTHETIC_NOTE, url
        elif "activeStorms" in document:
            assert all(storm["synthetic"] is True for storm in document["activeStorms"])
        elif "@graph" in document:
            assert all(item["synthetic"] is True for item in document["@graph"])
        else:
            assert document["synthetic"] is True, url
            assert "SYNTHETIC DEMONSTRATION" in document["productText"]


def test_a_stage_shown_later_moves_its_times_and_keeps_its_geometry() -> None:
    shown = datetime(2026, 10, 12, 21, tzinfo=UTC)
    history = demo_storm.stage_answers("cone")
    later = demo_storm.stage_answers("cone", shown)

    assert demo_storm.HISTORY_ISSUED_AT["cone"] + timedelta(hours=30) == shown
    early, moved = _roster(history)[0], _roster(later)[0]
    assert moved.public_advisory.issued_at == shown
    assert early.public_advisory.issued_at == demo_storm.HISTORY_ISSUED_AT["cone"]
    assert (moved.latitude, moved.longitude) == (early.latitude, early.longitude)
    urls = demo_storm.summary_layer_urls()
    cone = urls[demo_storm.FORECAST_CONE]
    assert (
        json.loads(history[cone].body)["features"][0]["geometry"]
        == json.loads(later[cone].body)["features"][0]["geometry"]
    )


def test_an_empty_roster_and_no_cone_attributes_without_a_storm() -> None:
    assert demo_storm.roster_document(None) == {"activeStorms": []}
    assert demo_storm.cone_advisory_attributes(None) == {"features": []}
    rows = demo_storm.cone_advisory_attributes("landfall")["features"]
    assert rows == [{"attributes": {"binnumber": "AT1", "advisnum": "8", "synthetic": True}}]
