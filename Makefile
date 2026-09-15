# One-click reproduction: `make all` (setup, tests, data, features, grid, importance, figures).
# Every target is a thin wrapper over the `netleak` CLI; see README.md and AGENTS.md.

PY ?= python3.11
BIN := .venv/bin
DATASETS := os_detection video_services

.PHONY: all setup test lint smoke data features grid importance figures clean-cache

all: setup test grid importance figures

setup:
	$(PY) -m venv .venv
	$(BIN)/pip install -q -e ".[dev]"

test:
	$(BIN)/pytest -q

lint:
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

smoke:
	$(BIN)/netleak smoke

data:
	for d in $(DATASETS); do $(BIN)/netleak download -d $$d || exit 1; done

features: data
	for d in $(DATASETS); do $(BIN)/netleak features -d $$d || exit 1; done

grid: features
	for d in $(DATASETS); do $(BIN)/netleak grid -d $$d || exit 1; done

importance: features
	for d in $(DATASETS); do $(BIN)/netleak importance -d $$d --rung R1 --model lgbm || exit 1; done

figures:
	$(BIN)/netleak figures

clean-cache:
	rm -rf cache/
