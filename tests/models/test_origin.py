# tests/models/test_origin.py
"""A snapshot's origin: live snapshots keep every Phase 2 rule; replay snapshots cite the archive.

A replay snapshot is one archived advisory read back: it asks no roster, its storms carry
the archive's ``ArchiveStorm``, and every record cites ``nhc-gis-archive`` or
``nhc-arrival-times``. A wind-speed-probability extract records the area it covers and
holds no band outside it.
"""

import pytest
from model_samples import (
    archive_storm,
    cone,
    landmark_point,
    landmark_square,
    outcomes,
    provenance,
    snapshot,
    storm_products,
    summary,
    wind_band,
    wind_product,
)
from pydantic import ValidationError

from weatherbot.models import (
    WGS84,
    ArchiveStorm,
    Crs,
    Geometry,
    Snapshot,
    SourceOutcome,
    StormProducts,
    WindProbabilityBand,
    WindProbabilityProduct,
)

ARCHIVE_OK = SourceOutcome(source_id="nhc-gis-archive", status="ok")
SPHERE = Crs.native(
    {
        "datum": "D_Sphere",
        "wkt": 'GEOGCS["GCS_Sphere",DATUM["D_Sphere",SPHEROID["Sphere",6371200.0,0.0]],'
        'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]',
    }
)


def archived_storm() -> StormProducts:
    """Return a replayed storm: the archive's header and a cone that cites the archive."""
    return StormProducts(
        archived=archive_storm(),
        cone=cone().model_copy(update={"provenance": provenance("nhc-gis-archive")}),
    )


def replay(**changes: object) -> Snapshot:
    """Return a replay snapshot of one archived storm, validated with ``changes``."""
    base = snapshot()
    fields: dict[str, object] = {
        "snapshot_id": base.snapshot_id,
        "origin": "replay",
        "started_at": base.started_at,
        "completed_at": base.started_at,
        "storms": (archived_storm(),),
        "source_outcomes": (ARCHIVE_OK,),
    }
    return Snapshot.model_validate({**fields, **changes})


def test_a_snapshot_is_live_unless_it_says_otherwise() -> None:
    assert snapshot().origin == "live"
    assert replay().origin == "replay"
    assert replay().status == "complete"


def test_a_live_snapshot_without_the_roster_s_outcome_is_refused() -> None:
    without = tuple(o for o in snapshot().source_outcomes if o.source_id != "nhc-current-storms")

    with pytest.raises(ValidationError, match="the roster always among them"):
        Snapshot.model_validate({**dict(snapshot()), "source_outcomes": without})


def test_a_live_snapshot_s_storms_carry_the_roster_s_summary() -> None:
    with pytest.raises(ValidationError, match="carry the roster's summary"):
        Snapshot.model_validate({**dict(snapshot()), "storms": (archived_storm(),)})


def test_a_replay_snapshot_with_a_roster_outcome_is_refused() -> None:
    roster = SourceOutcome(source_id="nhc-current-storms", status="ok")

    with pytest.raises(ValidationError, match="asks no roster"):
        replay(source_outcomes=(ARCHIVE_OK, roster))


def test_a_replay_snapshot_always_has_the_archive_s_outcome() -> None:
    with pytest.raises(ValidationError, match="the GIS archive always among them"):
        replay(source_outcomes=outcomes())
    with pytest.raises(ValidationError, match="one outcome per source"):
        replay(source_outcomes=(ARCHIVE_OK, ARCHIVE_OK))


def test_a_replay_snapshot_s_storms_carry_the_archive_s_record() -> None:
    with pytest.raises(ValidationError, match="carry the archive's record"):
        replay(storms=(storm_products(),))


def test_a_replay_snapshot_holds_only_archive_and_arrival_records() -> None:
    mapped = wind_product()

    with pytest.raises(ValidationError, match="only records of the archive"):
        replay(
            wind_probabilities=(mapped,),
            source_outcomes=(
                ARCHIVE_OK,
                SourceOutcome(source_id="nhc-map-tropical-weather", status="ok"),
            ),
        )
    archived = mapped.model_copy(update={"provenance": provenance("nhc-gis-archive")})
    assert replay(wind_probabilities=(archived,)).wind_probabilities == (archived,)


