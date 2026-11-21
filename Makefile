# Developer commands for Leva. Gate definitions: PLAN.md section 4.

UV ?= uv
PYTEST_COV := $(UV) run pytest --cov --cov-report=term-missing:skip-covered --cov-report=json
COVERAGE_GATE := $(UV) run python tools/coverage_gate.py coverage.json
VERIFY_HOME := $(CURDIR)/.cache/leva

.DEFAULT_GOAL := check
.PHONY: check lint fmt type arch test cov live verify py311

check:
	$(UV) lock --check
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run mypy
	$(UV) run lint-imports
	$(PYTEST_COV)
	$(COVERAGE_GATE)

lint:
	$(UV) run ruff check .

fmt:
	$(UV) run ruff format .

type:
	$(UV) run mypy

arch:
	$(UV) run lint-imports

test:
	$(UV) run pytest

cov:
	$(PYTEST_COV)
	$(COVERAGE_GATE)

live:
	$(UV) run pytest -m macos_live

verify:
	@test -n "$(CMD)" || { echo "usage: make verify CMD=<name>" >&2; exit 2; }
	mkdir -p "$(VERIFY_HOME)"
	LEVA_HOME="$(VERIFY_HOME)" $(UV) run leva --rebuild </dev/null
	$(UV) run python -m leva.verify --index "$(VERIFY_HOME)/index.db" --command "$(CMD)"

py311:
	UV_PROJECT_ENVIRONMENT=.venv-py311 $(UV) run --python 3.11 pytest -q
