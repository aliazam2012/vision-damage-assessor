# Agent Instructions

## Table of Contents

- [Commands](#commands)
- [Rules](#rules)

---

## Commands

- `make setup`: install this agent and its pinned runtime with uv.
- `make check`: ruff, mypy strict and pytest. Run it before every commit.
- `make eval`: the evaluation gate. `make eval-recorded`: replay a real model's committed cassettes.
- `make purity`: the clean-room scan and the Markdown link check.

## Rules

- Test first: write the failing test, watch it fail, then write the code.
- Never call a paid model API from a test. Use `ScriptedModel` or a cassette.
- Never move a case's state from a tool or a prompt; tools propose, the state machine decides.
- Any tool that sends outside is `Risk.SEND`, waits for a person's approval and is declared in the taint guard's controls.
- Made-up data only, on `example.com`, `example.net` or `example.org`.
- Shared behavior belongs in [agent-runtime](https://github.com/aliazam2012/agent-runtime); this repo bumps the runtime's tag in its own pull request.
