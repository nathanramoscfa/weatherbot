# tests/services/test_notification_goldens.py
"""The two operator-approved Irma notification goldens bind ``replay_notifications``."""

from copy import deepcopy
from datetime import date
from functools import cache

import pytest

import build_notification_goldens
from ladder_data import public_landmarks
from weatherbot.models import Thresholds

NAMES = tuple(
    f"{build_notification_goldens.IRMA_ATCF_ID}-{landmark}.json" for landmark in public_landmarks()
)


@cache
def current_notification_goldens() -> dict[str, dict[str, object]]:
    """Run both Irma notification timelines once for the frozen-reference checks."""
    return build_notification_goldens.candidates()


@pytest.mark.parametrize("name", NAMES)
def test_every_notification_timeline_equals_its_golden(name: str) -> None:
    expected = build_notification_goldens.read_document(
        build_notification_goldens.NOTIFICATION_GOLDENS / name
    )
    actual = current_notification_goldens()[name]
    assert {k: v for k, v in expected.items() if k != "approval"} == {
        k: v for k, v in actual.items() if k != "approval"
    }, name
    assert expected["ruleset"] == Thresholds().fingerprint(), name


@pytest.mark.parametrize("name", NAMES)
def test_every_notification_golden_has_an_operator_approval(name: str) -> None:
    assert build_notification_goldens.approved(
        build_notification_goldens.read_document(
            build_notification_goldens.NOTIFICATION_GOLDENS / name
        )
    ), name


def test_notification_golden_check_is_read_only_and_requires_all_approvals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_notification_goldens, "candidates", current_notification_goldens)
    assert build_notification_goldens.main(["--check"]) == 0


def test_an_edited_notification_golden_cannot_retain_its_approval() -> None:
    candidate: dict[str, object] = {
        "timelines": {"defaults": [{"level": 2}], "strict": []},
        "ruleset": "before",
        "approval": None,
    }
    frozen = build_notification_goldens.retain_approval(candidate, None, date(2000, 1, 1))
    assert build_notification_goldens.approved(frozen)
    assert build_notification_goldens.retain_approval(candidate, frozen, None) == frozen
    for key, value in (
        ("timelines", {"defaults": [{"level": 3}], "strict": []}),
        ("ruleset", "after"),
    ):
        edited = deepcopy(candidate) | {key: value}
        with pytest.raises(ValueError, match="new operator approval"):
            build_notification_goldens.retain_approval(edited, frozen, None)
    assert not build_notification_goldens.approved(
        frozen | {"timelines": {"defaults": [{"level": 3}], "strict": []}}
    )
