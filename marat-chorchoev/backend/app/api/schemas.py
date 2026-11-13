"""Shared request-body building blocks."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Body(BaseModel):
    """Strict request body: unknown fields are rejected, strings are trimmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Reason = Annotated[str, StringConstraints(min_length=3, max_length=1000)]
OptionalText = Annotated[str | None, Field(default=None, max_length=3000)]
CommandId = Annotated[
    str,
    StringConstraints(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$"),
    Field(description="Stable client-generated id. Replaying the same command is safe."),
]
Money = Annotated[int, Field(ge=0, le=10**12, description="Integer minor units (tyiyn).")]
Quantity = Annotated[int, Field(gt=0, le=1_000_000)]