def test_a_replay_snapshot_s_status_follows_the_archive() -> None:
    failed = SourceOutcome(source_id="nhc-gis-archive", status="failed", error_kind="schema")
    skipped = SourceOutcome(
        source_id="nhc-arrival-times", status="skipped", reason="the corpus holds none"
    )

    assert replay(storms=(), source_outcomes=(failed,)).status == "failed"
    assert replay(source_outcomes=(ARCHIVE_OK, skipped)).status == "complete"


@pytest.mark.parametrize("headers", ["both", "neither"])
def test_a_storm_carries_exactly_one_header(headers: str) -> None:
    fields: dict[str, object] = (
        {"summary": summary(), "archived": archive_storm()} if headers == "both" else {}
    )

    with pytest.raises(ValidationError, match="exactly one header"):
        StormProducts.model_validate(fields)


def test_a_storm_s_id_and_name_read_whichever_header_it_carries() -> None:
    live, replayed = storm_products(), archived_storm()

    assert (live.atcf_id, live.name) == (summary().atcf_id, summary().name)
    assert (replayed.atcf_id, replayed.name) == (archive_storm().atcf_id, archive_storm().name)
    assert replayed.summary is None
    assert live.archived is None


def test_an_archive_storm_comes_from_the_archive() -> None:
    with pytest.raises(ValidationError, match="comes from the GIS archive"):
        ArchiveStorm.model_validate({**dict(archive_storm()), "provenance": provenance()})


def test_a_replay_storm_s_products_belong_to_that_storm() -> None:
    other = archive_storm().model_copy(update={"atcf_id": "EP192026"})

    with pytest.raises(ValidationError, match="belongs to that storm"):
        StormProducts.model_validate({**dict(archived_storm()), "archived": other})


# Wind-speed-probability extracts


def extract(coverage: Geometry, *bands: WindProbabilityBand) -> WindProbabilityProduct:
    """Return a 34-kt extract covering ``coverage`` with ``bands``."""
    return WindProbabilityProduct.model_validate(
        {**dict(wind_product()), "bands": bands, "coverage": coverage}
    )


def test_a_full_product_has_no_coverage() -> None:
    assert wind_product().coverage is None


def test_an_extract_holds_its_bands_inside_its_coverage() -> None:
    band = WindProbabilityBand.from_label("5-10%", landmark_square(half=0.05))

    product = extract(landmark_square(half=1.0), band)

    assert product.coverage == landmark_square(half=1.0)
    assert extract(landmark_square(half=1.0)).bands == ()


def test_a_band_outside_its_product_s_coverage_is_refused() -> None:
    band = WindProbabilityBand.from_label("5-10%", landmark_square("nassau", half=0.05))

    with pytest.raises(ValidationError, match="inside its coverage"):
        extract(landmark_square(half=1.0), band)
    with pytest.raises(ValidationError, match="inside its coverage"):
        extract(landmark_square(half=0.01), wind_band())


def test_an_extract_s_coverage_is_areal_and_in_its_bands_crs() -> None:
    square = landmark_square(half=1.0)
    native = Geometry(type=square.type, coordinates=square.coordinates, crs=SPHERE)
    band = WindProbabilityBand.from_label("5-10%", landmark_square(half=0.05))

    with pytest.raises(ValidationError, match="must be one of"):
        extract(landmark_point())
    with pytest.raises(ValidationError, match="in its bands' CRS"):
        extract(native, band)
    assert extract(native).coverage is not None
    assert band.geometry.crs == WGS84


def test_a_band_says_how_its_shape_differs_from_the_source() -> None:
    assert wind_band().geometry_note is None
    noted = WindProbabilityBand.from_label(
        "5-10%", landmark_square(), "Source band invalid (Ring Self-intersection)."
    )

    assert noted.geometry_note == "Source band invalid (Ring Self-intersection)."
