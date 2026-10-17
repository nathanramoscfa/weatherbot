# tests/sources/test_nhc_text_products.py
"""Tests of the TCP and TWO client over the recorded NWS API captures."""

import json
import logging
from datetime import UTC, datetime

import httpx
import pytest
import respx
from source_support import Quiet, entry, recorded, recorded_result, recorded_storms, serve

from weatherbot.models import AdvisoryNumber, Provenance, StormSummary, TextProduct
from weatherbot.sources import nhc_text_products as text_products
from weatherbot.sources.drift import DRIFT_ATTRIBUTE
from weatherbot.sources.errors import SourceSchemaError

API_HOST_INTERVAL = 1.2
TWO_COUNT = 3


def recorded_product(name: str) -> tuple[bytes, Provenance]:
    directory = recorded("nhc-text-products")
    result = recorded_result(directory, entry(directory, name))
    return result.body, result.provenance()


def tcp() -> TextProduct:
    body, provenance = recorded_product("tcp-ep5-product.json")
    return text_products.parse_text_product(body, provenance, code="TCP", location="EP5")


def edited_tcp(old: str, new: str) -> tuple[bytes, Provenance]:
    body, provenance = recorded_product("tcp-ep5-product.json")
    document = json.loads(body)
    assert old in document["productText"]
    document["productText"] = document["productText"].replace(old, new)
    return json.dumps(document).encode(), provenance


def drift_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if hasattr(r, DRIFT_ATTRIBUTE)]


def test_the_recorded_tcp_names_its_storm_advisory_and_issuance() -> None:
    product = tcp()

    assert (product.code, product.location) == ("TCP", "EP5")
    assert product.atcf_id == "EP202026"
    assert product.advisory == AdvisoryNumber.parse("22A")
    assert product.issued_at == datetime(2026, 10, 12, 23, 33, tzinfo=UTC)
    assert (product.wmo_collective_id, product.issuing_office) == ("WTPZ35", "KNHC")
    assert product.text.startswith("\n000\nWTPZ35 KNHC 122333")


@pytest.mark.parametrize("basin", text_products.TWO_BASINS)
def test_every_recorded_two_parses_without_a_storm(basin: str) -> None:
    body, provenance = recorded_product(f"two-{basin.lower()}-product.json")

    product = text_products.parse_text_product(body, provenance, code="TWO", location=basin)

    assert (product.atcf_id, product.advisory) == (None, None)
    assert product.issued_at.tzinfo == UTC


@pytest.mark.parametrize(
    ("line", "number"),
    [
        ("Hurricane Simon Advisory Number 23", "23"),
        ("Hurricane Simon INTERMEDIATE ADVISORY NUMBER 22B", "22B"),
        ("Tropical Storm Simon Special Advisory Number 7", "7"),
    ],
)
def test_the_advisory_number_comes_from_the_text(line: str, number: str) -> None:
    body, provenance = edited_tcp("Hurricane Simon Intermediate Advisory Number 22A", line)

    product = text_products.parse_text_product(body, provenance, code="TCP", location="EP5")

    assert product.advisory == AdvisoryNumber.parse(number)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("EP202026", ""),
        ("Intermediate Advisory Number 22A", "Update"),
    ],
    ids=["no-atcf-id", "no-advisory"],
)
def test_a_tcp_without_its_storm_or_advisory_is_a_schema_error(old: str, new: str) -> None:
    body, provenance = edited_tcp(old, new)

    with pytest.raises(SourceSchemaError, match="names no ATCF id or advisory number"):
        text_products.parse_text_product(body, provenance, code="TCP", location="EP5")


