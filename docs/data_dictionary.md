# Data Dictionary

All data is **synthetic**. No external datasets are used (see `source_manifest.md`).

## Conventions

- **Types:** `str`, `int`, `float`, `bool`, `date` (ISO `YYYY-MM-DD`), `datetime` (ISO-8601 UTC, `...Z`).
- **Req:** `Y` = required, `N` = optional (null allowed; reason in the rule column), `D` = derived (must reconcile to source records; never generated independently).
- **PK** = primary key. **FK** = foreign key, written `-> Table.field`.
- **Append-only:** historical rows are never updated. State changes are new rows or dated stage columns.
- **Time window:** 2024-10-01 to 2026-09-30 (24 months, 8 quarters: 2024Q4, 2025Q1 ... 2026Q3). Quarter token format `YYYYQn`.
- **`recorded_at`:** when the row became available in the system. A row may be used as a model feature at cutoff `C` only if `recorded_at <= C 23:59:59Z`. This is the core anti-leakage rule. Regular rows are recorded on or before the close of their own snapshot day; anything later is an anomaly.
- **Booleans** are written as `True`/`False` in CSV. Nulls are empty cells.
- **Currency:** INR, annual, whole rupees.
- **Excluded on purpose:** age, gender, ethnicity, religion, caste, nationality, disability/health, marital/family status, leave type, home location or PIN code, names. See `design_decisions.md` section 10.

---

## 1. Role (master)

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| **role_id** (PK) | str | Y | `ROLE-001` ... `ROLE-999` | - | Y | Matches regex |
| role_title | str | Y | `<job_family> L<level>` | - | Y | Equals family + level |
| job_family | str | Y | Engineering, Product, Sales, Customer_Support, Operations, IT_Ops, People_HR | - | with level | In enum |
| level | int | Y | 1-5 | level | with job_family | 1 <= level <= 5 |
| is_people_manager_track | bool | Y | true/false | - | N | True only if level >= 4 |

Cardinality: 35 rows (7 families x 5 levels). Immutable catalog.

## 2. CompensationBand (master, effective-dated)

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| **band_id** (PK) | str | Y | `BAND-<role number>-<FY start year>`, e.g. `BAND-003-2025` | - | Y | Matches regex |
| role_id | str | Y | FK -> Role.role_id | - | N | Must exist |
| effective_from | date | Y | 1 April of FY start year | - | with role_id | Version year = year(effective_from) |
| effective_to | date | N | 31 March of next year; null = open (current version) | - | N | >= effective_from; versions of a role do not overlap and are contiguous |
| currency | str | Y | INR | - | N | Constant |
| annual_min | int | Y | > 0 | INR/yr | N | min < mid < max |
| annual_mid | int | D | round((min + max) / 2) | INR/yr | N | Reconciles to min and max |
| annual_max | int | Y | > annual_min | INR/yr | N | - |

Cardinality: Role 1 : N CompensationBand (3 versions per role: FY2024, FY2025, FY2026). Mid-points rise about 4% per FY.

## 3. Employee (master)

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| **employee_id** (PK) | str | Y | `EMP-000001` ... `EMP-999999` | - | Y | Matches regex; immutable |
| hire_date | date | Y | 2016-01-01 to 2026-06-30 | - | N | <= first snapshot date; <= exit date |
| initial_role_id | str | Y | FK -> Role.role_id | - | N | Must exist |
| employment_type | str | Y | Full_Time, Fixed_Term | - | N | In enum |
| recorded_at | datetime | Y | - | - | N | >= hire_date |

No mutable status column. Current state is derived from AttritionOutcome and the latest snapshot.

## 4. Team (master)

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| **team_id** (PK) | str | Y | `TEAM-0001` ... | - | Y | Matches regex |
| team_name | str | Y | `<job_family> Team <n>` | - | Y | - |
| job_family | str | Y | Same enum as Role | - | N | In enum |
| manager_employee_id | str | Y | FK -> Employee.employee_id | - | N | Manager was hired before the window, has level >= 4 at window start, same job_family. The manager of record may later exit (limitation L3) |
| planned_peak_quarter | int | Y | 1-4 (calendar quarter with a known planned peak, e.g. fiscal close, release) | - | N | 1-4 |
| created_date | date | Y | <= 2024-10-01 | - | N | - |

Manager changes over time are out of scope (limitation L3).

## 5. EmployeeTeamAssignment (bridge, effective-dated)

