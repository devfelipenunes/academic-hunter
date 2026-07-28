.PHONY: install test test-fast lint format clean build docker-build

VENV = .venv
PYTHON = $(VENV)/bin/python
PYTEST = $(VENV)/bin/pytest
RUFF = $(VENV)/bin/ruff

install:
	pip install -e ".[rag,dev]"

install-dev:
	pip install -e ".[rag,dev]"
	pip install ruff pre-commit pytest-cov pytest-xdist pytest-benchmark
	pre-commit install

test:
	$(PYTEST) tests/ --deselect tests/interfaces/mcp/test_server_integration.py -v --tb=short

test-fast:
	$(PYTEST) tests/ --deselect tests/interfaces/mcp/test_server_integration.py -n auto -q --tb=short

test-all:
	$(PYTEST) tests/ -v --tb=short

test-cov:
	$(PYTEST) tests/ --deselect tests/interfaces/mcp/test_server_integration.py --cov=src/academic_hunter --cov-report=term-missing

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
