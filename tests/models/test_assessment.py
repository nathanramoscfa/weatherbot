# tests/models/test_assessment.py
"""The assessment models' own rules: citations, evidence, official products, readings, spans."""

import pytest
from model_samples import (
    assessment,
    breakpoint_span,
    evidence,
    location_wind_probability,
    official_product,
    provenance,
    unavailable_input,
)
from pydantic import ValidationError

from weatherbot.models import (
    LOCATED_SOURCES,
    RULE_LEVELS,
    AlertLevel,
    Assessment,
    BreakpointSpan,
    Citation,
    DomainModel,
    Evidence,
    LocationWindProbability,
    OfficialProduct,
    RuleId,
    SourceId,
)


def revalidate[M: DomainModel](model: M, **changes: object) -> M:
    fields = {name: getattr(model, name) for name in type(model).model_fields}
    return type(model).model_validate(fields | changes)


# Citations ---------------------------------------------------------------------------------


@pytest.mark.parametrize("source", sorted(LOCATED_SOURCES))
def test_a_citation_drops_the_url_of_a_source_that_carries_a_location(source: SourceId) -> None:
    record = provenance(source)

    cited = Citation.of(record)

    assert cited.url is None
    assert (cited.source_id, cited.sha256, cited.fetched_at) == (
        source,
        record.sha256,
        record.fetched_at,
    )


def test_a_citation_keeps_the_url_of_any_other_source() -> None:
    record = provenance("nws-alerts-zone")

    assert Citation.of(record).url == record.url


def test_a_citation_refuses_a_located_url() -> None:
    record = provenance("nws-alerts-point")

    with pytest.raises(ValidationError, match="carry a location"):
        revalidate(Citation.of(record), url=record.url)


# Evidence and products ---------------------------------------------------------------------


def test_only_the_toggle_is_tested_as_a_toggle_and_cites_nothing() -> None:
    toggle = Evidence(
        rule=RuleId.EVACUATION_ORDER, product="evacuation_toggle", test="toggle", detail="On."
    )

    assert toggle.source_id is None
    assert evidence().source_id == "nhc-map-tropical-weather"
    with pytest.raises(ValidationError, match="only the toggle"):
        revalidate(toggle, citation=evidence().citation)
    with pytest.raises(ValidationError, match="only the toggle"):
        revalidate(evidence(), citation=None)
    with pytest.raises(ValidationError, match="only the toggle"):
        revalidate(evidence(), test="toggle")


def test_only_a_covering_product_triggers_a_rule() -> None:
    with pytest.raises(ValidationError, match="only a covering product"):
        revalidate(official_product(), covers=False, rule=RuleId.HURRICANE_WARNING)


def test_an_alert_names_its_id_and_a_segment_its_storm() -> None:
    with pytest.raises(ValidationError, match="an alert names its id"):
        revalidate(official_product(), alert_id=None)
    with pytest.raises(ValidationError, match="an alert names its id"):
        revalidate(official_product(), atcf_id="EP202026")
    with pytest.raises(ValidationError, match="an alert names its id"):
        revalidate(official_product(), kind="watch_warning_segment")
    assert isinstance(
        revalidate(
            official_product(), kind="watch_warning_segment", alert_id=None, atcf_id="EP202026"
        ),
        OfficialProduct,
    )


def test_a_band_reading_names_its_band_and_no_other_reading_does() -> None:
    below = revalidate(
        location_wind_probability(),
        reading="below_every_band",
        label=None,
        lower_pct=None,
        upper_pct=None,
    )

    assert isinstance(below, LocationWindProbability)
    with pytest.raises(ValidationError, match="names its band"):
        revalidate(location_wind_probability(), label=None)
    with pytest.raises(ValidationError, match="names its band"):
        revalidate(below, label="5-10%")


@pytest.mark.parametrize(
    ("names", "region"),
    [((), False), (("A", "B", "C"), False), (("A", "B"), True)],
    ids=["none", "three", "two-region"],
)
def test_a_span_names_one_or_two_breakpoints_and_a_region_one(
    names: tuple[str, ...], *, region: bool
) -> None:
    with pytest.raises(ValidationError):
        revalidate(breakpoint_span(), names=names, is_region=region)


def test_a_span_without_its_load_date_is_kept() -> None:
    span = BreakpointSpan(names=("A",), country="Testland", is_region=True)

    assert span.catalog_loaded_at is None


# The assessment ----------------------------------------------------------------------------


def test_an_assessments_level_is_its_rules_level() -> None:
    with pytest.raises(ValidationError, match="the deciding rule's level"):
        revalidate(assessment(), level=AlertLevel.ALL_CLEAR)
    assert assessment().level == RULE_LEVELS[assessment().rule]


def test_the_evidence_is_the_deciding_rules_and_all_clear_has_none() -> None:
    other = revalidate(evidence(), rule=RuleId.HURRICANE_WATCH)

    with pytest.raises(ValidationError, match="all_clear has none"):
        revalidate(assessment(), evidence=(other,))
    with pytest.raises(ValidationError, match="all_clear has none"):
        revalidate(assessment(), evidence=())
    with pytest.raises(ValidationError, match="all_clear has none"):
        revalidate(assessment(), rule=RuleId.ALL_CLEAR, level=AlertLevel.ALL_CLEAR)


def test_an_assessment_is_complete_exactly_when_nothing_was_unavailable() -> None:
    complete = revalidate(assessment(), unavailable=(), complete=True)

    assert isinstance(complete, Assessment)
    with pytest.raises(ValidationError, match="complete exactly when"):
        revalidate(assessment(), complete=True)
    with pytest.raises(ValidationError, match="complete exactly when"):
        revalidate(complete, complete=False)
    assert unavailable_input().kind == "nws_alerts"


def test_an_assessment_round_trips_its_level_as_a_number() -> None:
    document = assessment().model_dump(mode="json")

    assert document["level"] == AlertLevel.HURRICANE_WARNING.value
    assert Assessment.model_validate_json(assessment().model_dump_json()) == assessment()
