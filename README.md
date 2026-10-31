# YottaFlex Retention Signals

Synthetic workforce data and an explainable model that prioritises **supportive retention conversations**.
It is a decision-support signal for HR partners, never an automatic employment decision.

The repository generates a reproducible synthetic dataset (10,000 employees over 24 months, about 10%
voluntary attrition) with 11 linked entities, injects four labelled data-quality problems with a separate
ground truth, validates the data with 171 rules, trains a transparent logistic-regression model with a
temporal split and a leak audit, and proves that the same seed gives byte-identical output.
All data is synthetic. No external data is used (`docs/source_manifest.md`).

## Quick start

Python 3.10 or newer. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1                      # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-lock.txt  # the exact versions the results were produced with
python -m pip install -e .
```

Generate, validate, model and export (the full pipeline, a few minutes):

```powershell
python -m yottaflex.generate --n-employees 10000 --seed 20261022 --out data/full
python -m yottaflex.validate --data data/full --report docs/validation_summary.md
python -m yottaflex.model    --data data/full --out data/full/model --report docs/model_report.md
python -m yottaflex.export   --data data/full
```

A small starter dataset uses the same generator: `--n-employees 500 --out data/starter`.
Use `--no-inject` to generate the clean baseline without injected anomalies or ground truth.
On macOS/Linux, `make all` runs the same steps (see `Makefile`).

## Verify

```powershell
python -m pytest                                                   # 126 tests, about two minutes
python scripts/repro_check.py --n-employees 500 --label starter    # regenerate twice, compare SHA-256
python scripts/repro_check.py --n-employees 10000 --label full --compare-committed data/full
```

`repro_check.py` regenerates the data twice with the same seed, plus a different-seed control that must
differ, and writes the row counts and SHA-256 of every file to `docs/reproducibility_<label>.md`.

## What you get

| Output | Where |
|---|---|
| 11 CSV tables, `generation_report.json` (seed, command, SHA-256 of every file) | `data/<scale>/` |
| `ground_truth.csv` / `.json`: injected anomalies and benign decoys, never read by validator or model | `data/<scale>/` |
| JSON per table, `schema.sql` (PK, FK), `seed.sql` | `data/<scale>/export/` |
| Retention signals (top 5%, explanation, reviewer slot), coefficients, subgroup audit, metrics | `data/full/model/` |
| Data dictionary, design decisions, validation summary, model report, source manifest, AI usage | `docs/` |

Entities: Employee, Role, Team, TenureSnapshot, EngagementSurvey, WorkloadSnapshot, CompensationBand,
PromotionHistory, AttritionOutcome, Intervention, plus a bridge table `EmployeeTeamAssignment`
(Employee N:M Team over time, so internal transfers are new rows, never updates).
IDs follow the brief: `EMP-000001`, `SNAP-EMP-000001-2026Q1`, `SURV-2026-000001`, `INT-2026-000001`, `OUT-EMP-000001-2026`.

## Repository layout

```
src/yottaflex/
  config.py ids.py dates.py labels.py io.py   shared constants, ID helpers, the single label function, deterministic CSV writer
  generate/    masters, simulate (risk rule + attrition), tables, anomalies, calibrate, params, rng, CLI
  validate/    schema (machine-readable data dictionary), rules (171), evaluate (precision/recall), report, CLI
  model/       features (as-of), dataset (temporal splits), train, metrics, explain, audit, report, CLI
  export.py    JSON + SQL seed export with a load-and-verify check
scripts/repro_check.py    the two-run reproducibility proof
tests/                    generator, IDs, validator, model, export, CLI, docs hygiene
docs/                     design and evidence documents (see below)
```

## Key decisions

Full reasoning is in [docs/design_decisions.md](docs/design_decisions.md). The ones that matter most:

- **Outcomes come from a documented rule, not random labels.** A transparent hazard rule (engagement, stagnation,
  pay gap, non-peak overload, early tenure, plus unobservable noise) drives attrition. The intercept is solved
  so that voluntary attrition lands on the 10% target (measured: 10.02% voluntary, 1.50% involuntary).
- **State is never overwritten.** Transfers, promotions and interventions are new dated rows. Outcomes are
  derived from termination facts by one function (`labels.py`), so a stored label can always be re-derived and checked.
- **Missing is not negative.** Every quarter has a survey row; non-response is an explicit `Skipped` status
  with a null score, and a skipped survey never becomes a low score.
- **Anomalies are labelled, not silent.** Four problems (future-information leak, missing survey scored as
  negative, label inconsistent with termination date, individual score without explanation or review) are
  injected at small rates, with benign decoys (planned workload peaks, internal transfers, skipped surveys)
  that look suspicious but must not be flagged.
- **Temporal evaluation.** Features are as of a cutoff using only rows recorded by that day. Train, validation
  and test cutoffs are 2025-03-31, 2025-09-30 and 2026-03-31 with six-month labels, and each horizon ends before the next cutoff.
- **Supportive framing is enforced in code.** No row is emitted without a plain-language explanation, a reviewer slot,
  `human_review_required = True` and `automated_action_allowed = False`.

## Results

Detailed tables are in [docs/validation_summary.md](docs/validation_summary.md) and [docs/model_report.md](docs/model_report.md).

| Question | Result |
|---|---|
| Does the validator pass the clean baseline? | 0 rule violations |
| Are the four anomaly detectors accurate? | Precision 1.00 and recall 1.00 for all four types against the ground truth, 0 of 900 decoys flagged |
| Does the model rank future leavers? | Test ROC-AUC 0.713, PR-AUC 0.094 against a 0.035 base rate. Reviewing the top 5% finds about 20% of later voluntary leavers (4.1x lift) |
| Does a complex model help? | No. Gradient boosting does not beat the explainable model |
| Are leaks caught? | Yes. A 25-row `recorded_at` leak lifts PR-AUC from 0.094 to 0.126 and fails the audit; a blatant leak reaches 0.983 and is named |
| Is the output reproducible? | Same seed gives identical SHA-256 for every file; a different seed differs |

## Assumptions and trade-offs

- Performance is modest on purpose. With a 3.5% base rate and noise the generator adds, ROC-AUC near 0.7 is
  close to the ceiling set by the generating rule (0.722). A model that scored much higher would be suspicious.
- Intervention effects are small and assumed (hazard multipliers 0.75 to 0.90), so they are not evidence of what works in a real company.
- The top 5% list over-represents long-tenure and under-represents first-year employees. The model report shows
  this trade-off instead of hiding it.
- The model treats a recent conversation as a feature, so a good intervention process makes the model look worse over time.

## Limitations

- Everything is synthetic. Results show that the pipeline behaves correctly, not how real attrition works (L1).
- The generating mechanism is a simple transparent rule with a fixed manager per team; real drivers such as manager
  quality, life events and the labour market are not modelled (L2 to L4).
- The 6-month horizon gives about 315 positives per cutoff, so confidence intervals are wide (L7).
- `engagement_delta` after an intervention is confounded by regression to the mean and must not be read as a causal effect (L8).
- The validator and the generator share two helper functions (`months_between`, `derive_label`), so a bug in those
  would not be caught by the validator. Tests cover them separately.

The complete list (L1 to L11) is in section 12 of [docs/design_decisions.md](docs/design_decisions.md).

## AI usage

See [docs/ai_usage.md](docs/ai_usage.md) for the AI-use disclosure and the status of prompt-history records.

## Licence

MIT, see `LICENSE`.
