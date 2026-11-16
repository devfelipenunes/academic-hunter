.PHONY: install install-dev test test-fast test-all test-cov eval eval-run lint format clean build docker-build docker-run

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
# having fixed for itself — and `make test` runs the analysis tests, so the
# targets below need it. `fulltext` (pypdf) is the same story for the PDF leg of
# full-text. The integration tests are already deselected by `addopts` in
# pyproject.toml, so nothing here has to name them.
#
# `install` and `install-dev` install the same runtime set; the second adds the
# linters and the hooks. They used to be identical, which made `install` a
# developer install that happened to be named like a user's.
#
# `$(VENV)/bin/pip`, not a bare `pip`: on Ubuntu 24.04 the bare name resolves to
# the system pip and dies on PEP 668 (`externally-managed-environment`) while
# every other target here already uses the venv.
install:
	$(VENV)/bin/pip install -e ".[ml,fulltext]"

install-dev:
	$(VENV)/bin/pip install -e ".[ml,fulltext,dev]"
	$(VENV)/bin/pip install ruff pre-commit pytest-cov pytest-xdist
	pre-commit install

test:
	$(PYTEST) tests/ -v --tb=short

# Not a faster `test`: on a machine carrying the `ml` extra the outcome is the
# same either way, and what `-n auto` buys is seconds. How many tests fail
# without `ml` is not quoted here because it moves with the suite; what matters
# is that they fail the same way in both modes — it is the missing extra
# (sentence-transformers, sklearn), not a race, and so does everything else.
# Serial stays canonical because the suite shares one ONNX model cache under
# ~/.cache/chroma, the one race no per-test fixture can isolate without
# re-downloading the model into every worker.
test-fast:
	$(PYTEST) tests/ -n auto -q --tb=short

test-all:
	$(PYTEST) tests/ -m integration -v --tb=short

test-cov:
	$(PYTEST) tests/ --cov=src/academic_hunter --cov-report=term-missing

# Retrieval quality. Two measurements, neither a gate and neither run by CI.
#
# `eval` grades the judged pool: five queries, fifty fixed candidates each, 250
# graded judgments, all of it versioned in `tests/evaluation/`. It asks how well
# a ranking ordered a candidate set that is the same every time, which is what a
# change to fusion or to reranking moves — and because the data ships with the
# repository, it runs on a fresh clone with no configuration, no network and no
# model.
#
# `eval-run` asks the other question: 25 questions over one run's corpus, whether
# the right paper was found at all. It defaults to the run the qrels was written
# against, versioned under `tests/evaluation/fixtures/` for the same reason —
# and not to the newest run in `results/`, which is the one thing that cannot
# work: a qrels is about a corpus, so pointing it at another run resolves none of
# its targets and scores zero. `EVAL_RUN=results/run_<ts>` measures your own run
# against it, which is worth doing only when that run is on the same topic, and
# the harness says so when it is not.
#
# Either is the before/after pair for a change to the ranking. A change with no
# number on either side is an opinion, and this project already paid for one of
# those: two measurements used to live in the prose of `core/pipeline/steps.py`
# and nothing can re-check them today, because the data behind them left with
# `evaluation/`.
#
#   make eval                                            # the judged pool
#   make eval-run                                        # the run the qrels names
#   make eval-run EVAL_ARGS="--dense query --weights 0.7,0.3 --rerank"
#
# Both print which legs actually ran. A dense leg whose embedder is missing
# scores zero and a rerank without `ml` is skipped, and neither raises — so the
# line under the number is what separates a measurement from a number.
EVAL_POOL ?= tests/evaluation/pool_blockchain_governance.json
EVAL_RUN ?= tests/evaluation/fixtures/run_20261013_093241
EVAL_QRELS ?= tests/evaluation/qrels_blockchain.json

eval:
	$(PYTHON) tests/evaluation/harness.py --pool $(EVAL_POOL) $(EVAL_ARGS)

eval-run:
	$(PYTHON) tests/evaluation/harness.py --run $(EVAL_RUN) --qrels $(EVAL_QRELS) $(EVAL_ARGS)

lint:
	$(RUFF) check src/ tests/

# Not a gate, and not run by CI: it rewrites most of the tree today, and how
# much is not quoted here because it moves with every commit — run
# `ruff format --check src/ tests/` for the number that is true right now. The
# only path that can trigger it unasked is the ruff-format pre-commit hook, and
# only where `pre-commit install` was run.
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
