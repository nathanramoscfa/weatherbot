# src/weatherbot/web/routes/settings.py
"""``GET/PUT /api/settings``, ``GET /api/retention``, and ``POST /api/retention/run``."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated, Final, cast

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status

from weatherbot.services.config import (
    ENVIRONMENT_OVERRIDES,
    RETENTION_MAX_DAYS,
    RETENTION_MIN_DAYS,
    ConfigError,
    SettingOrigin,
    Settings,
    setting_origins,
)
from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.locks import held
from weatherbot.services.retention import (
    RetentionCutoffError,
    RetentionService,
    validate_cutoff,
)
from weatherbot.services.settings_file import (
    EnvironmentOverrideError,
    SettingChange,
    StaleSettingsFileError,
    UneditableSettingError,
    applies_at,
    apply_changes,
    is_editable,
    restart_keys,
    settings_file_sha256,
)
from weatherbot.web.schemas import (
    RetentionLastRunResponse,
    RetentionPlanResponse,
    RetentionResponse,
    RetentionSettingResponse,
    RunRetentionRequest,
    RunRetentionResponse,
    SettingOriginResponse,
    SettingsResponse,
    UpdateSettingsRequest,
    UpdateSettingsResponse,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from weatherbot.web.app import WebState

router = APIRouter()

DEFAULT_PREVIEW_DAYS: Final = 365


def _fallback_origins(settings: Settings) -> tuple[SettingOrigin, ...]:
    items: list[SettingOrigin] = []
    for (table, key), variable in ENVIRONMENT_OVERRIDES.items():
        section = getattr(settings, table)
        items.append(
            SettingOrigin(
                table=table,
                key=key,
                value=getattr(section, key),
                origin="default",
                variable=variable,
            )
        )
    return tuple(items)


def _origin_responses(origins: "Sequence[SettingOrigin]") -> tuple[SettingOriginResponse, ...]:
    return tuple(
        SettingOriginResponse(
            table=item.table,
            key=item.key,
            value=item.value,
            origin=item.origin,
            variable=item.variable,
            editable=is_editable(item.table, item.key),
            applies=applies_at(item.table, item.key),
        )
        for item in origins
    )


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

    try:
        digest = settings_file_sha256(state.paths)
    except ConfigError:
        digest = ""

    problem: str | None = None
    try:
        origins = setting_origins(state.paths, state.environ)
    except ConfigError as error:
        problem = str(error)
        origins = (
            state.last_setting_origins or state.setting_origins or _fallback_origins(state.settings)
        )
    except UnicodeDecodeError:
        problem = f"{settings_path} is not valid UTF-8"
        origins = (
            state.last_setting_origins or state.setting_origins or _fallback_origins(state.settings)
        )
    except OSError as error:
        problem = f"could not read {settings_path} ({type(error).__name__})"
        origins = (
            state.last_setting_origins or state.setting_origins or _fallback_origins(state.settings)
        )
    else:
        state.set_last_setting_origins(origins)

    return SettingsResponse(
        settings_file=str(settings_path),
        settings_file_exists=file_exists,
        settings_file_sha256=digest,
        file_modified_since_start=modified_since_start,
        restart_keys=restart_keys(state.settings, origins),
        settings_file_problem=problem,
        settings=_origin_responses(origins),
        notice=NOTICE,
    )


@router.put("/api/settings")
def put_settings(request: Request, body: UpdateSettingsRequest) -> UpdateSettingsResponse:
    """Validate and atomically apply allowlisted setting changes to ``weatherbot.toml``."""
    state = cast("WebState", request.app.state.web)
    changes = [
        SettingChange(table=item.table, key=item.key, value=item.value) for item in body.changes
    ]
    try:
        update = apply_changes(
            state.paths,
            changes,
            expected_sha256=body.expected_sha256,
            environ=state.environ,
        )
    except (StaleSettingsFileError, EnvironmentOverrideError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except (UneditableSettingError, ConfigError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    origins = setting_origins(state.paths, state.environ)
    state.set_last_setting_origins(origins)
    state.hub.publish("health", None, ("settings",))

    return UpdateSettingsResponse(
        settings_file_sha256=update.settings_file_sha256,
        applied_next_cycle=update.next_cycle,
        applied_next_start=update.next_start,
        restart_keys=restart_keys(state.settings, origins),
        settings=_origin_responses(origins),
        notice=NOTICE,
    )


@router.get("/api/retention")
def get_retention(
    request: Request,
    days: Annotated[
        int | None,
        Query(
            ge=RETENTION_MIN_DAYS,
            le=RETENTION_MAX_DAYS,
            description="Preview retention plan for this many days (30..3650).",
        ),
    ] = None,
) -> RetentionResponse:
    """Return database and WAL sizes, row counts, retention setting, last run, and preview plan."""
    state = cast("WebState", request.app.state.web)
    try:
        origins = setting_origins(state.paths, state.environ)
    except (ConfigError, OSError, UnicodeDecodeError):
        origins = (
            state.last_setting_origins or state.setting_origins or _fallback_origins(state.settings)
        )
    else:
        state.set_last_setting_origins(origins)

    retention_origin = next(
        (item for item in origins if item.table == "retention" and item.key == "history_days"),
        SettingOrigin(
            table="retention",
            key="history_days",
            value=state.settings.retention.history_days,
            origin="default",
            variable="WEATHERBOT_RETENTION_HISTORY_DAYS",
        ),
    )
    configured_days = (
        int(retention_origin.value) if not isinstance(retention_origin.value, bool) else 0
    )
    plan_days = (
        days
        if days is not None
        else (configured_days if configured_days >= RETENTION_MIN_DAYS else DEFAULT_PREVIEW_DAYS)
    )

    service = RetentionService(
        state.database.engine,
        state.paths,
        now=state.clock,
    )
    overview = service.overview()
    plan = service.plan(plan_days)
    last_run = overview.last_run

    return RetentionResponse(
        database_bytes=overview.database_bytes,
        wal_bytes=overview.wal_bytes,
        oldest_snapshot_at=overview.oldest_snapshot_at,
        newest_snapshot_at=overview.newest_snapshot_at,
        row_counts=overview.row_counts,
        setting=RetentionSettingResponse(
            history_days=configured_days,
            origin=retention_origin.origin,
            variable=retention_origin.variable,
            editable=is_editable("retention", "history_days")
            and retention_origin.origin != "environment",
        ),
        last_run=(
            RetentionLastRunResponse(
                ran_at=last_run.ran_at,
                cutoff=last_run.cutoff,
                status=last_run.status,
                batches=last_run.batches,
                total_deleted=last_run.total_deleted,
                counts=last_run.counts,
                backup_file=last_run.backup_file,
            )
            if last_run is not None
            else None
        ),
        plan=RetentionPlanResponse(
            days=plan_days,
            cutoff=plan.cutoff,
            counts=plan.counts,
            total_rows=plan.total_rows,
            estimated_bytes=plan.estimated_bytes,
            kept=plan.kept,
            kept_snapshots=plan.kept_snapshots,
            kept_assessments=plan.kept_assessments,
        ),
        notice=NOTICE,
    )


@router.post("/api/retention/run", status_code=status.HTTP_202_ACCEPTED)
def run_retention(
    request: Request,
    body: RunRetentionRequest,
    background_tasks: BackgroundTasks,
) -> RunRetentionResponse:
    """Validate ``cutoff`` and run one retention prune as a single-flight background task."""
    state = cast("WebState", request.app.state.web)
    now = state.clock().astimezone(UTC)
    try:
        validated_cutoff = validate_cutoff(body.cutoff, now=now)
    except RetentionCutoffError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    if state.retention_in_flight or held(state.paths.retention_lock_path):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="another retention prune is already running",
        )

    state.mark_retention_in_flight(in_flight=True)
    background_tasks.add_task(state.run_retention_prune, validated_cutoff)
    return RunRetentionResponse(
        status="accepted",
        cutoff=validated_cutoff,
        started_at=now,
        notice=NOTICE,
    )