Resolves Employee N : M Team over time. Internal transfers are new rows, not updates.

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| **assignment_id** (PK) | str | Y | `ASG-000001` ... | - | Y | Matches regex |
| employee_id | str | Y | FK -> Employee.employee_id | - | N | Must exist |
| team_id | str | Y | FK -> Team.team_id | - | N | Must exist |
| effective_from | date | Y | - | - | N | First row per employee = hire_date |
| effective_to | date | N | inclusive end date; null = current | - | N | >= effective_from; next row's effective_from = this effective_to + 1 day (no gap, no overlap); last row = termination_date on exit |
| change_reason | str | Y | Hire, Internal_Transfer, Reorg | - | N | First row = Hire; later rows != Hire |

## 6. TenureSnapshot (longitudinal, quarterly)

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| **snapshot_id** (PK) | str | Y | `SNAP-EMP-000001-2026Q1` | - | Y | = `SNAP-` + employee_id + `-` + quarter |
| employee_id | str | Y | FK -> Employee.employee_id | - | with quarter | Must exist |
| snapshot_quarter | str | Y | `2024Q4` ... `2026Q3` | - | with employee_id | In window |
| snapshot_date | date | Y | Last day of the quarter | - | N | Employee active on that date |
| role_id | str | Y | FK -> Role.role_id | - | N | Reconciles to initial role + PromotionHistory chain |
| team_id | str | Y | FK -> Team.team_id | - | N | Reconciles to the assignment covering snapshot_date |
| tenure_months | int | D | whole months from hire_date to snapshot_date | months | N | Recomputes exactly |
| months_since_last_promotion | int | D | months since last Promotion event, or since hire if none | months | N | Recomputes exactly |
| months_in_current_team | int | D | months since current assignment effective_from | months | N | Recomputes exactly |
| base_salary_annual | int | Y | Within 70%-140% of band mid (generation targets 80%-125%; promotions can land low in the next band) | INR/yr | N | Between consecutive snapshots: unchanged, or +0%-10% merit in Q2 snapshots, or equal to the promotion/lateral event's new salary |
| compa_ratio | float | D | base_salary_annual / annual_mid of band effective on snapshot_date, 3 dp | ratio | N | Recomputes exactly |
| transfer_in_quarter | bool | D | team changed during the quarter | - | N | Matches assignments |
| promotion_in_quarter | bool | D | Promotion event during the quarter | - | N | Matches PromotionHistory |
| recorded_at | datetime | Y | snapshot_date, 18:00-20:59 UTC (end-of-day close) | - | N | Same calendar day as snapshot_date. Later = anomaly (see GT) |

Cardinality: Employee 1 : N TenureSnapshot (0 snapshots is not allowed: every employee has >= 1).

## 7. EngagementSurvey (quarterly pulse)

One row per active employee per quarter, **including non-responders**, so missingness is explicit and never silently dropped.

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| **survey_id** (PK) | str | Y | `SURV-<year>-<6-digit counter>`, counter restarts each year | - | Y | Year = year(survey_date); counter assigned in (employee_id, quarter) order |
| employee_id | str | Y | FK -> Employee.employee_id | - | with snapshot_id | Must exist |
| snapshot_id | str | Y | FK -> TenureSnapshot.snapshot_id | - | Y (1:1) | Same employee as snapshot |
| survey_date | date | Y | 0-20 days before quarter end | - | N | Within the snapshot quarter |
| response_status | str | Y | Responded, Partial, Skipped | - | N | Responded = 5 items, Partial = 3-4, Skipped = 0 |
| q_manager_support | int | N | 1-5 Likert (1 = strongly disagree) | score | N | Null iff not answered |
| q_growth_opportunity | int | N | 1-5 | score | N | same |
| q_workload_sustainable | int | N | 1-5 | score | N | same |
| q_recognition | int | N | 1-5 | score | N | same |
| q_intent_to_stay | int | N | 1-5 | score | N | same |
| items_answered | int | D | count of non-null items | count | N | Matches response_status |
| engagement_score | float | D | 100 x (mean of answered items - 1) / 4, 1 dp; **null if Skipped** | 0-100 | N | Null iff Skipped. A non-null score on a Skipped row is the injected anomaly `missing_survey_as_negative` |
| recorded_at | datetime | Y | survey_date + 0-2 days from 08:00 UTC, never later than 20:59 UTC on the snapshot date | - | N | >= survey_date; <= snapshot close |

