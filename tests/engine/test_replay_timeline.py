# tests/engine/test_replay_timeline.py
"""The replay service preserves advisory order, assessment settings, and change events."""

import pytest
from engine_support import IRMA, REPLAY, landmark_location

from weatherbot.models import AlertLevel, Thresholds
from weatherbot.services.replay import ReplayCorpus, ReplayError, ReplayService


def test_irma_timeline_has_initial_events_and_the_recorded_cone_transitions() -> None:
    corpus = ReplayCorpus.open(REPLAY)
    storm = next(item for item in corpus.storms() if item.atcf_id == IRMA)
    thresholds = Thresholds()

    timeline = ReplayService(corpus).timeline(IRMA, landmark_location(), thresholds)

    assert len(timeline) == storm.advisories
    instants = [step.assessment.as_of for step in timeline]
    assert instants == sorted(set(instants))
    assert (instants[0], instants[-1]) == (storm.first_issued_at, storm.last_issued_at)
    assert all(step.assessment.origin == "replay" for step in timeline)
    assert all(step.assessment.thresholds == thresholds for step in timeline)
    assert all(step.assessment.ruleset == thresholds.fingerprint() for step in timeline)
    initial = timeline[0].changes[0]
    assert (initial.kind, initial.direction, initial.previous_level) == (
        "level_changed",
        "initial",
        None,
    )
    events = [event for step in timeline for event in step.changes]
    assert sum(event.kind == "advisory_issued" for event in events) == storm.advisories
    assert [
        (event.kind, str(event.advisory)) for event in events if event.kind.startswith("cone")
    ] == [
        ("cone_entered", "22"),
        ("cone_left", "40"),
    ]


def test_timeline_uses_the_supplied_location_and_thresholds_without_state() -> None:
    service = ReplayService(ReplayCorpus.open(REPLAY))
    location = landmark_location("nassau", evacuation=True)
    thresholds = Thresholds(cone_horizon_h=96, hurricane_wind_floor_pct=20)

    timeline = service.timeline(IRMA, location, thresholds)

    assert all(step.assessment.location_name == location.name for step in timeline)
    assert all(step.assessment.level >= AlertLevel.WARNING_WATCH_EVACUATION for step in timeline)
    assert all(step.assessment.thresholds == thresholds for step in timeline)
    assert service.timeline(IRMA, location, thresholds) == timeline


def test_timeline_preserves_the_corpus_refusal_of_an_unknown_storm() -> None:
    service = ReplayService(ReplayCorpus.open(REPLAY))

    with pytest.raises(ReplayError, match="lists no storm"):
        service.timeline("AL002000", landmark_location(), Thresholds())
