# src/weatherbot/sources/fields.py
"""Strict readers for JSON payloads: a missing or mistyped field is a ``SourceSchemaError``.

Every parser reads a feature's properties through ``Fields``, which allows only the names
its parser declares (the register's "Fields v2 uses", which the field-coverage contract
test compares). A message names the field and where it was expected, never its value: a
value can be a coordinate.
"""

import json
from collections.abc import Collection, Generator, Mapping, Sequence
from contextlib import contextmanager
from typing import Final, cast

from pydantic import ValidationError

from weatherbot.models import SourceId
from weatherbot.sources.errors import SourceSchemaError

MISSING_VALUE: Final = 9999
"""NHC's stand-in for a missing forecast-point value (the register's Forecast Points)."""


def parse_document(body: bytes, source_id: SourceId, what: str) -> object:
    """Parse a JSON payload.

    Args:
        body: The payload.
        source_id: The register id, for the error.
        what: What the payload is, for the error.

    Returns:
        The parsed value.

    Raises:
        SourceSchemaError: The payload is not JSON.
    """
    try:
        value: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        message = f"{what} is not valid JSON"
        raise SourceSchemaError(source_id, message) from None
    return value


def as_mapping(value: object, source_id: SourceId, what: str) -> Mapping[str, object]:
    """Return ``value`` as a JSON object.

    Args:
        value: A parsed JSON value.
        source_id: The register id, for the error.
        what: What the value is, for the error.

    Returns:
        The object.

    Raises:
        SourceSchemaError: The value is not an object.
    """
    if not isinstance(value, dict):
        message = f"{what} is not a JSON object"
        raise SourceSchemaError(source_id, message)
    return cast("dict[str, object]", value)


def as_sequence(value: object, source_id: SourceId, what: str) -> Sequence[object]:
    """Return ``value`` as a JSON array.

    Args:
        value: A parsed JSON value.
        source_id: The register id, for the error.
        what: What the value is, for the error.

    Returns:
        The array.

    Raises:
        SourceSchemaError: The value is not an array.
    """
    if not isinstance(value, list):
        message = f"{what} is not a JSON array"
        raise SourceSchemaError(source_id, message)
    return cast("list[object]", value)


@contextmanager
def model_errors(source_id: SourceId, what: str) -> Generator[None]:
    """Turn a model's validation error into a ``SourceSchemaError`` naming the rule.

    The models hide their input in errors, so the message never repeats a value.

    Args:
        source_id: The register id.
        what: What was being built, for the message.

    Yields:
        Nothing; the block builds the model.

    Raises:
        SourceSchemaError: The model refused the values.
    """
    try:
        yield
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "the record"
        message = f"{what} breaks the model at {where}: {first['msg']}"
        raise SourceSchemaError(source_id, message) from None
    except ValueError as error:
        message = f"{what} breaks the model: {error}"
        raise SourceSchemaError(source_id, message) from None


class Fields:
    """A JSON object read only through the names its parser declares.

    A declared name that is absent is a ``SourceSchemaError``; an undeclared name is a
    programming error, so ``FIELDS_READ`` can never fall behind what a parser reads.
    """

    def __init__(
        self,
        values: Mapping[str, object],
        declared: Collection[str],
        *,
        source_id: SourceId,
        where: str,
    ) -> None:
        """Wrap an object.

        Args:
            values: The object, such as a feature's ``properties``.
            declared: The names the parser may read.
            source_id: The register id, for errors.
            where: The layer or object, for errors.
        """
        self._values = values
        self._declared = declared
        self.source_id: SourceId = source_id
        self.where = where

    def _error(self, name: str, problem: str) -> SourceSchemaError:
        return SourceSchemaError(self.source_id, f"{self.where}: {name!r} {problem}")

    def raw(self, name: str) -> object:
        """Return a declared field's value, which may be null.

        Args:
            name: The field.

        Returns:
            The value.

        Raises:
            RuntimeError: The parser did not declare the field.
            SourceSchemaError: The field is absent.
        """
        if name not in self._declared:
            message = f"{self.where}: the parser reads {name!r} without declaring it"
            raise RuntimeError(message)
        if name not in self._values:
            raise self._error(name, "is missing")
        return self._values[name]

    def optional_text(self, name: str) -> str | None:
        """Return a text field, or ``None`` when it is null.

        Args:
            name: The field.

        Returns:
            The text.

        Raises:
            SourceSchemaError: The field is absent or not text.
        """
        value = self.raw(name)
        if value is None or isinstance(value, str):
            return value
        raise self._error(name, "is not text")

    def text(self, name: str) -> str:
        """Return a text field that is never null.

        Args:
            name: The field.

        Returns:
            The text.

        Raises:
            SourceSchemaError: The field is absent, null, or not text.
        """
        value = self.optional_text(name)
        if value is None:
            raise self._error(name, "is null")
        return value

    def optional_integer(self, name: str, *, sentinel: bool = False) -> int | None:
        """Return an integer field (a number or decimal digits), or ``None`` when null.

        Args:
            name: The field.
            sentinel: Whether ``9999`` means "no value" here (the register says where).

        Returns:
            The integer.

        Raises:
            SourceSchemaError: The field is absent or not an integer.
        """
        value = self.raw(name)
        number: int | None
        if value is None:
            number = None
        elif isinstance(value, bool):
            raise self._error(name, "is not an integer")
        elif isinstance(value, int):
            number = value
        elif isinstance(value, float) and value.is_integer():
            number = int(value)
        elif isinstance(value, str) and value.strip().isdigit():
            number = int(value.strip())
        else:
            raise self._error(name, "is not an integer")
        return None if sentinel and number == MISSING_VALUE else number

    def integer(self, name: str) -> int:
        """Return an integer field that is never null.

        Args:
            name: The field.

        Returns:
            The integer.

        Raises:
            SourceSchemaError: The field is absent, null, or not an integer.
        """
        value = self.optional_integer(name)
        if value is None:
            raise self._error(name, "is null")
        return value

    def optional_number(self, name: str) -> float | None:
        """Return a numeric field, or ``None`` when null.

        Args:
            name: The field.

        Returns:
            The number.

        Raises:
            SourceSchemaError: The field is absent or not a number.
        """
        value = self.raw(name)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise self._error(name, "is not a number")
        return float(value)

    def number(self, name: str) -> float:
        """Return a numeric field that is never null.

        Args:
            name: The field.

        Returns:
            The number.

        Raises:
            SourceSchemaError: The field is absent, null, or not a number.
        """
        value = self.optional_number(name)
        if value is None:
            raise self._error(name, "is null")
        return value

    def code(self, name: str) -> str:
        """Return a field NOAA spells as text or as a number (``22A`` or ``22``), as text.

        Args:
            name: The field.

        Returns:
            The text.

        Raises:
            SourceSchemaError: The field is absent, null, or neither text nor an integer.
        """
        value = self.raw(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
        raise self._error(name, "is not a code")

    def child(self, name: str, declared: Collection[str]) -> "Fields | None":
        """Return a nested object's fields, or ``None`` when the object is absent or null.

        Args:
            name: The member holding the object.
            declared: The names the parser may read inside it.

        Returns:
            The nested fields.

        Raises:
            SourceSchemaError: The member is not an object.
        """
        value = self._values.get(name)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise self._error(name, "is not an object")
        return Fields(
            cast("dict[str, object]", value),
            declared,
            source_id=self.source_id,
            where=f"{self.where}.{name}",
        )
