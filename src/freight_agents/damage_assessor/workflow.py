"""The assessment desk: a damage claim's photos become a decision, and filing gets the amount.

claims-intake calls `assess` when a damage claim with photos is ready to file. The desk
reads the photos into findings, looks up the shipment's documented value in the TMS, and
lets the rules decide. A filing recommendation hands its amount straight to claims-intake,
which hands the case to carrier-filing. A deny, an inspect, or a salvage that leaves
nothing to file waits for a person, who files an amount or declines; the person's amount
is held to the documented value and the claim. Each assessment is a statecore case keyed
by the claim's case id, so assessing a claim twice changes nothing.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from freight_agents.agentcore.approvals import AuditLog
from freight_agents.claims_intake.domain import ClaimFields
from freight_agents.damage_assessor.calibration import Calibration, load_calibration
from freight_agents.damage_assessor.domain import (
    Assessment,
    Evidence,
    Finding,
    Outcome,
    Recommendation,
)
from freight_agents.damage_assessor.extract import Photo, extract, reference_model
from freight_agents.damage_assessor.rules import ClaimFacts, decide
from freight_agents.damage_assessor.sources import SOURCES
from freight_agents.integrations.email import EmailMessage
from freight_agents.integrations.tms import Shipment, TmsClient
from freight_agents.llm import Model
from freight_agents.statecore.engine import CaseEngine
from freight_agents.statecore.machine import CaseView, StateMachine, Transition
from freight_agents.statecore.store import SqliteEventStore

ASSESSMENT_MACHINE = StateMachine(
    name="assessment",
    initial="assessed",
    transitions=[
        Transition("assessed", "file", "handed_off"),
        Transition("assessed", "needs_person", "waiting"),
        Transition("waiting", "person_filed", "handed_off"),
        Transition("waiting", "person_declined", "declined"),
    ],
    terminal={"handed_off", "declined"},
)

Clock = Callable[[], dt.datetime]
ModelFor = Callable[[Sequence[Photo]], Model]
# claims-intake's hand_off: case id, amount, the assessment's summary, who decided.
HandOff = Callable[[str, float, dict[str, Any], str], object]


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def reference_models(labels: Mapping[str, Finding]) -> ModelFor:
    """Reference mode: a photo's findings are its label; a photo with no label gets none."""

    def model_for(photos: Sequence[Photo]) -> Model:
        return reference_model({p.name: labels[p.name] for p in photos if p.name in labels})

    return model_for


@dataclass
class Stores:
    engine: CaseEngine
    audit: AuditLog

    @classmethod
    def at(cls, directory: Path, clock: Clock = _utc_now) -> Stores:
        directory.mkdir(parents=True, exist_ok=True)
        return cls(
            engine=CaseEngine(
                ASSESSMENT_MACHINE, SqliteEventStore(directory / "events.sqlite3"), clock
            ),
            audit=AuditLog(directory / "audit.sqlite3"),
        )


def _money(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value)).quantize(Decimal("0.01"))


