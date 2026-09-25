.PHONY: install test test-fast lint format clean build docker-build

# `venv`, not `.venv`: the README, the tutorial and install.py all create `venv`,
# and a Makefile that looks somewhere else fails on a fresh clone.
VENV = venv
PYTHON = $(VENV)/bin/python
PYTEST = $(VENV)/bin/pytest
RUFF = $(VENV)/bin/ruff

# `ml` carries sentence-transformers and the clustering stack. Without it the
# tools that need them degrade quietly, which is what the Dockerfile documents
# having fixed for itself. `fulltext` (pypdf) is the same story for the PDF leg
# of full-text. `rag` is gone: its only entry, chromadb, is already a base
# dependency. The integration tests are already deselected by `addopts` in
# pyproject.toml, so nothing here has to name them.
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

# Not a faster `test`: `-n auto` reports failures that are not there. Measured on
# this checkout, the same suite is 15 failed / 1046 passed run serially and 47
# failed under `-n auto`. The extra 32 are workers racing on state they share —
# the ChromaDB store and its ONNX model cache, which fails to load with
# `InvalidProtobuf` only when several workers touch it at once. Use this for a
# quick signal, and re-run anything it reports serially before believing it.
test-fast:
	$(PYTEST) tests/ -n auto -q --tb=short

test-all:
	$(PYTEST) tests/ -m integration -v --tb=short

test-cov:
	$(PYTEST) tests/ --cov=src/academic_hunter --cov-report=term-missing

lint:
	$(RUFF) check src/ tests/

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
