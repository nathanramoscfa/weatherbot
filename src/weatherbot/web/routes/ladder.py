# src/weatherbot/web/routes/ladder.py
"""``GET /api/ladder``: the engine's threat levels, ordered rules, official codes, and thresholds."""  # noqa: E501 - route summary docstring

from typing import TYPE_CHECKING, cast

from fastapi import APIRouter, Request

from weatherbot.services.disclaimer import NOTICE
from weatherbot.services.ladder import ladder_reference
from weatherbot.web.schemas import (
    LadderCodeResponse,
    LadderEventResponse,
    LadderResponse,
    LadderRuleResponse,
    LadderThresholdResponse,
    ThreatLevelResponse,
)

if TYPE_CHECKING:
    from weatherbot.web.app import WebState

router = APIRouter()


@router.get("/api/ladder")
def get_ladder(request: Request) -> LadderResponse:
    """Return the engine's levels, ordered rules, read products, and running startup thresholds."""
    state = cast("WebState", request.app.state.web)
    ref = ladder_reference(state.settings.engine.thresholds())
    return LadderResponse(
        levels=tuple(
            ThreatLevelResponse(
                number=level.number,
                label=level.label,
                actions=level.actions,
            )
            for level in ref.levels
        ),
        rules=tuple(
            LadderRuleResponse(
                order=rule.order,
                id=rule.id,
                level=rule.level,
                sentence=rule.sentence,
                sources=rule.sources,
            )
            for rule in ref.rules
        ),
        events=tuple(
            LadderEventResponse(
                event=item.event,
                rule=item.rule,
                level=item.level,
            )
            for item in ref.events
        ),
        codes=tuple(
            LadderCodeResponse(
                code=item.code,
                name=item.name,
                rule=item.rule,
                level=item.level,
            )
            for item in ref.codes
        ),
        thresholds=tuple(
            LadderThresholdResponse(
                name=item.name,
                value=item.value,
                unit=item.unit,
                description=item.description,
            )
            for item in ref.thresholds
        ),
        ruleset=ref.ruleset,
        notice=NOTICE,
    )
