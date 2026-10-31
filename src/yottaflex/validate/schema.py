"""Machine-readable version of docs/data_dictionary.md.

The first column of every table is its primary key. `coerce` turns CSV strings or
generated frames into typed frames and reports values that cannot be parsed.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .. import config


@dataclass(frozen=True)
class Col:
    name: str
    typ: str = "str"            # str | int | float | bool | date | datetime
    req: bool = True
    allowed: tuple | None = None
    lo: float | None = None
    hi: float | None = None
    fk: tuple | None = None      # (parent_table, parent_column)
    kind: str | None = None      # ID format key in yottaflex.ids.PATTERNS


def C(name, typ="str", req=True, **kw) -> Col:
    return Col(name, typ, req, **kw)


FAM, LV = config.JOB_FAMILIES, config.LEVELS
SCHEMA: dict[str, list[Col]] = {
    "role": [C("role_id", kind="role"), C("role_title"), C("job_family", allowed=FAM),
             C("level", "int", allowed=LV), C("is_people_manager_track", "bool")],
    "compensation_band": [
        C("band_id", kind="band"), C("role_id", fk=("role", "role_id")), C("effective_from", "date"),
        C("effective_to", "date", False), C("currency", allowed=("INR",)), C("annual_min", "int", lo=1),
        C("annual_mid", "int", lo=1), C("annual_max", "int", lo=1)],
    "employee": [
        C("employee_id", kind="employee"), C("hire_date", "date"),
        C("initial_role_id", fk=("role", "role_id")), C("employment_type", allowed=config.EMPLOYMENT_TYPES),
        C("recorded_at", "datetime")],
    "team": [
        C("team_id", kind="team"), C("team_name"), C("job_family", allowed=FAM),
        C("manager_employee_id", fk=("employee", "employee_id")), C("planned_peak_quarter", "int", lo=1, hi=4),
        C("created_date", "date")],
    "employee_team_assignment": [
        C("assignment_id", kind="assignment"), C("employee_id", fk=("employee", "employee_id")),
        C("team_id", fk=("team", "team_id")), C("effective_from", "date"), C("effective_to", "date", False),
        C("change_reason", allowed=config.ASSIGNMENT_REASONS)],
    "tenure_snapshot": [
        C("snapshot_id", kind="snapshot"), C("employee_id", fk=("employee", "employee_id")),
        C("snapshot_quarter", allowed=config.QUARTERS), C("snapshot_date", "date"),
        C("role_id", fk=("role", "role_id")), C("team_id", fk=("team", "team_id")),
        C("tenure_months", "int", lo=0), C("months_since_last_promotion", "int", lo=0),
        C("months_in_current_team", "int", lo=0), C("base_salary_annual", "int", lo=1),
        C("compa_ratio", "float", lo=0.70, hi=1.40), C("transfer_in_quarter", "bool"),
        C("promotion_in_quarter", "bool"), C("recorded_at", "datetime")],
    "engagement_survey": [
        C("survey_id", kind="survey"), C("employee_id", fk=("employee", "employee_id")),
        C("snapshot_id", fk=("tenure_snapshot", "snapshot_id")), C("survey_date", "date"),
        C("response_status", allowed=config.SURVEY_STATUSES),
        *[C(q, "int", False, lo=1, hi=5) for q in ("q_manager_support", "q_growth_opportunity",
                                                  "q_workload_sustainable", "q_recognition", "q_intent_to_stay")],
        C("items_answered", "int", lo=0, hi=5), C("engagement_score", "float", False, lo=0, hi=100),
        C("recorded_at", "datetime")],
    "workload_snapshot": [
        C("workload_id", kind="workload"), C("employee_id", fk=("employee", "employee_id")),
        C("snapshot_id", fk=("tenure_snapshot", "snapshot_id")),
        C("avg_weekly_hours", "float", lo=30.0, hi=65.0), C("active_project_count", "int", lo=0, hi=12),
        C("on_call_days", "int", lo=0, hi=30), C("planned_peak_flag", "bool"),
        C("overtime_hours_quarter", "float", lo=0), C("workload_index", "float", lo=0, hi=100),
        C("high_load_flag", "bool"), C("recorded_at", "datetime")],
    "promotion_history": [
        C("promotion_id", kind="promotion"), C("employee_id", fk=("employee", "employee_id")),
        C("event_type", allowed=config.PROMOTION_EVENT_TYPES), C("effective_date", "date"),
        C("from_role_id", fk=("role", "role_id")), C("to_role_id", fk=("role", "role_id")),
        C("prior_base_salary_annual", "int", lo=1), C("new_base_salary_annual", "int", lo=1),
        C("salary_change_pct", "float"), C("recorded_at", "datetime")],
    "attrition_outcome": [
        C("outcome_id", kind="outcome"), C("employee_id", fk=("employee", "employee_id")),
        C("final_status", allowed=config.FINAL_STATUSES), C("termination_date", "date", False),
        C("termination_reason_category", "str", False, allowed=config.TERMINATION_REASONS),
        C("prediction_cutoff_date", "date"), C("horizon_end_date", "date"), C("eligible_at_cutoff", "bool"),
        C("voluntary_attrition_label", "int", False, allowed=(0, 1)),
        C("label_rule_version", allowed=(config.LABEL_RULE_VERSION,)), C("recorded_at", "datetime")],
    "intervention": [
        C("intervention_id", kind="intervention"), C("employee_id", fk=("employee", "employee_id")),
        C("trigger_snapshot_id", fk=("tenure_snapshot", "snapshot_id")),
        C("trigger_source", allowed=config.TRIGGER_SOURCES), C("intervention_type", allowed=config.INTERVENTION_TYPES),
        C("signal_score", "float", False, lo=0, hi=1), C("signal_top_factors", "str", False),
        C("review_status", allowed=config.REVIEW_STATUSES),
        C("reviewed_by_employee_id", "str", False, fk=("employee", "employee_id")),
        C("reviewed_date", "date", False), C("proposed_date", "date"), C("conducted_date", "date", False),
        C("closed_date", "date", False), C("status", allowed=config.INTERVENTION_STATUSES),
        C("hazard_multiplier", "float", lo=0.5, hi=1.0), C("engagement_delta", "float", False),
        C("outcome_category", allowed=("Improved", "No_Change", "Declined", "Not_Applicable")),
        C("left_within_2_quarters", "bool", False)],
}
GROUND_TRUTH = [
    C("gt_id", kind="ground_truth"), C("issue_type", allowed=config.ISSUE_TYPES), C("issue_subtype"),
    C("entity", allowed=tuple(SCHEMA)), C("record_id"), C("field", "str", False),
    C("original_value", "str", False), C("expected_decision", allowed=config.EXPECTED_DECISIONS),
    C("is_injected", "bool"), C("description")]

_BOOL = {True: True, False: False, "True": True, "False": False, "true": True, "false": False}


def _coerce_col(s: pd.Series, typ: str) -> pd.Series:
    if typ == "str":
        return s.astype("object").where(s.notna(), None)
    if typ == "int":
        num = pd.to_numeric(s, errors="coerce")
        num = num.where(num == num.round())            # non-integral values fail
        return num.astype("Int64")
    if typ == "float":
        return pd.to_numeric(s, errors="coerce").astype("float64")
    if typ == "bool":
        return s.map(lambda v: _BOOL.get(v, pd.NA) if not pd.isna(v) else pd.NA).astype("boolean")
    if typ == "date":
        return pd.to_datetime(s, errors="coerce", format="mixed").dt.normalize().astype("datetime64[ns]")
    if typ == "datetime":
        return pd.to_datetime(s, errors="coerce", utc=True, format="mixed").dt.tz_localize(None).astype("datetime64[ns]")
    raise ValueError(typ)


def coerce(df: pd.DataFrame, cols: list[Col]) -> tuple[pd.DataFrame, list[int], list[str]]:
    """Return (typed frame, row positions with an unparseable value, column-structure problems)."""
    problems = []
    names = [c.name for c in cols]
    if list(df.columns) != names:
        missing, extra = [n for n in names if n not in df.columns], [n for n in df.columns if n not in names]
        problems.append(f"missing={missing} extra={extra} order_ok={[n for n in df.columns if n in names] == [n for n in names if n in df.columns]}")
    out = pd.DataFrame(index=df.index)
    bad = pd.Series(False, index=df.index)
    for c in cols:
        if c.name not in df.columns:
            out[c.name] = pd.Series([pd.NA] * len(df), index=df.index)
            continue
        typed = _coerce_col(df[c.name], c.typ)
        bad |= (df[c.name].notna() & typed.isna()).to_numpy()
        out[c.name] = typed
    return out.reset_index(drop=True), [int(i) for i in bad.to_numpy().nonzero()[0]], problems