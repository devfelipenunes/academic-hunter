.PHONY: install install-dev test test-fast test-all test-cov lint format clean build docker-build docker-run

# `venv`, not `.venv`: the README, the tutorial and install.py all create `venv`,
# and a Makefile that looks somewhere else fails on a fresh clone.
VENV = venv
PYTHON = $(VENV)/bin/python
# `python -m pytest`, not the `pytest` script, and it is not a style choice: the
# console script puts `venv/bin` on `sys.path` and never the repository root, so
# `tests/test_pool_rebuild.py` — which imports `evaluation.rebuild_pool` from the
# root, where there is no `__init__.py` — fails to collect on a fresh clone. The
# CI already runs the `-m` form for this reason.
PYTEST = $(PYTHON) -m pytest
RUFF = $(VENV)/bin/ruff

# `ml` carries sentence-transformers and the clustering stack. Without it the
# tools that need them degrade quietly, which is what the Dockerfile documents
# having fixed for itself. `fulltext` (pypdf) is the same story for the PDF leg
# of full-text. `rag` is redundant — its only entry, chromadb, is already a base
# dependency — and stays declared so that `pip install .[rag]` keeps working.
# The integration tests are already deselected by `addopts` in pyproject.toml,
# so nothing here has to name them.
#
# `$(VENV)/bin/pip`, not a bare `pip`: on Ubuntu 24.04 the bare name resolves to
# the system pip and dies on PEP 668 (`externally-managed-environment`) while
# every other target here already uses the venv.
install:
	$(VENV)/bin/pip install -e ".[ml,fulltext,dev]"

install-dev:
	$(VENV)/bin/pip install -e ".[ml,fulltext,dev]"
	$(VENV)/bin/pip install ruff pre-commit pytest-cov pytest-xdist pytest-benchmark
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
