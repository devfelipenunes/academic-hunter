.PHONY: install test test-fast lint format clean build docker-build

# `venv`, not `.venv`: the README, the tutorial and install.py all create `venv`,
# and a Makefile that looks somewhere else fails on a fresh clone.
VENV = venv
PYTHON = $(VENV)/bin/python
PYTEST = $(VENV)/bin/pytest
RUFF = $(VENV)/bin/ruff

# `ml` carries sentence-transformers and the clustering stack. Without it the
# tools that need them degrade quietly, which is what the Dockerfile documents
# having fixed for itself. The integration tests are already deselected by
# `addopts` in pyproject.toml, so nothing here has to name them.
install:
	pip install -e ".[ml,rag,dev]"

install-dev:
	pip install -e ".[ml,rag,dev]"
	pip install ruff pre-commit pytest-cov pytest-xdist pytest-benchmark
	pre-commit install

test:
	$(PYTEST) tests/ -v --tb=short

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