class AssessmentDesk:
    def __init__(
        self,
        stores: Stores,
        tms: TmsClient,
        hand_off: HandOff,
        models: ModelFor,
        calibration: Calibration | None = None,
        clock: Clock = _utc_now,
        mode: Literal["reference", "live"] = "reference",
    ) -> None:
        self.stores, self.tms, self.hand_off, self.models = stores, tms, hand_off, models
        self.calibration = calibration or load_calibration()
        self.clock, self.mode = clock, mode

    def _shipment(self, fields: ClaimFields) -> Shipment | None:
        found = self.tms.get_shipment(fields.pro_number) if fields.pro_number else None
        if found is None and fields.bol_number:
            found = self.tms.find_by_bol(fields.bol_number)
        return found

    def assess(self, case_id: str, fields: ClaimFields, message: EmailMessage) -> CaseView:
        engine = self.stores.engine
        if engine.exists(case_id):
            existing = engine.view(case_id)
            # "assessed" is a step, not a resting state: an earlier hand-off failed.
            return self._route(case_id) if existing.state == "assessed" else existing
        now = self.clock()
        photos = [
            Photo(name=a.filename, media_type=a.media_type, data=a.data)
            for a in message.attachments
            if a.media_type.startswith("image/")
        ]
        extraction = extract(photos, fields.damage_description or "", self.models(photos), now)
        shipment = self._shipment(fields)
        value = _money(shipment.declared_value_usd) if shipment else None
        if value is None:
            recommendation = Recommendation(
                outcome=Outcome.INSPECT,
                amount_usd=None,
                evidence=[
                    Evidence(kind="document", ref="TMS", text="no shipment found for this claim"),
                    Evidence(kind="rule", ref="370.7", text=SOURCES["370.7"].says),
                ],
            )
        else:
            facts = ClaimFacts(
                claim_id=case_id,
                documented_value_usd=value,
                claimed_amount_usd=_money(fields.claimed_amount_usd),
            )
            recommendation = decide(extraction.findings, facts, self.calibration)
        assessment = Assessment(
            claim_id=case_id,
            documented_value_usd=value,
            findings=extraction.findings,
            recommendation=recommendation,
            assessed_at=now,
            mode=self.mode,
        )
        engine.open(
            case_id,
            {
                "assessment": assessment.model_dump(mode="json"),
                "extraction": {
                    "recorded": extraction.recorded,
                    "refused": extraction.refused,
                    "dropped": extraction.dropped,
                },
            },
            actor="damage-assessor",
        )
        return self._route(case_id)

    def _route(self, case_id: str) -> CaseView:
        """Hand a filing amount off, or leave the claim for a person."""
        engine = self.stores.engine
        assessment = self.assessment(case_id)
        recommendation = assessment.recommendation
        amount = recommendation.amount_usd
        if recommendation.needs_person or amount is None or amount <= 0:
            return engine.fire(case_id, "needs_person", actor="rules")
        self.hand_off(case_id, float(amount), self._summary(assessment, "rules", amount), "rules")
        return engine.fire(case_id, "file", actor="rules")

    def resolve(self, case_id: str, person: str, amount_usd: Decimal | None) -> CaseView:
        """A person files an amount for a claim that waited, or declines it."""
        engine = self.stores.engine
        case = engine.view(case_id)
        if case.state != "waiting":
            raise ValueError(f"{case_id} is {case.state}, not waiting for a person")
        actor = f"person:{person}"
        if amount_usd is None:
            return engine.fire(case_id, "person_declined", {"decided_by": person}, actor=actor)
        assessment = self.assessment(case_id)
        value = assessment.documented_value_usd
        if amount_usd <= 0 or (value is not None and amount_usd > value):
            raise ValueError(f"amount {amount_usd} is outside the documented value {value}")
        self.hand_off(
            case_id, float(amount_usd), self._summary(assessment, person, amount_usd), actor
        )
        return engine.fire(
            case_id,
            "person_filed",
            {"decided_by": person, "filed_usd": str(amount_usd)},
            actor=actor,
        )

    def assessment(self, case_id: str) -> Assessment:
        return Assessment.model_validate(self.stores.engine.view(case_id).data["assessment"])

    def waiting(self) -> list[CaseView]:
        engine = self.stores.engine
        cases = (engine.view(case_id) for case_id in engine.store.case_ids())
        return [case for case in cases if case.state == "waiting"]

    def _summary(self, assessment: Assessment, decided_by: str, amount: Decimal) -> dict[str, Any]:
        rec = assessment.recommendation
        return {
            "outcome": rec.outcome.value,
            "recommended_usd": None if rec.amount_usd is None else str(rec.amount_usd),
            "filed_usd": str(amount),
            "decided_by": decided_by,
            "mode": assessment.mode,
            "evidence": [f"{e.kind}:{e.ref}" for e in rec.evidence],
        }
