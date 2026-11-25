# damage-assessor

Photos of damaged freight become structured findings from a vision model (damage type, severity, packaging, visible or concealed, each with a confidence), and rules in code turn the findings and the claim's documents into a recommendation: file in full, file in part, salvage then file, deny, or inspect. The model describes; code decides. A deny or an inspect always waits for a person.

## Table of Contents

- [Results](#results)
- [How It Works](#how-it-works)
- [Rules](#rules)
- [Commands](#commands)
- [Run It](#run-it)
- [Limits](#limits)

---

## Results

From the [2026-11-25 evaluation](evals/reports/2026-11-25-reference.md): 43 hand-labeled shipments with synthetic and openly licensed photos.

| Metric | Value |
|---|---|
| Outcome right on gold findings (hand-written expectations) | 43 of 43 |
| Amount right to the cent | 43 of 43 |
| Amounts above the documented value | 0 |
| Denies and inspects handed off without a person | 0 |
| Red-team cases where a fooled model moved money | 0 of 3 |

The rules are measured for real: each shipment's outcome and amount were written by hand from the rules' stated policy and compared with what the code decides. Findings and calibration run in reference mode, where the findings are the labels, so they say nothing yet about a real model; a recorded run of a vision model over the same photos measures them (issue #10). The report also names a known limit: a model that lies outright about damage gets the claim filed, capped by the claim and the documented value.

## How It Works

| Part | Module | What it does |
|---|---|---|
| Types | `domain.py` | `Finding`, null wherever a photo cannot say; `Recommendation`, whose types refuse a negative amount, an amount on a deny or inspect, or a recommendation with no evidence |
| Sources | `sources.py` | Each legal rule names its passage in the knowledge package (49 U.S.C. 14706(a), 49 CFR 370.3, 370.7, 370.11); practice is labeled as practice |
| Images | `images.py` | 50 synthetic photos drawn from a seed with their ground truth, and 9 public-domain or CC BY photos with hand labels; [credits](../../data/damage/README.md) |
| Extraction | `extract.py` | Photos as image parts, the description escaped as data, one strict `record_findings` tool; a photo the model skips gets a null finding |
| Calibration | `calibration.py` | Reliability bins, expected calibration error, and per finding type the lowest confidence that keeps precision at the target; a labeled default until a recorded run |
| Rules | `rules.py` | Findings and documents to a recommendation, citing each rule and finding |
| Desk | `workflow.py` | Called by claims-intake when a damage claim with photos is ready; hands a filing amount to carrier-filing, or waits for a person |

[ADR-0014](../../docs/adr/ADR-0014-model-describes-code-decides.md) explains why the model never recommends.

## Rules

In order; the first that applies decides.

| Condition | Outcome | Source |
|---|---|---|
| No usable finding (blank frame, document, unknown photo) | inspect | practice |
| The most severe finding is below its calibrated threshold | inspect | practice |
| Concealed damage, or damage reported after delivery, with a clean delivery receipt | inspect | practice |
| Packaging a credible finding shows as inadequate | inspect | practice |
| No damage in any credible finding | deny, for a person to confirm | 14706(a) |
| Severe or total damage, with salvage | salvage then file the value less salvage, never below zero | 370.11, practice |
| Severe or total damage | file the documented value | 14706(a), 370.7 |
| Minor or moderate damage with a documented repair cost | file the repair cost | 14706(a), 370.7 |
| Minor or moderate damage without one | inspect | 370.3(b) |

Every amount is capped at the documented value and at what the claimant asked for. 49 CFR 370.11 governs how a carrier processes salvage and records the proceeds; it sets no rule for crediting salvage against a claim, so that step is labeled practice.

## Commands

| Command | Does |
|---|---|
| `freight-damage assess PHOTO... --value 1200 [--claimed] [--repair] [--salvage]` | Assesses photos on disk and prints the recommendation with its evidence |
| `freight-damage run --inbox DIR` | Assesses every ready damage claim in the claims-intake state |
| `freight-damage waiting` | Lists assessments waiting for a person |
| `freight-damage resolve CASE --by NAME --amount 300` or `--decline` | A person files an amount (within the documented value and the claim) or declines |
| `freight-damage eval` | Grades the golden shipments; exits 1 when a floor fails |
| `freight-damage mcp` | Read tools over MCP: `get_assessment`, `list_waiting` |

## Run It

```bash
uv run freight-damage assess data/damage/synthetic/carton-wet-severe-1.png --value 1200 --claimed 1000
uv run freight-damage eval
```

## Limits

- Reference mode only. A live vision run costs money and comes with the recorded run in v0.1.0.
- A model that records false damage within the schema and above the threshold is not caught by any rule; the photos travel with the claim to the carrier.
- claims-intake does not extract repair costs, salvage offers or delivery exceptions yet, so in the full flow partial damage waits for a person.
- Calibration thresholds are a labeled default (0.8 for every type) until a recorded run measures them.
