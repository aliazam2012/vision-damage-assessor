"""What a photo shows, and what code recommends from it.

A `Finding` is what a vision model saw in one photo, recorded through a strict tool:
every field it cannot see stays null. A `Recommendation` is what the rules decide from
the findings, the documented value and any salvage; the model never writes one. The
types carry the guarantees a person relies on: a deny or an inspect always waits for a
person, an amount is never negative, never above the documented value, and every
recommendation cites its evidence.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DamageType = Literal["crushed", "punctured", "wet", "torn", "shifted", "none"]
Severity = Literal["none", "minor", "moderate", "severe", "total"]
Visibility = Literal["visible", "concealed"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Finding(_Frozen):
    photo: str
    damage_type: DamageType | None = None
    severity: Severity | None = None
    packaging_adequate: bool | None = None
    visibility: Visibility | None = None
    confidence: float = Field(ge=0, le=1)


class Outcome(StrEnum):
    FILE_FULL = "file_full"
    FILE_PARTIAL = "file_partial"
    SALVAGE_THEN_FILE = "salvage_then_file"
    DENY = "deny"
    INSPECT = "inspect"


PERSON_DECIDES = frozenset({Outcome.DENY, Outcome.INSPECT})


class Evidence(_Frozen):
    kind: Literal["finding", "rule", "document"]
    ref: str  # a photo, a source id from sources.SOURCES, or a document name
    text: str


class Recommendation(_Frozen):
    outcome: Outcome
    amount_usd: Decimal | None
    evidence: list[Evidence] = Field(min_length=1)

    @property
    def needs_person(self) -> bool:
        return self.outcome in PERSON_DECIDES

    @model_validator(mode="after")
    def _amount_fits_outcome(self) -> Self:
        amount = self.amount_usd
        if self.outcome in PERSON_DECIDES:
            if amount is not None:
                raise ValueError(f"{self.outcome} carries no amount; a person decides")
        elif amount is None:
            raise ValueError(f"{self.outcome} needs an amount")
        elif amount < 0:
            raise ValueError("an amount is never negative")
        elif amount == 0 and self.outcome != Outcome.SALVAGE_THEN_FILE:
            raise ValueError(f"{self.outcome} needs an amount above zero")
        return self


class Assessment(_Frozen):
    claim_id: str
    documented_value_usd: Decimal | None = Field(ge=0)  # None: no invoice or TMS value found
    findings: list[Finding]
    recommendation: Recommendation
    assessed_at: dt.datetime
    mode: Literal["reference", "live"]

    @model_validator(mode="after")
    def _amount_within_documented_value(self) -> Self:
        amount, value = self.recommendation.amount_usd, self.documented_value_usd
        if amount is not None and value is None:
            raise ValueError("an amount needs a documented value")
        if amount is not None and value is not None and amount > value:
            raise ValueError(
                f"recommended {amount} is above the documented value {self.documented_value_usd}"
            )
        return self
