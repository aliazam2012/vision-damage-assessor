# Contributing

## Table of Contents

- [Setup](#setup)
- [Making a Change](#making-a-change)
- [Rules](#rules)

---

## Setup

Install [uv](https://docs.astral.sh/uv/), then `make setup` and `make check`. `make demo` shows the system end to end without an API key.

## Making a Change

1. Write the failing test first, then the code.
2. `make check` must pass: ruff, mypy strict, pytest, and the reference evaluation.
3. Open a pull request using the template; CI runs the same checks plus secret scanning and a dependency audit.
4. Reviews follow [docs/CHECKLIST-code-review.md](docs/CHECKLIST-code-review.md); releases follow [docs/RUNBOOK-release.md](docs/RUNBOOK-release.md); incidents get a blameless postmortem from [docs/TPL-postmortem.md](docs/TPL-postmortem.md).

## Rules

- Tests and CI never call a paid model API. Use `ScriptedModel` or a recorded cassette.
- Every company, person and address is made up; email domains are `example.com`, `example.net` or `example.org`. New company names are checked first ([docs/NAMES.md](docs/NAMES.md)).
- A new tool declares its risk (read, write or send); a new send tool declares its control arguments for the taint guard.
- A decision someone will ask "why" about gets an ADR in `docs/adr/`.
