"""Bounded model outputs: a proposal is never execution authority."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Proposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["query", "document", "insufficient", "incompatible", "unsupported"]
    import_id: str = Field(default="", max_length=100)
    sql: str = Field(default="", max_length=8192)
    # Optional deterministic trend over the returned (not truncated) result.
    year_column: str = Field(default="", max_length=63)
    value_column: str = Field(default="", max_length=63)


class Cell(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row: int = Field(ge=0, le=999)
    column: str = Field(min_length=1, max_length=63)
    value: str | int | float | bool | None


class Quote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(max_length=100)
    quote: str = Field(min_length=1, max_length=512)


class Synthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["supported", "insufficient"]
    cells: list[Cell] = Field(default_factory=list, max_length=30)
    quotes: list[Quote] = Field(default_factory=list, max_length=2)
