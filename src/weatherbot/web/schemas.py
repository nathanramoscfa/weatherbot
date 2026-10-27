# src/weatherbot/web/schemas.py
"""Typed Pydantic response models for the local web API.

Every response model is frozen and forbids unknown fields. No model carries coordinates
except the locations API (added in Step 2), and validation error responses strip ``input``
so rejected payloads are never echoed back.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _ApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DatabaseHealth(_ApiModel):
    """Database revision status reported by ``GET /api/health``."""

    revision: str | None
    head: str
    current: bool


class SchedulerHealth(_ApiModel):
    """The ``serve`` runner heartbeat summary reported by ``GET /api/health``."""

    last_success_at: datetime | None
    expected_every_s: int | None
    stale: bool


class HeartbeatHealth(_ApiModel):
    """One source, watch, or runner heartbeat row reported by ``GET /api/health``."""

    kind: str
    name: str
    last_success_at: datetime | None
    age_s: float | None
    consecutive_failures: int
    expected_every_s: int | None
    stale: bool


class UiHealth(_ApiModel):
    """Whether the built frontend bundle is present on disk at startup."""

    present: bool
    index_sha256: str | None


class HealthResponse(_ApiModel):
    """Response document for ``GET /api/health``."""

    version: str
    started_at: datetime
    now: datetime
    database: DatabaseHealth
    scheduler: SchedulerHealth
    heartbeats: list[HeartbeatHealth]
    stale: bool
    next_product_at: datetime
    ui: UiHealth
    corpus: bool
    notice: str
