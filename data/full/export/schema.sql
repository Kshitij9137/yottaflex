CREATE TABLE "role" (
  "role_id" TEXT PRIMARY KEY,
  "role_title" TEXT NOT NULL,
  "job_family" TEXT NOT NULL,
  "level" INTEGER NOT NULL,
  "is_people_manager_track" INTEGER NOT NULL
);

CREATE TABLE "compensation_band" (
  "band_id" TEXT PRIMARY KEY,
  "role_id" TEXT NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  "currency" TEXT NOT NULL,
  "annual_min" INTEGER NOT NULL,
  "annual_mid" INTEGER NOT NULL,
  "annual_max" INTEGER NOT NULL,
  FOREIGN KEY ("role_id") REFERENCES "role" ("role_id")
);

CREATE TABLE "employee" (
  "employee_id" TEXT PRIMARY KEY,
  "hire_date" TEXT NOT NULL,
  "initial_role_id" TEXT NOT NULL,
  "employment_type" TEXT NOT NULL,
  "recorded_at" TEXT NOT NULL,
  FOREIGN KEY ("initial_role_id") REFERENCES "role" ("role_id")
);

CREATE TABLE "team" (
  "team_id" TEXT PRIMARY KEY,
  "team_name" TEXT NOT NULL,
  "job_family" TEXT NOT NULL,
  "manager_employee_id" TEXT NOT NULL,
  "planned_peak_quarter" INTEGER NOT NULL,
  "created_date" TEXT NOT NULL,
  FOREIGN KEY ("manager_employee_id") REFERENCES "employee" ("employee_id")
);

CREATE TABLE "employee_team_assignment" (
  "assignment_id" TEXT PRIMARY KEY,
  "employee_id" TEXT NOT NULL,
  "team_id" TEXT NOT NULL,
  "effective_from" TEXT NOT NULL,
  "effective_to" TEXT,
  "change_reason" TEXT NOT NULL,
  FOREIGN KEY ("employee_id") REFERENCES "employee" ("employee_id"),
  FOREIGN KEY ("team_id") REFERENCES "team" ("team_id")
);

CREATE TABLE "tenure_snapshot" (
  "snapshot_id" TEXT PRIMARY KEY,
  "employee_id" TEXT NOT NULL,
  "snapshot_quarter" TEXT NOT NULL,
  "snapshot_date" TEXT NOT NULL,
  "role_id" TEXT NOT NULL,
  "team_id" TEXT NOT NULL,
  "tenure_months" INTEGER NOT NULL,
  "months_since_last_promotion" INTEGER NOT NULL,
  "months_in_current_team" INTEGER NOT NULL,
  "base_salary_annual" INTEGER NOT NULL,
  "compa_ratio" REAL NOT NULL,
  "transfer_in_quarter" INTEGER NOT NULL,
  "promotion_in_quarter" INTEGER NOT NULL,
  "recorded_at" TEXT NOT NULL,
  FOREIGN KEY ("employee_id") REFERENCES "employee" ("employee_id"),
  FOREIGN KEY ("role_id") REFERENCES "role" ("role_id"),
  FOREIGN KEY ("team_id") REFERENCES "team" ("team_id")
);

CREATE TABLE "engagement_survey" (
  "survey_id" TEXT PRIMARY KEY,
  "employee_id" TEXT NOT NULL,
  "snapshot_id" TEXT NOT NULL,
  "survey_date" TEXT NOT NULL,
  "response_status" TEXT NOT NULL,
  "q_manager_support" INTEGER,
  "q_growth_opportunity" INTEGER,
  "q_workload_sustainable" INTEGER,
  "q_recognition" INTEGER,
  "q_intent_to_stay" INTEGER,
  "items_answered" INTEGER NOT NULL,
  "engagement_score" REAL,
  "recorded_at" TEXT NOT NULL,
  FOREIGN KEY ("employee_id") REFERENCES "employee" ("employee_id"),
  FOREIGN KEY ("snapshot_id") REFERENCES "tenure_snapshot" ("snapshot_id")
);

CREATE TABLE "workload_snapshot" (
  "workload_id" TEXT PRIMARY KEY,
  "employee_id" TEXT NOT NULL,
  "snapshot_id" TEXT NOT NULL,
  "avg_weekly_hours" REAL NOT NULL,
  "active_project_count" INTEGER NOT NULL,
  "on_call_days" INTEGER NOT NULL,
  "planned_peak_flag" INTEGER NOT NULL,
  "overtime_hours_quarter" REAL NOT NULL,
  "workload_index" REAL NOT NULL,
  "high_load_flag" INTEGER NOT NULL,
  "recorded_at" TEXT NOT NULL,
  FOREIGN KEY ("employee_id") REFERENCES "employee" ("employee_id"),
  FOREIGN KEY ("snapshot_id") REFERENCES "tenure_snapshot" ("snapshot_id")
);

CREATE TABLE "promotion_history" (
  "promotion_id" TEXT PRIMARY KEY,
  "employee_id" TEXT NOT NULL,
  "event_type" TEXT NOT NULL,
  "effective_date" TEXT NOT NULL,
  "from_role_id" TEXT NOT NULL,
  "to_role_id" TEXT NOT NULL,
  "prior_base_salary_annual" INTEGER NOT NULL,
  "new_base_salary_annual" INTEGER NOT NULL,
  "salary_change_pct" REAL NOT NULL,
  "recorded_at" TEXT NOT NULL,
  FOREIGN KEY ("employee_id") REFERENCES "employee" ("employee_id"),
  FOREIGN KEY ("from_role_id") REFERENCES "role" ("role_id"),
  FOREIGN KEY ("to_role_id") REFERENCES "role" ("role_id")
);

CREATE TABLE "attrition_outcome" (
  "outcome_id" TEXT PRIMARY KEY,
  "employee_id" TEXT NOT NULL,
  "final_status" TEXT NOT NULL,
  "termination_date" TEXT,
  "termination_reason_category" TEXT,
  "prediction_cutoff_date" TEXT NOT NULL,
  "horizon_end_date" TEXT NOT NULL,
  "eligible_at_cutoff" INTEGER NOT NULL,
  "voluntary_attrition_label" INTEGER,
  "label_rule_version" TEXT NOT NULL,
  "recorded_at" TEXT NOT NULL,
  FOREIGN KEY ("employee_id") REFERENCES "employee" ("employee_id")
);

CREATE TABLE "intervention" (
  "intervention_id" TEXT PRIMARY KEY,
  "employee_id" TEXT NOT NULL,
  "trigger_snapshot_id" TEXT NOT NULL,
  "trigger_source" TEXT NOT NULL,
  "intervention_type" TEXT NOT NULL,
  "signal_score" REAL,
  "signal_top_factors" TEXT,
  "review_status" TEXT NOT NULL,
  "reviewed_by_employee_id" TEXT,
  "reviewed_date" TEXT,
  "proposed_date" TEXT NOT NULL,
  "conducted_date" TEXT,
  "closed_date" TEXT,
  "status" TEXT NOT NULL,
  "hazard_multiplier" REAL NOT NULL,
  "engagement_delta" REAL,
  "outcome_category" TEXT NOT NULL,
  "left_within_2_quarters" INTEGER,
  FOREIGN KEY ("employee_id") REFERENCES "employee" ("employee_id"),
  FOREIGN KEY ("trigger_snapshot_id") REFERENCES "tenure_snapshot" ("snapshot_id"),
  FOREIGN KEY ("reviewed_by_employee_id") REFERENCES "employee" ("employee_id")
);
