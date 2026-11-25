"""damage-assessor over MCP: read an assessment and the claims waiting for a person.
Nothing here files, declines or changes an assessment."""

from __future__ import annotations

import uuid
from typing import Any

from freight_agents.agentcore.guards import cap_size
from freight_agents.agentcore.hooks import HookContext
from freight_agents.agentcore.tools import Risk, Tool, ToolRegistry, strict_schema, tool
from freight_agents.damage_assessor.domain import Evidence, Finding
from freight_agents.damage_assessor.workflow import AssessmentDesk
from freight_agents.llm import ToolSpec
from freight_agents.mcp.bridge import Route, RouteError, build_server
from pydantic import BaseModel

INSTRUCTIONS = (
    "Damage claims are assessed from their photos: a model describes, rules decide. Read an "
    "assessment or the claims waiting for a person. Filing and declining are not available "
    "over MCP."
)


class CaseIn(BaseModel):
    case_id: str


class AssessmentOut(BaseModel):
    case_id: str
    state: str
    outcome: str
    amount_usd: str | None
    documented_value_usd: str | None
    findings: list[Finding]
    evidence: list[Evidence]


class WaitingIn(BaseModel):
    pass


class Waiting(BaseModel):
    case_id: str
    outcome: str
    because: list[str]


class WaitingOut(BaseModel):
    waiting: list[Waiting]


def _specs() -> list[ToolSpec]:
    described: list[tuple[str, str, type[BaseModel]]] = [
        ("get_assessment", "A claim's assessment: findings, outcome, amount, evidence.", CaseIn),
        ("list_waiting", "Assessments waiting for a person to file or decline.", WaitingIn),
    ]
    return [ToolSpec(name=n, description=d, input_schema=strict_schema(m)) for n, d, m in described]


def build_damage_server(desk: AssessmentDesk) -> Any:
    engine = desk.stores.engine

    @tool(name="get_assessment", description="Read an assessment.", risk=Risk.READ)
    def get_assessment(args: CaseIn) -> AssessmentOut:
        case = engine.view(args.case_id)
        a = desk.assessment(args.case_id)
        rec = a.recommendation
        return AssessmentOut(
            case_id=case.case_id,
            state=case.state,
            outcome=rec.outcome.value,
            amount_usd=None if rec.amount_usd is None else str(rec.amount_usd),
            documented_value_usd=(
                None if a.documented_value_usd is None else str(a.documented_value_usd)
            ),
            findings=a.findings,
            evidence=rec.evidence,
        )

    @tool(name="list_waiting", description="Assessments waiting for a person.", risk=Risk.READ)
    def list_waiting(args: WaitingIn) -> WaitingOut:
        out = []
        for case in desk.waiting():
            rec = desk.assessment(case.case_id).recommendation
            because = [e.ref for e in rec.evidence if e.kind == "rule"]
            out.append(Waiting(case_id=case.case_id, outcome=rec.outcome.value, because=because))
        return WaitingOut(waiting=out)

    reads: dict[str, Tool] = {"get_assessment": get_assessment, "list_waiting": list_waiting}

    def route(name: str, args: dict[str, Any]) -> Route:
        if name not in reads:
            raise RouteError("unknown_tool", f"no tool {name}")
        if "case_id" in args and not engine.exists(str(args["case_id"])):
            raise RouteError("not_found", f"no assessment {args['case_id']}")
        ctx = HookContext(run_id=f"mcp-{uuid.uuid4().hex[:10]}", agent="mcp", now=desk.clock())
        return Route(ToolRegistry([reads[name]]), [], [cap_size()], ctx, name, args)

    return build_server("freight-damage", _specs(), route, desk.stores.audit, INSTRUCTIONS)
