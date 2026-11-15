"""Shared request-body building blocks."""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator


def _reject_nul(value: Any) -> Any:
    """PostgreSQL cannot store U+0000 in text; reject it as a 422 instead of failing with a 500."""
    if isinstance(value, str) and "\x00" in value:
        raise ValueError("Text must not contain NUL (U+0000) characters.")
    if isinstance(value, list | tuple):
        for item in value:
            _reject_nul(item)
    return value


class Body(BaseModel):
    """Strict request body: unknown fields are rejected, strings are trimmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def _no_nul_characters(cls, value: Any) -> Any:
        return _reject_nul(value)


Reason = Annotated[str, StringConstraints(min_length=3, max_length=1000)]
OptionalText = Annotated[str | None, Field(default=None, max_length=3000)]
CommandId = Annotated[
    str,
    StringConstraints(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$"),
    Field(description="Stable client-generated id. Replaying the same command is safe."),
]
Money = Annotated[int, Field(ge=0, le=10**12, description="Integer minor units (tyiyn).")]
Quantity = Annotated[int, Field(gt=0, le=1_000_000)]
