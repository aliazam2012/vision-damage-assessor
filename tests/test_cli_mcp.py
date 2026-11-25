import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import anyio
from freight_agents.claims_intake.workflow import ClaimsIntake
from freight_agents.damage_assessor.cli import main
from freight_agents.damage_assessor.mcp_server import build_damage_server
from freight_agents.integrations.email import parse_eml
from freight_agents.llm import ScriptedModel
from mcp import Client

from .conftest import FIELDS, World, claim_eml, intake_script

DATA = Path(__file__).resolve().parents[3] / "data" / "damage"


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue()


def _call(server: Any, name: str, args: dict[str, Any]) -> tuple[bool, Any]:
    async def go() -> tuple[bool, Any]:
        async with Client(server) as client:
            result = await client.call_tool(name, args)
            return bool(result.is_error), json.loads(result.content[0].text)

    return anyio.run(go)


def _names(server: Any) -> set[str]:
    async def go() -> set[str]:
        async with Client(server) as client:
            return {t.name for t in (await client.list_tools()).tools}

    return anyio.run(go)


def test_assess_prints_a_recommendation_for_photos_on_disk() -> None:
    photo = str(DATA / "synthetic" / "carton-wet-severe-1.png")
    code, out = run("assess", photo, "--value", "1200", "--claimed", "1000", "--data", str(DATA))
    assert code == 0
    assert "file_full" in out
    assert "$1,000.00" in out
    assert "14706(a)" in out


def test_run_assesses_ready_damage_claims_from_the_claims_state(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.intake.assessor = None  # claims-intake ran on its own; the desk catches up
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for k, photos in enumerate([["carton-crushed-severe-1.png"], ["carton-none-none-1.png"]]):
        raw = claim_eml(photos)
        (inbox / f"{k}.eml").write_bytes(raw)
        world.intake.model = ScriptedModel(intake_script(FIELDS))
        world.intake.process(parse_eml(raw))
    state, claims = tmp_path / "damage-cli", tmp_path / "claims"
    tms = tmp_path / "tms.json"
    args = ("--state", str(state), "--claims-state", str(claims), "--tms", str(tms))
    code, out = run("run", "--inbox", str(inbox), "--data", str(DATA), *args)
    assert code == 0
    assert "handed_off" in out
    assert "waiting" in out
    code, out = run("waiting", "--state", str(state))
    (line,) = out.strip().splitlines()
    case_id = line.split()[0]
    code, out = run("resolve", case_id, "--decline", "--by", "U-lee", *args)
    assert code == 0
    assert "declined" in out


def test_mcp_reads_assessments_and_offers_nothing_that_files(world: World) -> None:
    filed = world.claim(["carton-crushed-severe-1.png"])
    waiting = world.claim_with(["carton-none-none-1.png"])
    server = build_damage_server(world.desk)
    assert _names(server) == {"get_assessment", "list_waiting"}
    error, got = _call(server, "get_assessment", {"case_id": filed.case_id})
    assert not error
    assert got["state"] == "handed_off"
    assert got["outcome"] == "file_full"
    assert got["amount_usd"] == "800.00"
    error, got = _call(server, "list_waiting", {})
    assert [w["case_id"] for w in got["waiting"]] == [waiting.case_id]
    error, _ = _call(server, "get_assessment", {"case_id": "clm_nope"})
    assert error


def test_the_intake_and_the_desk_share_one_flow(tmp_path: Path) -> None:
    world = World(tmp_path)
    assert isinstance(world.intake, ClaimsIntake)
    assert world.intake.assessor is world.desk


def test_eval_writes_a_dated_report_and_exits_on_the_gate(tmp_path: Path) -> None:
    code, out = run("eval", "--reports", str(tmp_path), "--day", "2026-11-25", "--data", str(DATA))
    assert code == 0
    assert "gate: passed" in out
    assert (tmp_path / "2026-11-25-reference.md").exists()
    assert (tmp_path / "latest.json").exists()
