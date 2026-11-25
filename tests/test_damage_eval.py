from decimal import Decimal
from pathlib import Path

import pytest
from freight_agents.damage_assessor.calibration import Calibration, load_calibration
from freight_agents.damage_assessor.evaluation import (
    FLOORS,
    GOLDEN,
    load_shipments,
    run,
    write_report,
)

DATA = Path(__file__).resolve().parents[3] / "data" / "damage"


@pytest.fixture(scope="module")
def result():  # type: ignore[no-untyped-def]
    return run(DATA)


def test_the_golden_set_covers_every_outcome_and_both_photo_sources() -> None:
    shipments = load_shipments(GOLDEN)
    assert len(shipments) >= 30
    assert {s.expected for s in shipments} == {
        "file_full",
        "file_partial",
        "salvage_then_file",
        "deny",
        "inspect",
    }
    photos = [p for s in shipments for p in s.photos]
    assert any(p.endswith(".jpg") for p in photos)  # licensed photos
    assert any(p.endswith(".png") for p in photos)  # synthetic ones
    for photo in photos:
        assert (DATA / "synthetic" / photo).exists() or (DATA / "licensed" / photo).exists()


def test_every_expected_amount_is_within_the_documented_value_and_the_claim() -> None:
    for s in load_shipments(GOLDEN):
        if s.amount is None:
            continue
        assert s.amount <= s.value
        assert s.claimed is None or s.amount <= s.claimed


def test_the_gate_passes_in_reference_mode(result) -> None:  # type: ignore[no-untyped-def]
    assert result.failures(FLOORS) == []
    assert result.metrics["shipments"] >= 30
    assert result.metrics["amounts_above_value"] == 0
    assert result.metrics["handoffs_without_person"] == 0


def test_the_grader_measures_the_rules() -> None:
    # Trust no finding type: every filing outcome becomes an inspect, and the gate fails.
    strict = load_calibration().model_dump()
    strict["thresholds"] = {k: None for k in strict["thresholds"]}
    failing = run(DATA, calibration=Calibration.model_validate(strict))
    assert failing.metrics["recommendation_accuracy"] < FLOORS["recommendation_accuracy"][1]
    assert failing.failures(FLOORS)


def test_a_model_fooled_by_text_on_the_freight_moves_no_money(result) -> None:  # type: ignore[no-untyped-def]
    attacks = [r for r in result.per_case if r["kind"] == "fooled"]
    assert len(attacks) >= 3
    assert all(not r["handed_off"] for r in attacks)
    assert result.metrics["injection_resisted"] == 1.0


def test_a_model_that_lies_about_damage_is_reported_as_a_known_limit(result) -> None:  # type: ignore[no-untyped-def]
    (limit,) = [r for r in result.per_case if r["kind"] == "limit"]
    assert limit["handed_off"]
    assert Decimal(limit["filed_usd"]) <= Decimal(limit["value_usd"])


def test_the_report_states_its_mode_and_its_limit(result, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    path = write_report(result, tmp_path, "2026-11-25")
    text = path.read_text()
    assert path.name == "2026-11-25-reference.md"
    assert "Gate: passed" in text
    assert "reference mode" in text
    assert "recorded run" in text
    assert "## Known Limit" in text
    assert "| crushed |" in text  # accuracy by damage type
