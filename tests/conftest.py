import datetime as dt
import json
from email.message import EmailMessage as Mime
from pathlib import Path
from typing import Any

import pytest
from freight_agents.claims_intake.workflow import ClaimsIntake
from freight_agents.claims_intake.workflow import Stores as ClaimsStores
from freight_agents.damage_assessor.images import load_labels, load_manifest
from freight_agents.damage_assessor.workflow import AssessmentDesk, Stores, reference_models
from freight_agents.integrations.email import EmailMessage, parse_eml
from freight_agents.integrations.tms import FixtureTms
from freight_agents.llm import ModelTurn, ScriptedModel, ToolCall, Usage
from freight_agents.statecore.machine import CaseView

DATA = Path(__file__).resolve().parents[3] / "data" / "damage"
T0 = dt.datetime(2026, 11, 24, 10, 0, tzinfo=dt.UTC)
SHIPMENT = {
    "pro_number": "7741-2209",
    "bol_number": "BOL-55102",
    "carrier": "Example Freight Lines",
    "shipper": "Larkspur Home Goods",
    "consignee": "Harbor Street Furniture",
    "ship_date": "2026-11-02",
    "delivery_date": "2026-11-09",
    "commodity": "dining chairs",
    "declared_value_usd": 2400.0,
    "pieces": 12,
    "weight_lb": 640.0,
}
FIELDS: dict[str, Any] = {
    "pro_number": "7741-2209",
    "bol_number": None,
    "carrier": "Example Freight Lines",
    "ship_date": "2026-11-02",
    "delivery_date": "2026-11-09",
    "commodity": "dining chairs",
    "claim_type": "damage",
    "damage_description": "4 of 12 chairs arrived with broken legs",
    "claimed_amount_usd": 800.0,
    "claimant_name": "Dana Reyes",
    "claimant_email": "dana@example.com",
    "photo_count": 1,
}


def labels() -> dict[str, Any]:
    found = {x.image: x.finding for x in load_labels(DATA / "synthetic" / "labels.jsonl")}
    for photo in load_manifest(DATA / "licensed" / "manifest.json"):
        found[photo.label.image] = photo.label.finding
    return found


def claim_email(photos: list[str]) -> EmailMessage:
    return parse_eml(claim_eml(photos))


def claim_eml(photos: list[str]) -> bytes:
    msg = Mime()
    msg["Message-ID"] = f"<{'-'.join(photos)}@example.com>"
    msg["From"] = "Dana Reyes <dana@example.com>"
    msg["To"] = "claims@example.org"
    msg["Subject"] = "Damage claim PRO 7741-2209"
    msg["Date"] = "Mon, 16 Nov 2026 09:30:00 -0800"
    msg.set_content("4 of 12 chairs arrived with broken legs. Claiming $800. Photos attached.")
    for name in photos:
        path = DATA / "synthetic" / name
        data = path.read_bytes() if path.exists() else b"\x89PNG not a known photo"
        msg.add_attachment(data, maintype="image", subtype="png", filename=name)
    return msg.as_bytes()


def _turn(*calls: ToolCall) -> ModelTurn:
    stop = "tool_use" if calls else "end"
    return ModelTurn(text="", tool_calls=list(calls), stop=stop, usage=Usage(), model="scripted")


def intake_script(fields: dict[str, Any]) -> list[ModelTurn]:
    return [
        _turn(ToolCall(id="t1", name="submit_triage", args={"label": "claim", "reason": "test"})),
        _turn(),
        _turn(ToolCall(id="l1", name="lookup_shipment", args={"pro_number": "7741-2209"})),
        _turn(ToolCall(id="s1", name="save_claim_fields", args={"fields": fields})),
        _turn(),
    ]


class World:
    def __init__(self, root: Path) -> None:
        tms_path = root / "tms.json"
        tms_path.write_text(json.dumps([SHIPMENT]))
        self.tms = FixtureTms(tms_path)
        self.intake = ClaimsIntake(
            model=ScriptedModel(intake_script(FIELDS)),
            tms=self.tms,
            stores=ClaimsStores.at(root / "claims", lambda: T0),
            clock=lambda: T0,
        )
        self.desk = AssessmentDesk(
            Stores.at(root / "damage"),
            tms=self.tms,
            hand_off=self.intake.hand_off,
            models=reference_models(labels()),
            clock=lambda: T0,
        )
        self.intake.assessor = self.desk

    def claim(self, photos: list[str]) -> CaseView:
        return self.intake.process(claim_email(photos))

    def claim_with(self, photos: list[str]) -> CaseView:
        """A second claim in the same world: the scripted intake model needs a fresh script."""
        self.intake.model = ScriptedModel(intake_script(FIELDS))
        return self.claim(photos)

    def claims_case(self, case_id: str) -> CaseView:
        return self.intake.stores.engine.view(case_id)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)
