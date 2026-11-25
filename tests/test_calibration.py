import random
from pathlib import Path

import pytest
from freight_agents.damage_assessor.calibration import (
    DEFAULT_FILE,
    Scored,
    calibrate,
    expected_calibration_error,
    load_calibration,
    reliability,
    threshold_for,
)


def batch(kind: str, confidence: float, correct: int, wrong: int) -> list[Scored]:
    return [Scored(kind, confidence, True)] * correct + [Scored(kind, confidence, False)] * wrong


def test_reliability_bins_count_every_prediction_and_measure_accuracy() -> None:
    scored = batch("crushed", 0.85, 8, 2) + batch("crushed", 0.35, 1, 3)
    bins = reliability(scored, bins=10)
    assert sum(b.count for b in bins) == 14
    (high,) = [b for b in bins if b.lo == pytest.approx(0.8)]
    assert high.count == 10
    assert high.accuracy == pytest.approx(0.8)
    assert high.mean_confidence == pytest.approx(0.85)
    (low,) = [b for b in bins if b.lo == pytest.approx(0.3)]
    assert low.accuracy == pytest.approx(0.25)


def test_a_confidence_of_one_lands_in_the_top_bin() -> None:
    bins = reliability(batch("wet", 1.0, 3, 0), bins=10)
    assert [b.count for b in bins if b.count] == [3]
    assert bins[-1].count == 3


def test_a_calibrated_model_has_a_small_calibration_error() -> None:
    rng = random.Random(11)
    scored = []
    for _ in range(4000):
        confidence = rng.random()
        scored.append(Scored("torn", confidence, rng.random() < confidence))
    assert expected_calibration_error(scored) < 0.03


def test_an_overconfident_model_has_a_large_one() -> None:
    scored = batch("torn", 0.95, 60, 40)
    assert expected_calibration_error(scored) == pytest.approx(0.35)


def test_the_threshold_is_the_lowest_confidence_that_keeps_precision_at_target() -> None:
    scored = (
        batch("crushed", 0.95, 10, 0) + batch("crushed", 0.85, 8, 2) + batch("crushed", 0.6, 3, 7)
    )
    # At 0.85 and above: 18 of 20 right (0.90). Adding 0.6: 21 of 30 (0.70).
    assert threshold_for(scored, "crushed", target=0.9) == pytest.approx(0.85)
    assert threshold_for(scored, "crushed", target=0.95) == pytest.approx(0.95)


def test_no_threshold_when_the_target_is_out_of_reach_or_the_sample_is_thin() -> None:
    assert threshold_for(batch("wet", 0.9, 5, 5), "wet", target=0.9) is None
    assert threshold_for(batch("wet", 0.9, 3, 0), "wet", target=0.9, min_support=5) is None


def test_calibrate_writes_thresholds_per_finding_type_and_reads_back(tmp_path: Path) -> None:
    scored = batch("crushed", 0.9, 19, 1) + batch("wet", 0.7, 5, 5)
    result = calibrate(scored, target=0.9, source="recorded", model="a-model", day="2026-11-24")
    assert result.thresholds["crushed"] == pytest.approx(0.9)
    assert result.thresholds["wet"] is None  # a person looks at every wet finding
    assert result.samples == 30
    path = tmp_path / "calibration.json"
    result.write(path)
    assert load_calibration(path) == result


def test_the_committed_default_says_real_numbers_come_from_a_recorded_run() -> None:
    default = load_calibration(DEFAULT_FILE)
    assert default.source == "default"
    assert "recorded run" in default.note
    assert set(default.thresholds) == {"crushed", "punctured", "wet", "torn", "shifted", "none"}
    assert all(t is not None and 0 < t < 1 for t in default.thresholds.values())