def test_a_wmo_line_that_disagrees_with_issuance_time_is_drift(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body, provenance = edited_tcp("WTPZ35 KNHC 122333", "WTPZ35 KNHC 122051")

    with caplog.at_level(logging.WARNING, "weatherbot.sources"):
        text_products.parse_text_product(body, provenance, code="TCP", location="EP5")

    assert any("WMO line" in message for message in drift_messages(caplog))


def test_the_newest_product_id_is_the_latest_issuance() -> None:
    body, _ = recorded_product("tcp-ep5-list.json")
    graph = json.loads(body)["@graph"]
    newest = max(graph, key=lambda item: datetime.fromisoformat(item["issuanceTime"]))

    found = text_products.newest_product_id(body, "nhc-text-products", "the list")

    assert found == newest["id"]


@pytest.mark.parametrize(
    ("graph", "expected"),
    [
        ([], None),
        ([{"id": "../etc", "issuanceTime": "2026-10-12T20:51:00+00:00"}], "unexpected id"),
        ([{"id": "abcdefgh-1234"}], "issuanceTime"),
    ],
    ids=["empty", "bad-id", "missing-time"],
)
def test_a_list_is_read_strictly(graph: list[dict[str, str]], expected: str | None) -> None:
    body = json.dumps({"@graph": graph}).encode()
    if expected is None:
        assert text_products.newest_product_id(body, "nhc-text-products", "the list") is None
        return
    with pytest.raises(SourceSchemaError, match=expected):
        text_products.newest_product_id(body, "nhc-text-products", "the list")


def _storm_with(storm: StormSummary, **changes: object) -> StormSummary:
    return storm.model_copy(update=changes)


def test_a_reused_slot_tcp_is_not_attributed_and_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    (storm,) = recorded_storms()
    later = _storm_with(storm, atcf_id="EP212026", name="Trudy")

    with caplog.at_level(logging.WARNING, "weatherbot.sources"):
        assert text_products.attribute_tcp(tcp(), later) is None

    assert any("not attributed" in message for message in drift_messages(caplog))


def test_an_older_tcp_keeps_its_own_advisory_number(caplog: pytest.LogCaptureFixture) -> None:
    (storm,) = recorded_storms()
    roster_ahead = _storm_with(
        storm,
        public_advisory=storm.public_advisory.model_copy(
            update={"advisory": AdvisoryNumber.parse("23")}
        ),
    )

    with caplog.at_level(logging.WARNING, "weatherbot.sources"):
        product = text_products.attribute_tcp(tcp(), roster_ahead)

    assert product is not None
    assert product.advisory == AdvisoryNumber.parse("22A")
    assert any("keeps its own number" in message for message in drift_messages(caplog))


def test_a_tcp_matching_the_roster_is_attributed_quietly(caplog: pytest.LogCaptureFixture) -> None:
    (storm,) = recorded_storms()

    with caplog.at_level(logging.WARNING, "weatherbot.sources"):
        assert text_products.attribute_tcp(tcp(), storm) == tcp()

    assert drift_messages(caplog) == []


@pytest.mark.anyio
async def test_fetch_tcps_lists_the_slot_and_reads_the_newest_product() -> None:
    quiet = Quiet()
    with respx.mock(assert_all_called=False) as router:
        serve(router, recorded("nhc-text-products"))
        async with httpx.AsyncClient() as client:
            result = await text_products.fetch_tcps(quiet.fetcher(client), recorded_storms())

    (product,) = result.records
    assert product.atcf_id == "EP202026"
    assert [r.url for r in result.responses] == [
        text_products.list_url("TCP", "EP5"),
        f"{text_products.API_ROOT}/products/{product.product_id}",
    ]


@pytest.mark.anyio
async def test_fetch_tcps_leaves_out_a_reused_slots_product() -> None:
    (storm,) = recorded_storms()
    with respx.mock(assert_all_called=False) as router:
        serve(router, recorded("nhc-text-products"))
        async with httpx.AsyncClient() as client:
            result = await text_products.fetch_tcps(
                Quiet().fetcher(client), [_storm_with(storm, atcf_id="EP212026")]
            )

    assert result.records == ()
    assert len(result.responses) == len(("list", "product"))


@pytest.mark.anyio
async def test_fetch_twos_reads_the_english_basins_paced_as_api_weather_gov() -> None:
    quiet = Quiet()
    with respx.mock(assert_all_called=False) as router:
        serve(router, recorded("nhc-text-products"))
        async with httpx.AsyncClient() as client:
            result = await text_products.fetch_twos(quiet.fetcher(client))

    assert [p.location for p in result.records] == list(text_products.TWO_BASINS)
    assert len(result.records) == TWO_COUNT
    requested = [response.url for response in result.responses]
    assert not any("/locations/S" in url for url in requested), "a Spanish edition was asked for"
    # Six requests to one host: five waits of the API's interval on the pacer's clock.
    assert quiet.clock.sleeps == pytest.approx([API_HOST_INTERVAL] * (len(requested) - 1))
