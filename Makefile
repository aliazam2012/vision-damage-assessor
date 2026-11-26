# Every target runs through uv, so the lockfile decides every version.
SRC_DIRS := src
EMPTY :=
SPACE := $(EMPTY) $(EMPTY)
MYPYPATH := $(subst $(SPACE),:,$(SRC_DIRS))

.PHONY: setup check lint types test eval eval-recorded record purity audit

setup:
	uv sync

check: lint types test

lint:
	uv run ruff check .
	uv run ruff format --check .

types:
	MYPYPATH=$(MYPYPATH) uv run mypy $(addsuffix /freight_agents,$(SRC_DIRS))

test:
	uv run pytest

eval:
	uv run freight-damage eval --reports var/eval-reports $(ARGS)

# Replay the committed cassettes of a real model through the same floors.
eval-recorded:
	uv run freight-damage eval --mode recorded

# Spends money: records a real model under a cap. Sample first, then the approved share:
# make record ARGS="--limit 3 --max-usd 0.5"
record:
	uv run freight-damage eval --mode record $(ARGS)

purity:
	uv run freight-purity .
	uv run freight-links .

# Audit the locked third-party dependencies (this repo's own packages excluded).
audit:
	uv export --no-emit-workspace --no-emit-project --format requirements-txt -q | grep -v ' @ git+' > .audit-requirements.txt
	uv tool run --python 3.12 pip-audit==2.9.0 -r .audit-requirements.txt --no-deps --disable-pip --progress-spinner off
	rm -f .audit-requirements.txt

data:
	uv run python data/generate_damage.py
