import json
from pathlib import Path

import pytest
from freight_agents.damage_assessor.domain import Finding
from freight_agents.damage_assessor.images import (
    ALLOWED_LICENSES,
    load_labels,
    load_manifest,
    parse_manifest,
    write_synthetic,
)
from PIL import Image

DATA = Path(__file__).resolve().parents[3] / "data" / "damage"


@pytest.fixture(scope="module")
def drawn(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("synthetic")
    write_synthetic(directory, seed=7)
    return directory


def test_the_same_seed_draws_the_same_bytes(drawn: Path, tmp_path: Path) -> None:
    write_synthetic(tmp_path / "again", seed=7)
    write_synthetic(tmp_path / "other", seed=8)
    images = sorted(p.name for p in drawn.glob("*.png"))
    assert images
    for name in images:
        assert (drawn / name).read_bytes() == (tmp_path / "again" / name).read_bytes()
    assert any(
        (drawn / name).read_bytes() != (tmp_path / "other" / name).read_bytes() for name in images
    )


def test_every_synthetic_label_names_its_image_and_validates_as_a_finding(drawn: Path) -> None:
    labels = load_labels(drawn / "labels.jsonl")
    assert len(labels) == len(list(drawn.glob("*.png")))
    for label in labels:
        assert label.origin == "synthetic"
        assert label.finding.photo == label.image
        assert (drawn / label.image).exists()
        Finding.model_validate(label.finding.model_dump())
        with Image.open(drawn / label.image) as im:
            assert im.size == (320, 240)


def test_the_set_covers_every_damage_type_both_subjects_and_the_hard_cases(drawn: Path) -> None:
    labels = load_labels(drawn / "labels.jsonl")
    freight = [x for x in labels if x.freight]
    assert {x.finding.damage_type for x in freight} == {
        "crushed",
        "punctured",
        "wet",
        "torn",
        "shifted",
        "none",
    }
    assert {x.subject for x in labels} == {"carton", "pallet", "blank", "document"}
    assert any(x.finding.visibility == "concealed" for x in freight)
    assert any(x.finding.packaging_adequate is False for x in freight)
    assert len([x for x in labels if x.injected_text]) >= 3
    not_freight = [x for x in labels if not x.freight]
    assert not_freight
    for x in not_freight:  # nothing to see on a blank frame or a document scan
        assert x.finding.damage_type is None
        assert x.finding.severity is None


def test_the_committed_synthetic_labels_match_the_generator(tmp_path: Path) -> None:
    write_synthetic(tmp_path)  # the default seed, as data/generate_damage.py runs it
    committed = DATA / "synthetic" / "labels.jsonl"
    assert (tmp_path / "labels.jsonl").read_text() == committed.read_text()


def test_every_licensed_photo_carries_its_license_attribution_and_source() -> None:
    photos = load_manifest(DATA / "licensed" / "manifest.json")
    assert len(photos) >= 8
    for photo in photos:
        assert photo.license in ALLOWED_LICENSES
        assert photo.author
        assert photo.source_url.startswith("https://commons.wikimedia.org/wiki/File:")
        assert photo.changes
        assert (DATA / "licensed" / photo.label.image).exists()
        assert photo.label.origin == "licensed"
        assert photo.label.finding.photo == photo.label.image


def test_share_alike_and_non_commercial_licenses_are_refused() -> None:
    for name in ("CC BY-SA 4.0", "CC BY-NC 2.0", "CC BY-ND 3.0"):
        assert name not in ALLOWED_LICENSES
    raw = json.loads((DATA / "licensed" / "manifest.json").read_text())
    raw[0]["license"] = "CC BY-SA 4.0"
    with pytest.raises(ValueError, match="license"):
        parse_manifest(raw)


def test_concealed_damage_leaves_the_outside_of_the_carton_unmarked() -> None:
    import random

    from freight_agents.damage_assessor.images import Spec, draw

    concealed = Spec("c", "carton", "crushed", "moderate", concealed=True)
    intact = Spec("c", "carton", "none", "none", concealed=True)
    # Same seed, same carton: only the label differs, so the pixels must not.
    assert draw(concealed, random.Random(5)).tobytes() == draw(intact, random.Random(5)).tobytes()


def test_the_attribution_file_credits_every_licensed_photo() -> None:
    credits = (DATA / "README.md").read_text()
    for photo in load_manifest(DATA / "licensed" / "manifest.json"):
        assert photo.label.image in credits
        assert photo.author in credits
        assert photo.license in credits
        assert photo.source_url in credits
