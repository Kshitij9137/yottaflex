# YottaFlex Retention Signals (Synthetic Data + Explainable Model)

One-paragraph summary of the problem and approach.

## Status
Work in progress (challenge started 30 Oct 2026).

## Quick start

From the repository root, install the project into the active Python environment
and generate the full dataset:

```powershell
python -m pip install -e .
python -m yottaflex.generate --n-employees 10000 --seed 20261022 --out data/full
```

Use `--no-inject` to generate the clean baseline without injected anomalies or
ground truth.

## Repository layout
(to be filled)

## Key design decisions
(link to docs/design_decisions.md)

## Validation and reproducibility
(link to docs/validation_summary.md)

## AI usage disclosure
See docs/ai_usage.md and prompts/.

## Limitations
(to be filled)
