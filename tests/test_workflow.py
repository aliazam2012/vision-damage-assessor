import json
from decimal import Decimal
from pathlib import Path

import pytest
from freight_agents.claims_intake.domain import ClaimFields
from freight_agents.damage_assessor.workflow import AssessmentDesk, Stores, reference_models
from freight_agents.integrations.tms import FixtureTms

from .conftest import FIELDS, SHIPMENT, T0, World, claim_email, labels


def test_a_crushed_carton_is_filed_and_handed_off_for_filing(world: World) -> None:
    case = world.claim(["carton-crushed-severe-1.png"])
    assert case.state == "handed_off"
    assessed = world.desk.stores.engine.view(case.case_id)
    assert assessed.state == "handed_off"
    assert assessed.data["assessment"]["recommendation"]["outcome"] == "file_full"
    # carrier-filing builds its packet from these fields: the claim, under the $2,400 value.
    assert case.data["fields"]["claimed_amount_usd"] == 800.0
    assert case.data["assessment"]["decided_by"] == "rules"


def test_no_damage_waits_for_a_person_and_nothing_is_handed_off(world: World) -> None:
    case = world.claim(["carton-none-none-1.png"])
    assert case.state == "ready_to_file"
    assert world.desk.stores.engine.view(case.case_id).state == "waiting"
    assert [c.case_id for c in world.desk.waiting()] == [case.case_id]


def test_a_person_files_an_inspected_claim_at_the_amount_they_set(world: World) -> None:
    case = world.claim(["carton-torn-moderate-1.png"])  # partial, no repair cost: inspect
    assert world.desk.stores.engine.view(case.case_id).state == "waiting"
    world.desk.resolve(case.case_id, "U-lee", Decimal("300.00"))
    claims = world.claims_case(case.case_id)
    assert claims.state == "handed_off"
    assert claims.data["fields"]["claimed_amount_usd"] == 300.0
    assert claims.data["assessment"]["decided_by"] == "U-lee"
    assert world.desk.waiting() == []


def test_a_person_can_decline_and_nothing_is_filed(world: World) -> None:
    case = world.claim(["carton-none-none-1.png"])
    assert world.desk.resolve(case.case_id, "U-lee", None).state == "declined"
    assert world.claims_case(case.case_id).state == "ready_to_file"


@pytest.mark.parametrize("amount", ["900.00", "3000.00", "0.00"])
def test_a_person_cannot_file_more_than_the_claim_supports(world: World, amount: str) -> None:
    case = world.claim(["carton-torn-moderate-1.png"])
    with pytest.raises(ValueError, match="amount"):
        world.desk.resolve(case.case_id, "U-lee", Decimal(amount))
    assert world.desk.stores.engine.view(case.case_id).state == "waiting"
    assert world.claims_case(case.case_id).state == "ready_to_file"


def test_photos_reference_mode_does_not_know_go_to_a_person(world: World) -> None:
    case = world.claim(["IMG_0001.png"])
    assessed = world.desk.stores.engine.view(case.case_id)
    assert assessed.state == "waiting"
    assert assessed.data["assessment"]["recommendation"]["outcome"] == "inspect"


def test_assessing_the_same_claim_twice_changes_nothing(world: World) -> None:
    message = claim_email(["carton-crushed-severe-1.png"])
    case = world.intake.process(message)
    again = world.desk.assess(case.case_id, ClaimFields.model_validate(FIELDS), message)
    assert again.state == "handed_off"
    assert world.claims_case(case.case_id).state == "handed_off"


def test_a_shipment_the_tms_does_not_know_goes_to_a_person(world: World) -> None:
    fields = ClaimFields.model_validate({**FIELDS, "pro_number": "0000-0000"})
    message = claim_email(["carton-crushed-severe-1.png"])
    assessed = world.desk.assess("clm_unknown", fields, message)
    assert assessed.state == "waiting"
    evidence = assessed.data["assessment"]["recommendation"]["evidence"]
    assert any(e["ref"] == "370.7" for e in evidence)


def test_a_person_cannot_file_above_the_documented_value_even_within_the_claim(
    tmp_path: Path,
) -> None:
    cheap = {**SHIPMENT, "declared_value_usd": 500.0}  # the claim asks $800 for $500 of goods
    (tmp_path / "tms.json").write_text(json.dumps([cheap]))
    filed: list[float] = []
    desk = AssessmentDesk(
        Stores.at(tmp_path / "damage"),
        tms=FixtureTms(tmp_path / "tms.json"),
        hand_off=lambda case_id, amount, summary, by: filed.append(amount),
        models=reference_models(labels()),
        clock=lambda: T0,
    )
    message = claim_email(["carton-torn-moderate-1.png"])
    desk.assess("clm_cheap", ClaimFields.model_validate(FIELDS), message)
    with pytest.raises(ValueError, match="documented value"):
        desk.resolve("clm_cheap", "U-lee", Decimal("600.00"))
    desk.resolve("clm_cheap", "U-lee", Decimal("500.00"))
    assert filed == [500.0]


def test_only_a_claim_that_is_waiting_can_be_resolved(world: World) -> None:
    case = world.claim(["carton-crushed-severe-1.png"])  # already filed by the rules
    with pytest.raises(ValueError, match="not waiting"):
        world.desk.resolve(case.case_id, "U-lee", None)


def test_an_assessment_whose_hand_off_failed_resumes_on_the_next_run(tmp_path: Path) -> None:
    (tmp_path / "tms.json").write_text(json.dumps([SHIPMENT]))
    filed: list[float] = []
    failures = [RuntimeError("claims store busy")]

    def hand_off(case_id: str, amount: float, summary: object, by: str) -> None:
        if failures:
            raise failures.pop()
        filed.append(amount)

    desk = AssessmentDesk(
        Stores.at(tmp_path / "damage"),
        tms=FixtureTms(tmp_path / "tms.json"),
        hand_off=hand_off,
        models=reference_models(labels()),
        clock=lambda: T0,
    )
    message = claim_email(["carton-crushed-severe-1.png"])
    fields = ClaimFields.model_validate(FIELDS)
    with pytest.raises(RuntimeError):
        desk.assess("clm_retry", fields, message)
    assert desk.assess("clm_retry", fields, message).state == "handed_off"
    assert filed == [800.0]
