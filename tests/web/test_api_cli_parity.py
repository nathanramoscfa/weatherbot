# tests/web/test_api_cli_parity.py
"""Parity tests holding ``/api/assessments``, ``/api/storms``, and ``/api/alerts`` to the CLI."""

import asyncio
from datetime import timedelta

import httpx
from cli_support import MIAMI, NASSAU, add_landmark, county_statement, parse, recorded_services, run
from source_support import NOW

from weatherbot.cli.documents import (
    AlertsDocument,
    StatusDocument,
    StatusLocationEntry,
    StormsDocument,
)
from weatherbot.services.config import AppPaths, load_settings, setting_origins
from weatherbot.services.persistence.database import open_database
from weatherbot.web.app import WebState, create_app
from weatherbot.web.map_layers import SNAPSHOT_CACHE
from weatherbot.web.schemas import (
    AlertsResponse,
    AssessmentsResponse,
    LocationAssessmentResponse,
    StormsResponse,
)


def _assert_location_matches_cli(
    api_loc: LocationAssessmentResponse, cli_loc: StatusLocationEntry
) -> None:
    assert api_loc.inside_nws_coverage == cli_loc.inside_nws_coverage
    assert api_loc.time_zone == cli_loc.time_zone
    assert api_loc.evacuation_order.on == cli_loc.evacuation_order.on
    assert api_loc.evacuation_order.set_at == cli_loc.evacuation_order.set_at
    assert api_loc.breakpoint_span == cli_loc.breakpoint_span

    stored = api_loc.assessment
    assert stored is not None
    assert stored.as_of == cli_loc.as_of
    assert stored.level.number == cli_loc.level
    assert stored.level.label == cli_loc.level_name
    assert stored.level.actions == cli_loc.actions
    assert stored.rule == cli_loc.rule
    assert stored.rule_trigger == cli_loc.rule_trigger
    assert stored.complete == cli_loc.complete
    assert stored.ruleset == cli_loc.ruleset
    assert stored.toggle_changed == cli_loc.toggle_changed

    assert [
        (e.product, e.source_id, e.code, e.atcf_id, e.advisory, e.distance_km)
        for e in stored.evidence
    ] == [
        (e.product, e.source_id, e.code, e.atcf_id, e.advisory, e.distance_km)
        for e in cli_loc.evidence
    ]
    assert [(o.kind, o.code, o.covers, o.rule, o.reason) for o in stored.official] == [
        (o.kind, o.code, o.covers, o.rule, o.reason) for o in cli_loc.official
    ]
    assert [
        (u.kind, u.source_id, u.storm_name, u.threshold_kt, u.reason) for u in stored.unavailable
    ] == [
        (u.kind, u.source_id, u.storm_name, u.threshold_kt, u.reason) for u in cli_loc.unavailable
    ]
    assert [
        (
            t.atcf_id,
            t.storm_name,
            t.advisory,
            t.in_cone,
            t.distance_km,
            t.bearing_deg,
            t.closest_approach_km,
            t.lead_h,
        )
        for t in stored.threats
    ] == [
        (
            t.atcf_id,
            t.storm_name,
            t.advisory,
            t.in_cone,
            t.distance_km,
            t.bearing_deg,
            t.closest_approach_km,
            t.lead_h,
        )
        for t in cli_loc.threats
    ]


def test_api_assessments_storms_and_alerts_match_cli_json_documents() -> None:
    with recorded_services(overrides=county_statement()):
        assert add_landmark(MIAMI, "miami-dade").exit_code == 0
        assert add_landmark(NASSAU, "nassau").exit_code == 0
        assert run(["locations", "evacuation", MIAMI, "on"]).exit_code == 0
        status_doc = parse(run(["status", "--json"]), StatusDocument)
        status_no_fetch_doc = parse(run(["status", "--no-fetch", "--json"]), StatusDocument)
        storms_doc = parse(run(["storms", "--no-fetch", "--json"]), StormsDocument)
        alerts_miami_doc = parse(
            run(["alerts", "--no-fetch", "--location", MIAMI, "--json"]),
            AlertsDocument,
        )
        alerts_nassau_doc = parse(
            run(["alerts", "--no-fetch", "--location", NASSAU, "--json"]),
            AlertsDocument,
        )

    assert status_doc.snapshot.snapshot_id == status_no_fetch_doc.snapshot.snapshot_id

    SNAPSHOT_CACHE.clear()
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    try:
        state = WebState(
            database=database,
            paths=paths,
            settings=load_settings(paths),
            setting_origins=setting_origins(paths),
            clock=lambda: NOW,
            started_at=NOW - timedelta(minutes=10),
        )
        app = create_app(state)

        async def _query() -> tuple[AssessmentsResponse, StormsResponse, AlertsResponse]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                assessments_res = await client.get("/api/assessments")
                storms_res = await client.get("/api/storms")
                alerts_res = await client.get("/api/alerts")
                return (
                    AssessmentsResponse.model_validate_json(assessments_res.text),
                    StormsResponse.model_validate_json(storms_res.text),
                    AlertsResponse.model_validate_json(alerts_res.text),
                )

        api_assessments, api_storms, api_alerts = asyncio.run(_query())
    finally:
        database.close()

    assert api_assessments.snapshot is not None
    assert api_assessments.snapshot.snapshot_id == status_no_fetch_doc.snapshot.snapshot_id

    cli_by_name = {loc.name: loc for loc in status_no_fetch_doc.data.locations}
    api_by_name = {loc.name: loc for loc in api_assessments.locations}
    assert set(api_by_name) == set(cli_by_name) == {MIAMI, NASSAU}

    for name, cli_loc in cli_by_name.items():
        _assert_location_matches_cli(api_by_name[name], cli_loc)

    # /api/storms parity with storms --no-fetch --json
    assert [
        (s.atcf_id, s.name, s.classification, s.intensity_kt, s.advisory) for s in api_storms.storms
    ] == [
        (s.atcf_id, s.name, s.classification, s.intensity_kt, s.advisory)
        for s in storms_doc.data.storms
    ]
    assert [
        (o.basin, o.kind, o.chance_2day_pct, o.chance_7day_pct) for o in api_storms.outlook
    ] == [(o.basin, o.kind, o.chance_2day_pct, o.chance_7day_pct) for o in storms_doc.data.outlook]

    # /api/alerts parity with alerts --no-fetch --json for both locations
    alerts_by_name = {group.location.name: group for group in api_alerts.locations}
    miami_alerts = alerts_by_name[MIAMI].alerts
    assert miami_alerts is not None
    assert alerts_miami_doc.data.alerts is not None
    assert [(a.id, a.event, a.covers, a.rule) for a in miami_alerts] == [
        (a.id, a.event, a.covers, a.rule) for a in alerts_miami_doc.data.alerts
    ]
    assert alerts_by_name[NASSAU].alerts is None
    assert [
        (w.atcf_id, w.tcww, w.advisory, w.covers) for w in alerts_by_name[NASSAU].watch_warnings
    ] == [(w.atcf_id, w.tcww, w.advisory, w.covers) for w in alerts_nassau_doc.data.watch_warnings]
