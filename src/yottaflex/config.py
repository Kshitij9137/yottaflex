"""Single source of truth for constants shared by the generator, validators and model.

Values mirror docs/design_decisions.md. Change them there first, then here.
"""
from __future__ import annotations

from datetime import date

SEED = 20261022

# --- Time window: 24 months, 8 quarterly snapshots -------------------------
WINDOW_START = date(2024, 10, 1)
WINDOW_END = date(2026, 9, 30)
QUARTERS = (
    "2024Q4", "2025Q1", "2025Q2", "2025Q3",
    "2025Q4", "2026Q1", "2026Q2", "2026Q3",
)

# --- Temporal evaluation: 6-month horizon after each cutoff ----------------
HORIZON_MONTHS = 6
CUTOFFS = {
    "train": date(2025, 3, 31),
    "validation": date(2025, 9, 30),
    "test": date(2026, 3, 31),
}
HORIZON_ENDS = {
    "train": date(2025, 9, 30),
    "validation": date(2026, 3, 31),
    "test": date(2026, 9, 30),
}
OUTCOME_YEAR = 2026
LABEL_RULE_VERSION = "v1"

# --- Attrition calibration --------------------------------------------------
TARGET_VOLUNTARY_ATTRITION = 0.10
TOTAL_ATTRITION_BOUNDS = (0.05, 0.15)

# --- Enumerations -----------------------------------------------------------
JOB_FAMILIES = (
    "Engineering", "Product", "Sales", "Customer_Support",
    "Operations", "IT_Ops", "People_HR",
)
LEVELS = (1, 2, 3, 4, 5)
EMPLOYMENT_TYPES = ("Full_Time", "Fixed_Term")
ASSIGNMENT_REASONS = ("Hire", "Internal_Transfer", "Reorg")
SURVEY_STATUSES = ("Responded", "Partial", "Skipped")
PROMOTION_EVENT_TYPES = ("Promotion", "Lateral_Move")
FINAL_STATUSES = ("Active", "Exited_Voluntary", "Exited_Involuntary")
TERMINATION_REASONS = (
    "Better_Opportunity", "Career_Growth", "Compensation", "Workload", "Other",
)
TRIGGER_SOURCES = ("Signal_Flagged", "Manager_Initiated", "HR_Initiated")
INTERVENTION_TYPES = (
    "Stay_Conversation", "Workload_Rebalance",
    "Career_Path_Discussion", "Compensation_Review",
)
REVIEW_STATUSES = ("Not_Required", "Pending", "Approved", "Declined")
INTERVENTION_STATUSES = ("Proposed", "Approved", "Conducted", "Closed", "Declined")
ISSUE_TYPES = (
    "future_information_leak", "missing_survey_as_negative",
    "label_termination_mismatch", "unreviewed_individual_score",
    "benign_high_workload", "benign_internal_transfer", "benign_missing_survey",
)
EXPECTED_DECISIONS = ("flag", "do_not_flag")

# Columns that must never reach model features (post-outcome or ground truth).
FORBIDDEN_FEATURE_COLUMNS = frozenset({
    "final_status", "termination_date", "termination_reason_category",
    "voluntary_attrition_label", "horizon_end_date",
    "issue_type", "expected_decision", "is_injected", "original_value",
})