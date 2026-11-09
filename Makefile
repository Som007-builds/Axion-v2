.PHONY: lint typecheck test report

PYTHON ?= python

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest

report:
	@echo "not implemented"
