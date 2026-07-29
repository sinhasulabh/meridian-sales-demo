"""Pydantic result/receipt models (spec §8). No LLM, no I/O — just shapes."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class Stamp(StrEnum):
    VERIFIED = "verified"
    ASSUMPTION = "assumption"
    CANNOT_VERIFY = "cannot_verify"


class Segment(StrEnum):
    ENTERPRISE = "Enterprise"
    MID_MARKET = "Mid-Market"
    SMB = "SMB"


class Region(StrEnum):
    WEST = "West"
    CENTRAL = "Central"
    NORTHEAST = "Northeast"
    SOUTHEAST = "Southeast"


# A validated viewer identity. "LEADERSHIP" sees everything; a rep_id like
# "REP-02" is scoped to that rep; anything else must fail closed (INV-10).
LEADERSHIP = "LEADERSHIP"


class Receipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    definition: str
    sql: str
    assumptions: list[str] = []
    rows: list[dict[str, Any]] = []
    row_count: str


class ToolResult(BaseModel):
    """The standard envelope every governed tool/function returns (spec §8)."""

    model_config = ConfigDict(frozen=True)

    stamp: Stamp
    value: dict[str, Any]
    answer_template: str
    receipt: Receipt
    interpretation: dict[str, Any] = {}
