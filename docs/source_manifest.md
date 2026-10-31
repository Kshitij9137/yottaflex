# Source Manifest

## External data

**No external data was used.** Every record in this repository is synthetic and produced by
`python -m yottaflex.generate`. No dataset was downloaded, scraped, or copied; no URL, licence,
retrieval date, attribution, or field-discard log applies. No access controls were bypassed and no
confidential or personal information was collected.

| Item | Value |
|---|---|
| External datasets | None |
| Source URLs / dataset versions / retrieval dates | Not applicable |
| Licences or terms of use | Not applicable (data is original and synthetic, released under this repository MIT licence) |
| Transformations applied to external data | Not applicable |
| Fields discarded from external data | Not applicable |
| Schema inspiration | The entity list and rules come from the assignment brief only. [CONFIRM: no public HR dataset was consulted. If one was, list it here.] |

## Provenance of the synthetic data

| Item | Value |
|---|---|
| Generator | `src/yottaflex/generate` (one code path for starter and full scale) |
| Fixed seed | `20261022` (independent named streams derived with `numpy.random.SeedSequence`) |
| Full dataset | `python -m yottaflex.generate --n-employees 10000 --seed 20261022 --out data/full` |
| Starter dataset | `python -m yottaflex.generate --n-employees 500 --seed 20261022 --out data/starter` |
| Exports (JSON, SQL seed) | `python -m yottaflex.export --data data/full` |
| Python dependencies | pinned in `requirements-lock.txt` |
| Integrity evidence | `generation_report.json` (SHA-256 of every CSV) and `docs/reproducibility_*.md` (two identical runs, plus a different-seed control that differs) |

## Sensitive data

No sensitive attributes or proxies are generated: age, gender, ethnicity, religion, caste, nationality,
disability or health, family status, leave type, location or PIN code, and names are excluded by design
(see `docs/design_decisions.md`, section 10). The model audit checks this again.