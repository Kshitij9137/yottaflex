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

I got these 2 mail:
Hi Kshitij Gupta,
Congratulations! You've cleared the AI Screening, and you're through to Round 3: the 72 Hours Code Challenge. You're now among a small group of candidates, and that says a lot about you.
This is where you get to build something real. Your problem statement is waiting for you on the portal.
Your 72 hours end on: Monday, November 2, 2026 at 1:01:51 AM India Standard Time

Hi Kshitij Gupta,
Congratulations! You've cleared the AI Screening, and you're through to Round 3: the 72 Hours Code Challenge. You're now among a small group of candidates, and that says a lot about you.
This is where you get to build something real. Your problem statement is waiting for you on the portal.
Your 72 hours end on: Monday, November 2, 2026 at 12:47:42 AM India Standard Time
View your problem statement
What to submit

Put your code and everything the problem statement asks for in one GitHub repository.
Submit your repository link on the portal before the deadline.

Important: your repository must be public
We can only assess public GitHub repositories. If your repository is private, we can't open it, and your submission won't clear this round. Before you submit, open your link in a private browser window to check it works.
You're welcome to use AI coding tools. Just make sure you understand every line you submit, because you may be asked to explain your work in later rounds.
Plan your time, build what you're proud of, and enjoy it. We can't wait to see what you create.
We're rooting for you.
Warm regards,
Talent Acquisition Team
YottaFlex AI Technologies Pvt. Ltd.

For now explain this project to me and create to - do plan to build this. You have to help me clear this coding challenge. Do you best

What this project is

It’s a synthetic HR data generator plus a small analytics pipeline, not a product. YottaFlex wants to see whether you can:

Design a realistic relational data model (10 entities, keys, lifecycles).
Generate 10,000 employee histories where outcomes come from documented rules, not random coin flips.
Inject labelled mistakes (data leaks, bad labels, and so on) and prove you can detect them.
Build an explainable, supportive “who might benefit from a retention conversation” signal with honest, time-based evaluation.
Be reproducible, documented, and transparent about your AI use.

Reviewers will judge judgment, working software, honest AI disclosure and clear communication, so the README and reasoning matter as much as the code.

Deadline warning

Your two emails show different deadlines: 12:47:42 AM IST and 1:01:51 AM IST, both on Monday, Nov 2. Treat the earlier one as the real deadline and confirm on the portal. In practice, aim to submit by Sunday, Nov 1 evening, leaving a buffer for repo-visibility checks. Keep all commits inside the window, because timestamps are used for verification. Don’t force-push or rewrite history.

Key concepts
Workflow: master tables (Employee, Role, Team, CompensationBand), then dependent tables (TenureSnapshot, EngagementSurvey, WorkloadSnapshot, PromotionHistory, Intervention, AttritionOutcome). Parents are created first so every foreign key is valid.
Labels from rules: attrition comes from a documented risk function (low engagement, long promotion stagnation, low pay ratio, sustained overload) plus noise, then calibrated to land at 5–15% overall.
Benign cases: a high-workload period with no engagement drop (e.g. a quarterly peak) should not strongly raise risk. Internal transfers must not look like attrition.
Pre-outcome features only: features come from snapshots dated before the prediction cutoff. Labels come from the horizon after it.
Four injected anomalies, each labelled in a separate ground_truth file that never touches the features:
Future information leaks into features.
A missing survey treated as a negative score.
An outcome label inconsistent with the termination date.
An individual score used without explanation or human review.
Framing: outputs are “supportive signals” that need human review. Never present them as automatic employment decisions. Exclude sensitive attributes and proxies (age, gender, ethnicity, religion, health, marital status, home location and so on).
Design decisions to settle early
Timeline: 24 months = 8 quarterly snapshots (e.g. 2025Q1 to 2026Q4). The ID SNAP-EMP-000001-2026Q1 fits this.
Outcome ID: OUT-<employee-id>-2026 allows one outcome per employee. I suggest storing prediction_cutoff_date, horizon_end_date and the label on it. Temporal evaluation then trains on an earlier cutoff and tests on a later one, with the training labels fully observed before the test cutoff. Document this clearly.
Bridge tables: Employee↔Team over time (EmployeeTeamAssignment, which handles transfers and effective dates), and Intervention↔reviewer/participant if needed.
Event history: never overwrite. Role changes, transfers, interventions and terminations are new rows with effective dates.
Suggested stack

