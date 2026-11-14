.PHONY: lint typecheck test report day0-check

PYTHON ?= python

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest

day0-check:
	$(PYTHON) scripts/day0_check.py

report:
	@echo "not implemented"
