"""Shared schema primitives."""

from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    """Read model sourced directly from a SQLAlchemy instance."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class StrictModel(BaseModel):
    """Write model: unknown keys are a client bug, so reject them loudly."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def OrderField(default: int = 0) -> Field:  # type: ignore[valid-type]
    """Public ``order`` field backed by the ``sort_order`` column.

    ``order`` is a reserved word in SQL, so the column is ``sort_order`` while
    the JSON contract the frontend consumes stays ``order``.
    """
    return Field(
        default,
        ge=0,
        validation_alias=AliasChoices("order", "sort_order"),
        description="Ascending display order",
    )
