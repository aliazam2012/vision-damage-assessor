"""Where each rule comes from.

A legal source names a passage in the knowledge package, and a test resolves every one,
so a recommendation never cites law the package does not hold. Practice is what claims
desks commonly do where the law sets no rule; it is labeled as practice and cites none.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from freight_agents.claims_intake.rules import claim_rules
from freight_agents.knowledge.index import Passage


@dataclass(frozen=True)
class Source:
    id: str
    says: str
    doc_id: str | None = None
    heading: str | None = None

    @property
    def practice(self) -> bool:
        return self.doc_id is None


SOURCES: dict[str, Source] = {
    s.id: s
    for s in [
        Source(
            "14706(a)",
            "The carrier is liable for the actual loss or injury to the property it causes.",
            "49-usc-14706",
            "14706(a) Carrier liability",
        ),
        Source(
            "370.3(b)",
            "A claim asks for a specified or determinable amount of money.",
            "49-cfr-370",
            "370.3 Filing a claim: what counts",
        ),
        Source(
            "370.7",
            "A claim is supported by the bill of lading, freight charges and the invoice or a "
            "certified value when they are a necessary part of the investigation.",
            "49-cfr-370",
            "370.7 Investigating a claim",
        ),
        Source(
            "370.11",
            "Damaged goods that are refused or not delivered are sold or disposed of as salvage "
            "after notice, and the claim file records the lot and the money recovered.",
            "49-cfr-370",
            "370.11 Processing salvage",
        ),
        Source(
            "practice:salvage-credit",
            "Claim the documented value less what the damaged goods recover as salvage.",
        ),
        Source(
            "practice:concealed-damage",
            "Damage found after a clean delivery receipt is inspected before anyone decides, "
            "since the claimant must show it happened in transit.",
        ),
        Source(
            "practice:packaging",
            "Packaging a photo shows as inadequate goes to a person: it can move liability to "
            "the shipper.",
        ),
        Source(
            "practice:severity-to-loss",
            "Severe or total damage is filed as a loss of the goods; minor or moderate damage "
            "is filed at the documented cost to repair it.",
        ),
        Source(
            "practice:confidence",
            "Code does not act on a finding below the calibrated confidence threshold; a person "
            "looks at the photo.",
        ),
    ]
}


@cache
def _passages() -> dict[tuple[str, str], Passage]:
    return {(p.doc_id, p.heading): p for p in claim_rules()}


def passage(source_id: str) -> Passage:
    """The knowledge passage a legal source cites; LookupError for practice or a gap."""
    source = SOURCES.get(source_id)
    if source is None or source.doc_id is None or source.heading is None:
        raise LookupError(f"{source_id} cites no knowledge passage")
    found = _passages().get((source.doc_id, source.heading))
    if found is None:
        raise LookupError(f"{source_id}: no passage {source.heading!r} in {source.doc_id}")
    return found
