# tests/web/test_api_errors.py
"""Validation error sanitization (never echoing ``input``) and traceback coordinate redaction."""

import asyncio
import logging
from http import HTTPStatus
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import cast

import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from source_support import NOW

from weatherbot.services.config import AppPaths, Settings
from weatherbot.services.logs import configure_logging
from weatherbot.services.persistence.database import open_database
from weatherbot.web.app import WebState, create_app

PROBE_INPUT = "untrusted-input-probe-9b4e"


class _StrictPayload(BaseModel):
    count: int


def _close_rotating_handlers() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler):
            root.removeHandler(handler)
            handler.close()


def _raise_coord_error(lat: str, lon: str) -> None:
    msg = f"failed for https://api.weather.gov/points/{lat},{lon}"
    raise RuntimeError(msg)


def test_request_and_response_validation_errors_strip_input(tmp_path: Path) -> None:
    paths = AppPaths.resolve()
    database = open_database(paths, now=lambda: NOW)
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    try:
        state = WebState(
            database=database,
            paths=paths,
            settings=Settings(),
            clock=lambda: NOW,
            started_at=NOW,
            static_dir=static_dir,
        )
        app = create_app(state)
        router = APIRouter()

        @router.post("/api/validate-req")
        def validate_req(payload: _StrictPayload) -> dict[str, int]:
            return {"count": payload.count}

        @router.get("/api/validate-res", response_model=_StrictPayload)
        def validate_res() -> dict[str, str]:
            return {"count": PROBE_INPUT}

        app.router.routes.insert(0, router.routes[1])
        app.router.routes.insert(0, router.routes[0])

        async def _call() -> tuple[httpx.Response, httpx.Response]:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://127.0.0.1:8765"
            ) as client:
                req_err = await client.post(
                    "/api/validate-req",
                    json={"count": PROBE_INPUT},
                )
                res_err = await client.get("/api/validate-res")
                return req_err, res_err

        req_err, res_err = asyncio.run(_call())
    finally:
        database.close()

    assert req_err.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    req_detail = cast("list[dict[str, object]]", req_err.json()["detail"])
    assert len(req_detail) == 1
    assert set(req_detail[0]) == {"loc", "msg", "type"}
    assert "input" not in req_detail[0]
    assert PROBE_INPUT not in req_err.text

    assert res_err.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    res_detail = cast("list[dict[str, object]]", res_err.json()["detail"])
    assert len(res_detail) == 1
    assert set(res_detail[0]) == {"loc", "msg", "type"}
    assert "input" not in res_detail[0]
    assert PROBE_INPUT not in res_err.text


def test_formatted_exception_tracebacks_redact_coordinates_in_log_file(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "logs" / "weatherbot.log"
    coord_lat = "25.7757"
    coord_lon = "-80.1966"
    try:
        configure_logging("INFO", log_file=log_path)
        logger = logging.getLogger("weatherbot.test.exc")
        try:
            _raise_coord_error(coord_lat, coord_lon)
        except RuntimeError:
            logger.exception("unhandled route failure")
    finally:
        _close_rotating_handlers()
        configure_logging("INFO")

    text = log_path.read_text(encoding="utf-8")
    assert "unhandled route failure" in text
    assert "RuntimeError" in text
    assert "/points/<redacted>" in text
    assert coord_lat not in text
    assert coord_lon not in text