Missingness (design): about 18% Skipped and about 4% Partial, with non-response depending on workload, not on intent to leave. See design section 8.

## 8. WorkloadSnapshot (longitudinal, quarterly)

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| **workload_id** (PK) | str | Y | `WKL-EMP-000001-2026Q1` | - | Y | = `WKL-` + employee_id + `-` + quarter |
| employee_id | str | Y | FK -> Employee.employee_id | - | N | Must exist |
| snapshot_id | str | Y | FK -> TenureSnapshot.snapshot_id | - | Y (1:1) | Same employee and quarter |
| avg_weekly_hours | float | Y | 30.0-65.0, 1 dp | hours/week | N | In range |
| active_project_count | int | Y | 0-12 | count | N | In range |
| on_call_days | int | Y | 0-30 | days/quarter | N | In range |
| planned_peak_flag | bool | Y | true if quarter-of-year = Team.planned_peak_quarter | - | N | Must match team calendar |
| overtime_hours_quarter | float | D | max(0, avg_weekly_hours - 40) x 13 | hours | N | Recomputes exactly |
| workload_index | float | D | clip(100 x (0.55 x (hours - 35) / 20 + 0.30 x projects / 8 + 0.15 x on_call / 20), 0, 100), 1 dp | 0-100 | N | Recomputes exactly (tolerance 0.05) |
| high_load_flag | bool | D | workload_index >= 65 | - | N | Recomputes exactly |
| recorded_at | datetime | Y | snapshot_date, 18:00-20:59 UTC | - | N | Same calendar day as snapshot_date |

## 9. PromotionHistory (event log)

Initial role at hire is not an event. Pre-window events are allowed so tenure and stagnation are realistic at window start.

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| **promotion_id** (PK) | str | Y | `PRM-000001` ... | - | Y | Matches regex |
| employee_id | str | Y | FK -> Employee.employee_id | - | N | Must exist |
| event_type | str | Y | Promotion, Lateral_Move | - | N | In enum |
| effective_date | date | Y | - | - | N | >= hire_date and <= exit date |
| from_role_id | str | Y | FK -> Role.role_id | - | N | Equals previous event's to_role_id, or initial_role_id for the first event |
| to_role_id | str | Y | FK -> Role.role_id | - | N | Promotion: same family, level + 1. Lateral_Move: same level, different role |
| prior_base_salary_annual | int | Y | > 0 | INR/yr | N | - |
| new_base_salary_annual | int | Y | > 0 | INR/yr | N | Promotion: 6%-20% higher. Lateral: 0%-5% |
| salary_change_pct | float | D | 100 x (new / prior - 1), 2 dp | % | N | Recomputes exactly |
| recorded_at | datetime | Y | effective_date + 0-3 days from 10:00 UTC, never later than 20:59 UTC on the last day of that quarter | - | N | >= effective_date |

## 10. AttritionOutcome (one row per employee)

Holds termination **facts** (source of truth) and the **primary test label**. Labels for earlier cutoffs (train, validation) are recomputed from `termination_date` by the same single function, never stored independently.

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| **outcome_id** (PK) | str | Y | `OUT-EMP-000001-2026` | - | Y | = `OUT-` + employee_id + `-2026` |
| employee_id | str | Y | FK -> Employee.employee_id | - | Y (1:1) | Must exist |
| final_status | str | Y | Active, Exited_Voluntary, Exited_Involuntary | - | N | Lifecycle: see design section 5 |
| termination_date | date | N | In window; required iff final_status != Active | - | N | > first snapshot date; = last assignment effective_to |
| termination_reason_category | str | N | Better_Opportunity, Career_Growth, Compensation, Workload, Other; only for Exited_Voluntary | - | N | **Post-outcome field. Never a feature** |
| prediction_cutoff_date | date | Y | 2026-03-31 (test cutoff) | - | N | Constant |
| horizon_end_date | date | Y | 2026-09-30 | - | N | = cutoff + 6 months |
| eligible_at_cutoff | bool | D | employee has a snapshot on the cutoff date | - | N | Recomputes exactly |
| voluntary_attrition_label | int | D | 1 if Exited_Voluntary and cutoff < termination_date <= horizon_end; 0 if eligible and not; null if not eligible or Exited_Involuntary inside the horizon (competing event, excluded) | - | N | Recomputes exactly from termination fields. A mismatch is the injected anomaly `label_termination_mismatch` |
| label_rule_version | str | Y | `v1` | - | N | Constant |
| recorded_at | datetime | Y | termination_date + 0-30 days, or 2026-10-15 for Active | - | N | >= termination_date |

