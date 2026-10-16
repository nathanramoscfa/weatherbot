# src/weatherbot/models/advisory_number.py
"""NHC advisory numbers: a full advisory and its lettered intermediates."""

import re
from typing import Any, Final, Self

from pydantic import Field, model_validator

from weatherbot.models.base import DomainModel

_ADVISORY_NUMBER: Final = re.compile(r"0*(?P<number>[1-9]\d{0,2})(?P<letter>[A-Za-z])?")


class AdvisoryNumber(DomainModel):
    """An advisory number such as ``22`` or ``22A``, ordered ``22 < 22A < 22B < 23``.

    It parses every spelling NOAA uses (``22A`` in the map layers, ``022a`` in the roster,
    ``22``, ``022``) and prints as NHC prints it in its products (``22A``).
    """

    number: int = Field(ge=1, le=999)
    letter: str | None = Field(default=None, pattern=r"^[A-Z]$")

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:  # noqa: ANN401 - pydantic hands over raw input
        # Lax on purpose: products spell the number as text, and the parsers pass it on.
        return cls._parts(data) if isinstance(data, str) else data

    @classmethod
    def _parts(cls, text: str) -> dict[str, object]:
        match = _ADVISORY_NUMBER.fullmatch(text.strip())
        if match is None:
            message = f"not an advisory number: {text!r}"
            raise ValueError(message)
        letter = match["letter"]
        return {"number": int(match["number"]), "letter": letter.upper() if letter else None}

    @classmethod
    def parse(cls, text: str) -> Self:
        """Parse ``22A``, ``022a``, ``22``, or ``022``.

        Args:
            text: The advisory number as a product spells it.

        Returns:
            The advisory number.
        """
        return cls.model_validate(cls._parts(text))

    @property
    def is_intermediate(self) -> bool:
        """Whether this is a lettered intermediate advisory."""
        return self.letter is not None

    def _key(self) -> tuple[int, str]:
        return (self.number, self.letter or "")

    def __str__(self) -> str:
        """Print the number as NHC does: ``22A``."""
        return f"{self.number}{self.letter or ''}"

    def __lt__(self, other: object) -> bool:
        """Order by number, then letter."""
        if not isinstance(other, AdvisoryNumber):
            return NotImplemented
        return self._key() < other._key()

    def __le__(self, other: object) -> bool:
        """Order by number, then letter."""
        if not isinstance(other, AdvisoryNumber):
            return NotImplemented
        return self._key() <= other._key()

    def __gt__(self, other: object) -> bool:
        """Order by number, then letter."""
        if not isinstance(other, AdvisoryNumber):
            return NotImplemented
        return self._key() > other._key()

    def __ge__(self, other: object) -> bool:
        """Order by number, then letter."""
        if not isinstance(other, AdvisoryNumber):
            return NotImplemented
        return self._key() >= other._key()
