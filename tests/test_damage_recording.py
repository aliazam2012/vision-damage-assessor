from pathlib import Path

import pytest
from freight_agents.damage_assessor.evaluation import (
    FLOORS,
    GOLDEN,
    load_shipments,
    record,
    recorded_calibration,
    run_recorded,
    write_report,
)
from freight_agents.damage_assessor.extract import reference_model
from freight_agents.damage_assessor.images import labels_by_image
from freight_agents.evals.recording import StaleCassette
from freight_agents.llm import Message, Model, ModelTurn, ToolSpec, Usage

DATA = Path(__file__).resolve().parents[3] / "data" / "damage"
SHIPMENTS = {s.id: s for s in load_shipments(GOLDEN)}
LABELS = {name: label.finding for name, label in labels_by_image(DATA).items()}


class PricedAs:
    def __init__(self, inner: Model) -> None:
        self._inner = inner

    @property
    def name(self) -> str:
        return "claude-opus-5-5"

    def complete(self, system: str, messages: list[Message], tools: list[ToolSpec]) -> ModelTurn:
        turn = self._inner.complete(system, messages, tools)
        usage = Usage(input_tokens=1_200, output_tokens=150)
        return turn.model_copy(update={"model": "claude-opus-5-5", "usage": usage})


def live_reference(case_id: str) -> Model:
    photos = SHIPMENTS[case_id].photos
    return PricedAs(reference_model({p: LABELS[p] for p in photos}))


@pytest.fixture(scope="module")
def cassettes(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("cassettes")
    assert record(DATA, out, live_reference, cap=20.0).code == 0
    return out


def test_every_golden_shipment_is_recorded(cassettes: Path) -> None:
    assert {p.stem for p in cassettes.glob("*.jsonl")} == set(SHIPMENTS)


def test_recorded_mode_replays_through_the_same_gate(cassettes: Path, tmp_path: Path) -> None:
    result = run_recorded(DATA, cassettes, "claude-opus-5-5")
    assert result.failures(FLOORS) == []
    path = write_report(result, tmp_path, "2026-11-25", mode="recorded", model="claude-opus-5-5")
    assert path.name == "2026-11-25-recorded.md"
    text = path.read_text()
    assert "recorded turns of claude-opus-5-5" in text
    assert "by construction" not in text


def test_calibration_from_a_recorded_run_says_so(cassettes: Path) -> None:
    result = run_recorded(DATA, cassettes, "claude-opus-5-5")
    calibration = recorded_calibration(result, "claude-opus-5-5", "2026-11-25")
    assert calibration.source == "recorded"
    assert calibration.model == "claude-opus-5-5"
    assert calibration.samples == sum(len(s.photos) for s in SHIPMENTS.values())


def test_a_missing_cassette_fails_naming_the_shipment(cassettes: Path, tmp_path: Path) -> None:
    victim, *rest = sorted(cassettes.glob("*.jsonl"))
    for path in rest:
        (tmp_path / path.name).write_bytes(path.read_bytes())
    with pytest.raises(StaleCassette, match=victim.stem):
        run_recorded(DATA, tmp_path, "claude-opus-5-5")


def test_the_eval_command_refuses_to_record_without_a_cap(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    from freight_agents.damage_assessor.cli import main

    code = main(["eval", "--mode", "record", "--cassettes", str(tmp_path), "--data", str(DATA)])
    assert code == 2
    assert "--max-usd" in capsys.readouterr().out


def test_thresholds_are_only_written_from_a_recorded_run(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    from freight_agents.damage_assessor.calibration import DEFAULT_FILE
    from freight_agents.damage_assessor.cli import main

    before = DEFAULT_FILE.read_text()
    args = ["eval", "--write-calibration", "--data", str(DATA), "--reports", str(tmp_path)]
    assert main(args) == 2
    assert "--mode recorded" in capsys.readouterr().out
    assert DEFAULT_FILE.read_text() == before
