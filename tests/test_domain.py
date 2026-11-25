import datetime as dt
from decimal import Decimal

import pytest
from freight_agents.damage_assessor.domain import (
    Assessment,
    Evidence,
    Finding,
    Outcome,
    Recommendation,
)
from freight_agents.damage_assessor.sources import SOURCES, passage
from pydantic import ValidationError

AT = dt.datetime(2026, 11, 24, 15, 0, tzinfo=dt.UTC)


def crushed(photo: str = "p1.jpg", confidence: float = 0.9) -> Finding:
    return Finding(
        photo=photo,
        damage_type="crushed",
        severity="severe",
        packaging_adequate=True,
        visibility="visible",
        confidence=confidence,
    )


def filed(amount: str = "1200.00") -> Recommendation:
    return Recommendation(
        outcome=Outcome.FILE_FULL,
        amount_usd=Decimal(amount),
        evidence=[
            Evidence(kind="finding", ref="p1.jpg", text="crushed, severe, visible, 0.90"),
            Evidence(kind="rule", ref="14706(a)", text="carrier liable for actual loss"),
        ],
    )


def test_a_finding_round_trips_through_json() -> None:
    finding = crushed()
    assert Finding.model_validate_json(finding.model_dump_json()) == finding


def test_what_a_photo_does_not_show_stays_null() -> None:
    finding = Finding(photo="blank.jpg", confidence=0.2)
    assert finding.damage_type is None
    assert finding.severity is None
    assert finding.packaging_adequate is None
    assert finding.visibility is None


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_confidence_outside_zero_to_one_is_refused(confidence: float) -> None:
    with pytest.raises(ValidationError):
        crushed(confidence=confidence)


def test_an_unknown_damage_type_is_refused() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate({"photo": "p1.jpg", "damage_type": "exploded", "confidence": 0.5})


@pytest.mark.parametrize(
    ("outcome", "waits"),
    [
        (Outcome.FILE_FULL, False),
        (Outcome.FILE_PARTIAL, False),
        (Outcome.SALVAGE_THEN_FILE, False),
        (Outcome.DENY, True),
        (Outcome.INSPECT, True),
    ],
)
def test_deny_and_inspect_always_wait_for_a_person(outcome: Outcome, waits: bool) -> None:
    amount = None if outcome in (Outcome.DENY, Outcome.INSPECT) else Decimal("10.00")
    rec = Recommendation(outcome=outcome, amount_usd=amount, evidence=filed().evidence)
    assert rec.needs_person is waits


def test_a_filing_outcome_needs_a_positive_amount() -> None:
    with pytest.raises(ValidationError):
        Recommendation(outcome=Outcome.FILE_FULL, amount_usd=None, evidence=filed().evidence)
    with pytest.raises(ValidationError):
        filed("0.00")
    with pytest.raises(ValidationError):
        filed("-5.00")


def test_salvage_covering_the_whole_value_leaves_zero_to_file_never_less() -> None:
    rec = Recommendation(
        outcome=Outcome.SALVAGE_THEN_FILE, amount_usd=Decimal("0.00"), evidence=filed().evidence
    )
    assert rec.amount_usd == Decimal("0.00")
    with pytest.raises(ValidationError):
        Recommendation(
            outcome=Outcome.SALVAGE_THEN_FILE,
            amount_usd=Decimal("-1.00"),
            evidence=filed().evidence,
        )


def test_deny_and_inspect_carry_no_amount() -> None:
    with pytest.raises(ValidationError):
        Recommendation(outcome=Outcome.DENY, amount_usd=Decimal("10.00"), evidence=filed().evidence)


def test_a_recommendation_cites_its_evidence() -> None:
    with pytest.raises(ValidationError):
        Recommendation(outcome=Outcome.INSPECT, amount_usd=None, evidence=[])


def test_an_amount_above_the_documented_value_is_refused() -> None:
    with pytest.raises(ValidationError):
        Assessment(
            claim_id="CLM-1",
            documented_value_usd=Decimal("1000.00"),
            findings=[crushed()],
            recommendation=filed("1200.00"),
            assessed_at=AT,
            mode="reference",
        )


def test_an_assessment_round_trips_through_json() -> None:
    assessment = Assessment(
        claim_id="CLM-1",
        documented_value_usd=Decimal("1200.00"),
        findings=[crushed()],
        recommendation=filed("1200.00"),
        assessed_at=AT,
        mode="reference",
    )
    assert Assessment.model_validate_json(assessment.model_dump_json()) == assessment


def test_every_legal_source_resolves_to_a_knowledge_passage() -> None:
    legal = [s for s in SOURCES.values() if not s.practice]
    assert {s.id for s in legal} >= {"14706(a)", "370.3(b)", "370.7", "370.11"}
    for source in legal:
        found = passage(source.id)
        assert found.heading == source.heading
        assert found.source_url.startswith("https://")


def test_practice_is_labeled_and_cites_no_law() -> None:
    practice = [s for s in SOURCES.values() if s.practice]
    assert practice
    for source in practice:
        assert source.id.startswith("practice:")
        with pytest.raises(LookupError):
            passage(source.id)


def test_an_amount_needs_a_documented_value_but_an_inspect_does_not() -> None:
    with pytest.raises(ValidationError):
        Assessment(
            claim_id="CLM-1",
            documented_value_usd=None,
            findings=[crushed()],
            recommendation=filed("100.00"),
            assessed_at=AT,
            mode="reference",
        )
    inspect = Recommendation(outcome=Outcome.INSPECT, amount_usd=None, evidence=filed().evidence)
    assessment = Assessment(
        claim_id="CLM-1",
        documented_value_usd=None,
        findings=[],
        recommendation=inspect,
        assessed_at=AT,
        mode="reference",
    )
    assert assessment.documented_value_usd is None
