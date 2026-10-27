# src/weatherbot/web/routes/disclaimer.py
"""``GET /api/disclaimer``: notice, essential points, full text, and public URL."""

from fastapi import APIRouter

from weatherbot.services.disclaimer import DISCLAIMER_URL, ESSENTIALS, NOTICE, full_text
from weatherbot.web.schemas import DisclaimerResponse

router = APIRouter()


@router.get("/api/disclaimer")
def get_disclaimer() -> DisclaimerResponse:
    """Return Weatherbot's notice, essential summary points, full text, and URL."""
    return DisclaimerResponse(
        notice=NOTICE,
        essentials=ESSENTIALS,
        full_text=full_text(),
        url=DISCLAIMER_URL,
    )
