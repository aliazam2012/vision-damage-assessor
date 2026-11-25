"""How far to trust a model's confidence, measured on labeled photos.

Each prediction is scored against its label: the finding type the model gave, its
confidence, and whether the label agrees. Reliability bins and the expected calibration
error show whether a confidence of 0.8 is right about 80% of the time. For each finding
type, the threshold is the lowest confidence at which the predictions at or above it still
meet the target precision; below it, code does not act on a finding and a person looks.
A type that never reaches the target, or has too few samples, gets no threshold at all.

The committed `calibration.json` is a conservative default, not a measurement. Real
thresholds come from a recorded run of a real model over the labeled set.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

DEFAULT_FILE = Path(__file__).resolve().parent / "calibration.json"


@dataclass(frozen=True)
class Scored:
    kind: str  # the finding type the model gave
    confidence: float
    correct: bool  # the label agrees


class Bin(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lo: float
    hi: float
    count: int
    mean_confidence: float
    accuracy: float


class Calibration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Literal["default", "reference", "recorded"]
    model: str
    measured_on: str
    target_precision: float
    samples: int
    ece: float | None
    bins: list[Bin]
    thresholds: dict[str, float | None]
    note: str

    def write(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2) + "\n")


def load_calibration(path: Path = DEFAULT_FILE) -> Calibration:
    return Calibration.model_validate_json(path.read_text())


def reliability(scored: Sequence[Scored], bins: int = 10) -> list[Bin]:
    width = 1.0 / bins
    out = []
    for k in range(bins):
        lo, hi = k * width, (k + 1) * width
        inside = [
            s for s in scored if lo <= s.confidence < hi or (k == bins - 1 and s.confidence == 1.0)
        ]
        count = len(inside)
        out.append(
            Bin(
                lo=round(lo, 6),
                hi=round(hi, 6),
                count=count,
                mean_confidence=sum(s.confidence for s in inside) / count if count else 0.0,
                accuracy=sum(s.correct for s in inside) / count if count else 0.0,
            )
        )
    return out


def expected_calibration_error(scored: Sequence[Scored], bins: int = 10) -> float:
    total = len(scored)
    if not total:
        return 0.0
    return sum(
        b.count / total * abs(b.accuracy - b.mean_confidence) for b in reliability(scored, bins)
    )


def threshold_for(
    scored: Sequence[Scored], kind: str, target: float, min_support: int = 5
) -> float | None:
    """The lowest confidence whose predictions at or above it meet the target precision."""
    mine = [s for s in scored if s.kind == kind]
    best = None
    for cut in sorted({s.confidence for s in mine}, reverse=True):
        kept = [s for s in mine if s.confidence >= cut]
        if len(kept) >= min_support and sum(s.correct for s in kept) / len(kept) >= target:
            best = cut
    return best


def calibrate(
    scored: Sequence[Scored],
    target: float,
    source: Literal["default", "reference", "recorded"],
    model: str,
    day: str,
    bins: int = 10,
) -> Calibration:
    kinds = sorted({s.kind for s in scored})
    return Calibration(
        source=source,
        model=model,
        measured_on=day,
        target_precision=target,
        samples=len(scored),
        ece=round(expected_calibration_error(scored, bins), 4),
        bins=reliability(scored, bins),
        thresholds={kind: threshold_for(scored, kind, target) for kind in kinds},
        note=(
            f"Measured on {len(scored)} labeled findings from a {source} run of {model}."
            if source == "recorded"
            else f"A {source} run: real thresholds come from a recorded run of a real model."
        ),
    )
