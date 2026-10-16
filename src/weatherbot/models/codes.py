# src/weatherbot/models/codes.py
"""Coded values: a closed official vocabulary that keeps the codes it does not know.

A coded value holds the raw string as received, the matching enum member, and
``recognized``. A code outside the vocabulary parses with ``recognized`` false and its raw
value, so an official product is never dropped because NOAA added a code; ``doctor``
reports it as source drift.
"""

from enum import StrEnum
from typing import ClassVar, Self

from pydantic import model_validator

from weatherbot.models.base import DomainModel


class CodedValue(DomainModel):
    """The shared shape of every coded value; each subclass names its vocabulary."""

    vocabulary: ClassVar[type[StrEnum]]

    raw: str
    recognized: bool

    @classmethod
    def parse(cls, raw: str) -> Self:
        """Build the coded value of ``raw``, recognized or not.

        Args:
            raw: The code exactly as the product spelled it.

        Returns:
            The coded value.
        """
        code = next((member for member in cls.vocabulary if member.value == raw), None)
        return cls.model_validate({"raw": raw, "recognized": code is not None, "code": code})

    @model_validator(mode="after")
    def _agrees_with_raw(self) -> Self:
        code: StrEnum | None = getattr(self, "code", None)
        expected = next((m for m in self.vocabulary if m.value == self.raw), None)
        if code != expected or self.recognized != (expected is not None):
            message = f"code and recognized must follow the raw value {self.raw!r}"
            raise ValueError(message)
        return self


class StormClassificationCode(StrEnum):
    """Storm classifications, from NHC's Tropical Cyclone Status JSON File Reference."""

    TROPICAL_DEPRESSION = "TD"
    SUBTROPICAL_DEPRESSION = "STD"
    TROPICAL_STORM = "TS"
    HURRICANE = "HU"
    SUBTROPICAL_STORM = "STS"
    POST_TROPICAL_CYCLONE = "PTC"
    TYPHOON = "TY"
    POTENTIAL_TROPICAL_CYCLONE = "PC"


class StormClassification(CodedValue):
    """A storm's ``classification`` from the roster."""

    vocabulary: ClassVar[type[StrEnum]] = StormClassificationCode
    code: StormClassificationCode | None


class WatchWarningCode(StrEnum):
    """Watch-warning ``tcww`` codes of the NHC forecast packages and map layers."""

    HURRICANE_WATCH = "HWA"
    HURRICANE_WARNING = "HWR"
    TROPICAL_STORM_WATCH = "TWA"
    TROPICAL_STORM_WARNING = "TWR"


class WatchWarningType(CodedValue):
    """A watch-warning segment's ``tcww``."""

    vocabulary: ClassVar[type[StrEnum]] = WatchWarningCode
    code: WatchWarningCode | None


class OutlookRiskCode(StrEnum):
    """Formation risk in the Graphical Tropical Weather Outlook."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class OutlookRisk(CodedValue):
    """An outlook area's ``risk2day`` or ``risk7day``."""

    vocabulary: ClassVar[type[StrEnum]] = OutlookRiskCode
    code: OutlookRiskCode | None


class AlertSeverityCode(StrEnum):
    """CAP ``severity``."""

    EXTREME = "Extreme"
    SEVERE = "Severe"
    MODERATE = "Moderate"
    MINOR = "Minor"
    UNKNOWN = "Unknown"


class AlertSeverity(CodedValue):
    """An alert's CAP ``severity``."""

    vocabulary: ClassVar[type[StrEnum]] = AlertSeverityCode
    code: AlertSeverityCode | None


class AlertCertaintyCode(StrEnum):
    """CAP ``certainty``."""

    OBSERVED = "Observed"
    LIKELY = "Likely"
    POSSIBLE = "Possible"
    UNLIKELY = "Unlikely"
    UNKNOWN = "Unknown"


class AlertCertainty(CodedValue):
    """An alert's CAP ``certainty``."""

    vocabulary: ClassVar[type[StrEnum]] = AlertCertaintyCode
    code: AlertCertaintyCode | None


class AlertUrgencyCode(StrEnum):
    """CAP ``urgency``."""

    IMMEDIATE = "Immediate"
    EXPECTED = "Expected"
    FUTURE = "Future"
    PAST = "Past"
    UNKNOWN = "Unknown"


class AlertUrgency(CodedValue):
    """An alert's CAP ``urgency``."""

    vocabulary: ClassVar[type[StrEnum]] = AlertUrgencyCode
    code: AlertUrgencyCode | None


class AlertStatusCode(StrEnum):
    """CAP ``status``."""

    ACTUAL = "Actual"
    EXERCISE = "Exercise"
    SYSTEM = "System"
    TEST = "Test"
    DRAFT = "Draft"


class AlertStatus(CodedValue):
    """An alert's CAP ``status``."""

    vocabulary: ClassVar[type[StrEnum]] = AlertStatusCode
    code: AlertStatusCode | None


class AlertMessageTypeCode(StrEnum):
    """CAP ``msgType``, which the NWS API names ``messageType``."""

    ALERT = "Alert"
    UPDATE = "Update"
    CANCEL = "Cancel"
    ACK = "Ack"
    ERROR = "Error"


class AlertMessageType(CodedValue):
    """An alert's ``messageType``."""

    vocabulary: ClassVar[type[StrEnum]] = AlertMessageTypeCode
    code: AlertMessageTypeCode | None


class AlertCategoryCode(StrEnum):
    """CAP ``category``."""

    GEO = "Geo"
    MET = "Met"
    SAFETY = "Safety"
    SECURITY = "Security"
    RESCUE = "Rescue"
    FIRE = "Fire"
    HEALTH = "Health"
    ENV = "Env"
    TRANSPORT = "Transport"
    INFRA = "Infra"
    CBRNE = "CBRNE"
    OTHER = "Other"


class AlertCategory(CodedValue):
    """An alert's CAP ``category``."""

    vocabulary: ClassVar[type[StrEnum]] = AlertCategoryCode
    code: AlertCategoryCode | None
