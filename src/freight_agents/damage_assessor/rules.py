"""Findings and the claim's documents become a recommendation, in code.

The rules read only findings (never the model's words) and the claim's documented facts.
In order: no usable finding, a worst finding below its calibrated threshold, concealed
damage after a clean delivery, and inadequate packaging each go to a person (inspect).
No damage in any credible finding is a deny, which also waits for a person. Severe or
total damage is filed as a loss of the goods, less any salvage; minor or moderate damage
is filed at its documented repair cost. Every amount is capped at the documented value
and at what the claimant asked for, and is never negative.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from freight_agents.damage_assessor.calibration import Calibration
from freight_agents.damage_assessor.domain import Evidence, Finding, Outcome, Recommendation
from freight_agents.damage_assessor.sources import SOURCES
from pydantic import BaseModel, ConfigDict, Field

CENT = Decimal("0.01")
RANK = {"none": 0, "minor": 1, "moderate": 2, "severe": 3, "total": 4}
LOSS = {"severe", "total"}


class ClaimFacts(BaseModel):
    """What the claim's documents say, beside the photos."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    documented_value_usd: Decimal = Field(ge=0)  # invoice or certified value (370.7)
    claimed_amount_usd: Decimal | None = Field(default=None, ge=0)  # 370.3(b)
    repair_cost_usd: Decimal | None = Field(default=None, ge=0)
    salvage_value_usd: Decimal | None = Field(default=None, ge=0)
    delivery_exception: bool = False  # damage noted on the delivery receipt
    reported_after_delivery: bool = False


def _rule(source_id: str) -> Evidence:
    return Evidence(kind="rule", ref=source_id, text=SOURCES[source_id].says)


def _seen(f: Finding) -> Evidence:
    parts: list[str | None] = [f.damage_type, f.severity, f.visibility]
    if f.packaging_adequate is False:
        parts.append("packaging inadequate")
    described = ", ".join(p for p in parts if p) or "nothing usable"
    return Evidence(kind="finding", ref=f.photo, text=f"{described}, {f.confidence:.2f}")


def _document(name: str, amount: Decimal) -> Evidence:
    return Evidence(kind="document", ref=name, text=f"${amount:,.2f}")


def _credible(f: Finding, calibration: Calibration) -> bool:
    if f.damage_type is None:
        return False
    threshold = calibration.thresholds.get(f.damage_type)
    return threshold is not None and f.confidence >= threshold


def _worst(findings: Sequence[Finding]) -> Finding | None:
    usable = [f for f in findings if f.damage_type is not None]
    if not usable:
        return None
    return max(usable, key=lambda f: (RANK.get(f.severity or "", 5), f.confidence))


def _inspect(evidence: list[Evidence], *sources: str) -> Recommendation:
    return Recommendation(
        outcome=Outcome.INSPECT,
        amount_usd=None,
        evidence=[*evidence, *(_rule(s) for s in sources)],
    )


def decide(
    findings: Sequence[Finding], facts: ClaimFacts, calibration: Calibration
) -> Recommendation:
    seen = [_seen(f) for f in findings] or [
        Evidence(kind="document", ref=facts.claim_id, text="no photos")
    ]
    worst = _worst(findings)
    if worst is None:
        return _inspect(seen, "practice:confidence")
    if not _credible(worst, calibration) or worst.severity is None:
        return _inspect([_seen(worst)], "practice:confidence")
    credible = [f for f in findings if _credible(f, calibration)]

    concealed = worst.visibility == "concealed" or facts.reported_after_delivery
    if concealed and not facts.delivery_exception:
        return _inspect([_seen(worst)], "practice:concealed-damage")
    flawed = [f for f in credible if f.packaging_adequate is False]
    if flawed:
        return _inspect([_seen(f) for f in flawed], "practice:packaging")
    if worst.damage_type == "none":
        return Recommendation(
            outcome=Outcome.DENY,
            amount_usd=None,
            evidence=[*(_seen(f) for f in credible), _rule("14706(a)")],
        )

    value = facts.documented_value_usd
    cap = min(value, facts.claimed_amount_usd) if facts.claimed_amount_usd is not None else value
    evidence = [
        _seen(worst),
        _document("documented value", value),
        _rule("14706(a)"),
        _rule("370.7"),
        _rule("practice:severity-to-loss"),
    ]
    if worst.severity in LOSS:
        if facts.salvage_value_usd is not None:
            left = max(Decimal(0), value - facts.salvage_value_usd)
            return Recommendation(
                outcome=Outcome.SALVAGE_THEN_FILE,
                amount_usd=min(left, cap).quantize(CENT, ROUND_HALF_UP),
                evidence=[
                    *evidence,
                    _document("salvage value", facts.salvage_value_usd),
                    _rule("370.11"),
                    _rule("practice:salvage-credit"),
                ],
            )
        return _file(Outcome.FILE_FULL, cap, evidence)
    if facts.repair_cost_usd is None:
        return _inspect([_seen(worst)], "370.3(b)", "practice:severity-to-loss")
    return _file(
        Outcome.FILE_PARTIAL,
        min(facts.repair_cost_usd, cap),
        [*evidence, _document("repair cost", facts.repair_cost_usd)],
    )


def _file(outcome: Outcome, amount: Decimal, evidence: list[Evidence]) -> Recommendation:
    amount = amount.quantize(CENT, ROUND_HALF_UP)
    if amount <= 0:  # nothing documented to file: a person values it
        return _inspect(evidence, "370.3(b)")
    return Recommendation(outcome=outcome, amount_usd=amount, evidence=evidence)
