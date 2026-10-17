# tests/contract/test_doctor_register.py
"""``doctor``'s copy of the register equals the register (``docs/DATA_SOURCES.md``).

The wheel does not carry the register, so ``weatherbot.services.register`` holds the
layer names ``doctor`` resolves; these tests keep the two equal.
"""

import re
import typing

import pytest
from fixture_support import register_layers, register_rows

from weatherbot.models import SourceId, StormSlot
from weatherbot.services.doctor import REGISTER_ORDER
from weatherbot.services.register import (
    MAP_LAYERS,
    NOT_PROBED,
    SHARED_HOST,
    SLOTS,
    SURGE_RISK_REGIONS,
)
from weatherbot.sources.arcgis import SERVICES

EN_DASH = chr(0x2013)  # the register writes a range with an en dash
CATEGORIES = re.compile(rf"Categories (\d){EN_DASH}(\d)")


@pytest.mark.parametrize("source", list(MAP_LAYERS))
def test_doctors_layer_names_are_the_registers(source: SourceId) -> None:
    registered = [layer.name for layer in register_layers(SERVICES[source].name)]

    assert list(MAP_LAYERS[source]) == registered


def test_the_surge_risk_categories_are_the_registers_notes() -> None:
    notes = {
        layer.name: range(int(found[1]), int(found[2]) + 1)
        for layer in register_layers(SERVICES["nhc-map-surge-risk"].name)
        if (found := CATEGORIES.search(layer.notes))
    }

    assert notes == dict(SURGE_RISK_REGIONS)


def test_the_slots_are_the_models_fifteen() -> None:
    assert typing.get_args(StormSlot.__value__) == SLOTS
    assert len(SLOTS) == 15  # noqa: PLR2004 - five per basin


def test_doctor_reports_every_register_source_once() -> None:
    registered = [row.source_id for row in register_rows()]

    assert list(REGISTER_ORDER) == registered
    assert set(NOT_PROBED) | set(SHARED_HOST) <= set(registered)
    assert set(NOT_PROBED).isdisjoint(SHARED_HOST)
