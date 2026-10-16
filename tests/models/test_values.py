# tests/models/test_values.py
"""Advisory numbers, coded values, outlook chances, wind bands, and source ids."""

import json
from enum import StrEnum
from typing import cast, get_args

import pytest
from model_samples import RECORDED, VOCABULARIES
from pydantic import ValidationError

import verify_phase01
from weatherbot.models import (
    WIND_PROBABILITY_BANDS,
    AdvisoryNumber,
    CodedValue,
    OutlookRisk,
    SourceId,
    StormClassification,
    WatchWarningType,
    WindProbabilityBand,
    parse_band_label,
    parse_percent,
)
from weatherbot.models.codes import StormClassificationCode, WatchWarningCode


@pytest.mark.parametrize("text", ["22A", "022a", "22a", "022A"])
def test_advisory_numbers_parse_every_spelling_of_an_intermediate(text: str) -> None:
    number = AdvisoryNumber.parse(text)

    assert (number.number, number.letter, str(number)) == (22, "A", "22A")
    assert number.is_intermediate


@pytest.mark.parametrize("text", ["22", "022", "0022"])
def test_advisory_numbers_parse_a_full_advisory(text: str) -> None:
    assert str(AdvisoryNumber.parse(text)) == "22"
    assert not AdvisoryNumber.parse(text).is_intermediate


@pytest.mark.parametrize("text", ["", "A", "0", "000", "22AB", "1000", "22-A", "-1"])
def test_malformed_advisory_numbers_are_rejected(text: str) -> None:
    with pytest.raises(ValueError, match="advisory number"):
        AdvisoryNumber.parse(text)


def test_advisory_numbers_are_ordered_as_nhc_issues_them() -> None:
    issued = [AdvisoryNumber.parse(t) for t in ("22", "22A", "22B", "23", "100")]

    shuffled = [issued[3], issued[1], issued[4], issued[0], issued[2]]

    assert sorted(shuffled) == issued
    assert AdvisoryNumber.parse("22") < AdvisoryNumber.parse("22A") < AdvisoryNumber.parse("23")
    assert AdvisoryNumber.parse("022a") == AdvisoryNumber.parse("22A")
    assert AdvisoryNumber.parse("22B") >= AdvisoryNumber.parse("22A")
    assert AdvisoryNumber.parse("22") <= AdvisoryNumber.parse("22")
    assert AdvisoryNumber.parse("23") > AdvisoryNumber.parse("22B")


def test_an_advisory_number_reads_from_json_text_or_parts() -> None:
    assert AdvisoryNumber.model_validate_json('"022a"') == AdvisoryNumber.parse("22A")
    assert AdvisoryNumber.model_validate_json('{"number": 22, "letter": "A"}') == AdvisoryNumber(
        number=22, letter="A"
    )


def test_the_recorded_roster_and_layers_spell_one_advisory_two_ways() -> None:
    roster = json.loads(
        (RECORDED / "nhc-current-storms/2026-10-12/CurrentStorms.json").read_text("utf-8")
    )
    spelled = roster["activeStorms"][0]["publicAdvisory"]["advNum"]

    assert spelled == "022a"
    assert AdvisoryNumber.parse(spelled) == AdvisoryNumber.parse("22A")


@pytest.mark.parametrize(("coded", "vocabulary"), VOCABULARIES, ids=lambda v: v.__name__)
def test_every_code_of_a_vocabulary_is_recognized(
    coded: type[CodedValue], vocabulary: type[StrEnum]
) -> None:
    for member in vocabulary:
        value = coded.parse(member.value)
        assert (value.raw, value.recognized, getattr(value, "code")) == (member.value, True, member)  # noqa: B009 - code is declared per subclass


@pytest.mark.parametrize(("coded", "vocabulary"), VOCABULARIES, ids=lambda v: v.__name__)
def test_an_unknown_code_keeps_its_raw_value(
    coded: type[CodedValue], vocabulary: type[StrEnum]
) -> None:
    value = coded.parse("XQZ-new")

    assert (value.raw, value.recognized, getattr(value, "code")) == ("XQZ-new", False, None)  # noqa: B009 - code is declared per subclass
    assert coded.model_validate_json(value.model_dump_json()) == value
    assert vocabulary


