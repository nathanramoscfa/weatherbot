# tests/models/test_conventions.py
"""Conventions every public model keeps: frozen, strict, closed, round-tripping, schema'd."""

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from model_samples import FETCHED_AT, SAMPLES, provenance
from pydantic import ValidationError

from weatherbot import models
from weatherbot.models import CodedValue, DomainModel, Provenance

ABSTRACT: set[type[DomainModel]] = {DomainModel, CodedValue}


def public_models() -> list[type[DomainModel]]:
    found: list[type[DomainModel]] = []
    for name in models.__all__:
        value: object = getattr(models, name)
        if isinstance(value, type) and issubclass(value, DomainModel):
            found.append(value)
    return sorted(found, key=lambda cls: cls.__name__)


PUBLIC_MODELS = public_models()
CONCRETE = [cls for cls in PUBLIC_MODELS if cls not in ABSTRACT]


def ids(cls: type[DomainModel]) -> str:
    return cls.__name__


def test_every_public_name_is_exported_and_importable() -> None:
    assert len(set(models.__all__)) == len(models.__all__)
    assert all(hasattr(models, name) for name in models.__all__)


def test_the_overview_s_models_are_public() -> None:
    names = {
        "Provenance", "Location", "StormSummary", "Advisory", "AdvisoryNumber", "ConeGeometry",
        "TrackPoint", "ForecastTrack", "WatchWarningSegment", "WindRadii",
        "ArrivalTimeProduct", "ArrivalTimeLine", "OutlookArea", "WindProbabilityProduct",
        "WindProbabilityBand", "NwsAlert", "AlertQuery", "NwsZone", "GeocodeResult",
        "Breakpoint", "TextProduct", "GisFeedItem", "OutlookGraphic", "MapCatalog",
        "OverlayCatalog", "DisplayLayer", "Snapshot", "SourceOutcome", "Geometry",
        "NwsCoverage", "SourceId", "parse_nhc_local_time", "resolve_track_valid_time",
        "parse_synoptic_time", "from_epoch_ms", "resolve_arrival_label",
    }  # fmt: skip
    assert names <= set(models.__all__)


def test_every_concrete_public_model_has_a_sample() -> None:
    assert set(CONCRETE) == set(SAMPLES)


@pytest.mark.parametrize("cls", PUBLIC_MODELS, ids=ids)
def test_every_model_is_frozen_strict_and_closed(cls: type[DomainModel]) -> None:
    config = cls.model_config
    assert (config.get("frozen"), config.get("strict"), config.get("extra")) == (
        True,
        True,
        "forbid",
    )
    assert config.get("hide_input_in_errors") is True


@pytest.mark.parametrize("cls", CONCRETE, ids=ids)
def test_every_model_constructs_from_minimal_data(cls: type[DomainModel]) -> None:
    assert isinstance(SAMPLES[cls](), cls)


@pytest.mark.parametrize("cls", CONCRETE, ids=ids)
def test_every_model_round_trips_through_json(cls: type[DomainModel]) -> None:
    model = SAMPLES[cls]()

    assert cls.model_validate_json(model.model_dump_json()) == model


@pytest.mark.parametrize("cls", PUBLIC_MODELS, ids=ids)
def test_every_model_produces_a_json_schema(cls: type[DomainModel]) -> None:
    schema = cls.model_json_schema()

    assert schema["type"] == "object"
    json.dumps(schema)


@pytest.mark.parametrize("cls", CONCRETE, ids=ids)
def test_every_model_rejects_an_unknown_field(cls: type[DomainModel]) -> None:
    document = json.loads(SAMPLES[cls]().model_dump_json())
    document["unexpected"] = 1

    with pytest.raises(ValidationError) as error:
        cls.model_validate_json(json.dumps(document))
    assert "extra_forbidden" in {item["type"] for item in error.value.errors()}


@pytest.mark.parametrize("cls", CONCRETE, ids=ids)
def test_every_model_rejects_mutation(cls: type[DomainModel]) -> None:
    model = SAMPLES[cls]()
    field = next(iter(cls.model_fields))

    with pytest.raises(ValidationError) as error:
        setattr(model, field, getattr(model, field))
    assert error.value.errors()[0]["type"] == "frozen_instance"


def test_strict_json_accepts_iso_8601_instants_and_normalizes_them_to_utc() -> None:
    document = json.loads(provenance().model_dump_json())
    document["fetched_at"] = "2026-10-12T21:08:56-04:00"

    parsed = Provenance.model_validate_json(json.dumps(document))

    assert parsed.fetched_at == datetime(2026, 10, 13, 1, 8, 56, tzinfo=UTC)
    assert parsed.fetched_at.tzinfo is UTC


@pytest.mark.parametrize("text", ["2026-10-12T21:08:56", "2026-10-12 21:08"])
def test_a_naive_iso_instant_is_rejected(text: str) -> None:
    document = json.loads(provenance().model_dump_json())
    document["fetched_at"] = text

    with pytest.raises(ValidationError):
        Provenance.model_validate_json(json.dumps(document))


def test_a_naive_datetime_is_rejected_in_python() -> None:
    with pytest.raises(ValidationError):
        provenance().model_copy(update={}).model_validate(
            {**dict(provenance()), "fetched_at": FETCHED_AT.replace(tzinfo=None)}
        )


def test_an_aware_datetime_in_another_zone_is_stored_in_utc() -> None:
    eastern = FETCHED_AT.astimezone(timezone(timedelta(hours=-4)))

    stored = Provenance.model_validate({**dict(provenance()), "fetched_at": eastern})

    assert stored.fetched_at == FETCHED_AT
    assert stored.fetched_at.tzinfo is UTC


def test_strict_python_input_refuses_coercion() -> None:
    with pytest.raises(ValidationError):
        Provenance.model_validate({**dict(provenance()), "status": "200"})
