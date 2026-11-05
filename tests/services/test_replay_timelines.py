# tests/services/test_replay_timelines.py
"""Tests for ``ReplayTimelines`` single-flight LRU caching and ``replay_notes``."""

import threading
from datetime import UTC, datetime

import pytest

from check_personal_data import load_landmarks, synthetic_coordinates
from ladder_data import CORPUS, public_landmarks
from weatherbot.models import WGS84, Geometry, LatLon, Location, Thresholds
from weatherbot.services.replay import (
    FULL_CONVERSION,
    ReplayCorpus,
    ReplayService,
    ReplayStep,
    ReplayTimelines,
    replay_notes,
)


def test_replay_timelines_computes_once_under_concurrent_requests_for_same_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = ReplayCorpus.open(CORPUS)
    thresholds = Thresholds()
    nassau = public_landmarks()["nassau"]
    timelines = ReplayTimelines(corpus, thresholds, max_size=4)

    calls = 0
    calls_lock = threading.Lock()
    entered = threading.Event()
    release = threading.Event()
    original_timeline = ReplayService.timeline

    def _slow_timeline(
        self: ReplayService,
        atcf_id: str,
        location: Location,
        active_thresholds: Thresholds,
    ) -> tuple[ReplayStep, ...]:
        nonlocal calls
        with calls_lock:
            calls += 1
        entered.set()
        release.wait(timeout=5.0)
        return original_timeline(self, atcf_id, location, active_thresholds)

    monkeypatch.setattr(ReplayService, "timeline", _slow_timeline)

    results: list[tuple[ReplayStep, ...]] = []
    errors: list[BaseException] = []

    def _worker(loc: Location) -> None:
        try:
            results.append(timelines.timeline("AL142024", loc))
        except BaseException as exc:  # noqa: BLE001 - capture any worker exception
            errors.append(exc)

    # Toggle state differs, but without_evacuation_order is applied internally (same key).
    toggled_nassau = nassau.model_copy(
        update={
            "evacuation_order_in_effect": True,
            "evacuation_order_set_at": datetime(2026, 10, 12, tzinfo=UTC),
        }
    )
    first = threading.Thread(target=_worker, args=(nassau,))
    second = threading.Thread(target=_worker, args=(toggled_nassau,))

    first.start()
    assert entered.wait(timeout=5.0)
    second.start()
    release.set()
    first.join(timeout=10.0)
    second.join(timeout=10.0)

    assert not errors
    assert calls == 1
    assert len(results) == 2  # noqa: PLR2004
    assert results[0] == results[1]
    assert all(step.assessment.rule != "evacuation_order" for step in results[0])


def test_replay_timelines_evicts_least_recently_used_and_keys_on_point_and_polygon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    corpus = ReplayCorpus.open(CORPUS)
    thresholds = Thresholds()
    landmarks = public_landmarks()
    nassau = landmarks["nassau"]
    miami = landmarks["miami-dade"]

    with pytest.raises(ValueError, match="max_size"):
        ReplayTimelines(corpus, thresholds, max_size=0)

    timelines = ReplayTimelines(corpus, thresholds, max_size=2)
    computed_keys: list[tuple[str, str, float, float, bool]] = []
    original_timeline = ReplayService.timeline

    def _counting_timeline(
        self: ReplayService,
        atcf_id: str,
        location: Location,
        active_thresholds: Thresholds,
    ) -> tuple[ReplayStep, ...]:
        computed_keys.append(
            (
                atcf_id,
                location.name,
                location.point.latitude,
                location.point.longitude,
                location.polygon is not None,
            )
        )
        return original_timeline(self, atcf_id, location, active_thresholds)

    monkeypatch.setattr(ReplayService, "timeline", _counting_timeline)

    # Populate two entries: (AL142024, nassau) and (AL142024, miami-dade).
    timelines.timeline("AL142024", nassau)
    timelines.timeline("AL142024", miami)
    assert len(computed_keys) == 2  # noqa: PLR2004

    # Touch nassau so miami-dade becomes the least-recently-used entry.
    timelines.timeline("AL142024", nassau)
    assert len(computed_keys) == 2  # noqa: PLR2004

    # Removing and re-adding nassau at different coordinates must compute a fresh timeline
    # and evict miami-dade (the LRU entry).
    lat_str, lon_str = synthetic_coordinates(load_landmarks(), (), seed=17)
    relocated_nassau = nassau.model_copy(
        update={"point": LatLon(latitude=float(lat_str), longitude=float(lon_str))}
    )
    timelines.timeline("AL142024", relocated_nassau)
    assert len(computed_keys) == 3  # noqa: PLR2004

    # Original nassau is still cached (it was MRU before relocated_nassau was inserted).
    timelines.timeline("AL142024", nassau)
    assert len(computed_keys) == 3  # noqa: PLR2004

    # miami-dade was evicted, so requesting it again recomputes.
    timelines.timeline("AL142024", miami)
    assert len(computed_keys) == 4  # noqa: PLR2004

    # Adding a polygon to the same named location also changes the cache key.
    lat = nassau.point.latitude
    lon = nassau.point.longitude
    box = Geometry(
        type="Polygon",
        coordinates=(((lon, lat), (lon + 0.01, lat), (lon + 0.01, lat + 0.01), (lon, lat)),),
        crs=WGS84,
    )
    polygon_nassau = nassau.model_copy(update={"polygon": box})
    timelines.timeline("AL142024", polygon_nassau)
    assert len(computed_keys) == 5  # noqa: PLR2004


def test_replay_notes_reports_evacuation_toggle_outside_wsp_window_and_missing_inputs() -> None:
    corpus = ReplayCorpus.open(CORPUS)
    thresholds = Thresholds()
    timelines = ReplayTimelines(corpus, thresholds)

    lat_str, lon_str = synthetic_coordinates(load_landmarks(), (), seed=19)
    far_location = Location(
        name="Far synthetic place",
        point=LatLon(latitude=float(lat_str), longitude=float(lon_str)),
        evacuation_order_in_effect=True,
        evacuation_order_set_at=datetime(2026, 10, 12, tzinfo=UTC),
    )
    steps = timelines.timeline("AL142024", far_location)
    notes = replay_notes(far_location, steps)

    assert any("evacuation-order toggle" in note for note in notes)
    assert any(FULL_CONVERSION in note for note in notes)
    assert any("Replayed assessments lack" in note for note in notes)