def test_the_spec_s_minimum_vocabularies_are_present() -> None:
    assert {"HWA", "HWR", "TWA", "TWR"} <= {m.value for m in WatchWarningCode}
    assert {"Low", "Medium", "High"} == {m.value for m in OutlookRisk.vocabulary}
    assert StormClassification.parse("HU").code is StormClassificationCode.HURRICANE


def test_recorded_tcww_codes_are_recognized() -> None:
    layer = RECORDED / "nhc-map-tropical-weather/2026-10-12/query-ep5-watch-warning.geojson"
    codes = {f["properties"]["tcww"] for f in json.loads(layer.read_text("utf-8"))["features"]}

    assert codes == {"HWA", "HWR"}
    assert all(WatchWarningType.parse(code).recognized for code in codes)


@pytest.mark.parametrize(
    "document",
    [
        '{"raw": "HU", "recognized": false, "code": null}',
        '{"raw": "HU", "recognized": true, "code": "TS"}',
        '{"raw": "XX", "recognized": true, "code": null}',
    ],
)
def test_a_coded_value_that_disagrees_with_its_raw_code_is_rejected(document: str) -> None:
    with pytest.raises(ValidationError, match="raw value"):
        StormClassification.model_validate_json(document)


def test_recorded_outlook_chances_and_risks_parse() -> None:
    layer = RECORDED / (
        "nhc-map-tropical-weather/2026-10-12/query-seven-day-potential-development-region.geojson"
    )
    features = json.loads(layer.read_text("utf-8"))["features"]

    parsed = {
        (
            parse_percent(f["properties"]["prob2day"]),
            OutlookRisk.parse(f["properties"]["risk2day"]).recognized,
        )
        for f in features
    }

    assert parsed == {(20, True), (100, True)}


@pytest.mark.parametrize("text", ["20", "101%", "-5%", "5.5%", "high"])
def test_a_malformed_chance_is_an_error(text: str) -> None:
    with pytest.raises(ValueError, match="percentage"):
        parse_percent(text)


def recorded_band_labels() -> set[str]:
    labels: set[str] = set()
    for service in ("nhc-map-tropical-weather", "nhc-map-tropical-summary"):
        for threshold in (34, 50, 64):
            path = (
                RECORDED
                / service
                / "2026-10-12"
                / f"query-probabilistic-winds-{threshold}-kts.geojson"
            )
            features = json.loads(path.read_text("utf-8"))["features"]
            labels |= {f["properties"]["percentage"] for f in features}
    return labels


def test_every_recorded_band_label_parses() -> None:
    labels = recorded_band_labels()

    assert labels == set(WIND_PROBABILITY_BANDS)
    assert parse_band_label("<5%") == (0, 5)
    assert parse_band_label("5-10%") == (5, 10)
    assert parse_band_label(">90%") == (90, 100)


def test_only_the_top_band_includes_its_upper_bound() -> None:
    from model_samples import landmark_square  # noqa: PLC0415 - one helper for one test

    bands = [
        WindProbabilityBand.from_label(label, landmark_square()) for label in WIND_PROBABILITY_BANDS
    ]

    assert [band.upper_inclusive for band in bands] == [False] * 10 + [True]
    edges = [(band.lower_pct, band.upper_pct) for band in bands]
    assert all(edges[i][1] == edges[i + 1][0] for i in range(len(edges) - 1))


@pytest.mark.parametrize("label", ["0-5%", "90-100%", "5 - 10%", "<5", ""])
def test_an_unknown_band_label_is_a_schema_error(label: str) -> None:
    from model_samples import landmark_square  # noqa: PLC0415 - one helper for one test

    with pytest.raises(ValueError, match="band"):
        WindProbabilityBand.from_label(label, landmark_square())
    document = json.loads(
        WindProbabilityBand.from_label("5-10%", landmark_square()).model_dump_json()
    )
    document["label"] = label
    with pytest.raises(ValidationError):
        WindProbabilityBand.model_validate_json(json.dumps(document))


def test_the_source_id_literal_equals_the_register() -> None:
    register = [row[0] for row in verify_phase01.register_rows()]

    assert list(cast("tuple[str, ...]", get_args(SourceId.__value__))) == register