Python 3.11, numpy (default_rng(20261022)), pandas, scikit-learn, pytest, SQLite for the SQL seed, and a single CLI (python -m yottaflex.generate --n-employees 10000 --seed 20261022). The --n-employees flag is how you get a small starter set and the full set from one generator.

Repo structure
README.md
docs/ (data_dictionary.md, design_decisions.md, ai_usage.md, validation_summary.md, source_manifest.md)
prompts/ (exported chat history)
src/ (generate/, validate/, model/, report/)
tests/
data/ (starter/ and full/: csv, json, sql, ground_truth)
Makefile
To-do plan (72 hours)
Phase 0: Setup (about 1 hour)
 Create the public repo, add a .gitignore, LICENSE and a skeleton README.
 Start prompts/ and save every AI conversation, including this one.
 Make the first commit.
Phase 1: Design (Day 1, about 4–5 hours)
 Write the data dictionary for all 10 entities: type, required/optional, allowed values, units, uniqueness, validation rule.
 Draw the ER diagram with PKs, FKs, cardinality, optional relationships and lifecycle states.
 Write the risk-rule spec: factors, weights, the benign-workload exception, and attrition calibration to a target of around 10%.
 Define the ID formats and zero-padding helpers.
Phase 2: Generator (Day 1–2, about 8–10 hours)
 Master tables: Role, Team, CompensationBand, Employee.
 Snapshots: Tenure and Workload (with benign peaks) quarterly, plus engagement surveys with scales and realistic missingness.
 Promotion history and internal transfers.
 Latent risk, then voluntary attrition and termination dates, then AttritionOutcome labels, all derived from rules.
 Interventions with simulated outcomes (a modest effect, not a magic fix).
 Derived values computed from source records, never generated independently.
 Parameterized scale and fixed seed.
Phase 3: Anomalies and ground truth (Day 2, about 3 hours)
 Inject the four edge cases at a small, labelled rate into the data.
 Write a separate ground_truth.csv/json with issue_type, entity, record ID and expected decision.
Phase 4: Validation (Day 2, about 4 hours)
 Check PK uniqueness, FK integrity, enums, date ordering, reconciliation, lifecycle transitions and duplicates.
 Write detectors for the four anomaly types and score them against the ground truth (precision and recall).
 Output a validation_summary.
Phase 5: Explainable model and evaluation (Day 2–3, about 6 hours)
 Use a simple, interpretable baseline (logistic regression, possibly with gradient boosting for comparison).
 Do a temporal split, and show a leak-checked pipeline where the leaked feature visibly inflates the metric and then gets caught.
 Report PR-AUC, precision/recall@top-k, lift and calibration.
 Give per-employee top contributing factors in plain language.
 Make every output carry a “supportive signal, human review required” flag and a reviewer field.
 Run a proxy and sensitive-attribute check.
 Optionally add a small report or Streamlit view for managers and HR.
Phase 6: Reproducibility and exports (Day 3, about 3 hours)
 Export CSV, JSON and SQL seed files.
 Regenerate twice with the same seed and compare row counts and SHA-256 checksums, with a script and logged proof.
 Write the source manifest (state “no external data used”).
Phase 7: Tests and docs (Day 3, about 4 hours)
 Write pytest tests for ID formats, FK integrity, determinism and anomaly detection.
 Finish the README: install, configure, run, verify, assumptions, trade-offs, limitations.
 Write ai_usage.md: where AI accelerated you, where you relied on it heavily, and what you reviewed, changed or validated.
 Keep commits small and meaningful.
Phase 8: Submit (Sunday, with buffer)
 Clone the repo fresh and run the README steps from scratch.
 Open the repo in a private browser window to confirm it’s public.
 Submit the link on the portal at least several hours early.
 Prepare your walkthrough: the problem, key decisions, how you know it works, and the limitations.
Pitfalls to avoid
Random labels that don’t follow your documented rules.
Anomalies that corrupt unrelated rows. Each one needs a label.
ground_truth leaking into features.
Claiming the model is accurate without a temporal split.
Submitting code you can’t explain. You’ll be asked to walk through it, so understand every part.

I’d suggest starting with Phase 1, the data dictionary and ER design, since everything else depends on it. Want me to draft that next, including the entity fields, keys and risk-rule spec?