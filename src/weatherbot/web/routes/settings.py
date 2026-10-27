# src/weatherbot/web/routes/settings.py
"""``GET /api/settings``: effective settings, origins, and ``weatherbot.toml`` status."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Request

from weatherbot.services.config import setting_origins
from weatherbot.services.disclaimer import NOTICE
from weatherbot.web.schemas import SettingOriginResponse, SettingsResponse

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()


@router.get("/api/settings")
def get_settings(request: Request) -> SettingsResponse:
    """Return every setting's effective value, origin, and whether weatherbot.toml changed."""
    state = cast("WebState", request.app.state.web)
    settings_path = state.paths.settings_path
    started_at = state.started_at.astimezone(UTC)

    try:
        stat_result = settings_path.stat()
    except OSError:
        file_exists = False
        modified_since_start = False
    else:
        file_exists = True
        mtime = datetime.fromtimestamp(stat_result.st_mtime, tz=UTC)
        modified_since_start = mtime > started_at

    origins = state.setting_origins or setting_origins(state.paths)

    return SettingsResponse(
        settings_file=str(settings_path),
        settings_file_exists=file_exists,
        file_modified_since_start=modified_since_start,
        settings=tuple(
            SettingOriginResponse(
                table=item.table,
                key=item.key,
                value=item.value,
                origin=item.origin,
                variable=item.variable,
            )
            for item in origins
        ),
        notice=NOTICE,
    )
