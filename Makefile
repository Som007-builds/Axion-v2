.PHONY: lint typecheck test report day0-check ablate ablate-report

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
	$(PYTHON) scripts/build_p1_report.py

ablate:
	$(PYTHON) scripts/ablate.py --all

ablate-report:
	$(PYTHON) scripts/ablate.py --all --report docs/reports/P2-ablation.md
