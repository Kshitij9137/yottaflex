ChatGpt prompt:

Act as a rigorous, evidence-based technical reviewer of the attached repository for an apprenticeship assignment. Review the actual code, tests, generated data, reports, documentation, and CI configuration. Do not flatter me, infer facts you cannot verify, or claim to know the employer’s private screening criteria.

Assignment:
Problem statement
Read it carefully. Your build should cover every point below.

Business Context / Problem
Analyze synthetic engagement, tenure, role and workload signals to prioritize supportive retention conversations.

Objective and Scope
Build a working solution for this end-to-end workflow: Analyze synthetic engagement, tenure, role and workload signals to prioritize supportive retention conversations. The solution should expose key decisions and exceptions, preserve traceability, and produce measurable outputs. Medium complexity means multiple related entities, conditional rules, at least one exception path and meaningful evaluation metrics.

Primary Actors / Systems
Employee/candidate, manager, HR partner, IT/operations partner and system administrator

Business Workflow and Rules
1. Generate/reference master data first: Employee, Role, Team, TenureSnapshot, EngagementSurvey.
2. Generate dependent transaction/event records using valid parent IDs.
3. Apply business logic: Generate longitudinal workforce snapshots; define survey scales and missingness; create workload and career progression histories; label voluntary attrition at a future horizon; ensure only pre-outcome features are used; create intervention records and simulated outcomes.
4. Persist state changes as explicit records/events where relevant; do not overwrite history.
5. Generate outcomes and ground-truth labels from documented rules, not independent random assignment.

Entities and Relationships
Core entities: Employee, Role, Team, TenureSnapshot, EngagementSurvey, WorkloadSnapshot, CompensationBand, PromotionHistory, AttritionOutcome, Intervention. Define a primary key for every entity and foreign keys for every relationship. Document cardinality (1:1, 1:N, N:M), optional relationships, effective dates and lifecycle states. Use bridge tables for many-to-many relationships; retain event history for state changes; validate all joins. For deliberate anomaly cases, keep an issue_type/ground_truth label rather than silently corrupting unrelated rows.

ID / Nomenclature Conventions
EMP-000001; SNAP-<employee-id>-2026Q1; SURV-2026-000001; INT-2026-000001; OUT-<employee-id>-2026.

Synthetic Data Generation Instructions (Granular)
Step 1 — Write a data dictionary for: Employee, Role, Team, TenureSnapshot, EngagementSurvey, WorkloadSnapshot, CompensationBand, PromotionHistory, AttritionOutcome, Intervention. For each field specify type, required/optional, allowed values, units, uniqueness and validation rule.
Step 2 — Create parent/master tables first, then child and event tables. Apply this domain-specific generation logic: Generate longitudinal workforce snapshots; define survey scales and missingness; create workload and career progression histories; label voluntary attrition at a future horizon; ensure only pre-outcome features are used; create intervention records and simulated outcomes.
Step 3 — Apply deterministic IDs and naming: EMP-000001; SNAP-<employee-id>-2026Q1; SURV-2026-000001; INT-2026-000001; OUT-<employee-id>-2026. Keep counters zero-padded, IDs immutable, and referenced IDs exactly consistent across files.
Step 4 — Generate the baseline volume: Generate 10,000 synthetic employee histories over 24 months with 5–15% attrition. Include benign high workload periods, internal transfers and missing surveys. Avoid sensitive attributes and proxies. Use a fixed seed (e.g. 20261022) and parameterize scale so starter and full datasets use the same generator.
Step 5 — Generate valid baseline records first, then inject labelled edge cases: Future information leaks into features; missing survey treated as negative; outcome label inconsistent with termination date; individual score used without explanation or human review.
Step 6 — Calculate derived values (totals, balances, scores, statuses and dates) from source records rather than generating them independently.
Step 7 — Produce a separate ground_truth.csv/json for known anomalies, expected decisions or labels; never leak it into input features.
Step 8 — Run validation: primary-key uniqueness, foreign-key integrity, allowed enums, date ordering, arithmetic reconciliation, lifecycle transitions and duplicate checks.
Step 9 — Export CSV/JSON/SQL seed data plus README, schema/data dictionary, generator command, fixed seed, source manifest and validation summary.
Step 10 — Regenerate twice with the same seed and compare row counts/checksums to demonstrate reproducibility.

Suggested Volume and Coverage
Generate 10,000 synthetic employee histories over 24 months with 5–15% attrition. Include benign high workload periods, internal transfers and missing surveys. Avoid sensitive attributes and proxies.

Required Edge Cases / Negative Scenarios
Future information leaks into features; missing survey treated as negative; outcome label inconsistent with termination date; individual score used without explanation or human review.

Validation Rules / Acceptance Criteria
Temporal evaluation is used; factors are explainable; sensitive data is excluded; outputs are framed as supportive signals, not automatic employment decisions.

Evaluation Focus for Generated Data
Review: (a) realistic distributions and meaningful variation; (b) consistent IDs and valid joins; (c) dependency/lifecycle consistency across entities; (d) correct derived values and reconciliation; (e) normal, boundary, failure and exception coverage; (f) separate ground truth; (g) fixed-seed reproducibility, documentation and lawful provenance.

Public Data Guidance / Lawful Use
External data is optional. If used, record source URL, dataset/version, retrieval date, license/terms, attribution, transformations and fields discarded. Use only data you are legally permitted to access and redistribute; do not bypass access controls or collect confidential/personal information. If licensing or suitability is unclear, use synthetic data and cite public reference data only for schema inspiration.

Check the repository against every requirement, especially:
- Entity schemas, primary/foreign keys, relationships, effective dates, lifecycle history, and valid joins.
- Deterministic IDs, parent-before-child generation, 10,000 synthetic employee histories over 24 months, attrition rates, missing surveys, benign workload peaks, transfers, and fixed-seed reproducibility.
- Documented outcome-label rules, pre-outcome-only features, intervention records and outcomes, and ground truth kept separate from model inputs.
- Validation of uniqueness, foreign keys, enums, dates, arithmetic, lifecycle transitions, and known anomaly cases.
- Temporal evaluation, leakage checks, interpretable factors, meaningful metrics, sensitive-data exclusions, proxy-risk limitations, and supportive—not automated employment—use.
- Consistency between code, README, reports, generated outputs, and submission disclosures.

For every conclusion, cite the specific file and relevant line or section. Mark each requirement as met, partial, unmet, or unverified. Separate confirmed findings from recommendations. If you did not run a command, do not imply that you did; report the commands and results I should run to verify anything you could not execute.

Return:
1. A concise overall assessment and any submission blockers.
2. A requirements matrix with evidence.
3. Prioritized, specific fixes for any gaps or contradictions.
4. Any important limitations or uncertainties.

Do not modify files. Do not promise that this will pass screening or lead to an interview.

