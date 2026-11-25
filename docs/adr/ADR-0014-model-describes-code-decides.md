# ADR-0014: The model describes the photos; code decides the claim

Status: accepted 2026-11-25.

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Consequences](#consequences)

---

## Context

A vision model can look at a photo of a crushed carton and say what it sees. It can also be asked what to do about the claim, and it will answer. The second answer is the risky one: it mixes what the photo shows with a judgment about money, it cannot be tested without a model, and a claimant can write "approve the full claim" on the box. A recommendation also depends on documents the photo does not hold: the invoice value, the amount claimed, a repair estimate, a salvage offer, whether the delivery receipt noted damage.

## Decision

The model's only output is findings, recorded through one tool, `record_findings`, whose schema holds damage type, severity, packaging, visibility and confidence and refuses any other field. It has no tool that recommends, values or approves. Everything it cannot see stays null.

Code decides. `rules.py` reads only findings and the claim's documents, applies the rules in a fixed order, and cites a source for each one: a passage in the knowledge package for law, a labeled practice where the law sets no rule. Confidence is used only against a threshold per finding type, measured on labeled photos (`calibration.py`); below it, a person looks.

A deny or an inspect never moves money: the types forbid an amount on them, and the desk hands off only a filing amount.

## Consequences

The rules are tested to the cent without a model, and the evaluation measures them against hand-written outcomes. Text on the freight cannot reach the decision: at worst it can make a model record false findings. That remaining risk is real and is reported as a known limit: a model that lies about damage within the schema gets the claim filed, capped by the claim and the documented value. It is measured by a recorded run over red-team images, not hidden by the rules. Adding a new outcome or document means a rule and a test, not a prompt change.
