# src/weatherbot/models/base.py
"""The base class every domain model shares."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """A frozen, strict record: unknown fields are errors and values are never coerced.

    JSON enters through ``model_validate_json``, where strict mode still accepts what JSON
    can only spell as text: ISO 8601 instants, UUIDs, and enum values. A field turns lax
    only with a comment that says why.

    A validation error never repeats its input, because the input of a location or a
    geometry can be the operator's coordinates.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        hide_input_in_errors=True,
    )
