# Convenience targets for macOS/Linux and CI. On Windows, run the commands from the README.
PY ?= python

.PHONY: install test starter full validate model export repro all clean

install:
	$(PY) -m pip install -r requirements-lock.txt
	$(PY) -m pip install -e .

test:
	$(PY) -m pytest

starter:
	$(PY) -m yottaflex.generate --n-employees 500 --seed 20261022 --out data/starter
	$(PY) -m yottaflex.export --data data/starter

full:
	$(PY) -m yottaflex.generate --n-employees 10000 --seed 20261022 --out data/full

validate:
	$(PY) -m yottaflex.validate --data data/full --report docs/validation_summary.md

model:
	$(PY) -m yottaflex.model --data data/full --out data/full/model --report docs/model_report.md

export:
	$(PY) -m yottaflex.export --data data/full

repro:
	$(PY) scripts/repro_check.py --n-employees 500 --label starter
	$(PY) scripts/repro_check.py --n-employees 10000 --label full --compare-committed data/full

all: full validate model export test

clean:
	rm -rf .pytest_cache build dist *.egg-info
