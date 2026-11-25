"""freight-damage: assess photos, catch up on ready damage claims, resolve what waits for a
person, and serve read tools over MCP.

Reference mode only: a photo's findings are its label from data/damage. A live vision run
costs money and lands with the recorded run (issue #10).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from freight_agents.claims_intake.domain import ClaimFields
from freight_agents.claims_intake.workflow import ClaimsIntake
from freight_agents.claims_intake.workflow import Stores as ClaimsStores
from freight_agents.damage_assessor.calibration import load_calibration
from freight_agents.damage_assessor.domain import Finding, Recommendation
from freight_agents.damage_assessor.extract import Photo, extract
from freight_agents.damage_assessor.images import labels_by_image
from freight_agents.damage_assessor.rules import ClaimFacts, decide
from freight_agents.damage_assessor.workflow import AssessmentDesk, Stores, reference_models
from freight_agents.integrations.email import parse_eml
from freight_agents.integrations.tms import FixtureTms
from freight_agents.llm import Model

DEFAULT_STATE = Path("var/damage")
DEFAULT_CLAIMS = Path("var/claims")
DEFAULT_DATA = Path("data/damage")
DEFAULT_TMS = Path("data/demo/tms.json")


def labels(data: Path) -> dict[str, Finding]:
    return {name: label.finding for name, label in labels_by_image(data).items()}


def show(rec: Recommendation) -> str:
    amount = "" if rec.amount_usd is None else f" ${rec.amount_usd:,.2f}"
    person = " (waits for a person)" if rec.needs_person else ""
    lines = [f"{rec.outcome.value}{amount}{person}"]
    lines += [f"  {e.kind} {e.ref}: {e.text}" for e in rec.evidence]
    return "\n".join(lines)


def _money(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _desk(args: argparse.Namespace) -> tuple[AssessmentDesk, ClaimsIntake]:
    tms = FixtureTms(args.tms)
    intake = ClaimsIntake(model=None, tms=tms, stores=ClaimsStores.at(args.claims_state))
    desk = AssessmentDesk(
        Stores.at(args.state),
        tms=tms,
        hand_off=intake.hand_off,
        models=reference_models(labels(args.data)),
    )
    return desk, intake


def _assess(args: argparse.Namespace) -> int:
    paths = [Path(p) for p in args.photos]
    photos = [Photo(name=p.name, media_type="image/png", data=p.read_bytes()) for p in paths]
    model = reference_models(labels(args.data))(photos)
    found = extract(photos, args.description, model, dt.datetime.now(dt.UTC))
    facts = ClaimFacts(
        claim_id="cli",
        documented_value_usd=Decimal(args.value),
        claimed_amount_usd=_money(args.claimed),
        repair_cost_usd=_money(args.repair),
        salvage_value_usd=_money(args.salvage),
        delivery_exception=args.delivery_exception,
        reported_after_delivery=args.after_delivery,
    )
    print(show(decide(found.findings, facts, load_calibration())))
    return 0


def _run(args: argparse.Namespace) -> int:
    desk, intake = _desk(args)
    messages = {}
    for path in sorted(args.inbox.glob("*.eml")):
        message = parse_eml(path.read_bytes())
        messages[message.message_id] = message
    engine = intake.stores.engine
    for case_id in engine.store.case_ids():
        case = engine.view(case_id)
        if case.state != "ready_to_file":
            continue
        fields = ClaimFields.model_validate(case.data["fields"])
        sent = messages.get(case.data["email"]["message_id"])
        if fields.claim_type != "damage" or sent is None:
            continue
        assessed = desk.assess(case_id, fields, sent)
        outcome = desk.assessment(case_id).recommendation.outcome.value
        print(f"{case_id} {assessed.state} {outcome}")
    return 0


def _waiting(args: argparse.Namespace) -> int:
    desk = AssessmentDesk(
        Stores.at(args.state), tms=FixtureTms(args.tms), hand_off=_no_hand_off, models=_no_model
    )
    for case in desk.waiting():
        rec = desk.assessment(case.case_id).recommendation
        because = ", ".join(e.ref for e in rec.evidence if e.kind == "rule")
        print(f"{case.case_id} {rec.outcome.value} because {because}")
    return 0


def _resolve(args: argparse.Namespace) -> int:
    desk, _ = _desk(args)
    amount = None if args.decline else Decimal(args.amount)
    case = desk.resolve(args.case_id, args.by, amount)
    print(f"{case.case_id} {case.state}")
    return 0


def _mcp(args: argparse.Namespace) -> int:
    import anyio
    from freight_agents.damage_assessor.mcp_server import build_damage_server
    from mcp.server.stdio import stdio_server

    desk = AssessmentDesk(
        Stores.at(args.state), tms=FixtureTms(args.tms), hand_off=_no_hand_off, models=_no_model
    )
    server = build_damage_server(desk)

    async def serve() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(serve)
    return 0


def _eval(args: argparse.Namespace) -> int:
    from freight_agents.damage_assessor.evaluation import FLOORS, run, write_report

    result = run(args.data)
    for name, value in result.metrics.items():
        print(f"{name}: {value:.2f}")
    failures = result.failures(FLOORS)
    print("gate: " + ("passed" if not failures else "failed: " + "; ".join(failures)))
    print(f"report: {write_report(result, args.reports, args.day)}")
    return 1 if failures else 0


def _no_hand_off(case_id: str, amount: float, summary: object, by: str) -> object:
    raise RuntimeError("this command only reads")


def _no_model(photos: Sequence[Photo]) -> Model:
    raise RuntimeError("this command only reads")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="freight-damage")
    commands = parser.add_subparsers(dest="command", required=True)

    assess = commands.add_parser("assess", help="assess photos on disk against claim facts")
    assess.add_argument("photos", nargs="+")
    assess.add_argument("--value", required=True, help="documented value of the goods, USD")
    assess.add_argument("--claimed", help="the amount the claimant asks for, USD")
    assess.add_argument("--repair", help="documented repair cost, USD")
    assess.add_argument("--salvage", help="documented salvage value, USD")
    assess.add_argument("--delivery-exception", action="store_true")
    assess.add_argument("--after-delivery", action="store_true", help="found after delivery")
    assess.add_argument("--description", default="")

    run = commands.add_parser("run", help="assess every ready damage claim in the claims state")
    run.add_argument("--inbox", type=Path, required=True)

    commands.add_parser("waiting", help="list assessments waiting for a person")

    resolve = commands.add_parser("resolve", help="file an amount for a waiting claim, or decline")
    resolve.add_argument("case_id")
    resolve.add_argument("--by", required=True)
    choice = resolve.add_mutually_exclusive_group(required=True)
    choice.add_argument("--amount")
    choice.add_argument("--decline", action="store_true")

    commands.add_parser("mcp", help="serve the read tools over MCP on stdio")

    evaluate = commands.add_parser("eval", help="grade the golden shipments; exit 1 on the gate")
    evaluate.add_argument(
        "--reports", type=Path, default=Path("apps/damage-assessor/evals/reports")
    )
    evaluate.add_argument("--day", default=dt.date.today().isoformat())

    for sub in commands.choices.values():
        sub.add_argument("--state", type=Path, default=DEFAULT_STATE)
        sub.add_argument("--claims-state", type=Path, default=DEFAULT_CLAIMS)
        sub.add_argument("--tms", type=Path, default=DEFAULT_TMS)
        sub.add_argument("--data", type=Path, default=DEFAULT_DATA)

    args = parser.parse_args(argv)
    handlers = {
        "assess": _assess,
        "run": _run,
        "waiting": _waiting,
        "resolve": _resolve,
        "mcp": _mcp,
        "eval": _eval,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
