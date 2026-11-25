"""Draw the synthetic damage photos and their labels into data/damage/synthetic/.

Run: uv run --all-packages python data/generate_damage.py
"""

from __future__ import annotations

from pathlib import Path

from freight_agents.damage_assessor.images import write_synthetic

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    labels = write_synthetic(ROOT / "data" / "damage" / "synthetic")
    print(f"{len(labels)} synthetic images written to data/damage/synthetic/")