## 11. Intervention (retention conversations and simulated outcomes)

Each row is one supportive action. Lifecycle stages are kept as dated columns, so history is never overwritten.

| Field | Type | Req | Allowed values / format | Unit | Unique | Validation rule |
|---|---|---|---|---|---|---|
| **intervention_id** (PK) | str | Y | `INT-<year>-<6-digit counter>`, counter restarts each year | - | Y | Year = year(proposed_date) |
| employee_id | str | Y | FK -> Employee.employee_id | - | N | Must exist |
| trigger_snapshot_id | str | Y | FK -> TenureSnapshot.snapshot_id | - | N | Same employee; proposed_date > snapshot_date |
| trigger_source | str | Y | Signal_Flagged, Manager_Initiated, HR_Initiated | - | N | In enum |
| intervention_type | str | Y | Stay_Conversation, Workload_Rebalance, Career_Path_Discussion, Compensation_Review | - | N | In enum |
| signal_score | float | N | 0-1; required iff Signal_Flagged | prob. | N | Range check |
| signal_top_factors | str | N | JSON list of up to 3 `{factor, contribution}`; required iff Signal_Flagged | - | N | Valid JSON, non-empty (**missing = anomaly `unreviewed_individual_score`**) |
| review_status | str | Y | Not_Required, Pending, Approved, Declined | - | N | Signal_Flagged must not be Not_Required |
| reviewed_by_employee_id | str | N | FK -> Employee.employee_id; required iff Approved or Declined | - | N | Reviewer's role job_family = People_HR |
| reviewed_date | date | N | - | - | N | >= proposed_date |
| proposed_date | date | Y | - | - | N | In window |
| conducted_date | date | N | - | - | N | >= reviewed_date (or proposed_date if Not_Required); <= exit date |
| closed_date | date | N | - | - | N | >= conducted_date |
| status | str | Y | Proposed, Approved, Conducted, Closed, Declined | - | N | Legal transitions only (design section 5) |
| hazard_multiplier | float | D | 1.0 unless conducted; else the documented effect for the type (0.75-0.90) | x | N | Recomputes from type and eligibility rule |
| engagement_delta | float | D | mean of up to 2 post-conduct survey scores minus last pre-conduct score | points | N | Null if scores missing. **Not causal**: triggers fire on low or falling scores, so regression to the mean inflates it (limitation L8) |
| outcome_category | str | D | Improved (delta >= +5), No_Change, Declined (delta <= -5), Not_Applicable (delta null, including not conducted) | - | N | Recomputes from engagement_delta |
| left_within_2_quarters | bool | D | voluntary exit within 182 days after conducted_date; null if never conducted | - | N | Recomputes from AttritionOutcome |

---

## 12. GroundTruth (separate file, never a feature source)

Files: `ground_truth.csv` and `ground_truth.json` (same content). Contains injected anomalies **and** benign decoys (cases that look suspicious but must not be flagged).

| Field | Type | Req | Allowed values / format | Validation rule |
|---|---|---|---|---|
| **gt_id** (PK) | str | Y | `GT-000001` ... | Unique, matches regex |
| issue_type | str | Y | future_information_leak, missing_survey_as_negative, label_termination_mismatch, unreviewed_individual_score, benign_high_workload, benign_internal_transfer, benign_missing_survey | In enum |
| issue_subtype | str | Y | late_recorded_row, snapshot_after_exit, skipped_scored_zero, label_missing_exit, label_without_exit, label_outside_horizon, no_explanation, no_human_review, no_explanation_no_review, planned_peak_healthy_engagement, assignment_closed_by_transfer, skipped_null_score | Belongs to its issue_type |
| entity | str | Y | Table name | Must be a real table |
| record_id | str | Y | PK of the affected row | Must exist in that table |
| field | str | N | Column(s) edited, comma-separated; `(inserted row)` for added rows; empty for decoys | - |
| original_value | str | N | JSON of the pre-injection values (null for inserted rows and decoys) | Valid JSON |
| expected_decision | str | Y | flag, do_not_flag | `flag` iff is_injected |
| is_injected | bool | Y | True for the four anomaly types, False for benign decoys | - |
| description | str | Y | Plain-language reason this record is the expected outcome | - |

Rows are ordered by issue_type, entity, record_id, and `gt_id` is assigned in that order.