.PHONY: install install-dev test test-fast test-all test-cov eval lint format clean build docker-build docker-run

# `venv`, not `.venv`: the README, the tutorial and install.py all create `venv`,
# and a Makefile that looks somewhere else fails on a fresh clone.
VENV = venv
PYTHON = $(VENV)/bin/python
# `python -m pytest`, not the `pytest` script: the console script puts
# `venv/bin` on `sys.path` and never the working directory, so a test that
# imports a module living at the repository root would fail to collect there
# and nowhere else. The CI runs the `-m` form, so this matches it.
PYTEST = $(PYTHON) -m pytest
RUFF = $(VENV)/bin/ruff

# `ml` carries sentence-transformers and the clustering stack. Without it the
# tools that need them degrade quietly, which is what the Dockerfile documents
# having fixed for itself. `fulltext` (pypdf) is the same story for the PDF leg
# of full-text. The integration tests are already deselected by `addopts` in
# pyproject.toml, so nothing here has to name them.
#
# `$(VENV)/bin/pip`, not a bare `pip`: on Ubuntu 24.04 the bare name resolves to
# the system pip and dies on PEP 668 (`externally-managed-environment`) while
# every other target here already uses the venv.
install:
	$(VENV)/bin/pip install -e ".[ml,fulltext,dev]"

install-dev:
	$(VENV)/bin/pip install -e ".[ml,fulltext,dev]"
	$(VENV)/bin/pip install ruff pre-commit pytest-cov pytest-xdist
	pre-commit install

test:
	$(PYTEST) tests/ -v --tb=short

# Not a faster `test`: measured on this checkout the outcome is identical —
# 15 failed / 1140 passed either way — and the gain is ~20 s (72 s serial
# against 55 s under `-n auto`). The 15 are the missing `ml` extra
# (sentence-transformers, sklearn), not races: they fail the same way in both
# modes, and so does everything else. Serial stays canonical because the suite
# still shares one ONNX model cache under ~/.cache/chroma, the one race no
# per-test fixture can isolate without re-downloading 79 MB into every worker.
test-fast:
	$(PYTEST) tests/ -n auto -q --tb=short

test-all:
	$(PYTEST) tests/ -m integration -v --tb=short

test-cov:
	$(PYTEST) tests/ --cov=src/academic_hunter --cov-report=term-missing

# Retrieval quality, over a run that already exists. Not a gate and not run by
# CI: it needs a run in `results/`, which is not versioned, and the qrels beside
# the harness names the run it was written against.
#
# It is the before/after pair for any change to the ranking. Two measurements
# used to live in the prose of `core/pipeline/steps.py` and nothing today can
# re-check them, because the data behind them left with `evaluation/`. Run this
# on both sides of a change, or the change is an opinion.
#
#   make eval                                          # the configuration in use today
#   make eval EVAL_ARGS="--dense query --weights 0.7,0.3 --rerank"
EVAL_RUN ?= $(shell ls -d results/run_* 2>/dev/null | tail -1)
EVAL_QRELS ?= tests/evaluation/qrels_blockchain.json

eval:
	@test -n "$(EVAL_RUN)" || { echo "no run in results/ — run a search first"; exit 1; }
	$(PYTHON) tests/evaluation/harness.py --run $(EVAL_RUN) --qrels $(EVAL_QRELS) $(EVAL_ARGS)

lint:
	$(RUFF) check src/ tests/

# Not a gate, and not run by CI: it would rewrite 172 of the 234 files today.
# The only path that can trigger it unasked is the ruff-format pre-commit hook,
# and only where `pre-commit install` was run.
format:
	$(RUFF) format src/ tests/

clean:
	rm -rf .coverage .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build:
	pip install build
	python -m build

docker-build:
	docker compose build

docker-run:
	docker compose up
