# Repository Review Prompt Record

The following is the review request retained in the project. The tool and date associated with this individual record were not recorded, so they are not inferred. This is a selected prompt record, not a complete AI conversation transcript.

prompt:

Please review my repository against the assignment below. I’m preparing this project for an apprenticeship submission and want an honest, evidence-based assessment of how well it meets the technical requirements.

Review the actual source code, tests, generated data, reports, documentation, and CI configuration. Don’t assume a requirement is satisfied just because the README says so. Don’t flatter me, invent evidence, or claim to know the employer’s private screening criteria.

## Assignment

### Business context and objective

Build an end-to-end solution that analyzes **synthetic** engagement, tenure, role, and workload signals to prioritize supportive retention conversations. It should expose important decisions and exceptions, preserve traceability, and produce measurable outputs. The expected complexity includes multiple related entities, conditional business rules, at least one exception path, and meaningful evaluation metrics.

The primary actors and systems are the employee or candidate, manager, HR partner, IT or operations partner, and system administrator.

### Workflow and business rules

1. Generate or reference master data first: Employee, Role, Team, TenureSnapshot, and EngagementSurvey.
2. Generate dependent transactions and events using valid parent IDs.
3. Generate longitudinal workforce snapshots; define survey scales and missingness; create workload and career-progression histories; label voluntary attrition at a future horizon; ensure features use only information available before the outcome; and create intervention records with simulated outcomes.
4. Persist relevant state changes as explicit records or events rather than overwriting history.
5. Derive outcomes and ground-truth labels from documented rules, not independent random assignment.

### Entities, relationships, and identifiers

The core entities are Employee, Role, Team, TenureSnapshot, EngagementSurvey, WorkloadSnapshot, CompensationBand, PromotionHistory, AttritionOutcome, and Intervention.

For every entity, define a primary key; define foreign keys for relationships; and document cardinality (1:1, 1:N, or N:M), optionality, effective dates, and lifecycle states. Use bridge tables for many-to-many relationships, preserve state-change history, and validate joins. For deliberate anomaly cases, label the issue type and ground truth rather than silently corrupting unrelated records.

Use deterministic, immutable IDs with zero-padded counters and consistent references across files. Examples:

- `EMP-000001`
- `SNAP-<employee-id>-2026Q1`
- `SURV-2026-000001`
- `INT-2026-000001`
- `OUT-<employee-id>-2026`

### Synthetic data and generation

Create a data dictionary for each core entity. For every field, specify its type, whether it is required or optional, allowed values, units, uniqueness, and validation rules.

Generate parent/master records before dependent records. Use a fixed seed (for example, `20261022`) and parameterize the scale so starter and full datasets use the same generator. The full dataset should contain 10,000 synthetic employee histories spanning 24 months, with 5–15% voluntary attrition. Include benign high-workload periods, internal transfers, and missing surveys. Do not generate sensitive attributes or use them as model features.

Generate valid baseline records before injecting clearly labelled edge cases:

- Future information leaking into model features.
- A missing survey being treated as a negative signal.
- An attrition label that conflicts with the termination date.
- An individual score being used without explanation or human review.

Calculate derived values—including totals, balances, scores, statuses, and dates—from their source records rather than generating them independently.

Keep known anomalies, expected decisions, or labels in a separate `ground_truth.csv` or `ground_truth.json`; never expose ground truth as an input feature.

### Validation, outputs, and reproducibility

Validate primary-key uniqueness, foreign-key integrity, allowed values, date ordering, arithmetic reconciliation, lifecycle transitions, and duplicates.

Export CSV, JSON, and/or SQL seed data, along with a README, schema and data dictionary, generator command, fixed seed, source manifest, and validation summary.

Regenerate the data twice with the same seed and compare row counts and checksums to demonstrate reproducibility.

### Evaluation and lawful data use

Assess realistic distributions and meaningful variation; consistent IDs and valid joins; entity dependencies and lifecycle consistency; correct derived values and reconciliations; normal, boundary, failure, and exception coverage; separation of ground truth; reproducibility; documentation; and lawful data provenance.

Use temporal evaluation. Make model factors explainable, exclude sensitive data, and frame outputs as supportive signals—not automatic employment decisions.

External data is optional. If used, document the source URL, dataset and version, retrieval date, license or terms, attribution, transformations, and fields discarded. Use only data that may legally be accessed and redistributed. Do not bypass access controls or collect confidential or personal information. If licensing or suitability is unclear, use synthetic data and cite public data only as schema inspiration.

## What I’d like you to assess

Check the repository against every assignment requirement, including:

- Entity schemas, keys, relationships, effective dates, lifecycle history, and join integrity.
- Generation order, deterministic IDs, dataset size and duration, attrition, missing surveys, benign workload peaks, transfers, and reproducibility.
- Documented outcome-label rules, feature time boundaries, interventions and simulated outcomes, and separation of ground truth from model inputs.
- Validation coverage, including the required anomaly cases.
- Temporal evaluation, leakage checks, explainability, meaningful metrics, sensitive-data exclusions, proxy-risk limitations, and the intended supportive use of outputs.
- Consistency among the implementation, README, reports, generated files, and disclosures.

For each conclusion, cite the relevant file and line numbers or document section. Mark each requirement **met**, **partially met**, **not met**, or **unverified**. Distinguish findings confirmed from repository evidence from recommendations.

Do not claim to have run commands or tests unless you actually ran them. If you cannot verify something by inspection or execution, say what remains uncertain and provide the specific command or check I should run.

Please return:

1. A concise overall assessment, including any submission blockers.
2. A requirements matrix with status and evidence.
3. Prioritized, specific recommendations for gaps or contradictions.
4. Important limitations or uncertainties.

Do not modify the repository, and do not promise that the project will pass screening or lead to an interview.
